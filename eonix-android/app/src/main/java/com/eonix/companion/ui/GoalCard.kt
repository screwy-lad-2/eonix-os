package com.eonix.companion.ui

import android.animation.ObjectAnimator
import android.widget.ProgressBar
import android.widget.TextView
import com.eonix.companion.data.GoalResponse

object GoalCard {
    fun bind(goal: GoalResponse?, title: TextView, subtitle: TextView, progress: ProgressBar, updated: TextView) {
        if (goal == null) {
            title.text = "No active goal"
            subtitle.text = "0% complete"
            animateProgress(progress, 0)
            updated.text = "synced just now"
            return
        }

        val pct = (goal.progress * 100f).toInt().coerceIn(0, 100)
        title.text = goal.name.ifBlank { "Unnamed goal" }
        subtitle.text = "$pct% complete"
        animateProgress(progress, pct)
        updated.text = "status: ${goal.status}"
    }

    private fun animateProgress(progress: ProgressBar, target: Int) {
        val animator = ObjectAnimator.ofInt(progress, "progress", progress.progress, target)
        animator.duration = 500
        animator.start()
    }
}
