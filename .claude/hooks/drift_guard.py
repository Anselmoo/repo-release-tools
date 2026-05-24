#!/usr/bin/env python3
"""Claude Stop hook: block completion when agent-facing surfaces drift."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _block(reason: str) -> int:
    payload = {"decision": "block", "reason": reason}
    print(json.dumps(payload, ensure_ascii=False))
    return 2


def _tail(text: str, *, lines: int = 12) -> str:
    entries = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(entries[-lines:]) if entries else ""


def main() -> int:
    """Run the canonical drift check and block if lockfile surfaces are stale."""
    _ = sys.stdin.read()

    repo_root = Path.cwd()
    command = os.getenv("RRT_DRIFT_CHECK_COMMAND", "uv run rrt drift check")

    try:
        result = subprocess.run(  # noqa: S603
            shlex.split(command),
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # pragma: no cover - defensive for hook runtime
        return _block(f"Drift guard could not execute '{command}': {exc}")

    if result.returncode == 0:
        return 0

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    details = _tail(combined)
    guidance = "Run `uv run rrt drift generate` to refresh `.rrt/drift.lock.toml`, then re-check."
    reason = f"Drift guard failed (`{command}`, exit {result.returncode}). {guidance}"
    if details:
        reason = f"{reason}\n\nLast output:\n{details}"

    return _block(reason)


if __name__ == "__main__":
    raise SystemExit(main())
