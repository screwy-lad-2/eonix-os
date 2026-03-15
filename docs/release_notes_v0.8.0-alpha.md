## v0.8.0-alpha — Week 27: ISO Base System Pipeline
**Released:** May 2026

### What's New

#### ISO Build Pipeline (Week 27)
- Added Linux base bootstrap orchestration script: `iso/build_base.sh`
- Added chroot provisioning script with package/user/system setup: `iso/chroot_setup.sh`
- Added GRUB config staging script for BIOS + UEFI structure: `iso/grub_config.sh`
- Added Codespaces automation runner: `iso/codespaces_build.sh`

#### GitHub Codespaces Support
- Added `.devcontainer/devcontainer.json` for Ubuntu-based Codespaces with Python preconfigured
- Added step-by-step Linux execution guide: `docs/week27_codespaces.md`
- Full bootstrap flow can be executed via:
  - `bash iso/codespaces_build.sh`
  - `RUN_FULL_BUILD=1 bash iso/codespaces_build.sh`

#### Test + CI Updates
- Added ISO unit suite: `iso/test_iso_build.py`
  - Validates script syntax, installer dev-flag usage, autostart profile, GRUB menu, timeout, safe mode, and EFI structure
- Added CI job `test-iso-scripts` in `.github/workflows/test.yml`
  - Syntax checks for ISO shell scripts
  - Runs `python -m pytest iso/test_iso_build.py -v`
- Updated cumulative runner `run_all_tests.py`
  - Added ISO suite to `SUITES`
  - Added Week 27 target line: `>= 154 passed`

### Week 27 Notes
- Actual debootstrap/chroot bootstrap requires Linux privileges and tooling.
- Windows local dev should run non-destructive checks; use Codespaces/Linux for full build.

### Target Status
| Metric | Target |
|---|---|
| CI jobs | 27 |
| Cumulative tests | 154+ |
| Full ISO bootstrap | Linux/Codespaces |

---
*Next: v0.8.0-beta — live image assembly and boot artifact validation*
