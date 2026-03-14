#!/usr/bin/env python3
"""EONIX MIND v1.0 - first voice interaction pipeline."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_GGUF = REPO_ROOT / "models" / "gguf" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
SCHED_META = REPO_ROOT / "models" / "onnx" / "model_metadata.json"
SECURITY_ALERTS = Path.home() / ".eonix" / "security_alerts.log"
DEADLOCK_LOG = Path("/proc/eonix/deadlock_log")


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


def _safe_read_last_line(path: Path) -> str:
    try:
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return lines[-1] if lines else "N/A"
    except Exception:
        return "N/A"
    return "N/A"


def _get_last_commit_message() -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(REPO_ROOT), "log", "-1", "--pretty=%s"], text=True)
        return out.strip() or "N/A"
    except Exception:
        return "N/A"


def _get_repo_name() -> str:
    return REPO_ROOT.name


def _get_scheduler_meta() -> Dict:
    if not SCHED_META.exists():
        return {"version": "N/A", "top3": "N/A"}
    try:
        data = json.loads(SCHED_META.read_text(encoding="utf-8"))
        return {"version": data.get("version", "N/A"), "top3": data.get("top3", "N/A")}
    except Exception:
        return {"version": "N/A", "top3": "N/A"}


def build_system_context() -> Dict:
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    top5 = sorted(psutil.process_iter(["name", "memory_info"]), key=lambda p: (p.info["memory_info"].rss if p.info["memory_info"] else 0), reverse=True)[:5]

    top5_ram = []
    for p in top5:
        try:
            mb = (p.info["memory_info"].rss / (1024 * 1024)) if p.info["memory_info"] else 0
            top5_ram.append({"name": p.info.get("name") or "unknown", "ram_mb": round(mb, 2)})
        except Exception:
            continue

    meta = _get_scheduler_meta()
    return {
        "top5_processes_ram": top5_ram,
        "ram": {
            "used_gb": round(vm.used / (1024**3), 2),
            "total_gb": round(vm.total / (1024**3), 2),
            "percent": vm.percent,
        },
        "cpu_percent_1s": psutil.cpu_percent(interval=1),
        "disk": {
            "used_gb": round(du.used / (1024**3), 2),
            "total_gb": round(du.total / (1024**3), 2),
        },
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 2),
        "repo_name": _get_repo_name(),
        "last_commit_message": _get_last_commit_message(),
        "scheduler_model": {
            "version": meta["version"],
            "top3": meta["top3"],
        },
        "latest_deadlock_event": _safe_read_last_line(DEADLOCK_LOG),
        "latest_security_alert": _safe_read_last_line(SECURITY_ALERTS),
        "timestamp": datetime.utcnow().isoformat(),
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
    except Exception as e:
        raise RuntimeError("faster-whisper not installed") from e

    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), language=None)
    text = " ".join([s.text.strip() for s in segments]).strip()
    lang = getattr(info, "language", "en") or "en"
    return text, lang


class _FallbackLLM:
    def __call__(self, prompt: str, max_tokens: int = 128):
        return "I am running in fallback mode. Install llama-cpp-python and the GGUF model for full responses."


def load_llama():
    try:
        from llama_cpp import Llama
    except Exception:
        return _FallbackLLM()
    if not MODEL_GGUF.exists():
        return _FallbackLLM()
    return Llama(model_path=str(MODEL_GGUF), n_ctx=2048, n_threads=4, verbose=False)


def generate_response(llm, context: Dict, user_text: str, lang: str) -> str:
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"User ({lang}): {user_text}\nEon:"
    )
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


def main() -> None:
    llm = load_llama()
    print("⚡ Eon ready - press ENTER to speak (type 'exit' to quit)")

    while True:
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

            context = build_system_context()
            response = generate_response(llm, context, text, lang)
            print(f"Eon: {response}")
            speak(response, lang)
        finally:
            if audio_path.exists():
                audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()


def test_system_context_has_all_required_keys():
    ctx = build_system_context()
    required = {
        "top5_processes_ram",
        "ram",
        "cpu_percent_1s",
        "disk",
        "uptime_hours",
        "repo_name",
        "last_commit_message",
        "scheduler_model",
        "latest_deadlock_event",
        "latest_security_alert",
    }
    assert required.issubset(set(ctx.keys()))


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
