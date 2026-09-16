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
      className={`min-h-14 rounded-card px-5 text-[17px] font-medium transition-colors ${
        active ? 'bg-brand text-white' : 'bg-soft text-ink hover:bg-brand-tint'
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
    <div className="mx-auto min-h-screen max-w-lg px-6 py-12">
      <p className="mb-8 text-[20px] font-medium text-brand">MedPull Recovery</p>
      {content}
    </div>
  )

  if (isLoading) return shell(<p className="text-[16px] text-muted">Loading your check-in&hellip;</p>)

  if (error || !data) {
    const detail =
      error instanceof ApiError && error.status >= 400 && error.status < 500
        ? error.message
        : "This check-in couldn't be loaded. Please try again."
    return shell(
      <>
        <h1 className="text-[28px] font-normal leading-[1.25] text-ink">{detail}</h1>
        <p className="mt-3 text-[16px] text-muted">
          If you need a new link, ask your care team to send another check-in.
        </p>
      </>,
    )
  }

  if (submit.isSuccess)
    return shell(
      <>
        <h1 className="text-[28px] font-normal leading-[1.25] text-ink">
          Thanks, {data.patient_name} &mdash; all sent.
        </h1>
        <p className="mt-3 text-[16px] text-muted">
          Your care team will see this with your next review. You can close this page.
        </p>
      </>,
    )

  const answered = Object.values(answers).some((v) => v !== null && v !== '')

  return shell(
    <>
      <h1 className="text-[28px] font-normal leading-[1.25] text-ink">
        Hi {data.patient_name}, how's your recovery today?
      </h1>
      <p className="mt-2 text-[16px] text-muted">
        Takes under a minute. Skip anything you're not sure about.
      </p>

      <div className="mt-10 flex flex-col gap-10">
        {data.questions.map((q) => (
          <div key={q.id}>
            <p className="mb-4 text-[20px] font-medium text-ink">{q.prompt}</p>
            {q.kind === 'scale' && (
              <div className="grid grid-cols-6 gap-3">
                {Array.from({ length: 11 }, (_, n) => (
                  <Chip key={n} active={answers[q.id] === n} onClick={() => set(q.id, n)}>
                    {n}
                  </Chip>
                ))}
              </div>
            )}
            {(q.kind === 'yes_no' || q.kind === 'choice') && (
              <div className="flex flex-wrap gap-3">
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
                className="w-full rounded-field border border-line bg-panel p-4 text-[16px] text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:shadow-[0_0_0_1px_rgb(var(--brand))]"
              />
            )}
          </div>
        ))}
      </div>

      {submit.isError && (
        <p className="mt-6 text-[14px] font-medium text-risk-high">
          {/* A 410 means the link was already used or has expired, and a 422
              names the answer the form would not take. Telling that patient
              to check their connection sends them round the same loop. */}
          {submit.error instanceof ApiError && submit.error.status >= 400 && submit.error.status < 500
            ? submit.error.message
            : "Couldn't send your answers — check your connection and try again."}
        </p>
      )}

      <button
        type="button"
        disabled={!answered || submit.isPending}
        onClick={() => submit.mutate()}
        className="mt-10 min-h-16 w-full rounded-btn bg-brand text-[20px] font-medium text-white transition-[background-color,opacity] hover:bg-brand-deep disabled:opacity-40"
      >
        {submit.isPending ? 'Sending…' : 'Send to my care team'}
      </button>
    </>,
  )
}
