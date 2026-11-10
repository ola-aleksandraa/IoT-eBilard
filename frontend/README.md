# eBilard frontend

React 19 + TypeScript + Vite, styled with [Panda CSS](https://panda-css.com). Uses **pnpm**.

```sh
pnpm install   # also runs `panda codegen` (prepare script) → styled-system/
pnpm dev       # backend (../backend, :8001) + Vite (http://localhost:4321)
pnpm dev:web   # Vite only
pnpm dev:api   # backend only (needs uv on PATH)
pnpm build
pnpm lint
```

`pnpm dev` ([scripts/dev.mjs](scripts/dev.mjs)) starts the FastAPI backend with
`uv run --frozen --python 3.12 uvicorn … --reload` and then Vite. It reuses a
backend that is already running, and skips it when `BACKEND_URL` points elsewhere.
uv is found as `$UV`, `uv`, or `mise exec uv -- uv`. Ctrl+C stops both.

Requests to `/api` are proxied to the backend at `http://127.0.0.1:8001`
(override with `BACKEND_URL`).

### Data

On load the table view sends the test frame `public/demo/sample-table.png` to
`POST /api/v1/images/detect` and asks `POST /api/v1/shots` for the "Pomóż mi"
hint. The topbar shows "Dane: backend". If the backend is not reachable (it
retries for ~40 s), the Figma mock from `src/data/mock.ts` stays ("Dane: mock").
Players, score, turn, stats and the table history are always mock: the backend
has no game state yet, and the history is interpolated from a rack.

Styles are written with Panda's `css()` and JSX patterns imported from
`styled-system/` (generated, git-ignored). Theme tokens live in `panda.config.ts`.
