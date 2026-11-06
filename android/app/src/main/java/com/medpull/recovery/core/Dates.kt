package com.medpull.recovery.core

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

/** The server's timestamps are naive local wall time or dated strings; the
 *  app parses on demand, like the iPhone's `Dates`. */
object Dates {
    private val formats = listOf(
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSS"),
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS"),
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"),
    )

    fun parse(value: String?): LocalDateTime? {
        if (value.isNullOrBlank()) return null
        try { return OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime() } catch (_: DateTimeParseException) {}
        for (f in formats) try { return LocalDateTime.parse(value, f) } catch (_: DateTimeParseException) {}
        try { return LocalDate.parse(value).atStartOfDay() } catch (_: DateTimeParseException) {}
        return null
    }

    fun day(value: String?): LocalDate? = try { LocalDate.parse(value?.take(10)) } catch (_: Exception) { null }

    fun dayString(d: LocalDate): String = d.toString()

    /** ISO-8601 with the device's offset, for what the app records itself. */
    fun iso(instant: Instant = Instant.now()): String =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(instant.atZone(ZoneId.systemDefault()))

    fun monthDay(d: LocalDate): String = "${d.month.getDisplayName(java.time.format.TextStyle.SHORT, java.util.Locale.getDefault())} ${d.dayOfMonth}"

    fun relative(value: String?): String? {
        val t = parse(value) ?: return null
        val mins = Duration.between(t, LocalDateTime.now()).toMinutes()
        return when {
            mins < 1 -> "just now"
            mins < 60 -> "${mins}m ago"
            mins < 60 * 24 -> "${mins / 60}h ago"
            mins < 60 * 24 * 7 -> "${mins / (60 * 24)}d ago"
            else -> monthDay(t.toLocalDate())
        }
    }

    fun shortDay(d: LocalDate): String = d.dayOfWeek.getDisplayName(java.time.format.TextStyle.SHORT, java.util.Locale.getDefault())
}
