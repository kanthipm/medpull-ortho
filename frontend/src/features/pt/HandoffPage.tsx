import { useParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { dayText, useHandoffPage } from '../../api/pt'
import { PatientShell, PatientStatus, PatientTitle } from '../checkin/CheckinPage'

/**
 * `/h/<token>` — the page a clinic gives a person's trainer or coach.
 *
 * It exists only once the person has said yes to it, and the link is the
 * whole permission: no account, no sign-in, nothing to remember. It carries
 * what the therapist wrote for the trainer and nothing from the record: the
 * limits, the phase by name, this week's doses and ceilings, and what to send
 * back. No pain score, no diagnosis, no message, no chart.
 *
 * Read on a gym floor on whatever phone is to hand, so it follows the
 * /checkin house rules: one column, 16px ink body, no glass, no small print.
 */
export default function HandoffPage() {
  const { token } = useParams<{ token: string }>()
  const page = useHandoffPage(token)

  if (page.isLoading)
    return (
      <PatientShell>
        <PatientStatus tone="loading" title="Opening the page…" />
      </PatientShell>
    )

  if (page.error || !page.data) {
    const gone = page.error instanceof ApiError && page.error.status === 404
    return (
      <PatientShell>
        <PatientStatus tone="error" title={gone ? 'This page is no longer shared' : 'Can’t reach MedPull right now'}>
          {gone
            ? 'The person or their clinic has taken it down, or the link is not complete. Ask them for a new one.'
            : 'Check your connection, then try again.'}
        </PatientStatus>
      </PatientShell>
    )
  }

  const p = page.data
  const days = groupByDay(p.week)
  return (
    <PatientShell
      hero={
        <>
          <p className="text-copy-lg font-medium text-ink">{p.clinic}</p>
          <PatientTitle className="mt-3">{p.person}</PatientTitle>
          <p className="mt-3 text-copy-lg text-ink">
            {p.trainer_name ? `For ${p.trainer_name}. ` : ''}
            What {p.from ?? 'the clinic'} is asking you to work inside this week.
            {p.authorised_on ? ` Shared with ${p.person}’s agreement on ${dayText(p.authorised_on)}.` : ''}
          </p>
        </>
      }
    >
      <div className="space-y-4">
        {p.phase && (
          <section className="card p-5">
            <h2 className="text-label font-medium tracking-label text-secondary">
              Phase {p.phase.number} of {p.phase.count}
            </h2>
            <p className="mt-1 text-lede font-medium text-ink">{p.phase.name}</p>
            {p.phase.goal && <p className="mt-1 text-copy-lg text-ink">{p.phase.goal}</p>}
          </section>
        )}

        <section className="card p-5">
          <h2 className="text-label font-medium tracking-label text-secondary">Limits</h2>
          {p.limits.length === 0 ? (
            <p className="mt-1 text-copy-lg text-ink">None written yet.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {p.limits.map((l, i) => (
                <li key={i} className="flex gap-3 text-copy-lg text-ink">
                  <span aria-hidden className="mt-[0.6em] h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {days.length > 0 && (
          <section className="card p-5">
            <h2 className="text-label font-medium tracking-label text-secondary">
              This week from the clinic · week of {dayText(p.week_start)}
            </h2>
            <ul className="mt-2 divide-y divide-line">
              {days.map(([day, rows]) => (
                <li key={day} className="py-3 first:pt-1 last:pb-0">
                  <p className="text-copy-lg font-medium text-ink">{dayText(day)}</p>
                  <ul className="mt-1 space-y-2">
                    {rows.map((r, i) => (
                      <li key={i} className="text-copy-lg text-ink">
                        {r.title}
                        {r.dose && <span className="text-secondary"> · {r.dose}</span>}
                        {r.ceiling && <span className="block font-medium">{r.ceiling}</span>}
                        {r.instructions && <span className="block text-copy text-secondary">{r.instructions}</span>}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        )}

        {p.report_back && (
          <section className="card p-5">
            <h2 className="text-label font-medium tracking-label text-secondary">What to send back</h2>
            <p className="mt-1 whitespace-pre-line text-copy-lg text-ink">{p.report_back}</p>
          </section>
        )}

        <p className="px-1 text-copy text-secondary">
          This page shows the limits and doses the clinic wrote for you. It holds nothing from {p.person}’s health
          record, and {p.person} or the clinic can take it down at any time.
          {p.updated_at ? ` Last changed ${dayText(p.updated_at.slice(0, 10))}.` : ''}
        </p>
      </div>
    </PatientShell>
  )
}

type Row = { day: string; title: string; dose: string; ceiling: string; instructions: string }

function groupByDay(week: Row[]): [string, Row[]][] {
  const out = new Map<string, Row[]>()
  for (const r of week) out.set(r.day, [...(out.get(r.day) ?? []), r])
  return [...out.entries()].sort(([a], [b]) => a.localeCompare(b))
}
