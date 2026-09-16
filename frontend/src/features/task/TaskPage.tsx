import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, fetchJson } from '../../api/client'
import type { PublicTask } from '../../api/types'

/**
 * The page a task text links to (/t/<token>). Two ways in: the app, via its
 * URL scheme (tried once automatically, and offered as a button), or right
 * here — the same question chips the app and the check-in page use. The
 * token in the link is the credential, like /checkin/<token>.
 *
 * Patient-facing, on an unknown and often older device, so it follows the
 * same house rules as /checkin rather than the console's:
 *   - 16px (text-copy-lg) body floor, every sentence on --ink (17.124:1 on
 *     canvas light, 18.377:1 dark). --body is 6.729:1 on light canvas, under
 *     this route's 7:1 bar, so it carries labels only — never copy.
 *   - targets at least 48x56px (the 0-10 scale cells) or 56px tall and
 *     content-wide, with 8px between scale cells and 12px elsewhere.
 *   - no glass, no blur, no translucency; --faint is not used at all.
 *   - no uppercase: the 12px `.micro` eyebrow the console uses for the
 *     wordmark and the task kind is below this route's floor twice over.
 */

type Answers = Record<string, string | number | null>

const CHOICE_LABELS: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
  well: 'Well',
  rough: 'Rough night',
  all: 'All of them',
  some: 'Some',
  none: 'Not today',
}

/**
 * Identical to the /checkin chip, and deliberately so: a patient who answers
 * a text one day and a check-in link the next sees the same control. 56px
 * tall and never under 48px wide, so a single digit clears the 44px floor on
 * any screen. Selected is the brand FILL with --on-brand on it (4.602:1) and
 * a border of the same colour, so the box does not move by a pixel on tap.
 * Idle is the panel fill plus a --line-strong edge (3.573:1 on canvas) — the
 * fill alone is 1.073:1 there, so the edge is the control's only boundary and
 * WCAG 1.4.11 applies to it.
 */
function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex min-h-14 min-w-12 items-center justify-center rounded-control border px-tight text-copy-lg font-medium transition-[background-color,border-color,color] duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
        active
          ? 'border-brand bg-brand text-on-brand'
          : 'border-line-strong bg-panel text-ink hover:border-brand hover:bg-brand-tint'
      }`}
    >
      {children}
    </button>
  )
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

  const set = (id: string, value: string | number | null) =>
    setAnswers((a) => ({ ...a, [id]: a[id] === value ? null : value }))

  const shell = (content: React.ReactNode) => (
    <div className="mx-auto min-h-screen max-w-md px-snug py-region">
      <p className="mb-block text-copy-lg font-medium text-brand-ink">MedPull Recovery</p>
      {content}
    </div>
  )

  if (isLoading) return shell(<p className="text-copy-lg text-ink">Loading your task&hellip;</p>)

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This task couldn't be loaded. Please try again."
    return shell(
      <>
        <h1 className="text-title font-medium text-ink">{detail}</h1>
        <p className="mt-seam text-copy-lg text-ink">
          If you need a new link, reply to the text or ask your care team.
        </p>
      </>,
    )
  }

  if (submit.isSuccess || data.completed)
    return shell(
      <>
        <h1 className="text-title font-medium text-ink">
          {submit.isSuccess ? `Thanks, ${data.first_name} — all sent.` : 'This one is already done.'}
        </h1>
        <p className="mt-seam text-copy-lg text-ink">
          Your care team will see it with their next review. You can close this page.
        </p>
      </>,
    )

  const { task } = data
  const isCheckin = task.kind === 'checkin'
  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return shell(
    <>
      <p className="text-copy-lg text-body">{task.kind_label}</p>
      <h1 className="mt-el text-title font-medium text-ink">{task.title}</h1>
      {task.why && <p className="mt-seam text-copy-lg text-ink">{task.why}</p>}

      {/* The app hand-off: a 56px outlined target on the brand tint, labelled
          in --on-brand-tint (7.454:1 light, 5.624:1 dark) with a solid brand
          stroke (4.288:1 light, 3.993:1 dark — the tint fill is 1.079:1 on
          canvas, so the stroke is what makes it a button). */}
      <a
        href={data.deep_link}
        className="mt-block flex min-h-14 w-full items-center justify-center gap-seam rounded-control border border-brand bg-brand-tint text-copy-lg font-medium text-on-brand-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        Open in the MedPull app
      </a>
      <p className="mt-tight text-center text-copy-lg text-body">or answer right here</p>

      <div className="mt-region flex flex-col gap-region">
        {task.questions.map((q) => (
          <div key={q.id}>
            <p className="mb-snug text-subhead font-medium text-ink">{q.prompt}</p>
            {q.kind === 'scale' && (
              /* A 0-10 scale reads as a scale only if the rows line up, so it
                 is a fixed grid, not a wrap: 6 columns (0-5 / 6-10) from 360px
                 up, where a column is still (360-32-40)/6 = 48px wide, and 5
                 columns below that, where it is 51.2px. Either way every cell
                 clears the 44px target floor with 8px between cells, and a
                 `flex-wrap` row would instead orphan "10" on a third row at
                 375px and 390px, which is most phones. */
              <div className="grid grid-cols-5 gap-seam min-[360px]:grid-cols-6">
                {Array.from({ length: 11 }, (_, n) => (
                  <Chip key={n} active={answers[q.id] === n} onClick={() => set(q.id, n)}>
                    {n}
                  </Chip>
                ))}
              </div>
            )}
            {(q.kind === 'yes_no' || q.kind === 'choice') && (
              <div className="flex flex-wrap gap-tight">
                {(q.options ?? ['yes', 'no']).map((opt) => (
                  <Chip key={opt} active={answers[q.id] === opt} onClick={() => set(q.id, opt)}>
                    {CHOICE_LABELS[opt] ?? opt}
                  </Chip>
                ))}
              </div>
            )}
            {q.kind === 'number' && (
              <input
                type="number"
                inputMode="numeric"
                min={q.min ?? 0}
                max={q.max ?? 10000}
                value={(answers[q.id] as number | undefined) ?? ''}
                onChange={(e) =>
                  setAnswers((a) => ({
                    ...a,
                    [q.id]: e.target.value === '' ? null : Number(e.target.value),
                  }))
                }
                className="field min-h-14 border-line-strong px-snug text-copy-lg"
                placeholder={q.id === 'minutes' ? 'Minutes' : ''}
              />
            )}
            {q.kind === 'text' && (
              /* `.field` carries the focus indicator: a 2px --brand outline
                 declared at rest with no outline-style, flipped to solid on
                 :focus, so no box-shadow reset can erase it. The edge steps
                 up to --line-strong (`.field`'s --line is 1.447:1 on this
                 canvas) and the placeholder is --muted, never --faint. */
              <textarea
                rows={3}
                maxLength={2000}
                value={(answers[q.id] as string) ?? ''}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                placeholder="Optional"
                className="field border-line-strong p-snug text-copy-lg"
              />
            )}
          </div>
        ))}
      </div>

      {submit.isError && (
        <p className="mt-block text-copy-lg font-medium text-risk-high-ink">
          {submit.error instanceof ApiError
            ? submit.error.message
            : "Couldn't send your answers — check your connection and try again."}
        </p>
      )}

      {/* `.btn-primary` for the fill, the brand-deep pressed state, the
          focus-visible ring and the --disabled-fill/--disabled-ink pair
          (4.755:1 light, 4.582:1 dark). The disabled edge is added here
          because --disabled-fill is 1.057:1 on canvas: without it the button
          loses its shape, and --line-strong on it is 3.380:1. */}
      <button
        type="button"
        disabled={(isCheckin && !answered) || submit.isPending}
        onClick={() => submit.mutate()}
        className="btn-primary mt-region min-h-16 text-lede disabled:border disabled:border-line-strong"
      >
        {submit.isPending ? 'Sending…' : isCheckin ? 'Send to my care team' : 'Mark done'}
      </button>
    </>,
  )
}
