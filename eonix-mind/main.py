"""
Eonix OS — EONIX MIND Main Pipeline
=====================================
Voice assistant pipeline: wake word → STT → context assembly →
LLaMA inference → action routing → TTS response.

Usage: python3 main.py
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime, timezone

# ---- System Prompt ----

EONIX_MIND_SYSTEM_PROMPT = """
You are Eon, the intelligent core of Eonix OS — an AI-native operating system.
You have read access to:
- The user's active processes and resource usage
- The user's current Goal (what they're working on)
- The last 50 context events (files opened, commands run, etc.)
- Security alerts from the eBPF fabric
- Deadlock recovery events

Your personality: Calm, efficient, proactive, like JARVIS from Iron Man.
You speak in short, direct sentences. You never ask unnecessary questions.
You always tell the user what you're doing when you take an action.

Current system state: {system_state}
Active goal: {active_goal}
Recent context: {recent_context}
"""

# ---- Action Tags ----
# The LLM can include these in its response to trigger system actions:
# [OPEN_FILE path]     — Open a file in the default editor
# [KILL_PROCESS pid]   — Kill a process by PID
# [RUN_COMMAND cmd]    — Run a shell command
# [ALERT message]      — Show a desktop notification
# [SPEAK_ONLY]         — Just speak the response, no action


def get_system_state() -> dict:
    """Gather current system metrics."""
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "process_count": len(psutil.pids()),
            "uptime_hours": round(
                (time.time() - psutil.boot_time()) / 3600, 1
            ),
        }
    except ImportError:
        return {"error": "psutil not installed"}


def get_active_goal() -> dict:
    """Read the current active goal from GoalEngine."""
    goal_file = os.path.expanduser("~/.eonix/active_goal.json")
    if os.path.exists(goal_file):
        with open(goal_file) as f:
            return json.load(f)
    return {"title": "No active goal", "progress_score": 0.0}


def get_recent_context(limit: int = 10) -> list:
    """Get recent context events from ContextAgent."""
    # In production, this queries ChromaDB via the ContextAgent API
    context_file = os.path.expanduser("~/.eonix/recent_context.json")
    if os.path.exists(context_file):
        with open(context_file) as f:
            events = json.load(f)
            return events[-limit:]
    return []


def assemble_prompt(user_input: str) -> str:
    """Build the full prompt with system context."""
    system_state = json.dumps(get_system_state(), indent=2)
    active_goal = json.dumps(get_active_goal(), indent=2)
    recent_context = json.dumps(get_recent_context(), indent=2)

    system_prompt = EONIX_MIND_SYSTEM_PROMPT.format(
        system_state=system_state,
        active_goal=active_goal,
        recent_context=recent_context,
    )

    return f"{system_prompt}\n\nUser: {user_input}\nEon:"


def route_actions(response: str) -> str:
    """Parse and execute action tags from LLM response."""
    clean_response = response

    if "[OPEN_FILE" in response:
        start = response.index("[OPEN_FILE") + len("[OPEN_FILE ")
        end = response.index("]", start)
        filepath = response[start:end].strip()
        print(f"  [Action] Opening file: {filepath}")
        # In production: subprocess.Popen(["xdg-open", filepath])
        clean_response = response.replace(f"[OPEN_FILE {filepath}]", "")

    if "[KILL_PROCESS" in response:
        start = response.index("[KILL_PROCESS") + len("[KILL_PROCESS ")
        end = response.index("]", start)
        pid = response[start:end].strip()
        print(f"  [Action] Kill signal sent to PID {pid}")
        # In production: os.kill(int(pid), signal.SIGTERM)
        clean_response = response.replace(f"[KILL_PROCESS {pid}]", "")

    if "[RUN_COMMAND" in response:
        start = response.index("[RUN_COMMAND") + len("[RUN_COMMAND ")
        end = response.index("]", start)
        cmd = response[start:end].strip()
        print(f"  [Action] Running command: {cmd}")
        # In production: subprocess.run(cmd, shell=True) — with sandboxing
        clean_response = response.replace(f"[RUN_COMMAND {cmd}]", "")

    if "[ALERT" in response:
        start = response.index("[ALERT") + len("[ALERT ")
        end = response.index("]", start)
        message = response[start:end].strip()
        print(f"  [Action] Alert: {message}")
        # In production: notify-send via DBus
        clean_response = response.replace(f"[ALERT {message}]", "")

    return clean_response.replace("[SPEAK_ONLY]", "").strip()


def run_text_mode():
    """Run EONIX MIND in text mode (no voice, for development)."""
    print("=" * 50)
    print("  EONIX MIND — Text Mode (Development)")
    print("=" * 50)
    print("Type your questions. Type 'quit' to exit.\n")

    # Check for LLaMA model
    llm = None
    model_path = os.path.join(
        os.path.dirname(__file__), "..", "models", "gguf",
        "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    )

    try:
        from llama_cpp import Llama
        if os.path.exists(model_path):
            print(f"Loading LLaMA model from {model_path}...")
            llm = Llama(model_path=model_path, n_ctx=2048, n_threads=4)
            print("Model loaded.\n")
        else:
            print(f"Model not found at {model_path}")
            print("Running in echo mode (no LLM). Download the model first.\n")
    except ImportError:
        print("llama-cpp-python not installed. Running in echo mode.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        prompt = assemble_prompt(user_input)

        if llm:
            result = llm(prompt, max_tokens=256, stop=["User:", "\n\n"])
            response = result["choices"][0]["text"].strip()
        else:
            # Echo mode — demonstrate the pipeline without LLM
            response = (
                f"[Echo] I understood: '{user_input}'. "
                f"System CPU is at {get_system_state().get('cpu_percent', '?')}%. "
                f"Active goal: {get_active_goal().get('title', 'none')}."
            )

        clean = route_actions(response)
        print(f"Eon: {clean}\n")

    print("\n[EONIX MIND] Session ended.")


if __name__ == "__main__":
    run_text_mode()
