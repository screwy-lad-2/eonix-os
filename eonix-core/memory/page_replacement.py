"""
Eonix OS — Adaptive Page Replacement Simulator
================================================
Hybrid LRU-K (K=2) + ML-predicted page replacement.
Eviction score = (0.6 × LRU-K recency) + (0.4 × ML access prediction)

Runs a configurable simulation comparing:
  - Pure LRU
  - LRU-K (K=2)
  - Hybrid LRU-K + ML

Exports results to datasets/memory/ as JSON.
"""

import json
import os
import random
import unittest
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Page Table Entry
# ---------------------------------------------------------------------------

class PageEntry:
    __slots__ = ("page_id", "ref_history", "ml_access_prob")

    def __init__(self, page_id: int):
        self.page_id = page_id
        self.ref_history: list[int] = []
        self.ml_access_prob: float = 0.0

    def record_access(self, tick: int) -> None:
        self.ref_history.append(tick)

    def lruk_score(self, current_tick: int, k: int = 2) -> float:
        """Return a recency score based on the K-th most recent access.

        Higher score → more recently used → less likely to evict.
        """
        if not self.ref_history:
            return 0.0
        idx = max(0, len(self.ref_history) - k)
        k_ref = self.ref_history[idx]
        return k_ref / max(current_tick, 1)

    def hybrid_score(self, current_tick: int, k: int = 2) -> float:
        """Eviction score used by the hybrid algorithm.

        Higher score → keep the page. Evict the page with the *lowest* score.
        """
        return 0.6 * self.lruk_score(current_tick, k) + 0.4 * self.ml_access_prob


# ---------------------------------------------------------------------------
# Simulators
# ---------------------------------------------------------------------------

class PageReplacementSimulator:
    """Runs a page-replacement simulation with a given algorithm."""

    def __init__(self, num_frames: int, algorithm: str = "hybrid", k: int = 2):
        self.num_frames = num_frames
        self.algorithm = algorithm  # "lru", "lruk", "hybrid"
        self.k = k
        self.frames: OrderedDict[int, PageEntry] = OrderedDict()
        self.page_faults = 0
        self.total_accesses = 0
        self.tick = 0

    # -- public API ---------------------------------------------------------

    def access(self, page_id: int, ml_prob: float = 0.0) -> bool:
        """Access a page. Returns True if a page fault occurred."""
        self.tick += 1
        self.total_accesses += 1

        if page_id in self.frames:
            entry = self.frames[page_id]
            entry.record_access(self.tick)
            entry.ml_access_prob = ml_prob
            # Move to end for pure-LRU ordering
            self.frames.move_to_end(page_id)
            return False

        # Page fault
        self.page_faults += 1

        if len(self.frames) >= self.num_frames:
            self._evict()

        entry = PageEntry(page_id)
        entry.record_access(self.tick)
        entry.ml_access_prob = ml_prob
        self.frames[page_id] = entry
        return True

    @property
    def fault_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.page_faults / self.total_accesses

    def stats(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "num_frames": self.num_frames,
            "total_accesses": self.total_accesses,
            "page_faults": self.page_faults,
            "fault_rate": round(self.fault_rate, 4),
        }

    # -- eviction strategies ------------------------------------------------

    def _evict(self) -> None:
        if self.algorithm == "lru":
            # Evict least-recently used (first item in OrderedDict)
            self.frames.popitem(last=False)
        elif self.algorithm == "lruk":
            victim = min(self.frames.values(),
                         key=lambda e: e.lruk_score(self.tick, self.k))
            del self.frames[victim.page_id]
        elif self.algorithm == "hybrid":
            victim = min(self.frames.values(),
                         key=lambda e: e.hybrid_score(self.tick, self.k))
            del self.frames[victim.page_id]
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")


# ---------------------------------------------------------------------------
# Comparison runner
# ---------------------------------------------------------------------------

def generate_access_pattern(length: int = 2000, num_pages: int = 100,
                            seed: int = 42) -> list[int]:
    """Generate a realistic access pattern with locality of reference."""
    rng = random.Random(seed)
    hot_pages = list(range(num_pages // 5))  # 20% hot set
    cold_pages = list(range(num_pages // 5, num_pages))

    pattern: list[int] = []
    for _ in range(length):
        if rng.random() < 0.8:
            pattern.append(rng.choice(hot_pages))
        else:
            pattern.append(rng.choice(cold_pages))
    return pattern


def run_comparison(num_frames: int = 32, pattern_length: int = 2000,
                   num_pages: int = 100, seed: int = 42) -> list[dict]:
    """Run all three algorithms on the same access pattern and return stats."""
    pattern = generate_access_pattern(pattern_length, num_pages, seed)

    results = []
    for algo in ("lru", "lruk", "hybrid"):
        sim = PageReplacementSimulator(num_frames, algorithm=algo)
        for page_id in pattern:
            # ML probability: hot pages get higher prediction
            ml_prob = 0.8 if page_id < num_pages // 5 else 0.2
            sim.access(page_id, ml_prob=ml_prob)
        results.append(sim.stats())

    return results


def export_results(results: list[dict], output_dir: str | None = None) -> str:
    """Write comparison results to JSON. Returns the output path."""
    if output_dir is None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        output_dir = str(repo_root / "datasets" / "memory")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "page_replacement_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_comparison()
    for r in results:
        print(f"{r['algorithm']:>8s}  faults={r['page_faults']:4d}  "
              f"rate={r['fault_rate']:.4f}")
    out = export_results(results)
    print(f"\nResults exported to {out}")


# ===========================================================================
# Tests
# ===========================================================================

class TestPageEntry(unittest.TestCase):
    def test_lruk_score_increases_with_recency(self):
        p = PageEntry(1)
        p.record_access(10)
        p.record_access(20)
        score_early = p.lruk_score(100)
        p.record_access(80)
        p.record_access(90)
        score_late = p.lruk_score(100)
        self.assertGreater(score_late, score_early)


class TestPageReplacementSimulator(unittest.TestCase):
    def test_no_fault_on_cached_page(self):
        sim = PageReplacementSimulator(num_frames=4, algorithm="lru")
        sim.access(1)  # fault
        fault = sim.access(1)  # hit
        self.assertFalse(fault)

    def test_fault_when_page_not_cached(self):
        sim = PageReplacementSimulator(num_frames=2, algorithm="lru")
        self.assertTrue(sim.access(1))
        self.assertTrue(sim.access(2))
        self.assertTrue(sim.access(3))  # evicts page 1

    def test_hybrid_beats_or_matches_lru(self):
        """Hybrid should achieve <= fault rate of pure LRU on workload with locality."""
        results = run_comparison(num_frames=16, pattern_length=5000, seed=99)
        lru_rate = results[0]["fault_rate"]
        hybrid_rate = results[2]["fault_rate"]
        # Hybrid should be at least as good (allow small tolerance)
        self.assertLessEqual(hybrid_rate, lru_rate + 0.02)
