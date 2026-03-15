## v0.8.0-beta — Week 28: ISO Assembly & QEMU Smoke
**Released:** May 2026

### What's New

#### ISO Build & Assembly (Week 28)
- Added squashfs compressor: `iso/build_squashfs.sh`
- Added ISO assembler: `iso/build_iso.sh`
- Added QEMU boot test template: `results/week28_qemu_boot_test.txt`
- Added CI coverage for ISO assembly scripts

#### GitHub Codespaces Support
- Ubuntu devcontainer still supported; automation script now installs deps and can run squashfs/ISO steps.

#### Test + CI Updates
- Extended `iso/test_iso_build.py` to include syntax checks for squashfs/ISO scripts
- New CI job `test-iso-assembly` (syntax + unit tests; no full build)
- Cumulative runner targets updated to Week 28 (158+)

### Week 28 Notes
- Full squashfs/ISO build and QEMU tests require Linux with virtualization.
- Windows local dev should run syntax/unit checks only; use Codespaces/Linux for actual artifacts.

### Target Status
| Metric | Target |
|---|---|
| CI jobs | 28 |
| Cumulative tests | 158+ |
| Full ISO build | Linux/Codespaces |
| QEMU boot | Manual (Linux host) |

---
*Next: v0.8.0-rc — finalize ISO boot UX, polish GRUB theme, and publish checksum*
