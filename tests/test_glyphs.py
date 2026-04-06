from repo_release_tools.glyphs import GLYPHS
from repo_release_tools.glyphs import Glyph
from repo_release_tools.glyphs import display_width


def test_glyph_multiplies_like_a_string() -> None:
    glyph = Glyph("-", "dash")

    assert glyph * 3 == "---"
    assert 2 * glyph == "--"


def test_git_status_line_stays_compact() -> None:
    line = GLYPHS.git.status_line(
        "feat/add-parser",
        ahead=2,
        behind=1,
        modified=3,
        untracked=1,
    )

    assert "feat/add-parser" in line
    assert "2" in line
    assert "1" in line


def test_diff_line_accepts_line_numbers() -> None:
    rendered = GLYPHS.diff.line("added", "return result", lineno=12)

    assert "12" in rendered
    assert "return result" in rendered


def test_box_table_renders_consistent_widths() -> None:
    rendered = GLYPHS.box.table(
        ["Key", "Value"],
        [["branch", "feat/v0-15-0"], ["title", "feat: v0.15.0"]],
    )

    widths = {display_width(line) for line in rendered.splitlines()}
    assert len(widths) == 1
    assert "feat/v0-15-0" in rendered


def test_tree_render_supports_nested_entries() -> None:
    rendered = GLYPHS.tree.render(
        [
            ("src", True, [("repo_release_tools", True, [("glyphs.py", False, None)])]),
            ("README.md", False, None),
        ]
    )

    assert "src/" in rendered
    assert "repo_release_tools/" in rendered
    assert "glyphs.py" in rendered
    assert "README.md" in rendered


def test_progress_bar_and_spinner_are_available() -> None:
    bar = GLYPHS.progress.render_bar(0.5, width=4)
    spinner = GLYPHS.progress.spinner("ascii")

    assert "50%" in bar
    assert len(next(spinner)) >= 1
