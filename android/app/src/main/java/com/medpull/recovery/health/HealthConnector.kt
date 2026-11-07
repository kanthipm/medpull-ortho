package com.medpull.recovery.health

import android.content.Context
import android.util.Log
import androidx.activity.result.contract.ActivityResultContract
import com.medpull.recovery.R
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.SessionStore
import com.medpull.recovery.core.junctionSession
import io.tryvital.client.AuthenticateRequest
import io.tryvital.client.VitalClient
import io.tryvital.vitalhealthconnect.VitalHealthConnectManager
import io.tryvital.vitalhealthconnect.model.PermissionOutcome
import io.tryvital.vitalhealthcore.model.ConnectionPolicy
import io.tryvital.vitalhealthcore.model.ProviderAvailability
import io.tryvital.vitalhealthcore.model.SyncStatus
import io.tryvital.vitalhealthcore.model.VitalResource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class HealthConnectState {
    data object Idle : HealthConnectState()
    data object Connecting : HealthConnectState()
    data class Connected(val syncLine: String? = null) : HealthConnectState()
    data object Unavailable : HealthConnectState()
    data class Failed(val message: String) : HealthConnectState()
}

/**
 * Health Connect through Junction's Android SDK, the mirror of the iPhone's
 * HealthConnector: the backend mints a sign-in token for the patient's
 * Junction user (the team key never ships), the SDK signs in once per
 * installation, one permission sheet covers every resource the engine
 * reads, and the SDK syncs on app start and on request. Apple's gait types
 * have no Health Connect equivalent, so nothing is posted to the gait route.
 */
class HealthConnector(private val context: Context, private val session: SessionStore) {
    private val _state = MutableStateFlow<HealthConnectState>(HealthConnectState.Idle)
    val state: StateFlow<HealthConnectState> = _state
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var statusJob: Job? = null

    private val manager: VitalHealthConnectManager by lazy { VitalHealthConnectManager.getOrCreate(context) }

    /** Everything the engine reads that Health Connect can hold. */
    val resources: Set<VitalResource> = setOf(
        VitalResource.Profile, VitalResource.Body, VitalResource.Activity, VitalResource.Sleep, VitalResource.Workout,
        VitalResource.HeartRate, VitalResource.HeartRateVariability, VitalResource.BloodOxygen, VitalResource.RespiratoryRate,
        VitalResource.Temperature, VitalResource.BloodPressure, VitalResource.Steps, VitalResource.DistanceWalkingRunning,
        VitalResource.FloorsClimbed, VitalResource.ActiveEnergyBurned, VitalResource.Vo2Max,
    )

    val isSignedIn: Boolean get() = VitalClient.Status.SignedIn in VitalClient.status

    /** The SDK is signed in as the patient this session belongs to, not a previous one. */
    private val signedInAsCurrentPatient: Boolean
        get() {
            val id = session.patientId ?: return false
            return isSignedIn && VitalClient.identifiedExternalUser?.startsWith("medpull:$id:") == true
        }
    val isConnected: Boolean get() = _state.value is HealthConnectState.Connected

    fun availability(): ProviderAvailability = VitalHealthConnectManager.isAvailable(context)

    /** The permission sheet, launched through the Activity Result API by the screen. */
    fun permissionContract(): ActivityResultContract<Unit, Deferred<PermissionOutcome>> =
        manager.createPermissionRequestContract(resources, emptySet())

    /** On launch: reflect an existing sign-in for this patient without asking again. */
    fun restore() {
        if (signedInAsCurrentPatient) {
            _state.value = HealthConnectState.Connected()
            observeStatus()
        }
    }

    /** Step one of connecting: sign the SDK in with a token from our backend. */
    suspend fun signIn(app: AppModel): Boolean {
        val avail = availability()
        if (avail != ProviderAvailability.Installed) {
            _state.value = when (avail) {
                ProviderAvailability.NotInstalled -> HealthConnectState.Failed(context.getString(R.string.hc_install))
                ProviderAvailability.OnboardingIncomplete -> HealthConnectState.Failed(context.getString(R.string.hc_open_once))
                else -> HealthConnectState.Unavailable
            }
            return false
        }
        _state.value = HealthConnectState.Connecting
        return try {
            // The identity names the patient AND their Junction user, as on the
            // iPhone: the SDK skips re-authentication when the id is unchanged
            // and signs in afresh when it is, so a second patient on this phone
            // (or a chart whose Junction account was replaced) never pushes into
            // the old account.
            val patientId = app.current.me?.patient?.id ?: session.patientId
                ?: throw IllegalStateException(context.getString(R.string.hc_sign_in_first))
            val junction = app.api.junctionSession()
            VitalClient.identifyExternalUser(context, "medpull:$patientId:${junction.userId}") {
                AuthenticateRequest.SignInToken(junction.signInToken)
            }
            manager.configureHealthConnectClient(false, true, 90, null, ConnectionPolicy.AutoConnect)
            true
        } catch (e: Exception) {
            Log.w("HealthConnector", "sign-in failed", e)
            _state.value = HealthConnectState.Failed(e.message ?: context.getString(R.string.hc_connect_failed))
            false
        }
    }

    /** Step two: what the permission sheet came back with. */
    fun onPermissions(outcome: PermissionOutcome) {
        when (outcome) {
            is PermissionOutcome.Success, is PermissionOutcome.NotPrompted -> {
                _state.value = HealthConnectState.Connected(context.getString(R.string.hc_connected_syncing_now))
                observeStatus()
                scope.launch { syncNow() }
            }
            is PermissionOutcome.Cancelled -> _state.value = HealthConnectState.Failed(context.getString(R.string.hc_permissions_denied))
            is PermissionOutcome.HealthConnectUnavailable -> _state.value = HealthConnectState.Unavailable
            else -> _state.value = HealthConnectState.Failed(context.getString(R.string.hc_refused))
        }
    }

    suspend fun syncNow() {
        try { manager.syncData(resources) } catch (e: Exception) { Log.w("HealthConnector", "sync failed", e) }
    }

    suspend fun disconnect() {
        statusJob?.cancel(); statusJob = null
        try { if (isSignedIn) VitalClient.getOrCreate(context).signOut() } catch (e: Exception) { Log.w("HealthConnector", "sign-out failed", e) }
        _state.value = HealthConnectState.Idle
    }

    private fun observeStatus() {
        statusJob?.cancel()
        statusJob = scope.launch {
            manager.status.collect { s ->
                val line = when (s) {
                    is SyncStatus.ResourceSyncing -> context.getString(R.string.hc_syncing)
                    is SyncStatus.ResourceSyncingComplete, is SyncStatus.SyncingCompleted -> context.getString(R.string.hc_synced_just_now)
                    is SyncStatus.ResourceNothingToSync -> context.getString(R.string.hc_up_to_date)
                    is SyncStatus.ResourceSyncFailed -> context.getString(R.string.hc_sync_failed)
                    else -> null
                }
                if (_state.value is HealthConnectState.Connected) _state.value = HealthConnectState.Connected(line)
            }
        }
    }
}
