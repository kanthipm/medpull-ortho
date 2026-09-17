import { Sparkles, X } from 'lucide-react'
import type { DraftTask, KindInfo, ParamField, TaskPhase, TaskSchedule, TheirTaskKind } from '../../../api/plan'
import { PHASES, SCHEDULES, THEIR_KINDS } from '../../../api/plan'
import { defaultParams, kindInfo, numberWarning, titleCase } from './planCopy'

/** Field label: 12/500 secondary. The row sits on --soft. Inside the Modal
 *  secondary is --body (6.367 light / 6.211 dark on --soft); on the settings
 *  page it is --muted (4.755 / 4.582 on --soft). Both pass AA. */
const LABEL = 'mb-1 block px-1 text-label font-medium tracking-label text-secondary'

/** One editable draft row — the builder's draft list and the library's
 *  "New template" form share it. Verify kind drives the params fields (from
 *  `kinds[].params_schema`) and the default lifecycle kind. */
export default function DraftRowEditor({
  value,
  kinds,
  onChange,
  onRemove,
  libraryToggles = true,
  index,
}: {
  value: DraftTask
  kinds: KindInfo[]
  onChange: (next: DraftTask) => void
  onRemove?: () => void
  /** The builder shows "Save to library" / "Pin"; the library form hides them. */
  libraryToggles?: boolean
  index?: number
}) {
  const info = kindInfo(kinds, value.verify_kind)
  const set = <K extends keyof DraftTask>(key: K, v: DraftTask[K]) => onChange({ ...value, [key]: v })
  const setParam = (name: string, v: unknown) => onChange({ ...value, params: { ...value.params, [name]: v } })
  const changeKind = (kind: string) => {
    const next = kindInfo(kinds, kind)
    onChange({
      ...value,
      verify_kind: kind,
      task_kind: next?.task_kind ?? value.task_kind,
      params: defaultParams(next?.params_schema),
    })
  }
  const titleWarn = numberWarning(value.title, value.title)
  const whyWarn = numberWarning(value.why, value.title)
  const id = `draft-${index ?? 'row'}`

  return (
    <div className="rounded-surface bg-soft p-4">
      <div className="mb-3 flex items-center gap-3">
        {index != null && (
          <span
            aria-hidden
            className="grid h-7 w-7 shrink-0 place-items-center rounded-pill bg-panel text-label font-medium tabular-nums text-ink"
          >
            {index + 1}
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-copy font-medium text-ink">
            {index != null && <span className="sr-only">Task {index + 1}: </span>}
            {info?.label ?? titleCase(value.verify_kind)}
          </span>
          {value.source_template_key && (
            <span className="meta block truncate font-mono">{value.source_template_key}</span>
          )}
        </span>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${value.title.trim() || `task ${index != null ? index + 1 : ''}`.trim()}`}
            title="Remove from the draft list"
            className="btn-icon btn-sm -mr-1 shrink-0 hover:!bg-panel"
          >
            <X aria-hidden />
          </button>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor={`${id}-title`} className={LABEL}>
            Title (patient sees this)
          </label>
          <input
            id={`${id}-title`}
            className="field"
            value={value.title}
            placeholder="e.g. Take three short walks spread across the day"
            onChange={(e) => set('title', e.target.value)}
          />
          {titleWarn && <Hint>{titleWarn}</Hint>}
        </div>
        <div className="sm:col-span-2">
          <label htmlFor={`${id}-why`} className={LABEL}>
            Why (patient sees this)
          </label>
          <input
            id={`${id}-why`}
            className="field"
            value={value.why}
            placeholder="e.g. Gentle, frequent movement helps you heal."
            onChange={(e) => set('why', e.target.value)}
          />
          {whyWarn && <Hint>{whyWarn}</Hint>}
        </div>
        <div className="sm:col-span-2">
          <label htmlFor={`${id}-target`} className={LABEL}>
            Clinical target (care team only)
          </label>
          <input
            id={`${id}-target`}
            className="field"
            value={value.clinical_target}
            placeholder="e.g. Early mobilization, DVT prevention"
            onChange={(e) => set('clinical_target', e.target.value)}
          />
        </div>

        <Select
          id={`${id}-verify`}
          label="Verified by"
          value={value.verify_kind}
          onChange={changeKind}
          options={
            kinds.length
              ? kinds.map((k) => ({ key: k.kind, label: `${k.label} · ${k.verified_by}` }))
              : [{ key: value.verify_kind, label: titleCase(value.verify_kind) }]
          }
        />
        <Select
          id={`${id}-kind`}
          label="Conversation"
          value={value.task_kind}
          onChange={(v) => set('task_kind', v as TheirTaskKind)}
          options={THEIR_KINDS}
        />
        <Select
          id={`${id}-schedule`}
          label="Schedule"
          value={value.schedule}
          onChange={(v) => set('schedule', v as TaskSchedule)}
          options={SCHEDULES}
        />
        <Select
          id={`${id}-phase`}
          label="Phase"
          value={value.phase}
          onChange={(v) => set('phase', v as TaskPhase)}
          options={PHASES}
        />

        {(info?.params_schema ?? []).map((f) => (
          <ParamInput
            key={f.name}
            id={`${id}-p-${f.name}`}
            field={f}
            value={value.params[f.name]}
            onChange={(v) => setParam(f.name, v)}
          />
        ))}
      </div>

      {value.rationale && (
        <p className="mt-3 flex items-start gap-1.5 px-1 text-label tracking-label text-secondary">
          <Sparkles aria-hidden size={12} className="mt-px shrink-0 text-cat-teal-ink" />
          <span>{value.rationale}</span>
        </p>
      )}

      {libraryToggles && (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 px-1">
          <Check
            id={`${id}-save`}
            label="Save to library"
            checked={value.save_as_template}
            onChange={(c) => onChange({ ...value, save_as_template: c, pin: c ? value.pin : false })}
          />
          <Check
            id={`${id}-pin`}
            label="Pin as quick pick"
            checked={value.pin}
            disabled={!value.save_as_template}
            onChange={(c) => set('pin', c)}
          />
        </div>
      )}
    </div>
  )
}

function Hint({ children }: { children: string }) {
  return <p className="mt-1 px-1 text-label font-medium text-risk-med-ink">{children}</p>
}

function Select({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  options: { key: string; label: string }[]
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <select id={id} className="field cursor-pointer" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function ParamInput({
  id,
  field,
  value,
  onChange,
}: {
  id: string
  field: ParamField
  value: unknown
  onChange: (v: unknown) => void
}) {
  const label = field.label || titleCase(field.name)
  if (field.type === 'bool') {
    return (
      <div className="flex items-end">
        <Check id={id} label={label} checked={Boolean(value)} onChange={onChange} />
      </div>
    )
  }
  if (field.type === 'enum' && field.options) {
    return (
      <Select
        id={id}
        label={label}
        value={String(value ?? field.default ?? field.options[0] ?? '')}
        onChange={onChange}
        options={field.options.map((o) => ({ key: o, label: titleCase(o) }))}
      />
    )
  }
  if (field.type === 'list') {
    const items = Array.isArray(value) ? value.map(String) : []
    return (
      <div>
        <label htmlFor={id} className={LABEL}>
          {label} (comma-separated)
        </label>
        <input
          id={id}
          className="field"
          value={items.join(', ')}
          placeholder={Array.isArray(field.default) ? field.default.join(', ') : ''}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
            )
          }
        />
      </div>
    )
  }
  const numeric = field.type === 'int' || field.type === 'float'
  return (
    <div>
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        className="field tabular-nums"
        type={numeric ? 'number' : 'text'}
        step={field.type === 'float' ? 'any' : 1}
        min={field.min}
        max={field.max}
        value={value == null ? '' : String(value)}
        placeholder={field.default == null ? 'auto' : String(field.default)}
        onChange={(e) => {
          const raw = e.target.value
          if (!numeric) return onChange(raw)
          if (raw === '') return onChange(null)
          const n = field.type === 'int' ? parseInt(raw, 10) : parseFloat(raw)
          onChange(Number.isNaN(n) ? null : n)
        }}
      />
    </div>
  )
}

function Check({
  id,
  label,
  checked,
  disabled,
  onChange,
}: {
  id: string
  label: string
  checked: boolean
  disabled?: boolean
  onChange: (c: boolean) => void
}) {
  return (
    <label
      htmlFor={id}
      className={`inline-flex min-h-9 items-center gap-2 text-copy ${
        disabled ? 'cursor-not-allowed text-secondary' : 'cursor-pointer text-ink'
      }`}
    >
      <input
        id={id}
        type="checkbox"
        className="h-4 w-4 cursor-pointer accent-brand disabled:cursor-not-allowed"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}
