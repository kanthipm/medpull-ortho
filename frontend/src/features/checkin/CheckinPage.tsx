import { useMutation, useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useState } from 'react'
import { ApiError, fetchJson } from '../../api/client'

/**
 * /checkin/<token> — a post-operative patient, on their own device, often an
 * older phone and sometimes with reduced vision. The console's defaults are
 * deliberately NOT inherited here:
 *   - 16px (text-copy-lg) is the body floor, not 14px, and every sentence is
 *     --ink (17.124:1 on canvas light, 18.377:1 dark). --body is 6.729:1 on
 *     light canvas, i.e. under the 7:1 bar this route is held to, so it is
 *     used for labels only and never for copy.
 *   - every target is at least 48x56px (the 0-10 scale cells) or 56px tall
 *     and content-wide (everything else), with 8px between scale cells and
 *     12px everywhere else — all above the 44px / 8px floor.
 *   - no glass, no blur, no translucency of any kind on this route.
 *   - --faint appears nowhere: it is 2.409:1 on canvas and is non-text only.
 *   - no uppercase: the console's 12px `.micro` eyebrow is both too small and
 *     harder to read at this size, so the wordmark is sentence case.
 */

interface Question {
  id: string
  prompt: string
  kind: 'scale' | 'yes_no' | 'choice' | 'text'
  options?: string[]
}

interface CheckinForm {
  patient_name: string
  questions: Question[]
}

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
 * 56px tall and never under 48px wide, so a single digit clears the 44px
 * target floor on any screen (measured: 48.0x56.0 in a 360px-wide grid cell,
 * 53.0x56.0 at 390px). Selected is the brand FILL with --on-brand on it
 * (4.602:1); the border is the same colour as the fill, so the box measures
 * the same in both states and nothing shifts by a pixel on tap. Idle is the
 * panel fill plus a --line-strong edge (3.573:1 on canvas): the fill alone is
 * 1.073:1 there, so the edge is the only thing that says "this is a control"
 * and WCAG 1.4.11 applies to it.
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

  const set = (id: string, value: string | number | null) =>
    setAnswers((a) => ({ ...a, [id]: a[id] === value ? null : value }))

  const shell = (content: React.ReactNode) => (
    <div className="mx-auto min-h-screen max-w-lg px-snug py-region">
      <p className="mb-region text-copy-lg font-medium text-brand-ink">MedPull Recovery</p>
      {content}
    </div>
  )

  if (isLoading) return shell(<p className="text-copy-lg text-ink">Loading your check-in&hellip;</p>)

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This check-in couldn't be loaded. Please try again."
    return shell(
      <>
        <h1 className="text-section font-normal text-ink">{detail}</h1>
        <p className="mt-tight text-copy-lg text-ink">
          If you need a new link, ask your care team to send another check-in.
        </p>
      </>,
    )
  }

  if (submit.isSuccess)
    return shell(
      <>
        <h1 className="text-section font-normal text-ink">
          Thanks, {data.patient_name} &mdash; all sent.
        </h1>
        <p className="mt-tight text-copy-lg text-ink">
          Your care team will see this with your next review. You can close this page.
        </p>
      </>,
    )

  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return shell(
    <>
      <h1 className="text-section font-normal text-ink">
        Hi {data.patient_name}, how's your recovery today?
      </h1>
      <p className="mt-seam text-copy-lg text-ink">
        Takes under a minute. Skip anything you're not sure about.
      </p>

      <div className="mt-region flex flex-col gap-region">
        {data.questions.map((q) => (
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
            {q.kind === 'text' && (
              /* `.field` carries the focus indicator this route must keep: a
                 2px --brand outline declared at rest with no outline-style,
                 flipped to solid on :focus. It replaces the old
                 `focus:outline-none` + `focus:shadow-[0_0_0_1px_...]` pair,
                 which any box-shadow reset could have erased. The edge steps
                 up to --line-strong because `.field`'s --line is only 1.447:1
                 on this canvas, and the placeholder is --muted, never --faint. */
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
          {/* A 410 means the link was already used or has expired, and a 422
              names the answer the form would not take. Telling that patient
              to check their connection sends them round the same loop. */}
          {submit.error instanceof ApiError && submit.error.status >= 400 && submit.error.status < 500
            ? submit.error.message
            : "Couldn't send your answers — check your connection and try again."}
        </p>
      )}

      {/* `.btn-primary` for the fill, the brand-deep pressed state, the
          focus-visible ring and the --disabled-fill/--disabled-ink pair
          (4.755:1 light, 4.582:1 dark). The disabled edge is added here
          because --disabled-fill is 1.057:1 on canvas: without it the button
          loses its shape entirely, and --line-strong on it is 3.380:1. */}
      <button
        type="button"
        disabled={!answered || submit.isPending}
        onClick={() => submit.mutate()}
        className="btn-primary mt-region min-h-16 text-lede disabled:border disabled:border-line-strong"
      >
        {submit.isPending ? 'Sending…' : 'Send to my care team'}
      </button>
    </>,
  )
}
