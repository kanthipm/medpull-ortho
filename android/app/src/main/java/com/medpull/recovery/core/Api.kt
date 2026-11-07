package com.medpull.recovery.core

import com.medpull.recovery.R
import kotlinx.serialization.Serializable
import kotlinx.serialization.serializer

/** Every route the recovery app calls, one function each, on the shared client. */

@Serializable data class SearchBody(val hospitalId: String, val name: String, val phone: String? = null)
@Serializable data class EnrollBody(val patientId: String, val hospitalId: String, val phone: String,
                                    val consent: ConsentAcceptance? = null, val deviceName: String, val appVersion: String)
@Serializable data class VerifyBody(val verificationId: Int, val code: String, val consent: ConsentAcceptance? = null,
                                    val deviceName: String, val appVersion: String)
@Serializable data class JoinBody(
    val hospitalId: String, val name: String, val phone: String, val dateOfBirth: String? = null,
    val hadSurgery: Boolean, val procedureType: String? = null, val surgeryDate: String? = null,
    val consent: ConsentAcceptance? = null, val deviceName: String, val appVersion: String,
)
@Serializable data class ConsentBody(val version: String, val scopes: Map<String, Boolean>, val signature: String? = null,
                                     val deviceName: String, val appVersion: String)
@Serializable data class ConsentResponse(val ok: Boolean = true)
@Serializable data class SwitchBody(val patientId: String, val deviceName: String, val appVersion: String)
@Serializable data class SwitchResponse(val sessionToken: String? = null, val me: Me? = null)

// onboarding
suspend fun ApiClient.hospitals(query: String = ""): List<Hospital> =
    get<HospitalsResponse>("/api/mobile/hospitals", if (query.isBlank()) emptyMap() else mapOf("q" to query)).hospitals
suspend fun ApiClient.search(body: SearchBody): List<Candidate> =
    post<SearchBody, CandidatesResponse>("/api/mobile/patients/search", body).candidates
suspend fun ApiClient.enroll(body: EnrollBody): EnrollResponse = post("/api/mobile/enroll", body)
suspend fun ApiClient.verify(body: VerifyBody): EnrollResponse = post("/api/mobile/enroll/verify", body)
/** While the person texts MedPull for the first time: has the code gone out? */
suspend fun ApiClient.verificationStatus(id: Int): VerificationStatus = get("/api/mobile/enroll/verification/$id")
/** "I've sent it — send my code": the same verification, tried again. */
suspend fun ApiClient.resendVerification(id: Int): EnrollResponse = post("/api/mobile/enroll/verification/$id/resend")
suspend fun ApiClient.procedures(): List<Procedure> = get<ProceduresResponse>("/api/mobile/procedures").procedures
suspend fun ApiClient.join(body: JoinBody): EnrollResponse = post("/api/mobile/join", body)
suspend fun ApiClient.consentDocument(): ConsentDocument = get("/api/mobile/consent")
suspend fun ApiClient.acceptConsent(body: ConsentBody): ConsentResponse = post("/api/mobile/consent", body)
suspend fun ApiClient.switchProfile(body: SwitchBody): SwitchResponse = post("/api/mobile/profiles/switch", body)

// feeds
suspend fun ApiClient.me(): Me = get("/api/mobile/me")
suspend fun ApiClient.metrics(): PatientMetricsResponse = get("/api/mobile/metrics")
suspend fun ApiClient.tasks(): TasksResponse = get("/api/mobile/tasks")
suspend fun ApiClient.messages(sinceId: Int = 0): List<ChatMessage> =
    get<MessagesResponse>("/api/mobile/messages", mapOf("since_id" to sinceId.toString())).messages
suspend fun ApiClient.portfolio(days: Int = 14): PortfolioResponse =
    get("/api/mobile/portfolio", mapOf("days" to days.toString()))
suspend fun ApiClient.wearables(): WearablesResponse = get("/api/mobile/wearables")

// actions
suspend fun ApiClient.complete(taskId: Int, answers: Map<String, AnswerValue>, via: String = "app"): CompleteResponse =
    post("/api/mobile/tasks/$taskId/complete", AnswersBody(answers, via))
suspend fun ApiClient.skip(taskId: Int): CompleteResponse = post("/api/mobile/tasks/$taskId/skip")
suspend fun ApiClient.sendMessage(text: String, attachmentIds: List<Int>): ChatMessage =
    post<TextBody, SentMessageResponse>("/api/mobile/messages", TextBody(text, attachmentIds)).message
suspend fun ApiClient.markMessagesRead(): ReadResponse = post("/api/mobile/messages/read")
suspend fun ApiClient.agent(text: String, channel: String): AgentResponse =
    post("/api/mobile/agent", AgentBody(text, channel))
suspend fun ApiClient.signOut(): OkResponse = post("/api/mobile/signout")

// wearables
suspend fun ApiClient.junctionSession(): JunctionSession = post("/api/mobile/wearables/apple/session")
suspend fun ApiClient.refreshWearables(): WearablesResponse = post("/api/mobile/wearables/refresh")
suspend fun ApiClient.wearableLink(): LinkResponse = post("/api/mobile/wearables/link")

// measure
suspend fun ApiClient.uploadMotion(body: MotionUpload): MotionUploadResponse = post("/api/mobile/observations/motion", body)
suspend fun ApiClient.sixMinuteWalk(body: SixMinuteWalkUpload): SixMinuteWalkResponse = post("/api/mobile/tests/six-minute-walk", body)
suspend fun ApiClient.rangeOfMotion(body: RangeOfMotionUpload): RangeOfMotionResponse = post("/api/mobile/tests/range-of-motion", body)

// attachments: ticket -> presigned or direct -> confirm, as the iPhone does
suspend fun ApiClient.uploadAttachment(bytes: ByteArray, contentType: String, filename: String): ChatAttachment {
    val ticket: UploadTicket = get("/api/mobile/attachments/upload-ticket",
        mapOf("content_type" to contentType, "byte_size" to bytes.size.toString()))
    if (ticket.maxBytes > 0 && bytes.size > ticket.maxBytes) {
        throw ApiException(413, strings.get(R.string.api_file_too_big, ticket.maxBytes / 1_000_000))
    }
    val form = ticket.upload
    if (ticket.direct || form == null) {
        return upload("/api/mobile/attachments/direct", bytes, contentType, mapOf("filename" to filename),
            serializer<AttachmentResponse>()).attachment
    }
    presignedUpload(form.url, form.fields, bytes, contentType)
    return post<ConfirmBody, AttachmentResponse>("/api/mobile/attachments",
        ConfirmBody(ticket.storageKey, contentType, bytes.size.toLong(), filename)).attachment
}
suspend fun ApiClient.withdrawAttachment(id: Int): OkResponse = delete("/api/mobile/attachments/$id")
suspend fun ApiClient.attachmentBytes(id: Int): ByteArray {
    val link: AttachmentLinkResponse = get("/api/mobile/attachments/$id")
    val url = link.attachment.url
    return if (url != null) bytes(url, authenticated = false)
    else bytes("$baseUrl/api/mobile/attachments/$id/raw", authenticated = true)
}
