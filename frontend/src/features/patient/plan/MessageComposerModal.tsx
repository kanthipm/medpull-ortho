import { Send, Sparkles } from 'lucide-react'
import { useState } from 'react'
import type { MessageTone } from '../../../api/plan'
import {
  firstNameOf,
  useCreateMessageTemplate,
  useDraftPatientMessage,
  useMessageTemplates,
} from '../../../api/plan'
import { useMessagePatient } from '../../../api/queries'
import type { MessagePatientResult } from '../../../api/types'
import AIAttribution from '../../../components/AIAttribution'
import SegmentedControl from '../../../components/SegmentedControl'
import { useToast } from '../../../components/Toast'
import PlanModal from './PlanModal'
import { numberWarning, resolvePlaceholders, templatize } from './planCopy'

const SOFT_LIMIT = 280
const TONES: { key: MessageTone; label: string }[] = [
  { key: 'warm', label: 'Warm' },
  { key: 'direct', label: 'Direct' },
]

/** Compose a message to the patient: pinned templates fill the box with the
 *  placeholders resolved, the AI drafts from an intent and tone, and the
 *  send goes through the thread's own endpoint (a text when the patient has
 *  a phone, the app thread otherwise). */
export default function MessageComposerModal({
  patientId,
  patientName,
  surgeon,
  phone,
  prefill,
  onClose,
  onSent,
}: {
  patientId: string
  patientName: string
  surgeon?: string | null
  phone: string | null
  /** Starting text — a next step hands its draft in. */
  prefill?: string
  onClose: () => void
  /** Called with the thread's result so a next step can log completion. */
  onSent?: (result: MessagePatientResult) => void
}) {
  const toast = useToast()
  const first = firstNameOf(patientName)
  const ctx = { first, surgeon }
  const templates = useMessageTemplates()
  const draft = useDraftPatientMessage(patientId)
  const send = useMessagePatient(patientId)
  const createTemplate = useCreateMessageTemplate()

  const [text, setText] = useState(prefill ?? '')
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [intent, setIntent] = useState('')
  const [tone, setTone] = useState<MessageTone>('warm')
  const [provider, setProvider] = useState<string | null>(null)
  const [saveAs, setSaveAs] = useState(false)
  const [saveTitle, setSaveTitle] = useState('')

  const pinned = (templates.data?.templates ?? []).filter((t) => t.pinned && !t.archived)
  const warn = numberWarning(text)
  const over = text.length > SOFT_LIMIT

  const runDraft = () =>
    draft.mutate(
      { intent: intent.trim() || undefined, tone, template_id: templateId ?? undefined },
      {
        onSuccess: (r) => {
          setText(r.message)
          setProvider(r.provider)
        },
        onError: () => toast('Drafting failed — try again', 'warning'),
      },
    )

  const submit = () => {
    const body = text.trim()
    if (!body) return
    send.mutate(body, {
      onSuccess: (r) => {
        if (r.status === 'sent_sms') toast(`Texted ${first} — also in the app`, 'success')
        else if (r.status === 'stored_sms_failed')
          toast(`Saved to ${first}'s app thread — the text didn't go through`, 'warning')
        else toast(`Saved to ${first}'s app thread — no phone on file to text`, 'info')
        if (saveAs && saveTitle.trim()) {
          createTemplate.mutate(
            { title: saveTitle.trim(), body: templatize(body, ctx), tone },
            { onError: () => toast('The message sent, but the template was not saved', 'warning') },
          )
        }
        onSent?.(r)
        onClose()
      },
      onError: () => toast('Message could not be sent — try again', 'warning'),
    })
  }

  const footer = (
    <div className="flex flex-wrap items-center gap-3">
      <p className="text-[11px] font-medium text-faint">
        {phone ? `Texts ${phone} and shows in the app.` : `No phone on file — ${first} sees it in the app.`}
      </p>
      <button
        type="button"
        className="btn-primary sm:ml-auto sm:w-auto"
        disabled={!text.trim() || send.isPending}
        onClick={submit}
      >
        <Send size={13} />
        {send.isPending ? 'Sending…' : phone ? 'Send text' : 'Send to app'}
      </button>
    </div>
  )

  return (
    <PlanModal size="lg" title={`Message ${first}`} onClose={onClose} footer={footer}>
      <div className="space-y-4">
        {pinned.length > 0 && (
          <section>
            <p className="micro mb-1.5">Templates</p>
            <div className="flex flex-wrap gap-1.5">
              {pinned.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    setText(resolvePlaceholders(t.body, ctx))
                    setTemplateId(t.id)
                  }}
                  aria-pressed={templateId === t.id}
                  title={t.body}
                  className={`chip cursor-pointer border transition-colors duration-150 ${
                    templateId === t.id
                      ? 'border-brand/35 bg-brand-tint text-brand'
                      : 'border-line bg-panel text-body hover:border-brand/35 hover:bg-brand-tint hover:text-brand'
                  }`}
                >
                  {t.title}
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-row border border-line bg-soft/40 p-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="field min-w-[160px] flex-1"
              placeholder="What should it say? e.g. ask about swelling and sleep"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              aria-label="Message intent"
            />
            <SegmentedControl<MessageTone>
              options={TONES}
              value={tone}
              onChange={setTone}
              aria-label="Tone"
              className="flex-none"
            />
            <button type="button" className="qa-btn" disabled={draft.isPending} onClick={runDraft}>
              <Sparkles size={13} className={`text-brand ${draft.isPending ? 'animate-spin' : ''}`} />
              {draft.isPending ? 'Drafting…' : 'Draft with AI'}
            </button>
          </div>
          {provider && (
            <div className="mt-2">
              <AIAttribution kind="message draft" provider={provider} />
            </div>
          )}
        </section>

        <section>
          <div className="mb-1 flex items-baseline justify-between">
            <label htmlFor="composer-text" className="micro block">
              Message
            </label>
            <span
              className={`font-mono text-[11px] tabular-nums ${over ? 'text-risk-med' : 'text-faint'}`}
            >
              {text.length}/{SOFT_LIMIT}
            </span>
          </div>
          <textarea
            id="composer-text"
            rows={5}
            className={`field ${draft.isPending ? 'shimmer text-transparent' : ''}`}
            placeholder={`e.g. Hi ${first} — how did last night go? Reply here or in the app.`}
            value={text}
            disabled={draft.isPending}
            onChange={(e) => setText(e.target.value)}
          />
          {warn && <p className="mt-1 text-[11px] font-medium leading-snug text-risk-med">{warn}</p>}
          {over && !warn && (
            <p className="mt-1 text-[11px] font-medium text-faint">
              Long texts split into several messages — shorter reads better on a phone.
            </p>
          )}
        </section>

        <section className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 text-[12.5px] font-medium text-body">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-[rgb(var(--brand))]"
              checked={saveAs}
              onChange={(e) => setSaveAs(e.target.checked)}
            />
            Save as template
          </label>
          {saveAs && (
            <input
              className="field min-w-[180px] flex-1"
              placeholder="Template title"
              value={saveTitle}
              onChange={(e) => setSaveTitle(e.target.value)}
              aria-label="Template title"
            />
          )}
        </section>

        <p className="text-[11px] font-medium leading-[1.5] text-faint">
          AI drafts are editable — nothing sends without your review. Keep it number-free: the
          patient never sees scores or percentages.
        </p>
      </div>
    </PlanModal>
  )
}
