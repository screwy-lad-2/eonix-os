package com.eonix.companion.data

data class GoalResponse(
    val id: String = "",
    val name: String = "",
    val description: String = "",
    val progress: Float = 0f,
    val status: String = ""
)

data class MemoryItem(
    val text: String = "",
    val category: String = "general",
    val timestamp: String = "",
    val importance: Int = 1
)

data class SyncStatusResponse(
    val device_id: String = "",
    val peers_found: Int = 0,
    val last_sync: String = ""
)

data class ContextResponse(
    val summary: String = "",
    val event_count: Int = 0
)

data class SyncStateResponse(
    val device_id: String = "",
    val active_goal: GoalResponse? = null,
    val memory_summary: List<MemoryItem> = emptyList(),
    val system_snapshot: Map<String, Float> = emptyMap()
)
