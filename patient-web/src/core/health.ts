/* Apple Health, on the web: it cannot connect here.
   HealthKit lives on the phone. The iPhone app (Core/HealthConnector.swift)
   authorises it in one sheet and the Vital SDK pushes the data; a browser
   has no access to Health at all. So the web app has no Health step or
   button: the Connections sheet reports what a phone connected and says
   where the connection is made. */

export const IPHONE_NEEDED =
  'Apple Health connects from the MedPull iPhone app. Install it on your iPhone, sign in to this same record, and your steps, sleep and heart data show up here on their own.'

export type HealthState = 'idle' | 'connecting' | 'connected' | 'unavailable' | { failed: string }

export class HealthConnector {
  state: HealthState = 'unavailable'
  syncLine = ''
  lastGaitUpload: string | null = null

  get isConnected(): boolean { return false }

  /** On launch the phone restores the SDK's session; there is none here. */
  restore(): void {}

  /** Never succeeds on the web: the Connections screen explains why. */
  async connect(): Promise<boolean> {
    this.state = { failed: IPHONE_NEEDED }
    return false
  }

  syncNow(): void {}

  async disconnect(): Promise<void> {
    this.state = 'unavailable'
    this.syncLine = ''
  }

  /** Apple's walking metrics only exist on the phone. */
  async uploadGait(): Promise<number> {
    this.lastGaitUpload = 'Walking data is sent by the MedPull iPhone app'
    return 0
  }
}
