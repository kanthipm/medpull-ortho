import { Bell, Mail, MessageSquare } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useNotificationPreferences, useUpdateNotificationPreferences } from '../../api/queries'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'
import SettingsNav from './SettingsNav'

const CHANNEL_META: Record<string, { label: string; description: string; icon: typeof Bell }> = {
  in_app: {
    label: 'In-app',
    description: 'Shows in the notification bell when a patient reaches high priority.',
    icon: Bell,
  },
  sms: {
    label: 'Text message',
    description: 'Texts the assigned provider. Available once an SMS provider is connected.',
    icon: MessageSquare,
  },
  email: {
    label: 'Email',
    description: 'Emails the assigned provider. Available once an email provider is connected.',
    icon: Mail,
  },
}

export default function NotificationSettingsPage() {
  const { data: prefs, isLoading, isError } = useNotificationPreferences()
  const update = useUpdateNotificationPreferences()

  const header = (
    <div className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
      <SettingsNav className="mb-4" />
      <h1 className="text-title font-normal text-ink">Notifications</h1>
      <p className="mt-1.5 text-copy-lg text-muted">
        How the care team is alerted when a patient reaches high recovery priority.
      </p>
    </div>
  )

  if (isLoading)
    return (
      <div>
        {header}
        <div className="mt-6">
          <SkeletonCard lines={4} />
        </div>
      </div>
    )
  if (isError || !prefs) return <EmptyState title="Settings couldn't be loaded." />

  return (
    <div>
      {header}

      <SectionCard
        className="rise mt-6"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
        eyebrow={<span className="micro mb-1 block">Alert channels</span>}
      >
        <ul className="divide-y divide-line">
          {prefs.map((pref) => {
            const meta = CHANNEL_META[pref.channel] ?? {
              label: pref.channel,
              description: '',
              icon: Bell,
            }
            const Icon = meta.icon
            const on = pref.enabled && pref.available
            return (
              <li key={pref.channel} className="flex items-center gap-4 py-5 first:pt-0 last:pb-0">
                <span
                  className={`grid h-10 w-10 shrink-0 place-items-center rounded-control ${
                    on ? 'bg-brand-tint text-on-brand-tint' : 'bg-soft text-muted'
                  }`}
                >
                  <Icon size={18} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-seam text-copy-lg font-medium text-ink">
                    {meta.label}
                    {!pref.available && (
                      <span className="chip bg-risk-missing-tint text-risk-missing-ink">Coming soon</span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-copy text-muted">
                    {meta.description}
                  </span>
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  disabled={!pref.available || update.isPending}
                  onClick={() =>
                    update.mutate([
                      {
                        channel: pref.channel,
                        enabled: !pref.enabled,
                        min_priority: pref.min_priority,
                      },
                    ])
                  }
                  className={`relative h-7 w-12 shrink-0 cursor-pointer rounded-pill transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
                    !pref.available
                      ? 'cursor-not-allowed bg-disabled-fill'
                      : on
                        ? 'bg-brand'
                        : 'bg-line-strong'
                  }`}
                >
                  {/* `shadow-knob` is NOT elevation — it is the knob's
                      contact shadow, lifting it off its track. It has its own
                      token so dark mode gets its own value and an elevation
                      sweep cannot flatten the switch. */}
                  <span
                    className={`absolute top-0.5 h-6 w-6 rounded-pill shadow-knob transition-all duration-150 ${
                      !pref.available ? 'bg-disabled-ink' : 'bg-n-0'
                    } ${on ? 'left-[22px]' : 'left-0.5'}`}
                  />
                </button>
              </li>
            )
          })}
        </ul>
      </SectionCard>

      <p className="mt-snug border-t border-line pt-tight text-label text-muted">
        Alerts include the patient, the new priority, and the most important reason — with a
        link straight to their record.
      </p>
    </div>
  )
}
