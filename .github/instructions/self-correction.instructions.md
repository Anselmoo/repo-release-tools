---
applyTo: "**"
description: "Keep workspace instructions current — update them when a session reveals a gap"
---

# Instruction self-correction

After completing any task, check whether the session revealed a gap in the
existing workspace instructions. If yes, update instructions before closing.

## Rules

- After completing a task that required a post-fix (correcting previously written
  code or tests), add an imperative rule to the relevant instruction file that
  would have prevented the mistake.
- When a new pattern, workaround, or convention is discovered mid-session, capture
  it in `.github/instructions/<domain>.instructions.md` before the session ends.
- When documenting badge completeness or icon inventories, describe the full
  label taxonomy in play (for example platform, registry, and language) rather
  than saying "platform" if the table spans more than that one category.
- When `rrt tree --check --strict` reports drift, first compare against a clean
  clone or clean checkout and remove any local-only empty directories (for
  example under `src/`) before regenerating `.rrt/tree.lock.toml`.
- If an empty directory is intentional and should survive clean clones, warn
  for it in `rrt tree` and suggest a `.gitkeep` placeholder instead of relying
  on the directory itself being tracked by Git.
- When editing an instruction file, check for contradictions with other rules in
  the same file and with `.github/copilot-instructions.md` before saving.
- Prefer adding to an existing scoped instruction file over adding to
  `copilot-instructions.md` — the scoped file loads only when relevant.

## Do not

- Leave a repeated post-fix pattern undocumented after fixing it.
- Add time-sensitive phrasing to any instruction file ("until date X", "currently
  in beta", "as of version Y").
- Duplicate a rule that already exists in `copilot-instructions.md` or another
  instructions file in scope.
