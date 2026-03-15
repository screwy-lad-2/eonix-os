#!/usr/bin/env python3
"""EONIX MIND v2.0 full integration entrypoint."""

from __future__ import annotations

import argparse
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np

try:
    from system_reader import EonixSystemReader
except Exception:
    from eonix_mind.system_reader import EonixSystemReader

try:
    from proactive_monitor import ProactiveMonitor
except Exception:
    from eonix_mind.proactive_monitor import ProactiveMonitor

try:
    from memory import EonixMemory
except Exception:
    try:
        from eonix_mind.memory import EonixMemory
    except Exception:
        EonixMemory = None  # type: ignore


CONTEXT_BASE = "http://127.0.0.1:7736"
GOAL_BASE = "http://127.0.0.1:7735"
RESOURCE_BASE = "http://127.0.0.1:7737"
SYNC_BASE = "http://127.0.0.1:7740"
HUB_BASE = "http://127.0.0.1:7750"
ACTIVE_GOAL_FILE = Path.home() / ".eonix" / "active_goal.txt"


def _desktop_window_count() -> int:
    p = Path.home() / ".eonix" / "sessions"
    active_goal = ""
    if ACTIVE_GOAL_FILE.exists():
        active_goal = ACTIVE_GOAL_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    if not active_goal:
        return 0
    # Best-effort count by scanning latest session file matching goal text.
    for file in sorted(p.glob("*.json"), reverse=True):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            if str(payload.get("goal_name", "")).strip() == active_goal:
                return len(payload.get("windows", []))
        except Exception:
            continue
    return 0


class _FallbackLLM:
    def __call__(self, _prompt: str, max_tokens: int = 128):
        return "Fallback response: LLaMA not available."


def _http_json(url: str, timeout: int = 3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _http_post_json(url: str, payload: Dict, timeout: int = 4):
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _token_count(text: str) -> int:
    return len(text.split())


def _trim_tokens(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit])


def _goal_active() -> Dict:
    payload = _http_json(f"{GOAL_BASE}/goal/active")
    return payload if isinstance(payload, dict) else {}


def _goal_progress(goal_id: str) -> float:
    payload = _http_json(f"{GOAL_BASE}/goal/progress/{urllib.parse.quote(goal_id)}")
    if isinstance(payload, dict):
        try:
            return float(payload.get("progress", 0.0))
        except Exception:
            return 0.0
    return 0.0


def _resource_status() -> Dict:
    payload = _http_json(f"{RESOURCE_BASE}/resource/status")
    return payload if isinstance(payload, dict) else {}


def _sync_status() -> Dict:
    payload = _http_json(f"{SYNC_BASE}/sync/status")
    return payload if isinstance(payload, dict) else {}


def _sync_peers() -> list:
    payload = _http_json(f"{SYNC_BASE}/sync/peers")
    return payload if isinstance(payload, list) else []


def _sync_state() -> Dict:
    payload = _http_json(f"{SYNC_BASE}/sync/state")
    return payload if isinstance(payload, dict) else {}


def _sync_push() -> Dict:
    payload = _http_post_json(f"{SYNC_BASE}/sync/push", payload={})
    return payload if isinstance(payload, dict) else {}


def _hub_status() -> Dict:
    payload = _http_json(f"{HUB_BASE}/hub/status", timeout=1)
    return payload if isinstance(payload, dict) else {}


def _context_summary() -> str:
    q = urllib.parse.urlencode({"hours": 2})
    payload = _http_json(f"{CONTEXT_BASE}/context/summary?{q}")
    if isinstance(payload, dict):
        return str(payload.get("summary") or "")
    return ""


def load_llama():
    model_path = Path(__file__).resolve().parents[1] / "models" / "gguf" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    try:
        from llama_cpp import Llama  # type: ignore

        if model_path.exists():
            return Llama(model_path=str(model_path), n_ctx=4096, n_threads=4, verbose=False)
    except Exception:
        pass
    return _FallbackLLM()


def transcribe_audio(audio_path: Path) -> tuple[str, str]:
    try:
        with wave.open(str(audio_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        if data.size == 0 or float(np.sqrt(np.mean(np.square(data)))) < 120.0:
            return "", "en"
    except Exception:
        return "", "en"

    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("medium", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), language=None)
        text = " ".join([s.text.strip() for s in segments]).strip()
        lang = getattr(info, "language", "en") or "en"
        return text, lang
    except Exception:
        return "", "en"


def speak(text: str, lang: str = "en") -> None:
    try:
        from kokoro import KPipeline  # type: ignore

        pipeline = KPipeline(lang_code="hi" if lang == "hi" else "en")
        for _, _, audio in pipeline(text, voice=("hi" if lang == "hi" else "en")):
            try:
                import sounddevice as sd  # type: ignore

                sd.play(audio, samplerate=24000)
                sd.wait()
            except Exception:
                print(f"[TTS fallback] {text}")
                break
    except Exception:
        print(f"[TTS fallback] {text}")


class EonixMindV2:
    def __init__(
        self,
        reader: Optional[Any] = None,
        memory: Optional[object] = None,
        llm: Optional[object] = None,
        speaker: Optional[Callable[[str, str], None]] = None,
    ):
        self.reader = reader or EonixSystemReader()
        self.memory = memory
        if self.memory is None and EonixMemory is not None:
            try:
                self.memory = EonixMemory()
            except Exception:
                self.memory = None

        self.llm = llm or load_llama()
        self.speaker = speaker or speak
        self.monitor = ProactiveMonitor(speak_fn=lambda msg: self.speaker(msg, "en"), memory=self.memory)

    def startup_status(self) -> Dict:
        system = self.reader.read_all()
        model = system.get("model_version", {}) if isinstance(system, dict) else {}
        goal = _goal_active()
        gid = str(goal.get("id") or "")
        progress = _goal_progress(gid) if gid else 0.0
        memory_count = 0
        if self.memory is not None and hasattr(self.memory, "stats"):
            try:
                memory_count = int(self.memory.stats().get("total_memories", 0))
            except Exception:
                memory_count = 0

        resource = _resource_status()
        sync = _sync_status()
        return {
            "ram": system.get("ram", {}),
            "cpu": system.get("cpu", {}),
            "goal": goal,
            "goal_progress": progress,
            "model": model,
            "memory_count": memory_count,
            "resource": resource,
            "sync": sync,
            "proactive_rules": 7,
        }

    def startup_banner(self) -> str:
        s = self.startup_status()
        ram = s.get("ram", {})
        cpu = s.get("cpu", {})
        goal = s.get("goal", {})
        model = s.get("model", {})
        goal_name = goal.get("name", "none")
        goal_pct = int(float(s.get("goal_progress", 0.0)) * 100)
        top3 = float(model.get("top3") or 0.0) * 100.0
        resource_scored = int(s.get("resource", {}).get("processes_scored", 0)) if isinstance(s.get("resource"), dict) else 0
        sync = s.get("sync", {}) if isinstance(s.get("sync"), dict) else {}
        sync_id = str(sync.get("device_id") or "").strip()
        sync_peers = int(sync.get("peers_found", 0) or 0)
        sync_text = f"Sync: {sync_id} ({sync_peers} peers)" if sync_id else "Sync: standalone mode"
        hub = _hub_status()
        hub_text = ""
        if isinstance(hub, dict) and hub:
            hub_text = "Hub: http://localhost:7750 (open in browser)\n"
        desktop_windows = _desktop_window_count()
        session_goal = str(goal_name)
        return (
            "═══════════════════════════════\n"
            "⚡ EONIX MIND v2.0 - ONLINE\n"
            "═══════════════════════════════\n"
            f"RAM: {ram.get('used_gb', 0)}/{ram.get('total_gb', 0)}GB | CPU: {cpu.get('percent_1s', 0):.0f}%\n"
            f"Goal: {goal_name} ({goal_pct}%)\n"
            f"Model: {model.get('version', 'n/a')} ({top3:.2f}% Top-3)\n"
            f"Memory: {s.get('memory_count', 0)} memories\n"
            f"Resources: {resource_scored} processes scored\n"
            f"Desktop: {desktop_windows} windows | session: {session_goal}\n"
            f"{sync_text}\n"
            f"{hub_text}"
            f"Proactive: {s.get('proactive_rules', 7)} rules active\n"
            "───────────────────────────────\n"
            "Say 'Hey Eon' or press ENTER"
        )

    def build_context_injection(self, query: str) -> Dict:
        system_text = _trim_tokens(self.reader.format_for_llm(self.reader.read_all()), 300)
        memory_text = ""
        if self.memory is not None and hasattr(self.memory, "format_relevant"):
            try:
                memory_text = _trim_tokens(str(self.memory.format_relevant(query)), 150)
            except Exception:
                memory_text = ""

        context_text = _trim_tokens(_context_summary(), 100)
        goal = _goal_active()
        gid = str(goal.get("id") or "")
        progress = _goal_progress(gid) if gid else 0.0
        goal_text = _trim_tokens(f"Goal: {goal.get('name', 'none')} ({int(progress * 100)}%)", 50)

        sync_status = _sync_status()
        sync_peers_text = ""
        cross_goal_text = ""
        if isinstance(sync_status, dict) and int(sync_status.get("peers_found", 0) or 0) > 0:
            peers = _sync_peers()
            peer_names = [str(p.get("device_id", "")).strip() for p in peers if isinstance(p, dict)]
            peer_names = [p for p in peer_names if p]
            if peer_names:
                sync_peers_text = _trim_tokens(f"Synced with: {', '.join(peer_names[:6])}", 50)

            s = _sync_state()
            if isinstance(s, dict):
                cross_goal = s.get("active_goal") if isinstance(s.get("active_goal"), dict) else {}
                cross_name = str(cross_goal.get("name") or "").strip()
                if cross_name:
                    cross_goal_text = _trim_tokens(f"Cross-device goal: {cross_name}", 30)

        combined = "\n".join(
            [x for x in [system_text, memory_text, context_text, goal_text, sync_peers_text, cross_goal_text] if x.strip()]
        )
        return {
            "system": system_text,
            "memory": memory_text,
            "context": context_text,
            "goal": goal_text,
            "sync": sync_peers_text,
            "cross_goal": cross_goal_text,
            "combined": combined,
            "tokens": _token_count(combined),
        }

    def route_command(self, user_text: str) -> str:
        t = user_text.lower().strip()

        if "goal" in t:
            active = _goal_active()
            gid = str(active.get("id") or "")
            p = _goal_progress(gid) if gid else 0.0
            if not gid:
                return "No active goal right now."
            return f"Goal {active.get('name', 'unnamed')} is at {int(p * 100)}%."

        if "remember" in t and self.memory is not None and hasattr(self.memory, "remember"):
            payload = user_text.split("remember", 1)[-1].strip()
            if payload:
                self.memory.remember(payload, category="general", importance=2)
                return "Saved to memory."

        if "deadline" in t and self.memory is not None and hasattr(self.memory, "recall"):
            rows = self.memory.recall("deadline", n=3)
            if rows:
                return rows[0].get("text", "No deadline found.")
            return "No saved deadline found."

        if "security" in t:
            p = Path.home() / ".eonix" / "security_alerts.log"
            if p.exists():
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                return lines[-1] if lines else "No security alerts today."
            return "No security alerts today."

        if "deadlock" in t:
            p = Path("/proc/eonix/deadlock_log")
            if p.exists():
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                return lines[-1] if lines else "No deadlocks recorded."
            return "Deadlock log unavailable."

        if "scheduler" in t or "model version" in t:
            model = self.reader.read_all().get("model_version", {})
            return f"Scheduler model is {model.get('version', 'unknown')} with {(float(model.get('top3') or 0.0) * 100):.2f}% Top-3."

        device_phrases = [
            "what devices are connected",
            "what devices",
            "which devices",
            "connected devices",
            "kaun se device",
            "devices connected",
        ]
        if any(phrase in t for phrase in device_phrases):
            peers = _sync_peers()
            names = [str(p.get("device_id", "")).strip() for p in peers if isinstance(p, dict)]
            names = [n for n in names if n]
            if not names:
                return "No other Eonix devices are currently connected."
            return f"Found {len(names)} Eonix devices: {', '.join(names[:6])}."

        if "sync now" in t or "abhi sync karo" in t:
            out = _sync_push()
            pushed = int(out.get("pushed", 0) or 0) if isinstance(out, dict) else 0
            return f"Syncing brain state to all devices now. Pushed to {pushed} peers."

        if "what did i do on my other device" in t:
            payload = _sync_state()
            history = payload.get("sync_history", []) if isinstance(payload, dict) else []
            if not isinstance(history, list) or not history:
                return "No cross-device sync history available yet."
            recent = history[-3:]
            parts = []
            for item in recent:
                if not isinstance(item, dict):
                    continue
                src = str(item.get("from_device") or "unknown device")
                fields = item.get("fields_updated", [])
                if isinstance(fields, list) and fields:
                    parts.append(f"{src} updated {', '.join([str(f) for f in fields[:3]])}")
                else:
                    parts.append(f"{src} synced state")
            return "Recent cross-device activity: " + "; ".join(parts) + "."

        ctx = self.build_context_injection(user_text)
        prompt = (
            "You are Eon, concise and direct.\n"
            f"Context:\n{ctx['combined']}\n\n"
            f"User: {user_text}\nEon:"
        )
        if isinstance(self.llm, _FallbackLLM):
            return self.llm(prompt)
        try:
            out = self.llm(prompt, max_tokens=128, stop=["\nUser:"])
            return out["choices"][0]["text"].strip() or "I could not answer that right now."
        except Exception:
            return "I could not answer that right now."

    def start(self) -> None:
        sync = _sync_status()
        if isinstance(sync, dict) and sync.get("device_id"):
            print(
                f"🔗 Sync: {sync.get('device_id')} | {int(sync.get('peers_found', 0) or 0)} peers | "
                f"last sync: {sync.get('last_sync', '') or 'n/a'}"
            )
        else:
            print("🔗 Sync: standalone mode")
        print(self.startup_banner())
        self.monitor.start()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Eonix MIND v2")
    p.add_argument("--banner-only", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    mind = EonixMindV2()
    if args.banner_only:
        print(mind.startup_banner())
        return
    mind.start()

    while True:
        cmd = input().strip()
        if cmd.lower() in {"exit", "quit"}:
            mind.monitor.stop()
            break

        if not cmd:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = Path(tmp.name)
            try:
                # If voice stack is unavailable, user can type text directly.
                text, lang = transcribe_audio(wav_path)
                if not text:
                    print("No speech detected. Type your question.")
                    continue
                response = mind.route_command(text)
                print(f"Eon: {response}")
                mind.speaker(response, lang)
            finally:
                wav_path.unlink(missing_ok=True)
            continue

        response = mind.route_command(cmd)
        print(f"Eon: {response}")
        mind.speaker(response, "en")


if __name__ == "__main__":
    main()


class _DummyMemory:
    def __init__(self):
        self.saved = []

    def stats(self):
        return {"total_memories": len(self.saved)}

    def format_relevant(self, _q: str):
        return "OS exam on 2026-04-20"

    def remember(self, text: str, category: str = "general", importance: int = 1):
        self.saved.append((text, category, importance))

    def recall(self, _q: str, n: int = 3):
        return [{"text": "OS exam on 2026-04-20"}][:n]


def test_startup_banner_contains_all_sections(monkeypatch):
    class _R:
        def read_all(self):
            return {
                "ram": {"used_gb": 8.2, "total_gb": 16.0, "percent": 51},
                "cpu": {"percent_1s": 23.0},
                "model_version": {"version": "v1.1", "top3": 0.6161},
            }

        def format_for_llm(self, _d):
            return "system snapshot"

    monkeypatch.setattr("mind_v2._goal_active", lambda: {"id": "g1", "name": "Build EONIX MIND"})
    monkeypatch.setattr("mind_v2._goal_progress", lambda _gid: 0.34)
    monkeypatch.setattr("mind_v2._resource_status", lambda: {"processes_scored": 45})

    m = EonixMindV2(reader=_R(), memory=_DummyMemory(), llm=_FallbackLLM(), speaker=lambda _t, _l: None)
    banner = m.startup_banner()
    assert "EONIX MIND v2.0" in banner
    assert "Goal:" in banner
    assert "Memory:" in banner
    assert "Proactive:" in banner


def test_context_injection_under_600_tokens(monkeypatch):
    class _R:
        def read_all(self):
            return {"ram": {}, "cpu": {}, "model_version": {}}

        def format_for_llm(self, _d):
            return "x " * 500

    monkeypatch.setattr("mind_v2._context_summary", lambda: "y " * 500)
    monkeypatch.setattr("mind_v2._goal_active", lambda: {"id": "g1", "name": "Goal"})
    monkeypatch.setattr("mind_v2._goal_progress", lambda _gid: 0.5)

    m = EonixMindV2(reader=_R(), memory=_DummyMemory(), llm=_FallbackLLM(), speaker=lambda _t, _l: None)
    ctx = m.build_context_injection("deadline")
    assert int(ctx["tokens"]) <= 600


def test_command_routing_hits_correct_handler(monkeypatch):
    monkeypatch.setattr("mind_v2._goal_active", lambda: {"id": "g1", "name": "Build EONIX MIND"})
    monkeypatch.setattr("mind_v2._goal_progress", lambda _gid: 0.71)

    m = EonixMindV2(reader=EonixSystemReader(), memory=_DummyMemory(), llm=_FallbackLLM(), speaker=lambda _t, _l: None)
    out = m.route_command("What is my goal progress?")
    assert "71%" in out
