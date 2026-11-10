# IoT-eBilard

## Architecture

- **[`backend/`](backend/README.md) — Raspberry Pi service (detection only).**
  Standalone numerical FastAPI + OpenCV service. It receives a frame or captures
  a server camera and returns JSON with ball categories, counts, normalized 2D
  coordinates, decision evidence and homography matrices. All visualization and
  all shot mathematics live elsewhere: this process returns recognition data only.
- **[`central/`](central/README.md) — central server (website + shot planning).**
  FastAPI + NumPy. Owns `/api/v1/shots*` (ranking, cue-aim prediction and
  real-motion simulation), serves the built frontend in production, and proxies
  every other `/api/v1` route to the Pi so the browser talks to a single origin.
- **[`frontend/`](frontend/README.md) — React + TypeScript + Panda CSS app.**
  In development it proxies all `/api` traffic to the central service
  (default `http://127.0.0.1:8002`; override with `CENTRAL_URL`).

```text
browser → central :8002 (site, /api/v1/shots*) → Pi :8001 (images/camera detection)
```

## Start (development)

Python **3.11–3.13** with [uv](https://docs.astral.sh/uv/):

```sh
cd backend && uv sync --python 3.12 && uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
cd central && uv sync --python 3.12 && uv run uvicorn app.main:app --host 127.0.0.1 --port 8002
```

- Pi detection docs: **http://127.0.0.1:8001/docs**
- Central docs (shots API): **http://127.0.0.1:8002/docs**

Frontend (pnpm):

```sh
pnpm install
pnpm dev
```

## Clients

**[PoC/backend-verification/](PoC/backend-verification/README.md)** is a separate
React client restoring the first PoC's camera/table interface, calibration,
display stabilization and cue animation. It connects to the detection backend,
uploads local/browser-camera pixels, and draws the numerical response locally.

```sh
cd PoC/backend-verification
npm ci
npm run dev
```

Verification client: **http://127.0.0.1:5175**.

The original experiment remains in
[PoC/ball-detect-to-canvas/](PoC/ball-detect-to-canvas/README.md).
