"""Compatibility wrapper for the legacy top-level `repo_release_tools.hooks` module."""

from __future__ import annotations

from repo_release_tools.workflow import hooks as _workflow_hooks
from repo_release_tools.workflow.hooks import main

for _name in dir(_workflow_hooks):
    if _name.startswith("_"):
        continue
    globals()[_name] = getattr(_workflow_hooks, _name)


if __name__ == "__main__":
    raise SystemExit(main())
