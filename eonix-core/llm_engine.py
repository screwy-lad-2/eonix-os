# -*- coding: utf-8 -*-
"""Eonix LLM Engine — multi-backend AI with zero ISO size increase.

Priority: Groq → OpenAI → Ollama → llama.cpp → offline rules.
No Ollama in ISO. User installs on demand.
"""
import os
import json
import threading

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_PATH = os.path.expanduser(
    "~/.config/eonix/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
SYSTEM_PROMPT = (
    "You are Eonix AI, the built-in assistant of Eonix OS — a custom Linux desktop. "
    "You are helpful, concise, and aware of the user's goals and notes from the context provided. "
    "Keep answers under 4 sentences unless detail is requested. "
    "For OS actions say: EONIX_CMD: [action]")


class EonixLLM:

    def __init__(self):
        self._llama = None
        self._llama_loading = False
        self._cfg = self._load_cfg()

    def _load_cfg(self):
        p = os.path.expanduser("~/.config/eonix/settings.json")
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _rag_context(self):
        parts = []
        for fname, label in [("goals.json", "Goals"), ("notes.json", "Notes")]:
            p = os.path.expanduser(f"~/.config/eonix/{fname}")
            if not os.path.exists(p):
                continue
            try:
                with open(p) as f:
                    data = json.load(f)
                items = [x.get("title", x.get("content", "")) for x in data[:4]]
                if items:
                    parts.append(f"{label}: " + "; ".join(items))
            except Exception:
                pass
        return " | ".join(parts)

    def _messages(self, prompt):
        ctx = self._rag_context()
        sys_msg = SYSTEM_PROMPT
        if ctx:
            sys_msg += f"\nContext: {ctx}"
        return [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}]

    def _try_groq(self, prompt):
        key = self._cfg.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not key:
            return None
        import urllib.request
        try:
            data = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": self._messages(prompt),
                "max_tokens": 350,
                "temperature": 0.7
            }).encode()
            req = urllib.request.Request(
                GROQ_URL, data=data,
                headers={"Authorization": f"Bearer {key}",
                          "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read())
            return res["choices"][0]["message"]["content"].strip() or None
        except Exception as e:
            print(f"[LLM] Groq: {e}")
            return None

    def _try_openai(self, prompt):
        key = self._cfg.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return None
        import urllib.request
        try:
            data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": self._messages(prompt),
                "max_tokens": 350
            }).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={"Authorization": f"Bearer {key}",
                          "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                res = json.loads(r.read())
            return res["choices"][0]["message"]["content"].strip() or None
        except Exception as e:
            print(f"[LLM] OpenAI: {e}")
            return None

    def _try_ollama(self, prompt):
        """User-installed Ollama (not bundled in ISO)."""
        import urllib.request
        try:
            ctx = self._rag_context()
            data = json.dumps({
                "model": "tinyllama",
                "prompt": f"System: {SYSTEM_PROMPT}\nContext: {ctx}\nUser: {prompt}\nAssistant:",
                "stream": False,
                "options": {"num_predict": 300, "temperature": 0.7}
            }).encode()
            req = urllib.request.Request(
                OLLAMA_URL, data=data,
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                res = json.loads(r.read())
            return res.get("response", "").strip() or None
        except Exception:
            return None

    def _load_llama_bg(self):
        if self._llama_loading or not os.path.exists(MODEL_PATH):
            return
        self._llama_loading = True
        def _load():
            try:
                from llama_cpp import Llama
                self._llama = Llama(model_path=MODEL_PATH, n_ctx=1024, n_threads=2, verbose=False)
            except Exception as e:
                print(f"[LLM] llama load: {e}")
            self._llama_loading = False
        threading.Thread(target=_load, daemon=True).start()

    def _try_llama(self, prompt):
        if self._llama is None:
            self._load_llama_bg()
            return None
        try:
            ctx = self._rag_context()
            out = self._llama(
                f"<|system|>\n{SYSTEM_PROMPT}\nContext:{ctx}\n<|user|>\n{prompt}\n<|assistant|>",
                max_tokens=256, temperature=0.7, stop=["<|user|>"])
            return out["choices"][0]["text"].strip() or None
        except Exception as e:
            print(f"[LLM] llama: {e}")
            return None

    def _fallback(self, text):
        """Smart rule fallback — always works, no internet, no model."""
        t = text.lower().strip()
        import datetime
        now = datetime.datetime.now()

        if any(w in t for w in ["hi", "hello", "hey", "good morning", "good evening"]):
            return ("Hello! I'm Eonix AI.\nI can open apps, manage goals, save notes, and answer questions.\n"
                    "Add a free Groq key in Settings > AI for full LLM answers.")

        if any(w in t for w in ["cpu", "ram", "memory", "disk", "system"]):
            try:
                import psutil
                c = psutil.cpu_percent(interval=0.3)
                m = psutil.virtual_memory()
                return f"CPU: {c:.0f}%  |  RAM: {m.used // 1048576}MB / {m.total // 1048576}MB ({m.percent:.0f}%)"
            except Exception:
                return "EONIX_CMD: cpu"

        if any(w in t for w in ["time", "date", "day", "today", "what day"]):
            return now.strftime("%A, %d %B %Y \u2014 %I:%M %p")

        if any(w in t for w in ["help", "what can", "commands", "how"]):
            return ("Commands I understand:\nopen terminal / files / notes / goals\n"
                    "cpu, ram, screenshot\nvolume up/down, mute\nlock screen\n"
                    "note: [your text]\n\nFor full LLM answers:\nSettings > AI > Groq API Key (free)")

        return ("I'm not sure about that.\nFor full AI answers, add a Groq API key in Settings > AI. "
                "It's free at groq.com.\nOr type 'help' for available commands.")

    def ask(self, prompt, on_response, on_source=None):
        """Non-blocking LLM query with priority cascade."""
        self._cfg = self._load_cfg()

        def _worker():
            from gi.repository import GLib
            backends = [
                ("groq", self._try_groq),
                ("openai", self._try_openai),
                ("ollama", self._try_ollama),
                ("local", self._try_llama),
            ]
            for name, fn in backends:
                try:
                    r = fn(prompt)
                except Exception:
                    r = None
                if r:
                    GLib.idle_add(on_response, r)
                    if on_source:
                        GLib.idle_add(on_source, name)
                    return
            fb = self._fallback(prompt)
            GLib.idle_add(on_response, fb)
            if on_source:
                GLib.idle_add(on_source, "offline")

        threading.Thread(target=_worker, daemon=True).start()
