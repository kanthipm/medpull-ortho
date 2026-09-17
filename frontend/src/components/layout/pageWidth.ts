/** Content width per page (R3). The sky window, the ambient echo and the bar
 *  background stay full-bleed; the content column, the bar's inner row and
 *  the sky window's frame all use the page's own cap.
 *    worklist  1080px   ('/')
 *    patient   1240px   ('/patients/…')
 *    settings   960px   ('/settings…', '/integrations')
 *    wide      --container-max (any other route)
 *  Kept out of AppShell.tsx so that file exports components only. */
export type PageWidth = 'worklist' | 'patient' | 'settings' | 'wide'

export function pageWidthFor(pathname: string): PageWidth {
  if (pathname === '/') return 'worklist'
  if (pathname.startsWith('/patients/')) return 'patient'
  if (pathname.startsWith('/settings') || pathname.startsWith('/integrations')) return 'settings'
  return 'wide'
}

export const PAGE_CLASS: Record<PageWidth, string> = {
  worklist: 'page page-worklist',
  patient: 'page page-patient',
  settings: 'page page-settings',
  wide: 'page',
}
