import { Eye, TrendingUp } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/personal/:memberId/trends` — a demo member's trends, read-only. The
 *  page head is in place; the charts arrive with the Personal stream
 *  (docs/dev/showcase.md, "Personal"). */
export default function PersonalTrendsPage() {
  const { memberId = '' } = useParams()
  const member = useWorkspaces().data?.members.find((m) => m.id === memberId)
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<TrendingUp />}
        title="Trends"
        badge={member && <span className="badge-ring">{member.name}</span>}
      >
        {member ? `${member.name}’s` : 'A member’s'} last thirteen weeks will be here: sleep and
        recovery, training load and form.
      </SettingsHero>

      <EmptyState className="rise mt-8" icon={<Eye />} family="indigo" title="A member’s own space, read-only">
        The console shows a demo member’s space exactly as the app does. Nothing in it can be
        edited from here.
      </EmptyState>
    </div>
  )
}
