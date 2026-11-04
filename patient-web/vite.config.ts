import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The patient app, on its own port so it can run beside the provider
// console (5173). `/api` is proxied to `make dev-backend`, the way the
// console's dev server does it, so nothing is ever cross-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
