"""
Eonix OS — GoalEngine
======================
Manages Goal Objects — the first-class OS primitive in Eonix OS.
Goals track what the user is working on, related files, progress,
and context across sessions and devices.

Usage: python3 engine.py
"""

import os
import json
import uuid
from datetime import datetime, timezone


GOALS_DIR = os.path.expanduser("~/.eonix/goals")
ACTIVE_GOAL_FILE = os.path.expanduser("~/.eonix/active_goal.json")


class Goal:
    """A Goal object — the new first-class OS primitive."""

    def __init__(self, title: str, goal_id: str | None = None):
        self.goal_id = goal_id or str(uuid.uuid4())
        self.title = title
        self.created = datetime.now(timezone.utc).isoformat()
        self.status = "active"
        self.progress_score = 0.0
        self.related_files: list[str] = []
        self.related_apps: list[str] = []
        self.related_branches: list[str] = []
        self.context_snapshots: list[dict] = []
        self.devices: list[str] = []

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "created": self.created,
            "status": self.status,
            "progress_score": self.progress_score,
            "related_files": self.related_files,
            "related_apps": self.related_apps,
            "related_branches": self.related_branches,
            "context_snapshots": self.context_snapshots,
            "devices": self.devices,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        goal = cls(data["title"], data.get("goal_id"))
        goal.created = data.get("created", goal.created)
        goal.status = data.get("status", "active")
        goal.progress_score = data.get("progress_score", 0.0)
        goal.related_files = data.get("related_files", [])
        goal.related_apps = data.get("related_apps", [])
        goal.related_branches = data.get("related_branches", [])
        goal.context_snapshots = data.get("context_snapshots", [])
        goal.devices = data.get("devices", [])
        return goal


class GoalEngine:
    """Manages the lifecycle of Goal objects."""

    def __init__(self):
        os.makedirs(GOALS_DIR, exist_ok=True)
        self.goals: dict[str, Goal] = {}
        self._load_all()

    def _load_all(self):
        """Load all goals from disk."""
        for fname in os.listdir(GOALS_DIR):
            if fname.endswith(".json"):
                filepath = os.path.join(GOALS_DIR, fname)
                with open(filepath) as f:
                    data = json.load(f)
                    goal = Goal.from_dict(data)
                    self.goals[goal.goal_id] = goal

    def _save_goal(self, goal: Goal):
        """Persist a goal to disk."""
        filepath = os.path.join(GOALS_DIR, f"{goal.goal_id}.json")
        with open(filepath, "w") as f:
            json.dump(goal.to_dict(), f, indent=2)

    def create_goal(self, title: str) -> Goal:
        """Create a new goal and set it as active."""
        goal = Goal(title)
        self.goals[goal.goal_id] = goal
        self._save_goal(goal)
        self.set_active(goal.goal_id)
        print(f"[GoalEngine] Created goal: {title} ({goal.goal_id[:8]}...)")
        return goal

    def set_active(self, goal_id: str):
        """Set a goal as the currently active goal."""
        if goal_id in self.goals:
            goal = self.goals[goal_id]
            with open(ACTIVE_GOAL_FILE, "w") as f:
                json.dump(goal.to_dict(), f, indent=2)
            print(f"[GoalEngine] Active goal: {goal.title}")

    def update_progress(self, goal_id: str, score: float):
        """Update progress score for a goal."""
        if goal_id in self.goals:
            self.goals[goal_id].progress_score = max(0.0, min(1.0, score))
            self._save_goal(self.goals[goal_id])

    def add_related_file(self, goal_id: str, filepath: str):
        """Associate a file with a goal."""
        if goal_id in self.goals:
            if filepath not in self.goals[goal_id].related_files:
                self.goals[goal_id].related_files.append(filepath)
                self._save_goal(self.goals[goal_id])

    def list_goals(self) -> list[dict]:
        """List all goals."""
        return [g.to_dict() for g in self.goals.values()]

    def get_active(self) -> dict | None:
        """Get the currently active goal."""
        if os.path.exists(ACTIVE_GOAL_FILE):
            with open(ACTIVE_GOAL_FILE) as f:
                return json.load(f)
        return None


def main():
    """Interactive GoalEngine CLI for development."""
    engine = GoalEngine()

    print("=" * 50)
    print("  EONIX GoalEngine — Development CLI")
    print("=" * 50)
    print("Commands: new <title>, list, active, progress <id> <score>, quit\n")

    while True:
        try:
            cmd = input("goal> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd or cmd == "quit":
            break
        elif cmd.startswith("new "):
            title = cmd[4:].strip()
            if title:
                engine.create_goal(title)
        elif cmd == "list":
            for g in engine.list_goals():
                status_icon = "●" if g["status"] == "active" else "○"
                print(f"  {status_icon} [{g['goal_id'][:8]}] "
                      f"{g['title']} ({g['progress_score']*100:.0f}%)")
        elif cmd == "active":
            active = engine.get_active()
            if active:
                print(f"  Active: {active['title']} "
                      f"({active['progress_score']*100:.0f}%)")
            else:
                print("  No active goal")
        elif cmd.startswith("progress "):
            parts = cmd.split()
            if len(parts) == 3:
                gid = parts[1]
                score = float(parts[2])
                # Find goal by prefix match
                for goal_id in engine.goals:
                    if goal_id.startswith(gid):
                        engine.update_progress(goal_id, score)
                        break

    print("\n[GoalEngine] Session ended.")


if __name__ == "__main__":
    main()
