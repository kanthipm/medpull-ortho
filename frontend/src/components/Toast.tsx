import { createContext, useContext } from 'react'

export type ToastKind = 'success' | 'info' | 'warning'

/** The push function ToastProvider (components/ToastProvider.tsx) puts in
 *  context. This file holds no components, so it can export the hook
 *  (react-refresh). */
export const ToastContext = createContext<(text: string, kind?: ToastKind) => void>(() => {})

/** `const toast = useToast(); toast('Sent', 'success')`. */
export function useToast() {
  return useContext(ToastContext)
}
