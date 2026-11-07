package com.medpull.recovery

import android.content.Context
import com.medpull.recovery.core.ApiClient
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.SessionStore
import com.medpull.recovery.core.Strings
import com.medpull.recovery.health.HealthConnector
import com.medpull.recovery.ui.Appearance

/** The app's objects, built once. No DI framework: this is the whole graph. */
class AppGraph(context: Context) {
    val config = AppConfig(context)
    val session = SessionStore(context)
    val strings = Strings { id, args -> context.getString(id, *args) }
    val api = ApiClient(config, session, strings)
    val health = HealthConnector(context, session)
    val app = AppModel(api, session, config, health, strings)
    val appearance = Appearance(context)
}
