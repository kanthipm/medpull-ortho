import { BookOpenCheck, Check, Flag, Gauge, ListChecks, Plus, ShieldAlert, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useState } from 'react'
import {
  usePtCatalog,
  usePtFlags,
  usePtSettings,
  useProtocolAction,
  useProtocols,
  useRedFlagAction,
  useRedFlags,
  useUpdatePtSettings,
  type PtFlagRule,
  type PtProtocol,
  type PtRedFlag,
  type PtSettings,
} from '../../api/pt'
import Modal from '../../components/Modal'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import ExercisesNav from '../hep/ExercisesNav'
import { SettingsHero } from '../settings/Switch'
import { ActingAs, Pill } from './ptBits'
import { errorText, useActingAs } from './ptWords'

const LABELS: Record<string, string> = {
  load_watch_ratio: 'Raise the flag at (× recent average)',
  load_spike_ratio: 'High at (× recent average)',
  pain_rise_points: 'Points above the week before',
  program_low: 'Share of the program done (0 to 1)',
  quiet_days: 'Days without a check-in',
  quiet_days_high: 'High after (days)',
}

/** `/calendar/rules` — what the clinic itself decides, in one place: what
 *  each flag fires on (and how often it has), the fixed words that answer a
 *  short list of worrying messages, which questions cannot wait for the
 *  weekly block, how many exercises a day may carry before the calendar
 *  asks, what is asked by itself, the change that counts on each outcome
 *  measure, and the clinic's protocols.
 *
 *  Every rule on this page is a sentence a clinician can read and a number
 *  she can change. None of it is a model. */
export default function RulesPage() {
  const catalog = usePtCatalog()
  const team = catalog.data?.care_team ?? []
  const [by, setBy] = useActingAs(team)
  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<SlidersHorizontal />}
        title="Rules"
        decor={[<Flag key="f" />, <ShieldAlert key="s" />, <ListChecks key="l" />]}
      >
        What your clinic decides for itself: what each flag fires on, the words that go back when a message cannot
        wait, your protocols and their criteria. Every rule here is a sentence you can read and a number you can
        change.
      </SettingsHero>
      <div className="mt-6 flex justify-end">
        <ActingAs team={team} value={by} onChange={setBy} />
      </div>
      <div className="mt-4 space-y-6">
        <FlagRules by={by} />
        <RedFlags by={by} />
        <ClinicSettings by={by} />
        <Protocols by={by} />
      </div>
    </div>
  )
}

// --- flags ----------------------------------------------------------------------------

function FlagRules({ by }: { by: string }) {
  const flags = usePtFlags()
  if (flags.isLoading) return <SkeletonCard rows={4} />
  return (
    <SectionCard
      title="Flags"
      icon={<Tile size="sm" family="indigo" icon={<Flag />} />}
      aside="For charts followed by check-ins"
    >
      <ul className="divide-y divide-line">
        {(flags.data?.flags ?? []).map((f) => (
          <FlagRow key={f.code} flag={f} by={by} />
        ))}
      </ul>
      <p className="meta mt-3">
        Changing a threshold rescores every chart in the clinic on its next read. The load tile on a chart keeps
        the product’s own band (0.8 to 1.3 times), whatever is set here.
      </p>
    </SectionCard>
  )
}

function FlagRow({ flag, by }: { flag: PtFlagRule; by: string }) {
  const toast = useToast()
  const save = useUpdatePtSettings()
  const [draft, setDraft] = useState<Record<string, string>>({})
  const dirty = flag.thresholds.some((t) => draft[t.key] != null && Number(draft[t.key]) !== t.value)
  const changed = flag.thresholds.some((t) => t.changed)
  const send = (flags: Record<string, number | null>) =>
    save.mutate(
      { flags, by } as Partial<PtSettings> & { flags: Record<string, number | null> },
      {
        onSuccess: () => {
          setDraft({})
          toast('Saved. Charts are rescored on their next read.', 'success')
        },
        onError: (e) => toast(errorText(e), 'warning'),
      },
    )
  const { today, charts, chart_days, window_days } = flag.fired
  return (
    <li className="py-4 first:pt-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-copy-lg font-medium text-ink">{flag.name}</h3>
        <p className="text-label text-secondary tabular-nums">
          {today > 0 ? (
            <Pill tone="warn">
              Up on {today} {today === 1 ? 'chart' : 'charts'} today
            </Pill>
          ) : (
            <span>Not up today</span>
          )}
          <span className="ml-2">
            {chart_days} chart-{chart_days === 1 ? 'day' : 'days'} on {charts} {charts === 1 ? 'chart' : 'charts'} in{' '}
            {window_days} days
          </span>
        </p>
      </div>
      <p className="mt-1 text-copy text-ink">{flag.rule}</p>
      <p className="mt-0.5 text-copy text-secondary">Reads: {flag.inputs}</p>
      {flag.thresholds.length > 0 && (
        <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-2">
          {flag.thresholds.map((t) => (
            <label key={t.key} className="block">
              <span className="block text-label text-secondary">
                {LABELS[t.key] ?? t.key}
                {t.changed && <span className="ml-1 text-brand-ink">· default {t.default}</span>}
              </span>
              <input
                type="number"
                step={t.whole ? 1 : 0.1}
                min={t.low}
                max={t.high}
                className="field mt-1 !w-28"
                value={draft[t.key] ?? String(t.value)}
                onChange={(e) => setDraft((d) => ({ ...d, [t.key]: e.target.value }))}
              />
            </label>
          ))}
          <button
            type="button"
            className="btn-tinted btn-sm"
            disabled={!dirty || save.isPending}
            onClick={() =>
              send(Object.fromEntries(flag.thresholds.map((t) => [t.key, Number(draft[t.key] ?? t.value)])))
            }
          >
            Save
          </button>
          {changed && (
            <button
              type="button"
              className="btn-plain btn-sm"
              disabled={save.isPending}
              onClick={() => send(Object.fromEntries(flag.thresholds.map((t) => [t.key, null])))}
            >
              Back to the defaults
            </button>
          )}
        </div>
      )}
    </li>
  )
}

// --- red flags ------------------------------------------------------------------------

function RedFlags({ by }: { by: string }) {
  const flags = useRedFlags()
  const act = useRedFlagAction()
  const toast = useToast()
  const [label, setLabel] = useState('')
  const [phrases, setPhrases] = useState('')
  if (flags.isLoading) return <SkeletonCard rows={3} />
  const entries = flags.data?.entries ?? []
  return (
    <SectionCard title="Red-flag messages" icon={<Tile size="sm" family="risk-high" icon={<ShieldAlert />} />}>
      <p className="text-copy text-secondary">
        A short list of things that should never sit unread. A message that matches one is marked, goes to today, and
        raises your notice. What goes back is your own text for it, word for word, once one of you has approved it.
        Until then it is this one line, and the assistant never answers a message that matched:
      </p>
      <p className="mt-2 rounded-control bg-soft px-3 py-2 text-copy text-ink">{flags.data?.standing_reply}</p>
      <ul className="mt-3 divide-y divide-line">
        {entries.map((e) => (
          <RedFlagRow key={e.id} entry={e} by={by} />
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input className="field !w-64" placeholder="Another thing to listen for" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="What the entry is for" />
        <input className="field min-w-[14rem] flex-1" placeholder="Phrases, separated by commas" value={phrases} onChange={(e) => setPhrases(e.target.value)} aria-label="Phrases to listen for" />
        <button
          type="button"
          className="btn-gray btn-sm"
          disabled={!label.trim() || !phrases.trim() || act.isPending}
          onClick={() =>
            act.mutate(
              { body: { label, phrases: phrases.split(',').map((p) => p.trim()).filter(Boolean), text: '', by } },
              {
                onSuccess: () => {
                  setLabel('')
                  setPhrases('')
                },
                onError: (e) => toast(errorText(e), 'warning'),
              },
            )
          }
        >
          <Plus aria-hidden /> Add
        </button>
      </div>
    </SectionCard>
  )
}

function RedFlagRow({ entry, by }: { entry: PtRedFlag; by: string }) {
  const toast = useToast()
  const act = useRedFlagAction()
  const [text, setText] = useState(entry.text)
  const [phrases, setPhrases] = useState(entry.phrases.join(', '))
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const list = phrases.split(',').map((p) => p.trim()).filter(Boolean)
  const dirty = text !== entry.text || list.join(',') !== entry.phrases.join(',')
  const approved = entry.status === 'approved'
  return (
    <li className="py-4 first:pt-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-copy-lg font-medium text-ink">{entry.label}</h3>
        <Pill tone={approved ? 'brand' : 'plain'}>
          {approved ? (
            <>
              <Check aria-hidden size={12} /> Approved: your words go out
            </>
          ) : (
            'Draft: the standing line goes out'
          )}
        </Pill>
      </div>
      <label className="mt-2 block">
        <span className="text-label text-secondary">Listens for</span>
        <input className="field mt-1" value={phrases} onChange={(e) => setPhrases(e.target.value)} />
      </label>
      <label className="mt-2 block">
        <span className="text-label text-secondary">Your text</span>
        <textarea className="field mt-1 resize-y" rows={2} maxLength={480} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-tinted btn-sm"
          disabled={!dirty || act.isPending}
          onClick={() =>
            act.mutate(
              { path: `/${entry.id}`, method: 'PATCH', body: { text, phrases: list, by } },
              { onSuccess: () => toast('Saved as a draft: approve it to send it', 'info'), onError: fail },
            )
          }
        >
          Save
        </button>
        {approved ? (
          <button
            type="button"
            className="btn-plain btn-sm"
            disabled={act.isPending}
            onClick={() => act.mutate({ path: `/${entry.id}/approve`, body: { by, approved: false } }, { onError: fail })}
          >
            Take the approval off
          </button>
        ) : (
          <button
            type="button"
            className="btn-gray btn-sm"
            disabled={dirty || !by || act.isPending}
            title={dirty ? 'Save the text first' : undefined}
            onClick={() =>
              act.mutate(
                { path: `/${entry.id}/approve`, body: { by, approved: true } },
                { onSuccess: () => toast('Approved under your name', 'success'), onError: fail },
              )
            }
          >
            <Check aria-hidden /> Approve these words
          </button>
        )}
        <button
          type="button"
          className="btn-icon btn-sm ml-auto"
          aria-label={`Delete the entry: ${entry.label}`}
          title="Delete this entry"
          disabled={act.isPending}
          onClick={() => act.mutate({ path: `/${entry.id}`, method: 'DELETE' }, { onError: fail })}
        >
          <Trash2 aria-hidden />
        </button>
      </div>
    </li>
  )
}

// --- the clinic's own settings ----------------------------------------------------------

function ClinicSettings({ by }: { by: string }) {
  const toast = useToast()
  const settings = usePtSettings()
  const catalog = usePtCatalog()
  const save = useUpdatePtSettings()
  const [words, setWords] = useState<string | null>(null)
  const [guard, setGuard] = useState<string | null>(null)
  const [thresholds, setThresholds] = useState<Record<string, string>>({})
  if (settings.isLoading || !settings.data) return <SkeletonCard rows={4} />
  const s = settings.data.settings
  const done = { onSuccess: () => toast('Saved', 'success'), onError: (e: unknown) => toast(errorText(e), 'warning') }
  const wordText = words ?? s.triage_words.join(', ')
  return (
    <SectionCard title="Questions, the calendar and what is asked" icon={<Tile size="sm" family="teal" icon={<Gauge />} />}>
      <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
        <div>
          <h3 className="text-label font-medium tracking-label text-secondary">A question is for today when it says</h3>
          <textarea className="field mt-1.5 resize-y" rows={4} value={wordText} onChange={(e) => setWords(e.target.value)} aria-label="Always-today words" />
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              className="btn-tinted btn-sm"
              disabled={words == null || save.isPending}
              onClick={() =>
                save.mutate(
                  { triage_words: wordText.split(',').map((w) => w.trim()).filter(Boolean), by } as Partial<PtSettings>,
                  { ...done, onSuccess: () => { setWords(null); toast('Saved', 'success') } },
                )
              }
            >
              Save the words
            </button>
            <span className="meta">Separated by commas. Every other question waits for the weekly block.</span>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <h3 className="text-label font-medium tracking-label text-secondary">Exercises on one day</h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-copy text-ink">
              Ask before a day goes past
              <input
                type="number"
                min={1}
                max={20}
                className="field !w-20 text-center"
                value={guard ?? String(s.exercise_guard)}
                onChange={(e) => setGuard(e.target.value)}
                aria-label="Exercise count"
              />
              exercises
              <button
                type="button"
                className="btn-tinted btn-sm"
                disabled={guard == null || save.isPending}
                onClick={() =>
                  save.mutate({ exercise_guard: Number(guard), by } as Partial<PtSettings>, {
                    ...done,
                    onSuccess: () => { setGuard(null); toast('Saved', 'success') },
                  })
                }
              >
                Save
              </button>
            </div>
          </div>
          <div>
            <h3 className="text-label font-medium tracking-label text-secondary">Asked without anyone pressing</h3>
            <label className="mt-1.5 flex items-start gap-2 text-copy text-ink">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-brand"
                checked={s.morning_check.on}
                onChange={(e) => save.mutate({ morning_check: { ...s.morning_check, on: e.target.checked }, by } as Partial<PtSettings>, done)}
              />
              <span>
                The morning after a loaded session: the pain now, and whether they are stiffer than usual. Settled
                means pain at or under {s.morning_check.ceiling} and no stiffer.
              </span>
            </label>
            <label className="mt-2 flex items-start gap-2 text-copy text-ink">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-brand"
                checked={s.week_checkin.on}
                onChange={(e) => save.mutate({ week_checkin: { on: e.target.checked }, by } as Partial<PtSettings>, done)}
              />
              <span>Every Friday: how the week went, and what is different about the next one.</span>
            </label>
            <p className="meta mt-2">
              These go out with the morning text, which this deployment can have off. Either one can be turned off
              for one person on their chart, and asked by hand from it at any time.
            </p>
          </div>
        </div>

        <div className="lg:col-span-2">
          <h3 className="text-label font-medium tracking-label text-secondary">The change that counts on an outcome measure</h3>
          <div className="mt-1.5 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-copy">
              <thead className="text-label text-secondary">
                <tr>
                  <th className="py-1 pr-3 font-medium">Measure</th>
                  <th className="py-1 pr-3 font-medium">Published</th>
                  <th className="py-1 pr-3 font-medium">Where from</th>
                  <th className="py-1 font-medium">Your own</th>
                </tr>
              </thead>
              <tbody>
                {(catalog.data?.instruments ?? []).map((i) => (
                  <tr key={i.key} className="border-t border-line align-top">
                    <td className="py-2 pr-3 text-ink">
                      {i.name}
                      <span className="block text-label text-secondary">
                        {i.mode === 'asked' ? 'Asked in the app' : 'Total entered from the clinic’s own copy'}
                      </span>
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-ink">
                      {i.threshold_is_clinic || i.threshold == null ? '—' : `${i.threshold} points`}
                    </td>
                    <td className="py-2 pr-3 text-label text-secondary">{i.source || i.note}</td>
                    <td className="py-2">
                      <span className="flex items-center gap-2">
                        <input
                          type="number"
                          min={0.5}
                          step={0.5}
                          className="field !h-8 !min-h-0 !w-20 !py-0 text-label"
                          placeholder="—"
                          value={thresholds[i.key] ?? (s.outcome_thresholds[i.key] != null ? String(s.outcome_thresholds[i.key]) : '')}
                          onChange={(e) => setThresholds((t) => ({ ...t, [i.key]: e.target.value }))}
                          aria-label={`Your own threshold for ${i.short}`}
                        />
                        {thresholds[i.key] != null && (
                          <button
                            type="button"
                            className="btn-plain btn-sm"
                            disabled={save.isPending}
                            onClick={() => {
                              const next: Record<string, number | null> = { ...s.outcome_thresholds }
                              next[i.key] = thresholds[i.key] === '' ? null : Number(thresholds[i.key])
                              save.mutate({ outcome_thresholds: next, by } as unknown as Partial<PtSettings>, {
                                ...done,
                                onSuccess: () => {
                                  setThresholds((t) => {
                                    const rest = { ...t }
                                    delete rest[i.key]
                                    return rest
                                  })
                                  toast('Saved', 'success')
                                },
                              })
                            }}
                          >
                            Save
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta mt-2">
            A threshold is a starting point, not a verdict: the chart shows the change beside it and says no more.
          </p>
        </div>
      </div>
    </SectionCard>
  )
}

// --- protocols ------------------------------------------------------------------------

type DraftPhase = { name: string; goal: string; criteria: string }
const blank = (): DraftPhase => ({ name: '', goal: '', criteria: '' })

function Protocols({ by }: { by: string }) {
  const protocols = useProtocols()
  const [open, setOpen] = useState<PtProtocol | 'new' | null>(null)
  if (protocols.isLoading) return <SkeletonCard rows={2} />
  const list = protocols.data?.protocols ?? []
  return (
    <SectionCard
      title="Protocols"
      icon={<Tile size="sm" family="violet" icon={<BookOpenCheck />} />}
      action={
        <button type="button" className="btn-plain btn-sm" onClick={() => setOpen('new')}>
          <Plus aria-hidden /> New protocol
        </button>
      }
    >
      <p className="text-copy text-secondary">
        A protocol is phases, each with the criteria you look for before the next. A person is put on one from their
        chart; you tick the criteria and you move the phase.
      </p>
      {list.length === 0 ? (
        <p className="mt-3 text-copy text-secondary">No protocols yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-line">
          {list.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-copy-lg font-medium text-ink">{p.name}</p>
                <p className="text-copy text-secondary">{p.phases.map((ph) => ph.name).join(' → ')}</p>
              </div>
              <button type="button" className="btn-gray btn-sm" onClick={() => setOpen(p)}>
                Edit
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && <ProtocolEditor protocol={open === 'new' ? null : open} by={by} onClose={() => setOpen(null)} />}
    </SectionCard>
  )
}

function ProtocolEditor({ protocol, by, onClose }: { protocol: PtProtocol | null; by: string; onClose: () => void }) {
  const toast = useToast()
  const act = useProtocolAction()
  const [name, setName] = useState(protocol?.name ?? '')
  const [description, setDescription] = useState(protocol?.description ?? '')
  const [phases, setPhases] = useState<DraftPhase[]>(
    protocol?.phases.map((p) => ({ name: p.name, goal: p.goal, criteria: p.criteria.join('\n') })) ?? [blank(), blank()],
  )
  const set = (i: number, patch: Partial<DraftPhase>) =>
    setPhases((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  const body = {
    name,
    description,
    by,
    phases: phases
      .filter((p) => p.name.trim())
      .map((p) => ({ name: p.name, goal: p.goal, criteria: p.criteria.split('\n').map((c) => c.trim()).filter(Boolean) })),
  }
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  return (
    <Modal
      size="lg"
      title={protocol ? 'Edit protocol' : 'New protocol'}
      description="People already on it keep the phases they were given; a change shows for the next person put on it."
      onClose={onClose}
      footer={
        <div className="flex items-center gap-2">
          {protocol && (
            <button
              type="button"
              className="btn-plain btn-sm"
              disabled={act.isPending}
              onClick={() => act.mutate({ path: `/${protocol.id}`, method: 'DELETE' }, { onSuccess: onClose, onError: fail })}
            >
              <Trash2 aria-hidden /> Archive
            </button>
          )}
          <button type="button" className="btn-plain ml-auto" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-filled"
            disabled={!name.trim() || body.phases.length === 0 || act.isPending}
            onClick={() =>
              act.mutate(
                protocol ? { path: `/${protocol.id}`, method: 'PUT', body } : { body },
                { onSuccess: onClose, onError: fail },
              )
            }
          >
            Save
          </button>
        </div>
      }
    >
      <div className="space-y-3 pt-1">
        <input className="field" placeholder="Name, e.g. Patellar tendon · in season" value={name} onChange={(e) => setName(e.target.value)} aria-label="Protocol name" />
        <input className="field" placeholder="A line about it (optional)" value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
        <ol className="space-y-3">
          {phases.map((p, i) => (
            <li key={i} className="rounded-surface border border-line p-3">
              <div className="flex items-center gap-2">
                <span className="text-label font-medium tabular-nums text-secondary">Phase {i + 1}</span>
                {phases.length > 1 && (
                  <button type="button" className="btn-icon btn-sm ml-auto" aria-label={`Remove phase ${i + 1}`} onClick={() => setPhases((ps) => ps.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                  </button>
                )}
              </div>
              <input className="field mt-1.5" placeholder="Name" value={p.name} onChange={(e) => set(i, { name: e.target.value })} aria-label={`Phase ${i + 1} name`} />
              <input className="field mt-1.5" placeholder="What it is for" value={p.goal} onChange={(e) => set(i, { goal: e.target.value })} aria-label={`Phase ${i + 1} goal`} />
              <textarea className="field mt-1.5 resize-y" rows={3} placeholder="Criteria to move on, one to a line" value={p.criteria} onChange={(e) => set(i, { criteria: e.target.value })} aria-label={`Phase ${i + 1} criteria`} />
            </li>
          ))}
        </ol>
        {phases.length < 8 && (
          <button type="button" className="btn-gray btn-sm" onClick={() => setPhases((ps) => [...ps, blank()])}>
            <Plus aria-hidden /> Add a phase
          </button>
        )}
      </div>
    </Modal>
  )
}
