# eBilard frontend

React 19 + TypeScript + Vite, styled with [Panda CSS](https://panda-css.com). Uses **pnpm**.

```sh
pnpm install   # also runs `panda codegen` (prepare script) → styled-system/
pnpm dev       # http://localhost:4321
pnpm build
pnpm lint
```

Requests to `/api` are proxied to the backend at `http://127.0.0.1:8001`
(override with `BACKEND_URL`).

Styles are written with Panda's `css()` and JSX patterns imported from
`styled-system/` (generated, git-ignored). Theme tokens live in `panda.config.ts`.
