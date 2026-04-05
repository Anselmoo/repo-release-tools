from repo_release_tools.glyphs import GLYPHS
from repo_release_tools.glyphs import Glyph


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
