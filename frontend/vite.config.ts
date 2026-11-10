import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Override the proxy target when the central server runs on another port.
// All /api traffic goes through the central service; it proxies ball detection
// to the Raspberry Pi backend (PI_BACKEND_URL, default 127.0.0.1:8001).
const target = process.env.CENTRAL_URL ?? process.env.BACKEND_URL ?? 'http://127.0.0.1:8002'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 4321, proxy: { '/api': target } },
  preview: { host: 'localhost', port: 4321, proxy: { '/api': target } },
})
