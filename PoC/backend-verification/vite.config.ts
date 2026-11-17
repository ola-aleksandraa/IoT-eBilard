import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Override only the proxy target when the backend runs on another port.
const target = process.env.BACKEND_URL ?? 'http://127.0.0.1:8001'
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5175, strictPort: true, proxy: { '/api': target } },
  preview: { host: '127.0.0.1', port: 5175, strictPort: true, proxy: { '/api': target } },
})
