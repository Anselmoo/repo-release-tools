from __future__ import annotations

import pytest

from repo_release_tools.ui import font


def test_bold_uses_color_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(font, "apply", lambda text, style, *, stream=None: f"BOLD:{text}")

    assert font.bold("hello") == "BOLD:hello"


def test_italic_and_underline_use_color_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        font,
        "apply",
        lambda text, style, *, stream=None: f"STYLE:{text}:{style.italic}:{style.underline}",
    )

    assert font.italic("hello") == "STYLE:hello:True:False"
    assert font.underline("hello") == "STYLE:hello:False:True"
