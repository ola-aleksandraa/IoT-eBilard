import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Override the proxy target when the backend runs on another port.
const target = process.env.BACKEND_URL ?? 'http://127.0.0.1:8001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 4321, proxy: { '/api': target } },
  preview: { host: 'localhost', port: 4321, proxy: { '/api': target } },
})
