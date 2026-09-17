import { Paperclip, Send, Sparkles } from 'lucide-react'
import { useId, useState } from 'react'
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
import Modal from '../../../components/Modal'
import SegmentedControl from '../../../components/SegmentedControl'
import { useToast } from '../../../components/Toast'
import { PendingAttachments } from '../ThreadAttachments'
import { useAttachmentPicker } from '../useAttachmentPicker'
import { numberWarning, resolvePlaceholders, templatize } from './planCopy'

const SOFT_LIMIT = 280
const TONES: { key: MessageTone; label: string }[] = [
  { key: 'warm', label: 'Warm' },
  { key: 'direct', label: 'Direct' },
]

/** Compose a message to the patient: pinned templates fill the box with the
 *  placeholders resolved, the AI drafts from an intent and tone, and the
 *  send goes through the thread's own endpoint (a text when the patient has
 *  a phone, the app thread otherwise).
 *
 *  App anatomy: gray template capsules (tinted when chosen, aria-pressed),
 *  the ask-style capsule field for the AI draft with a round sparkle button,
 *  the message box, and a pinned footer with a gray Attach and the filled
 *  Send. Secondary text is `text-secondary`, which the Modal scopes to
 *  --body (dark --muted on the overlay panel is 3.655:1; --body 4.955). */
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
  const files = useAttachmentPicker(patientId)

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
  const uid = useId()
  const intentId = `${uid}-intent`
  const textId = `${uid}-text`
  const toneId = `${uid}-tone`

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
    // A file can be the whole message, so words are not required — but a
    // send with neither is refused by the server, and here too.
    if (!body && files.ids.length === 0) return
    send.mutate({ text: body, attachment_ids: files.ids }, {
      onSuccess: (r) => {
        if (r.status === 'sent_sms')
          toast(
            files.ids.length
              // A file is never attached to the text: an MMS link is a
              // public URL, and this is a patient's own record.
              ? `Texted ${first} — the ${files.ids.length === 1 ? 'file is' : 'files are'} in the app`
              : `Texted ${first} — also in the app`,
            'success',
          )
        else if (r.status === 'stored_sms_failed')
          toast(
            // Carry the provider's reason: "the text didn't go through" sent
            // people looking for a fault in the app instead of the account.
            `Saved to ${first}'s app thread — text failed: ${r.detail || 'no reason given'}`,
            'warning',
          )
        else toast(`Saved to ${first}'s app thread — no phone on file to text`, 'info')
        if (saveAs && saveTitle.trim()) {
          createTemplate.mutate(
            { title: saveTitle.trim(), body: templatize(body, ctx), tone },
            { onError: () => toast('The message sent, but the template was not saved', 'warning') },
          )
        }
        files.reset()
        onSent?.(r)
        onClose()
      },
      onError: () => toast('Message could not be sent — try again', 'warning'),
    })
  }

  const footer = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <p className="meta min-w-0 flex-1 basis-56">
        {phone ? `Texts ${phone} and shows in the app.` : `No phone on file — ${first} sees it in the app.`}
        {files.ids.length > 0 && ` Files open in the app, never in the text.`}
      </p>
      <input {...files.inputProps} />
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          className="btn-gray"
          title="Attach a photo or file"
          disabled={files.busy}
          onClick={files.open}
        >
          <Paperclip aria-hidden size={16} />
          {files.busy ? 'Uploading…' : 'Attach'}
        </button>
        <button
          type="button"
          className="btn-filled"
          disabled={(!text.trim() && files.ids.length === 0) || send.isPending || files.busy}
          onClick={submit}
        >
          <Send aria-hidden size={16} />
          {send.isPending ? 'Sending…' : phone ? 'Send text' : 'Send to app'}
        </button>
      </div>
    </div>
  )

  return (
    <Modal size="lg" title={`Message ${first}`} onClose={onClose} footer={footer} initialFocus="textarea">
      <div className="space-y-5 pt-1">
        {pinned.length > 0 && (
          <section aria-labelledby={`${uid}-templates`}>
            <h3 id={`${uid}-templates`} className="mb-2 text-label font-medium tracking-label text-secondary">
              Templates
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {pinned.map((t) => {
                const on = templateId === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      setText(resolvePlaceholders(t.body, ctx))
                      setTemplateId(t.id)
                    }}
                    aria-pressed={on}
                    title={t.body}
                    className={`${on ? 'btn-tinted' : 'btn-gray'} btn-sm`}
                  >
                    {t.title}
                  </button>
                )
              })}
            </div>
          </section>
        )}

        {/* The ask field: the app's capsule with a sparkle at the left and a
            round draft button at the right; the tone sits under it. */}
        <section aria-label="Draft with AI">
          <form
            className="relative"
            onSubmit={(e) => {
              e.preventDefault()
              if (!draft.isPending) runDraft()
            }}
          >
            <label htmlFor={intentId} className="sr-only">
              What should the message say?
            </label>
            <Sparkles
              aria-hidden
              size={18}
              className={`pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-cat-teal-ink ${
                draft.isPending ? 'motion-safe:animate-pulse' : ''
              }`}
            />
            <input
              id={intentId}
              className="field field-pill"
              placeholder="Ask AI to draft, e.g. check on swelling and sleep"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
            />
            {/* Wrapped: the press scale sets `transform`, which would undo a
                translate on the button itself. */}
            <span className="absolute right-2 top-1/2 flex -translate-y-1/2">
              <button
                type="submit"
                className="btn-send"
                disabled={draft.isPending}
                aria-label={draft.isPending ? 'Drafting…' : 'Draft with AI'}
                title="Draft with AI — the words land in the box below for review"
              >
                <Sparkles aria-hidden size={16} className={draft.isPending ? 'motion-safe:animate-spin' : undefined} />
              </button>
            </span>
          </form>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 px-1">
            <span id={toneId} className="text-label font-medium tracking-label text-secondary">
              Tone
            </span>
            <SegmentedControl<MessageTone>
              options={TONES}
              value={tone}
              onChange={setTone}
              size="sm"
              role="radiogroup"
              aria-labelledby={toneId}
              className="flex-none"
            />
            {provider && <AIAttribution kind="message draft" provider={provider} className="ml-auto" />}
          </div>
        </section>

        <section>
          <div className="mb-1.5 flex items-baseline justify-between px-1">
            <label htmlFor={textId} className="text-label font-medium tracking-label text-secondary">
              Message
            </label>
            <span
              aria-live="polite"
              className={`text-label tabular-nums ${over ? 'font-medium text-risk-med-ink' : 'text-secondary'}`}
            >
              {text.length}/{SOFT_LIMIT}
            </span>
          </div>
          <textarea
            id={textId}
            rows={5}
            className={`field resize-y rounded-surface px-4 py-3 text-copy-lg ${
              draft.isPending ? 'shimmer text-transparent' : ''
            }`}
            placeholder={`e.g. Hi ${first} — how did last night go? Reply here or in the app.`}
            value={text}
            disabled={draft.isPending}
            onChange={(e) => setText(e.target.value)}
            onDrop={files.drop}
            onDragOver={(e) => e.preventDefault()}
          />
          <PendingAttachments items={files.pending} onRemove={files.remove} busy={files.busy} />
          {warn && <p className="mt-1.5 px-1 text-label font-medium text-risk-med-ink">{warn}</p>}
          {over && !warn && (
            <p className="meta mt-1.5 px-1">
              Long texts split into several messages — shorter reads better on a phone.
            </p>
          )}
        </section>

        <section className="flex flex-wrap items-center gap-3 px-1">
          <label className="inline-flex min-h-9 cursor-pointer items-center gap-2 text-copy text-ink">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
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

        <p className="meta px-1">
          AI drafts are editable — nothing sends without your review. Keep it number-free: the
          patient never sees scores or percentages.
        </p>
      </div>
    </Modal>
  )
}
