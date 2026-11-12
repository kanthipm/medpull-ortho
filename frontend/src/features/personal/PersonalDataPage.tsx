import { Database, Eye } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/personal/:memberId/data` — the data under a demo member's space,
 *  read-only. The page head is in place; the panels arrive with the
 *  Personal stream (docs/dev/showcase.md, "Personal"). */
export default function PersonalDataPage() {
  const { memberId = '' } = useParams()
  const member = useWorkspaces().data?.members.find((m) => m.id === memberId)
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<Database />}
        title="Data"
        badge={member && <span className="badge-ring">{member.name}</span>}
      >
        Everything under {member ? `${member.name}’s` : 'a member’s'} space will be here: each
        panel with its method and coverage, the raw signals and the logs.
      </SettingsHero>

      <EmptyState className="rise mt-8" icon={<Eye />} family="indigo" title="A member’s own space, read-only">
        The console shows a demo member’s space exactly as the app does. Nothing in it can be
        edited from here.
      </EmptyState>
    </div>
  )
}
