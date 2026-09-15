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
      className={`min-h-11 rounded-btn border px-4 text-[14px] font-medium transition-colors ${
        active
          ? 'border-brand bg-brand-tint text-brand'
          : 'border-line bg-panel text-ink hover:border-brand/40'
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
    <div className="mx-auto min-h-screen max-w-md px-5 py-10">
      <p className="micro mb-6">MedPull Recovery</p>
      {content}
    </div>
  )

  if (isLoading) return shell(<p className="text-[14px] text-muted">Loading your task&hellip;</p>)

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This task couldn't be loaded. Please try again."
    return shell(
      <>
        <h1 className="text-[22px] font-semibold tracking-[-.02em] text-ink">{detail}</h1>
        <p className="mt-2 text-[14px] text-muted">
          If you need a new link, reply to the text or ask your care team.
        </p>
      </>,
    )
  }

  if (submit.isSuccess || data.completed)
    return shell(
      <>
        <h1 className="text-[22px] font-semibold tracking-[-.02em] text-ink">
          {submit.isSuccess ? `Thanks, ${data.first_name} — all sent.` : 'This one is already done.'}
        </h1>
        <p className="mt-2 text-[14px] text-muted">
          Your care team will see it with their next review. You can close this page.
        </p>
      </>,
    )

  const { task } = data
  const isCheckin = task.kind === 'checkin'
  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return shell(
    <>
      <p className="micro">{task.kind_label}</p>
      <h1 className="mt-1 text-[22px] font-semibold tracking-[-.02em] text-ink">{task.title}</h1>
      {task.why && <p className="mt-1 text-[13px] text-muted">{task.why}</p>}

      <a
        href={data.deep_link}
        className="mt-5 flex min-h-12 w-full items-center justify-center gap-2 rounded-btn border border-brand/40 bg-brand-tint text-[14px] font-semibold text-brand"
      >
        Open in the MedPull app
      </a>
      <p className="mt-2 text-center text-[12px] text-faint">or answer right here</p>

      <div className="mt-6 flex flex-col gap-7">
        {task.questions.map((q) => (
          <div key={q.id}>
            <p className="mb-3 text-[14.5px] font-semibold text-ink">{q.prompt}</p>
            {q.kind === 'scale' && (
              <div className="grid grid-cols-6 gap-2">
                {Array.from({ length: 11 }, (_, n) => (
                  <Chip key={n} active={answers[q.id] === n} onClick={() => set(q.id, n)}>
                    {n}
                  </Chip>
                ))}
              </div>
            )}
            {(q.kind === 'yes_no' || q.kind === 'choice') && (
              <div className="flex flex-wrap gap-2">
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
                className="field min-h-11 text-[15px]"
                placeholder={q.id === 'minutes' ? 'Minutes' : ''}
              />
            )}
            {q.kind === 'text' && (
              <textarea
                rows={3}
                maxLength={2000}
                value={(answers[q.id] as string) ?? ''}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                placeholder="Optional"
                className="w-full rounded-btn border border-line bg-panel p-3 text-[14px] text-ink placeholder:text-faint focus:border-brand focus:outline-none"
              />
            )}
          </div>
        ))}
      </div>

      {submit.isError && (
        <p className="mt-6 text-[13px] font-medium text-red-500">
          {submit.error instanceof ApiError
            ? submit.error.message
            : "Couldn't send your answers — check your connection and try again."}
        </p>
      )}

      <button
        type="button"
        disabled={(isCheckin && !answered) || submit.isPending}
        onClick={() => submit.mutate()}
        className="mt-8 min-h-12 w-full rounded-btn bg-brand text-[15px] font-semibold text-white transition-opacity disabled:opacity-40"
      >
        {submit.isPending ? 'Sending…' : isCheckin ? 'Send to my care team' : 'Mark done'}
      </button>
    </>,
  )
}
