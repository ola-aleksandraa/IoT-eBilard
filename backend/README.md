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

## Public API

| Method and path | Input | Numerical response |
| --- | --- | --- |
| `GET /health` | — | Process and OpenCV version |
| `GET /api/v1/settings` | — | Default per-frame settings |
| `GET /api/v1/categories` | — | `cue`, `eight`, `solid`, `striped`, `unknown` and meanings |
| `POST /api/v1/images/calibrate` | Multipart `file`, optional JSON string `config` | Source dimensions, normalized corners, forward/inverse homographies |
| `POST /api/v1/images/detect` | Multipart `file`, optional JSON string `config` | Types, counts, normalized coordinates, geometry, decision evidence |
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
`AnalysisOptions`, `AnalysisResult`, `Ball`, `Counts`, `Geometry`, `Calibration`
and `LensCalibration` from that contract when generating a client.

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
tests/fixtures/           Synthetic test data; not imported by the application
```

The engine derives from PoC commit `660539e`. HSV thresholding, CIELAB local
contrast, dominant-hue histograms, Gaussian/median filtering, morphology,
connected components, contour circularity `4πA/P²`, minimum enclosing circles,
Canny edges, gradient Hough circles, Euclidean distance transforms, local maxima,
marker-controlled watershed, bounded white-balance channel gains, color-area
ratios, angular sectors, classification thresholds, special-ball uniqueness
and homography mapping are retained. Recognition thresholds and decision rules
were not retuned for this API change. Debug rendering/encoding was removed from
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
using the first PoC's canvas. Its fixture files are served by Vite. The backend
does not import that client. Later apps can consume the same OpenAPI contract.

JPEG, PNG and WebP inputs are supported. Limits: 12 MiB, 16 megapixels, 100–10,000
pixels per side. `413` means exceeded limits, `415` unsupported format, `422`
invalid image/options/calibration, `503` busy or unavailable camera. Busy responses
include `Retry-After: 1`. One expensive operation runs per process; docs and health
remain available. Inputs/results are processed in memory and not stored.

This is a deterministic recognizer, not a guarantee of flawless measurements.
Occluded stripes, glare, shadows, motion blur, hands, occlusion and low-resolution
balls can produce errors. Automatic boundaries assume a dominant cloth region;
manual corners remain available. Ball height produces parallax because homography
describes the cloth plane. Validate the intended camera and scene. Stable physical
identities, temporal filtering, shot completion and trajectory prediction remain
separate application features. No minimum RAM or Raspberry Pi latency is claimed.

References: [FastAPI response contracts](https://fastapi.tiangolo.com/tutorial/response-model/),
[modular applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/),
[OpenCV homography mathematics](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html).
