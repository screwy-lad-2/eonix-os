package com.eonix.companion.ui

import android.widget.TextView

object StatusBar {
    fun renderSnapshot(view: TextView, snapshot: Map<String, Float>) {
        val ram = snapshot["ram_percent"] ?: 0f
        val cpu = snapshot["cpu_percent"] ?: 0f
        val disk = snapshot["disk_percent"] ?: 0f
        view.text = "RAM: ${ram.toInt()}%  CPU: ${cpu.toInt()}%  Disk: ${disk.toInt()}%"
    }
}
