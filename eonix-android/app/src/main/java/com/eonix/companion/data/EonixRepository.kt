package com.eonix.companion.data

import android.content.Context
import com.eonix.companion.network.EonixApiClient

class EonixRepository(context: Context) {
    private val api = EonixApiClient(context)

    suspend fun refreshAll(): RefreshBundle {
        val goal = api.getActiveGoal()
        val progress = if (!goal?.id.isNullOrBlank()) api.getGoalProgress(goal!!.id) else 0f
        val status = api.getSyncStatus()
        val memory = api.getMemorySummary()
        val snapshot = api.getSystemSnapshot()

        val hydratedGoal = goal?.copy(progress = progress)
        val connected = status != null

        return RefreshBundle(
            activeGoal = hydratedGoal,
            memory = memory,
            syncStatus = status,
            systemSnapshot = snapshot,
            connected = connected
        )
    }

    suspend fun sendVoiceCommand(text: String): String = api.sendVoiceCommand(text)

    suspend fun createGoal(name: String, desc: String): Boolean = api.pushGoalFromPhone(name, desc)

    suspend fun syncNow(): Boolean = api.syncNow()
}

data class RefreshBundle(
    val activeGoal: GoalResponse?,
    val memory: List<MemoryItem>,
    val syncStatus: SyncStatusResponse?,
    val systemSnapshot: Map<String, Float>,
    val connected: Boolean
)
