#!/usr/bin/env python3
"""rrt-ux-design write guard — PreToolUse hook.

Intercepts every Write/Edit/MultiEdit tool call.  When the target file is
inside the rrt source or test tree, scans the *new content* for hard
violations and blocks the write if any are found.

This is the enforcement layer.  UserPromptSubmit only reminds; this hook
actually stops bad code from landing on disk.

Exit codes:
  0  — allow the write
  2  — block the write; stderr is shown to the user
"""

from __future__ import annotations

import json
import re
import sys

# ---------------------------------------------------------------------------
# Hard violations — patterns that must never be written to rrt source files
# ---------------------------------------------------------------------------

# (pattern, human description)
_HARD_BLOCKS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\\x1b\[|\\033\["),
        "raw ANSI escape sequence — use repo_release_tools.ui functions instead",
    ),
    (
        re.compile(r'\bprint\s*\(\s*f?"[^"]*\\x1b'),
        "print() call embedding a raw ANSI escape",
    ),
]

# Patterns that trigger a WARN but still allow the write (injected as context)
_SOFT_WARNS: list[tuple[re.Pattern[str], str]] = []

# Only enforce on files inside these path prefixes
_SCOPE = re.compile(
    r"src/repo_release_tools/"
    r"|tests/"
    r"|src\\repo_release_tools\\"  # Windows paths
    r"|tests\\"
)

# Test files may assert on raw ANSI sequences — hard blocks are demoted to
# warnings so legitimate terminal-output assertions are not rejected.
_TEST_PATH = re.compile(r"tests[\\/]")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_in_scope(path: str) -> bool:
    return bool(_SCOPE.search(path.replace("\\", "/")))


def _extract_new_content(payload: dict) -> tuple[str, str]:
    """Return (file_path, new_content) from a Write/Edit/MultiEdit payload.

    Returns ("", "") when the tool type is not recognised or has no content.
    """
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {})

    if tool == "Write":
        return inp.get("file_path", ""), inp.get("content", "")

    if tool in ("Edit", "str_replace_based_edit"):
        # Only the new_string is being written; old_string is being removed
        return inp.get("file_path", "") or inp.get("path", ""), inp.get("new_string", "")

    if tool == "MultiEdit":
        path = inp.get("file_path", "")
        # Concatenate all new_string values for scanning
        edits = inp.get("edits", [])
        content = "\n".join(e.get("new_string", "") for e in edits)
        return path, content

    return "", ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    payload = json.loads(sys.stdin.read())
    path, content = _extract_new_content(payload)

    if not path or not content or not _is_in_scope(path):
        # Not our concern — allow silently
        sys.exit(0)

    # --- Hard blocks ---
    is_test = bool(_TEST_PATH.search(path.replace("\\", "/")))
    hard_hits: list[str] = []
    for pattern, desc in _HARD_BLOCKS:
        for match in pattern.finditer(content):
            # Find the line number within the new content
            line_no = content[: match.start()].count("\n") + 1
            hard_hits.append(f"  line {line_no}: {desc}\n  > {match.group()[:100]}")

    if hard_hits and not is_test:
        msg = (
            "[rrt-ux-contract] BLOCKED: hard violation(s) in new content for "
            f"{path}:\n\n" + "\n\n".join(hard_hits) + "\n\n"
            "Fix: replace raw escapes with the appropriate repo_release_tools.ui function.\n"
            "See the rrt-ux-design skill for the full migration map."
        )
        print(msg, file=sys.stderr)
        sys.exit(2)

    if hard_hits and is_test:
        # Demote to a soft warning — test assertions on ANSI sequences are valid.
        soft_hits_from_hard = [
            f"  {h.splitlines()[0].strip()} [test assertion — allowed]" for h in hard_hits
        ]

    # --- Soft warns — allow but inject context ---
    soft_hits: list[str] = []
    for pattern, desc in _SOFT_WARNS:
        for match in pattern.finditer(content):
            line_no = content[: match.start()].count("\n") + 1
            soft_hits.append(f"  line {line_no}: {desc}")

    if is_test and hard_hits:
        soft_hits = soft_hits_from_hard + soft_hits

    if soft_hits:
        warn_text = (
            f"[rrt-ux-contract] WARNING: {path} uses deprecated output.py patterns:\n"
            + "\n".join(soft_hits)
            + "\nMigrate these to repo_release_tools.ui before the PR is merged."
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": warn_text,
                    }
                }
            )
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
