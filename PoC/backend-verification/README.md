# Ball / Detect — numerical-backend client

The original `PoC/ball-detect-to-canvas` interface runs against the standalone
root `backend/`. Camera preview, source overlays, table rendering and animation
stay in the browser. FastAPI returns numerical JSON only.

## Run

Start the root backend using [its instructions](../../backend/README.md), then:

```sh
cd PoC/backend-verification
npm ci
npm run dev
```

Open **[http://127.0.0.1:5175](http://127.0.0.1:5175)**. Vite proxies `/api` to
`http://127.0.0.1:8001`. For another server:

```sh
BACKEND_URL=http://127.0.0.1:8002 npm run dev
```

The original PoC is unchanged and is not needed at runtime.

## Camera and photos

- **Connect camera** opens the selected browser camera, shows its live feed and
  sends sequential JPEG frames (at most 1280×960) for recognition automatically.
  The next request waits for the previous one; disconnect stops every track and
  aborts pending recognition. Camera access needs localhost or HTTPS and browser
  permission. This preview comes from the browser camera, not a server stream.
- Fixed-camera mode locks corners after eight consistent observations and
  stabilizes the displayed balls. **Camera is unstable** instead recalibrates
  each frame. **Recalibrate corners** discards the lock after camera movement.
- **Try a sample image** loads the local synthetic fixture and recognizes it
  immediately. **Settings → Upload photo** does the same for JPEG, PNG or WebP.
  EXIF orientation is handled locally; the pixels displayed are those uploaded.
  The backend provides neither a demo nor an image-preparation endpoint.
- **Settings → Set corners manually** freezes a live frame or edits the photo.
  Click four inner-cushion corners clockwise, first edge along the long side.
  Drag corners, reset them, rotate the mapping, apply, or cancel. Saved corners
  can be reused only at matching dimensions and the same camera position.
- Detection settings, stationary-ball tolerance, ball IDs, table grid and shot
  suggestions live in Settings. Use **Apply to image** after changing photo
  detection settings. Select a ball on the virtual table or source image to see
  its coordinates and decision evidence. Arrow keys inspect balls; Escape clears.
- **Show shot predictions** requests ranked direct/bank paths from `/api/v1/shots`.
  **Aim cue** lets you drag on the virtual table and animates the numerical
  `/api/v1/shots/simulate` result, including contacts, cushions and pots.
- **Export layout** downloads browser-rendered layout data and calibration as
  JSON. In fixed-camera mode this is the stabilized display layout; session IDs
  are approximate associations, not persistent physical identities.

Geometry uses `center=(x*W,y*H)`, `radius=r*H`, `W/H=table_ratio`.
Colors, stripes, grid, cue and shot paths are client presentation. API recognition
retains frame correlation and clears old balls on table loss or request failure.
The root API also supports server-camera capture; the main UI uses the browser
camera so a source preview is always available.

## Verification

```sh
npm test
npm run build
```

Coverage includes request shape, JSON-only responses and frame correlation,
camera lifecycle, sequential polling, corner consensus, display stabilization,
source loss/failure recovery, photos, calibration and shot controls.

The local synthetic sample contains 12 candidates: 1 cue, 1 eight, 7 solids and
3 stripes. It checks functionality, not physical-camera accuracy. Real photos
with blur, glare and shadows can still misclassify full/half patterns; inspect
uncertain types before using predictions. Physics scores are heuristic too.

`public/sample-table.png` and `public/empty-table.png` are local test assets.
Regenerate explicitly from the repository root with a compatible Python runtime:

```sh
python PoC/backend-verification/scripts/make-fixtures.py
```
