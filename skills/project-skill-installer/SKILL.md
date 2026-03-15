---
name: project-skill-installer
description: Install or update additional skills into this project's local `skills/` directory so the agent can evolve over time. Use when the user asks to add a new skill from GitHub, update an installed skill, or keep all skills scoped to the current project instead of global Codex skills.
---

# Project Skill Installer

## Overview

Install skills only into the current project's `skills/` directory. Do not write into global `~/.codex/skills` unless the user explicitly asks for a global install.

Use the `install_project_skill` tool for the actual installation. After installing, inspect the local `skills/` directory and tell the user which skill was added or updated.

## Workflow

1. Confirm the GitHub source in `owner/repo` form and the repo-relative skill path.
2. If the source path is unclear, ask for the exact repo and skill path instead of guessing.
3. Call `install_project_skill` with:
   - `repo`
   - `skill_path`
   - `ref` when the branch or tag matters
   - `replace_existing=true` only when the user asked to update or overwrite
4. After installation, use `list_directory(path="skills")` to verify the local project skills.
5. Tell the user:
   - which skill was installed
   - where it was installed
   - whether an existing skill was replaced
   - that a new conversation or service restart may be needed for the agent to fully pick it up

## Constraints

- Keep installations local to the current project.
- Prefer one skill at a time unless the user clearly asks for a batch install.
- Do not claim a remote skill exists unless the repo path is known.
- If installation fails, report the exact error and the repo/path that failed.
