# Eonix OS AI Model

## Current Model: LightGBM v1.2
- Algorithm: LightGBM gradient boosting
- Trained on: 148,812 scheduling events
- Accuracy: 63.47% (top-1)
- Precision/Recall/F1: saved to metadata/report
- ONNX export: yes (onnxmltools + skl2onnx)

## Auto-Retrain Pipeline
- Threshold: 120,000 rows triggers retrain
- Rollback safety: auto-reverts if accuracy
  drops >2% OR top3 drops >3%
- Version comparison: semver-safe
- Status: python3 eonix-core/scheduler/auto_retrain.py --status --json

## Training
  python3 eonix-core/scheduler/train_scheduler.py
