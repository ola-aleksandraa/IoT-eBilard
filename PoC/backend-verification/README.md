# Numerical-backend verification client

This separate React/Vite PoC connects to the root `backend/`. It reuses the first
PoC's canvas, source overlay and browser-camera lifecycle, with a new numerical
API adapter. Every rectangle, circle, stripe and label is drawn in this browser.
The backend returns JSON only.

## Run

Start the root backend first (see [backend README](../../backend/README.md)).
Then from this directory, using Node.js 22.12+:

```sh
npm ci
npm run dev
```

Open **[http://127.0.0.1:5175](http://127.0.0.1:5175)**. The default Vite proxy
for `/api` points to **http://127.0.0.1:8001**. Override a different server with:

```sh
BACKEND_URL=http://127.0.0.1:8002 npm run dev
```

The API-docs link in the page targets the default localhost:8001. The app runs
separately; FastAPI does not serve or depend on this client. The original
`PoC/ball-detect-to-canvas` remains unchanged.

## Verify

1. Select **Load local sample**, then **Recognize frame**. Vite serves the local
   synthetic PNG; the client uploads it to `/api/v1/images/detect`.
2. Confirm 12 detected candidates: 1 cue, 1 eight, 7 solids, 3 stripes. This is a
   synthetic functionality fixture, not a real-camera accuracy claim.
3. Inspect the locally drawn table, coordinate rows and **Inspect numerical API
   response**. There are no returned images, debug options or backend demo calls.
4. Select **Load blank frame**, then recognize: old positions clear and the API
   reports `searching`. Upload a real photo to verify the same path.
5. Select **Connect browser camera**, grant camera access, then recognize once or
   enable **Sequential live updates**. Requests wait for one another; frames are
   capped at 1280×960. The local preview and uploaded pixels belong to the browser.
6. Use **Reuse detected corners** for a fixed camera, or **Set corners manually**
   and click four inner-cushion corners clockwise, first edge along the long side.
   **Reset calibration** returns to automatic estimation. Moving the camera needs
   fresh calibration even if resolution is unchanged.
7. **Use server camera** selects `/api/v1/camera/detect`; the server keeps its pixels
   internally and only its numerical results appear. Configure `CAMERA_SOURCE`
   when starting FastAPI. Server-camera mode intentionally has no source image.

The client clears stale results on source changes, table loss and request failure.
It aborts in-flight requests on reset/disconnect, correlates frame tokens and
ignores responses from previous source generations. It does not pretend that
frame-local ball IDs are stable physical identities. There is no temporal
smoothing here, so the view exposes the actual numerical detections for review.

Rendering uses `center=(x*W,y*H)`, `radius=r*H`, `W/H=table_ratio`. Type colors
and stripe styles live only in `src/types.ts` and `TableCanvas.tsx`.

## Tests and build

```sh
npm test
npm run build
```

Tests cover request shape, JSON-only response handling, frame correlation, source
loading, numerical rendering, clearing stale detections, late-response rejection
and the original camera lifecycle tests. The production build also typechecks the
client. Browser integration is checked against the real root service.

`public/sample-table.png` and `public/empty-table.png` are local test assets.
The synthetic sample derives from the original PoC generator now kept under
`backend/tests/fixtures/synthetic.py`; neither fixture generation nor delivery is
part of the runtime API. Regenerate explicitly from the repository root:

```sh
backend/.venv/bin/python PoC/backend-verification/scripts/make-fixtures.py
```
