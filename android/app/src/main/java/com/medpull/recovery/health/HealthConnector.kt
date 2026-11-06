package com.medpull.recovery.health

import android.app.Activity
import android.content.Context
import com.medpull.recovery.core.AppModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

sealed class HealthConnectState {
    data object Idle : HealthConnectState()
    data object Connecting : HealthConnectState()
    data class Connected(val syncLine: String? = null) : HealthConnectState()
    data object Unavailable : HealthConnectState()
    data class Failed(val message: String) : HealthConnectState()
}

/**
 * Health Connect through Junction's Android SDK. Placeholder until the SDK
 * batch: the shape the screens bind to is final, the calls land next.
 */
class HealthConnector(private val context: Context) {
    private val _state = MutableStateFlow<HealthConnectState>(HealthConnectState.Idle)
    val state: StateFlow<HealthConnectState> = _state

    fun restore() {}

    suspend fun connect(activity: Activity, app: AppModel): Boolean {
        _state.value = HealthConnectState.Failed("Health Connect linking lands in the next build.")
        return false
    }

    suspend fun syncNow() {}
    suspend fun disconnect() { _state.value = HealthConnectState.Idle }
}
