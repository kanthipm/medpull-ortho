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
  build: {
    rolldownOptions: {
      output: {
        // The framework in its own long-lived chunk beside the tab chunks
        // App.tsx splits off: it changes only when a dependency is bumped,
        // so a deploy of app code leaves it cached on every phone that has
        // opened the app before.
        codeSplitting: {
          groups: [
            {
              name: 'vendor',
              test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/,
            },
          ],
        },
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': process.env.MEDPULL_API ?? 'http://127.0.0.1:8000',
    },
  },
}))
