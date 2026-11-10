# IoT-eBilard

The backend is split into two FastAPI services (Python 3.11–3.13, uv):

- **[back_raspberry/](back_raspberry/README.md)** runs on the Raspberry Pi. It
  captures a frame from its camera and returns JSON with ball categories, counts,
  normalized 2D coordinates, decision evidence and homography matrices
  (`/api/v1/camera`, `/camera/calibrate`, `/camera/detect`). Default port 8002.
- **[back_website/](back_website/README.md)** serves the web application:
  configuration (`/api/v1/settings`, `/categories`) and shot planning
  (`/shots`, `/shots/predict`, `/shots/simulate`). Default port 8001.

All visualization belongs to the consuming application. Run each service from
its own directory:

```sh
cd back_website   # or back_raspberry (with --port 8002)
uv sync --python 3.12 --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Interactive API: **[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)**
(website) and **[http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs)** (Raspberry Pi).

**[frontend/](frontend/README.md)** is the React + TypeScript + Panda CSS
application (pnpm). Run from the repository root (or from `frontend/`):

```sh
pnpm install   # installs frontend/ dependencies
pnpm dev       # starts back_website/ (:8001, via uv) + the frontend dev server
```

The root `package.json` only forwards these scripts to `frontend/`
(`dev`, `dev:web`, `dev:api`, `build`, `lint`, `preview`).

**[PoC/backend-verification/](PoC/backend-verification/README.md)** is a separate
React client restoring the first PoC's camera/table interface, calibration,
display stabilization, shot suggestions and cue animation. It uploads local/browser-camera pixels
to the former `/images/*` endpoints, which the split backends no longer provide.

```sh
cd PoC/backend-verification
npm ci
npm run dev
```

Verification client: **[http://127.0.0.1:5175](http://127.0.0.1:5175)**.

The original experiment remains in
[PoC/ball-detect-to-canvas/](PoC/ball-detect-to-canvas/README.md).
