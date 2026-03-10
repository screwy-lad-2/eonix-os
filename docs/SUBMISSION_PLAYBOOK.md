# Eonix OS — Weekend Submission Playbook

Complete step-by-step guide for Saturday March 14, 2026.
Estimated total time: **2–3 hours** (video ~1h, arXiv ~30min, updates ~10min).

---

## S1: Demo Video (OBS, 4 minutes)

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
   - Description: (paste the block below)

```
Eonix OS: A self-healing, AI-native operating system with autonomous deadlock
recovery (279ms average) and eBPF-based intrusion detection (100% recall on
ADFA-LD).

Built by a 2nd-year B.Tech student as a 7-month research project.

🔗 GitHub: https://github.com/shahnoor-exe/eonix-os
📄 arXiv: https://arxiv.org/abs/2603.XXXXX (update with real ID)

Key results:
• 100% detection across 130 deadlock scenarios
• Zero false positives over 1,000 benign cycles
• 279ms mean recovery — 107× faster than manual reboot
• 0.0125% CPU overhead
• 100% recall on ADFA-LD (833 normal + 746 attack traces)
• eBPF monitoring of 7 syscall tracepoints

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

## S2: arXiv Submission

### Prerequisites

- arXiv account at https://arxiv.org (create one if needed — uses ORCID or institutional email)
- PDF of the paper (generated from the .tex file)

### Step 1: Generate PDF from .tex (if not done)

**Option A — Overleaf (easiest, recommended):**

1. Go to https://www.overleaf.com
2. New Project → Upload Project → upload `docs/arxiv-paper.tex`
3. Click **Recompile**
4. Download the PDF

**Option B — Local MiKTeX:**

```powershell
# Install MiKTeX from https://miktex.org/download
# Then:
cd C:\Users\laska\Projects\eonix-os\docs
pdflatex arxiv-paper.tex
pdflatex arxiv-paper.tex   # run twice for references
```

**Option C — WSL2:**

```bash
sudo apt-get install -y texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended
cd /mnt/c/Users/laska/Projects/eonix-os/docs
pdflatex arxiv-paper.tex
pdflatex arxiv-paper.tex
```

5. Copy the generated PDF to `docs/arxiv-paper.pdf` (overwrite the old one)

### Step 2: Submit to arXiv

1. Go to https://arxiv.org/submit
2. Log in (or create account)
3. **New submission**
4. Fill in:

| Field | Value |
|-------|-------|
| Title | Eonix OS: A Self-Healing, Proactive Security Kernel with Autonomous Deadlock Recovery and eBPF Threat Detection |
| Authors | Shahnoor Ahmed Butt |
| Abstract | *(copy the full abstract from docs/arxiv-paper.md — everything between "Abstract" and "Keywords")* |
| Primary category | **cs.OS** (Operating Systems) |
| Cross-list | **cs.DC** (Distributed Computing), **cs.CR** (Cryptography and Security) |
| Comments | 12 pages, 5 tables, open-source at https://github.com/shahnoor-exe/eonix-os |
| License | arXiv.org perpetual non-exclusive license (default) |

5. **Upload source**: Upload the .tex file (or a .zip containing arxiv-paper.tex)
   - arXiv prefers .tex source over PDF
   - If uploading .tex only, arXiv will compile it server-side
6. **Preview** — verify the PDF looks correct
7. **Submit**

### Step 3: Wait for arXiv ID

- arXiv typically assigns an ID within **1–2 business days**
- You'll get an email with the ID (format: `2603.XXXXX`)
- The paper appears on arXiv after the next announcement cycle

---

## S3 + S4: Update arXiv ID (After Receiving It)

Once you receive your arXiv ID (e.g., `2603.12345`), run:

```powershell
cd C:\Users\laska\Projects\eonix-os
python scripts/update_arxiv_id.py 2603.12345
```

This automatically replaces `2603.XXXXX` in:
- `README.md` (badge + link + BibTeX citation)
- `docs/arxiv-paper.md`
- `docs/arxiv-paper.tex`

Then commit and push:

```powershell
git add -A
git commit -m "docs: update arXiv ID to 2603.12345"
git push origin master
```

Also update the YouTube video description with the real arXiv link.

---

## Saturday Checklist

```
□  1. Generate PDF from .tex (Overleaf or local LaTeX)    ~15 min
□  2. Copy PDF to docs/arxiv-paper.pdf                    ~1 min
□  3. Record demo video (OBS + WSL2 script)               ~30 min
□  4. Trim and upload to YouTube                          ~15 min
□  5. Update README with YouTube URL                      ~2 min
□  6. Submit .tex to arXiv                                ~20 min
□  7. Commit + push all changes                           ~2 min
□  8. [After arXiv ID arrives] Run update_arxiv_id.py     ~5 min
```

Total: ~90 minutes of focused work.
