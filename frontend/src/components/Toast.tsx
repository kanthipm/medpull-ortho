import { CircleCheck, Info, TriangleAlert } from 'lucide-react'
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

type ToastKind = 'success' | 'info' | 'warning'

interface ToastItem {
  id: number
  kind: ToastKind
  text: string
}

const ToastContext = createContext<(text: string, kind?: ToastKind) => void>(() => {})

export function useToast() {
  return useContext(ToastContext)
}

const ICON: Record<ToastKind, ReactNode> = {
  success: <CircleCheck size={15} className="text-risk-low" />,
  info: <Info size={15} className="text-brand" />,
  warning: <TriangleAlert size={15} className="text-risk-high" />,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const push = useCallback(
    (text: string, kind: ToastKind = 'success') => {
      const id = nextId.current++
      setToasts((t) => [...t, { id, kind, text }])
      window.setTimeout(() => dismiss(id), 3800)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-[18px] top-[18px] z-[100] flex w-full max-w-[340px] flex-col items-end gap-2.5"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            onClick={() => dismiss(toast.id)}
            className={`pointer-events-auto flex w-auto animate-toastIn cursor-pointer items-center gap-2.5 rounded-card border bg-panel px-4 py-3 text-[13px] font-medium leading-[1.4] shadow-glass ${
              toast.kind === 'warning'
                ? 'border-risk-high/30 text-risk-high'
                : 'border-line text-ink'
            }`}
          >
            {ICON[toast.kind]}
            {toast.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
