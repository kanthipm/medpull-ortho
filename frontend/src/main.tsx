import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { shouldRetry } from './api/client'
import App from './App'
import { ToastProvider } from './components/ToastProvider'
import { ThemeProvider } from './lib/ThemeProvider'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    // Five minutes fresh, half an hour kept: navigating back to a page paints
    // from the cache at once, the page refetches in the background only when
    // it is actually stale, and the per-page refetchInterval keeps the
    // numbers moving every five minutes while a tab stays open.
    queries: {
      staleTime: 5 * 60_000,
      gcTime: 30 * 60_000,
      refetchOnWindowFocus: true,
      retry: shouldRetry,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <ToastProvider>
            <App />
          </ToastProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
