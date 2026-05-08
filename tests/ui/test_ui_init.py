from __future__ import annotations

import pytest

import repo_release_tools.ui as ui


def test_fmt_path_applies_public_underline_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "underline", lambda path: f"underlined:{path}")

    assert ui.fmt_path("README.md") == "underlined:README.md"


def test_ui_public_surface_exports_expected_names() -> None:
    expected = {
        "DryRunPrinter",
        "ProgressLine",
        "banner",
        "cli_error",
        "diff_highlight",
        "fmt_cmd",
        "fmt_path",
        "fmt_version",
        "highlight_terminal",
        "hyperlink",
        "json_highlight",
        "panel",
        "pretty_print",
        "render_action",
        "render_warning",
        "spinner_lines",
    }

    assert expected.issubset(set(ui.__all__))
    for name in expected:
        assert getattr(ui, name) is not None
