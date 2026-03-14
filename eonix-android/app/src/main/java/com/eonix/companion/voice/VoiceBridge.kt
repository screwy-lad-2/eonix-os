package com.eonix.companion.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import com.eonix.companion.network.EonixApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.withContext
import java.util.Locale

class VoiceBridge(private val context: Context) {
    private val api = EonixApiClient(context)
    private val tts = TextToSpeech(context) { status ->
        if (status == TextToSpeech.SUCCESS) tts.language = Locale("en", "IN")
    }
    private val db by lazy {
        Room.databaseBuilder(context, VoiceDb::class.java, "voice_chat.db").build()
    }

    fun startListening(onResult: (String) -> Unit) {
        val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onError(error: Int) = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit

            override fun onResults(results: Bundle?) {
                val transcript = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()
                    ?.trim()
                    .orEmpty()
                if (transcript.isNotBlank()) onResult(transcript)
                recognizer.destroy()
            }
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        }
        recognizer.startListening(intent)
    }

    suspend fun sendToDesktop(text: String): String = withContext(Dispatchers.IO) {
        try {
            val reply = withTimeoutOrNull(15_000) { api.sendVoiceCommand(text) } ?: "Desktop did not respond"
            db.chatDao().insert(ChatMessage(role = "user", text = text, ts = System.currentTimeMillis()))
            db.chatDao().insert(ChatMessage(role = "eon", text = reply, ts = System.currentTimeMillis()))
            db.chatDao().trimToLast50()
            reply
        } catch (_: Exception) {
            "Desktop did not respond"
        }
    }

    fun speak(text: String) {
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "eonix-reply")
    }
}

@Entity(tableName = "chat_history")
data class ChatMessage(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val role: String,
    val text: String,
    val ts: Long
)

@Dao
interface ChatDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(item: ChatMessage)

    @Query("SELECT * FROM chat_history ORDER BY ts DESC LIMIT 50")
    suspend fun latest(): List<ChatMessage>

    @Query("DELETE FROM chat_history WHERE id NOT IN (SELECT id FROM chat_history ORDER BY ts DESC LIMIT 50)")
    suspend fun trimToLast50()
}

@Database(entities = [ChatMessage::class], version = 1)
abstract class VoiceDb : RoomDatabase() {
    abstract fun chatDao(): ChatDao
}
