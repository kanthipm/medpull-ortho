package com.medpull.recovery.core

/** A user-facing string by resource id: the app reads its resources, a test can hand in a stub. */
fun interface Strings {
    fun get(id: Int, vararg args: Any): String
}
