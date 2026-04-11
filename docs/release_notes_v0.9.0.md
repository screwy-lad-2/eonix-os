## Eonix OS v0.9.0 — Month 9: ISO Hardening + AI Hooks

### Boot Verification (April 11, 2026)
All 8 boot checks passed on `eonix-os-0.9.0.iso`:
- GRUB menu ✅ | Agents x5 ✅ | MIND v2 ✅
- vboxvideo ✅ | GTK4 desktop ✅ | GoalPanel ✅

### What's New in v0.9.0
- All 4 VM boot bugs fixed (httpx, mind_v2 path, vboxvideo, hostname)
- v1.2 retrain hooks: `on_retrain_complete()`, `compare_model_versions()`, rollback at >2% degradation
- Hub `/hub/status` now returns `model_version`, `model_ready`, `next_retrain_eta`
- `train_scheduler.py` persists precision/recall/F1
- 16 Month 9 regression tests (15 pass, 1 skip Windows)
- CI: manual trigger only (quota-safe)

### AI Model v1.2 — Live (April 2026)
- Trained on 148,812 rows (threshold: 120,000)
- v1.1 accuracy: 61.61% → v1.2 accuracy: 63.47%
- Improvement: +1.86%
- Rollback: NOT triggered (above 2% safety threshold)
- ONNX export: complete
- Precision/Recall/F1: persisted to metadata

### Test Results
  Windows: 162 passed | 0 failed
  Linux:   182+ passed | 0 failed
  CI jobs: 30 defined

### Install
  VirtualBox: 4GB RAM, 2 CPUs, VMSVGA display
  QEMU: `qemu-system-x86_64 -cdrom eonix-os-0.9.0.iso -m 4G`

### Next: v1.0.0 — Month 10/11 Public Release

### Download ISO
[eonix-os-0.9.0.iso � Google Drive](YOUR_GOOGLE_DRIVE_LINK_HERE)

