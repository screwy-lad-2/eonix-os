"""Eonix Voice Engine — offline voice commands + TTS.

Uses speech_recognition (Google Web Speech online, Sphinx offline fallback).
TTS via pyttsx3 → espeak-ng on Linux.
Wake word: "Hey Eonix"
"""
import threading
import queue

try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    sr = None
    SR_OK = False

try:
    import pyttsx3
    TTS_OK = True
except ImportError:
    pyttsx3 = None
    TTS_OK = False


class EonixVoice:
    """Offline voice engine for Eonix OS."""

    WAKE_WORDS = ["hey eonix", "eonix", "hey onyx", "a eonix"]

    def __init__(self, command_callback=None):
        self._cb = command_callback
        self._running = False
        self._q = queue.Queue()
        self._listening = False

        # TTS engine
        self._tts = None
        if TTS_OK:
            try:
                self._tts = pyttsx3.init()
                self._tts.setProperty("rate", 160)
                self._tts.setProperty("volume", 0.9)
                voices = self._tts.getProperty("voices")
                if voices:
                    self._tts.setProperty("voice", voices[0].id)
            except Exception as e:
                print(f"[VOICE] TTS init failed: {e}")
                self._tts = None

        # Speech recogniser
        self._rec = None
        if SR_OK:
            self._rec = sr.Recognizer()
            self._rec.energy_threshold = 300
            self._rec.pause_threshold = 0.8
            self._rec.dynamic_energy_threshold = True

    @property
    def is_available(self):
        return SR_OK and self._rec is not None

    @property
    def tts_available(self):
        return self._tts is not None

    @property
    def is_listening(self):
        return self._listening

    def speak(self, text):
        """Text-to-speech (non-blocking)."""
        if not self._tts:
            print(f"[VOICE TTS] {text}")
            return

        def _say():
            try:
                self._tts.say(text)
                self._tts.runAndWait()
            except Exception as e:
                print(f"[VOICE TTS] Error: {e}")

        threading.Thread(target=_say, daemon=True).start()

    def listen_once(self):
        """Listen for one utterance. Returns text or None."""
        if not SR_OK or not self._rec:
            return None
        self._listening = True
        try:
            with sr.Microphone() as src:
                self._rec.adjust_for_ambient_noise(src, duration=0.4)
                try:
                    audio = self._rec.listen(src, timeout=5, phrase_time_limit=8)
                except sr.WaitTimeoutError:
                    return None
            # Try online first
            try:
                return self._rec.recognize_google(audio).lower()
            except sr.UnknownValueError:
                return None
            except Exception:
                pass
            # Fallback: offline Sphinx
            try:
                return self._rec.recognize_sphinx(audio).lower()
            except Exception:
                return None
        except Exception as e:
            print(f"[VOICE] Listen error: {e}")
            return None
        finally:
            self._listening = False

    def start_wake_word_listener(self):
        """Background thread listens for wake word → calls _cb."""
        self._running = True
        threading.Thread(target=self._wake_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _wake_loop(self):
        self.speak("Eonix voice ready. Say: Hey Eonix.")
        while self._running:
            text = self.listen_once()
            if not text:
                continue
            if any(w in text for w in self.WAKE_WORDS):
                self.speak("Yes?")
                cmd = self.listen_once()
                if cmd:
                    self.speak(f"Running: {cmd}")
                    if self._cb:
                        self._cb(cmd)
                else:
                    self.speak("I didn't catch that. Try again.")

    def set_rate(self, wpm):
        """Set TTS speech rate (words per minute)."""
        if self._tts:
            self._tts.setProperty("rate", max(80, min(200, wpm)))

    def set_volume(self, vol):
        """Set TTS volume (0.0 to 1.0)."""
        if self._tts:
            self._tts.setProperty("volume", max(0.0, min(1.0, vol)))

    def test_microphone(self):
        """Test mic — returns True if audio captured."""
        if not SR_OK:
            return False
        try:
            with sr.Microphone() as src:
                self._rec.adjust_for_ambient_noise(src, duration=0.5)
            return True
        except Exception:
            return False
