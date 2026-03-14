## v0.6.0-alpha - Week 19: EonixShell Online
**Released:** April 2026

### What's New
- EonixShell: goal-aware 2-line prompt (live every 5s)
- Built-in eon commands: status, goal, remember,
  recall, sync, hub, history, help
- Bash passthrough with ContextAgent logging
- Shell history persisted to ~/.eonix/shell_history.txt
- Tab-complete: eon subcommands + goal names + paths
- POST /context/event endpoint for external ingestion
- Hub timeline now parses shell events correctly

### Tests: 88+ passing | CI: 21/21 green
