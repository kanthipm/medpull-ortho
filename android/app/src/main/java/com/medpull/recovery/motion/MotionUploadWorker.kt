package com.medpull.recovery.motion

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.core.ApiException
import com.medpull.recovery.core.MotionUpload
import com.medpull.recovery.core.uploadMotion
import kotlinx.serialization.json.Json
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Uploads a free-living bout after the capture service has stopped. The
 * payload is spooled to a file first, so a bout recorded on the bus with no
 * signal, or with the process killed straight after, still arrives once the
 * network is back. Retried with backoff; a 4xx means the server will never
 * take it, so the file is dropped.
 */
class MotionUploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val file = File(inputData.getString(KEY_PATH) ?: return Result.failure())
        if (!file.exists()) return Result.failure()
        val api = (applicationContext as MedPullApp).graph.api
        return try {
            api.uploadMotion(api.json.decodeFromString(MotionUpload.serializer(), file.readText()))
            file.delete()
            Result.success()
        } catch (e: ApiException) {
            val refused = e.status in 400..499 && e.status != 429
            if (refused || runAttemptCount >= MAX_ATTEMPTS) { Log.w(TAG, "bout dropped (${e.status})"); file.delete(); Result.failure() }
            else Result.retry()
        } catch (e: Exception) {
            if (runAttemptCount >= MAX_ATTEMPTS) { Log.w(TAG, "bout dropped", e); file.delete(); Result.failure() } else Result.retry()
        }
    }

    companion object {
        private const val TAG = "MotionUpload"
        private const val KEY_PATH = "path"
        private const val MAX_ATTEMPTS = 6

        fun enqueue(context: Context, upload: MotionUpload, json: Json) {
            val dir = File(context.filesDir, "uploads").apply { mkdirs() }
            val file = File(dir, "bout-${System.currentTimeMillis()}.json")
            file.writeText(json.encodeToString(MotionUpload.serializer(), upload))
            val request = OneTimeWorkRequestBuilder<MotionUploadWorker>()
                .setInputData(workDataOf(KEY_PATH to file.absolutePath))
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
