package com.medpull.recovery.features.care

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import com.medpull.recovery.R
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Speech in and out for the Care tab: the platform recogniser with partial
 * results, on-device when the phone can, and the platform synthesiser with
 * the best English voice it has. Nothing is recorded or stored; only the
 * transcript text leaves the phone, to the copilot.
 */
class SpeechController(private val context: Context) {
    private val _transcript = MutableStateFlow("")
    val transcript: StateFlow<String> = _transcript
    private val _listening = MutableStateFlow(false)
    val listening: StateFlow<Boolean> = _listening
    private val _speaking = MutableStateFlow(false)
    val speaking: StateFlow<Boolean> = _speaking
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    /** A reply asked for while the engine was still starting; spoken once it is. */
    private var queued: String? = null

    val available: Boolean get() = SpeechRecognizer.isRecognitionAvailable(context)

    fun startListening() {
        stopSpeaking()
        if (!available) { _error.value = context.getString(R.string.speech_unavailable); return }
        val r = recognizer ?: SpeechRecognizer.createSpeechRecognizer(context).also { recognizer = it }
        r.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { _listening.value = true }
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() { _listening.value = false }
            override fun onError(error: Int) {
                _listening.value = false
                if (error != SpeechRecognizer.ERROR_NO_MATCH && error != SpeechRecognizer.ERROR_CLIENT) _error.value = context.getString(R.string.speech_not_heard)
            }
            override fun onResults(results: Bundle?) {
                results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { _transcript.value = it }
                _listening.value = false
            }
            override fun onPartialResults(partialResults: Bundle?) {
                partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { _transcript.value = it }
            }
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        _transcript.value = ""
        _error.value = null
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        }
        r.startListening(intent)
        _listening.value = true
    }

    /** Ends the capture and returns what was heard, trimmed. */
    fun stopListening(): String {
        recognizer?.stopListening()
        _listening.value = false
        return _transcript.value.trim()
    }

    fun speak(text: String) {
        if (text.isBlank()) return
        if (ttsReady) { say(text); return }
        // Not ready yet (first use, or the engine is still starting): keep the
        // latest reply and say it when the engine reports in.
        queued = text
        if (tts != null) return
        tts = TextToSpeech(context) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (!ttsReady) { queued = null; _error.value = context.getString(R.string.tts_unavailable); return@TextToSpeech }
            pickVoice()
            queued?.let { say(it) }
            queued = null
        }.also {
            it.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) { _speaking.value = true }
                override fun onDone(utteranceId: String?) { _speaking.value = false }
                @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) { _speaking.value = false }
            })
        }
    }

    private fun say(text: String) {
        tts?.setSpeechRate(0.95f)
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "medpull-${System.currentTimeMillis()}")
    }

    /** The highest-quality English voice that needs no network, by name preference then quality. */
    private fun pickVoice() {
        val engine = tts ?: return
        val voices: Set<Voice> = try { engine.voices ?: emptySet() } catch (_: Exception) { emptySet() }
        val english = voices.filter { it.locale.language == Locale.ENGLISH.language && !it.isNetworkConnectionRequired }
        val best = english.filter { it.locale.country == "US" }.ifEmpty { english }
            .maxWithOrNull(compareBy<Voice> { it.quality }.thenBy { it.latency * -1 })
        if (best != null) engine.voice = best else engine.language = Locale.US
    }

    fun stopSpeaking() { queued = null; tts?.stop(); _speaking.value = false }

    fun release() {
        recognizer?.destroy(); recognizer = null
        tts?.shutdown(); tts = null; ttsReady = false
    }
}
