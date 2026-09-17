import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Bandage,
  ClipboardList,
  Dumbbell,
  Footprints,
  MessageCircle,
  Pill,
  Smartphone,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, fetchJson } from '../../api/client'
import type { PublicTask, TaskKind } from '../../api/types'
import Tile, { type TileFamily } from '../../components/Tile'
import {
  PatientError,
  PatientShell,
  PatientStatus,
  PatientTitle,
  QuestionCard,
  SendButton,
} from '../checkin/CheckinPage'

/**
 * The page a task text links to (/t/<token>). Two ways in: the app, via its
 * URL scheme (tried once automatically, and offered as a button), or right
 * here, with the same question cards the check-in page uses. The token in
 * the link is the credential, like /checkin/<token>.
 *
 * Patient-facing, on an unknown and often older device, so it follows the
 * /checkin house rules (see CheckinPage): no glass, no ambient wash, a 16px
 * --ink body floor, 56px targets, no uppercase, no 12px text.
 */

type Answers = Record<string, string | number | null>

/** The same tile families the app's Tasks list uses (communication = blue,
 *  activity = teal, meds and wound = violet). Decorative: the kind label
 *  beside it says the same thing in words. */
const KIND_TILE: Record<TaskKind, { family: TileFamily; icon: ReactNode }> = {
  checkin: { family: 'blue', icon: <MessageCircle /> },
  exercise: { family: 'teal', icon: <Dumbbell /> },
  walk: { family: 'teal', icon: <Footprints /> },
  medication: { family: 'violet', icon: <Pill /> },
  wound_check: { family: 'violet', icon: <Bandage /> },
  custom: { family: 'blue', icon: <ClipboardList /> },
}

export default function TaskPage() {
  const { token } = useParams<{ token: string }>()
  const [answers, setAnswers] = useState<Answers>({})
  const triedApp = useRef(false)

  const { data, isLoading, error } = useQuery<PublicTask>({
    queryKey: ['public-task', token],
    queryFn: () => fetchJson(`/api/tasks/${token}`),
    retry: false,
  })

  const submit = useMutation({
    mutationFn: () =>
      fetchJson(`/api/tasks/${token}`, {
        method: 'POST',
        body: JSON.stringify({ answers, via: 'web' }),
      }),
  })

  // One quiet attempt to hand off to the app; the page stays usable if it
  // is not installed (the scheme simply does nothing).
  useEffect(() => {
    if (!data || data.completed || triedApp.current) return
    triedApp.current = true
    const ua = navigator.userAgent
    if (/iPhone|iPad|iPod/.test(ua)) {
      const iframe = document.createElement('iframe')
      iframe.style.display = 'none'
      iframe.src = data.deep_link
      document.body.appendChild(iframe)
      window.setTimeout(() => iframe.remove(), 1500)
    }
  }, [data])

  if (isLoading)
    return (
      <PatientShell width="md">
        <PatientStatus tone="loading" title="Loading your task…" />
      </PatientShell>
    )

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This task couldn't be loaded. Please try again."
    return (
      <PatientShell width="md">
        <PatientStatus tone="error" title={detail}>
          If you need a new link, reply to the text or ask your care team.
        </PatientStatus>
      </PatientShell>
    )
  }

  if (submit.isSuccess || data.completed)
    return (
      <PatientShell width="md">
        <PatientStatus
          tone="done"
          title={submit.isSuccess ? `Thanks, ${data.first_name}. All sent.` : 'This one is already done.'}
        >
          Your care team will see it with their next review. You can close this page.
        </PatientStatus>
      </PatientShell>
    )

  const { task } = data
  const isCheckin = task.kind === 'checkin'
  const answered = Object.values(answers).some((v) => v !== null && v !== '')
  const tile = KIND_TILE[task.kind] ?? KIND_TILE.custom

  return (
    <PatientShell
      width="md"
      hero={
        <>
          {/* Kind label: --ink, like everything in the gradient head (9.536
              dark / 12.277 light at its most saturated point; --body would
              be 3.688 in dark there). */}
          <p className="flex items-center gap-2.5 text-copy-lg font-medium text-ink">
            <Tile family={tile.family} icon={tile.icon} />
            {task.kind_label}
          </p>
          <PatientTitle className="mt-3">{task.title}</PatientTitle>
          {task.why && <p className="mt-3 text-copy-lg text-ink">{task.why}</p>}
        </>
      }
    >

      {/* The app hand-off: a 56px tinted capsule. Label --on-brand-tint on the
          tint (7.454 light / 5.624 dark); the brand edge is what makes it a
          button on the canvas (4.288 / 3.993), since the tint fill alone is
          1.079 there. */}
      <a
        href={data.deep_link}
        className="flex min-h-14 w-full select-none items-center justify-center gap-2.5 rounded-pill border border-brand bg-brand-tint px-6 text-copy-lg font-medium text-on-brand-tint transition-[background-color,transform] duration-state ease-apple hover:bg-brand-tint-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-press forced-colors:border-[LinkText]"
      >
        <Smartphone size={20} aria-hidden />
        Open in the MedPull app
      </a>

      {/* "or" divider: hairlines are decorative; the words are a label. */}
      <p className="my-6 flex items-center gap-3 text-copy-lg text-body">
        <span aria-hidden className="h-px flex-1 bg-hairline" />
        or answer right here
        <span aria-hidden className="h-px flex-1 bg-hairline" />
      </p>

      {task.questions.length > 0 && (
        <div className="flex flex-col gap-stack">
          {task.questions.map((q) => (
            <QuestionCard
              key={q.id}
              q={q}
              value={answers[q.id]}
              onChange={(v, mode) =>
                setAnswers((a) => ({ ...a, [q.id]: mode === 'toggle' && a[q.id] === v ? null : v }))
              }
            />
          ))}
        </div>
      )}

      {submit.isError && (
        <PatientError>
          {submit.error instanceof ApiError
            ? submit.error.message
            : "Couldn't send your answers. Check your connection and try again."}
        </PatientError>
      )}

      <SendButton
        disabled={isCheckin && !answered}
        pending={submit.isPending}
        onClick={() => submit.mutate()}
      >
        {isCheckin ? 'Send to my care team' : 'Mark done'}
      </SendButton>
    </PatientShell>
  )
}
