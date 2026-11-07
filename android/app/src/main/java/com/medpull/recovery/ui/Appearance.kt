package com.medpull.recovery.ui

import android.content.Context
import com.medpull.recovery.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** Light, dark or the phone's setting. Light is the default, as on the iPhone. */
enum class AppearanceMode(val labelRes: Int) { LIGHT(R.string.appearance_light), DARK(R.string.appearance_dark), SYSTEM(R.string.appearance_system) }

class Appearance(context: Context) {
    private val prefs = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)
    private val _mode = MutableStateFlow(
        prefs.getString(KEY, null)?.let { v -> AppearanceMode.entries.firstOrNull { it.name == v } } ?: AppearanceMode.LIGHT
    )
    val mode: StateFlow<AppearanceMode> = _mode

    fun set(mode: AppearanceMode) {
        _mode.value = mode
        prefs.edit().putString(KEY, mode.name).apply()
    }

    companion object { private const val KEY = "appearance" }
}
