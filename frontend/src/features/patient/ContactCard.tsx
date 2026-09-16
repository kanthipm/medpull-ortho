import { Link2, Pencil, Smartphone, SmartphoneNfc } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import { useAppLinkCandidates, useLinkApp, useUpdateContact } from '../../api/queries'
import type { AppEnrollment, AppLinkCandidate } from '../../api/types'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'

/**
 * "Phone & app" — the one place the console shows whether it can actually
 * reach this person: the number texts go to, and whether the patient app is
 * signed in on this chart. Both are editable here, because a chart with no
 * phone silently stores every message for an app nobody opened, and a
 * patient who signed up in the app under a second record never sees what
 * the console sends. Linking folds that second record into this one.
 */
export default function ContactCard({
  patientId,
  patientName,
  phone,
  app,
  smsConfigured,
}: {
  patientId: string
  patientName: string
  phone: string | null
  app: AppEnrollment
  smsConfigured: boolean
}) {
  const toast = useToast()
  const first = patientName.split(' ')[0]
  const update = useUpdateContact(patientId)
  const link = useLinkApp(patientId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(phone ?? '')
  const [linking, setLinking] = useState(false)
  const candidates = useAppLinkCandidates(patientId, linking)

  const savePhone = (force = false) => {
    const value = draft.trim()
    update.mutate(
      { phone: value || null, force },
      {
        onSuccess: (r) => {
          setEditing(false)
          toast(
            r.phone
              ? r.moved_from.length
                ? `Number moved to ${first} from ${r.moved_from.join(', ')}`
                : `${first} can now be texted at ${r.phone}`
              : `Phone cleared — messages stay in the app only`,
            'info',
          )
        },
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409 && !force) {
            if (window.confirm(`${e.message}\n\nMove the number to ${first} anyway?`)) savePhone(true)
            return
          }
          toast(e instanceof ApiError ? e.message : 'Could not save the number', 'warning')
        },
      },
    )
  }

  const doLink = (c: AppLinkCandidate) => {
    if (c.refusal) {
      // The server would refuse, and the reason is worth reading rather than
      // discovering after a click that cannot be undone.
      toast(c.refusal, 'warning')
      return
    }
    const moving = [
      c.observations > 0 && `${c.observations} health readings`,
      c.checkins > 0 && `${c.checkins} check-ins`,
      c.app.ever_enrolled && 'an app session',
    ].filter(Boolean)
    if (
      !window.confirm(
        `Link "${c.name}" (${c.patient_id}) into ${patientName}'s chart?\n\n` +
          (moving.length ? `That record holds ${moving.join(', ')}. ` : '') +
          `Its session, messages, tasks and health data move here and the "${c.name}" record is removed. This cannot be undone.`,
      )
    )
      return
    link.mutate(c.patient_id, {
      onSuccess: (r) => {
        setLinking(false)
        toast(
          `Linked — ${first}'s phone is now on this chart${r.phone ? ` (${r.phone})` : ''}`,
          'success',
        )
      },
      onError: (e) => toast(e instanceof ApiError ? e.message : 'Linking failed', 'warning'),
    })
  }

  const reach = !phone
    ? { label: 'No phone on file', tone: 'text-risk-med-ink' }
    : !smsConfigured
      ? { label: 'Texting is not configured on this server', tone: 'text-muted' }
      : { label: 'Texts reach this number', tone: 'text-risk-low-ink' }

  return (
    <div className="panel px-3.5 py-3">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-[220px] flex-1">
          <p className="flex items-center gap-1.5 text-label font-medium text-muted">
            <Smartphone size={11} /> Phone
          </p>
          {editing ? (
            <div className="mt-1.5 flex gap-2">
              <input
                className="field"
                autoFocus
                inputMode="tel"
                placeholder="+1 512 555 0100"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') savePhone()
                  if (e.key === 'Escape') setEditing(false)
                }}
              />
              <button
                type="button"
                className="qa-btn shrink-0"
                disabled={update.isPending}
                onClick={() => savePhone()}
              >
                Save
              </button>
              <button
                type="button"
                className="qa-btn shrink-0"
                onClick={() => {
                  setDraft(phone ?? '')
                  setEditing(false)
                }}
              >
                Cancel
              </button>
            </div>
          ) : (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-copy font-medium text-ink">{phone ?? '—'}</span>
              <span className={`text-label font-medium ${reach.tone}`}>{reach.label}</span>
              <button
                type="button"
                className="inline-flex cursor-pointer items-center gap-1 rounded-control px-1.5 py-0.5 text-label font-medium text-brand-ink transition-colors duration-150 hover:bg-brand-tint"
                onClick={() => {
                  setDraft(phone ?? '')
                  setEditing(true)
                }}
              >
                <Pencil size={11} /> {phone ? 'Change' : 'Add number'}
              </button>
            </div>
          )}
        </div>

        <div className="min-w-[220px] flex-1">
          <p className="flex items-center gap-1.5 text-label font-medium text-muted">
            <SmartphoneNfc size={11} /> Patient app
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {app.enrolled ? (
              <>
                <span className="chip bg-risk-low-tint text-risk-low-ink">Signed in</span>
                <span className="text-label font-medium text-muted">
                  {app.device_name ?? 'iPhone'}
                  {app.last_seen_at && <> · seen {relativeTime(app.last_seen_at)}</>}
                </span>
              </>
            ) : (
              <>
                <span className="chip bg-soft text-muted">
                  {app.ever_enrolled ? 'Signed out' : 'Not enrolled'}
                </span>
                <span className="text-label font-medium text-muted">
                  Messages and tasks reach {first} by text only
                </span>
                <button
                  type="button"
                  className="inline-flex cursor-pointer items-center gap-1 rounded-control px-1.5 py-0.5 text-label font-medium text-brand-ink transition-colors duration-150 hover:bg-brand-tint"
                  onClick={() => setLinking((v) => !v)}
                >
                  <Link2 size={11} /> {linking ? 'Close' : 'Link an app sign-up'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {linking && !app.enrolled && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-label font-medium text-muted">
            If {first} signed up in the app as a separate record, pick it here to fold it into this
            chart. Their phone, messages, tasks and health data move; the other record is removed.
          </p>
          {candidates.isLoading && <p className="mt-2 text-label text-muted">Looking…</p>}
          {candidates.data && candidates.data.candidates.length === 0 && (
            <p className="mt-2 text-label font-medium text-muted">
              No other record has signed in on the app or has a phone yet.
            </p>
          )}
          {candidates.data && candidates.data.candidates.length > 0 && (
            <ul className="mt-2 divide-y divide-line">
              {candidates.data.candidates.slice(0, 8).map((c) => (
                <li key={c.patient_id} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-copy font-medium text-ink">
                      {c.name}{' '}
                      <span className="font-mono text-label font-medium text-muted">{c.patient_id}</span>
                    </p>
                    <p className="text-label font-medium text-muted">
                      {c.mode === 'general' ? 'General patient' : c.procedure_display}
                      {c.phone_masked && <> · {c.phone_masked}</>}
                      {c.app.enrolled ? (
                        <>
                          {' '}
                          · app signed in{c.app.last_seen_at && <>, seen {relativeTime(c.app.last_seen_at)}</>}
                        </>
                      ) : (
                        <> · app not signed in</>
                      )}
                      {c.phone_match && <span className="text-risk-low-ink"> · same number</span>}
                      {c.name_match && !c.phone_match && <span className="text-brand-ink"> · name matches</span>}
                      {c.observations > 0 && <> · {c.observations} readings</>}
                      {c.checkins > 0 && <> · {c.checkins} check-ins</>}
                    </p>
                    {c.refusal && (
                      <p className="mt-0.5 text-label font-medium text-risk-high-ink">
                        Cannot link: {c.refusal}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="qa-btn shrink-0"
                    disabled={link.isPending || Boolean(c.refusal)}
                    title={c.refusal ?? `Fold ${c.name} into this chart`}
                    onClick={() => doLink(c)}
                  >
                    <Link2 size={13} /> Link
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
