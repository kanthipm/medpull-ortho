import { Bell, Mail, MessageSquare } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useNotificationPreferences, useUpdateNotificationPreferences } from '../../api/queries'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'

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
      <h1 className="text-[26px] font-semibold tracking-[-.03em] text-ink">Notifications</h1>
      <p className="mt-1 text-[13px] font-medium text-muted">
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
              <li key={pref.channel} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
                <span
                  className={`grid h-8 w-8 shrink-0 place-items-center rounded-btn ${
                    on ? 'bg-brand-tint text-brand' : 'bg-soft text-faint'
                  }`}
                >
                  <Icon size={15} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-[13.5px] font-semibold tracking-[-.01em] text-ink">
                    {meta.label}
                    {!pref.available && (
                      <span className="chip bg-risk-missing-bg text-risk-missing">Coming soon</span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[12px] font-medium text-muted">
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
                  className={`relative h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand ${
                    on ? 'bg-brand' : 'bg-line'
                  } ${!pref.available ? 'cursor-not-allowed opacity-50' : ''}`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-[#fff] shadow-segment transition-all duration-150 ${
                      on ? 'left-[18px]' : 'left-0.5'
                    }`}
                  />
                </button>
              </li>
            )
          })}
        </ul>
      </SectionCard>

      <p className="mt-4 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
        Alerts include the patient, the new priority, and the most important reason — with a
        link straight to their record.
      </p>
    </div>
  )
}
