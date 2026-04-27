#!/usr/bin/env python3
"""rrt-ux-design agent hook.

Reads the UserPromptSubmit JSON from stdin.  When the user prompt touches
terminal output, styling, or ui/ module files, injects a system message that
reminds the agent of the rrt UX contract so it never writes raw ANSI escapes
or bypasses the ui/ layer.

Exit codes:
  0  — continue (with or without injected context)
"""

from __future__ import annotations

import json
import re
import sys

_UI_KEYWORDS = re.compile(
    r"\b("
    r"color|colour|ansi|escape|styling|style|no.color|output|print|terminal"
    r"|tty|bold|italic|underline|dim|progress|sparkline|prompt|highlight"
    r"|syntax|rule|box|align|truncate|section.line|messaging|error|warning"
    r"|info|success|subtle|apply_style|OutputContext"
    r")\b"
    r"|ui/|_ui/|ui\\.py|color\\.py|layout\\.py|font\\.py|syntax\\.py"
    r"|output\\.py|glyphs\\.py",
    re.IGNORECASE,
)

_SYSTEM_MESSAGE = """\
[rrt-ux-contract] Terminal output reminder:
- All terminal output MUST go through `repo_release_tools.ui` — never write raw \\x1b[...] escapes.
- Use `error()`, `warning()`, `info()`, `success()`, `subtle()` for semantic messaging.
- Use `bold()`, `italic()`, `underline()` for inline emphasis.
- Use `rule()`, `section_line()`, `box()`, `align()`, `truncate()` for layout.
- Use `progress_bar()` / `sparkline()` for progress and data sparklines.
- Respect `NO_COLOR` / `RRT_COLOR` / non-TTY: functions degrade automatically — never gate on color manually.
- Every new ui/ function needs a test class in tests/test_user_experience_simulator.py
  AND a line in that file's "Affected entrypoints" docstring section.
- Run `uv run pytest tests/test_user_experience_simulator.py -v` after changes.
"""


def main() -> None:
    payload = json.loads(sys.stdin.read())
    prompt: str = payload.get("prompt", "") or ""

    if _UI_KEYWORDS.search(prompt):
        print(json.dumps({"systemMessage": _SYSTEM_MESSAGE}))
    # Exit 0 always — this hook never blocks.


if __name__ == "__main__":
    main()
