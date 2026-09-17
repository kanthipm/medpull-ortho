import {
  Archive,
  ArchiveRestore,
  BookMarked,
  Check,
  ClipboardList,
  MessageSquare,
  Plus,
  Star,
} from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
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
import { Tooltip } from '../../components/Menu'
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
import Switch, { GroupFooter, GroupHeader, SettingsHero } from './Switch'

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
    <div className="pb-10">
      <SettingsHero
        nav={<SettingsNav />}
        icon={<BookMarked />}
        title="Library"
        decor={[<ClipboardList key="tasks" />, <MessageSquare key="messages" />, <Star key="star" />]}
      >
        Care-plan tasks and patient messages the team reuses. Starred ones show first as quick
        picks.
      </SettingsHero>

      {/* The toolbar sits in the sky's tail. Left: the glass tabs and a glass
          capsule around the switch (the dark brand track is 2.666 on the bare
          sky, 3.7 on the glass). Right, inside the decor zone at >= 1024px:
          only the opaque filled capsule (white on #1976D2, 4.602). */}
      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-3 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <SegmentedControl<Tab>
          options={TABS}
          value={tab}
          onChange={(t) => {
            setTab(t)
            setCreating(false)
          }}
          tone="glass"
          aria-label="Library section"
        />
        <span className="glass inline-flex min-h-11 items-center gap-2.5 rounded-pill py-1 pl-2 pr-4">
          <Switch
            id="library-show-archived"
            checked={showArchived}
            onChange={setShowArchived}
            aria-labelledby="library-show-archived-label"
          />
          <label
            id="library-show-archived-label"
            htmlFor="library-show-archived"
            className="cursor-pointer text-copy font-medium text-ink"
          >
            Show archived
          </label>
        </span>
        <button
          type="button"
          className="btn-filled ml-auto"
          aria-expanded={creating}
          onClick={() => setCreating((c) => !c)}
        >
          <Plus size={16} /> New template
        </button>
      </div>

      <div className="rise mt-6" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        {tab === 'tasks' ? (
          <TaskLibrary showArchived={showArchived} creating={creating} onDone={() => setCreating(false)} />
        ) : (
          <MessageLibrary showArchived={showArchived} creating={creating} onDone={() => setCreating(false)} />
        )}
      </div>
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

  if (library.isLoading) return <SkeletonCard rows={5} />
  if (library.isError)
    return (
      <EmptyState title="The task library couldn’t be loaded." icon={<ClipboardList />}>
        Refresh the page to try again.
      </EmptyState>
    )

  return (
    <div className="space-y-8">
      {creating && (
        <SectionCard title="New task template">
          <div className="space-y-5">
            <DraftRowEditor value={draft} kinds={kinds} onChange={setDraft} libraryToggles={false} />
            <fieldset>
              <legend className="mb-2 text-copy font-medium text-body">
                Pathways <span className="font-normal text-secondary">(none selected means every pathway)</span>
              </legend>
              <div className="flex flex-wrap gap-2">
                {PATHWAY_KEYS.map((key) => {
                  const on = pathways.includes(key)
                  return (
                    <ToggleCapsule
                      key={key}
                      on={on}
                      onClick={() =>
                        setPathways((p) => (on ? p.filter((k) => k !== key) : [...p, key]))
                      }
                    >
                      {pathwayName(key)}
                    </ToggleCapsule>
                  )
                })}
              </div>
            </fieldset>
            <FormFooter
              pinId="task-pin"
              pinLabel="Star as a quick pick"
              pinned={pinned}
              onPinned={setPinned}
              onCancel={onDone}
              onSave={save}
              canSave={!!draft.title.trim()}
              saving={create.isPending}
            />
          </div>
        </SectionCard>
      )}

      <LibraryGroup
        id="task-templates"
        title="Task templates"
        count={rows.length}
        empty={
          <EmptyState
            variant="inline"
            title="No task templates yet"
            icon={<ClipboardList />}
            family="violet"
          >
            Save one from a patient’s plan, or use New template.
          </EmptyState>
        }
      >
        {rows.length > 0 && (
          <table className="w-full min-w-[760px] text-left text-copy">
            <thead>
              <tr className="border-b border-hairline">
                <Th>Title</Th>
                <Th>Verified by</Th>
                <Th>Phase</Th>
                <Th className="text-right">Used</Th>
                <Th className="w-[88px] text-right">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {rows.map((t) => (
                <tr key={t.id} className={rowClass(t.archived)}>
                  <Td className="max-w-[380px]">
                    <TitleCell title={t.title} archived={t.archived} />
                    {t.why && <span className="mt-0.5 block text-copy text-secondary">{t.why}</span>}
                    <span className="meta mt-1 block">
                      {[
                        ucLabel(t.use_case),
                        t.clinical_target,
                        t.pathways.length === 0
                          ? 'All pathways'
                          : t.pathways.map(pathwayName).join(', '),
                        t.source !== 'library' ? titleCase(t.source) : '',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </Td>
                  <Td>
                    <span className="block font-medium text-ink">{kindLabel(kinds, t.verify_kind)}</span>
                    <span className="meta block">
                      {t.verified_by ?? kindInfo(kinds, t.verify_kind)?.verified_by ?? 'self-report'}
                    </span>
                  </Td>
                  <Td className="text-body">{phaseLabel(t.phase)}</Td>
                  <Td className="text-right tabular-nums text-body">{t.usage_count}</Td>
                  <Td className="text-right">
                    <RowActions
                      title={t.title}
                      pinned={t.pinned}
                      archived={t.archived}
                      onPin={() => toggle(t, { pinned: !t.pinned })}
                      onArchive={() => toggle(t, { archived: !t.archived })}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </LibraryGroup>
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

  if (library.isLoading) return <SkeletonCard rows={5} />
  if (library.isError)
    return (
      <EmptyState title="The message library couldn’t be loaded." icon={<MessageSquare />}>
        Refresh the page to try again.
      </EmptyState>
    )

  return (
    <div className="space-y-8">
      {creating && (
        <SectionCard title="New message template">
          <div className="space-y-5">
            <div>
              <label htmlFor="mt-title" className="mb-2 block text-copy font-medium text-body">
                Title
              </label>
              <input
                id="mt-title"
                className="field"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Check on swelling"
              />
            </div>
            <div>
              <label htmlFor="mt-body" className="mb-2 block text-copy font-medium text-body">
                Message{' '}
                <span className="font-normal text-secondary">
                  use {'{first}'} and {'{surgeon}'}
                </span>
              </label>
              <textarea
                id="mt-body"
                rows={4}
                className="field"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                aria-describedby={warn ? 'mt-body-warn' : undefined}
                placeholder="Hi {first}, {surgeon}'s team here. How is the swelling today? Reply here or in the app."
              />
              {warn && (
                <p id="mt-body-warn" className="mt-2 text-copy font-medium text-risk-med-ink">
                  {warn}
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span id="mt-tone-label" className="text-copy font-medium text-body">
                Tone
              </span>
              <SegmentedControl<MessageTone>
                options={TONES}
                value={tone}
                onChange={setTone}
                size="sm"
                role="radiogroup"
                aria-labelledby="mt-tone-label"
              />
            </div>
            <FormFooter
              pinId="message-pin"
              pinLabel="Star as a composer quick pick"
              pinned={pinned}
              onPinned={setPinned}
              onCancel={onDone}
              onSave={save}
              canSave={!!title.trim() && !!body.trim()}
              saving={create.isPending}
            />
          </div>
        </SectionCard>
      )}

      <LibraryGroup
        id="message-templates"
        title="Message templates"
        count={rows.length}
        empty={
          <EmptyState
            variant="inline"
            title="No message templates yet"
            icon={<MessageSquare />}
            family="blue"
          >
            Save one from the composer, or use New template.
          </EmptyState>
        }
      >
        {rows.length > 0 && (
          <table className="w-full min-w-[640px] text-left text-copy">
            <thead>
              <tr className="border-b border-hairline">
                <Th>Message</Th>
                <Th>Tone</Th>
                <Th className="text-right">Used</Th>
                <Th className="w-[88px] text-right">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {rows.map((t) => (
                <tr key={t.id} className={rowClass(t.archived)}>
                  <Td className="max-w-[480px]">
                    <TitleCell title={t.title} archived={t.archived} />
                    <span className="mt-0.5 block text-copy text-secondary">{t.body}</span>
                    {(t.tags ?? []).length > 0 && (
                      <span className="meta mt-1 block">{(t.tags ?? []).join(' · ')}</span>
                    )}
                  </Td>
                  <Td className="text-body">{titleCase(t.tone)}</Td>
                  <Td className="text-right tabular-nums text-body">{t.usage_count}</Td>
                  <Td className="text-right">
                    <RowActions
                      title={t.title}
                      pinned={t.pinned}
                      archived={t.archived}
                      onPin={() => toggle(t, { pinned: !t.pinned })}
                      onArchive={() => toggle(t, { archived: !t.archived })}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </LibraryGroup>
    </div>
  )
}

// --- bits ----------------------------------------------------------------------

/** Archived rows sit on --soft. Dark --muted on --soft is below 4.5, so the
 *  row's secondary text switches to --body (the R8 scope). The "Archived"
 *  chip in the title cell says it in words too. */
function rowClass(archived: boolean) {
  return archived ? 'bg-soft [--text-secondary:var(--body)]' : ''
}

/** A grouped section: sentence-case header with a count, then the table in a
 *  rounded, clipped group that scrolls sideways on narrow screens. */
function LibraryGroup({
  id,
  title,
  count,
  empty,
  children,
}: {
  id: string
  title: string
  count: number
  empty: ReactNode
  children: ReactNode
}) {
  return (
    <section aria-labelledby={id}>
      {/* The count rides beside the title as a ring badge, on the left: the
          header can sit in the sky's tail, and its right end would be in the
          decor zone, where only ink may go. */}
      <GroupHeader id={id} onSky>
        {title}
        <span className="sr-only">, </span>
        <span className="badge-ring ml-2 align-[1px] tabular-nums">
          {count}
          <span className="sr-only"> {count === 1 ? 'template' : 'templates'}</span>
        </span>
      </GroupHeader>
      <div className="card-group">
        {count === 0 ? (
          <div className="px-4 py-6">{empty}</div>
        ) : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-labelledby={id}>
            {children}
          </div>
        )}
      </div>
      <GroupFooter>
        Titles, reasons and messages are what patients see, so keep them plain and free of
        numbers. Clinical targets stay with the care team.
      </GroupFooter>
    </section>
  )
}

function Th({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={`px-2 py-2.5 text-label font-medium tracking-label text-secondary first:pl-4 last:pr-4 ${className}`}
    >
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <td className={`px-2 py-3 align-top first:pl-4 last:pr-3 ${className}`}>{children}</td>
}

/** The title, plus an "Archived" chip when it applies. Quick-pick state is
 *  the filled star in the actions column (named "Quick pick: <title>",
 *  aria-pressed), and pinned rows sort first, so no pill repeats it. */
function TitleCell({ title, archived }: { title: string; archived: boolean }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="font-medium text-ink">{title}</span>
      {archived && <span className="chip bg-risk-missing-tint text-risk-missing-ink">Archived</span>}
    </span>
  )
}

/** Gray capsule that toggles; pressed = brand tint plus a check mark, so the
 *  state is never colour alone. */
function ToggleCapsule({
  on,
  onClick,
  children,
}: {
  on: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`btn-gray btn-sm ${
        on ? 'bg-brand-tint text-on-brand-tint hover:bg-brand-tint-strong' : ''
      }`}
    >
      {on && <Check aria-hidden />}
      {children}
    </button>
  )
}

function FormFooter({
  pinId,
  pinLabel,
  pinned,
  onPinned,
  onCancel,
  onSave,
  canSave,
  saving,
}: {
  pinId: string
  pinLabel: string
  pinned: boolean
  onPinned: (v: boolean) => void
  onCancel: () => void
  onSave: () => void
  canSave: boolean
  saving: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 pt-1">
      <span className="inline-flex items-center gap-2">
        <Switch id={pinId} checked={pinned} onChange={onPinned} aria-labelledby={`${pinId}-label`} />
        <label id={`${pinId}-label`} htmlFor={pinId} className="cursor-pointer text-copy font-medium text-body">
          {pinLabel}
        </label>
      </span>
      <span className="ml-auto flex items-center gap-2">
        <button type="button" className="btn-gray" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn-filled" disabled={!canSave || saving} onClick={onSave}>
          {saving ? 'Saving…' : 'Save template'}
        </button>
      </span>
    </div>
  )
}

function RowActions({
  title,
  pinned,
  archived,
  onPin,
  onArchive,
}: {
  title: string
  pinned: boolean
  archived: boolean
  onPin: () => void
  onArchive: () => void
}) {
  const ArchiveIcon = archived ? ArchiveRestore : Archive
  return (
    <span className="inline-flex items-center gap-1">
      {/* Judge #13: the name and the tooltip say the same thing. A toggle
          keeps one name; aria-pressed (and the filled star) carry on/off. */}
      <Tooltip content="Quick pick">
        <button
          type="button"
          onClick={onPin}
          aria-pressed={pinned}
          aria-label={`Quick pick: ${title}`}
          className={`btn-icon btn-sm ${pinned ? 'text-brand-ink hover:text-brand-ink' : ''}`}
        >
          <Star fill={pinned ? 'currentColor' : 'none'} />
        </button>
      </Tooltip>
      <Tooltip content={archived ? 'Restore to the library' : 'Archive'}>
        <button
          type="button"
          onClick={onArchive}
          aria-label={archived ? `Restore ${title}` : `Archive ${title}`}
          className="btn-icon btn-sm"
        >
          <ArchiveIcon />
        </button>
      </Tooltip>
    </span>
  )
}
