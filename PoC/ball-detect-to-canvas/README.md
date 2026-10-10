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

- **Set corners manually:** freeze a calibration frame and click/drag top-left → top-right → bottom-right → bottom-left at the inner cushion boundaries. Resume live analysis with those corners. Return to automatic detection when desired.
- **Save current corners / Use saved corners:** store a manual calibration in this browser. Reuse requires matching frame dimensions. Check that the camera position is unchanged; matching dimensions alone do not establish that.
- **Table proportions:** actual cloth width / height, usually 2:1. Keep the table's long dimension horizontal in the mapped view.
- **Ball radius:** `ball diameter / (2 × short playing-surface dimension)`. For 57.15 mm balls and 1,120 mm cloth height, use approximately 2.55%.
- **Cloth hue tolerance, touching separation, ball IDs, and grid** for optional tuning/display changes. Live settings take effect automatically. Still images use **Apply to image**.
- **Try sample / Upload photo** for testing without a camera, and **Export layout** for normalized JSON.

The sample is explicitly synthetic: 12 balls, including a touching pair, with pockets and a cue fragment as distractors. The same automatic table/ball detector processes its pixels; displayed positions are not hardcoded. Synthetic tests are not a measurement of real-camera accuracy.

Select a ball on the canvas to inspect its type and coordinates. Keyboard users can focus the canvas, use left/right arrows to select a ball, and Escape to clear selection.

## Detection pipeline

1. Validate/decode the image and normalize EXIF orientation. Live frames are JPEGs captured at no more than 1,280 × 960 pixels, retaining their original aspect ratio.
2. Generate HSV, low-saturation, and LAB color masks. Denoise the masks and score convex regions by color coverage, convexity, and straightness. Fit robust lines along rail edges, excluding pockets, and intersect them to recover the four corners. Refine inward toward coherent cushion seams. Apply a homography to a 1,000-pixel-wide rectangle of the configured physical ratio. Locked/manual calibration bypasses corner finding.
3. Segment the cloth with circular hue distance and saturation/value thresholds. Hue consistency suppresses cloth shadows; pale/grey cloth uses local lightness and chroma contrast instead. Morphological opening/closing and filled contours clean the mask.
4. Filter components by area, circularity, aspect ratio, and expected radius. Fit contour circles and add edge-supported Hough proposals, including balls that resemble cloth colors. Border checks reject clipped pocket fragments; suppress duplicate centers.
5. Seed distance-transform maxima inside touching regions and watershed their foreground silhouettes. Hough can still separate some touching balls when watershed is disabled.
6. Classify central ball pixels using saturated color, darkness, white-area proportion, and white distribution across outer sectors. Return `cue`, `eight`, `solid`, `striped`, or `unknown`, with an explanation and heuristic rule score. The score is **not a calibrated probability**.
7. Map centers to normalized cloth coordinates and invert the homography for the camera overlay.

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

## Pi and practical limits

Use 64-bit Raspberry Pi OS and Python 3.11–3.13. OpenCV is headless and CPU-only. Benchmark on the actual Pi: no Pi hardware performance claim is made. `npm run build` and `npm run preview` serve a local production bundle; for deployment, configure a proper static host/reverse proxy. Development servers bind to loopback by default. Camera access requires **localhost or HTTPS**; plain HTTP over a Pi's LAN IP will generally not allow browser-camera capture. The browser sees cameras attached to its own device, not a remote Pi CSI camera. A Pi capture service can submit frames to the same API later.

Limitations:

- Automatic table finding assumes a dominant, approximately uniform cloth region with all four corners visible. A similarly colored background may produce an incorrect quadrilateral; manual corners remain available.
- Real-camera precision/recall and classification accuracy have not been measured. Test labeled frames from the intended fixed camera before relying on positions downstream.
- Homography maps the cloth plane. Ball height creates parallax with angled cameras; correction needs camera extrinsics and a sphere model. Rectification can also stretch silhouettes.
- Lighting, reflections, hands, deep shadows, cloth-colored balls, and motion blur can cause misses or false positives.
- Touching separation is best effort. Fully occluded balls cannot be reconstructed reliably from a single view.
- An invisible stripe can make a stripe ball look solid. “Unknown” handles visible ambiguity but cannot reveal hidden evidence.
- The backend is stateless. Fixed-camera frontend filtering reduces display jitter and brief dropouts, but does not detect shot completion, compensate camera motion, read ball numbers, or predict trajectories. A falsely detected position can persist briefly; a wrong but consistent corner estimate can still lock. Recalibrate or set corners manually when needed.

The next accuracy milestone is a labeled set of frames from your real table, with center error, missed/extra detections, and a type confusion matrix measured before threshold tuning.
