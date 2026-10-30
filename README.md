# IoT-eBilard

**[backend/](backend/README.md)** is the standalone numerical FastAPI service.
It receives a frame or captures a server camera and returns JSON with ball
categories, counts, normalized 2D coordinates, decision evidence and homography
matrices. All visualization belongs to the consuming application.

See the [backend startup instructions](backend/README.md#start-and-api-reference)
for the Python 3.11–3.13 runtime restored by the downgrade revert. Run from `backend/`:

```sh
uv sync --python 3.12 --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Interactive API: **[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)**.

**[PoC/backend-verification/](PoC/backend-verification/README.md)** is a separate
React client restoring the first PoC's camera/table interface, calibration,
display stabilization, shot suggestions and cue animation. It connects to the root backend, uploads local/browser-camera pixels,
and draws the numerical response locally. Fixtures are served by that client.

```sh
cd PoC/backend-verification
npm ci
npm run dev
```

Verification client: **[http://127.0.0.1:5175](http://127.0.0.1:5175)**.

The original experiment remains in
[PoC/ball-detect-to-canvas/](PoC/ball-detect-to-canvas/README.md).
