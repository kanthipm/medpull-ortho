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

/** Icons take the `-ink` half of each pair — the bare `risk-*` / `brand` names
 *  are fills, and #1976D2 as a foreground is the one thing --brand may not be. */
const ICON: Record<ToastKind, ReactNode> = {
  success: <CircleCheck size={18} className="text-risk-low-ink" />,
  info: <Info size={18} className="text-brand-ink" />,
  warning: <TriangleAlert size={18} className="text-risk-high-ink" />,
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
        className="pointer-events-none fixed right-block top-block z-[100] flex w-full max-w-[340px] flex-col items-end gap-tight"
      >
        {/* A toast is genuinely floating, so it keeps the ambient shadow via
            `.overlay`. Its EDGE is one mechanism per mode: light separates with
            the white panel fill under the ambient wash, dark with `.dark
            .overlay`'s 1px --overlay-border, which earns its keep — the dark
            overlay panel is only 1.435:1 on --canvas. The risk tint on a
            warning is state colour, not an edge, and it replaces the panel fill
            rather than adding a second border (the old `border-risk-high/30`
            was a 1.5:1 stroke on top of both). */}
        {toasts.map((toast) => (
          <div
            key={toast.id}
            onClick={() => dismiss(toast.id)}
            className={`overlay pointer-events-auto flex w-auto animate-toastIn cursor-pointer items-center gap-tight px-4 py-3 text-copy font-medium ${
              toast.kind === 'warning'
                ? 'bg-risk-high-tint text-risk-high-ink'
                : 'text-ink'
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
