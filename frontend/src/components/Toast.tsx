import { CircleCheck, Info, TriangleAlert } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Tile, { type TileFamily } from './Tile'

type ToastKind = 'success' | 'info' | 'warning'

interface ToastItem {
  id: number
  kind: ToastKind
  text: string
  leaving: boolean
}

const ToastContext = createContext<(text: string, kind?: ToastKind) => void>(() => {})

export function useToast() {
  return useContext(ToastContext)
}

/** Each kind gets a tile and an icon, so the state never rests on colour.
 *  success is teal (the "verified" slot), info blue, warning the risk tile.
 *  Glyph on tile: teal 5.171 / 8.142, blue 4.963 / 5.624, risk 4.835 / 5.701. */
const KIND: Record<ToastKind, { family: TileFamily; icon: ReactNode; label: string }> = {
  success: { family: 'teal', icon: <CircleCheck />, label: 'Done' },
  info: { family: 'blue', icon: <Info />, label: 'Note' },
  warning: { family: 'risk-high', icon: <TriangleAlert />, label: 'Warning' },
}

const VISIBLE_MS = 3800
const LEAVE_MS = 180

/** Floating capsule toasts, top-right, in the top layer.
 *
 *  A toast is an `.overlay` with pill corners: opaque panel, the soft layered
 *  shadow, a leading Tile and a 14/500 ink label (17+ light / 12.810 dark on
 *  the overlay panel). A warning no longer turns the whole capsule red; the
 *  risk tile and the icon carry it, and the word is announced.
 *
 *  Announced politely (warnings assertively). Hovering or focusing a toast
 *  pauses its timer; clicking dismisses it. Enter slides in on the spring,
 *  exit fades; Reduce Motion drops both (index.css). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)
  const timers = useRef(new Map<number, number>())

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const dismiss = useCallback(
    (id: number) => {
      window.clearTimeout(timers.current.get(id))
      timers.current.delete(id)
      setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x)))
      window.setTimeout(() => remove(id), LEAVE_MS)
    },
    [remove],
  )

  const arm = useCallback(
    (id: number) => {
      window.clearTimeout(timers.current.get(id))
      timers.current.set(
        id,
        window.setTimeout(() => dismiss(id), VISIBLE_MS),
      )
    },
    [dismiss],
  )

  const pause = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id))
  }, [])

  const push = useCallback(
    (text: string, kind: ToastKind = 'success') => {
      const id = nextId.current++
      setToasts((t) => [...t.slice(-3), { id, kind, text, leaving: false }])
      arm(id)
    },
    [arm],
  )

  useEffect(() => {
    const map = timers.current
    return () => {
      for (const t of map.values()) window.clearTimeout(t)
    }
  }, [])

  const region = (
    <div className="pointer-events-none fixed inset-x-3 top-3 z-[100] flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6 sm:top-[calc(var(--bar-height)+12px)] sm:w-[360px]">
      <div aria-live="polite" role="status" className="flex w-full flex-col items-end gap-2">
        {toasts
          .filter((t) => t.kind !== 'warning')
          .map((t) => (
            <ToastView key={t.id} toast={t} onDismiss={dismiss} onPause={pause} onResume={arm} />
          ))}
      </div>
      <div aria-live="assertive" role="alert" className="flex w-full flex-col items-end gap-2">
        {toasts
          .filter((t) => t.kind === 'warning')
          .map((t) => (
            <ToastView key={t.id} toast={t} onDismiss={dismiss} onPause={pause} onResume={arm} />
          ))}
      </div>
    </div>
  )

  return (
    <ToastContext.Provider value={push}>
      {children}
      {typeof document !== 'undefined' ? createPortal(region, document.body) : region}
    </ToastContext.Provider>
  )
}

function ToastView({
  toast,
  onDismiss,
  onPause,
  onResume,
}: {
  toast: ToastItem
  onDismiss: (id: number) => void
  onPause: (id: number) => void
  onResume: (id: number) => void
}) {
  const k = KIND[toast.kind]
  return (
    <button
      type="button"
      onClick={() => onDismiss(toast.id)}
      onPointerEnter={() => onPause(toast.id)}
      onPointerLeave={() => onResume(toast.id)}
      onFocus={() => onPause(toast.id)}
      onBlur={() => onResume(toast.id)}
      aria-label={`${k.label}: ${toast.text}. Dismiss`}
      className={`overlay pointer-events-auto flex min-h-11 max-w-full cursor-pointer items-center gap-2.5 !rounded-pill py-2 pl-2 pr-4 text-left text-copy font-medium text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
        toast.leaving ? 'animate-toastOut' : 'animate-toastIn'
      }`}
    >
      <Tile family={k.family} icon={k.icon} className="!rounded-pill" />
      <span className="min-w-0">{toast.text}</span>
    </button>
  )
}
