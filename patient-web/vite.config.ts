import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The patient app, on its own port so it can run beside the provider
// console (5173). `/api` is proxied to `make dev-backend`, the way the
// console's dev server does it, so nothing is ever cross-origin.
// Production builds live under /patient/ on the console's host
// (infra/deploy.sh uploads dist/ to web/patient/); dev stays at /.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/patient/' : '/',
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': process.env.MEDPULL_API ?? 'http://127.0.0.1:8000',
    },
  },
}))
