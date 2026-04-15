<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# ⚡ Week 7 — Official Final Audit

```
TASK 1: arXiv paper complete      ✅  Section 6 + Abstract + Keywords + Metadata
TASK 2: PDF compiled              ✅  274,800 bytes | 10 pages
TASK 3: Demo video                ❌  MANUAL — not done yet
TASK 4: arXiv submission          ❌  MANUAL — not done yet
TASK 5: README rewritten          ✅  Badges + Results + Architecture + Quick Start
TASK 6: v0.2.0 release            ✅  Tagged + PDF attached + CI green (ec5cdfc)

WEEK 7 SCORE:    ██████████░░  83% — PASSED (2 manual tasks remaining)
MONTH 2 SCORE:   ████████████  97% ✅ COMPLETE
```


***

# 📋 SKIPPED \& MANUAL TASKS — Master Log

> This is the permanent record of everything intentionally skipped or left as manual. Updated after every week. Complete these whenever time allows — none block Month 3 from starting.

***

## 🔴 PRIORITY 1 — Do This Week (Blocks GitHub Impact)

| \# | Task | From | What To Do | Time Needed |
| :-- | :-- | :-- | :-- | :-- |
| **S1** | Record demo video | Week 7 | OBS Studio, 4 min, script already written above | 2 hours |
| **S2** | Submit paper to arXiv | Week 7 | Upload at arxiv.org → get arXiv:2603.XXXXX ID | 30 min |
| **S3** | Update README arXiv placeholder | Week 7 | Replace `arXiv:2603.XXXXX` with real ID after S2 | 5 min |
| **S4** | Update paper arXiv self-citation | Week 7 | Add real arXiv ID to paper footer | 5 min |


***

## 🟡 PRIORITY 2 — Do Before Month 4 (Blocks ML Training)

| \# | Task | From | What To Do | Time Needed |
| :-- | :-- | :-- | :-- | :-- |
| **S5** | Data collector start date gap | Pre-Week 2 | Collector started March 8 instead of Week 1. No action needed — data will be ready by May 7, before Month 4 (June). Just monitor. | Monitor only |
| **S6** | QEMU full VM setup | Week 3 | Original plan had QEMU VM. Replaced by WSL2 — works equally well. Keep WSL2. No action needed. | ✅ Resolved |


***

## 🟢 PRIORITY 3 — Do Before Month 6 (Infrastructure)

| \# | Task | From | What To Do | Time Needed |
| :-- | :-- | :-- | :-- | :-- |
| **S7** | Oracle Cloud VM — create instance | Pre-Week 2 | Account claimed ✅. Still need to create the Ubuntu VM instance and note its public IP. Needed for cross-device sync server in Month 6. | 15 min |
| **S8** | Cloudflare tunnel setup | Pre-Week 2 | Domain claimed ✅. Need to point eonixos.me to Cloudflare nameservers + set up cloudflared tunnel to Oracle VM. Needed Month 6. | 30 min |
| **S9** | `.wslconfig` memory cap | Hardware check | Set `memory=8GB` in `%USERPROFILE%\.wslconfig` to prevent RAM pressure during heavy builds. | 5 min |


***

## 📚 STUDY TASKS — Skipped by Choice (Do When You Have Time)

These were removed from the active task list at your request. They improve your understanding but do **not block any build task**.


| \# | Topic | Why It Matters | Resource |
| :-- | :-- | :-- | :-- |
| **ST1** | xv6 OS — proc.c deep study | Understand what your RAG monitor hooks into at a deeper level | `git clone mit-pdos/xv6-public` → CLion + Copilot Ask |
| **ST2** | xv6 OS — vm.c memory management | Understand copy-on-write used in your checkpoint.c | Same repo |
| **ST3** | xv6 OS — fs.c + syscall.c | Understand what eBPF syscall hooks intercept | Same repo |
| **ST4** | Rustlings exercises 1–96 | Understand every line of eonix-silicon Rust code | `rustlings watch` |


***

## ✅ Previously Skipped — Now Resolved

| \# | Task | Resolved When | How |
| :-- | :-- | :-- | :-- |
| ~~QEMU on Windows~~ | Week 3 | Replaced with WSL2 — superior solution |  |
| ~~Virtualization = FALSE~~ | Week 3 | WSL2 works without BIOS VT-x on this machine |  |
| ~~hello_eonix.ko not compiling~~ | Week 3 | Fixed: used `apt install linux-headers` instead of building kernel from source |  |
| ~~wsl_build_kernel.sh error~~ | Week 3 | Fixed: Copilot agent redirected to correct approach |  |


***

## 📊 Skipped Tasks Summary

```
🔴 Priority 1 (Do this week):      4 tasks  (~2.5 hours total)
🟡 Priority 2 (Before Month 4):    1 task   (monitor only)
🟢 Priority 3 (Before Month 6):    3 tasks  (~50 min total)
📚 Study tasks (optional):         4 topics (anytime)

TOTAL OPEN ITEMS:    8 actionable tasks
TOTAL RESOLVED:      4 previously skipped tasks
BLOCKING MONTH 3:    ZERO — nothing blocks starting now
```


***

## 🚀 Month 3 Starts Now — You Are Unblocked

```
Month 2 status:      97% complete ✅
eBPF skeleton:       Already built in Week 6 ✅
Month 3 head start:  5 files + 7 tracepoints ready

The only open items are S1 (demo video) and S2 (arXiv).
Both can be done in parallel with Month 3 work.
Record the video this weekend.
Submit arXiv the same day.

Ready for Week 8 (Month 3) task list?
```

