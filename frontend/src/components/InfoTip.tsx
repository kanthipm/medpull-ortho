import { Info } from 'lucide-react'
import { useId, useRef, useState, type MouseEvent } from 'react'
import type { Explanation } from '../api/explain'
import { Popover } from './Menu'

/** The "i" beside a chart or metric: a 32px round icon button that opens the
 *  in-depth explanation as a top-layer popover (R5). A hover tooltip would
 *  not do — the text is five short sections, and a reader on a keyboard or
 *  a touch screen needs to be able to open, read and dismiss it.
 *
 *  Renders nothing until the glossary entry is in hand, so a page never
 *  shows an icon that opens an empty panel. The button is `.btn-icon .btn-sm`
 *  (body glyph, fill on hover, focus ring from the button set); on a dark
 *  gradient tile the caller passes `onTile` for a white glyph on the glass.
 *
 *  Never nested inside another button: the headline tiles place it as a
 *  sibling positioned over the tile, and the click stops here so the tile
 *  does not open Full stats underneath the popover. */
export default function InfoTip({
  entry,
  className = '',
  onTile = false,
  placement = 'bottom-end',
}: {
  entry: Explanation | undefined
  className?: string
  /** On a gradient tile's dark top band: white glyph, glass fill. */
  onTile?: boolean
  placement?: 'bottom-start' | 'bottom-end' | 'bottom' | 'top-start' | 'top-end' | 'top'
}) {
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLButtonElement>(null)
  const id = useId()
  if (!entry) return null

  const toggle = (e: MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    setOpen((o) => !o)
  }

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        onClick={toggle}
        aria-label={`About ${entry.title}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        className={`btn-icon btn-sm ${
          onTile ? '!text-white hover:!bg-white/15 hover:!text-white' : ''
        } ${className}`}
      >
        <Info aria-hidden size={16} />
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={anchorRef}
        placement={placement}
        variant="popover"
        role="dialog"
        id={id}
        aria-label={`About ${entry.title}`}
        className="w-[22rem] max-w-[calc(100vw-16px)] p-4"
      >
        <h3 className="text-copy-lg font-medium text-ink">{entry.title}</h3>
        <dl className="mt-3 space-y-3">
          <Section label="What it measures" body={entry.what} />
          <Section label="Data it takes in" body={entry.inputs} />
          <Section label="How it’s computed" body={entry.how} />
          <Section label="How to read it" body={entry.reading} />
          <Section label="Shows after" body={entry.shows_after} />
        </dl>
      </Popover>
    </>
  )
}

function Section({ label, body }: { label: string; body: string }) {
  if (!body) return null
  return (
    <div>
      <dt className="meta">{label}</dt>
      <dd className="mt-0.5 text-copy text-body">{body}</dd>
    </div>
  )
}
