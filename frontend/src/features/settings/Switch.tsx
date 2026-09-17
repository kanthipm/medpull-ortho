import { useState } from 'react'

/** iOS-style switch for the settings pages (W6).
 *
 *  Track 44x26 capsule, knob 22px white with the knob contact shadow, sliding
 *  on --ease-spring (Reduce Motion shortens it through the token). State is
 *  never colour alone: the knob POSITION is the state, and role="switch" +
 *  aria-checked announce it.
 *
 *  Contrast (WCAG 1.4.11, 3:1 for control parts), light / dark:
 *    on  track --brand on --panel           4.602 / 3.736; knob on it 4.602
 *    off track --line-strong on --panel     3.834 / 5.671; knob on it 3.834 / 3.032
 *    disabled: --disabled-fill track keeps an inset --line-strong edge
 *              (3.834 / 5.671 on panel; the fill alone is 1.134 / 1.071),
 *              knob --disabled-ink (4.755 / 4.582 on the fill).
 *    focus ring --focus on --panel          4.602 / 6.783, 2px offset. */
export default function Switch({
  checked,
  onChange,
  disabled = false,
  busy = false,
  id,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
  className = '',
}: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  /** A save is in flight: ignore clicks without greying the switch out. */
  busy?: boolean
  id?: string
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  className?: string
}) {
  // Skip the slide on first paint so a page load does not animate every knob.
  const [armed, setArmed] = useState(false)
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
      aria-describedby={ariaDescribedby}
      aria-busy={busy || undefined}
      disabled={disabled}
      onClick={() => {
        if (busy) return
        setArmed(true)
        onChange(!checked)
      }}
      className={`relative inline-flex h-[26px] w-11 shrink-0 cursor-pointer items-center rounded-pill transition-colors duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed forced-colors:border forced-colors:border-[ButtonText] ${
        disabled
          ? 'bg-disabled-fill shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]'
          : checked
            ? 'bg-brand'
            : 'bg-line-strong'
      } ${className}`}
    >
      {/* Before/after the tap the thumb is the only moving part. */}
      <span
        aria-hidden
        className={`absolute left-[2px] top-[2px] h-[22px] w-[22px] rounded-pill shadow-knob forced-colors:bg-[ButtonText] ${
          armed ? 'transition-transform duration-spring ease-spring' : ''
        } ${disabled ? 'bg-disabled-ink' : 'bg-n-0'} ${
          checked ? 'translate-x-[18px]' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

/** One settings row whose trailing control is a Switch. The text column is
 *  the switch's label (click it to toggle), like an iOS settings cell. */
export function SwitchRow({
  id,
  leading,
  title,
  detail,
  checked,
  onChange,
  disabled,
  busy,
  badge,
}: {
  id: string
  leading?: React.ReactNode
  title: string
  detail?: React.ReactNode
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  busy?: boolean
  /** A state chip after the title, e.g. "Coming soon". */
  badge?: React.ReactNode
}) {
  const labelId = `${id}-label`
  const detailId = `${id}-detail`
  return (
    <li className="card-row grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3">
      {leading ? <span className="flex shrink-0 items-center">{leading}</span> : <span />}
      <div className="min-w-0">
        <label
          htmlFor={id}
          id={labelId}
          className={`flex flex-wrap items-center gap-2 text-copy-lg font-medium text-ink ${
            disabled ? 'cursor-default' : 'cursor-pointer'
          }`}
        >
          {title}
          {badge}
        </label>
        {detail && (
          <p id={detailId} className="mt-0.5 text-copy text-secondary">
            {detail}
          </p>
        )}
      </div>
      <Switch
        id={id}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        busy={busy}
        aria-labelledby={labelId}
        aria-describedby={detail ? detailId : undefined}
      />
    </li>
  )
}

/** iOS grouped-list section header / footer (sentence case, secondary). */
export function GroupHeader({ id, children, aside }: { id?: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3 px-4">
      <h2 id={id} className="text-copy font-medium text-secondary">
        {children}
      </h2>
      {aside}
    </div>
  )
}

export function GroupFooter({ children }: { children: React.ReactNode }) {
  return <p className="meta mt-2 px-4">{children}</p>
}

/** Page title block shared by the settings pages. It sits on the ambient wash,
 *  so the intro is --body, not --muted: dark muted on the wash's brand-tint
 *  peak is 4.067, body is 5.513 (light 6.237). */
export function SettingsHeading({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <>
      <h1 className="text-section font-semibold text-ink">{title}</h1>
      {children && <p className="mt-2 max-w-2xl text-copy-lg text-body">{children}</p>}
    </>
  )
}
