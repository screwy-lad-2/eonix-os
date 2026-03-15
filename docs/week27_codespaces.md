# Week 27 ISO Build in GitHub Codespaces

This guide runs the Week 27 ISO pipeline on Linux, which is required for debootstrap and live-image tooling.

## 1) Open in Codespaces

1. Push your branch to GitHub.
2. Open repository on GitHub.
3. Click Code -> Codespaces -> Create codespace on branch.

## 2) Verify environment

Run:

```bash
python --version
uname -a
```

Expected: Linux host inside Codespaces.

## 3) Run Week 27 automation

From repository root:

```bash
bash iso/codespaces_build.sh
```

This performs:
- apt install of ISO toolchain
- syntax checks of ISO scripts
- unit tests in iso/test_iso_build.py
- GRUB staging
- cumulative run_all_tests.py

## 4) Full base bootstrap build

To run debootstrap and EONIX install inside chroot:

```bash
RUN_FULL_BUILD=1 bash iso/codespaces_build.sh
```

Expected output includes:
- [build_base] ✅ Base system ready
- [build_base] Size: X

## 5) Manual commands (optional)

```bash
bash -n iso/build_base.sh
bash -n iso/chroot_setup.sh
bash -n iso/grub_config.sh
python -m pytest iso/test_iso_build.py -v
sudo bash iso/build_base.sh
```

## 6) Suggested release flow for v0.8.0-alpha

```bash
git add -A
git commit -m "feat(iso): base system bootstrap + GRUB config + ISO build scripts"
git tag -a v0.8.0-alpha -m "Week 27: ISO base system — EONIX OS bootable image pipeline started"
git push origin master --tags
```

## Note for Windows local dev

On Windows, keep using syntax checks and repository tests. Use Codespaces/Linux for the actual bootstrap build and later ISO artifact generation.
