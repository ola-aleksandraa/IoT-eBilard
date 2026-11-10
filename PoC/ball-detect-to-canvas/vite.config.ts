import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Ball-motion simulation & shot planning live on the central server;
      // detection (live/detect/prepare/demo) is proxied to the Pi backend.
      '/api/shots': 'http://127.0.0.1:8001',
      '/api': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    proxy: {
      '/api/shots': 'http://127.0.0.1:8001',
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
