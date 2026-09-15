import { X } from 'lucide-react'
import type { DraftTask, KindInfo, ParamField, TaskPhase, TaskSchedule, TheirTaskKind } from '../../../api/plan'
import { PHASES, SCHEDULES, THEIR_KINDS } from '../../../api/plan'
import { defaultParams, kindInfo, numberWarning, titleCase } from './planCopy'

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
    <div className="rounded-row border border-line bg-soft/40 p-3">
      <div className="mb-2.5 flex items-center gap-2">
        {index != null && (
          <span className="chip bg-panel font-mono tabular-nums text-faint">{index + 1}</span>
        )}
        <span className="text-[11px] font-medium text-muted">
          {info?.label ?? titleCase(value.verify_kind)}
          {value.source_template_key && (
            <span className="ml-1.5 font-mono text-[10.5px] text-faint">· {value.source_template_key}</span>
          )}
        </span>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remove task"
            className="ml-auto grid h-6 w-6 cursor-pointer place-items-center rounded-btn text-faint transition-colors duration-150 hover:bg-panel hover:text-ink"
          >
            <X size={13} />
          </button>
        )}
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor={`${id}-title`} className="micro mb-1 block">
            Title <span className="normal-case tracking-normal">(patient sees this)</span>
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
          <label htmlFor={`${id}-why`} className="micro mb-1 block">
            Why <span className="normal-case tracking-normal">(patient sees this)</span>
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
          <label htmlFor={`${id}-target`} className="micro mb-1 block">
            Clinical target <span className="normal-case tracking-normal">(care team only)</span>
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
        <p className="mt-2.5 text-[12px] font-medium leading-snug text-muted">{value.rationale}</p>
      )}

      {libraryToggles && (
        <div className="mt-2.5 flex flex-wrap items-center gap-4">
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
  return <p className="mt-1 text-[11px] font-medium leading-snug text-risk-med">{children}</p>
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
      <label htmlFor={id} className="micro mb-1 block">
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
      <div className="flex items-end pb-2">
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
        <label htmlFor={id} className="micro mb-1 block">
          {label} <span className="normal-case tracking-normal">(comma-separated)</span>
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
      <label htmlFor={id} className="micro mb-1 block">
        {label}
      </label>
      <input
        id={id}
        className="field font-mono tabular-nums"
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
      className={`inline-flex items-center gap-2 text-[12.5px] font-medium ${
        disabled ? 'cursor-not-allowed text-faint' : 'cursor-pointer text-body'
      }`}
    >
      <input
        id={id}
        type="checkbox"
        className="h-3.5 w-3.5 cursor-pointer accent-[rgb(var(--brand))] disabled:cursor-not-allowed"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}
