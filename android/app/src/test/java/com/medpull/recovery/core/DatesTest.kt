package com.medpull.recovery.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

/** The server writes naive ISO-8601 with microseconds, or a bare day. */
class DatesTest {
    @Test
    fun `parses the server's naive timestamps and days`() {
        assertEquals(LocalDate.of(2026, 11, 6), Dates.parse("2026-11-06T09:15:30.123456")?.toLocalDate())
        assertEquals(LocalDate.of(2026, 11, 6), Dates.parse("2026-11-06T09:15:30")?.toLocalDate())
        assertEquals(LocalDate.of(2026, 11, 6), Dates.parse("2026-11-06")?.toLocalDate())
        assertNotNull(Dates.parse("2026-11-06T09:15:30+00:00"))
        assertNull(Dates.parse(null))
        assertNull(Dates.parse("yesterday"))
    }

    @Test
    fun `day takes the first ten characters`() {
        assertEquals(LocalDate.of(2026, 11, 6), Dates.day("2026-11-06T09:15:30.123456"))
        assertNull(Dates.day("nope"))
    }

    @Test
    fun `relative says just now for the present`() {
        val now = java.time.LocalDateTime.now().format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSS"))
        assertEquals("just now", Dates.relative(now))
    }
}
