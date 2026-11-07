package com.medpull.recovery.features.onboarding

import android.net.Uri
import com.medpull.recovery.R
import com.medpull.recovery.core.ApiClient
import com.medpull.recovery.core.ApiException
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.Candidate
import com.medpull.recovery.core.ConsentAcceptance
import com.medpull.recovery.core.ConsentDocument
import com.medpull.recovery.core.EnrollBody
import com.medpull.recovery.core.EnrollResponse
import com.medpull.recovery.core.Hospital
import com.medpull.recovery.core.JoinBody
import com.medpull.recovery.core.Procedure
import com.medpull.recovery.core.SearchBody
import com.medpull.recovery.core.Strings
import com.medpull.recovery.core.VerifyBody
import com.medpull.recovery.core.consentDocument
import com.medpull.recovery.core.enroll
import com.medpull.recovery.core.hospitals
import com.medpull.recovery.core.join
import com.medpull.recovery.core.procedures
import com.medpull.recovery.core.resendVerification
import com.medpull.recovery.core.search
import com.medpull.recovery.core.verificationStatus
import com.medpull.recovery.core.verify
import com.medpull.recovery.features.consent.agreed
import java.time.LocalDate
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

enum class Step { WELCOME, MODE, CONSENT, HOSPITAL, PATH, IDENTITY, JOIN, VERIFY, HEALTH, WALKS, WEARABLE, DONE, PERSONAL_SOON }
enum class Path { FIND_RECORD, JOIN_GENERAL, JOIN_AFTER_SURGERY }

data class OnboardingState(
    val hospitals: List<Hospital> = emptyList(), val hospital: Hospital? = null, val hospitalQuery: String = "",
    val path: Path = Path.FIND_RECORD,
    val name: String = "", val phone: String = "", val candidates: List<Candidate> = emptyList(),
    val selected: Candidate? = null, val searching: Boolean = false,
    val dateOfBirth: LocalDate? = null, val hadSurgery: Boolean = false, val procedures: List<Procedure> = emptyList(),
    val procedure: Procedure? = null, val surgeryDate: LocalDate = LocalDate.now().minusDays(7),
    val consent: ConsentDocument? = null, val consentScopes: Map<String, Boolean> = emptyMap(), val signature: String = "",
    val accepted: ConsentAcceptance? = null,
    val verificationId: Int? = null, val phoneMasked: String? = null, val code: String = "",
    // Text-first: the server could not text the code yet, because on Sendblue's free plan a
    // number has to text the line once before it can be reached. The verify step then asks
    // for that one text and polls; cleared the moment the code goes out.
    val textFirst: Boolean = false, val textTo: String? = null, val textBody: String? = null,
    val working: Boolean = false, val error: String? = null,
) {
    val canEnroll get() = selected != null && phoneDigits(phone).length >= 10 && hospital != null
    val canJoin get() = name.trim().length >= 2 && phoneDigits(phone).length >= 10 && hospital != null &&
        (!hadSurgery || procedure != null)
    val canAgree get() = consent?.agreed(consentScopes, signature) == true
}

fun phoneDigits(s: String) = s.filter { it.isDigit() }

/** The onboarding flow's state and calls, mirroring ios OnboardingModel.swift. */
class OnboardingModel(private val api: ApiClient, private val app: AppModel, private val config: AppConfig, private val strings: Strings) {
    val state = MutableStateFlow(OnboardingState())
    val s get() = state.value

    private suspend fun <T> guarded(block: suspend () -> T): T? {
        state.update { it.copy(working = true, error = null) }
        return try { block() } catch (e: ApiException) { state.update { it.copy(error = e.detail) }; null }
        catch (e: Exception) { state.update { it.copy(error = e.message ?: strings.get(R.string.error_generic)) }; null }
        finally { state.update { it.copy(working = false) } }
    }

    suspend fun loadHospitals() { guarded { val h = api.hospitals(); state.update { it.copy(hospitals = h) } } }
    suspend fun loadProcedures() { if (s.procedures.isEmpty()) guarded { val p = api.procedures(); state.update { it.copy(procedures = p) } } }
    suspend fun loadConsent() { if (s.consent == null) guarded {
        val doc = api.consentDocument()
        state.update { it.copy(consent = doc, consentScopes = doc.scopes.associate { sc -> sc.key to true }) }
    } }

    fun filteredHospitals(): List<Hospital> {
        val q = s.hospitalQuery.trim().lowercase()
        if (q.isEmpty()) return s.hospitals
        return s.hospitals.filter { listOf(it.name, it.system.orEmpty(), it.city).any { f -> f.lowercase().contains(q) } }
    }

    fun agree() {
        val doc = s.consent ?: return
        state.update { it.copy(accepted = ConsentAcceptance(doc.version, s.consentScopes, s.signature.trim())) }
    }

    /** Debounced by the screen; sends the phone only with ten digits. */
    suspend fun search() {
        val hospital = s.hospital ?: return
        val name = s.name.trim()
        if (name.length < 2) { state.update { it.copy(candidates = emptyList(), selected = null) }; return }
        state.update { it.copy(searching = true) }
        try {
            val phone = s.phone.trim().takeIf { phoneDigits(it).length >= 10 }
            val found = api.search(SearchBody(hospital.id, name, phone))
            state.update { it.copy(candidates = found, selected = if (found.size == 1) found[0] else it.selected?.takeIf { sel -> found.any { f -> f.patientId == sel.patientId } }) }
        } catch (e: Exception) {
            state.update { it.copy(error = (e as? ApiException)?.detail ?: e.message) }
        } finally { state.update { it.copy(searching = false) } }
    }

    suspend fun enroll(): Step? = guarded {
        val r = api.enroll(EnrollBody(s.selected!!.patientId, s.hospital!!.id, s.phone.trim(), s.accepted,
            AppConfig.deviceName, config.appVersion))
        handle(r)
    }

    suspend fun join(): Step? {
        state.update { it.copy(working = true, error = null) }
        return try {
            val r = api.join(JoinBody(
                s.hospital!!.id, s.name.trim(), s.phone.trim(), s.dateOfBirth?.toString(), s.hadSurgery,
                if (s.hadSurgery) s.procedure?.id else null, if (s.hadSurgery) s.surgeryDate.toString() else null,
                s.accepted, AppConfig.deviceName, config.appVersion,
            ))
            handle(r)
        } catch (e: ApiException) {
            if (e.status == 409) {
                state.update { it.copy(path = Path.FIND_RECORD, error = strings.get(R.string.onboarding_number_on_record)) }
                Step.IDENTITY
            } else { state.update { it.copy(error = e.detail) }; null }
        } catch (e: Exception) { state.update { it.copy(error = e.message) }; null }
        finally { state.update { it.copy(working = false) } }
    }

    suspend fun verify(): Step? = guarded {
        val r = api.verify(VerifyBody(s.verificationId!!, s.code.trim(), s.accepted, AppConfig.deviceName, config.appVersion))
        handle(r)
    }

    suspend fun resend(): Step? = if (s.path == Path.FIND_RECORD) enroll() else join()

    // --- text us first -------------------------------------------------------------------

    /** The sms: URI that opens Messages with the first text already written (Android takes ?body=). */
    fun textFirstUri(): String? {
        val to = s.textTo ?: return null
        return "sms:$to?body=${Uri.encode(s.textBody ?: strings.get(R.string.onboarding_default_text))}"
    }

    /** "I've sent it — send my code": the webhook may already have sent it when the text
     *  landed; if not, the server tries again now that the number is known to the provider. */
    suspend fun continueAfterText(): Step? = guarded {
        val id = s.verificationId ?: return@guarded null
        if (api.verificationStatus(id).codeIsOut) {
            state.update { it.copy(textFirst = false) }
            Step.VERIFY
        } else {
            val step = handle(api.resendVerification(id))
            if (s.textFirst) state.update { it.copy(error = strings.get(R.string.onboarding_text_not_yet)) }
            step
        }
    }

    /** Polled while the step waits: the code goes out the moment the text lands, and the
     *  field appears by itself. */
    suspend fun pollForCode() {
        val id = s.verificationId ?: return
        if (!s.textFirst) return
        try {
            if (api.verificationStatus(id).codeIsOut) state.update { it.copy(textFirst = false, error = null) }
        } catch (_: Exception) {
            // keep waiting; the next tick asks again
        }
    }

    private fun handle(r: EnrollResponse): Step = when (r.status) {
        "verification_required" -> {
            // codeSent false means the number has never texted MedPull and the server is
            // waiting on that text before it can send anything.
            state.update { it.copy(verificationId = r.verificationId, phoneMasked = r.phoneMasked, code = "",
                textFirst = (r.textFirst ?: false) && !(r.codeSent ?: true), textTo = r.textTo, textBody = r.textBody) }
            Step.VERIFY
        }
        "enrolled" -> {
            val token = r.sessionToken ?: throw ApiException(0, strings.get(R.string.error_no_session))
            val me = r.me ?: throw ApiException(0, strings.get(R.string.error_no_profile))
            app.adoptSession(token, me)
            Step.HEALTH
        }
        else -> throw ApiException(0, strings.get(R.string.onboarding_unexpected_status, r.status))
    }
}
