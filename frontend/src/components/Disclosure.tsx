import { ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'

/** Progressive disclosure with a smooth grid-rows expand. */
export default function Disclosure({
  label,
  hint,
  defaultOpen = false,
  children,
}: {
  label: string
  hint?: string
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex w-full cursor-pointer items-center gap-2 rounded-btn px-1 py-2 text-left text-[13px] font-medium text-body transition-colors duration-150 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      >
        <ChevronRight
          size={15}
          className={`text-faint transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
        />
        {label}
        {hint && !open && <span className="text-[12px] font-medium text-faint">{hint}</span>}
      </button>
      <div
        className="grid transition-[grid-template-rows,opacity] duration-300 ease-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr', opacity: open ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <div className="mt-1 border-t border-line pt-2.5">{children}</div>
        </div>
      </div>
    </div>
  )
}
