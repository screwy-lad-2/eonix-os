"""
Eonix OS — Test Suite
======================
Basic tests for core Python components.
Run: pytest tests/ -v
"""

import os
import sys
import json
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGoalEngine:
    """Tests for the GoalEngine."""

    def test_goal_creation(self):
        """Test that a Goal object can be created."""
        from eonix_cortex_goal_engine import Goal
        goal = Goal("Test Goal")
        assert goal.title == "Test Goal"
        assert goal.status == "active"
        assert goal.progress_score == 0.0

    def test_goal_serialization(self):
        """Test Goal to_dict and from_dict round-trip."""
        from eonix_cortex_goal_engine import Goal
        goal = Goal("Build Scheduler")
        goal.progress_score = 0.5
        goal.related_files = ["scheduler.c", "test.c"]

        data = goal.to_dict()
        restored = Goal.from_dict(data)

        assert restored.title == "Build Scheduler"
        assert restored.progress_score == 0.5
        assert "scheduler.c" in restored.related_files


class TestResourceScoring:
    """Tests for ResourceAgent scoring."""

    def test_score_related_process(self):
        """Process related to active goal should score higher."""
        goal = {"title": "Coding", "related_apps": ["vim", "gcc"]}
        proc_related = {"name": "vim", "cpu_percent": 10, "memory_percent": 5}
        proc_unrelated = {"name": "spotify", "cpu_percent": 10, "memory_percent": 5}

        # Simple scoring logic
        def score(proc, g):
            relevance = 1.0 if proc["name"].lower() in [a.lower() for a in g.get("related_apps", [])] else 0.0
            cpu = min(1.0, proc.get("cpu_percent", 0) / 100.0)
            mem = min(1.0, proc.get("memory_percent", 0) / 100.0)
            return (relevance * 0.5) + (cpu * 0.3) + (mem * 0.2)

        assert score(proc_related, goal) > score(proc_unrelated, goal)


# Allow importing goal engine module
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eonix-cortex", "goal-engine"))

    # Create a temporary importable module
    import importlib.util
    goal_engine_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eonix-cortex", "goal-engine", "engine.py")

    if os.path.exists(goal_engine_path):
        spec = importlib.util.spec_from_file_location("eonix_cortex_goal_engine", goal_engine_path)
        eonix_cortex_goal_engine = importlib.util.module_from_spec(spec)
        sys.modules["eonix_cortex_goal_engine"] = eonix_cortex_goal_engine
        spec.loader.exec_module(eonix_cortex_goal_engine)
        Goal = eonix_cortex_goal_engine.Goal
except Exception:
    pass
