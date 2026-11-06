package com.medpull.recovery.features.care

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaRecorder
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.effect.Presentation
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import com.medpull.recovery.core.ApiClient
import com.medpull.recovery.core.ChatAttachment
import com.medpull.recovery.core.attachmentBytes
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/** A file ready to send: bytes, type and a name, within the server's budgets. */
data class Prepared(val bytes: ByteArray, val contentType: String, val filename: String)

/**
 * The same budgets the iPhone applies before upload (ios/MedPull/Core/Attachments.swift):
 * photos as JPEG 0.82 with the long edge at most 2048 px, video as MP4 at 540p
 * when it is not already a small MP4, everything at most 48 MB.
 */
object AttachmentPrep {
    const val MAX_EDGE = 2048
    const val JPEG_QUALITY = 82
    const val MAX_MEDIA_BYTES = 48L * 1024 * 1024
    const val PASSTHROUGH_VIDEO_BYTES = 8L * 1024 * 1024
    val acceptedMimes = arrayOf("application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
        "video/mp4", "video/quicktime", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-m4a")

    suspend fun fromUri(context: Context, uri: Uri): Prepared? = withContext(Dispatchers.IO) {
        val type = context.contentResolver.getType(uri) ?: guessType(uri)
        val name = displayName(context, uri) ?: "file"
        when {
            type.startsWith("image/") -> image(context, uri, name)
            type.startsWith("video/") -> video(context, uri, name, type)
            type.startsWith("audio/") -> context.contentResolver.openInputStream(uri)?.use { it.readBytes() }?.let {
                val mime = when (type) { "audio/x-m4a", "audio/mp4", "audio/aac" -> "audio/mp4"; "audio/mpeg" -> "audio/mpeg"; "audio/wav", "audio/x-wav" -> "audio/wav"; else -> return@withContext null }
                if (it.size > MAX_MEDIA_BYTES) null else Prepared(it, mime, name)
            }
            type == "application/pdf" -> context.contentResolver.openInputStream(uri)?.use { it.readBytes() }?.let { Prepared(it, type, name) }
            else -> null
        }
    }

    /** Decode at a sample size that lands near 2048, honour EXIF rotation, re-encode as JPEG. */
    fun image(context: Context, uri: Uri, name: String): Prepared? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) } ?: return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_EDGE) sample *= 2
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        val raw = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) } ?: return null
        val rotation = context.contentResolver.openInputStream(uri)?.use { ExifInterface(it).rotationDegrees } ?: 0
        val longEdge = maxOf(raw.width, raw.height)
        val scaled = if (longEdge > MAX_EDGE) {
            val f = MAX_EDGE / longEdge.toFloat()
            Bitmap.createScaledBitmap(raw, (raw.width * f).toInt(), (raw.height * f).toInt(), true)
        } else raw
        val upright = if (rotation != 0) {
            val m = android.graphics.Matrix().apply { postRotate(rotation.toFloat()) }
            Bitmap.createBitmap(scaled, 0, 0, scaled.width, scaled.height, m, true)
        } else scaled
        val out = ByteArrayOutputStream()
        upright.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
        val base = name.substringBeforeLast('.').ifBlank { "photo" }
        return Prepared(out.toByteArray(), "image/jpeg", "$base.jpg")
    }

    /** A small MP4 goes as is; anything else is re-encoded to 540p H.264 in an MP4. */
    suspend fun video(context: Context, uri: Uri, name: String, type: String): Prepared? {
        val size = context.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } ?: -1
        if (type == "video/mp4" && size in 1..PASSTHROUGH_VIDEO_BYTES) {
            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
            return Prepared(bytes, "video/mp4", name.substringBeforeLast('.').ifBlank { "video" } + ".mp4")
        }
        val out = File(context.cacheDir, "captures/transcode-${System.currentTimeMillis()}.mp4").apply { parentFile?.mkdirs() }
        transcode(context, uri, out)
        val bytes = out.readBytes().also { out.delete() }
        if (bytes.size > MAX_MEDIA_BYTES) return null
        return Prepared(bytes, "video/mp4", name.substringBeforeLast('.').ifBlank { "video" } + ".mp4")
    }

    private suspend fun transcode(context: Context, uri: Uri, out: File) = withContext(Dispatchers.Main) {
        val done = CompletableDeferred<Unit>()
        val transformer = Transformer.Builder(context)
            .setVideoMimeType(MimeTypes.VIDEO_H264)
            .setAudioMimeType(MimeTypes.AUDIO_AAC)
            .addListener(object : Transformer.Listener {
                override fun onCompleted(composition: Composition, exportResult: ExportResult) { done.complete(Unit) }
                override fun onError(composition: Composition, exportResult: ExportResult, exportException: ExportException) {
                    done.completeExceptionally(exportException)
                }
            })
            .build()
        val item = EditedMediaItem.Builder(MediaItem.fromUri(uri))
            .setEffects(Effects(emptyList(), listOf(Presentation.createForHeight(540))))
            .build()
        transformer.start(item, out.absolutePath)
        done.await()
    }

    private fun displayName(context: Context, uri: Uri): String? =
        context.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: uri.lastPathSegment

    private fun guessType(uri: Uri): String = when (uri.toString().substringAfterLast('.').lowercase()) {
        "jpg", "jpeg" -> "image/jpeg"; "png" -> "image/png"; "webp" -> "image/webp"; "heic", "heif" -> "image/heic"
        "mp4" -> "video/mp4"; "mov" -> "video/quicktime"; "m4a" -> "audio/mp4"; "mp3" -> "audio/mpeg"; "wav" -> "audio/wav"
        "pdf" -> "application/pdf"; else -> "application/octet-stream"
    }
}

/** AAC in an MP4 container, 44.1 kHz mono at 64 kbps, at most 180 s, as on iPhone. */
class VoiceNoteRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var startedAt = 0L
    val isRecording get() = recorder != null

    fun start() {
        val f = File(context.cacheDir, "captures/note-${System.currentTimeMillis()}.m4a").apply { parentFile?.mkdirs() }
        @Suppress("DEPRECATION")
        val r = if (android.os.Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else MediaRecorder()
        r.setAudioSource(MediaRecorder.AudioSource.MIC)
        r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        r.setAudioChannels(1)
        r.setAudioSamplingRate(44_100)
        r.setAudioEncodingBitRate(64_000)
        r.setMaxDuration(180_000)
        r.setOutputFile(f.absolutePath)
        r.prepare(); r.start()
        recorder = r; file = f; startedAt = System.currentTimeMillis()
    }

    /** Stops and returns the note, or null for a tap shorter than half a second. */
    fun stop(): Prepared? {
        val r = recorder ?: return null
        val f = file
        recorder = null; file = null
        try { r.stop() } catch (_: Exception) { r.release(); f?.delete(); return null }
        r.release()
        val ms = System.currentTimeMillis() - startedAt
        if (f == null || ms < 500) { f?.delete(); return null }
        val bytes = f.readBytes(); f.delete()
        val stamp = java.text.SimpleDateFormat("MMM d, h.mm a", java.util.Locale.getDefault()).format(java.util.Date())
        return Prepared(bytes, "audio/mp4", "Voice note $stamp.m4a")
    }

    fun cancel() { recorder?.let { try { it.stop() } catch (_: Exception) {}; it.release() }; recorder = null; file?.delete(); file = null }
}

/** Downloaded attachments, kept as files under the cache so images, video
 *  and audio can be shown again without another fetch. */
class MediaCache(private val context: Context, private val api: ApiClient) {
    private val failed = ConcurrentHashMap.newKeySet<Int>()
    private val dir = File(context.cacheDir, "medpull-media").apply { mkdirs() }

    fun cached(a: ChatAttachment): File? = fileFor(a).takeIf { it.exists() && it.length() > 0 }

    suspend fun fetch(a: ChatAttachment): File? {
        cached(a)?.let { return it }
        if (a.id in failed) return null
        return try {
            val bytes = api.attachmentBytes(a.id)
            val f = fileFor(a)
            withContext(Dispatchers.IO) { f.writeBytes(bytes) }
            f
        } catch (e: Exception) { failed.add(a.id); null }
    }

    private fun fileFor(a: ChatAttachment): File {
        val ext = when {
            a.contentType.contains("jpeg") -> "jpg"; a.contentType.contains("png") -> "png"; a.contentType.contains("webp") -> "webp"
            a.contentType.startsWith("video/") -> "mp4"; a.contentType == "audio/mpeg" -> "mp3"; a.contentType == "audio/wav" -> "wav"
            a.contentType.startsWith("audio/") -> "m4a"; a.contentType == "application/pdf" -> "pdf"; else -> "bin"
        }
        return File(dir, "${a.sha256 ?: "id-${a.id}"}.$ext")
    }
}
