import react from '@vitejs/plugin-react'
import { defineConfig, type ProxyOptions } from 'vite'

// Override the proxy targets when the backends run elsewhere (e.g. PI_URL=http://raspberrypi.local:8002).
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8001'
const pi = process.env.PI_URL ?? 'http://127.0.0.1:8002'

const proxy: Record<string, string | ProxyOptions> = {
  // Website backend (back_website/): shot planning, configuration.
  '/api': backend,
  // Raspberry Pi backend (back_raspberry/): camera capture + ball detection. /pi/api/v1/… → /api/v1/…
  '/pi': { target: pi, changeOrigin: true, rewrite: (path) => path.replace(/^\/pi/, '') },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 4321, proxy },
  preview: { host: 'localhost', port: 4321, proxy },
})
