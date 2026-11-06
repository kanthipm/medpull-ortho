package com.medpull.recovery.core

import android.content.Context
import android.os.Build
import com.medpull.recovery.BuildConfig

/** Where the app talks to, and how it names itself to the server. */
class AppConfig(context: Context) {
    private val prefs = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)

    /** The Profile screen's override wins, else the build's default. */
    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, null)?.takeIf { it.isNotBlank() } ?: BuildConfig.API_BASE_URL
        set(value) {
            prefs.edit().putString(KEY_BASE_URL, value.trim().trimEnd('/').ifBlank { null }).apply()
        }

    val defaultBaseUrl: String get() = BuildConfig.API_BASE_URL
    val scheme: String get() = BuildConfig.DEEP_LINK_SCHEME
    val appVersion: String get() = BuildConfig.VERSION_NAME

    companion object {
        private const val KEY_BASE_URL = "api_base_url"

        /** "Pixel 9 · Android 15": what the console shows as "enrolled on". */
        val deviceName: String
            get() = "${Build.MANUFACTURER.replaceFirstChar { it.uppercase() }} ${Build.MODEL} · Android ${Build.VERSION.RELEASE}"
    }
}
