import type { StaffMember } from '../../api/sports'
import Avatar from '../../components/Avatar'
import ListRow, { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'

/** Who is on the team's staff and whether the athlete sees them. */
export default function StaffCard({ staff }: { staff: StaffMember[] }) {
  return (
    <SectionCard flush title="Staff" aside={staff.length > 0 ? `${staff.length}` : undefined}>
      {staff.length === 0 ? (
        <p className="px-5 pb-5 text-copy text-secondary">No staff on this team yet.</p>
      ) : (
        <ListGroup embedded inset="avatar" aria-label="Team staff">
          {staff.map((s) => (
            <ListRow
              key={s.id}
              compact
              leading={<Avatar name={s.name} size="sm" />}
              title={s.name}
              subtitle={s.role_label}
              aside={s.athlete_facing ? 'Athlete-facing' : 'Staff only'}
            />
          ))}
        </ListGroup>
      )}
    </SectionCard>
  )
}
