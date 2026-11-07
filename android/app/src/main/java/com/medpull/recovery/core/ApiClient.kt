package com.medpull.recovery.core

import com.medpull.recovery.R
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.serializer
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/** What the server said when it refused; status 0 means nothing answered. */
class ApiException(val status: Int, val detail: String) : IOException(detail) {
    val isUnauthorized get() = status == 401
    val isPaywall get() = status == 402
}

/**
 * One client for every route, the same rules as the iPhone's: snake_case on
 * the wire, timestamps kept as strings, a 30 s deadline, GETs retried once
 * after 1.5 s on a transport failure, 429 or a 5xx, nothing else retried.
 */
@OptIn(ExperimentalSerializationApi::class)
class ApiClient(private val config: AppConfig, private val session: SessionStore, val strings: Strings) {
    val json: Json = Json {
        namingStrategy = JsonNamingStrategy.SnakeCase
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        isLenient = true
        // Defaults go on the wire too: `platform: "android"` on a motion
        // window and `via: "app"` on an answer are defaults here but not on
        // the server, which would read an Android frame as an iPhone's.
        encodeDefaults = true
    }

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .build()

    val baseUrl: String get() = config.baseUrl

    suspend inline fun <reified T> get(path: String, query: Map<String, String> = emptyMap()): T =
        request(path, "GET", null, query, serializer())

    suspend inline fun <reified B, reified T> post(path: String, body: B): T =
        request(path, "POST", json.encodeToString(serializer<B>(), body), emptyMap(), serializer())

    suspend inline fun <reified T> post(path: String): T =
        request(path, "POST", "{}", emptyMap(), serializer())

    suspend inline fun <reified B, reified T> patch(path: String, body: B): T =
        request(path, "PATCH", json.encodeToString(serializer<B>(), body), emptyMap(), serializer())

    suspend inline fun <reified T> delete(path: String): T =
        request(path, "DELETE", "{}", emptyMap(), serializer())

    suspend fun <T> request(
        path: String, method: String, body: String?, query: Map<String, String>, deserializer: KSerializer<T>,
    ): T = withContext(Dispatchers.IO) {
        val url = baseUrl.toHttpUrl().newBuilder().encodedPath(path).apply {
            query.forEach { (k, v) -> addQueryParameter(k, v) }
        }.build()
        var attempt = 0
        while (true) {
            attempt += 1
            val (status, text) = try {
                exchange(url.toString(), method, body, JSON_TYPE_HEADER)
            } catch (e: CancellationException) {
                throw e
            } catch (e: IOException) {
                0 to ""
            }
            val retryable = method == "GET" && attempt == 1 && (status == 0 || status == 429 || status >= 500)
            if (retryable) {
                delay(1500)
                continue
            }
            if (status == 0) throw ApiException(0, strings.get(R.string.api_unreachable))
            if (status !in 200..299) throw ApiException(status, detailOf(text, status))
            return@withContext try {
                json.decodeFromString(deserializer, text)
            } catch (e: Exception) {
                throw ApiException(status, strings.get(R.string.api_unexpected_answer, e.message ?: ""))
            }
        }
        @Suppress("UNREACHABLE_CODE")
        throw IllegalStateException()
    }

    /** Raw bytes in, JSON out: the direct attachment upload. */
    suspend fun <T> upload(path: String, bytes: ByteArray, contentType: String, query: Map<String, String>,
                           deserializer: KSerializer<T>): T = withContext(Dispatchers.IO) {
        val url = baseUrl.toHttpUrl().newBuilder().encodedPath(path).apply {
            query.forEach { (k, v) -> addQueryParameter(k, v) }
        }.build()
        val req = Request.Builder().url(url).post(bytes.toRequestBody(contentType.toMediaType()))
            .header("Accept", "application/json").also { b -> session.token?.let { b.header("Authorization", "Bearer $it") } }
            .build()
        http.newCall(req).execute().use { res ->
            val text = res.body?.string().orEmpty()
            if (!res.isSuccessful) throw ApiException(res.code, detailOf(text, res.code))
            json.decodeFromString(deserializer, text)
        }
    }

    /** Multipart POST to a presigned storage URL: no bearer header, status only. */
    suspend fun presignedUpload(url: String, fields: Map<String, String>, bytes: ByteArray, contentType: String) =
        withContext(Dispatchers.IO) {
            val multipart = okhttp3.MultipartBody.Builder().setType(okhttp3.MultipartBody.FORM)
            fields.forEach { (k, v) -> multipart.addFormDataPart(k, v) }
            multipart.addFormDataPart("file", "upload", bytes.toRequestBody(contentType.toMediaType()))
            val req = Request.Builder().url(url).post(multipart.build()).build()
            http.newCall(req).execute().use { res ->
                if (!res.isSuccessful) throw ApiException(res.code, strings.get(R.string.api_upload_refused))
            }
        }

    /** Download bytes, with the bearer header only for our own host. */
    suspend fun bytes(url: String, authenticated: Boolean): ByteArray = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).also { b ->
            if (authenticated) session.token?.let { b.header("Authorization", "Bearer $it") }
        }.build()
        http.newCall(req).execute().use { res ->
            if (!res.isSuccessful) throw ApiException(res.code, strings.get(R.string.api_fetch_failed))
            res.body?.bytes() ?: ByteArray(0)
        }
    }

    private fun exchange(url: String, method: String, body: String?, contentType: String): Pair<Int, String> {
        val rb: RequestBody? = body?.toRequestBody(contentType.toMediaType())
        val builder = Request.Builder().url(url).header("Accept", "application/json")
        session.token?.let { builder.header("Authorization", "Bearer $it") }
        when (method) {
            "GET" -> builder.get()
            "DELETE" -> builder.delete(rb)
            else -> builder.method(method, rb)
        }
        http.newCall(builder.build()).execute().use { res ->
            return res.code to res.body?.string().orEmpty()
        }
    }

    private fun detailOf(text: String, status: Int): String = try {
        val obj = json.parseToJsonElement(text) as? JsonObject
        obj?.get("detail")?.jsonPrimitive?.content ?: strings.get(R.string.api_server_answered, status)
    } catch (_: Exception) {
        strings.get(R.string.api_server_answered, status)
    }

    companion object {
        const val JSON_TYPE_HEADER = "application/json"
    }
}
