package com.medpull.recovery.core

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/*
 * The wire types, mirroring ios/MedPull/Core/Models.swift and the backend's
 * openapi.json. Keys are snake_case on the wire (the client's naming
 * strategy converts); every vocabulary is a plain String so an unknown
 * server value never breaks decoding; timestamps stay Strings.
 */

// --- onboarding -------------------------------------------------------------------

@Serializable data class Hospital(val id: String, val name: String, val system: String? = null,
                                  val city: String = "", val state: String = "")
@Serializable data class HospitalsResponse(val hospitals: List<Hospital>)

@Serializable data class Candidate(
    val patientId: String, val displayName: String, val procedureDisplay: String = "",
    val surgeryMonth: String? = null, val confidence: String = "", val phoneMatch: Boolean = false,
    val hasPhoneOnFile: Boolean = false,
)
@Serializable data class CandidatesResponse(val candidates: List<Candidate>)

@Serializable data class Procedure(val id: String, val label: String)
@Serializable data class ProceduresResponse(val procedures: List<Procedure>)

@Serializable data class ConsentAcceptance(val version: String, val scopes: Map<String, Boolean>,
                                           val signature: String? = null)

@Serializable data class EnrollResponse(
    val status: String, val verificationId: Int? = null, val phoneMasked: String? = null,
    val expiresAt: String? = null, val verified: Boolean? = null, val sessionToken: String? = null,
    val me: Me? = null,
)

@Serializable data class ConsentScope(val key: String, val label: String, val detail: String = "",
                                      val required: Boolean = false)
@Serializable data class ConsentDocument(val kind: String = "beta", val version: String, val text: String,
                                         val textSha256: String = "", val scopes: List<ConsentScope> = emptyList(),
                                         val beta: Boolean = true)

// --- me ---------------------------------------------------------------------------

@Serializable data class CareTeamMember(val name: String, val role: String = "")

@Serializable data class PatientProfile(
    val id: String, val name: String = "", val firstName: String = "", val initials: String = "",
    val mode: String = "recovery", val accountKind: String = "clinic", val procedureDisplay: String = "",
    val surgeryDate: String? = null, val joinedDate: String? = null, val postopDay: Int? = null,
    val daysEnrolled: Int = 0, val carePathway: String? = null, val phoneMasked: String? = null,
    val email: String? = null, val hospital: Hospital? = null, val careTeam: List<CareTeamMember> = emptyList(),
) {
    val isRecovery get() = mode == "recovery"
    val isPersonal get() = mode == "personal" || accountKind == "personal"
}

@Serializable data class Trajectory(val state: String = "unknown", val pct: Double? = null)
@Serializable data class Recovery(
    val level: String = "", val label: String = "", val blurb: String = "", val trajectory: Trajectory = Trajectory(),
    val daysWithData: Int? = null, val daysUntilFullPicture: Int? = null, val computedAt: String? = null,
)

@Serializable data class AppleHealthStatus(val connected: Boolean = false, val lastSyncAt: String? = null)
@Serializable data class DeviceHealthStatus(val platform: String? = null, val connected: Boolean = false,
                                            val lastSyncAt: String? = null)
@Serializable data class WearableDevice(val provider: String, val model: String = "", val status: String = "",
                                        val lastSyncAt: String? = null)
@Serializable data class WearableSummary(
    val aggregatorConfigured: Boolean = false, val connectionStatus: String? = null,
    val appleHealth: AppleHealthStatus = AppleHealthStatus(),
    val deviceHealth: DeviceHealthStatus = DeviceHealthStatus(),
    val devices: List<WearableDevice> = emptyList(), val lastDataAt: String? = null,
)

@Serializable data class Features(val sms: Boolean = false, val appleHealth: Boolean = false,
                                  val deviceHealth: Boolean = false, val deepLinkScheme: String = "medpull",
                                  val beta: Boolean = true, val consentVersion: String = "")
@Serializable data class ConsentStatus(val needsConsent: Boolean = false, val version: String? = null,
                                       val acceptedAt: String? = null, val researchUse: Boolean? = null)
@Serializable data class SpaceProfile(val patientId: String, val kind: String, val label: String = "",
                                      val detail: String = "", val current: Boolean = false)
@Serializable data class SubscriptionState(val state: String = "none", val source: String? = null,
                                           val productId: String? = null, val expiresAt: String? = null,
                                           val daysLeft: Int? = null, val verified: Boolean = false,
                                           val autoRenew: Boolean = false, val entitled: Boolean = false,
                                           val trialUsed: Boolean = false, val products: List<String> = emptyList())

@Serializable data class Me(
    val patient: PatientProfile, val recovery: Recovery = Recovery(), val tasksOpen: Int = 0,
    val unreadMessages: Int = 0, val wearables: WearableSummary = WearableSummary(),
    val features: Features = Features(), val profiles: List<SpaceProfile>? = null,
    val subscription: SubscriptionState? = null, val consent: ConsentStatus? = null,
) {
    val isPersonal get() = patient.isPersonal
    val needsConsent get() = consent?.needsConsent == true
}

// --- tasks -----------------------------------------------------------------------

@Serializable data class Question(val id: String, val prompt: String, val kind: String = "text",
                                  val options: List<String>? = null, val min: Int? = null, val max: Int? = null)

@Serializable data class RecoveryTask(
    val id: Int, val kind: String = "custom", val kindLabel: String = "", val title: String = "",
    val why: String = "", val status: String = "pending", val createdAt: String? = null, val dueAt: String? = null,
    val sentAt: String? = null, val completedAt: String? = null, val completedVia: String? = null,
    val questions: List<Question> = emptyList(), val inSmsConversation: Boolean = false,
    val recurring: Boolean? = null, val schedule: String? = null, val scheduleLabel: String? = null,
    val lastDoneOn: String? = null,
) {
    val isOpen get() = status == "pending" || status == "sent"
    val isCheckin get() = kind == "checkin"
}
@Serializable data class TasksResponse(val open: List<RecoveryTask> = emptyList(),
                                       val recent: List<RecoveryTask> = emptyList())
@Serializable data class CompleteResponse(val ok: Boolean = true, val task: RecoveryTask? = null)

/** A check-in answer: a number for scales, a string for everything else. */
@Serializable(with = AnswerValueSerializer::class)
sealed class AnswerValue {
    data class Num(val value: Int) : AnswerValue()
    data class Text(val value: String) : AnswerValue()
}

object AnswerValueSerializer : KSerializer<AnswerValue> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("AnswerValue", PrimitiveKind.STRING)
    override fun serialize(encoder: Encoder, value: AnswerValue) {
        val out = encoder as JsonEncoder
        when (value) {
            is AnswerValue.Num -> out.encodeJsonElement(JsonPrimitive(value.value))
            is AnswerValue.Text -> out.encodeJsonElement(JsonPrimitive(value.value))
        }
    }
    override fun deserialize(decoder: Decoder): AnswerValue {
        val el: JsonElement = (decoder as JsonDecoder).decodeJsonElement()
        val p = el.jsonPrimitive
        p.intOrNull?.let { return AnswerValue.Num(it) }
        return AnswerValue.Text(p.content)
    }
}

@Serializable data class AnswersBody(val answers: Map<String, AnswerValue>, val via: String = "app")

// --- thread -----------------------------------------------------------------------

@Serializable data class MessageAction(val kind: String, val taskId: Int? = null, val label: String = "")
@Serializable data class ChatAttachment(
    val id: Int, val contentType: String = "", val byteSize: Long = 0, val filename: String? = null,
    val kind: String = "file", val sha256: String? = null, val uploadedBy: String = "", val source: String = "",
    val createdAt: String? = null, val withdrawn: Boolean? = null,
) {
    val isImage get() = kind == "image"
    val isVideo get() = kind == "video"
    val isAudio get() = kind == "audio"
    val isWithdrawn get() = withdrawn == true
}
@Serializable data class ChatMessage(
    val id: Int, val sender: String = "", val authoredBy: String? = null, val authorName: String? = null,
    val channel: String = "app", val text: String = "", val createdAt: String? = null,
    val deliveryStatus: String? = null, val action: MessageAction? = null,
    val attachments: List<ChatAttachment>? = null, val read: Boolean = true,
) {
    val fromClinician get() = authoredBy == "care_team"
    val files get() = attachments.orEmpty()
}
@Serializable data class MessagesResponse(val messages: List<ChatMessage> = emptyList())
@Serializable data class TextBody(val text: String, val attachmentIds: List<Int> = emptyList())
@Serializable data class SentMessageResponse(val ok: Boolean = true, val message: ChatMessage)
@Serializable data class AgentBody(val text: String, val channel: String)
@Serializable data class AgentResponse(val reply: String = "", val flagged: Boolean = false,
                                       val provider: String = "", val tasksOpen: Int = 0)
@Serializable data class OkResponse(val ok: Boolean = true)
@Serializable data class ReadResponse(val ok: Boolean = true, val count: Int = 0)

// --- attachments -------------------------------------------------------------------

@Serializable data class UploadForm(val url: String, val fields: Map<String, String> = emptyMap(),
                                    val expiresIn: Int? = null)
@Serializable data class UploadTicket(val storageKey: String, val direct: Boolean = true, val maxBytes: Long = 0,
                                      val upload: UploadForm? = null)
@Serializable data class ConfirmBody(val storageKey: String, val contentType: String, val byteSize: Long,
                                     val filename: String? = null)
@Serializable data class AttachmentResponse(val attachment: ChatAttachment)
@Serializable data class AttachmentLink(val url: String? = null)
@Serializable data class AttachmentLinkResponse(val attachment: AttachmentLink)

// --- portfolio and the patient view ---------------------------------------------

@Serializable data class PortfolioPoint(val date: String, val value: Double)
@Serializable data class PortfolioMetric(
    val key: String, val label: String = "", val unit: String = "", val latest: Double? = null,
    val series: List<PortfolioPoint> = emptyList(), val daysWithData: Int = 0,
) {
    val isDailyTotal get() = key in setOf("steps", "active_energy", "exercise_session")
    val average: Double? get() = series.map { it.value }.takeIf { it.isNotEmpty() }?.average()
}
@Serializable data class PortfolioResponse(val days: Int = 14, val since: String? = null,
                                           val metrics: List<PortfolioMetric> = emptyList())

@Serializable data class MetricReadiness(
    val ready: Boolean? = null, val stage: String? = null, val have: Int? = null, val need: Int? = null,
    val firm: Int? = null, val left: Int? = null, val firmLeft: Int? = null, val unit: String = "days",
    val note: String? = null,
)
/** The three patient-facing lines the server writes for a metric (engine/explain.py). */
@Serializable data class MetricExplain(val title: String = "", val what: String = "", val why: String = "",
                                       val help: String = "")
@Serializable data class ChartPoint(val x: Double? = null, val y: Double? = null)
@Serializable data class PatientMetricChart(val kind: String = "line", val points: List<ChartPoint> = emptyList(),
                                            val xLabel: String = "Post-op day")
@Serializable data class PatientMetric(
    val id: String, val key: String? = null, val title: String = "", val state: String = "waiting",
    val stateLabel: String = "", val headline: String = "",
    /** Already formatted by the server ("120/80", "85%"), never a number. */
    val value: String? = null, val unit: String = "",
    val readiness: MetricReadiness? = null, val daysLeftText: String? = null, val explain: MetricExplain? = null,
    val chart: PatientMetricChart? = null,
) {
    val isWaiting get() = state == "waiting"
}
@Serializable data class PatientSignal(
    val key: String, val title: String = "", val state: String = "waiting", val stateLabel: String = "",
    val availability: String? = null, val headline: String = "", val latest: PortfolioPoint? = null,
    val unit: String = "", val readiness: MetricReadiness? = null, val daysLeftText: String? = null,
    val explain: MetricExplain? = null, val series: List<PortfolioPoint> = emptyList(),
)
@Serializable data class PatientMetricOverall(val showing: Int = 0, val waiting: Int = 0,
                                              val daysUntilFullPicture: Int? = null, val blurb: String? = null)
@Serializable data class PatientMetricsResponse(
    val metrics: List<PatientMetric> = emptyList(), val signals: List<PatientSignal> = emptyList(),
    val overall: PatientMetricOverall = PatientMetricOverall(), val trajectory: JsonElement? = null,
)

// --- wearables --------------------------------------------------------------------

@Serializable data class JunctionSession(val signInToken: String, val userId: String, val clientUserId: String? = null,
                                         val environment: String = "sandbox", val region: String = "us")
@Serializable data class LinkResponse(val linkUrl: String, val expiresAt: String? = null)
@Serializable data class WearablesResponse(val summary: WearableSummary, val refreshError: String? = null)

// --- measure ----------------------------------------------------------------------

@Serializable data class MotionWindowUpload(
    val startedAt: String, val sampleRateHz: Double, val accel: List<List<Double>>,
    val gyro: List<List<Double>>? = null, val gravity: List<List<Double>>? = null,
    val timestamps: List<Double>? = null, val altitude: List<List<Double>>? = null,
    val gpsDistanceM: Double? = null, val gpsAccuracyM: Double? = null, val pedometerSteps: Int? = null,
    val pedometerDistanceM: Double? = null, val pocketSide: String? = null, val context: String = "guided_walk",
    val platform: String = "android",
)
@Serializable data class MotionUpload(val windows: List<MotionWindowUpload>, val heightCm: Double? = null,
                                      val deviceModel: String? = null)
@Serializable data class StairSummary(val direction: String = "", val speedMps: Double? = null)
@Serializable data class MotionWindowSummary(
    val durationS: Double? = null, val walkingS: Double? = null,
    val bouts: Int = 0, val steps: Int? = null, val cadenceSpm: Double? = null, val walkingSpeedMps: Double? = null,
    val stepLengthM: Double? = null, val asymmetryPct: Double? = null, val doubleSupportPct: Double? = null,
    val steadiness: Double? = null, val stairs: List<StairSummary> = emptyList(), val notes: List<String> = emptyList(),
)
@Serializable data class MotionUploadResponse(val version: String = "", val windows: List<MotionWindowSummary> = emptyList(),
                                              val rows: Int = 0, val ingested: Int = 0, val updated: Int = 0,
                                              val duplicates: Int = 0)
@Serializable data class SixMinuteWalkUpload(
    val startedAt: String, val durationS: Double, val steps: Int? = null, val pedometerDistanceM: Double? = null,
    val gpsDistanceM: Double? = null, val gpsAccuracyM: Double? = null, val minuteSteps: List<Int>? = null,
    val heightCm: Double? = null, val deviceModel: String? = null, val motion: MotionWindowUpload? = null,
)
@Serializable data class SixMinuteWalkResponse(val distanceM: Double = 0.0, val method: String = "", val steps: Int? = null,
                                               val cadenceSpm: Double? = null, val fadePct: Double? = null,
                                               val motion: MotionWindowSummary? = null)
@Serializable data class RangeOfMotionUpload(
    val recordedAt: String, val protocol: String, val side: String, val reference: List<List<Double>>,
    val movement: List<List<Double>>, val deviceModel: String? = null, val platform: String = "android",
)
@Serializable data class RangeOfMotionResponse(val joint: String = "", val movement: String = "", val side: String = "",
                                               val angleDeg: Double = 0.0, val steady: Boolean = true)

/** Loose JSON helpers for the few fields the server leaves untyped. */
fun JsonElement?.asDouble(): Double? = (this as? JsonPrimitive)?.doubleOrNull
fun JsonElement?.asBool(): Boolean? = (this as? JsonPrimitive)?.booleanOrNull
