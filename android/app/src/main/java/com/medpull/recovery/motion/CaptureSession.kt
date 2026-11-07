package com.medpull.recovery.motion

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

enum class CaptureState { IDLE, RUNNING, DONE }

/**
 * What is being recorded right now, shared between the foreground service
 * that owns the sensors and the screens that watch it. One per process.
 */
object CaptureSession {
    private val _state = MutableStateFlow(CaptureState.IDLE)
    val state: StateFlow<CaptureState> = _state

    /** The recorder of the current or last test, read by the Measure screens. */
    @Volatile var recorder: MotionRecorder? = null
        private set
    /** A passive bout, which uploads itself, rather than a guided test. */
    @Volatile var freeLiving: Boolean = false
        private set

    internal fun begin(recorder: MotionRecorder, freeLiving: Boolean) {
        this.recorder = recorder
        this.freeLiving = freeLiving
        _state.value = CaptureState.RUNNING
    }

    internal fun finished() { _state.value = CaptureState.DONE }

    /** Forget the last test once its screen has uploaded it. */
    fun reset() {
        recorder = null
        freeLiving = false
        _state.value = CaptureState.IDLE
    }
}
