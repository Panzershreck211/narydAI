import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = process.env.API_URL ?? 'http://127.0.0.1:8000'

// В dev всё проксируется на бэкенд — тот же origin, что и в проде за nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': API,
      '/media': API,
      '/ws': { target: API.replace(/^http/, 'ws'), ws: true },
    },
  },
})
