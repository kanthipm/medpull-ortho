package com.medpull.recovery.core

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * The patient's session tokens, in Keystore-backed storage: the current one
 * plus one per space the person holds (a clinic chart and a paired personal
 * space), so switching back is instant, as on the iPhone.
 */
class SessionStore(context: Context) {
    private val prefs: SharedPreferences = run {
        val key = MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            context, "medpull.session", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    @Volatile var token: String? = prefs.getString(KEY_TOKEN, null)
        private set

    fun set(token: String, patientId: String? = null) {
        this.token = token
        prefs.edit().putString(KEY_TOKEN, token).apply()
        if (patientId != null) prefs.edit().putString(KEY_SPACE + patientId, token).apply()
    }

    fun tokenFor(patientId: String): String? = prefs.getString(KEY_SPACE + patientId, null)

    fun clear() {
        token = null
        prefs.edit().clear().apply()
    }

    companion object {
        private const val KEY_TOKEN = "session_token"
        private const val KEY_SPACE = "session_token:"
    }
}
