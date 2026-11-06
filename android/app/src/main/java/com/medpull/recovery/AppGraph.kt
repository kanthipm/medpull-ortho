package com.medpull.recovery

import android.content.Context
import com.medpull.recovery.core.ApiClient
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.SessionStore
import com.medpull.recovery.health.HealthConnector

/** The app's objects, built once. No DI framework: this is the whole graph. */
class AppGraph(context: Context) {
    val config = AppConfig(context)
    val session = SessionStore(context)
    val api = ApiClient(config, session)
    val app = AppModel(api, session, config)
    val health = HealthConnector(context)
}
