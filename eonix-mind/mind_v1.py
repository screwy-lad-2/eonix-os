#!/usr/bin/env python3
"""EONIX MIND v1.0 with system reader, context, goals, and persistent memory."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from system_reader import EonixSystemReader

try:
    from memory import EonixMemory
except Exception:
    EonixMemory = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_GGUF = REPO_ROOT / "models" / "gguf" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
CONTEXT_BASE = "http://127.0.0.1:7736"
GOAL_BASE = "http://127.0.0.1:7735"
ACTIVE_GOAL_FILE = Path.home() / ".eonix" / "active_goal.txt"


SYSTEM_PROMPT = (
    "You are Eon, the AI assistant built into Eonix OS.\n"
    "You have real-time system data provided below.\n"
    "Rules:\n"
    "- Respond in max 2 sentences\n"
    "- Use actual numbers from system data - never invent\n"
    "- Respond in the SAME language as the user\n"
    "- If asked to act (close app, commit): say what command to run\n"
    "- Be direct. No filler."
)


class _FallbackLLM:
    def __call__(self, prompt: str, max_tokens: int = 128):
        return "I am running in fallback mode. Install llama-cpp-python and the GGUF model for full responses."


def _http_json(url: str, timeout: int = 2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _http_post_json(url: str, payload: Dict, timeout: int = 3):
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def context_agent_status() -> Dict:
    return _http_json(f"{CONTEXT_BASE}/context/status") or {}


def context_agent_summary(hours: int = 2) -> str:
    q = urllib.parse.urlencode({"hours": hours})
    payload = _http_json(f"{CONTEXT_BASE}/context/summary?{q}")
    if isinstance(payload, dict):
        return str(payload.get("summary") or "")
    return ""


def context_agent_recent(n: int = 5):
    q = urllib.parse.urlencode({"n": n})
    payload = _http_json(f"{CONTEXT_BASE}/context/recent?{q}")
    return payload if isinstance(payload, list) else []


def context_agent_search(query: str, n: int = 3):
    q = urllib.parse.urlencode({"q": query, "n": n})
    payload = _http_json(f"{CONTEXT_BASE}/context/search?{q}")
    return payload if isinstance(payload, list) else []


def goal_active() -> Dict:
    payload = _http_json(f"{GOAL_BASE}/goal/active")
    return payload if isinstance(payload, dict) else {}


def goal_create(name: str, description: str = "") -> Dict:
    payload = _http_post_json(f"{GOAL_BASE}/goal/create", {"name": name, "description": description})
    return payload if isinstance(payload, dict) else {}


def goal_complete(goal_id: str) -> Dict:
    payload = _http_post_json(f"{GOAL_BASE}/goal/complete", {"goal_id": goal_id})
    return payload if isinstance(payload, dict) else {}


def goal_progress(goal_id: str) -> float:
    payload = _http_json(f"{GOAL_BASE}/goal/progress/{urllib.parse.quote(goal_id)}")
    if isinstance(payload, dict):
        try:
            return float(payload.get("progress", 0.0))
        except Exception:
            return 0.0
    return 0.0


def _goal_line() -> str:
    active = goal_active()
    if active and active.get("id"):
        prog = goal_progress(str(active["id"]))
        return f"Goal: {active.get('name', 'unnamed')} - {int(prog * 100)}% complete"

    if ACTIVE_GOAL_FILE.exists():
        name = ACTIVE_GOAL_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        if name:
            return f"Goal: {name} - progress unavailable"
    return "Goal: none"


def build_system_context(reader: EonixSystemReader, memory: Optional[EonixMemory] = None) -> Dict:
    data = reader.read_all()
    summary = reader.format_for_llm(data)
    recent_activity = context_agent_summary(hours=2)
    goal_line = _goal_line()

    mem_stats = ""
    if memory is not None:
        try:
            mem_stats = f"Memory entries: {memory.stats().get('total_memories', 0)}"
        except Exception:
            mem_stats = ""

    combined = summary + f"\n{goal_line}"
    if mem_stats:
        combined += f"\n{mem_stats}"

    return {
        "raw": data,
        "summary": combined,
        "recent_activity": recent_activity,
        "goal_line": goal_line,
    }


def record_audio_5s(path: Path, sample_rate: int = 16000) -> None:
    try:
        import pyaudio
    except Exception as e:
        raise RuntimeError("pyaudio not installed. Install with pip install pyaudio") from e

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=1024,
    )
    frames = []
    for _ in range(0, int(sample_rate / 1024 * 5)):
        frames.append(stream.read(1024))

    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))


def _is_silence(audio_path: Path, threshold: float = 150.0) -> bool:
    with wave.open(str(audio_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if data.size == 0:
        return True
    rms = float(np.sqrt(np.mean(np.square(data))))
    return rms < threshold


def transcribe_audio(audio_path: Path) -> Tuple[str, str]:
    if _is_silence(audio_path):
        return "", "en"

    try:
        from faster_whisper import WhisperModel
    except Exception:
        return "", "en"

    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), language=None)
    text = " ".join([s.text.strip() for s in segments]).strip()
    lang = getattr(info, "language", "en") or "en"
    return text, lang


def load_llama():
    try:
        from llama_cpp import Llama
    except Exception:
        return _FallbackLLM()
    if not MODEL_GGUF.exists():
        return _FallbackLLM()
    return Llama(model_path=str(MODEL_GGUF), n_ctx=2048, n_threads=4, verbose=False)


def _save_memory_trigger(memory: Optional[EonixMemory], user_text: str) -> Optional[str]:
    if memory is None:
        return None

    text_l = user_text.lower().strip()
    try:
        if text_l.startswith("remember that"):
            payload = user_text.split("remember that", 1)[-1].strip()
            if payload:
                memory.remember(payload, category="general", importance=2)
                return "Noted. I'll remember that."

        if "my deadline is" in text_l:
            memory.remember(user_text, category="deadline", importance=3)
            return "Got it. I saved your deadline."

        if text_l.startswith("i prefer"):
            memory.remember(user_text, category="preference", importance=2)
            return "Preference saved."

        if text_l.startswith("note that"):
            payload = user_text.split("note that", 1)[-1].strip()
            if payload:
                memory.remember(payload, category="fact", importance=2)
                return "Done. I saved that note."
    except Exception:
        return None

    return None


def _extract_goal_name(user_text: str) -> str:
    t = user_text.strip()
    t = re.sub(r"^(set goal|new goal)\s*[:\-]?\s*", "", t, flags=re.I)
    return t.strip()


def _handle_goal_command(user_text: str) -> Optional[str]:
    text_l = user_text.lower().strip()

    if text_l.startswith("set goal") or text_l.startswith("new goal"):
        name = _extract_goal_name(user_text)
        if not name:
            return "Please tell me the goal name."
        created = goal_create(name)
        if created.get("id"):
            return f"Goal set: {created.get('name', name)}. I will track your progress."
        return "I could not reach GoalEngine right now."

    if "what goal am i working on" in text_l or "mera goal kya hai" in text_l:
        active = goal_active()
        if active.get("id"):
            p = goal_progress(str(active["id"]))
            return f"You're working on {active.get('name', 'an active goal')}, currently {int(p * 100)} percent complete."
        return "No active goal right now. Say set goal and the goal name."

    if "how much progress on my goal" in text_l:
        active = goal_active()
        if active.get("id"):
            p = goal_progress(str(active["id"]))
            return f"You are {int(p * 100)} percent through {active.get('name', 'your goal')} based on recent activity."
        return "I cannot estimate progress without an active goal."

    if "mark goal complete" in text_l or "goal complete karo" in text_l:
        active = goal_active()
        if active.get("id"):
            out = goal_complete(str(active["id"]))
            if out.get("ok"):
                return f"Goal complete: {active.get('name', 'done')}."
            return "I could not mark the goal complete right now."
        return "No active goal to complete."

    return None


def generate_response(llm, context: Dict, user_text: str, lang: str, memory: Optional[EonixMemory] = None) -> str:
    text_l = user_text.lower()

    goal_cmd = _handle_goal_command(user_text)
    if goal_cmd:
        return goal_cmd

    if "what do you remember about" in text_l or "kya yaad hai" in text_l:
        if memory is None:
            return "Memory service is unavailable right now."
        q = user_text.split("about", 1)[-1].strip() if "about" in text_l else user_text
        found = memory.recall(q, n=5)
        if not found:
            return "I do not have memory entries for that yet."
        top = found[:3]
        return "I remember: " + " | ".join([x["text"] for x in top])

    if "what was i doing" in text_l or "kya kar raha tha" in text_l:
        recent = context_agent_recent(5)
        if recent:
            return "You recently: " + "; ".join([f"{e.get('type','event')}" for e in recent[:5]])
        return "I could not find recent tracked activity right now."

    if "find my work on" in text_l:
        topic = user_text.split("find my work on", 1)[-1].strip() or "recent work"
        matches = context_agent_search(topic, 3)
        if matches:
            return "Top matches: " + "; ".join([str(m)[:80] for m in matches])
        return f"I did not find context matches for {topic}."

    if ("what is my" in text_l or "what's my" in text_l) and memory is not None:
        found = memory.recall(user_text, n=3)
        if found:
            return found[0]["text"]

    save_reply = _save_memory_trigger(memory, user_text)
    if save_reply:
        return save_reply

    memory_context = ""
    if memory is not None:
        try:
            memory_context = memory.format_relevant(user_text)
        except Exception:
            memory_context = ""

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"System Snapshot:\n{context.get('summary','')}\n"
        f"Recent activity: {context.get('recent_activity','none')}\n"
    )
    if memory_context:
        prompt += f"From my memory: {memory_context}\n"
    prompt += f"\nUser ({lang}): {user_text}\nEon:"

    if isinstance(llm, _FallbackLLM):
        return llm(prompt)

    out = llm(prompt, max_tokens=120, stop=["\nUser:"])
    text = out["choices"][0]["text"].strip()
    return text if text else "I could not generate a response right now."


def speak(text: str, lang: str) -> None:
    try:
        from kokoro import KPipeline  # type: ignore
    except Exception:
        print(f"[TTS fallback] {text}")
        return

    voice = "hi" if lang == "hi" else "en"
    pipeline = KPipeline(lang_code=voice)
    for _, _, audio in pipeline(text, voice=voice):
        try:
            import sounddevice as sd

            sd.play(audio, samplerate=24000)
            sd.wait()
        except Exception:
            print(f"[TTS fallback] {text}")
            break


def _proactive_alerts(last_deadlock: str, last_alert: str, context_raw: Dict) -> Tuple[str, str, List[str]]:
    alerts: List[str] = []
    ram_percent = float(context_raw.get("ram", {}).get("percent", 0.0))
    if ram_percent > 85:
        alerts.append(f"Alert: RAM usage is high at {ram_percent:.0f}%.")

    dead = str(context_raw.get("deadlock_log", "unavailable"))
    if dead not in {"", "unavailable"} and dead != last_deadlock:
        alerts.append(f"New deadlock event: {dead}")
        last_deadlock = dead

    sec = context_raw.get("security_alerts", [])
    sec_last = sec[-1] if isinstance(sec, list) and sec else ""
    if sec_last and sec_last != last_alert:
        alerts.append(f"New security alert: {sec_last}")
        last_alert = sec_last

    return last_deadlock, last_alert, alerts


def main() -> None:
    reader = EonixSystemReader()
    llm = load_llama()

    memory = None
    if EonixMemory is not None:
        try:
            memory = EonixMemory()
            stats = memory.stats()
            print(f"✅ Memory: {stats.get('total_memories', 0)} memories loaded")
        except Exception:
            print("⚠️ Memory unavailable")
    else:
        print("⚠️ Memory module unavailable")

    active = goal_active()
    if active.get("id"):
        p = goal_progress(str(active["id"]))
        print(f"🎯 Active goal: {active.get('name', 'unnamed')} ({int(p * 100)}%)")
    else:
        print("💡 No active goal - say Hey Eon set a goal")

    status = context_agent_status()
    if status:
        print("✅ ContextAgent connected")
    else:
        print("⚠️ ContextAgent offline - context limited")

    startup = build_system_context(reader, memory=memory)
    print("⚡ Eon ready - press ENTER to speak (type 'exit' to quit)")
    print(startup["summary"])

    last_deadlock = ""
    last_alert = ""
    while True:
        snapshot = build_system_context(reader, memory=memory)
        last_deadlock, last_alert, alerts = _proactive_alerts(last_deadlock, last_alert, snapshot["raw"])
        for a in alerts:
            print(f"Eon: {a}")
            speak(a, "en")

        cmd = input().strip().lower()
        if cmd == "exit":
            break

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = Path(tmp.name)

        try:
            record_audio_5s(audio_path)
            text, lang = transcribe_audio(audio_path)
            if not text:
                print("Didn't catch that")
                continue

            context = build_system_context(reader, memory=memory)
            response = generate_response(llm, context, text, lang, memory=memory)
            print(f"Eon: {response}")
            speak(response, lang)
        finally:
            if audio_path.exists():
                audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()


def test_system_context_has_all_required_keys():
    reader = EonixSystemReader()
    ctx = build_system_context(reader)
    assert {"raw", "summary", "recent_activity"}.issubset(set(ctx.keys()))


def test_llama_loads_without_error():
    model = load_llama()
    assert model is not None


def test_whisper_transcribes_silence_as_empty_string(tmp_path):
    wav_path = tmp_path / "silence.wav"
    sample_rate = 16000
    silence = (np.zeros(sample_rate * 2)).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(silence.tobytes())

    text, _ = transcribe_audio(wav_path)
    assert text == ""
