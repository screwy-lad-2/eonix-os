#!/usr/bin/env python3
"""EonixShell: goal-aware interactive shell for EONIX OS sessions."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import psutil
from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter, WordCompleter
from prompt_toolkit.history import InMemoryHistory


HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
HISTORY_PATH = EONIX_DIR / "shell_history.txt"
SHELL_CONFIG_PATH = EONIX_DIR / "shell_config.json"
MODEL_METADATA_PATH = EONIX_DIR / "model_metadata.json"
MIND_MEMORY_DB = EONIX_DIR / "mind_memory" / "memory_fallback.db"

GOAL_BASE = "http://127.0.0.1:7735"
CONTEXT_BASE = "http://127.0.0.1:7736"
RESOURCE_BASE = "http://127.0.0.1:7737"
SYNC_BASE = "http://127.0.0.1:7740"
HUB_BASE = "http://127.0.0.1:7750"


try:
    import sqlite3
except Exception:
    sqlite3 = None

try:
    import importlib.util

    _MEMORY_PATH = Path(__file__).resolve().parents[1] / "eonix-mind" / "memory.py"
    _SPEC = importlib.util.spec_from_file_location("eonix_memory_module", str(_MEMORY_PATH))
    if _SPEC is not None and _SPEC.loader is not None:
        _MEMORY_MOD = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(_MEMORY_MOD)
        EonixMemory = _MEMORY_MOD.EonixMemory
    else:
        EonixMemory = None
except Exception:
    EonixMemory = None

try:
    from nl_interpreter import NLInterpreter, NLResult, INTENT_QUERY
except Exception:
    import importlib.util

    _NLI_PATH = Path(__file__).resolve().parent / "nl_interpreter.py"
    _NLI_SPEC = importlib.util.spec_from_file_location("eonix_nl_interpreter", str(_NLI_PATH))
    if _NLI_SPEC is not None and _NLI_SPEC.loader is not None:
        _NLI_MOD = importlib.util.module_from_spec(_NLI_SPEC)
        _NLI_SPEC.loader.exec_module(_NLI_MOD)
        NLInterpreter = _NLI_MOD.NLInterpreter
        NLResult = _NLI_MOD.NLResult
        INTENT_QUERY = _NLI_MOD.INTENT_QUERY
    else:
        NLInterpreter = None
        NLResult = None
        INTENT_QUERY = "INTENT_QUERY"

try:
    from branding import format_banner as branding_format_banner, print_boot_art as branding_print_boot_art
except Exception:
    branding_format_banner = None
    branding_print_boot_art = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(url: str, timeout: float = 3.0) -> Optional[Dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _http_post_json(url: str, payload: Dict, timeout: float = 5.0) -> Optional[Dict]:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


@dataclass
class PromptState:
    goal_name: str = "No active goal"
    progress_pct: int = 0
    ram_gb: float = 0.0
    ram_percent: float = 0.0
    model_version: str = "v?"
    nl_enabled: bool = True
    nl_flash: bool = False
    voice_state: str = ""


class EonixCompleter(Completer):
    def __init__(self, shell: "EonixShell"):
        self.shell = shell
        self.path_completer = PathCompleter(expanduser=True)
        self.word_completer = WordCompleter(
            [
                "eon status",
                "eon goal",
                "eon goal set",
                "eon goal done",
                "eon remember",
                "eon recall",
                "eon sync",
                "eon hub",
                "eon history",
                "eon nl",
                "eon nl on",
                "eon nl off",
                "eon listen",
                "eon listen --continuous",
                "eon help",
            ],
            ignore_case=True,
            sentence=True,
        )

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor
        stripped = text.lstrip()

        if stripped.startswith("eon"):
            for c in self.word_completer.get_completions(document, complete_event):
                yield c

            try:
                parts = shlex.split(stripped) if stripped.strip() else []
            except ValueError:
                parts = stripped.split()
            if len(parts) >= 2 and parts[0] == "eon" and parts[1] == "goal":
                if len(parts) == 2 or (len(parts) >= 3 and parts[2].startswith("s")):
                    for name in self.shell.goal_name_candidates(prefix=document.get_word_before_cursor()):
                        yield Completion(name, start_position=-len(document.get_word_before_cursor()))
            return

        for c in self.path_completer.get_completions(document, complete_event):
            yield c


class EonixShell:
    REFRESH_SECONDS = 5

    def __init__(self):
        EONIX_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
        self.state = PromptState(nl_enabled=bool(self.config.get("nl_enabled", True)))
        self._lock = threading.Lock()
        self._running = True
        self._cmd_count = 0
        self._nl_flash_until = 0.0
        self._voice_state = ""

        self.history_lines: List[str] = self._load_history_lines(limit=1000)
        self.history = InMemoryHistory()
        for line in self.history_lines:
            cmd = self._extract_command(line)
            if cmd:
                self.history.append_string(cmd)

        self.memory = EonixMemory() if EonixMemory is not None else None
        self.nl_interpreter = NLInterpreter(memory=self.memory) if NLInterpreter is not None else None

        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        self.session: Optional[PromptSession] = None

    @staticmethod
    def _load_config() -> Dict:
        if not SHELL_CONFIG_PATH.exists():
            return {"nl_enabled": True}
        try:
            data = json.loads(SHELL_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {"nl_enabled": bool(data.get("nl_enabled", True))}
        except Exception:
            pass
        return {"nl_enabled": True}

    def _save_config(self) -> None:
        payload = {"nl_enabled": bool(self.state.nl_enabled)}
        SHELL_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_history_lines(self, limit: int = 1000) -> List[str]:
        if not HISTORY_PATH.exists():
            return []
        lines = HISTORY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-limit:]

    @staticmethod
    def _extract_command(history_line: str) -> str:
        if "] " in history_line:
            return history_line.split("] ", 1)[1]
        return history_line

    def _save_history_line(self, command: str) -> None:
        line = f"[{_utc_now()}] [{os.getcwd()}] {command}"
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.history_lines.append(line)
        self.history.append_string(command)

    def _read_model_meta(self) -> Dict:
        if MODEL_METADATA_PATH.exists():
            try:
                return json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}

        fallback = Path(__file__).resolve().parents[1] / "models" / "onnx" / "model_metadata.json"
        if fallback.exists():
            try:
                return json.loads(fallback.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _refresh_prompt_data(self) -> None:
        active = _http_json(f"{GOAL_BASE}/goal/active") or {}
        model_meta = self._read_model_meta()
        vm = psutil.virtual_memory()

        goal_name = str(active.get("name") or "No active goal")
        progress = float(active.get("progress") or 0.0)
        progress_pct = int(round(progress * 100))

        model_version = str(model_meta.get("version") or model_meta.get("model_version") or "v?")
        if not model_version.startswith("v"):
            model_version = f"v{model_version}"

        with self._lock:
            self.state = PromptState(
                goal_name=goal_name,
                progress_pct=progress_pct,
                ram_gb=float(vm.used / 1e9),
                ram_percent=float(vm.percent),
                model_version=model_version,
                nl_enabled=bool(self.state.nl_enabled),
                nl_flash=time.time() < float(self._nl_flash_until),
                voice_state=str(self._voice_state),
            )

    def _refresh_loop(self) -> None:
        while self._running:
            try:
                self._refresh_prompt_data()
            except Exception:
                pass
            time.sleep(self.REFRESH_SECONDS)

    def _state_snapshot(self) -> PromptState:
        with self._lock:
            return PromptState(**self.state.__dict__)

    def _goal_short(self, name: str, max_len: int = 18) -> str:
        if len(name) <= max_len:
            return name
        return name[: max_len - 1].rstrip() + "..."

    def _cwd_short(self) -> str:
        cwd = Path.cwd()
        home = HOME
        txt = str(cwd)
        try:
            txt = str(cwd).replace(str(home), "~")
        except Exception:
            pass
        if len(txt) <= 28:
            return txt
        return "..." + txt[-25:]

    def build_prompt(self) -> ANSI:
        st = self._state_snapshot()

        if st.voice_state == "listening":
            return ANSI("<style fg='#00FF88'>🎤 EONIX [listening...]</style> <style fg='ansigreen'>❯</style> ")
        if st.voice_state == "thinking":
            return ANSI("<style fg='#00FF88'>⚙ EONIX [thinking...]</style> <style fg='ansigreen'>❯</style> ")

        goal = self._goal_short(st.goal_name)

        progress_color = "ansiyellow" if st.progress_pct < 50 else "ansigreen"
        ram_color = "ansired" if st.ram_percent > 80 else "ansiwhite"

        line1 = (
            f"<b><style fg='#00FF88'>⚡ EONIX</style></b>  "
            f"<style fg='ansicyan'>{goal}</style> "
            f"(<style fg='{progress_color}'>{st.progress_pct}%</style>)  "
            f"<style fg='{ram_color}'>{st.ram_gb:.1f}GB</style>  "
            f"<style fg='ansiwhite'>{st.model_version}</style>"
        )
        line2 = (
            f"<style fg='ansiblue'>eonix {self._cwd_short()}</style> "
            f"<style fg='ansimagenta'>{'[NL] ' if st.nl_flash else ''}</style>"
            f"<style fg='ansigreen'>❯</style> "
        )
        return ANSI(line1 + "\n" + line2)

    def goal_name_candidates(self, prefix: str = "") -> List[str]:
        data = _http_json(f"{GOAL_BASE}/goal/list")
        if not isinstance(data, list):
            return []
        names = [str(x.get("name") or "") for x in data if isinstance(x, dict)]
        p = (prefix or "").lower()
        return [n for n in names if n and (not p or n.lower().startswith(p))][:25]

    def _progress_bar(self, pct: int, width: int = 16) -> str:
        pct = max(0, min(100, pct))
        filled = int(round((pct / 100.0) * width))
        return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"

    def _memory_count(self) -> int:
        if self.memory is not None:
            try:
                return int(self.memory.stats().get("total_memories", 0))
            except Exception:
                return 0
        if sqlite3 is not None and MIND_MEMORY_DB.exists():
            try:
                conn = sqlite3.connect(str(MIND_MEMORY_DB))
                n = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                conn.close()
                return int(n)
            except Exception:
                return 0
        return 0

    def startup_banner(self) -> str:
        st = self._state_snapshot()
        model_status = _http_json(f"{HUB_BASE}/hub/snapshot") or {}
        model_info = model_status.get("model_info", {}) if isinstance(model_status, dict) else {}
        top3 = float(model_info.get("top3", 0.0) or 0.0) * 100.0
        vm = psutil.virtual_memory()
        free_gb = vm.available / 1e9

        if branding_format_banner is not None:
            return branding_format_banner(
                goal=self._goal_short(st.goal_name, 40),
                progress=max(0.0, min(1.0, st.progress_pct / 100.0)),
                ram=f"{free_gb:.1f}GB free",
                model=f"{st.model_version} | {top3:.2f}% Top-3",
                memories=self._memory_count(),
                peers=len((model_status.get("peers", []) if isinstance(model_status, dict) else []) or []),
            )

        lines = [
            "╔══════════════════════════════════════╗",
            "║  ⚡ EONIX SHELL v0.6.0              ║",
            f"║  Goal: {self._goal_short(st.goal_name, 20):<20} ({st.progress_pct:>3}%) ║",
            f"║  Model: {st.model_version:<5} | {top3:>6.2f}% Top-3      ║",
            f"║  NL Mode: {'ON (LLaMA 3B)' if st.nl_enabled else 'OFF':<24}║",
            f"║  RAM: {free_gb:>4.1f}GB free | {self._memory_count():>4} memories  ║",
            "║  Type 'eon help' for Eonix commands ║",
            "╚══════════════════════════════════════╝",
        ]
        return "\n".join(lines)

    def _log_context_event(self, command: str) -> None:
        payload = {
            "type": "shell",
            "command": command,
            "cwd": os.getcwd(),
            "timestamp": _utc_now(),
        }
        _http_post_json(f"{CONTEXT_BASE}/context/event", payload, timeout=2.0)

    def _print_status(self) -> None:
        snapshot = _http_json(f"{HUB_BASE}/hub/snapshot") or {}
        status = _http_json(f"{HUB_BASE}/hub/status") or {}

        print("=== EONIX SYSTEM SNAPSHOT ===")
        print(f"all_agents_healthy: {bool(status.get('all_agents_healthy', False))}")
        print(f"goal: {json.dumps(snapshot.get('goal', {}), ensure_ascii=False)}")
        print(f"context_summary: {json.dumps(snapshot.get('context_summary', {}), ensure_ascii=False)}")
        print(f"resource_status: {json.dumps(snapshot.get('resource_status', {}), ensure_ascii=False)}")
        print(f"sync_status: {json.dumps(snapshot.get('sync_status', {}), ensure_ascii=False)}")
        print(f"peers: {len(snapshot.get('peers', []) if isinstance(snapshot.get('peers'), list) else [])}")
        print(f"model_info: {json.dumps(snapshot.get('model_info', {}), ensure_ascii=False)}")

    def _print_goal(self) -> None:
        active = _http_json(f"{GOAL_BASE}/goal/active") or {}
        name = str(active.get("name") or "No active goal")
        pct = int(round(float(active.get("progress") or 0.0) * 100))
        print(name)
        print(f"{self._progress_bar(pct)} {pct}%")

    def _goal_set(self, name: str) -> None:
        out = _http_post_json(f"{GOAL_BASE}/goal/create", {"name": name, "description": ""})
        if isinstance(out, dict) and out.get("id"):
            print(f"Goal set: {name}")
            return
        print("Failed to set goal")

    def _goal_done(self) -> None:
        active = _http_json(f"{GOAL_BASE}/goal/active") or {}
        gid = str(active.get("id") or "")
        if not gid:
            print("No active goal")
            return
        out = _http_post_json(f"{GOAL_BASE}/goal/complete", {"goal_id": gid})
        if isinstance(out, dict) and out.get("ok"):
            print("Goal completed ✅")
        else:
            print("Failed to complete goal")

    def _remember(self, text: str) -> None:
        if self.memory is None:
            print("Memory backend unavailable")
            return
        self.memory.remember(text, category="command")
        print("Remembered ✅")

    def _recall(self, query: str) -> None:
        if self.memory is None:
            print("Memory backend unavailable")
            return
        rows = self.memory.recall(query, n=3)
        if not rows:
            print("No memories found")
            return
        for i, row in enumerate(rows, start=1):
            print(f"{i}. {row.get('text', '')}")

    def _sync(self) -> None:
        out = _http_post_json(f"{SYNC_BASE}/sync/push", {})
        n = int(out.get("pushed", 0)) if isinstance(out, dict) else 0
        print(f"Synced to {n} devices")

    def _hub(self) -> None:
        print("Opening Eonix Hub...")
        url = HUB_BASE
        try:
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception:
            pass

    def _history_cmd(self) -> None:
        rows = self.history_lines[-20:]
        if not rows:
            print("No history yet")
            return
        for row in rows:
            print(row)

    def _flash_nl(self, seconds: float = 4.0) -> None:
        self._nl_flash_until = time.time() + float(seconds)

    def _set_voice_state(self, state: str) -> None:
        self._voice_state = state
        self._refresh_prompt_data()

    @staticmethod
    def _speak(text: str) -> None:
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception:
            return

    def _capture_audio_to_wav(self, seconds: float = 7.0) -> Optional[Path]:
        try:
            import pyaudio  # type: ignore
            import wave
        except Exception:
            return None

        rate = 16000
        chunk = 1024
        channels = 1
        max_frames = int(rate / chunk * max(2.0, seconds))
        silence_limit = int(rate / chunk * 2.0)
        silence_count = 0

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=chunk,
        )

        frames = []
        try:
            for _ in range(max_frames):
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
                # Basic silence check from max amplitude.
                mx = max(data[i + 1] << 8 | data[i] for i in range(0, len(data) - 1, 2)) if data else 0
                if mx < 1200:
                    silence_count += 1
                else:
                    silence_count = 0
                if silence_count >= silence_limit:
                    break
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

        if not frames:
            return None

        path = Path(tempfile.gettempdir()) / f"eonix_voice_{int(time.time() * 1000)}.wav"
        wf = wave.open(str(path), "wb")
        try:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"".join(frames))
        finally:
            wf.close()
        return path

    def _transcribe_once(self) -> str:
        wav_path = self._capture_audio_to_wav(seconds=8.0)
        if wav_path is None:
            return ""
        try:
            from faster_whisper import WhisperModel  # type: ignore

            model = WhisperModel("base.en", device="cpu", compute_type="int8")
            segments, _info = model.transcribe(str(wav_path), vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
            return text.strip()
        except Exception:
            return ""
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _process_nl_text(self, text: str, from_voice: bool = False) -> str:
        if self.nl_interpreter is None:
            return "NL interpreter unavailable"

        result = self.nl_interpreter.handle(text)
        output = result.output or ""
        self._flash_nl()
        if from_voice and bool(getattr(result, "should_speak", False)):
            self._speak(output)
        return output

    def _listen_once(self) -> str:
        self._set_voice_state("listening")
        text = self._transcribe_once()
        if not text:
            self._set_voice_state("")
            return "No speech detected"

        print(f"[voice] {text}")
        self._set_voice_state("thinking")
        out = self._process_nl_text(text, from_voice=True)
        self._set_voice_state("")
        return out

    def _listen_continuous(self) -> str:
        print("Voice mode active. Say 'exit voice' to stop.")
        while True:
            self._set_voice_state("listening")
            text = self._transcribe_once()
            if not text:
                print("No speech detected")
                continue
            print(f"[voice] {text}")
            if text.strip().lower() == "exit voice":
                self._set_voice_state("")
                return "Voice mode stopped"
            self._set_voice_state("thinking")
            out = self._process_nl_text(text, from_voice=True)
            if out:
                print(out)

    @staticmethod
    def _help_cmd() -> None:
        print("Available eon commands:")
        print("  eon status           Full system snapshot")
        print("  eon goal             Active goal and progress bar")
        print("  eon goal set [name]  Create and activate a goal")
        print("  eon goal done        Complete active goal")
        print("  eon remember [text]  Store memory in command category")
        print("  eon recall [query]   Recall top 3 memories")
        print("  eon sync             Push sync state to peers")
        print("  eon hub              Open Eonix Hub in browser")
        print("  eon history          Show last 20 commands")
        print("  eon nl [on/off]      Toggle natural-language mode")
        print("  eon listen           Voice command (single utterance)")
        print("  eon listen --continuous  Continuous voice mode")
        print("  eon help             Show this help")

    def handle_eon_command(self, command: str) -> bool:
        parts = shlex.split(command)
        if len(parts) == 0 or parts[0] != "eon":
            return False

        if len(parts) == 1 or (len(parts) == 2 and parts[1] == "help"):
            self._help_cmd()
            return True

        if parts[1] == "status":
            self._print_status()
            return True

        if parts[1] == "goal":
            if len(parts) == 2:
                self._print_goal()
                return True
            if len(parts) >= 4 and parts[2] == "set":
                self._goal_set(" ".join(parts[3:]))
                return True
            if len(parts) >= 3 and parts[2] == "done":
                self._goal_done()
                return True
            print("Usage: eon goal | eon goal set [name] | eon goal done")
            return True

        if parts[1] == "remember":
            text = command.split("remember", 1)[1].strip()
            if text:
                self._remember(text)
            else:
                print("Usage: eon remember [text]")
            return True

        if parts[1] == "recall":
            text = command.split("recall", 1)[1].strip()
            if text:
                self._recall(text)
            else:
                print("Usage: eon recall [query]")
            return True

        if parts[1] == "sync":
            self._sync()
            return True

        if parts[1] == "hub":
            self._hub()
            return True

        if parts[1] == "history":
            self._history_cmd()
            return True

        if parts[1] == "nl":
            if len(parts) == 2:
                print(f"NL mode is {'ON' if self.state.nl_enabled else 'OFF'}")
                return True
            if len(parts) >= 3 and parts[2].lower() in {"on", "off"}:
                enabled = parts[2].lower() == "on"
                with self._lock:
                    self.state.nl_enabled = enabled
                self._save_config()
                print(f"NL mode {'ON' if enabled else 'OFF'}")
                return True
            print("Usage: eon nl [on/off]")
            return True

        if parts[1] == "listen":
            if len(parts) >= 3 and parts[2] == "--continuous":
                print(self._listen_continuous())
                return True
            print(self._listen_once())
            return True

        if parts[1] == "help":
            self._help_cmd()
            return True

        print("Unknown eon command. Try: eon help")
        return True

    def run_os_command(self, command: str) -> int:
        proc = subprocess.run(command, shell=True, text=True, capture_output=True)
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="")
        return int(proc.returncode)

    def run(self) -> int:
        if self.session is None:
            self.session = PromptSession(history=self.history, completer=EonixCompleter(self))

        if branding_print_boot_art is not None:
            sync_state = _http_json(f"{SYNC_BASE}/sync/status") or {}
            device_id = str(sync_state.get("device_id") or "local") if isinstance(sync_state, dict) else "local"
            branding_print_boot_art(self._state_snapshot().model_version, device_id)
        print(self.startup_banner())
        while True:
            try:
                assert self.session is not None
                command = self.session.prompt(self.build_prompt())
            except EOFError:
                break
            except KeyboardInterrupt:
                print("")
                continue

            cmd = command.strip()
            if not cmd:
                continue

            if cmd in {"exit", "quit"}:
                break

            self._cmd_count += 1
            self._save_history_line(cmd)
            self._log_context_event(cmd)

            if self.handle_eon_command(cmd):
                continue

            if self.state.nl_enabled and self.nl_interpreter is not None:
                if not self.nl_interpreter.is_shell_command(cmd):
                    out = self._process_nl_text(cmd)
                    if out:
                        print(out)
                    continue

            self.run_os_command(cmd)

        self.shutdown()
        return 0

    def run_single_command(self, command: str) -> int:
        if branding_print_boot_art is not None:
            sync_state = _http_json(f"{SYNC_BASE}/sync/status") or {}
            device_id = str(sync_state.get("device_id") or "local") if isinstance(sync_state, dict) else "local"
            branding_print_boot_art(self._state_snapshot().model_version, device_id)
        print(self.startup_banner())
        cmd = (command or "").strip()
        if not cmd:
            self.shutdown()
            return 0

        self._cmd_count += 1
        self._save_history_line(cmd)
        self._log_context_event(cmd)
        if self.handle_eon_command(cmd):
            self.shutdown()
            return 0

        if self.state.nl_enabled and self.nl_interpreter is not None and not self.nl_interpreter.is_shell_command(cmd):
            out = self._process_nl_text(cmd)
            if out:
                print(out)
            self.shutdown()
            return 0

        rc = self.run_os_command(cmd)
        self.shutdown()
        return rc

    def shutdown(self) -> None:
        self._running = False
        try:
            self._refresh_thread.join(timeout=1.0)
        except Exception:
            pass
        print(f"EONIX Shell session ended. {self._cmd_count} commands run.")


def main() -> int:
    parser = argparse.ArgumentParser(description="EonixShell")
    parser.add_argument("--banner-only", action="store_true", help="Print startup banner and exit")
    parser.add_argument("--run-command", default="", help="Run one command then exit")
    args = parser.parse_args()

    shell = EonixShell()
    if args.banner_only:
        if branding_print_boot_art is not None:
            sync_state = _http_json(f"{SYNC_BASE}/sync/status") or {}
            device_id = str(sync_state.get("device_id") or "local") if isinstance(sync_state, dict) else "local"
            branding_print_boot_art(shell._state_snapshot().model_version, device_id)
        print(shell.startup_banner())
        shell.shutdown()
        return 0

    if args.run_command:
        return shell.run_single_command(args.run_command)

    return shell.run()


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------- tests ---------------------------


def test_prompt_contains_goal_and_progress(monkeypatch):
    shell = EonixShell()
    monkeypatch.setattr(shell, "_state_snapshot", lambda: PromptState("Build MIND", 47, 6.2, 72.0, "v1.2"))
    prompt = str(shell.build_prompt())
    shell.shutdown()
    assert "Build MIND" in prompt
    assert "47%" in prompt


def test_eon_status_returns_all_agent_fields(monkeypatch, capsys):
    shell = EonixShell()

    def fake_get(url, timeout=3.0):
        if url.endswith("/hub/snapshot"):
            return {
                "goal": {},
                "context_summary": {},
                "resource_status": {},
                "sync_status": {},
                "peers": [],
                "model_info": {},
            }
        return {"all_agents_healthy": True}

    monkeypatch.setattr(f"{__name__}._http_json", fake_get)
    shell.handle_eon_command("eon status")
    out = capsys.readouterr().out
    shell.shutdown()
    assert "all_agents_healthy" in out
    assert "model_info" in out


def test_eon_goal_set_creates_via_api(monkeypatch, capsys):
    shell = EonixShell()
    monkeypatch.setattr(f"{__name__}._http_post_json", lambda *_a, **_k: {"id": "g1"})
    shell.handle_eon_command("eon goal set Complete Eonix Shell")
    out = capsys.readouterr().out
    shell.shutdown()
    assert "Goal set" in out


def test_eon_remember_stores_in_memory(monkeypatch, capsys):
    class _M:
        def remember(self, text, category="general"):
            assert text == "Shell is working great"
            assert category == "command"

    shell = EonixShell()
    shell.memory = _M()
    shell.handle_eon_command("eon remember Shell is working great")
    out = capsys.readouterr().out
    shell.shutdown()
    assert "Remembered" in out


def test_shell_history_persisted_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(f"{__name__}.HISTORY_PATH", tmp_path / "shell_history.txt")
    shell = EonixShell()
    shell._save_history_line("echo hi")
    text = (tmp_path / "shell_history.txt").read_text(encoding="utf-8")
    shell.shutdown()
    assert "echo hi" in text


def test_non_eon_command_passed_to_bash(monkeypatch):
    shell = EonixShell()

    called = {"v": False}

    class _P:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, shell=True, text=True, capture_output=True):
        called["v"] = True
        assert cmd == "python3 --version"
        assert shell is True
        return _P()

    monkeypatch.setattr("subprocess.run", fake_run)
    rc = shell.run_os_command("python3 --version")
    shell.shutdown()
    assert called["v"] is True
    assert rc == 0


def test_voice_mode_toggles_prompt_indicator(monkeypatch):
    shell = EonixShell()
    monkeypatch.setattr(shell, "_transcribe_once", lambda: "show me all python files")
    monkeypatch.setattr(shell, "_process_nl_text", lambda _txt, from_voice=False: "Running: find . -name '*.py'")
    out = shell._listen_once()
    prompt = str(shell.build_prompt())
    shell.shutdown()
    assert "Running:" in out
    assert "listening" not in prompt
    assert "thinking" not in prompt


def test_listen_command_registered_in_eon_commands(monkeypatch, capsys):
    shell = EonixShell()
    monkeypatch.setattr(shell, "_listen_once", lambda: "heard")
    handled = shell.handle_eon_command("eon listen")
    out = capsys.readouterr().out
    shell.shutdown()
    assert handled is True
    assert "heard" in out
