import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, Check, CircleAlert, CircleCheck, HeartPulse } from 'lucide-react'
import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, fetchJson } from '../../api/client'
import Tile from '../../components/Tile'

/**
 * /checkin/<token> — a post-operative patient, on their own device, often an
 * older phone and sometimes with reduced vision. It is styled like the iOS
 * patient app (large friendly title, white 20px cards on the grey canvas,
 * capsule answers), but the console's defaults are deliberately NOT
 * inherited:
 *   - no glass, no blur, no ambient wash, no translucency of any kind.
 *   - 16px (text-copy-lg) is the body floor, and every sentence is --ink
 *     (17.124 canvas / 18.377 panel light; 18.377 / 17.194 dark). --body
 *     (6.729 on light canvas, 7.222 on panel) carries short labels only.
 *   - every answer target is 56px tall and at least 44px wide, with 8px
 *     between scale cells and 12px elsewhere; the send button is 56px.
 *   - no uppercase and no 12px text anywhere.
 *
 * The pieces below are shared with /t/<token> (TaskPage imports them), so a
 * patient who answers a text one day and a check-in link the next sees the
 * same controls.
 */

interface Question {
  id: string
  prompt: string
  kind: 'scale' | 'yes_no' | 'choice' | 'text' | 'number'
  options?: string[]
  min?: number
  max?: number
}

interface CheckinForm {
  patient_name: string
  questions: Question[]
}

type AnswerValue = string | number | null
type Answers = Record<string, AnswerValue>

const CHOICE_LABELS: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
  well: 'Well',
  rough: 'Rough night',
  all: 'All of them',
  some: 'Some',
  none: 'Not today',
}

// --- shared patient-web pieces ---------------------------------------------------

/** The page frame: canvas only (no wash, no bar), a 16px gutter, and a quiet
 *  lockup — a blue tile plus the name in --ink 600. The name is not
 *  brand-ink: that is 5.354 on light canvas, under this route's 7:1 bar. */
export function PatientShell({
  children,
  width = 'lg',
}: {
  children: ReactNode
  width?: 'md' | 'lg'
}) {
  return (
    <main
      className={`mx-auto min-h-screen px-4 pb-16 pt-8 sm:pt-12 ${width === 'md' ? 'max-w-md' : 'max-w-lg'}`}
    >
      <p className="mb-8 flex items-center gap-2.5 text-copy-lg font-semibold text-ink">
        <Tile family="blue" icon={<HeartPulse />} />
        MedPull Recovery
      </p>
      {children}
    </main>
  )
}

/** Large title at 600, like the app's two-line greeting. */
export function PatientTitle({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <h1 className={`text-balance text-section font-semibold text-ink ${className}`}>{children}</h1>
  )
}

/** A full-page state (loading, error, done): a large tile, a title and one
 *  line of --ink copy. The tile is decorative; the words carry the state. */
export function PatientStatus({
  tone,
  title,
  children,
}: {
  tone: 'loading' | 'error' | 'done'
  title: string
  children?: ReactNode
}) {
  const tile =
    tone === 'done' ? (
      <Tile size="lg" family="teal" icon={<CircleCheck />} />
    ) : tone === 'error' ? (
      <Tile size="lg" family="risk-high" icon={<CircleAlert />} />
    ) : (
      <Tile size="lg" family="blue" icon={<Activity />} className="motion-safe:animate-pulse" />
    )
  return (
    <section
      className="panel p-6"
      role={tone === 'loading' ? 'status' : undefined}
      aria-live={tone === 'loading' ? 'polite' : undefined}
    >
      {tile}
      <h1 className="mt-4 text-balance text-title font-semibold text-ink">{title}</h1>
      {children && <p className="mt-2 text-copy-lg text-ink">{children}</p>}
    </section>
  )
}

/**
 * One answer target. Idle: --panel with a --line-strong edge (3.834 light /
 * 5.671 dark on the card; WCAG 1.4.11 binds it because the edge is the only
 * boundary). Hover: brand tint with a brand edge, ink label (15.871 / 14.255).
 * Selected: the brand FILL with white (4.602), a same-colour edge so nothing
 * moves by a pixel, aria-pressed, and — on word answers — a check mark, so
 * the state is never colour alone. Focus: a 2px --focus ring 2px out
 * (4.602 / 6.783 on panel).
 */
function AnswerButton({
  active,
  onClick,
  shape,
  children,
}: {
  active: boolean
  onClick: () => void
  shape: 'cell' | 'capsule'
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex min-h-14 min-w-11 select-none items-center justify-center gap-2 border text-copy-lg font-medium transition-[background-color,border-color,color,transform] duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-press forced-colors:border-[ButtonText] ${
        shape === 'cell' ? 'w-full rounded-control tabular-nums' : 'rounded-pill px-6'
      } ${
        active
          ? 'border-brand bg-brand text-on-brand forced-colors:bg-[Highlight] forced-colors:text-[HighlightText]'
          : 'border-line-strong bg-panel text-ink hover:border-brand hover:bg-brand-tint'
      }`}
    >
      {shape === 'capsule' && active && <Check size={18} strokeWidth={2.5} aria-hidden />}
      {children}
    </button>
  )
}

/**
 * One question as an app-style card. The prompt names the answer group
 * (role="group" + aria-labelledby). A 0-10 scale is a fixed grid so the rows
 * line up: 6 columns (0-5 / 6-10) from 368px, where a cell is still
 * (368 - 32 gutter - 32 card padding - 40 gaps) / 6 = 44px, and 4 columns
 * (0-3 / 4-7 / 8-10) below that, 58px at 320px. A 5-column fallback would
 * orphan "10" on its own row.
 */
export function QuestionCard({
  q,
  value,
  onChange,
}: {
  q: Question
  value: AnswerValue | undefined
  onChange: (value: AnswerValue, mode: 'toggle' | 'set') => void
}) {
  const uid = useId()
  const promptId = `${uid}-prompt`
  const fieldId = `${uid}-field`
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby={promptId}>
      {q.kind === 'text' || q.kind === 'number' ? (
        <label id={promptId} htmlFor={fieldId} className="mb-4 block text-lede font-semibold text-ink">
          {q.prompt}
        </label>
      ) : (
        <h2 id={promptId} className="mb-4 text-lede font-semibold text-ink">
          {q.prompt}
        </h2>
      )}

      {q.kind === 'scale' && (
        <div role="group" aria-labelledby={promptId} className="grid grid-cols-4 gap-2 min-[368px]:grid-cols-6">
          {Array.from({ length: 11 }, (_, n) => (
            <AnswerButton key={n} shape="cell" active={value === n} onClick={() => onChange(n, 'toggle')}>
              {n}
            </AnswerButton>
          ))}
        </div>
      )}

      {(q.kind === 'yes_no' || q.kind === 'choice') && (
        <div role="group" aria-labelledby={promptId} className="flex flex-wrap gap-3">
          {(q.options ?? ['yes', 'no']).map((opt) => (
            <AnswerButton
              key={opt}
              shape="capsule"
              active={value === opt}
              onClick={() => onChange(opt, 'toggle')}
            >
              {CHOICE_LABELS[opt] ?? opt}
            </AnswerButton>
          ))}
        </div>
      )}

      {q.kind === 'number' && (
        <input
          id={fieldId}
          type="number"
          inputMode="numeric"
          min={q.min ?? 0}
          max={q.max ?? 10000}
          value={typeof value === 'number' ? value : ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value), 'set')}
          className="field min-h-14 px-4 text-copy-lg tabular-nums"
          placeholder={q.id === 'minutes' ? 'Minutes' : ''}
        />
      )}

      {q.kind === 'text' && (
        /* `.field`: --line-strong edge at rest, a 2px --focus outline on focus
           that no box-shadow reset can erase, --muted placeholder. */
        <textarea
          id={fieldId}
          rows={3}
          maxLength={2000}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value, 'set')}
          placeholder="Optional"
          className="field px-4 py-3 text-copy-lg"
        />
      )}
    </section>
  )
}

/** Error line above the send button: risk ink on its tint (4.835 / 5.701),
 *  with a glyph and the words, announced assertively. */
export function PatientError({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="mt-6 flex items-start gap-2.5 rounded-control bg-risk-high-tint px-4 py-3 text-copy-lg font-medium text-risk-high-ink"
    >
      <CircleAlert size={20} aria-hidden className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

/** The one filled action: a 56px full-width capsule. Disabled keeps a
 *  --line-strong edge because --disabled-fill alone is 1.057 on canvas; its
 *  label pair is 4.755 / 4.582. */
export function SendButton({
  disabled,
  pending,
  onClick,
  children,
}: {
  disabled: boolean
  pending: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      onClick={onClick}
      className="btn-filled btn-lg mt-8 min-h-14 w-full text-lede disabled:cursor-not-allowed disabled:border-line-strong disabled:bg-disabled-fill disabled:text-disabled-ink"
    >
      {pending ? 'Sending…' : children}
    </button>
  )
}

/** Tap an answer again to clear it; typed answers just replace. */
function applyAnswer(a: Answers, id: string, value: AnswerValue, mode: 'toggle' | 'set'): Answers {
  return { ...a, [id]: mode === 'toggle' && a[id] === value ? null : value }
}

// --- page ------------------------------------------------------------------------

export default function CheckinPage() {
  const { token } = useParams<{ token: string }>()
  const [answers, setAnswers] = useState<Answers>({})

  const { data, isLoading, error } = useQuery<CheckinForm>({
    queryKey: ['checkin', token],
    queryFn: () => fetchJson(`/api/checkin/${token}`),
    retry: false,
  })

  const submit = useMutation({
    mutationFn: () =>
      fetchJson(`/api/checkin/${token}`, { method: 'POST', body: JSON.stringify(answers) }),
  })

  if (isLoading)
    return (
      <PatientShell>
        <PatientStatus tone="loading" title="Loading your check-in…" />
      </PatientShell>
    )

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This check-in couldn't be loaded. Please try again."
    return (
      <PatientShell>
        <PatientStatus tone="error" title={detail}>
          If you need a new link, ask your care team to send another check-in.
        </PatientStatus>
      </PatientShell>
    )
  }

  if (submit.isSuccess)
    return (
      <PatientShell>
        <PatientStatus tone="done" title={`Thanks, ${data.patient_name}. All sent.`}>
          Your care team will see this with your next review. You can close this page.
        </PatientStatus>
      </PatientShell>
    )

  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return (
    <PatientShell>
      <PatientTitle>
        Hi {data.patient_name},<br />
        how's your recovery today?
      </PatientTitle>
      <p className="mt-3 text-copy-lg text-ink">
        Takes under a minute. Skip anything you're not sure about.
      </p>

      <div className="mt-8 flex flex-col gap-stack">
        {data.questions.map((q) => (
          <QuestionCard
            key={q.id}
            q={q}
            value={answers[q.id]}
            onChange={(v, mode) => setAnswers((a) => applyAnswer(a, q.id, v, mode))}
          />
        ))}
      </div>

      {submit.isError && (
        <PatientError>
          {/* A 410 means the link was already used or has expired, and a 422
              names the answer the form would not take. Telling that patient
              to check their connection sends them round the same loop. */}
          {submit.error instanceof ApiError && submit.error.status >= 400 && submit.error.status < 500
            ? submit.error.message
            : "Couldn't send your answers. Check your connection and try again."}
        </PatientError>
      )}

      <SendButton disabled={!answered} pending={submit.isPending} onClick={() => submit.mutate()}>
        Send to my care team
      </SendButton>
    </PatientShell>
  )
}
