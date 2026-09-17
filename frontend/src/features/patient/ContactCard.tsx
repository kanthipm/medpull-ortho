import { Link2, Pencil, Smartphone, SmartphoneNfc } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { useAppLinkCandidates, useLinkApp, useUpdateContact } from '../../api/queries'
import type { AppEnrollment, AppLinkCandidate } from '../../api/types'
import { ListGroup } from '../../components/ListRow'
import ListRow from '../../components/ListRow'
import { Popover } from '../../components/Menu'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import DotLine from './DotLine'

/** One reachability line: a 16px icon column, then the text in normal
 *  inline flow, so a wrapped line (and a wrapped action) starts at the text
 *  column, never under the icon or indented past it (judge #10). */
const ROW = 'grid grid-cols-[16px_minmax(0,1fr)] items-start gap-x-2'
const ICON = 'mt-[3px] text-body'
/** An action inside a line of text: brand-ink words with no side padding, so
 *  when it wraps it lines up with the text above it. 24px tall (2.5.8), and
 *  the focus ring is the console's solid 2px --focus. brand-ink on the safe
 *  sky: 4.832 light / 4.735 dark. */
const INLINE_ACTION =
  'inline-flex min-h-6 cursor-pointer items-center gap-1 whitespace-nowrap rounded-sm align-middle font-medium text-brand-ink underline-offset-2 transition-colors duration-state ease-apple hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus'

/**
 * Reachability, as one line of header meta: the number texts go to and
 * whether the patient app is signed in on this chart. Both stay editable —
 * a chart with no phone silently stores every message for an app nobody
 * opened, and a patient who signed up in the app under a second record never
 * sees what the console sends. Linking folds that second record into this one.
 *
 * The editors open in top-layer popovers (R5), so the header stays one line.
 * The window.confirm steps are unchanged on purpose.
 *
 * Text sits in the page head on the SAFE sky (AppShell's sky window); every
 * colour used here at the sky's most saturated point, light / dark:
 *   ink 15.453 / 12.002, body 6.073 / 4.642, brand-ink 4.832 / 4.735,
 *   risk-med-ink 4.890 / 6.729, risk-low-ink 4.514 / 6.307.
 * Each separator dot wraps with the item after it (DotLine).
 * In the popovers (overlay panel): body 4.955 dark, low 6.731, brand 5.054,
 * risk-high 5.635 — secondary text there is --body (OVERLAY_SCOPE).
 */
export default function ContactCard({
  patientId,
  patientName,
  phone,
  app,
  smsConfigured,
  className = '',
}: {
  patientId: string
  patientName: string
  phone: string | null
  app: AppEnrollment
  smsConfigured: boolean
  className?: string
}) {
  const toast = useToast()
  const first = patientName.split(' ')[0]
  const update = useUpdateContact(patientId)
  const link = useLinkApp(patientId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(phone ?? '')
  const [linking, setLinking] = useState(false)
  const candidates = useAppLinkCandidates(patientId, linking)
  const phoneBtn = useRef<HTMLButtonElement>(null)
  const linkBtn = useRef<HTMLButtonElement>(null)
  const phoneId = useId()
  const linkId = useId()
  const fieldId = useId()

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
    ? { label: 'No phone on file', tone: 'text-risk-med-ink font-medium' }
    : !smsConfigured
      ? { label: 'texting is not configured on this server', tone: 'text-body' }
      : { label: 'texts reach this number', tone: 'text-body' }

  return (
    <div className={`space-y-1 text-copy ${className}`}>
      {/* Phone */}
      <div className={ROW}>
        <Smartphone size={14} aria-hidden className={ICON} />
        <p className="min-w-0">
          <span className="sr-only">Phone: </span>
          <DotLine
            parts={[
              phone && <span className="font-medium tabular-nums text-ink">{phone}</span>,
              <span className={reach.tone}>{reach.label}</span>,
            ]}
          />{' '}
          <button
            ref={phoneBtn}
            type="button"
            className={INLINE_ACTION}
            aria-haspopup="dialog"
            aria-expanded={editing}
            aria-controls={editing ? phoneId : undefined}
            onClick={() => {
              setDraft(phone ?? '')
              setEditing((v) => !v)
            }}
          >
            <Pencil size={13} aria-hidden /> {phone ? 'Change' : 'Add number'}
          </button>
        </p>
      </div>

      {/* Patient app */}
      <div className={ROW}>
        <SmartphoneNfc size={14} aria-hidden className={ICON} />
        <p className="min-w-0">
          {app.enrolled ? (
            <DotLine
              parts={[
                <span className="font-medium text-risk-low-ink">App signed in</span>,
                app.device_name ?? 'iPhone',
                app.last_seen_at && `seen ${relativeTime(app.last_seen_at)}`,
              ]}
            />
          ) : (
            <>
              <DotLine
                parts={[
                  <span className="font-medium text-ink">
                    {app.ever_enrolled ? 'App signed out' : 'App not enrolled'}
                  </span>,
                  `${first} gets messages and tasks by text only`,
                ]}
              />{' '}
              <button
                ref={linkBtn}
                type="button"
                className={INLINE_ACTION}
                aria-haspopup="dialog"
                aria-expanded={linking}
                aria-controls={linking ? linkId : undefined}
                onClick={() => setLinking((v) => !v)}
              >
                <Link2 size={13} aria-hidden /> Link an app sign-up
              </button>
            </>
          )}
        </p>
      </div>

      <Popover
        open={editing}
        onClose={() => setEditing(false)}
        anchorRef={phoneBtn}
        placement="bottom-start"
        id={phoneId}
        aria-label={`${first}'s phone number`}
        className="w-[min(360px,calc(100vw-32px))] p-4"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault()
            savePhone()
          }}
        >
          <label htmlFor={fieldId} className="text-copy font-medium text-ink">
            Number for texts
          </label>
          <p className="meta mt-0.5">Messages and tasks for {first} go to this number.</p>
          <input
            id={fieldId}
            className="field mt-3"
            inputMode="tel"
            autoComplete="off"
            placeholder="+1 512 555 0100"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="btn-gray btn-sm" onClick={() => setEditing(false)}>
              Cancel
            </button>
            <button type="submit" className="btn-filled btn-sm" disabled={update.isPending}>
              {update.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Popover>

      <Popover
        open={linking && !app.enrolled}
        onClose={() => setLinking(false)}
        anchorRef={linkBtn}
        placement="bottom-start"
        id={linkId}
        aria-label="Link an app sign-up"
        className="w-[min(460px,calc(100vw-32px))] overflow-hidden"
      >
        <div className="px-4 pb-2 pt-4">
          <p className="text-copy font-medium text-ink">Link an app sign-up</p>
          <p className="meta mt-0.5">
            If {first} signed up in the app as a separate record, pick it here to fold it into this
            chart. Their phone, messages, tasks and health data move; the other record is removed.
          </p>
        </div>
        {candidates.isLoading && <p className="meta px-4 pb-4" role="status">Looking…</p>}
        {candidates.data && candidates.data.candidates.length === 0 && (
          <p className="px-4 pb-4 text-copy text-secondary">
            No other record has signed in on the app or has a phone yet.
          </p>
        )}
        {candidates.data && candidates.data.candidates.length > 0 && (
          <ListGroup
            embedded
            inset="none"
            aria-label="Records that can be linked"
            className="max-h-[min(360px,60vh)] overflow-y-auto pb-1"
          >
            {candidates.data.candidates.slice(0, 8).map((c) => (
              <ListRow
                key={c.patient_id}
                compact
                title={
                  <>
                    {c.name}{' '}
                    <span className="font-mono text-label font-normal text-secondary">{c.patient_id}</span>
                  </>
                }
                subtitleLines={3}
                subtitle={
                  <>
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
                    {c.phone_match && <span className="font-medium text-risk-low-ink"> · same number</span>}
                    {c.name_match && !c.phone_match && (
                      <span className="font-medium text-brand-ink"> · name matches</span>
                    )}
                    {c.observations > 0 && <> · {c.observations} readings</>}
                    {c.checkins > 0 && <> · {c.checkins} check-ins</>}
                  </>
                }
                meta={
                  c.refusal ? (
                    <span className="font-medium text-risk-high-ink">Cannot link: {c.refusal}</span>
                  ) : undefined
                }
                trailing={
                  <button
                    type="button"
                    className="btn-tinted btn-sm"
                    disabled={link.isPending || Boolean(c.refusal)}
                    title={c.refusal ?? `Fold ${c.name} into this chart`}
                    aria-label={`Link ${c.name}`}
                    onClick={() => doLink(c)}
                  >
                    <Link2 aria-hidden /> Link
                  </button>
                }
              />
            ))}
          </ListGroup>
        )}
      </Popover>
    </div>
  )
}
