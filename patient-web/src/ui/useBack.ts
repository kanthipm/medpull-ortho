import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

/** The system back button: pops when there is somewhere to pop to, and
 *  otherwise goes to the tab root (a deep link landed straight on a
 *  pushed screen). */
export function useBack(fallback: string) {
  const navigate = useNavigate()
  return useCallback(() => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx > 0) navigate(-1)
    else navigate(fallback, { replace: true })
  }, [navigate, fallback])
}
