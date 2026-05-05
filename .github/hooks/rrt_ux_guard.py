#!/usr/bin/env python3
"""VS Code Copilot Chat hook — UserPromptSubmit.

Delegates to the canonical implementation in .claude/hooks/rrt_ux_guard.py
so that both the Claude Code session hooks and VS Code Copilot Chat hooks
share the same UX-guard logic without duplication.
"""

from __future__ import annotations

import runpy
from pathlib import Path

_target = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "rrt_ux_guard.py"
runpy.run_path(str(_target), run_name="__main__")
