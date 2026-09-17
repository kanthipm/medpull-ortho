import { ChevronRight } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

/** Progressive disclosure: a plain row button with a rotating chevron and a
 *  smooth grid-rows expand on the Apple ease (collapses to a quick fade under
 *  Reduce Motion). No rule above the content.
 *
 *  The chevron is the only mark of the open state besides aria-expanded, so
 *  it uses the secondary colour (--muted 5.393 / 4.906), not --faint. */
export default function Disclosure({
  label,
  hint,
  defaultOpen = false,
  children,
  className = '',
}: {
  label: string
  hint?: string
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()
  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        className="-mx-2 flex min-h-9 w-[calc(100%+1rem)] cursor-pointer items-center gap-2 rounded-control-sm px-2 text-left text-copy font-medium text-ink transition-colors duration-state ease-apple hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
      >
        <ChevronRight
          aria-hidden
          size={16}
          className={`shrink-0 text-secondary transition-transform duration-state ease-apple ${open ? 'rotate-90' : ''}`}
        />
        {label}
        {hint && !open && <span className="meta">{hint}</span>}
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows,opacity] duration-spring ease-apple"
        style={{ gridTemplateRows: open ? '1fr' : '0fr', opacity: open ? 1 : 0 }}
        inert={!open}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="pt-2">{children}</div>
        </div>
      </div>
    </div>
  )
}
