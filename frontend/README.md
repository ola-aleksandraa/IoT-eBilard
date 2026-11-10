# eBilard frontend

React 19 + TypeScript + Vite, styled with [Panda CSS](https://panda-css.com). Uses **pnpm**.

```sh
pnpm install   # also runs `panda codegen` (prepare script) → styled-system/
pnpm dev       # both backends (:8001 website, :8002 Raspberry Pi) + Vite (http://localhost:4321)
pnpm dev:web   # Vite only
pnpm dev:api   # website backend only (needs uv on PATH)
pnpm dev:pi    # Raspberry Pi backend only (needs uv on PATH)
pnpm build
pnpm lint
```

`pnpm dev` ([scripts/dev.mjs](scripts/dev.mjs)) starts both FastAPI backends with
`uv run --frozen --python 3.12 uvicorn … --reload` (website on :8001, Raspberry Pi on :8002)
and then Vite. It reuses a backend that is already running, and skips one whose URL
(`BACKEND_URL` / `PI_URL`) points elsewhere. uv is found as `$UV`, `uv`, or
`mise exec uv -- uv`. Ctrl+C stops everything.

Vite proxies `/api` to the website backend (`BACKEND_URL`, default `http://127.0.0.1:8001`)
and `/pi` to the Raspberry Pi backend (`PI_URL`, default `http://127.0.0.1:8002`;
`/pi/api/v1/…` → `/api/v1/…`).

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_DETECT_INTERVAL_MS` | `7000` | How often the table view polls `POST /camera/detect` |
| `BACKEND_URL` | `http://127.0.0.1:8001` | Website backend (proxy target, `pnpm dev`) |
| `PI_URL` | `http://127.0.0.1:8002` | Raspberry Pi backend (proxy target, `pnpm dev`) |

`VITE_*` values go in `frontend/.env.local` (git-ignored) or inline, e.g.
`VITE_DETECT_INTERVAL_MS=5000 pnpm dev`; see [src/config.ts](src/config.ts).

### Data

The table view asks the Raspberry Pi for a detection (`POST /pi/api/v1/camera/detect`;
the Pi captures the frame itself) and the website backend for the "Pomóż mi" hint
(`POST /api/v1/shots`, optional). It polls every `VITE_DETECT_INTERVAL_MS`, one request
at a time; a failed poll keeps the last layout. The topbar shows "Dane: backend". If the
Pi is not reachable (it retries every 2 s for ~40 s at startup), the Figma mock from
`src/data/mock.ts` stays ("Dane: mock") and polling continues at the normal interval.

Without a camera, point the Pi backend at the test frame (a still image has one frame):

```sh
CAMERA_SOURCE=../frontend/public/demo/sample-table.png CAMERA_WARMUP_FRAMES=1 pnpm dev
```

Players, score, turn, stats and the table history are always mock: the backend
has no game state yet, and the history is interpolated from a rack.

Styles are written with Panda's `css()` and JSX patterns imported from
`styled-system/` (generated, git-ignored). Theme tokens live in `panda.config.ts`.
