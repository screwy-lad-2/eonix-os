package com.eonix.companion

import android.app.Application
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.viewModels
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.lifecycleScope
import com.eonix.companion.data.EonixRepository
import com.eonix.companion.data.GoalResponse
import com.eonix.companion.data.MemoryItem
import com.eonix.companion.data.SyncStatusResponse
import com.eonix.companion.ui.GoalCard
import com.eonix.companion.ui.MemoryFragment
import com.eonix.companion.ui.StatusBar
import com.eonix.companion.voice.VoiceBridge
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private val vm: EonixViewModel by viewModels()
    private lateinit var voiceBridge: VoiceBridge

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        voiceBridge = VoiceBridge(this)

        val swipe = findViewById<androidx.swiperefreshlayout.widget.SwipeRefreshLayout>(R.id.swipeRefresh)
        val offlineBanner = findViewById<TextView>(R.id.offlineBanner)
        val topTitle = findViewById<TextView>(R.id.topTitle)
        val deviceId = findViewById<TextView>(R.id.deviceId)
        val dot = findViewById<android.view.View>(R.id.connectionDot)
        val goalTitle = findViewById<TextView>(R.id.goalTitle)
        val goalSubtitle = findViewById<TextView>(R.id.goalSubtitle)
        val goalProgress = findViewById<android.widget.ProgressBar>(R.id.goalProgress)
        val lastUpdated = findViewById<TextView>(R.id.lastUpdated)
        val memoryStrip = findViewById<LinearLayout>(R.id.memoryStrip)
        val systemStatus = findViewById<TextView>(R.id.systemStatus)

        swipe.setOnRefreshListener {
            lifecycleScope.launch {
                vm.refresh()
                swipe.isRefreshing = false
            }
        }

        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnSpeak).setOnClickListener {
            voiceBridge.startListening { transcript ->
                lifecycleScope.launch {
                    val reply = vm.sendCommand(transcript)
                    voiceBridge.speak(reply)
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Eon Reply")
                        .setMessage("You: $transcript\n\nEon: $reply")
                        .setPositiveButton("OK", null)
                        .show()
                }
            }
        }

        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnSyncNow).setOnClickListener {
            lifecycleScope.launch { vm.syncNow() }
        }

        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnNewGoal).setOnClickListener {
            showNewGoalDialog()
        }

        vm.activeGoal.observe(this) { goal ->
            GoalCard.bind(goal, goalTitle, goalSubtitle, goalProgress, lastUpdated)
        }

        vm.systemSnapshot.observe(this) { snapshot ->
            StatusBar.renderSnapshot(systemStatus, snapshot)
        }

        vm.memorySummary.observe(this) { items ->
            renderMemoryChips(memoryStrip, items)
        }

        vm.syncStatus.observe(this) { sync ->
            val did = sync?.device_id ?: "unknown"
            topTitle.text = "⚡ EONIX"
            deviceId.text = did
        }

        vm.isConnected.observe(this) { connected ->
            dot.setBackgroundColor(if (connected) Color.parseColor("#00FF88") else Color.parseColor("#FF4444"))
            offlineBanner.visibility = if (connected) android.view.View.GONE else android.view.View.VISIBLE
        }

        lifecycleScope.launch {
            while (true) {
                vm.refresh()
                delay(30_000)
            }
        }
    }

    private fun showNewGoalDialog() {
        val nameInput = EditText(this).apply { hint = "Goal name" }
        val descInput = EditText(this).apply { hint = "Description" }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 24, 40, 0)
            addView(nameInput)
            addView(descInput)
        }

        AlertDialog.Builder(this)
            .setTitle("Create Goal")
            .setView(root)
            .setPositiveButton("Create") { _, _ ->
                lifecycleScope.launch {
                    vm.createGoal(nameInput.text.toString(), descInput.text.toString())
                    vm.refresh()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun renderMemoryChips(container: LinearLayout, items: List<MemoryItem>) {
        container.removeAllViews()
        val mf = MemoryFragment()
        items.forEach { item ->
            val chip = TextView(this)
            chip.text = MemoryFragment.asChipText(item)
            MemoryFragment.styleChip(chip)
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.marginEnd = 12
            chip.layoutParams = lp
            chip.gravity = Gravity.CENTER_VERTICAL
            chip.setOnClickListener { mf.showMemoryDialog(chip, item) }
            container.addView(chip)
        }
    }
}

class EonixViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = EonixRepository(app.applicationContext)

    private val _activeGoal = MutableLiveData<GoalResponse?>(null)
    val activeGoal: LiveData<GoalResponse?> = _activeGoal

    private val _memorySummary = MutableLiveData<List<MemoryItem>>(emptyList())
    val memorySummary: LiveData<List<MemoryItem>> = _memorySummary

    private val _syncStatus = MutableLiveData<SyncStatusResponse?>(null)
    val syncStatus: LiveData<SyncStatusResponse?> = _syncStatus

    private val _systemSnapshot = MutableLiveData<Map<String, Float>>(emptyMap())
    val systemSnapshot: LiveData<Map<String, Float>> = _systemSnapshot

    private val _isConnected = MutableLiveData(false)
    val isConnected: LiveData<Boolean> = _isConnected

    suspend fun refresh() {
        val out = repo.refreshAll()
        _activeGoal.postValue(out.activeGoal)
        _memorySummary.postValue(out.memory)
        _syncStatus.postValue(out.syncStatus)
        _systemSnapshot.postValue(out.systemSnapshot)
        _isConnected.postValue(out.connected)
    }

    suspend fun sendCommand(text: String): String = repo.sendVoiceCommand(text)

    suspend fun createGoal(name: String, desc: String): Boolean = repo.createGoal(name, desc)

    suspend fun syncNow(): Boolean = repo.syncNow()
}
