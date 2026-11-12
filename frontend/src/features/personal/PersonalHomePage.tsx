import { UserRound } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { landingSubject } from '../../components/layout/workspaceRows'
import { SkeletonCard } from '../../components/Skeleton'
import { SettingsHero } from '../settings/Switch'

/** `/personal` — names no one, so it forwards to the member who was open
 *  last on this browser, else the first one the workspace menu lists.
 *
 *  Where there are none (the real app, or a demo that has not been filled)
 *  it says what the version is and that this deployment has nothing to show
 *  in it: the console lists generated demo members only, never a real
 *  member's space. */
export default function PersonalHomePage() {
  const { data, isError } = useWorkspaces()
  if (!data && !isError) {
    return (
      <div className="space-y-stack pb-4 pt-8" role="status" aria-label="Loading">
        <SkeletonCard lines={3} />
      </div>
    )
  }
  const member = data ? landingSubject(data, 'personal') : null
  if (member) return <Navigate to={`/personal/${encodeURIComponent(member)}`} replace />

  return (
    <div className="pb-10">
      <SettingsHero icon={<UserRound />} title="Personal">
        The version a member uses to read their own body: today’s verdict, their trends, and the
        data behind both.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<UserRound />}
        family="indigo"
        title="No members to show on this deployment"
      >
        The console opens demo members only, and there are none here. A real member’s space is
        theirs alone and is never listed.
      </EmptyState>
    </div>
  )
}
