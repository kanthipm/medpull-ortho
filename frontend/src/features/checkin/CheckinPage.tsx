import { useMutation, useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useState } from 'react'
import { ApiError, fetchJson } from '../../api/client'

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
    <div className="mx-auto min-h-screen max-w-md px-5 py-10">
      <p className="micro mb-6">MedPull Recovery</p>
      {content}
    </div>
  )

  if (isLoading) return shell(<p className="text-[14px] text-muted">Loading your check-in&hellip;</p>)

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This check-in couldn't be loaded. Please try again."
    return shell(
      <>
        <h1 className="text-[22px] font-semibold tracking-[-.02em] text-ink">{detail}</h1>
        <p className="mt-2 text-[14px] text-muted">
          If you need a new link, ask your care team to send another check-in.
        </p>
      </>,
    )
  }

  if (submit.isSuccess)
    return shell(
      <>
        <h1 className="text-[22px] font-semibold tracking-[-.02em] text-ink">
          Thanks, {data.patient_name} &mdash; all sent.
        </h1>
        <p className="mt-2 text-[14px] text-muted">
          Your care team will see this with your next review. You can close this page.
        </p>
      </>,
    )

  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return shell(
    <>
      <h1 className="text-[22px] font-semibold tracking-[-.02em] text-ink">
        Hi {data.patient_name}, how's your recovery today?
      </h1>
      <p className="mt-1 text-[13px] text-muted">
        Takes under a minute. Skip anything you're not sure about.
      </p>

      <div className="mt-8 flex flex-col gap-8">
        {data.questions.map((q) => (
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
          Couldn't send your answers &mdash; check your connection and try again.
        </p>
      )}

      <button
        type="button"
        disabled={!answered || submit.isPending}
        onClick={() => submit.mutate()}
        className="mt-8 min-h-12 w-full rounded-btn bg-brand text-[15px] font-semibold text-white transition-opacity disabled:opacity-40"
      >
        {submit.isPending ? 'Sending…' : 'Send to my care team'}
      </button>
    </>,
  )
}
