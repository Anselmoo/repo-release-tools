"""UI helpers for terminal rendering in repo-release-tools."""

from repo_release_tools.ui.color import (
    THEMES,
    Style,
    apply,
    apply_style,
    detect_color_level,
    error,
    get_theme,
    info,
    set_theme,
    subtle,
    success,
    supports_color,
    warning,
)
from repo_release_tools.ui.color import (
    chrome as chrome,
)
from repo_release_tools.ui.color import (
    heading as heading,
)
from repo_release_tools.ui.color import success as fmt_version
from repo_release_tools.ui.context import OutputContext
from repo_release_tools.ui.font import Emphasis, bold, emphasize, italic, underline
from repo_release_tools.ui.glyphs import GLYPHS, IS_LEGACY_TERMINAL
from repo_release_tools.ui.layout import (
    align,
    banner,
    box,
    hyperlink,
    panel,
    progress_bar,
    rule,
    section,
    section_line,
    sparkline,
    terminal_width,
    truncate,
)
from repo_release_tools.ui.messaging import (
    DryRunPrinter,
    render_action,
    render_dry_run,
    render_dry_run_complete,
    render_error_line,
    render_hint,
    render_info,
    render_ok,
    render_status,
    render_warning,
)
from repo_release_tools.ui.messaging import (
    error as cli_error,
)
from repo_release_tools.ui.progress import ProgressLine, spinner_lines
from repo_release_tools.ui.prompt import ask, confirm
from repo_release_tools.ui.syntax import (
    diff_highlight,
    fmt_cmd,
    highlight_terminal,
    json_highlight,
    pretty_print,
)


def fmt_path(path: str) -> str:
    """Return *path* with an underline style applied (degrades on NO_COLOR)."""
    return underline(path)


__all__ = [
    "GLYPHS",
    "IS_LEGACY_TERMINAL",
    "Style",
    "THEMES",
    "Emphasis",
    "DryRunPrinter",
    "OutputContext",
    "ProgressLine",
    "align",
    "apply",
    "apply_style",
    "ask",
    "banner",
    "bold",
    "box",
    "cli_error",
    "confirm",
    "detect_color_level",
    "diff_highlight",
    "error",
    "emphasize",
    "fmt_cmd",
    "fmt_path",
    "fmt_version",
    "get_theme",
    "highlight_terminal",
    "hyperlink",
    "info",
    "italic",
    "json_highlight",
    "panel",
    "pretty_print",
    "render_action",
    "render_dry_run",
    "render_dry_run_complete",
    "render_error_line",
    "render_hint",
    "render_info",
    "render_ok",
    "render_status",
    "render_warning",
    "rule",
    "section",
    "section_line",
    "set_theme",
    "progress_bar",
    "sparkline",
    "spinner_lines",
    "subtle",
    "success",
    "supports_color",
    "terminal_width",
    "truncate",
    "underline",
    "warning",
]
