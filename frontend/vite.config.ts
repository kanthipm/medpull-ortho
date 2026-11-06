import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        // Long-lived chunks beside the route chunks App.tsx splits off.
        // `vendor` is the framework, which changes only when a dependency is
        // bumped, so a deploy of app code leaves it cached in every browser
        // that has it; `charts` is the charting library and what only it
        // pulls in, shared by the patient and sports pages and loaded by
        // whichever of them is opened first — never by the worklist.
        codeSplitting: {
          groups: [
            {
              name: 'vendor',
              test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom|@tanstack)[\\/]/,
            },
            {
              name: 'charts',
              test: /node_modules[\\/](recharts|recharts-scale|react-smooth|d3-[a-z-]+|lodash|decimal\.js-light|fast-equals|victory-vendor|internmap)[\\/]/,
            },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
