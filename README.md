# IoT-eBilard

**[backend/](backend/README.md)** is the standalone numerical FastAPI service.
It receives a frame or captures a server camera and returns JSON with ball
categories, counts, normalized 2D coordinates, decision evidence and homography
matrices. All visualization belongs to the consuming application.

```sh
cd backend
uv sync --python 3.12 --frozen
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Interactive API: **[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)**.

**[PoC/backend-verification/](PoC/backend-verification/README.md)** is a separate
React verification client based on the first PoC's canvas, source view and camera
lifecycle. It connects to the root backend, uploads local/browser-camera pixels,
and draws the numerical response locally. Fixtures are served by that client.

```sh
cd PoC/backend-verification
npm ci
npm run dev
```

Verification client: **[http://127.0.0.1:5175](http://127.0.0.1:5175)**.

The original experiment remains in
[PoC/ball-detect-to-canvas/](PoC/ball-detect-to-canvas/README.md).
