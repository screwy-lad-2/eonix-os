## v0.7.0 — Month 7: Eonix Desktop
**Released:** May 2026

### What's New

#### 🖥️ Eonix Desktop (GTK4)
- Full graphical desktop session (replaces standard WM)
- TopBar: goal name, clock, RAM/CPU live
- GoalPanel: active goal + progress + memory browser
- Wallpaper: animated particle grid (Cairo, 30fps)
- AppLauncher: search, launch, create goal from input

#### 🪟 Window Manager
- Snap zones: left/right/fullscreen/corners
- Super+arrow keyboard shortcuts
- Goal-relevance scoring per open window
- EonixTaskbar: window list with goal indicators
- Super+Tab: cycle focus by goal relevance

#### 💾 Session Manager
- Save/restore desktop sessions per goal
- Auto-save every 5 minutes
- [Open Workspace] restores apps for active goal
- Session files: ~/.eonix/sessions/{goal_id}.json

#### 🧠 Memory Browser Widget
- Category filter tabs (7 categories)
- Add/delete memories from desktop
- Semantic search via ContextAgent
- Embedded in GoalPanel + standalone window

#### ⚙️ Settings App
- GTK4 settings panel (5 sections)
- Agent port config, appearance, model info
- Reads/writes ~/.eonix/config.json

### Test Coverage
| New Suite         | Tests |
|-------------------|-------|
| desktop.py        | 9     |
| window_manager    | 8     |
| session_manager   | 4     |
| memory_widget     | 6     |
| settings          | 3     |
| Integration M7    | 8     |
| **New total**     | **38**|
| **Cumulative**    | **146**|

### CI: 26/26 jobs green

---
*Next: v0.8.0 — Month 8: Bootable ISO*
