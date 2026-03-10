# Eonix OS — Submission Playbook (arXiv + Demo Video)

Complete step-by-step guide for Saturday March 14, 2026.
Estimated total time: **2–3 hours** (video ~1h, arXiv ~45min, updates ~10min).

---

## Part A: arXiv Submission Rules & Compliance Checklist

### A.1 arXiv Source Requirements (MANDATORY)

arXiv **always compiles your .tex from source** server-side. You upload
`.tex` source, **not** a PDF. Key rules:

| Rule | Our Status | Notes |
|------|:----------:|-------|
| **TeX source required** — arXiv compiles server-side with TeX Live 2023 | ✅ | Single `arxiv-paper.tex` file, no external .sty |
| **`\pdfoutput=1`** — must appear before `\documentclass` | ✅ | Line 4 of our .tex |
| **US Letter paper** (`letterpaper`) — arXiv default; `a4paper` causes margin warnings | ✅ | Changed to `letterpaper` |
| **`hyperref` loaded last** — must come after all other packages to avoid conflicts | ✅ | Loaded last in our preamble |
| **No `\usepackage[utf8]{inputenc}`** — redundant with TeX Live 2020+; can cause encoding errors | ✅ | Removed |
| **All figures in TikZ/pgfplots** — no external image files needed | ✅ | 9 figures, all inline TikZ |
| **Inline bibliography** (`\begin{thebibliography}`) — no .bib file needed | ✅ | 15 `\bibitem` entries |
| **No generated files** — do NOT upload .aux, .log, .pdf, .synctex, .out | ✅ | Upload .tex only |
| **Standard packages only** — booktabs, amsmath, tikz, pgfplots, hyperref all available | ✅ | No custom .sty files |
| **File size < 10 MB** (source), **< 50 MB** (total with ancillary) | ✅ | ~40 KB .tex source |
| **No absolute paths** — no `C:\...` or `/home/...` paths in source | ✅ | |
| **No `\input{}` or `\include{}`** — single-file submission is simplest | ✅ | Self-contained |

### A.2 arXiv Metadata Rules

| Rule | Details |
|------|---------|
| **Title** | Must match the `\title{}` in your .tex exactly |
| **Author list** | Must match `\author{}` — use full legal name |
| **Abstract** | Plain text (no LaTeX math); arXiv strips most formatting. Keep under 1,920 characters |
| **Primary category** | **cs.OS** (Operating Systems) — choose carefully, cannot change after submission |
| **Cross-list categories** | **cs.DC** + **cs.CR** — adds visibility in those feeds |
| **Comments field** | "15 pages, 9 figures, 6 tables, open-source" — helps reviewers |
| **License** | "arXiv.org perpetual, non-exclusive license" (default, recommended) |
| **Journal-ref** | Leave blank (not published in a journal) |
| **DOI** | Leave blank |
| **Report-no** | Leave blank |

### A.3 arXiv Submission Restrictions

1. **New accounts** need endorsement for cs.OS — if your account is new, you may need a faculty endorser (a professor with prior arXiv papers in cs.OS can endorse you via email)
2. **Submission freeze**: arXiv has announcement deadlines — papers submitted after 14:00 ET on weekdays appear the next business day. Saturday submissions appear Monday evening
3. **Moderation**: cs.OS papers may be held 1–3 days for moderation; this is normal
4. **Revision**: After submission, you can upload revisions (`v2`, `v3`...) at any time via "Replace" on your submission page
5. **Withdrawal**: Papers can be withdrawn but the arXiv ID is never deleted — the stub remains
6. **One submission per day** per author — don't try submitting multiple papers in one day

### A.4 Common arXiv Rejection Reasons (and How We Avoid Them)

| Rejection Reason | Our Mitigation |
|-----------------|----------------|
| TeX compilation failure | We use only standard TeX Live packages; `\pdfoutput=1` set; test on Overleaf first |
| Missing figures/files | All figures are inline TikZ — zero external dependencies |
| Abstract too long / contains LaTeX | Our abstract is plain-text safe (uses `$\times$` etc. which arXiv renders correctly) |
| Wrong category | cs.OS is correct — kernel-level research on deadlock + eBPF |
| Overlapping content | This is original work — no prior publications |
| Missing author endorsement | See endorsement process below if needed |

---

## Part B: Step-by-Step arXiv Submission

### Step 1: Create arXiv Account (if you don't have one)

1. Go to **https://arxiv.org/user/register**
2. Fill in:
   - **Username**: your choice (e.g., `shahnoor-butt`)
   - **Email**: use your university email (`@presidencyuniversity.in`) — institutional emails are preferred
   - **Full name**: Shahnoor Ahmed Butt
   - **Affiliation**: Presidency University, Bengaluru, India
   - **Country**: India
   - **Default category**: cs.OS
3. Confirm your email
4. **Endorsement check**: After registration, try to start a new submission. If arXiv asks for endorsement:
   - You need ONE person who has published in cs.OS (or cs.DC, cs.CR) on arXiv to endorse you
   - Ask a professor — they receive an email with a link to click
   - Endorsement is instant once they click the link
   - If no endorser available: submit under cs.DC or cs.CR instead (broader categories, less strict endorsement)

### Step 2: Test Compilation on Overleaf (CRITICAL — Do This First)

This ensures arXiv will compile your .tex without errors.

1. Go to **https://www.overleaf.com** → Log in or create free account
2. **New Project** → **Upload Project**
3. Upload `docs/arxiv-paper.tex` as a single file
4. Click **Recompile** — verify:
   - [ ] No compilation errors (check the log)
   - [ ] All 9 TikZ figures render correctly
   - [ ] All 6 tables render correctly
   - [ ] All 15 bibliography entries appear
   - [ ] All cross-references resolve (no "??" in the text)
   - [ ] Page count is ~15 pages
   - [ ] All colors render (architecture diagram should show blue/green regions)
5. **Download PDF** → save as `docs/arxiv-paper.pdf` (for your records — NOT for arXiv upload)

**If Overleaf shows errors:**
- `pgfplots` version mismatch → change `\pgfplotsset{compat=1.18}` to `\pgfplotsset{compat=1.17}`
- `tikz` library not found → arXiv TeX Live should have all libraries we use; check for typos
- Encoding errors → we removed `inputenc`, so this shouldn't happen

### Step 3: Prepare the Submission Package

**Option A — Single .tex file (recommended, simplest):**

```powershell
# From your project root:
cd C:\Users\laska\Projects\eonix-os

# Create a clean submission folder
New-Item -ItemType Directory -Force -Path submission
Copy-Item docs\arxiv-paper.tex submission\arxiv-paper.tex
```

Upload the single `arxiv-paper.tex` file to arXiv.

**Option B — Zip archive (if arXiv has issues with single file):**

```powershell
cd C:\Users\laska\Projects\eonix-os

New-Item -ItemType Directory -Force -Path submission
Copy-Item docs\arxiv-paper.tex submission\arxiv-paper.tex

# Create zip (arXiv also accepts .tar.gz)
Compress-Archive -Path submission\arxiv-paper.tex -DestinationPath submission\eonix-os-arxiv.zip -Force
```

Upload the zip file.

### Step 4: Submit to arXiv

1. Go to **https://arxiv.org/submit**
2. Click **Start New Submission**
3. **Step 1 of 6 — Type & License:**
   - Submission type: **New**
   - License: **arXiv.org perpetual, non-exclusive license to distribute this article** ← select this
   - Click **Continue**
4. **Step 2 of 6 — Upload files:**
   - Click **Choose File** → select `arxiv-paper.tex` (or the .zip)
   - Wait for upload to complete
   - Click **Process**
   - arXiv will compile your .tex — **wait for "Processing completed"**
   - If errors appear: read the log, fix the .tex, re-upload
   - Click **Continue**
5. **Step 3 of 6 — Metadata:**

   Fill in these fields exactly:

   | Field | Value |
   |-------|-------|
   | **Title** | `Eonix OS: A Self-Healing, Proactive Security Kernel with Autonomous Deadlock Recovery and eBPF Threat Detection` |
   | **Authors** | `Shahnoor Ahmed Butt` |
   | **Abstract** | *(see below)* |
   | **Comments** | `15 pages, 9 figures, 6 tables, open-source at https://github.com/shahnoor-exe/eonix-os` |
   | **Primary category** | `cs.OS — Operating Systems` |
   | **Cross-list** | `cs.DC — Distributed, Parallel, and Cluster Computing` and `cs.CR — Cryptography and Security` |
   | **ACM classes** | `D.4.1 (Process Management), D.4.6 (Security and Protection)` |
   | **MSC classes** | *(leave blank)* |
   | **Journal-ref** | *(leave blank)* |
   | **DOI** | *(leave blank)* |
   | **Report-no** | *(leave blank)* |

   **Abstract to paste** (plain text, no LaTeX):

   ```
   Deadlocks -- permanent circular waits among concurrent processes -- remain
   an unsolved problem in production operating systems; every major kernel in
   use today simply ignores them. No existing system provides autonomous,
   kernel-level deadlock detection and recovery for general-purpose workloads.
   We present Eonix OS, a Linux-based research operating system with two core
   contributions: (1) a loadable kernel module that maintains a live Resource
   Allocation Graph via kprobes on mutex operations and runs an iterative
   depth-first search every 500ms to detect cycles, achieving 100% detection
   across 130 deadlock scenarios, zero false positives, and a mean recovery
   latency of 279ms -- 107x faster than manual reboot; and (2) an eBPF-based
   security fabric that monitors 7 syscall tracepoints in real time,
   processing events through a combined Isolation Forest and Random Forest
   anomaly detection pipeline augmented by Welford-algorithm behavioral
   fingerprinting, achieving 100% recall on the ADFA-LD intrusion detection
   dataset (833 normal + 746 attack traces) with a tiered response system
   (log -> restrict -> isolate) and near-zero CPU overhead. Together, these
   subsystems demonstrate that autonomous self-healing and proactive threat
   detection are achievable within the Linux kernel's existing extension
   mechanisms. The module, eBPF monitor, security pipeline, and this paper
   are open-source at https://github.com/shahnoor-exe/eonix-os.
   ```

   - Click **Continue**

6. **Step 4 of 6 — Preview:**
   - arXiv renders a PDF preview from your .tex
   - **Verify carefully:**
     - [ ] Title and author correct
     - [ ] Abstract renders properly
     - [ ] All 9 figures visible (architecture, RAG cycle, recovery pipeline, bar charts, etc.)
     - [ ] All 6 tables visible
     - [ ] Bibliography has 15 entries
     - [ ] No "??" or broken cross-references
     - [ ] Page count ~15
   - If anything is wrong → go back and fix
   - Click **Continue**

7. **Step 5 of 6 — Add co-authors:**
   - No co-authors → Click **Continue**

8. **Step 6 of 6 — Final confirmation:**
   - Review all metadata one last time
   - Check the box: "I have read and agree to the arXiv submission policies"
   - Click **Submit**

### Step 5: After Submission

1. **Confirmation email** arrives within minutes — contains your temporary submission ID
2. **arXiv ID assigned** within 1–2 business days (format: `2603.XXXXX`)
3. **Paper goes live** after the next announcement cycle (typically next business day after ID assignment)
4. **Saturday submissions** typically appear on **Monday evening** (US Eastern Time) or **Tuesday morning** (IST)

---

## Part C: Post-Submission Updates (After arXiv ID Arrives)

### Step C.1: Update All Placeholders

Once you receive the arXiv ID email (e.g., `2603.12345`):

```powershell
cd C:\Users\laska\Projects\eonix-os

# Automated replacement across README.md, arxiv-paper.md, arxiv-paper.tex
python scripts/update_arxiv_id.py 2603.12345
```

This replaces `2603.XXXXX` with the real ID in:
- `README.md` — badge link, arXiv URL, BibTeX citation
- `docs/arxiv-paper.md`
- `docs/arxiv-paper.tex`

### Step C.2: Commit and Push

```powershell
git add -A
git commit -m "docs: update arXiv ID to 2603.12345"
git push origin master
```

### Step C.3: Update YouTube Description

Edit your YouTube video description to replace `2603.XXXXX` with the real arXiv ID.

---

## Part D: Demo Video (OBS, 4 minutes)

### Prerequisites

1. **OBS Studio** — download from https://obsproject.com if not installed
2. **WSL2 Ubuntu** with kernel headers (you already have this)
3. **Kernel module** already built (if not, the script handles it)

### OBS Setup (10 min)

1. Open OBS Studio
2. Settings → Output:
   - Recording Format: **mp4**
   - Encoder: x264 (or NVENC if available)
   - Resolution: **1920×1080**
   - FPS: **30**
3. Settings → Audio:
   - Enable **Desktop Audio** (off)
   - Enable **Mic/Auxiliary Audio** (your microphone)
4. Sources:
   - Add **Window Capture** → select your WSL2 terminal (Windows Terminal recommended)
   - Add **Audio Input Capture** → your mic
5. Optional: Add a **Text (GDI+)** source in the corner with "Eonix OS Demo" as a watermark

### Recording Script

The terminal commands are fully automated. You just need to narrate.

```powershell
# From Windows, open WSL2:
wsl

# Inside WSL2:
cd /mnt/c/Users/laska/Projects/eonix-os
bash scripts/demo_video_commands.sh
```

The script pauses between each section — press ENTER when ready.

### Narration Guide (speak these while the commands run)

| Time | Section | What to Say |
|------|---------|-------------|
| 0:00 | Intro | "Hi, I'm Shahnoor. This is Eonix OS — a self-healing operating system I built as a 2nd-year B.Tech student. I'll show you autonomous deadlock recovery and eBPF security detection, both running in a real Linux kernel." |
| 0:20 | Build | "First, let's build the kernel module. It's about 770 lines of C — a loadable kernel module that hooks into mutex operations via kprobes." |
| 0:40 | Load | "Now I'll load it into the running kernel. You can see it registered in lsmod, and the dmesg output shows our RAG monitor initialized with 5 subsystems." |
| 1:00 | 2-way | "Let's trigger a classic 2-way deadlock. Process 1001 holds resource 1 and waits on 2. Process 1002 holds 2 and waits on 1. That's a circular wait — the textbook deadlock. Watch the log..." *(pause for detection)* "Detected and recovered in under 500 milliseconds. No human intervention." |
| 1:40 | 3-way | "Now a 3-way cycle — three processes, each waiting on the next. Same result: detected, victim selected by priority, recovered automatically." |
| 2:10 | Checkpoint | "The checkpoint manager saved the victim's state — PID, resources, command — so an admin could restart it if needed." |
| 2:30 | Security | "Switching to the security subsystem. We have 14 Python tests covering the eBPF pipeline, behavioral fingerprinting, and anomaly detection. All 14 pass." |
| 3:00 | ADFA-LD | "The anomaly detector trains on the ADFA-LD dataset — 833 normal traces, 746 attack traces. Combined Isolation Forest plus Random Forest achieves 100% recall, 100% precision, F1 of 1.0." |
| 3:30 | Cleanup | "Module unloaded cleanly. Total kernel overhead during monitoring was 0.0125% CPU. The full paper, code, and benchmarks are open-source on GitHub." |
| 3:50 | Outro | "That's Eonix OS — autonomous self-healing and proactive security in the Linux kernel. The arXiv paper and all code are linked in the description. Thanks for watching." |

### Post-Recording

1. **Trim** the video in OBS or any editor (remove dead air)
2. **Export** as MP4, aim for under 100 MB
3. **Upload to YouTube**:
   - Title: `Eonix OS — Autonomous Deadlock Recovery & eBPF Security (Live Demo)`
   - Description:

```
Eonix OS: A self-healing, AI-native operating system with autonomous deadlock
recovery (279ms average) and eBPF-based intrusion detection (100% recall on
ADFA-LD).

Built by a 2nd-year B.Tech student as a 7-month research project.

GitHub: https://github.com/shahnoor-exe/eonix-os
arXiv: https://arxiv.org/abs/2603.XXXXX (update with real ID)

Key results:
- 100% detection across 130 deadlock scenarios
- Zero false positives over 1,000 benign cycles
- 279ms mean recovery — 107x faster than manual reboot
- 0.0125% CPU overhead
- 100% recall on ADFA-LD (833 normal + 746 attack traces)
- eBPF monitoring of 7 syscall tracepoints

Tags: operating systems, kernel module, deadlock detection, eBPF, Linux,
cybersecurity, anomaly detection, machine learning
```

4. Set visibility to **Public**
5. Copy the YouTube URL
6. Update `README.md` — replace the placeholder:

```
Find:    https://youtube.com/PLACEHOLDER
Replace: https://youtube.com/watch?v=YOUR_VIDEO_ID
```

---

## Part E: Saturday March 14 — Master Checklist

Execute in this order:

### Morning Block (~45 min) — arXiv Submission

```
□  1. Open Overleaf → upload docs/arxiv-paper.tex                     5 min
□  2. Click Recompile → verify PDF renders correctly                  5 min
       ✓ 9 figures visible?
       ✓ 6 tables visible?
       ✓ No "??" cross-references?
       ✓ ~15 pages?
□  3. Download PDF → save to docs/arxiv-paper.pdf (for records)       1 min
□  4. Go to https://arxiv.org/submit → Start New Submission           2 min
□  5. License: "arXiv perpetual non-exclusive" → Continue             1 min
□  6. Upload arxiv-paper.tex → wait for "Processing completed"        5 min
       ⚠ If compile errors: read log, fix .tex, re-upload
□  7. Fill metadata (see Part B, Step 4, table above)                 5 min
□  8. Preview PDF → verify all content                                5 min
□  9. Final confirmation → Submit                                     1 min
□ 10. Check email for confirmation                                    1 min
```

### Afternoon Block (~45 min) — Demo Video

```
□ 11. Open OBS Studio → configure per Part D setup                   10 min
□ 12. Open WSL2 terminal → cd to project                              1 min
□ 13. Start OBS recording                                             1 min
□ 14. Run: bash scripts/demo_video_commands.sh                       10 min
       (narrate per the timing guide above)
□ 15. Stop recording                                                  1 min
□ 16. Trim video → export as MP4                                      5 min
□ 17. Upload to YouTube with title + description from Part D         10 min
□ 18. Copy YouTube URL → update README.md placeholder                 2 min
```

### Evening (~5 min) — Final Commit

```
□ 19. git add -A                                                      1 min
□ 20. git commit -m "docs: Saturday submission (arXiv + video)"       1 min
□ 21. git push origin master                                          1 min
```

### After arXiv ID Arrives (Monday/Tuesday)

```
□ 22. python scripts/update_arxiv_id.py 2603.XXXXX                   1 min
□ 23. git add -A && git commit -m "docs: arXiv ID" && git push       1 min
□ 24. Update YouTube description with real arXiv link                 2 min
```

---

## Appendix: Troubleshooting

### "arXiv says I need endorsement"

1. Go to your arXiv account → "Request endorsement"
2. Select category: **cs.OS**
3. arXiv shows a link you can send to an endorser
4. Ask any professor who has published on arXiv in cs.OS, cs.DC, or cs.CR
5. They click the link → you're endorsed instantly
6. **Fallback**: Submit under **cs.DC** instead (broader category, easier endorsement)

### "arXiv compilation failed"

1. Read the full error log on the arXiv processing page
2. Most common fixes:
   - Package version mismatch: change `\pgfplotsset{compat=1.18}` → `\pgfplotsset{compat=1.17}`
   - Missing font: we use `lmodern` which is always available
   - TikZ library issue: all our libraries are in standard TeX Live
3. Test on **Overleaf** first — Overleaf uses a similar TeX Live version to arXiv
4. If a specific TikZ figure fails: comment it out with `%` and resubmit, then fix later as v2

### "arXiv says my paper is on hold / under moderation"

- **Normal for new authors** — cs.OS moderators review papers from first-time submitters
- Typically resolves in 1–3 business days
- Do NOT resubmit — just wait
- If held > 5 days, email moderation@arxiv.org

### "I want to fix something after submission"

- Go to https://arxiv.org/user → "My submissions"
- Click "Replace" next to your paper
- Upload the corrected .tex
- The paper becomes version 2 (v2) — the original v1 remains accessible
- You can replace as many times as you want

### Local PDF Generation (for your own records)

**MiKTeX on Windows:**
```powershell
# Install MiKTeX from https://miktex.org/download
cd C:\Users\laska\Projects\eonix-os\docs
pdflatex arxiv-paper.tex
pdflatex arxiv-paper.tex   # run twice for cross-references
```

**WSL2 Ubuntu:**
```bash
sudo apt-get install -y texlive-latex-recommended texlive-latex-extra \
  texlive-fonts-recommended texlive-pictures
cd /mnt/c/Users/laska/Projects/eonix-os/docs
pdflatex arxiv-paper.tex
pdflatex arxiv-paper.tex
```
