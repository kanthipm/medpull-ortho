import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The patient app, on its own port so it can run beside the provider
// console (5173). `/api` is proxied to `make dev-backend`, the way the
// console's dev server does it, so nothing is ever cross-origin.
export default defineConfig({
  plugins: [react()],
  // Served beside the provider console on the deployed stack, under
  // /patient/ (CloudFront routes the prefix to patient-web/dist in the web
  // bucket; infra/cloudformation.yaml and infra/deploy.sh). The dev server
  // answers at http://localhost:5174/patient/ for the same reason.
  base: '/patient/',
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
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
