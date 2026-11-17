"""Background loop: poll the Pi camera, detect table changes, store settled layouts.

The watcher is the only client of the Pi's camera routes (the Pi runs one capture at a time and
answers 503 otherwise); the frontend reads the latest frame from GET /api/v1/table/live.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from .config import WatchConfig
from .pi_client import PiBusy, PiClient, PiError
from .repository import load_baseline, store_layout
from .schemas import LiveBall, LiveTable, WatcherStatus
from .stability import Frame, TableStateTracker, TrackedBall

log = logging.getLogger("ebilard.watcher")


class TableWatcher:
    def __init__(self, config: WatchConfig, session_factory: sessionmaker[Session],
                 pi: PiClient | None = None, sleep: Callable[[float], bool] | None = None):
        self.config = config
        self.pi = pi or PiClient(config.pi_url, config.pi_timeout_s)
        self._session_factory = session_factory
        self._stop = threading.Event()
        self._sleep = sleep or self._stop.wait  # returns True when stopping
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._calibration: dict | None = None
        self._misses = 0
        self.tracker = TableStateTracker(config.stability)
        self.frames_seen = 0
        self.states_stored = 0
        self.last_state_id = None
        self.last_error: str | None = None
        self.live: LiveTable | None = None

    # ----- lifecycle -------------------------------------------------------------------------

    def load_baseline(self) -> None:
        baseline = load_baseline(self._session_factory, self.config.table_width_cm,
                                 self.config.table_length_cm, self.config.ball_radius_ratio)
        self.tracker = TableStateTracker(self.config.stability, baseline=baseline)

    def start(self) -> None:
        self.load_baseline()
        self._thread = threading.Thread(target=self._run, name="table-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.config.pi_timeout_s + 2)
        self.pi.close()

    def _run(self) -> None:
        log.info("table watcher started (Pi %s, every %d ms)", self.config.pi_url, self.config.interval_ms)
        while not self._stop.is_set():
            try:
                self.step()
            except Exception as exc:  # never let the loop die
                log.exception("table watcher step failed")
                self.last_error = f"{type(exc).__name__}: {exc}"
            if self._sleep(self.config.interval_ms / 1000):
                break

    # ----- one iteration ---------------------------------------------------------------------

    def step(self) -> None:
        """Capture one frame through the Pi and feed it to the change detector."""
        settings = self.config.pi_settings
        try:
            if self._calibration is None:
                self._calibration = self.pi.calibrate(settings)
                if self._calibration is None:
                    self._lost("table not found during calibration")
                    return
            result = self.pi.detect(settings, self._calibration)
        except PiBusy:
            return  # not a gap in observation worth resetting for; just try again next tick
        except PiError as exc:
            self._lost(str(exc))
            return

        self.frames_seen += 1
        frame = self._to_frame(result)
        if frame.balls is None:
            self._lost("table not visible in frame")
            return
        self._misses = 0
        self.last_error = None
        with self._lock:
            settled = self.tracker.update(frame)
        if settled is not None:
            state_id = store_layout(self._session_factory, settled,
                                    self.config.table_width_cm, self.config.table_length_cm)
            self.states_stored += 1
            self.last_state_id = state_id
            log.info("stored table state %s with %d balls", state_id, len(settled.balls))

    def _lost(self, reason: str) -> None:
        self.last_error = reason
        self._misses += 1
        with self._lock:
            self.tracker.update(Frame(balls=None))
        if self._misses >= self.config.recalibrate_after:
            self._calibration = None  # camera may have moved: find the table again
            self._misses = 0

    def _to_frame(self, result: dict) -> Frame:
        acquired_at = datetime.fromisoformat(result["source"]["acquired_at"]) if result.get("source") else None
        detection = result.get("detection")
        detected = result.get("table_status") == "detected" and detection is not None
        balls = [LiveBall(**{k: b[k] for k in ("id", "kind", "x", "y", "radius")})
                 for b in (detection["balls"] if detected else [])]
        self.live = LiveTable(table_status="detected" if detected else "searching",
                              frame_id=result.get("frame_id"), acquired_at=acquired_at,
                              table_ratio=self.config.table_ratio, balls=balls)
        if not detected:
            return Frame(balls=None, acquired_at=acquired_at, frame_id=result.get("frame_id"))
        tracked = tuple(TrackedBall(b.kind, b.x, b.y, b.radius) for b in balls)
        return Frame(balls=tracked, acquired_at=acquired_at, frame_id=result.get("frame_id"))

    # ----- reporting -------------------------------------------------------------------------

    def status(self) -> WatcherStatus:
        with self._lock:
            phase, filled = self.tracker.phase, self.tracker.window_filled
        return WatcherStatus(
            enabled=True, running=self._thread is not None and self._thread.is_alive(),
            phase=phase, window_size=self.config.window, window_filled=filled,
            calibrated=self._calibration is not None, frames_seen=self.frames_seen,
            states_stored=self.states_stored, last_state_id=self.last_state_id, last_error=self.last_error)
