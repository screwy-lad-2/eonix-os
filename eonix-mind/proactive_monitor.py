#!/usr/bin/env python3
"""Eonix MIND proactive monitor with rule-based spoken alerts."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import psutil

try:
    from memory import EonixMemory
except Exception:
    EonixMemory = None  # type: ignore


GOAL_BASE = "http://127.0.0.1:7735"
CONTEXT_BASE = "http://127.0.0.1:7736"
EONIX_DIR = Path.home() / ".eonix"
SECURITY_ALERTS = EONIX_DIR / "security_alerts.log"
RETRAIN_HISTORY = EONIX_DIR / "retrain_history.json"
DEADLOCK_LOG = Path("/proc/eonix/deadlock_log")


class ProactiveMonitor:
    CHECK_INTERVAL = 60

    def __init__(
        self,
        speak_fn: Optional[Callable[[str], None]] = None,
        memory: Optional[object] = None,
        goal_base: str = GOAL_BASE,
        context_base: str = CONTEXT_BASE,
        deadlock_log: Path = DEADLOCK_LOG,
        security_alerts: Path = SECURITY_ALERTS,
        retrain_history: Path = RETRAIN_HISTORY,
    ):
        self.speak_fn = speak_fn or (lambda msg: print(f"Eon: {msg}"))
        self.memory = memory
        self.goal_base = goal_base
        self.context_base = context_base
        self.deadlock_log = deadlock_log
        self.security_alerts = security_alerts
        self.retrain_history = retrain_history

        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.cooldowns = {
            "ram_critical": timedelta(minutes=10),
            "deadlock": timedelta(seconds=0),
            "security": timedelta(seconds=0),
            "long_session": timedelta(hours=2),
            "goal_progress": timedelta(hours=4),
            "retrain": timedelta(seconds=0),
            "deadline": timedelta(days=1),
        }
        self.last_triggered: Dict[str, datetime] = {}

        self.last_deadlock_line = ""
        self.last_security_line = ""
        self.last_retrain_signature = ""
        self.last_goal_progress: Dict[str, float] = {}

    def _http_json(self, url: str, timeout: int = 3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

    def _can_trigger(self, key: str, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        last = self.last_triggered.get(key)
        cool = self.cooldowns.get(key, timedelta(seconds=0))
        if last is None:
            return True
        return now - last >= cool

    def _trigger(self, key: str, message: str, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if not self._can_trigger(key, now=now):
            return False
        self.last_triggered[key] = now
        self.speak_fn(message)
        return True

    def _read_tail_line(self, path: Path) -> str:
        try:
            if not path.exists():
                return ""
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return lines[-1].strip() if lines else ""
        except Exception:
            return ""

    def _parse_percent(self, text: str) -> Optional[float]:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def rule_ram_critical(self) -> None:
        ram = float(psutil.virtual_memory().percent)
        if ram > 85.0:
            self._trigger(
                "ram_critical",
                f"RAM at {ram:.0f}%. Your kernel build may fail. Shall I suspend background processes?",
            )

    def rule_deadlock_recovered(self) -> None:
        line = self._read_tail_line(self.deadlock_log)
        if not line or line == self.last_deadlock_line:
            return
        self.last_deadlock_line = line

        ms = self._parse_percent(line) or 0.0
        victim = "unknown"
        m = re.search(r"victim\s*[:=]\s*([A-Za-z0-9_.-]+)", line, re.IGNORECASE)
        if m:
            victim = m.group(1)

        self._trigger(
            "deadlock",
            f"Deadlock detected and resolved in {int(ms)}ms. Victim was {victim}.",
        )

    def rule_security_threat(self) -> None:
        line = self._read_tail_line(self.security_alerts)
        if not line or line == self.last_security_line:
            return

        score = 0.0
        m_score = re.search(r"combined_score\s*[:=]\s*([0-9.]+)", line)
        if m_score:
            try:
                score = float(m_score.group(1))
            except Exception:
                score = 0.0

        if score <= 0.5:
            return

        self.last_security_line = line
        process = "unknown"
        m_proc = re.search(r"process\s*[:=]\s*([A-Za-z0-9_.-]+)", line)
        if m_proc:
            process = m_proc.group(1)
        self._trigger(
            "security",
            f"Security alert: {process} is behaving anomalously. Network access restricted.",
        )

    def _focus_minutes(self) -> float:
        q = urllib.parse.urlencode({"n": 900})
        events = self._http_json(f"{self.context_base}/context/recent?{q}")
        if not isinstance(events, list):
            return 0.0
        focus_events = [e for e in events if str(e.get("type", "")).lower() == "focus"]
        return float(len(focus_events) * 0.1)

    def rule_long_session(self) -> None:
        minutes = self._focus_minutes()
        if minutes > 90.0:
            hours = minutes / 60.0
            self._trigger(
                "long_session",
                f"You have been coding for {hours:.1f} hours. Consider a break.",
            )

    def _active_goal(self) -> Dict:
        payload = self._http_json(f"{self.goal_base}/goal/active")
        return payload if isinstance(payload, dict) else {}

    def _goal_progress(self, goal_id: str) -> float:
        payload = self._http_json(f"{self.goal_base}/goal/progress/{urllib.parse.quote(goal_id)}")
        if not isinstance(payload, dict):
            return 0.0
        try:
            return float(payload.get("progress", 0.0))
        except Exception:
            return 0.0

    def _commits_today(self) -> int:
        q = urllib.parse.urlencode({"hours": 24})
        payload = self._http_json(f"{self.context_base}/context/summary?{q}")
        if isinstance(payload, dict):
            m = re.search(r"(\d+)\s+commit", str(payload.get("summary", "")), re.IGNORECASE)
            if m:
                return int(m.group(1))
        return 0

    def rule_goal_progress_update(self) -> None:
        active = self._active_goal()
        gid = str(active.get("id") or "")
        if not gid:
            return

        current = self._goal_progress(gid)
        previous = float(self.last_goal_progress.get(gid, 0.0))
        self.last_goal_progress[gid] = current
        if current - previous <= 0.10:
            return

        commits = self._commits_today()
        name = str(active.get("name") or "your goal")
        self._trigger(
            "goal_progress",
            f"Goal update: {name} is now {int(current * 100)}% complete. {commits} commits today.",
        )

    def rule_auto_retrain_fired(self) -> None:
        try:
            if not self.retrain_history.exists():
                return
            data = json.loads(self.retrain_history.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else data.get("history", [])
            if not isinstance(entries, list) or not entries:
                return
            latest = entries[-1]
            signature = json.dumps(latest, sort_keys=True)
            if signature == self.last_retrain_signature:
                return
            self.last_retrain_signature = signature

            version = str(latest.get("version") or "unknown")
            old_acc = float(latest.get("old_top3", 0.0)) * 100.0
            new_acc = float(latest.get("new_top3", 0.0)) * 100.0
            self._trigger(
                "retrain",
                f"Scheduler model updated to {version}. Top-3 accuracy improved from {old_acc:.2f}% to {new_acc:.2f}%.",
            )
        except Exception:
            return

    def _parse_deadline_date(self, text: str) -> Optional[datetime]:
        patterns = [
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s*\d{4})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if not m:
                continue
            raw = m.group(1)
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"]:
                try:
                    dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue
        return None

    def _deadline_entries(self) -> List[str]:
        if self.memory is not None and hasattr(self.memory, "recall_by_category"):
            try:
                rows = self.memory.recall_by_category("deadline")
                return [str(r.get("text", "")) for r in rows if str(r.get("text", ""))]
            except Exception:
                pass
        return []

    def rule_deadline_approaching(self) -> None:
        now = datetime.now(timezone.utc)
        for text in self._deadline_entries():
            dt = self._parse_deadline_date(text)
            if not dt:
                continue
            days = (dt.date() - now.date()).days
            if 0 <= days <= 7:
                self._trigger(
                    "deadline",
                    f"Reminder: {text}. {days} days remaining.",
                )
                return

    def check_all_rules(self) -> None:
        # Every rule is wrapped individually to keep the monitor resilient.
        for fn in [
            self.rule_ram_critical,
            self.rule_deadlock_recovered,
            self.rule_security_threat,
            self.rule_long_session,
            self.rule_goal_progress_update,
            self.rule_auto_retrain_fired,
            self.rule_deadline_approaching,
        ]:
            try:
                fn()
            except Exception:
                continue

    def _loop(self) -> None:
        while self._running:
            self.check_all_rules()
            time.sleep(max(1, int(self.CHECK_INTERVAL)))

    def start(self) -> threading.Thread:
        if self._running and self._thread is not None:
            return self._thread
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="EonixProactiveMonitor", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._running = False


def _dummy_memory(deadline_text: str):
    class _M:
        def recall_by_category(self, category: str):
            if category == "deadline":
                return [{"text": deadline_text}]
            return []

    return _M()


def test_cooldown_prevents_duplicate_alerts(monkeypatch):
    spoken: List[str] = []
    m = ProactiveMonitor(speak_fn=lambda msg: spoken.append(msg))
    monkeypatch.setattr(psutil, "virtual_memory", lambda: type("VM", (), {"percent": 91.0})())

    m.rule_ram_critical()
    m.rule_ram_critical()
    assert len(spoken) == 1


def test_deadline_detected_from_memory():
    from datetime import datetime, timedelta, timezone

    spoken: List[str] = []
    future = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
    m = ProactiveMonitor(speak_fn=lambda msg: spoken.append(msg), memory=_dummy_memory(f"OS exam on {future}"))
    m.rule_deadline_approaching()
    assert any("days remaining" in x for x in spoken)


def test_monitor_starts_as_daemon_thread(monkeypatch):
    m = ProactiveMonitor(speak_fn=lambda _msg: None)
    monkeypatch.setattr(m, "check_all_rules", lambda: m.stop())
    t = m.start()
    t.join(timeout=2)
    assert t.daemon is True


def test_all_rules_wrapped_in_try_except(monkeypatch):
    m = ProactiveMonitor(speak_fn=lambda _msg: None)
    monkeypatch.setattr(m, "rule_ram_critical", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    # Should not raise even if one rule fails.
    m.check_all_rules()
