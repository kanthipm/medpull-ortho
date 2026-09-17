import { Bell, Mail, MessageSquare, Moon, PanelTop } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useNotificationPreferences, useUpdateNotificationPreferences } from '../../api/queries'
import EmptyState from '../../components/EmptyState'
import { ListGroup } from '../../components/ListRow'
import { SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useGlass, useTheme } from '../../lib/theme'
import SettingsNav from './SettingsNav'
import { GroupFooter, GroupHeader, SettingsHeading, SwitchRow } from './Switch'

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

/** Rows with a 40px tile: 16 + 40 + 12. */
const TILE_LG_INSET = 68

/** `/settings/notifications` — the General settings page: alert channels
 *  and appearance, as iOS inset-grouped lists (the page is capped at 960px
 *  by AppShell). */
export default function NotificationSettingsPage() {
  const header = (
    <div className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
      <SettingsNav className="mb-6" />
      <SettingsHeading title="General">
        How the care team is alerted, and how the console looks on this device.
      </SettingsHeading>
    </div>
  )

  return (
    <div className="pb-10">
      {header}
      <AlertChannels />
      <Appearance />
    </div>
  )
}

function AlertChannels() {
  const { data: prefs, isLoading, isError } = useNotificationPreferences()
  const update = useUpdateNotificationPreferences()

  return (
    <section
      aria-labelledby="alert-channels"
      className="rise mt-8"
      style={{ '--rise-delay': '60ms' } as CSSProperties}
    >
      <GroupHeader id="alert-channels">Alert channels</GroupHeader>
      {isLoading ? (
        <SkeletonCard rows={3} />
      ) : isError || !prefs ? (
        <EmptyState title="Alert settings couldn't be loaded." icon={<Bell />}>
          Refresh the page to try again.
        </EmptyState>
      ) : (
        <ListGroup inset={TILE_LG_INSET} aria-labelledby="alert-channels">
          {prefs.map((pref) => {
            const meta = CHANNEL_META[pref.channel] ?? {
              label: pref.channel,
              description: '',
              icon: Bell,
            }
            const Icon = meta.icon
            return (
              <SwitchRow
                key={pref.channel}
                id={`channel-${pref.channel}`}
                leading={<Tile size="lg" family="blue" icon={<Icon />} />}
                title={meta.label}
                badge={
                  !pref.available && (
                    <span className="chip bg-risk-missing-tint text-risk-missing-ink">Coming soon</span>
                  )
                }
                detail={meta.description}
                checked={pref.enabled && pref.available}
                disabled={!pref.available}
                busy={update.isPending}
                onChange={(next) =>
                  update.mutate([
                    { channel: pref.channel, enabled: next, min_priority: pref.min_priority },
                  ])
                }
              />
            )
          })}
        </ListGroup>
      )}
      <GroupFooter>
        Alerts include the patient, the new priority and the most important reason, with a link
        straight to their record.
      </GroupFooter>
    </section>
  )
}

/** R18 — the glass kill switch, plus dark appearance. Both are per-device
 *  (localStorage), not workspace settings. */
function Appearance() {
  const { theme, setTheme } = useTheme()
  const { glass, setGlass, systemReducedTransparency } = useGlass()

  return (
    <section
      aria-labelledby="appearance"
      className="rise mt-8"
      style={{ '--rise-delay': '100ms' } as CSSProperties}
    >
      <GroupHeader id="appearance">Appearance</GroupHeader>
      <ListGroup inset={TILE_LG_INSET} aria-labelledby="appearance">
        <SwitchRow
          id="appearance-dark"
          leading={<Tile size="lg" family="indigo" icon={<Moon />} />}
          title="Dark appearance"
          detail="Light text on dark surfaces. Every colour pair is checked in both."
          checked={theme === 'dark'}
          onChange={(on) => setTheme(on ? 'dark' : 'light')}
        />
        <SwitchRow
          id="appearance-glass"
          leading={<Tile size="lg" family="blue" icon={<PanelTop />} />}
          title="Translucent app bar"
          detail={
            systemReducedTransparency
              ? "Your system's Reduce transparency setting keeps the bar solid."
              : 'Frosts the top bar as the page scrolls under it. Turn off for a solid bar.'
          }
          checked={glass === 'on' && !systemReducedTransparency}
          disabled={systemReducedTransparency}
          onChange={(on) => setGlass(on ? 'on' : 'off')}
        />
      </ListGroup>
      <GroupFooter>These choices are saved on this device only.</GroupFooter>
    </section>
  )
}
