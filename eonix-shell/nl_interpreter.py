#!/usr/bin/env python3
"""Eonix natural-language command interpreter for EonixShell."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


GOAL_BASE = "http://127.0.0.1:7735"
SYNC_BASE = "http://127.0.0.1:7740"

INTENT_SHELL = "INTENT_SHELL"
INTENT_QUERY = "INTENT_QUERY"
INTENT_MEMORY = "INTENT_MEMORY"
INTENT_GOAL = "INTENT_GOAL"

SIMILARITY_THRESHOLD = 0.35
DANGEROUS_FRAGMENTS = ["rm", "sudo", "dd", "mkfs", "chmod 777"]
BLOCKED_FRAGMENTS = ["rm -rf /", "mkfs", ":(){:|:&};:"]


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 4.0) -> Optional[Dict[str, Any]]:
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


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(dot / (na * nb))


@dataclass
class NLResult:
    intent: str
    output: str
    ran_command: str = ""
    should_speak: bool = False


class NLInterpreter:
    def __init__(
        self,
        memory: Any = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        command_runner: Optional[Callable[[str], Tuple[int, str]]] = None,
    ):
        self.memory = memory
        self.confirm_callback = confirm_callback or (lambda _cmd: True)
        self.command_runner = command_runner or self._default_runner

        self._embedding_model = None
        self._llm = None

        self.intent_templates: Dict[str, List[str]] = {
            INTENT_SHELL: [
                "show me all python files",
                "delete the temp folder",
                "how much disk space do i have",
                "list running processes",
                "find files modified today",
            ],
            INTENT_QUERY: [
                "what is my goal progress",
                "how is my system doing",
                "what did i work on today",
                "tell me about my project",
            ],
            INTENT_MEMORY: [
                "remember this for later",
                "what do you know about x",
                "i want to note that",
            ],
            INTENT_GOAL: [
                "start working on x",
                "i finished my goal",
                "switch to a new goal",
            ],
        }

        self._template_embeds: Dict[str, List[List[float]]] = {}

    @staticmethod
    def _default_runner(cmd: str) -> Tuple[int, str]:
        proc = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        output = (proc.stdout or "") + (proc.stderr or "")
        return int(proc.returncode), output.strip()

    def _load_embed_model(self) -> None:
        if self._embedding_model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            self._embedding_model = None

    def _embed(self, text: str) -> List[float]:
        self._load_embed_model()
        if self._embedding_model is None:
            return []
        try:
            return list(self._embedding_model.encode([text])[0])
        except Exception:
            return []

    def _load_llm(self) -> None:
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama  # type: ignore

            model_path = Path(__file__).resolve().parents[1] / "models" / "llama" / "llama-3.2-3b-instruct.Q4_K_M.gguf"
            if model_path.exists():
                self._llm = Llama(model_path=str(model_path), n_ctx=2048, verbose=False)
            else:
                self._llm = None
        except Exception:
            self._llm = None

    @staticmethod
    def is_eon_command(text: str) -> bool:
        return _safe_text(text).startswith("eon")

    @staticmethod
    def is_shell_command(text: str) -> bool:
        t = _safe_text(text)
        if not t:
            return False

        if t.startswith(("./", "../", "/")):
            return True

        if any(x in t for x in ["|", ";", "&&", "||", ">", "<"]):
            return True

        try:
            parts = shlex.split(t)
        except ValueError:
            parts = t.split()

        if not parts:
            return False

        first = parts[0]
        known = {"ls", "cd", "pwd", "cat", "echo", "find", "git", "python", "python3", "pip", "curl", "grep", "awk", "sed", "mkdir", "rm", "mv", "cp", "touch", "df", "free", "ps"}
        if first in known:
            return True

        return shutil.which(first) is not None

    def classify_intent(self, text: str) -> str:
        text = _safe_text(text)
        if not text:
            return INTENT_QUERY

        low = text.lower()
        if any(k in low for k in ["remember", "note that", "what do you know", "recall"]):
            return INTENT_MEMORY
        if any(k in low for k in ["switch goal", "start working on", "finished my goal", "goal done"]):
            return INTENT_GOAL
        if any(k in low for k in ["show me", "list ", "find ", "disk space", "ram", "running processes"]):
            return INTENT_SHELL
        if any(k in low for k in ["what is my", "how is my", "what did i", "tell me about"]):
            return INTENT_QUERY

        query_vec = self._embed(text)
        if query_vec:
            best_intent = INTENT_QUERY
            best_score = -1.0
            for intent, templates in self.intent_templates.items():
                if intent not in self._template_embeds:
                    self._template_embeds[intent] = [self._embed(t) for t in templates]
                scores = [_cosine(query_vec, tv) for tv in self._template_embeds[intent] if tv]
                score = max(scores) if scores else 0.0
                if score > best_score:
                    best_intent = intent
                    best_score = score
            if best_score >= SIMILARITY_THRESHOLD:
                return best_intent
            return INTENT_QUERY

        # Fallback lexical scoring.
        q_tokens = set(_tokenize(text))
        best_intent = INTENT_QUERY
        best_score = -1.0
        for intent, templates in self.intent_templates.items():
            score = 0.0
            for t in templates:
                tpl = set(_tokenize(t))
                if not tpl:
                    continue
                overlap = len(q_tokens.intersection(tpl)) / max(1, len(tpl))
                score = max(score, overlap)
            if score > best_score:
                best_score = score
                best_intent = intent
        return best_intent if best_score >= SIMILARITY_THRESHOLD else INTENT_QUERY

    def _llm_command_translation(self, text: str) -> str:
        self._load_llm()
        if self._llm is None:
            return ""

        prompt = (
            "Convert this to a single bash command. "
            "Output ONLY the command, nothing else.\n"
            f"Input: {text}\n"
            "Command:"
        )
        try:
            out = self._llm(prompt, max_tokens=64, temperature=0.0)
            raw = _safe_text(out.get("choices", [{}])[0].get("text", ""))
            return raw.splitlines()[0].strip()
        except Exception:
            return ""

    @staticmethod
    def _heuristic_translation(text: str) -> str:
        t = text.lower().strip()
        mapping = [
            ("show me all python files", "find . -name '*.py'"),
            ("python files", "find . -name '*.py'"),
            ("disk space", "df -h"),
            ("ram", "free -h"),
            ("memory", "free -h"),
            ("running processes", "ps aux"),
            ("modified today", "find . -type f -daystart -mtime 0"),
        ]
        for phrase, cmd in mapping:
            if phrase in t:
                return cmd
        return "echo " + shlex.quote("No safe translation available")

    def translate_to_bash(self, text: str) -> str:
        cmd = self._llm_command_translation(text)
        if not cmd:
            cmd = self._heuristic_translation(text)

        if not cmd.strip():
            return "echo " + shlex.quote("Translation failed")

        low = cmd.lower().strip()
        for frag in BLOCKED_FRAGMENTS:
            if frag in low:
                return ""
        return cmd

    def safe_execute(self, bash_cmd: str) -> str:
        cmd = _safe_text(bash_cmd)
        if not cmd:
            return "Blocked: empty command"

        low = cmd.lower()
        if any(frag in low for frag in BLOCKED_FRAGMENTS):
            return "Blocked dangerous command"

        if any(re.search(rf"\b{re.escape(frag)}\b", low) for frag in DANGEROUS_FRAGMENTS):
            if not self.confirm_callback(cmd):
                return "Cancelled dangerous command"

        rc, out = self.command_runner(cmd)
        header = f"Running: {cmd}"
        if out:
            return header + "\n" + out
        return header + f"\n(exit={rc})"

    def ask_mind(self, text: str) -> str:
        payload = {"command": text, "source": "shell-nl"}
        out = _http_post_json(f"{SYNC_BASE}/sync/voice", payload)
        if isinstance(out, dict):
            reply = _safe_text(out.get("reply"))
            if reply:
                return reply
        local = self._llm_command_translation(text)
        if local:
            return local
        return "MIND is unreachable right now."

    def _handle_memory_intent(self, text: str) -> NLResult:
        if self.memory is None:
            return NLResult(intent=INTENT_MEMORY, output="Memory backend unavailable")

        lower = text.lower().strip()
        if lower.startswith("remember") or "note that" in lower:
            category = "deadline" if any(k in lower for k in ["exam", "deadline", "submit", "april", "may"]) else "command"
            self.memory.remember(text, category=category)
            return NLResult(intent=INTENT_MEMORY, output="Remembered ✅")

        rows = self.memory.recall(text, n=3)
        if not rows:
            return NLResult(intent=INTENT_MEMORY, output="No memories found")
        lines = [f"{i}. {r.get('text', '')}" for i, r in enumerate(rows, start=1)]
        return NLResult(intent=INTENT_MEMORY, output="\n".join(lines))

    def _extract_goal_name(self, text: str) -> str:
        t = text.strip()
        m = re.search(r"(?:switch(?: my)? goal to|start working on)\s+(.+)$", t, flags=re.I)
        if m:
            return m.group(1).strip().strip('"')
        return t

    def _handle_goal_intent(self, text: str) -> NLResult:
        lower = text.lower().strip()
        if "finished" in lower or "done" in lower:
            active = _http_post_json(f"{GOAL_BASE}/goal/active", {})
            # active endpoint is GET; fallback by using urllib directly.
            try:
                with urllib.request.urlopen(f"{GOAL_BASE}/goal/active", timeout=3.0) as r:
                    active_obj = json.loads(r.read().decode("utf-8"))
            except Exception:
                active_obj = {}
            gid = _safe_text(active_obj.get("id") if isinstance(active_obj, dict) else "")
            if not gid:
                return NLResult(intent=INTENT_GOAL, output="No active goal")
            done = _http_post_json(f"{GOAL_BASE}/goal/complete", {"goal_id": gid})
            if isinstance(done, dict) and done.get("ok"):
                return NLResult(intent=INTENT_GOAL, output="Goal completed ✅")
            return NLResult(intent=INTENT_GOAL, output="Failed to complete goal")

        name = self._extract_goal_name(text)
        out = _http_post_json(f"{GOAL_BASE}/goal/create", {"name": name, "description": ""})
        if isinstance(out, dict) and out.get("id"):
            return NLResult(intent=INTENT_GOAL, output=f"Goal set: {name} ✅")
        return NLResult(intent=INTENT_GOAL, output="Failed to set goal")

    def handle(self, text: str) -> NLResult:
        raw = _safe_text(text)
        if not raw:
            return NLResult(intent=INTENT_QUERY, output="")

        if self.is_shell_command(raw):
            return NLResult(intent=INTENT_SHELL, output=raw, ran_command=raw)

        if self.is_eon_command(raw):
            return NLResult(intent="EON", output=raw)

        intent = self.classify_intent(raw)

        if intent == INTENT_SHELL:
            bash_cmd = self.translate_to_bash(raw)
            if not bash_cmd:
                return NLResult(intent=INTENT_SHELL, output="Blocked dangerous command")
            out = self.safe_execute(bash_cmd)
            return NLResult(intent=INTENT_SHELL, output=out, ran_command=bash_cmd)

        if intent == INTENT_MEMORY:
            return self._handle_memory_intent(raw)

        if intent == INTENT_GOAL:
            return self._handle_goal_intent(raw)

        reply = self.ask_mind(raw)
        return NLResult(intent=INTENT_QUERY, output=reply, should_speak=True)


# --------------------------- tests ---------------------------


def test_classify_shell_intent_correctly():
    nli = NLInterpreter(memory=None)
    nli._embed = lambda _t: []
    out = nli.classify_intent("show me all python files")
    assert out == INTENT_SHELL


def test_classify_query_intent_correctly():
    nli = NLInterpreter(memory=None)
    nli._embed = lambda _t: []
    out = nli.classify_intent("what did i work on today")
    assert out == INTENT_QUERY


def test_translate_to_bash_returns_valid_command(monkeypatch):
    nli = NLInterpreter(memory=None)
    monkeypatch.setattr(nli, "_llm_command_translation", lambda _t: "find . -name '*.py'")
    cmd = nli.translate_to_bash("show me all python files")
    assert cmd == "find . -name '*.py'"


def test_safe_execute_blocks_dangerous_commands():
    nli = NLInterpreter(memory=None, confirm_callback=lambda _cmd: False)
    out = nli.safe_execute("sudo rm -rf /tmp/demo")
    assert "Cancelled" in out or "Blocked" in out


def test_ask_mind_returns_string(monkeypatch):
    nli = NLInterpreter(memory=None)
    monkeypatch.setattr(f"{__name__}._http_post_json", lambda *_a, **_k: {"ok": True, "reply": "All good"})
    out = nli.ask_mind("how is my system")
    assert isinstance(out, str)
    assert out == "All good"


def test_memory_intent_stores_correctly():
    class _Mem:
        def __init__(self):
            self.saved = []

        def remember(self, text, category="command"):
            self.saved.append((text, category))

        def recall(self, _query, n=3):
            return [{"text": "x"}][:n]

    mem = _Mem()
    nli = NLInterpreter(memory=mem)
    nli._embed = lambda _t: []
    res = nli.handle("remember that my exam is April 20")
    assert "Remembered" in res.output
    assert mem.saved
