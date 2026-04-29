"""UI helpers for terminal rendering in repo-release-tools."""

from repo_release_tools.ui.color import (
    Style,
    THEMES,
    apply,
    apply_style,
    chrome as chrome,
    detect_color_level,
    error,
    get_theme,
    heading as heading,
    info,
    set_theme,
    subtle,
    success,
    supports_color,
    warning,
)
from repo_release_tools.ui.context import OutputContext
from repo_release_tools.ui.font import Emphasis, bold, emphasize, italic, underline
from repo_release_tools.ui.layout import (
    align,
    box,
    progress_bar,
    rule,
    section_line,
    sparkline,
    terminal_width,
    truncate,
)
from repo_release_tools.ui.syntax import highlight_terminal
from repo_release_tools.ui.prompt import ask, confirm
from repo_release_tools.ui.messaging import DryRunPrinter
from repo_release_tools.ui.progress import ProgressLine, spinner_lines

__all__ = [
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
    "bold",
    "box",
    "confirm",
    "detect_color_level",
    "error",
    "emphasize",
    "get_theme",
    "highlight_terminal",
    "info",
    "italic",
    "rule",
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
