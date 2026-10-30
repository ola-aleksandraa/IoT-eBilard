# Numerical ball-recognition backend

FastAPI + CPU-only OpenCV. A frame enters the service; numerical recognition
data leaves it. Rendering, colors, patterns and animation belong to the client.
The runtime contains no demo fixture, preview renderer, image encoder, image
response endpoint, base64 payload or debug-image switch.

## Start and API reference

Python **3.11–3.13** and [uv](https://docs.astral.sh/uv/) are required.
From the repository root:

```sh
cd backend
uv sync --python 3.12 --frozen
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

- Interactive docs: **[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)**
- Machine-readable contract: [http://127.0.0.1:8001/openapi.json](http://127.0.0.1:8001/openapi.json)
- Alternative reference: [http://127.0.0.1:8001/redoc](http://127.0.0.1:8001/redoc)
- Process health: [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health)

`/` redirects to `/docs`. The documentation pages are HTML; all application
success responses are JSON. There is no WebSocket requirement. Swagger's UI
assets use its default CDN. Use `--reload` during development and **one worker**
for a camera installation. Port 8001 avoids the original PoC's usual port 8000;
another port can be selected with `--port`.

The backend runs independently of `PoC/` and has no frontend startup dependency.
The lockfile pins the environment. `.env` files are not loaded automatically.
It binds to loopback by default; expose it through your application's configured
gateway when adding remote access/authentication.

## One environment for development and deployment

`pyproject.toml` and `uv.lock` define the supported Python 3.11–3.13 environment.
Python 3.12 is the documented default. The Python 3.7 downgrade was reverted;
Pydantic 1, Debian OpenCV 3.2 and the old `requirements-local.txt` are no longer
installation paths. Use the frozen lockfile above on both development and
server machines. This service uses Pydantic 2 and headless OpenCV 4.

## Public API

| Method and path | Input | Numerical response |
| --- | --- | --- |
| `GET /health` | — | Process and OpenCV version |
| `GET /api/v1/settings` | — | Default per-frame settings |
| `GET /api/v1/categories` | — | `cue`, `eight`, `solid`, `striped`, `unknown` and meanings |
| `POST /api/v1/images/calibrate` | Multipart `file`, optional JSON string `config` | Source dimensions, normalized corners, forward/inverse homographies |
| `POST /api/v1/images/detect` | Multipart `file`, optional JSON string `config` | Types, counts, normalized coordinates, geometry, decision evidence |
| `POST /api/v1/shots` | Normalized ball layout | Ranked direct/bank shot paths and scores |
| `POST /api/v1/shots/predict` | Layout and cue aim | First contact and pocket paths |
| `POST /api/v1/shots/simulate` | Layout, cue aim and power | Time-sampled ball motion, contacts, cushions and pots |
| `GET /api/v1/camera` | — | Server camera configuration, without accessing the device |
| `POST /api/v1/camera/calibrate` | Optional `CalibrationOptions` JSON body | Internal capture → calibration/geometry JSON |
| `POST /api/v1/camera/detect` | Optional `AnalysisOptions` JSON body | Internal capture → recognition JSON |

Upload options are a JSON string in a multipart form field because the file is
binary input. Camera requests use normal typed JSON bodies. Unknown options,
including the removed `debug` option, are rejected. No path returns a source
frame, rectified image, segmentation mask or rendered table.

```sh
curl -sS http://127.0.0.1:8001/api/v1/images/detect \
  -F 'file=@/absolute/path/frame.jpg' \
  -F 'config={"client_frame_id":"frame-42","settings":{"table_ratio":2,"ball_radius_ratio":0.026}}'

curl -sS http://127.0.0.1:8001/api/v1/images/calibrate \
  -F 'file=@/absolute/path/frame.jpg'

curl -sS -X POST http://127.0.0.1:8001/api/v1/camera/detect \
  -H 'Content-Type: application/json' -d '{}'
```

The OpenAPI schemas are the public contract for later web/mobile clients. Use
`AnalysisOptions`, `AnalysisResult`, `Ball`, `Counts`, `Geometry`, `Calibration`,
`LensCalibration`, `ShotsResult`, `PredictionResult` and `SimulationResult` from that contract when generating a client.

## Moving to another table

The routes and JSON vocabulary stay the same. The supported geometry is a
rectangular six-pocket pool table; snooker rules, carom tables and arbitrary
pocket arrangements are outside the current physics model.

1. Measure the inner playing surface (between cushion noses) and ball diameter
   in the same unit. Set `settings.table_ratio = long_side / short_side` and
   `settings.ball_radius_ratio = ball_diameter / (2 * short_side)`. The supported
   ranges are 1–3 and 0.012–0.06 respectively. The defaults are starting values,
   not measurements inferred from a perspective image.
2. Use automatic corners first. If the image contains several cloth-colored
   regions, supply `cloth_hue` (OpenCV HSV 0–179), `hue_tolerance` and
   `saturation_min`. Explicit color settings apply to both calibration and
   detection, for uploads and server-camera requests. With no hue override,
   calibration considers several color masks, including neutral cloth.
3. If automatic corners are inaccurate or partly obscured, supply four manual
   inner-cushion corners clockwise, starting along the long side. Recalibrate
   after moving the camera or changing resolution, crop or lens correction.
4. Send the returned `detection.balls` and `detection.geometry.table_ratio` to
   the shot endpoints. Keep the ratio with its layout; using the default ratio
   for a differently shaped table changes collision angles and clearances.

The verification client's **Settings → Table setup** converts physical
measurements to these settings and exposes cloth hue/saturation controls.
Existing ratio/radius sliders remain available. Photos require **Apply to image**
after a setting change; the live camera uses updated settings on the next frame.
There is no table-specific endpoint or stored server-side table state.

## Coordinate mathematics

Each ball has `x`, `y` in `[0,1]`: the center relative to cloth width/height.
The origin is the first calibration corner, with positive x to the right and
positive y down in the mapped rectangle. `radius` is relative to **table height**.
The frontend chooses its size and draws using:

```text
W / H = geometry.table_ratio
center_x = left + ball.x * W
center_y = top  + ball.y * H
radius   = ball.radius * H
```

For discrete raster pixel indices, use `W-1` and `H-1` for center coordinates.
Do not multiply radius by width or turn it into an ellipse. No frontend resolution
is imposed by the API. If physical cloth dimensions are known, positions in those
units are `ball.x * cloth_width`, `ball.y * cloth_height`.

`detection.geometry.source_to_table` is a 3×3 homography from **oriented source
pixels** to **normalized cloth coordinates**. For source pixel `(u,v)`:

```text
q = h31*u + h32*v + h33
x = (h11*u + h12*v + h13) / q
y = (h21*u + h22*v + h23) / q
```

`table_to_source` is its inverse: multiply `[x,y,1]`, then divide the first two
components by the third to recover source pixels. Ball `source_x` and `source_y`
are normalized source centers, so use `u=source_x*(source.width-1)` and
`v=source_y*(source.height-1)` before the forward transform. Reprojection tests
check that these equations agree with returned ball positions.

`geometry.source_space` states whether the source pixels are EXIF-oriented only,
or also lens-corrected. Corrected coordinates do not directly overlay an
uncorrected camera image; use matching correction or the table coordinates.

## Result semantics

`schema_version` identifies the numerical contract. `frame_id` uniquely identifies
the server analysis. Optional `client_frame_id` is echoed unchanged so a client
can correlate its own frames and discard late results. `source.acquired_at` is
server acquisition time; for uploads it is assigned after decoding and is not
the camera's original exposure timestamp.

`table_status=detected` includes `calibration` and `detection`.
`table_status=searching` includes `calibration=null` and `detection=null`.
The API is stateless and never returns a previous layout after losing the table.
A calibrated empty table can return `detected` with an empty ball list and zero
counts. The client must clear old balls on table loss or failed analysis.

`detection` contains:

- `balls`: `id`, `kind`, `x`, `y`, `radius`, `source_x`, `source_y`, `confidence`,
  `reason`, `white_fraction`, `method`.
- `counts`: `total`, `cue`, `eight`, `solid`, `striped`, `unknown`; includes every
  located candidate, including unknowns.
- `geometry`: table ratio, explicit coordinate conventions and both matrices.
- `cloth_hue`, `processing_ms`, and `warnings`.

IDs are **frame-local labels**, not printed ball numbers or stable tracking
identities. Confidence is a heuristic rule score, not a calibrated probability.
The API does not assign presentation colors or stripe graphics. It recognizes
categories rather than individual ball colors/numbers. Only the cue and eight
categories are globally unique; there is no invented total or seven-ball quota.

`analysis_ms` includes lens correction, automatic calibration and detection, but
excludes capture, decoding and network time. `processing_ms` measures the engine's
localization/classification portion and excludes automatic calibration.

## Calibration, lens correction and tuning

Automatic table finding is the default. For a fixed camera, request calibration
once or retain `AnalysisResult.calibration`, then send it with subsequent frames:

```json
{
  "client_frame_id": "frame-42",
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

These example corners describe a 1000×500 **already top-down, full-frame** image.
For a real camera, choose the inner-cushion corners clockwise, first edge along
the long side, normalized by `width-1` / `height-1`. The quadrilateral must be
convex and cover at least 2.5% of the source. Reuse requires matching camera
position, crop, resolution, EXIF orientation and lens correction. Resolution is
validated; matching dimensions alone cannot prove the camera has not moved.

`table_ratio=physical_cloth_width/physical_cloth_height` (1–3).
`ball_radius_ratio=ball_diameter/(2*physical_cloth_height)` (0.012–0.06).
For 57.15 mm balls and a 1120 mm short cloth dimension, use about 0.0255.
Hue uses OpenCV's 0–179 scale; leave null for histogram estimation. Hue tolerance
is 3–40, saturation minimum 15–180; touching-ball separation defaults to true.

Optional `lens` is accepted by both calibration and detection:

```json
{
  "lens": {
    "image_width": 1920,
    "image_height": 1080,
    "camera_matrix": [[1500, 0, 960], [0, 1500, 540], [0, 0, 1]],
    "distortion": [-0.1, 0.02, 0, 0, 0]
  }
}
```

These are illustrative intrinsics, not your camera calibration. Resolution must
match the oriented input; OpenCV distortion vectors may have 4, 5, 8, 12 or 14
coefficients. Correction happens internally. Send the same original pixels and
lens parameters on calibration and detection; no canonical-image round trip is
needed. Do not send already corrected pixels with the lens parameters again.

## Server camera

```sh
CAMERA_SOURCE=0 uv run uvicorn app.main:app --host 127.0.0.1 --port 8001

CAMERA_SOURCE='rtsp://camera-host:554/stream' \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The source belongs to the **server machine**. A remote browser webcam must upload
its own captured frame instead. Capture opens the source, reads startup frames,
uses the last one, and releases the device even after an error. Nothing opens at
startup. Poll sequentially; no background capture loop or image stream is exposed.
This remains a low-rate capture design with device-startup overhead.

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `CAMERA_SOURCE` | `0` | Device index, stream URL or local video path |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | `1280` / `960` | Requested device resolution; actual dimensions are returned |
| `CAMERA_WARMUP_FRAMES` | `3` | Read 1–30 frames, use last |
| `CAMERA_TIMEOUT_MS` | `5000` | FFmpeg open/read timeout per operation, not whole-request deadline |
| `OPENCV_THREADS` | `4` | OpenCV thread limit (1–16) |

A video file restarts on every request. USB-camera native drivers govern their
own blocking reads; FFmpeg timeouts do not apply to that path. Source URLs and
credentials are not returned in JSON. On macOS grant access to the terminal/process;
on Linux ensure device permissions. Pi CSI access needs a supported OpenCV capture
source or a separate Picamera2/libcamera process uploading frames.

## Structure and preserved mathematics

```text
app/
  main.py                 Application factory, health and docs
  config.py               Server/camera configuration
  schemas.py              Public typed numerical contracts
  api/routes.py           Upload, camera and configuration routes
  api/dependencies.py     Shared admission control
  services/analysis.py    Shared stateless calibration/recognition orchestration
  services/geometry.py    Source-pixel ↔ normalized-table matrices
  services/images.py      Bounded decode, EXIF and internal lens correction
  services/camera.py      On-demand capture and guaranteed release
  engine/                 Original PoC detection/classification mathematics
  trajectory/             Ported numerical shot planning and motion simulation
tests/fixtures/           Synthetic test data; not imported by the application
```

The engine derives from PoC commit `660539e`. HSV thresholding, CIELAB local
contrast, dominant-hue histograms, Gaussian/median filtering, morphology,
connected components, contour circularity `4πA/P²`, minimum enclosing circles,
Canny edges, gradient Hough circles, Euclidean distance transforms, local maxima,
marker-controlled watershed, bounded white-balance channel gains, color-area
ratios, angular sectors, classification thresholds, special-ball uniqueness
and homography mapping are retained. The photo follow-up now scores refined rail lines on their fitted inliers,
merges overlapping Hough proposals for unresolved shadowed silhouettes, and
uses stricter neutral-pixel selection for white balance. Appearance saturation
thresholds also distinguish pale color from white more conservatively. The
original regression suite remains in place. Debug rendering/encoding was removed from
the engine wrapper. Native source silhouettes are still analyzed before planar
mapping. An internal reference scale supports the original radius calculations;
it imposes no output canvas size on clients.

## Verification and limits

```sh
uv run --frozen pytest -q
```

Tests cover original recognition regressions, no-image/no-demo API contracts,
disabled debug options, no runtime image encoding, calibration/reprojection and
inverse matrices, lens/EXIF handling, invalid/oversized inputs, empty/lost tables,
admission control, camera errors/release and real OpenCV capture of a generated
video. The synthetic fixture exists under tests only.

The separate **[verification client](../PoC/backend-verification/README.md)**
uploads its local fixture/browser-camera frames to this API and renders the JSON
using the first PoC's complete camera/table interface, calibration controls,
shot suggestions and animated cue simulation. Its fixture files are served by Vite. The backend
does not import that client. Later apps can consume the same OpenAPI contract.

JPEG, PNG and WebP inputs are supported. Limits: 12 MiB, 16 megapixels, 100–10,000
pixels per side. `413` means exceeded limits, `415` unsupported format, `422`
invalid image/options/calibration, `503` busy or unavailable camera. Busy responses
include `Retry-After: 1`. The verification client serializes frame and shot requests through one queue,
skips cancelled queued requests, and briefly retries explicit busy responses.
One expensive operation runs per process; docs and health
remain available. Inputs/results are processed in memory and not stored.

This is a deterministic recognizer, not a guarantee of flawless measurements.
Occluded stripes, glare, shadows, motion blur, hands, occlusion and low-resolution
balls can produce errors. Automatic boundaries assume a dominant cloth region;
manual corners remain available. Ball height produces parallax because homography
describes the cloth plane. Validate the intended camera and scene. Stable physical identities and shot completion remain separate application
features. The verification client performs display stabilization; the stateless
recognition response has no temporal history. Shot planning and cue simulation
are available as separate numerical operations, using the original PoC physics
assumptions rather than a measured physical-table model. No minimum RAM or Raspberry Pi latency is claimed.

References: [FastAPI response contracts](https://fastapi.tiangolo.com/tutorial/response-model/),
[modular applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/),
[OpenCV homography mathematics](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html).

## Shot requests

Shot routes accept at most 24 balls with unique layout-local IDs. Each ball needs
only `id`, `kind`, `x`, `y`, `radius`; extra detection evidence is ignored. Layout
coordinates and drawing paths are normalized as above. `/shots` also accepts
`top_n` (1–20), `include_bank` and `include_blocked`. Aim operations accept
`aim_x`, `aim_y` in [0,1]; simulation adds `power` in [0,1]. All heavy operations
share the same admission guard and return 503 while another operation is active.

```sh
curl -sS http://127.0.0.1:8001/api/v1/shots/simulate \
  -H 'Content-Type: application/json' \
  -d '{"balls":[{"id":1,"kind":"cue","x":0.2,"y":0.5,"radius":0.026},{"id":2,"kind":"solid","x":0.6,"y":0.5,"radius":0.026}],"aim_x":0.9,"aim_y":0.5,"power":0.6}'
```

Results describe hypothetical motion, not a calibrated forecast for the physical
table. They contain coordinates/events only, without pixels or rendering styles.

## Real-photo evaluation

Run the same API against local files and inspect numerical results plus offline
annotations (the API itself still returns only JSON):

```sh
uv run --frozen python -m scripts.evaluate_images evaluation-output/photos/table-1.png evaluation-output/photos/table-2.png evaluation-output/photos/table-3.png
```

Use `--config options.json` for per-table settings/manual calibration and
`--output path` to change the output directory. Default output is the ignored
`evaluation-output/` folder. No workflow or hosted service is needed.

The original photos stay local in the ignored `evaluation-output/photos/`
directory, named `table-1.png` through `table-3.png`. Photo regression tests also
accept `EBILARD_PHOTO_DIR` and skip explicitly when the optional inputs are absent.
The synthetic multi-table tests run on a fresh checkout without these files.

The three user-supplied 1920×1080 frames are different layouts on one physical
table. Approximate manual center annotations identify 11, 3 and 17 visible
on-cloth balls. Default automatic recognition currently matches **7, 3 and 16**
respectively, with no unmatched rail/pocket candidates under the test's 25-pixel
association tolerance. That tolerance is not claimed measurement accuracy.
The sparse frame previously returned eight candidates, including five false
cushion detections. Inner seam selection now removes that chain; body-outline
ranking also avoids some shadow/number-patch centers and preserves the cue in
the crowded scenes.

Four rail/occlusion-adjacent balls remain missed in the first frame and one in
the third. Several full/half categories are visually ambiguous or incorrect.
These fixtures preserve confirmed improvements and record current recall;
they do not demonstrate perfect recognition or accuracy on every physical table.
