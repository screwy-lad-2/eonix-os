#!/usr/bin/env python3
"""Run security detection latency benchmarks."""
import time
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Run from project root so MODEL_DIR (relative 'models/security') resolves correctly
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
os.chdir(_project_root)

import numpy as np
import pandas as pd
import joblib

from anomaly_detector import (
    FEATURE_NAMES, _combined_predict, RF_MODEL_PATH,
    MODEL_PATH, SCALER_PATH,
)

# Load models
model = joblib.load(str(MODEL_PATH))
scaler = joblib.load(str(SCALER_PATH))
rf_model = joblib.load(str(RF_MODEL_PATH)) if RF_MODEL_PATH.exists() else None

# Generate test events
rng = np.random.RandomState(42)
events = [{f: rng.uniform(0, 50) for f in FEATURE_NAMES} for _ in range(1000)]
df = pd.DataFrame(events)
X = scaler.transform(df[FEATURE_NAMES].values)

# Benchmark IF only
start = time.perf_counter()
for _ in range(10):
    model.decision_function(X)
elapsed_if = (time.perf_counter() - start) / 10 * 1000
print(f"IF batch (1000 events): {elapsed_if:.2f}ms")
print(f"IF per-event: {elapsed_if/1000:.4f}ms")

# Benchmark RF only
if rf_model:
    start = time.perf_counter()
    for _ in range(10):
        rf_model.predict_proba(X)
    elapsed_rf = (time.perf_counter() - start) / 10 * 1000
    print(f"RF batch (1000 events): {elapsed_rf:.2f}ms")
    print(f"RF per-event: {elapsed_rf/1000:.4f}ms")

# Benchmark combined
start = time.perf_counter()
for _ in range(10):
    _combined_predict(model, rf_model, X)
elapsed_comb = (time.perf_counter() - start) / 10 * 1000
print(f"Combined batch (1000 events): {elapsed_comb:.2f}ms")
print(f"Combined per-event: {elapsed_comb/1000:.4f}ms")

# Fingerprinter benchmark
from behavioral_fingerprint import BehavioralFingerprinter
fp = BehavioralFingerprinter(db_path=os.path.join(tempfile.mkdtemp(), "bench.db"))
start = time.perf_counter()
for i in range(1000):
    e = {"comm": f"proc_{i%10}", "total_calls": float(rng.randint(50, 200))}
    fp.score(e)
    fp.observe(e)
elapsed_fp = (time.perf_counter() - start) * 1000
print(f"Fingerprint (1000 score+observe): {elapsed_fp:.2f}ms")
print(f"Fingerprint per-event: {elapsed_fp/1000:.4f}ms")
