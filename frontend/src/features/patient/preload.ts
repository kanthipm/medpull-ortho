/** The patient page's chunk. `App.tsx` lazy-loads the page through this
 *  same import, so calling it anywhere else (a worklist row under the
 *  pointer, the idle preload after first paint) warms the chunk the browser
 *  will need next; a second call is a no-op on the module cache. Kept apart
 *  from App.tsx so the worklist does not import the app root. */
export const loadPatientDetailPage = () => import('./PatientDetailPage')
