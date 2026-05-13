from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from repo_release_tools.integrations import agent_assets, skill_assets


def test_load_agent_raises_when_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    with pytest.raises(FileNotFoundError):
        agent_assets._load_agent("rrt-user-bootstrap")


def test_load_skill_raises_when_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    with pytest.raises(FileNotFoundError):
        cast(Any, skill_assets)._load_skill("rrt-user-bootstrap")
