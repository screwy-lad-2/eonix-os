# Eonix OS Project Rules

## GitHub Account Usage
As per the user's explicit preference established in Week 46:

1. **Main Development Account (`shahnoor-exe`)**:
   - Used for all primary code modifications, commits, and pushes.
   - Remote name: `origin`
   - URL: `https://github.com/shahnoor-exe/eonix-os.git`

2. **Actions & Build Trigger Account (`screwy-lad-2`)**:
   - Strictly used ONLY for triggering ISO builds and CI workflows via GitHub Actions.
   - Remote name: `build-server`
   - URL: `https://github.com/screwy-lad-2/eonix-os.git`

## Automated Workflows
- When code is modified, it MUST be committed and pushed to `origin` (`shahnoor-exe`).
- To trigger a build, code MUST be synced to `build-server` (`screwy-lad-2`), and the workflow triggered on that repository via `gh workflow run`.
- Use `gh auth switch -u <account>` to switch contexts securely.
