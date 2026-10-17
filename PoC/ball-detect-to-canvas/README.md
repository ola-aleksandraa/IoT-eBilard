# Ball / Detect

A minimal live pool-table detector: choose a camera, connect it, and see the balls mapped to a virtual table. React + TypeScript + Vite; FastAPI + headless OpenCV. No neural model, GPU, or cloud vision service.

## Start

Use Node.js 22.12+ (Node 24 tested), Python 3.11–3.13, and [uv](https://docs.astral.sh/uv/).

From `PoC/ball-detect-to-canvas`, start the backend:

```sh
cd backend
uv sync --python 3.12
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal, from `PoC/ball-detect-to-canvas`:

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. API docs: **http://127.0.0.1:8000/docs**. Vite proxies `/api` to port 8000. Both dependency lockfiles are included.

## Live camera workflow

1. Choose a camera and select **Connect camera**. Grant the browser camera permission. Before permission is granted, browsers may expose only “Default camera”; after connection, the picker shows the available camera names. Microphone access is never requested.
2. Frame the whole playing surface, including the four inner cushion corners. Leave **Camera is unstable** off for a fixed mount. The app collects eight consistent estimates (about four seconds at 2 Hz), rejects outliers, then locks the median corners. Subsequent requests reuse those corners and detect only the balls.
3. Watch the live camera feed and virtual table. The frontend targets **two detection updates per second**, with at most one request in flight. Slower hardware lowers the effective rate instead of queueing old frames. The camera video itself plays independently at its native preview rate.
4. Changing the camera stops the previous stream and starts the selected device. Disconnecting releases tracks, aborts pending requests, and clears the old layout. Unplugging a device also clears the connection.
5. Enable **Camera is unstable** to find corners independently on every frame. If the table disappears in this mode, the canvas clears and searches again. Press **Recalibrate corners** after moving a fixed camera; this clears the lock and gathers a fresh consensus. Switching cameras, capture resolution, or camera mode also resets calibration.

Fixed-camera display stabilization compares each observation with its displayed position. Changes below **0.6% of table height** stay still; modest changes need two consistent observations, while changes above three times that threshold update immediately. Slow real movement accumulates against the displayed anchor. Two missed frames are tolerated; the third removes a ball. New candidates require two observations after the first layout, and type changes require three. Adjust the tolerance in Settings. These nearest-position associations suppress noise; they do not guarantee ball identity through a shot. Unstable-camera mode displays fresh detections without this fixed-scene filter. Moving balls may blur; settled layouts remain the most reliable case.

The main screen contains the camera picker, connection control, instability switch, recalibration action, two views, and status. Everything else is under the **Settings** icon:

- **Set corners manually:** freeze a calibration frame and click/drag four corners clockwise at the inner cushion boundaries, with the first edge along the long side. **Rotate mapping** changes which edge becomes canvas width. Resume live analysis with those corners. Return to automatic detection when desired.
- **Save current corners / Use saved corners:** store a manual calibration in this browser. Reuse requires matching frame dimensions. Check that the camera position is unchanged; matching dimensions alone do not establish that.
- **Table proportions:** actual cloth width / height, usually 2:1. Keep the table's long dimension horizontal in the mapped view.
- **Ball radius:** `ball diameter / (2 × short playing-surface dimension)`. For 57.15 mm balls and 1,120 mm cloth height, use approximately 2.55%.
- **Cloth hue tolerance, touching separation, ball IDs, and grid** for optional tuning/display changes. Live settings take effect automatically. Still images use **Apply to image**.
- **Try sample / Upload photo** for testing without a camera, and **Export layout** for normalized JSON.

The sample is explicitly synthetic: 12 balls, including a touching pair, with pockets and a cue fragment as distractors. The same automatic table/ball detector processes its pixels; displayed positions are not hardcoded. Synthetic tests are not a measurement of real-camera accuracy.

The canvas shows **White**, **Black**, **Full**, and **Half**; all fulls use amber and all halves use the same amber band. It deliberately ignores individual ball hues. Gray **?** markers retain uncertain balls. At most one white and one black classification is displayed; missing or pocketed balls are never invented to fill a quota.

Select a ball on the canvas to inspect its type and coordinates. Keyboard users can focus the canvas, use left/right arrows to select a ball, and Escape to clear selection.

## Detection pipeline

1. Validate/decode the image and normalize EXIF orientation. Live frames are JPEGs captured at no more than 1,280 × 960 pixels, retaining their original aspect ratio.
2. Find the cloth quadrilateral from HSV/LAB masks and robust rail-line fits. A centered pinhole-camera estimate chooses the likely long edge for automatic mapping; manual ordering is authoritative. Fixed-camera calibration locks this ordering with the corners. The homography targets a 1,000-pixel-wide rectangle of the configured physical ratio.
3. Detect balls in the **original camera image**, before planar warping can stretch their silhouettes. Remove cloth by hue/saturation/value, supplementing with local LAB contrast to recover cloth-colored balls and neutral cloth. Clean and fill the foreground mask.
4. Constrain circle size using the local scale of the table homography. Combine contour fits, distance-transform/watershed separation, and independently edge-supported Hough circles. Suppress duplicates and reject pocket fragments using location and surrounding cloth support.
5. Estimate a bounded white-balance correction from bright, weakly saturated table pixels. Classify each original-image ball crop using white/dark/colored area, core appearance, opposing white rim sectors, and dark markings. Broad white regions suggest halves; small number patches are allowed on fulls. No individual hue or number is recognized.
6. Resolve competing cue/eight claims at table level. Keep only the strongest visual special-ball claim; use visible pattern evidence for an alternate type or retain the candidate as unknown. No seven-full/seven-half quota or fixed total count is imposed. Rule scores are **not calibrated probabilities**.
7. Map source centers through the homography to normalized cloth coordinates; preserve source coordinates for the camera overlay. Canvas radii use the configured physical size rather than distorted image silhouettes.

[carrotdan/ai-billiard-system](https://github.com/carrotdan/ai-billiard-system) supplied context for perspective mapping, circle/blob detection, and touching separation. This is a separate implementation without vendored code or model assets; its neural classification path is replaced here by deterministic rules.

## API

| Endpoint | Input | Output |
|---|---|---|
| `GET /api/health` | — | Health and OpenCV version |
| `GET /api/demo` | — | Synthetic image, known corners, expected count |
| `POST /api/live` | Multipart `file`, optional JSON `config` | `table_status`, detected calibration, detection or `null` |
| `POST /api/prepare` | Multipart `file`, optional JSON `lens` | Canonical PNG, dimensions, suggested corners, lens status |
| `POST /api/detect` | Multipart `file`, JSON `config` with calibration | Detection plus rectified, mask, and overlay images |

`/api/live` finds table corners when `calibration` is omitted/null. A lost table returns `{"table_status":"searching","calibration":null,"detection":null}`. The endpoint is stateless and never reuses a prior layout. Live responses omit debug images to reduce transfer and encoding overhead.

Example live request:

```sh
curl http://127.0.0.1:8000/api/live \
  -F 'file=@frame.jpg' \
  -F 'config={"settings":{"table_ratio":2,"ball_radius_ratio":0.026}}'
```

For `/api/detect`, or a locked/manual calibration on `/api/live`, use:

```json
{
  "calibration": {
    "image_width": 1000,
    "image_height": 500,
    "corners": [
      {"x": 0, "y": 0}, {"x": 1, "y": 0},
      {"x": 1, "y": 1}, {"x": 0, "y": 1}
    ]
  },
  "settings": {
    "table_ratio": 2,
    "ball_radius_ratio": 0.026,
    "cloth_hue": null,
    "hue_tolerance": 16,
    "saturation_min": 55,
    "split_touching": true
  }
}
```

These example corners describe an already top-down full-frame image, not your camera's calibration.

Each ball contains `id`, `kind`, `x`, `y`, `radius`, `source_x`, `source_y`, `color`, `confidence`, `reason`, `white_fraction`, and `method`.

- `x`, `y`: normalized cloth-plane coordinates, `(0,0)` top-left to `(1,1)` bottom-right.
- `radius`: relative to table **height**. Render with `cx=x×width`, `cy=y×height`, `r=radius×height`.
- `color`: canonical display color for the category, not the measured ball hue. `solid` means Full; `striped` means Half.
- `source_x`, `source_y`: normalized centers in the prepared/captured source image.
- `id`: API responses use frame-local labels. Fixed-camera frontend layouts use session-local nearest-position associations. Neither is a printed ball number or guaranteed physical identity.
- `processing_ms`: server vision computation, excluding upload, decode, debug encoding, and network latency.

Images are processed in memory and not retained by the backend. Uploaded photos are limited to 12 MB, 16 megapixels, and 10,000 pixels per side. Canonical lossless PNGs sent to detect/live can be up to 64 MB because preparation may expand a compressed original; the pixel ceiling remains. One detection runs per backend process; concurrent requests get a retryable 503.

### Lens distortion (API only)

The minimal live UI does not configure camera intrinsics. For lens-corrected static images, calibrate the camera separately, then send a JSON `lens` field to `/api/prepare`:

```json
{
  "image_width": 1920,
  "image_height": 1080,
  "camera_matrix": [[1500, 0, 960], [0, 1500, 540], [0, 0, 1]],
  "distortion": [-0.1, 0.02, 0, 0, 0]
}
```

These numbers are illustrative, not a calibration for your camera. Intrinsics must match the EXIF-oriented input resolution. OpenCV distortion vectors of 4, 5, 8, 12, or 14 values are supported. Use the returned canonical PNG to choose corners and detect; do not undistort it twice. Four cloth corners alone cannot determine lens distortion. Live mode currently assumes lens distortion is small or the input is already corrected.

## Tests

```sh
npm test
npm run build
cd backend
uv run pytest -q
```

- Backend tests: ground-truth localization under brightness changes, cue/pocket rejection, touching separation independently of Hough, classification/unknown rules, hue wraparound, inverse mapping, malformed input, EXIF/lens handling, and automatic table loss/reacquisition.
- Frontend tests: mocked camera lifecycle, cancellation, sequential requests, corner consensus/outlier rejection, fixed lock and recalibration, unstable mode, stationary jitter, real motion, dropouts, and type hysteresis.
- Camera lifecycle tests use simulated media devices; they do not access your physical camera. The mounted camera still needs its own validation.

### Real tournament images

Ball detection/classification was checked against **247 annotated tournament screenshots** from [Pix2Pockets](https://pix2pockets.compute.dtu.dk/) / [the authors’ dataset archive](https://github.com/viktorseba/pix2pockets/blob/main/8-Ball-Pool-3.zip), exported from the [8-Ball Pool dataset](https://universe.roboflow.com/bachelorthesis/8-ball-pool-l530o) (CC BY 4.0). No images or third-party executable code are bundled here.

The development split contains 198 frames. A reserved split contains 49 frames / 535 annotated balls: filenames with a leading numeric ID divisible by five. Related angle suffixes stay together. This is our split of the archive’s training folder, **not the authors’ official test split**; frames from the same tournaments remain correlated. The holdout was not used for threshold tuning. Annotation noise, small balls, occlusion, and incorrect automatically found tables are included.

| Reserved 49-frame result | Previous pipeline | Current pipeline |
|---|---:|---:|
| Located annotated balls | 289 / 535 (54.0%) | 469 / 535 (87.7%) |
| Center-match precision | 97.0% | 96.1% |
| Correct type among matched balls | 55.0% | 76.8% |
| Correctly located **and** typed / all annotations | 29.7% | 67.3% |
| Missed / extra detections | 246 / 9 | 66 / 19 |

Matches are one-to-one, greedily ordered by center error normalized by annotation size, with a maximum distance of 0.65 × the larger annotated box dimension. These are **center-match metrics, not object-detection AP or measured cloth-coordinate error**. Unknown counts as an incorrect type. Median end-to-end vision time was about 158 ms on the development Mac, including automatic table finding and excluding image decoding/transport; this is not a Raspberry Pi measurement. The previous pipeline is commit `921559b`.

Reproduce the ball benchmark (the script verifies the archive’s SHA-256):

```sh
curl -L 'https://raw.githubusercontent.com/viktorseba/pix2pockets/main/8-Ball-Pool-3.zip' -o /tmp/pool-tournament.zip
cd backend
uv run python scripts/benchmark_balls.py /tmp/pool-tournament.zip --split holdout
# Optional: --split development, --split all, --output /tmp/ball-results.json
```

This measures ball centers and types only. The detector does not reliably classify every visible ball in arbitrary tournament footage.

## Pi and practical limits

Use 64-bit Raspberry Pi OS and Python 3.11–3.13. OpenCV is headless and CPU-only. Benchmark on the actual Pi: no Pi hardware performance claim is made. `npm run build` and `npm run preview` serve a local production bundle; for deployment, configure a proper static host/reverse proxy. Development servers bind to loopback by default. Camera access requires **localhost or HTTPS**; plain HTTP over a Pi's LAN IP will generally not allow browser-camera capture. The browser sees cameras attached to its own device, not a remote Pi CSI camera. A Pi capture service can submit frames to the same API later.

Limitations:

- Automatic table finding assumes a dominant, approximately uniform cloth region with all four corners visible. A similarly colored background may produce an incorrect quadrilateral; manual corners remain available.
- Tournament-frame results below do not establish accuracy on your camera. Validate frames from the intended fixed setup before consuming positions downstream.
- Homography maps the cloth plane. Ball height creates parallax with angled cameras; correction needs camera extrinsics and a sphere model. Ball silhouettes are analyzed before rectification, but mapped centers still have this parallax error.
- Lighting, reflections, hands, deep shadows, cloth-colored balls, and motion blur can cause misses or false positives.
- Touching separation is best effort. Fully occluded balls cannot be reconstructed reliably from a single view.
- An invisible stripe can make a stripe ball look solid. “Unknown” handles visible ambiguity but cannot reveal hidden evidence.
- The backend is stateless. Fixed-camera frontend filtering reduces display jitter and brief dropouts, but does not detect shot completion, compensate camera motion, read ball numbers, or track ball motion. Shot *planning* (not motion tracking) is available through `POST /api/shots`, see below. A falsely detected position can persist briefly; a wrong but consistent corner estimate can still lock. Recalibrate or set corners manually when needed.

For a fixed installation, consistent exposure, a tighter table crop, and enough pixels per ball are more useful than forcing uncertain classifications.

## Shot predictions (ghost-ball planner)

`POST /api/shots` plans shots for the white ball with the engine in `backend/app/trajectory/` (adapted from [ai-billiard-system](https://github.com/carrotdan/ai-billiard-system)). It takes the balls from `/api/detect` in the same 0-1 table coordinates:

```json
{"balls": [{"id": 0, "kind": "cue", "x": 0.25, "y": 0.5, "radius": 0.026}, {"id": 1, "kind": "solid", "x": 0.6, "y": 0.4, "radius": 0.026}],
 "table_ratio": 2.0, "top_n": 5, "include_bank": true, "include_blocked": false}
```

and returns ranked direct and one-cushion bank shots with `cue_path`, `target_path`, `cue_deflect_path` (white ball after contact), `ghost_pos`, `score`, `cut_angle` and `velocity_remaining` (0-1). Enable **Show shot predictions** in Settings to draw them on the virtual table. The engine works in pixels on a table 1000 px wide (`service.ENGINE_WIDTH`); physics constants live in `app/trajectory/config.py`.

Scope: this plans where to aim and where the white ball goes after contact. It does not read the cue stick direction and has no spin or throw model.
