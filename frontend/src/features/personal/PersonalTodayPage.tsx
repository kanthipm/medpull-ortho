import { Eye, Sun } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/personal/:memberId` — a demo member's Today, read-only, as the member
 *  sees it in the app. The page head is in place; the day itself arrives
 *  with the Personal stream (docs/dev/showcase.md, "Personal"). */
export default function PersonalTodayPage() {
  const { memberId = '' } = useParams()
  const member = useWorkspaces().data?.members.find((m) => m.id === memberId)
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<Sun />}
        title="Today"
        badge={member && <span className="badge-ring">{member.name}</span>}
      >
        {member ? `${member.name}’s` : 'A member’s'} day will be here as they see it: the verdict,
        readiness, the plan, the brief, alerts and the coach.
      </SettingsHero>

      <EmptyState className="rise mt-8" icon={<Eye />} family="indigo" title="A member’s own space, read-only">
        The console shows a demo member’s space exactly as the app does. Nothing in it can be
        edited from here.
      </EmptyState>
    </div>
  )
}
