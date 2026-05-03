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
