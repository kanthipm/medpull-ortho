import { Copy, ExternalLink, Send, Share2, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { dayText, usePtAction, type PtChart } from '../../api/pt'
import { useToast } from '../../components/Toast'
import { Group, Pill } from './ptBits'
import { errorText, sentLine } from './ptWords'

const STATUS: Record<string, [string, 'plain' | 'warn' | 'brand' | 'alert']> = {
  draft: ['Not shared', 'plain'],
  awaiting: ['Waiting on their yes', 'warn'],
  active: ['Shared', 'brand'],
  declined: ['They said no', 'alert'],
  revoked: ['Taken back', 'plain'],
}

/** The trainer's page: what a therapist wants the person's trainer to know.
 *  Limits, this week's exercises with their ceilings, and what to report
 *  back. It is a page behind a link, and the link exists only once the
 *  person has said yes; nothing from their record is on it. */
export default function ProgramTrainer({
  patientId,
  first,
  data,
  by,
}: {
  patientId: string
  first: string
  data: PtChart
  by: string
}) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const h = data.handoff
  const editable = !h || h.status !== 'declined'
  const [trainer, setTrainer] = useState(h?.trainer_name ?? '')
  const [limits, setLimits] = useState((h?.limits ?? []).join('\n'))
  const [report, setReport] = useState(h?.report_back ?? '')
  const [week, setWeek] = useState(h?.include_week ?? true)
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const lines = limits.split('\n').map((l) => l.trim()).filter(Boolean)
  const [label, tone] = STATUS[h?.status ?? 'draft']
  const dirty =
    !h ||
    trainer !== h.trainer_name ||
    lines.join('\n') !== h.limits.join('\n') ||
    report !== h.report_back ||
    week !== h.include_week

  const save = (then?: () => void) =>
    act.mutate(
      {
        path: '/handoff',
        method: 'PUT',
        body: { trainer_name: trainer, limits: lines, report_back: report, include_week: week, by },
      },
      { onSuccess: () => (then ? then() : toast('Saved', 'success')), onError: fail },
    )
  const request = () =>
    act.mutate(
      { path: '/handoff/request', body: { by } },
      { onSuccess: (r) => toast(...sentLine(first, r.sent, 'The question')), onError: fail },
    )

  return (
    <div className="grid gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Group label="What the trainer is told" aside={<Pill tone={tone}>{label}</Pill>}>
        <div className="space-y-3">
          <label className="block">
            <span className="text-label text-secondary">Trainer</span>
            <input
              className="field mt-1"
              placeholder="Their trainer’s name"
              maxLength={120}
              value={trainer}
              disabled={h?.status === 'active'}
              onChange={(e) => setTrainer(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-label text-secondary">Limits, one to a line</span>
            <textarea
              className="field mt-1 resize-y"
              rows={4}
              placeholder={'No jumping or bounding yet\nSquats to a box: top half only'}
              value={limits}
              onChange={(e) => setLimits(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-label text-secondary">What to report back</span>
            <input
              className="field mt-1"
              maxLength={400}
              placeholder="Any session where it is worse the next morning."
              value={report}
              onChange={(e) => setReport(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-copy text-ink">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={week} onChange={(e) => setWeek(e.target.checked)} />
            Also show this week’s exercises with their doses and ceilings
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-tinted btn-sm" disabled={!editable || !dirty || act.isPending} onClick={() => save()}>
            Save
          </button>
          {(!h || h.status === 'draft' || h.status === 'declined' || h.status === 'revoked') && (
            <button
              type="button"
              className="btn-filled btn-sm"
              disabled={act.isPending || (lines.length === 0 && !report.trim())}
              onClick={() => (dirty ? save(request) : request())}
            >
              <Share2 aria-hidden /> Ask {first} to share it
            </button>
          )}
          {h?.status === 'awaiting' && (
            <button type="button" className="btn-gray btn-sm" disabled={act.isPending} onClick={request}>
              <Send aria-hidden /> Ask again
            </button>
          )}
          {h && (h.status === 'active' || h.status === 'awaiting') && (
            <button
              type="button"
              className="btn-plain btn-sm"
              disabled={act.isPending}
              onClick={() => act.mutate({ path: '/handoff/revoke' }, { onSuccess: () => toast('Taken back: the link is dead', 'info'), onError: fail })}
            >
              <Undo2 aria-hidden /> Take it back
            </button>
          )}
        </div>
      </Group>

      <Group label="The page">
        {h?.status === 'active' && h.url ? (
          <div className="space-y-2 text-copy">
            <p className="text-ink">
              {first} agreed{h.authorised_at ? ` on ${dayText(h.authorised_at)}` : ''}. Anyone with this link sees the
              page, and only the page.
            </p>
            <p className="break-all rounded-control bg-soft px-3 py-2 font-mono text-label text-ink">{h.url}</p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-gray btn-sm"
                onClick={() => {
                  void navigator.clipboard?.writeText(h.url ?? '')
                  toast('Link copied', 'success')
                }}
              >
                <Copy aria-hidden /> Copy the link
              </button>
              <a className="btn-plain btn-sm" href={h.url} target="_blank" rel="noreferrer">
                Open it <ExternalLink aria-hidden size={14} />
              </a>
            </div>
            <p className="meta">
              Opened {h.open_count} {h.open_count === 1 ? 'time' : 'times'}
              {h.last_opened_at ? `, last ${dayText(h.last_opened_at)}` : ''}. Edits above show on it at once.
            </p>
          </div>
        ) : h?.status === 'awaiting' ? (
          <p className="text-copy text-secondary">
            {first} was asked{h.requested_at ? ` on ${dayText(h.requested_at)}` : ''} and has not answered. There is no
            link until they say yes.
          </p>
        ) : h?.status === 'declined' ? (
          <p className="text-copy text-secondary">{first} said no. Nothing was shared, and there is no link.</p>
        ) : (
          <p className="text-copy text-secondary">
            Nothing is shared yet. Write the limits, then ask {first}: they are shown exactly what the trainer will see
            and it goes nowhere unless they say yes. The page carries limits and doses, and nothing from the record: no
            pain scores, no notes, no messages.
          </p>
        )}
      </Group>
    </div>
  )
}
