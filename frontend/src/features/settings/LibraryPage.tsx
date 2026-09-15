import { Archive, ArchiveRestore, Plus, Star } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { DraftTask, MessageTemplate, MessageTone, TaskTemplate } from '../../api/plan'
import {
  useCreateMessageTemplate,
  useCreateTaskTemplate,
  useMessageTemplates,
  useTaskTemplates,
  useUpdateMessageTemplate,
  useUpdateTaskTemplate,
} from '../../api/plan'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import DraftRowEditor from '../patient/plan/DraftRowEditor'
import {
  blankDraft,
  kindInfo,
  kindLabel,
  numberWarning,
  pathwayName,
  phaseLabel,
  titleCase,
  ucLabel,
} from '../patient/plan/planCopy'
import SettingsNav from './SettingsNav'

type Tab = 'tasks' | 'messages'
const TABS: { key: Tab; label: string }[] = [
  { key: 'tasks', label: 'Tasks' },
  { key: 'messages', label: 'Messages' },
]
const TONES: { key: MessageTone; label: string }[] = [
  { key: 'warm', label: 'Warm' },
  { key: 'direct', label: 'Direct' },
]
const PATHWAY_KEYS = [
  'ortho_tka', 'ortho_tha', 'ortho_acl', 'ortho_meniscus', 'ortho_ankle', 'ortho_shoulder',
  'ortho_spine', 'heart_failure', 'copd', 'diabetes', 'hypertension', 'chronic_pain',
  'general_recovery',
]

/** `/settings/library` — the reusable care-plan tasks and patient messages.
 *  Pinned rows are the quick picks the builder and composer offer first. */
export default function LibraryPage() {
  const [tab, setTab] = useState<Tab>('tasks')
  const [showArchived, setShowArchived] = useState(false)
  const [creating, setCreating] = useState(false)

  return (
    <div>
      <div className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <SettingsNav className="mb-4" />
        <h1 className="text-[26px] font-semibold tracking-[-.03em] text-ink">Library</h1>
        <p className="mt-1 text-[13px] font-medium text-muted">
          Care-plan tasks and patient messages the team reuses. Pinned ones show first as quick picks.
        </p>
      </div>

      <div
        className="rise mt-6 flex flex-wrap items-center gap-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <SegmentedControl<Tab>
          options={TABS}
          value={tab}
          onChange={(t) => {
            setTab(t)
            setCreating(false)
          }}
          aria-label="Library section"
        />
        <label className="inline-flex cursor-pointer items-center gap-2 text-[12.5px] font-medium text-muted">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-[rgb(var(--brand))]"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
        <button type="button" className="qa-btn ml-auto" onClick={() => setCreating((c) => !c)}>
          <Plus size={13} className="text-brand" /> New template
        </button>
      </div>

      <div className="rise mt-4" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        {tab === 'tasks' ? (
          <TaskLibrary showArchived={showArchived} creating={creating} onDone={() => setCreating(false)} />
        ) : (
          <MessageLibrary showArchived={showArchived} creating={creating} onDone={() => setCreating(false)} />
        )}
      </div>

      <p className="mt-4 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
        Titles, reasons and message bodies are what patients see — keep them plain and number-free.
        Clinical targets stay with the care team.
      </p>
    </div>
  )
}

// --- tasks ---------------------------------------------------------------------

function TaskLibrary({
  showArchived,
  creating,
  onDone,
}: {
  showArchived: boolean
  creating: boolean
  onDone: () => void
}) {
  const toast = useToast()
  const library = useTaskTemplates(undefined, showArchived)
  const update = useUpdateTaskTemplate()
  const create = useCreateTaskTemplate()
  const kinds = library.data?.kinds ?? []
  const [draft, setDraft] = useState<DraftTask>(() => blankDraft(undefined))
  const [pathways, setPathways] = useState<string[]>([])
  const [pinned, setPinned] = useState(false)

  const rows = (library.data?.templates ?? [])
    .filter((t) => showArchived || !t.archived)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.usage_count - a.usage_count || a.title.localeCompare(b.title))

  const save = () => {
    if (!draft.title.trim()) return
    create.mutate(
      {
        title: draft.title.trim(),
        why: draft.why.trim(),
        clinical_target: draft.clinical_target.trim(),
        verify_kind: draft.verify_kind,
        task_kind: draft.task_kind,
        params: draft.params,
        schedule: draft.schedule,
        phase: draft.phase,
        feeds: draft.feeds,
        pathways,
        pinned,
      },
      {
        onSuccess: () => {
          toast('Template saved', 'success')
          setDraft(blankDraft(kinds))
          setPathways([])
          setPinned(false)
          onDone()
        },
        onError: (e) => toast(`Could not save — ${e.message}`, 'warning'),
      },
    )
  }

  const toggle = (t: TaskTemplate, patch: { pinned?: boolean; archived?: boolean }) =>
    update.mutate(
      { id: t.id, ...patch },
      { onError: () => toast('Could not update the template — try again', 'warning') },
    )

  if (library.isLoading) return <SkeletonCard lines={5} />
  if (library.isError) return <EmptyState title="The task library couldn't be loaded." />

  return (
    <div className="space-y-3.5">
      {creating && (
        <SectionCard title="New task template">
          <div className="space-y-3">
            <DraftRowEditor value={draft} kinds={kinds} onChange={setDraft} libraryToggles={false} />
            <div>
              <p className="micro mb-1.5">Pathways <span className="normal-case tracking-normal">(none = every pathway)</span></p>
              <div className="flex flex-wrap gap-1.5">
                {PATHWAY_KEYS.map((key) => {
                  const on = pathways.includes(key)
                  return (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={on}
                      onClick={() =>
                        setPathways((p) => (on ? p.filter((k) => k !== key) : [...p, key]))
                      }
                      className={`chip cursor-pointer border transition-colors duration-150 ${
                        on
                          ? 'border-brand/35 bg-brand-tint text-brand'
                          : 'border-line bg-panel text-body hover:bg-soft'
                      }`}
                    >
                      {pathwayName(key)}
                    </button>
                  )
                })}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 text-[12.5px] font-medium text-body">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[rgb(var(--brand))]"
                  checked={pinned}
                  onChange={(e) => setPinned(e.target.checked)}
                />
                Pin as quick pick
              </label>
              <button type="button" className="qa-btn ml-auto" onClick={onDone}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary w-auto"
                disabled={!draft.title.trim() || create.isPending}
                onClick={save}
              >
                {create.isPending ? 'Saving…' : 'Save template'}
              </button>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard
        title="Task templates"
        aside={
          <span className="font-mono text-[11.5px] font-medium tabular-nums text-faint">{rows.length}</span>
        }
      >
        {rows.length === 0 ? (
          <p className="text-[12.5px] font-medium text-muted">No task templates yet.</p>
        ) : (
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[720px] text-left text-[12.5px]">
              <thead>
                <tr className="micro border-b border-line">
                  <Th>Title</Th>
                  <Th>Verified by</Th>
                  <Th>Phase</Th>
                  <Th>Pathways</Th>
                  <Th className="text-right">Used</Th>
                  <Th className="text-center">Pinned</Th>
                  <Th className="text-right">Archive</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((t) => (
                  <tr key={t.id} className={t.archived ? 'opacity-50' : ''}>
                    <td className="max-w-[320px] py-2.5 pr-3 align-top">
                      <span className="block font-semibold text-ink">{t.title}</span>
                      <span className="mt-0.5 block text-[11.5px] font-medium leading-snug text-muted">{t.why}</span>
                      <span className="mt-0.5 block text-[10.5px] font-medium text-faint">
                        {ucLabel(t.use_case)}
                        {t.clinical_target && <> · {t.clinical_target}</>}
                        {t.source !== 'library' && <> · {titleCase(t.source)}</>}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className="block font-medium text-body">{kindLabel(kinds, t.verify_kind)}</span>
                      <span className="block text-[10.5px] font-medium text-faint">
                        {t.verified_by ?? kindInfo(kinds, t.verify_kind)?.verified_by ?? 'self-report'}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 align-top font-medium text-body">{phaseLabel(t.phase)}</td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className="flex flex-wrap gap-1">
                        {t.pathways.length === 0 ? (
                          <span className="chip bg-soft text-muted">All</span>
                        ) : (
                          t.pathways.map((p) => (
                            <span key={p} className="chip bg-soft text-muted">{pathwayName(p)}</span>
                          ))
                        )}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-right align-top font-mono tabular-nums text-muted">{t.usage_count}</td>
                    <td className="py-2.5 text-center align-top">
                      <PinButton pinned={t.pinned} onClick={() => toggle(t, { pinned: !t.pinned })} />
                    </td>
                    <td className="py-2.5 text-right align-top">
                      <ArchiveButton archived={t.archived} onClick={() => toggle(t, { archived: !t.archived })} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

// --- messages ------------------------------------------------------------------

function MessageLibrary({
  showArchived,
  creating,
  onDone,
}: {
  showArchived: boolean
  creating: boolean
  onDone: () => void
}) {
  const toast = useToast()
  const library = useMessageTemplates(showArchived)
  const update = useUpdateMessageTemplate()
  const create = useCreateMessageTemplate()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [tone, setTone] = useState<MessageTone>('warm')
  const [pinned, setPinned] = useState(false)
  const warn = numberWarning(body)

  const rows = (library.data?.templates ?? [])
    .filter((t) => showArchived || !t.archived)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.usage_count - a.usage_count || a.title.localeCompare(b.title))

  const save = () => {
    if (!title.trim() || !body.trim()) return
    create.mutate(
      { title: title.trim(), body: body.trim(), tone, pinned },
      {
        onSuccess: () => {
          toast('Template saved', 'success')
          setTitle('')
          setBody('')
          setTone('warm')
          setPinned(false)
          onDone()
        },
        onError: (e) => toast(`Could not save — ${e.message}`, 'warning'),
      },
    )
  }

  const toggle = (t: MessageTemplate, patch: { pinned?: boolean; archived?: boolean }) =>
    update.mutate(
      { id: t.id, ...patch },
      { onError: () => toast('Could not update the template — try again', 'warning') },
    )

  if (library.isLoading) return <SkeletonCard lines={5} />
  if (library.isError) return <EmptyState title="The message library couldn't be loaded." />

  return (
    <div className="space-y-3.5">
      {creating && (
        <SectionCard title="New message template">
          <div className="space-y-3">
            <div>
              <label htmlFor="mt-title" className="micro mb-1 block">Title</label>
              <input id="mt-title" className="field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Check on swelling" />
            </div>
            <div>
              <label htmlFor="mt-body" className="micro mb-1 block">
                Body <span className="normal-case tracking-normal">— use {'{first}'} and {'{surgeon}'}</span>
              </label>
              <textarea
                id="mt-body"
                rows={4}
                className="field"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Hi {first} — {surgeon}'s team here. How is the swelling today? Reply here or in the app."
              />
              {warn && <p className="mt-1 text-[11px] font-medium leading-snug text-risk-med">{warn}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <SegmentedControl<MessageTone> options={TONES} value={tone} onChange={setTone} aria-label="Tone" />
              <label className="inline-flex cursor-pointer items-center gap-2 text-[12.5px] font-medium text-body">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[rgb(var(--brand))]"
                  checked={pinned}
                  onChange={(e) => setPinned(e.target.checked)}
                />
                Pin in the composer
              </label>
              <button type="button" className="qa-btn ml-auto" onClick={onDone}>Cancel</button>
              <button
                type="button"
                className="btn-primary w-auto"
                disabled={!title.trim() || !body.trim() || create.isPending}
                onClick={save}
              >
                {create.isPending ? 'Saving…' : 'Save template'}
              </button>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard
        title="Message templates"
        aside={
          <span className="font-mono text-[11.5px] font-medium tabular-nums text-faint">{rows.length}</span>
        }
      >
        {rows.length === 0 ? (
          <p className="text-[12.5px] font-medium text-muted">No message templates yet.</p>
        ) : (
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[640px] text-left text-[12.5px]">
              <thead>
                <tr className="micro border-b border-line">
                  <Th>Title</Th>
                  <Th>Tone</Th>
                  <Th>Tags</Th>
                  <Th className="text-right">Used</Th>
                  <Th className="text-center">Pinned</Th>
                  <Th className="text-right">Archive</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((t) => (
                  <tr key={t.id} className={t.archived ? 'opacity-50' : ''}>
                    <td className="max-w-[420px] py-2.5 pr-3 align-top">
                      <span className="block font-semibold text-ink">{t.title}</span>
                      <span className="mt-0.5 block text-[11.5px] font-medium leading-snug text-muted">{t.body}</span>
                    </td>
                    <td className="py-2.5 pr-3 align-top font-medium text-body">{titleCase(t.tone)}</td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className="flex flex-wrap gap-1">
                        {(t.tags ?? []).map((tag) => (
                          <span key={tag} className="chip bg-soft text-muted">{tag}</span>
                        ))}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-right align-top font-mono tabular-nums text-muted">{t.usage_count}</td>
                    <td className="py-2.5 text-center align-top">
                      <PinButton pinned={t.pinned} onClick={() => toggle(t, { pinned: !t.pinned })} />
                    </td>
                    <td className="py-2.5 text-right align-top">
                      <ArchiveButton archived={t.archived} onClick={() => toggle(t, { archived: !t.archived })} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

// --- bits ----------------------------------------------------------------------

function Th({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <th className={`py-2 pr-3 font-medium ${className}`}>{children}</th>
}

function PinButton({ pinned, onClick }: { pinned: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pinned}
      aria-label={pinned ? 'Unpin' : 'Pin'}
      title={pinned ? 'Unpin' : 'Pin as a quick pick'}
      className={`grid h-7 w-7 cursor-pointer place-items-center rounded-btn transition-colors duration-150 hover:bg-soft ${
        pinned ? 'text-brand' : 'text-faint hover:text-ink'
      }`}
    >
      <Star size={14} fill={pinned ? 'currentColor' : 'none'} />
    </button>
  )
}

function ArchiveButton({ archived, onClick }: { archived: boolean; onClick: () => void }) {
  const Icon = archived ? ArchiveRestore : Archive
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={archived ? 'Restore' : 'Archive'}
      title={archived ? 'Restore to the library' : 'Archive'}
      className="grid h-7 w-7 cursor-pointer place-items-center rounded-btn text-faint transition-colors duration-150 hover:bg-soft hover:text-ink"
    >
      <Icon size={14} />
    </button>
  )
}
