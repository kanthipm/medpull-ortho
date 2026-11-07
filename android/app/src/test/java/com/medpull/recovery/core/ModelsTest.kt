package com.medpull.recovery.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wire types against what the server sends (backend/app/engine/patient_view.py,
 * backend/app/api/mobility.py). Keys are snake_case; the care metric value is a
 * formatted string; the explanation has title/what/why/help.
 */
class ModelsTest {
    private val json = Json {
        namingStrategy = JsonNamingStrategy.SnakeCase
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        isLenient = true
        encodeDefaults = true
    }

    @Test
    fun `a motion window says it came from android`() {
        val w = MotionWindowUpload(startedAt = "2026-11-06T09:00:00-06:00", sampleRateHz = 50.0,
            accel = List(50) { listOf(0.0, 0.0, 9.81) })
        assertTrue(json.encodeToString(MotionWindowUpload.serializer(), w).contains("\"platform\":\"android\""))
    }

    @Test
    fun `care metrics decode with string values and the overall blurb`() {
        val body = """
        {
          "postop_day": 12, "mode": "recovery",
          "overall": {"blurb": "Three of five are showing.", "days_until_full_picture": 4, "showing": 3, "waiting": 2},
          "trajectory": {"state": "on_track", "pct": 4.5},
          "metrics": [
            {"id": "M12", "key": "bp", "title": "Blood pressure", "state": "good", "state_label": "Looking steady",
             "headline": "Steady this week.", "value": "120/80", "unit": "mmHg",
             "readiness": {"ready": true, "stage": "established", "have": 7, "need": 4, "firm": 7, "left": 0, "firm_left": 0, "unit": "days"},
             "explain": {"title": "Blood pressure", "what": "What it is.", "why": "Why it matters.", "help": "Wear the cuff."},
             "chart": {"kind": "line", "points": [{"x": 1, "y": 118}, {"x": 2, "y": 120}], "x_label": "Post-op day"}},
            {"id": "M1", "title": "Weekly load", "state": "waiting", "state_label": "Not showing yet", "headline": "Shows in 3 days.", "value": null, "unit": "",
             "readiness": {"ready": false, "stage": "collecting", "have": 2, "need": 5, "left": 3, "unit": "days", "note": "steps"}}
          ],
          "signals": []
        }
        """.trimIndent()
        val r = json.decodeFromString(PatientMetricsResponse.serializer(), body)
        assertEquals("Three of five are showing.", r.overall.blurb)
        assertEquals("120/80", r.metrics[0].value)
        assertEquals("Wear the cuff.", r.metrics[0].explain?.help)
        assertEquals(2, r.metrics[0].chart?.points?.size)
        assertTrue(r.metrics[1].isWaiting)
        assertNull(r.metrics[1].value)
    }

    @Test
    fun `me decodes with the hospital as an object and the device health block`() {
        val body = """
        {"patient": {"id": "p1", "name": "Ada Lovelace", "first_name": "Ada", "initials": "AL", "mode": "recovery",
                     "procedure_display": "Knee replacement", "postop_day": 3, "days_enrolled": 3,
                     "hospital": {"id": "h1", "name": "St Mary's", "city": "Austin", "state": "TX"},
                     "care_team": [{"name": "Dr. Priya Shah", "role": "surgeon"}]},
         "recovery": {"level": "ok", "label": "On track", "blurb": "Walking a little further each day.", "trajectory": {"state": "unknown"}},
         "tasks_open": 1, "unread_messages": 0,
         "wearables": {"aggregator_configured": true, "device_health": {"platform": "health_connect", "connected": true}, "devices": []},
         "features": {"sms": true, "apple_health": true, "device_health": true},
         "consent": {"needs_consent": false, "current_version": "2"}}
        """.trimIndent()
        val me = json.decodeFromString(Me.serializer(), body)
        assertEquals("St Mary's", me.patient.hospital?.name)
        assertTrue(me.wearables.deviceHealth.connected)
        assertEquals("Dr. Priya Shah", me.patient.careTeam.single().name)
    }

    @Test
    fun `a walk summary uses the server's steps key`() {
        val body = """{"version": "1", "windows": [{"duration_s": 180.0, "walking_s": 170.2, "bouts": 1, "steps": 212, "cadence_spm": 71.0, "notes": []}],
                       "rows": 5, "ingested": 5, "updated": 0, "duplicates": 0}"""
        val r = json.decodeFromString(MotionUploadResponse.serializer(), body)
        assertEquals(212, r.windows[0].steps)
        assertEquals(1, r.windows[0].bouts)
    }

    @Test
    fun `check-in answers encode as bare numbers and strings`() {
        val body = AnswersBody(mapOf("pain" to AnswerValue.Num(4), "sleep" to AnswerValue.Text("well")))
        assertEquals("""{"answers":{"pain":4,"sleep":"well"},"via":"app"}""", json.encodeToString(AnswersBody.serializer(), body))
    }
}
