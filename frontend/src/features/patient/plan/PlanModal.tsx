import type { ComponentProps } from 'react'
import Modal from '../../../components/Modal'

/** DEPRECATED shim (R16). The shared `Modal` now has the size and footer
 *  slots this file used to add, so PlanModal is only a default-export wrapper
 *  kept for any caller that still imports it. The plan modals import `Modal`
 *  directly. Delete in Cleanup once a grep finds no importers. */
export default function PlanModal(props: ComponentProps<typeof Modal>) {
  return <Modal {...props} />
}
