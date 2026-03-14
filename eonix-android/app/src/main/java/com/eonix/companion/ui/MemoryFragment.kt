package com.eonix.companion.ui

import android.app.AlertDialog
import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.eonix.companion.data.MemoryItem

class MemoryFragment : Fragment() {
    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(android.R.layout.simple_list_item_1, container, false)
    }

    fun showMemoryDialog(view: View, item: MemoryItem) {
        AlertDialog.Builder(view.context)
            .setTitle("${item.category} • importance ${item.importance}")
            .setMessage(item.text)
            .setPositiveButton("Close", null)
            .show()
    }

    companion object {
        fun asChipText(item: MemoryItem): String {
            val preview = if (item.text.length > 30) item.text.take(30) + "..." else item.text
            return "📌 ${item.category} $preview"
        }

        fun styleChip(tv: TextView) {
            tv.setBackgroundColor(Color.parseColor("#1A1A2E"))
            tv.setTextColor(Color.parseColor("#00FF88"))
            tv.setPadding(28, 14, 28, 14)
        }
    }
}
