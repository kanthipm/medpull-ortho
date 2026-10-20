import { useState } from 'react'
import type { SessionRow } from '../../api/sports'
import SectionCard from '../../components/SectionCard'
import { shortDate } from '../../lib/format'
import { DASH, fmt, words } from './sportsFormat'

const SHOW = 10
const TH = 'meta whitespace-nowrap px-3 pb-2 pt-1 text-left font-medium'
const TD = 'px-3 py-2 align-top text-copy'

/** The last four weeks of sessions, newest first. */
export default function SessionsCard({ sessions }: { sessions: SessionRow[] }) {
  const [all, setAll] = useState(false)
  const rows = all ? sessions : sessions.slice(0, SHOW)
  const totalLoad = sessions.reduce((a, s) => a + (s.load_au ?? 0), 0)
  return (
    <SectionCard
      flush
      title="Sessions"
      aside={sessions.length > 0 ? `${sessions.length} in 28 days · ${fmt(totalLoad)} AU` : undefined}
    >
      {sessions.length === 0 ? (
        <p className="px-5 pb-5 text-copy text-secondary">No sessions logged in the last 28 days.</p>
      ) : (
        <>
          <div className="overflow-x-auto pb-2">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th scope="col" className={`${TH} pl-5`}>Date</th>
                  <th scope="col" className={TH}>Session</th>
                  <th scope="col" className={`${TH} text-right`}>Minutes</th>
                  <th scope="col" className={`${TH} text-right`}>RPE</th>
                  <th scope="col" className={`${TH} text-right`}>Load</th>
                  <th scope="col" className={`${TH} text-right`}>Jumps</th>
                  <th scope="col" className={`${TH} pr-5`}>Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} className="border-t border-hairline">
                    <td className={`${TD} whitespace-nowrap pl-5 tabular-nums text-ink`}>{shortDate(s.date)}</td>
                    <td className={`${TD} text-ink`}>
                      {words(s.kind)}
                      {s.note && <span className="meta block max-w-[32ch] truncate">{s.note}</span>}
                    </td>
                    <td className={`${TD} text-right tabular-nums text-ink`}>{fmt(s.minutes)}</td>
                    <td className={`${TD} text-right tabular-nums text-ink`}>{fmt(s.rpe)}</td>
                    <td className={`${TD} whitespace-nowrap text-right tabular-nums text-ink`}>
                      {s.load_au == null ? DASH : `${fmt(s.load_au)} AU`}
                    </td>
                    <td className={`${TD} text-right tabular-nums text-ink`}>{fmt(s.jumps)}</td>
                    <td className={`${TD} pr-5 text-secondary`}>{words(s.source)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sessions.length > SHOW && (
            <div className="flex justify-center px-5 pb-4">
              <button type="button" className="btn-plain btn-sm" onClick={() => setAll((a) => !a)}>
                {all ? 'Show recent only' : `Show all ${sessions.length} sessions`}
              </button>
            </div>
          )}
        </>
      )}
    </SectionCard>
  )
}
