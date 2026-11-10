# eBilard frontend

React 19 + TypeScript + Vite, styled with [Panda CSS](https://panda-css.com). Uses **pnpm**.

```sh
pnpm install   # also runs `panda codegen` (prepare script) → styled-system/
pnpm dev       # http://localhost:4321
pnpm build
pnpm lint
```

Requests to `/api` are proxied to the central service at `http://127.0.0.1:8002`
(override with `CENTRAL_URL` or `BACKEND_URL`). The central service serves the
shot endpoints itself and proxies ball detection to the Raspberry Pi backend
(`PI_BACKEND_URL`, default `http://127.0.0.1:8001`).

Styles are written with Panda's `css()` and JSX patterns imported from
`styled-system/` (generated, git-ignored). Theme tokens live in `panda.config.ts`.
