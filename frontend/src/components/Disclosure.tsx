import { ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'

/** Progressive disclosure with a smooth grid-rows expand (300ms, the ceiling;
 *  killed by the prefers-reduced-motion block in index.css). */
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
        className="group flex w-full cursor-pointer items-center gap-2 rounded-control px-1 py-2 text-left text-copy font-medium text-body transition-colors duration-150 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      >
        {/* --muted, not --faint: the chevron is the only thing that states
            whether the section is open, so WCAG 1.4.11's 3:1 applies to it and
            --faint is 2.585:1 on panel. */}
        <ChevronRight
          size={16}
          className={`text-muted transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
        />
        {label}
        {hint && !open && <span className="text-label text-muted">{hint}</span>}
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
