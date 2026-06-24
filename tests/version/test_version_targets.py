"""Unit tests for the python_version and go_version target kinds."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
from repo_release_tools.version.targets import (
    _detect_json_indent,
    check_autodetected_version_consistency,
    read_current_version,
    read_group_current_version,
    read_group_version_strings,
    read_package_json_version,
    read_toml_field,
    read_version_string,
    replace_all_versions_atomic,
    replace_kind_pattern_version,
    replace_package_json_version,
    replace_pattern_version,
    replace_version_in_file,
)

# ---------------------------------------------------------------------------
# python_version – read
# ---------------------------------------------------------------------------


def test_read_python_version_double_quotes(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    assert read_version_string(target) == "1.2.3"


def test_read_python_version_single_quotes(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text("__version__ = '4.5.6'\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    assert read_version_string(target) == "4.5.6"


def test_read_python_version_with_spaces(tmp_path: Path) -> None:
    f = tmp_path / "__version__.py"
    f.write_text('__version__  =  "0.0.1"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    assert read_version_string(target) == "0.0.1"


def test_read_python_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text("# no version here\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    with pytest.raises(RuntimeError, match="Could not find __version__"):
        read_version_string(target)


# ---------------------------------------------------------------------------
# python_version – write
# ---------------------------------------------------------------------------


def test_replace_python_version_double_quotes(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text('"""Package."""\n\n__version__ = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    replace_version_in_file(target, "2.0.0", dry_run=False)
    assert '__version__ = "2.0.0"' in f.read_text(encoding="utf-8")


def test_replace_python_version_single_quotes(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text("__version__ = '0.1.0'\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    replace_version_in_file(target, "0.2.0", dry_run=False)
    assert "__version__ = '0.2.0'" in f.read_text(encoding="utf-8")


def test_replace_python_version_dry_run_no_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    f = tmp_path / "__init__.py"
    original = '__version__ = "1.0.0"\n'
    f.write_text(original, encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    replace_version_in_file(target, "1.1.0", dry_run=True)
    assert f.read_text(encoding="utf-8") == original
    assert "Would update" in capsys.readouterr().out


def test_replace_python_version_same_version_raises(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    with pytest.raises(RuntimeError):
        replace_version_in_file(target, "1.0.0", dry_run=False)


def test_read_python_version_indented(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text('    __version__ = "3.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    assert read_version_string(target) == "3.0.0"


def test_replace_python_version_indented(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    f.write_text('    __version__ = "3.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    replace_version_in_file(target, "3.1.0", dry_run=False)
    assert '    __version__ = "3.1.0"' in f.read_text(encoding="utf-8")


def test_python_version_mismatched_quotes_not_matched(tmp_path: Path) -> None:
    """A pattern with mismatched opening/closing quotes should not be matched."""
    f = tmp_path / "__init__.py"
    # Double-quote open, single-quote close – not a valid Python string literal
    f.write_text("__version__ = \"1.0.0'\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    with pytest.raises(RuntimeError, match="Could not find __version__"):
        read_version_string(target)


# ---------------------------------------------------------------------------
# go_version – leading whitespace and const (...) block
# ---------------------------------------------------------------------------


def test_read_go_version_leading_whitespace(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\n\tconst Version = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    assert read_version_string(target) == "1.2.3"


def test_replace_go_version_leading_whitespace(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\n\tconst Version = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    replace_version_in_file(target, "1.3.0", dry_run=False)
    assert 'Version = "1.3.0"' in f.read_text(encoding="utf-8")


def test_read_go_version_const_block(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text(
        'package version\n\nconst (\n\tVersion = "2.0.0"\n\tOther = "x"\n)\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="go_version")
    assert read_version_string(target) == "2.0.0"


def test_replace_go_version_const_block(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    original = 'package version\n\nconst (\n\tVersion = "2.0.0"\n\tOther = "x"\n)\n'
    f.write_text(original, encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    replace_version_in_file(target, "2.1.0", dry_run=False)
    assert 'Version = "2.1.0"' in f.read_text(encoding="utf-8")
    assert 'Other = "x"' in f.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# go_version – read
# ---------------------------------------------------------------------------


def test_read_go_version_const(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\nconst Version = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    assert read_version_string(target) == "1.0.0"


def test_read_go_version_var(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\nvar Version = "2.3.4"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    assert read_version_string(target) == "2.3.4"


def test_read_go_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text("package version\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    with pytest.raises(RuntimeError, match="Could not find Version"):
        read_version_string(target)


# ---------------------------------------------------------------------------
# go_version – write
# ---------------------------------------------------------------------------


def test_replace_go_version_const(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\nconst Version = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    replace_version_in_file(target, "1.1.0", dry_run=False)
    assert 'const Version = "1.1.0"' in f.read_text(encoding="utf-8")


def test_replace_go_version_var(tmp_path: Path) -> None:
    f = tmp_path / "version.go"
    f.write_text('package version\n\nvar Version = "0.9.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    replace_version_in_file(target, "1.0.0", dry_run=False)
    assert 'var Version = "1.0.0"' in f.read_text(encoding="utf-8")


def test_replace_go_version_dry_run_no_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    f = tmp_path / "version.go"
    original = 'package version\n\nconst Version = "1.0.0"\n'
    f.write_text(original, encoding="utf-8")
    target = VersionTarget(path=f, kind="go_version")
    replace_version_in_file(target, "2.0.0", dry_run=True)
    assert f.read_text(encoding="utf-8") == original
    assert "Would update" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# VersionTarget.validate() – new kinds accepted
# ---------------------------------------------------------------------------


def test_validate_python_version_kind() -> None:
    target = VersionTarget(path=Path("__init__.py"), kind="python_version")
    target.validate()  # must not raise


def test_validate_go_version_kind() -> None:
    target = VersionTarget(path=Path("version.go"), kind="go_version")
    target.validate()  # must not raise


def test_validate_unknown_kind_raises() -> None:
    target = VersionTarget(path=Path("file.py"), kind="ruby_version")
    with pytest.raises(ValueError, match="kind must be one of"):
        target.validate()


# ---------------------------------------------------------------------------
# replace_pin_in_file
# ---------------------------------------------------------------------------


def test_replace_pin_in_file_updates_version(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "action.md"
    f.write_text("- uses: Anselmoo/repo-release-tools@v0.1.7\n", encoding="utf-8")
    pin = PinTarget(
        path=f,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )

    replace_pin_in_file(pin, "1.0.0", dry_run=False)

    assert "v1.0.0" in f.read_text(encoding="utf-8")
    assert "v0.1.7" not in f.read_text(encoding="utf-8")


def test_replace_pin_in_file_dry_run_does_not_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "action.md"
    original = "- uses: Anselmoo/repo-release-tools@v0.1.7\n"
    f.write_text(original, encoding="utf-8")
    pin = PinTarget(
        path=f,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )

    replace_pin_in_file(pin, "1.0.0", dry_run=True)

    # File must be unchanged in dry-run mode
    assert f.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "Would update" in out


def test_replace_pin_in_file_already_current_skips(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "action.md"
    f.write_text("- uses: Anselmoo/repo-release-tools@v1.0.0\n", encoding="utf-8")
    pin = PinTarget(
        path=f,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )

    replace_pin_in_file(pin, "1.0.0", dry_run=False)

    out = capsys.readouterr().out
    assert "already" in out.lower() or "up to date" in out.lower() or "pin" in out.lower()


def test_replace_pin_in_file_no_match_warns(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "notes.md"
    f.write_text("# Just some notes\n", encoding="utf-8")
    pin = PinTarget(
        path=f,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )

    replace_pin_in_file(pin, "1.0.0", dry_run=False, pin_target_missing="warn")

    captured = capsys.readouterr()
    assert "did not match" in captured.out.lower() or "skipping" in captured.out.lower()


def test_replace_pin_in_file_replaces_all_occurrences(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """replace_pin_in_file updates every occurrence, not just the first."""
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "action.md"
    content = (
        "- uses: Anselmoo/repo-release-tools@v0.1.7\n"
        "# also: Anselmoo/repo-release-tools@v0.1.7\n"
        "- uses: Anselmoo/repo-release-tools@v0.1.7\n"
    )
    f.write_text(content, encoding="utf-8")
    pin = PinTarget(
        path=f,
        pattern=r"(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()",
    )

    replace_pin_in_file(pin, "2.0.0", dry_run=False)

    updated = f.read_text(encoding="utf-8")
    assert updated.count("v2.0.0") == 3
    assert "v0.1.7" not in updated


def test_read_current_version_helpers(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=pyproject, kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    cfg = RrtConfig(root=tmp_path, config_file=pyproject, version_groups=[group])

    assert str(read_current_version(cfg)) == "1.2.3"
    assert str(read_group_current_version(group)) == "1.2.3"
    assert read_group_version_strings(group) == [(target, "1.2.3")]


def test_check_autodetected_version_consistency_not_autodetected(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=pyproject, kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=tmp_path / "CHANGELOG.md",
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    cfg = RrtConfig(
        root=tmp_path,
        config_file=pyproject,
        version_groups=[group],
        autodetected=False,
    )
    assert check_autodetected_version_consistency(cfg) is None


def test_read_version_string_pep621_missing_raises(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")
    target = VersionTarget(path=pyproject, kind="pep621")
    with pytest.raises(RuntimeError, match=r"Could not find \[project\]\.version"):
        read_version_string(target)


def test_read_version_string_pattern_no_match_raises(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("version: 1.0.0\n", encoding="utf-8")
    target = VersionTarget(path=f, pattern=r"^(v)(\d+\.\d+\.\d+)()$")
    with pytest.raises(RuntimeError, match="Could not match configured pattern"):
        read_version_string(target)


def test_read_version_string_kind_pattern(tmp_path: Path) -> None:
    f = tmp_path / "pyproject.toml"
    f.write_text('dependencies = [\n    "ruff==0.15.18",\n]\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    assert read_version_string(target) == "0.15.18"


def test_read_version_string_kind_pattern_multiline_file(tmp_path: Path) -> None:
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\nname = "my-pkg"\n\n[project.dependencies]\nruff = "ruff==1.2.3"\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="pattern", pattern=r"ruff==(\d+\.\d+\.\d+)")
    assert read_version_string(target) == "1.2.3"


def test_read_version_string_kind_pattern_no_match_raises(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("no version here\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    with pytest.raises(RuntimeError, match="Could not match configured pattern"):
        read_version_string(target)


def test_replace_kind_pattern_version_basic() -> None:
    text = 'dependencies = [\n    "ruff==0.15.18",\n]\n'
    result = replace_kind_pattern_version(text, r'"ruff==(\d+\.\d+\.\d+)"', "1.0.0")
    assert result == 'dependencies = [\n    "ruff==1.0.0",\n]\n'


def test_replace_kind_pattern_version_first_occurrence_only() -> None:
    text = '"ruff==1.0.0"\n"ruff==1.0.0"\n'
    result = replace_kind_pattern_version(text, r'"ruff==(\d+\.\d+\.\d+)"', "2.0.0")
    # count=1: only the first occurrence is replaced
    assert result == '"ruff==2.0.0"\n"ruff==1.0.0"\n'


def test_replace_kind_pattern_version_preserves_surrounding_text() -> None:
    text = 'name = "my-pkg"\ndeps = ["ruff==0.5.0", "black==24.0"]\n'
    result = replace_kind_pattern_version(text, r"ruff==(\d+\.\d+\.\d+)", "0.6.0")
    assert result == 'name = "my-pkg"\ndeps = ["ruff==0.6.0", "black==24.0"]\n'


def test_replace_kind_pattern_version_no_match_raises() -> None:
    with pytest.raises(RuntimeError, match="Configured pattern did not match"):
        replace_kind_pattern_version("no version here", r'"ruff==(\d+\.\d+\.\d+)"', "1.0.0")


def test_replace_version_in_file_kind_pattern(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    f = tmp_path / "pyproject.toml"
    f.write_text('dependencies = ["ruff==0.15.18"]\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    replace_version_in_file(target, "1.0.0", dry_run=False)
    assert f.read_text(encoding="utf-8") == 'dependencies = ["ruff==1.0.0"]\n'


def test_replace_version_in_file_kind_pattern_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    f = tmp_path / "pyproject.toml"
    original = 'dependencies = ["ruff==0.15.18"]\n'
    f.write_text(original, encoding="utf-8")
    target = VersionTarget(path=f, kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    replace_version_in_file(target, "1.0.0", dry_run=True)
    assert f.read_text(encoding="utf-8") == original  # file unchanged
    assert "Would update" in capsys.readouterr().out


def test_replace_all_versions_atomic_kind_pattern(tmp_path: Path) -> None:
    f = tmp_path / "pyproject.toml"
    f.write_text('dependencies = ["ruff==0.15.18"]\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="pattern", pattern=r'"ruff==(\d+\.\d+\.\d+)"')
    replace_all_versions_atomic([target], "1.0.0", dry_run=False)
    assert f.read_text(encoding="utf-8") == 'dependencies = ["ruff==1.0.0"]\n'


def test_read_toml_field_missing_section_missing_field_and_non_string(tmp_path: Path) -> None:
    f = tmp_path / "x.toml"
    f.write_text("[project]\nname='x'\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"Missing section \[tool\.rrt\]"):
        read_toml_field(f, section="tool.rrt", field="version")

    f.write_text("[project]\nname='x'\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Missing field 'version'"):
        read_toml_field(f, section="project", field="version")

    f.write_text("[project]\nversion=1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="is not a string"):
        read_toml_field(f, section="project", field="version")


def test_read_package_json_version_error_paths(tmp_path: Path) -> None:
    f = tmp_path / "package.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="top-level object"):
        read_package_json_version(f)

    f.write_text('{"name":"x"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="Could not find top-level version"):
        read_package_json_version(f)

    f.write_text('{"version":1}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="is not a string"):
        read_package_json_version(f)


def test_replace_package_json_version_error_paths_and_newline_behavior() -> None:
    with pytest.raises(RuntimeError, match="top-level object"):
        replace_package_json_version("[]", "1.2.3")

    with pytest.raises(RuntimeError, match="Could not find top-level version"):
        replace_package_json_version('{"name":"x"}', "1.2.3")

    with pytest.raises(RuntimeError, match="must be a string"):
        replace_package_json_version('{"version":1}', "1.2.3")

    updated = replace_package_json_version('{"version":"1.0.0"}\n', "1.2.3")
    assert updated.endswith("\n")


def test_replace_pattern_version_no_match_raises() -> None:
    with pytest.raises(RuntimeError, match="Configured pattern did not match"):
        replace_pattern_version("x", r"^(v)(\d+\.\d+\.\d+)()$", "1.2.3")


def test_replace_pattern_target_atomic_updates_file(tmp_path: Path) -> None:
    """Atomic version replacement should handle regex-based targets too."""
    f = tmp_path / "README.md"
    f.write_text("version: v1.2.3", encoding="utf-8")
    target = VersionTarget(path=f, pattern=r"^(version: v)(\d+\.\d+\.\d+)(.*)$")

    replace_all_versions_atomic([target], "2.0.0", dry_run=False)

    assert f.read_text(encoding="utf-8") == "version: v2.0.0"


def test_detect_json_indent_tab() -> None:
    text = '{\n\t"version": "1.0.0"\n}\n'
    assert _detect_json_indent(text) == "\t"


# ---------------------------------------------------------------------------
# cargo_toml – read and replace
# ---------------------------------------------------------------------------


def test_read_cargo_toml_version(tmp_path: Path) -> None:
    f = tmp_path / "Cargo.toml"
    f.write_text('[package]\nname = "my-crate"\nversion = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="cargo_toml")
    assert read_version_string(target) == "1.2.3"


def test_read_cargo_toml_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "Cargo.toml"
    f.write_text('[package]\nname = "my-crate"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="cargo_toml")
    with pytest.raises(RuntimeError, match="Could not find"):
        read_version_string(target)


def test_replace_cargo_toml_version(tmp_path: Path) -> None:
    f = tmp_path / "Cargo.toml"
    f.write_text('[package]\nname = "my-crate"\nversion = "1.2.3"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="cargo_toml")
    replace_version_in_file(target, "1.3.0", dry_run=False)
    assert 'version = "1.3.0"' in f.read_text()


# ---------------------------------------------------------------------------
# maven_pom – read and replace
# ---------------------------------------------------------------------------


def test_read_maven_pom_version(tmp_path: Path) -> None:
    f = tmp_path / "pom.xml"
    f.write_text(
        "<?xml version='1.0'?>\n<project>\n  <version>1.2.3</version>\n</project>\n",
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="maven_pom")
    assert read_version_string(target) == "1.2.3"


def test_read_maven_pom_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "pom.xml"
    f.write_text("<?xml version='1.0'?>\n<project>\n</project>\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="maven_pom")
    with pytest.raises(RuntimeError, match="Could not find"):
        read_version_string(target)


def test_replace_maven_pom_version(tmp_path: Path) -> None:
    f = tmp_path / "pom.xml"
    f.write_text(
        "<?xml version='1.0'?>\n<project>\n  <version>1.2.3</version>\n</project>\n",
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="maven_pom")
    replace_version_in_file(target, "2.0.0", dry_run=False)
    assert "<version>2.0.0</version>" in f.read_text()


# ---------------------------------------------------------------------------
# gemspec – read and replace
# ---------------------------------------------------------------------------


def test_read_gemspec_version(tmp_path: Path) -> None:
    f = tmp_path / "mygem.gemspec"
    f.write_text(
        'Gem::Specification.new do |spec|\n  spec.version = "1.2.3"\nend\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="gemspec")
    assert read_version_string(target) == "1.2.3"


def test_read_gemspec_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "mygem.gemspec"
    f.write_text("Gem::Specification.new do |spec|\nend\n", encoding="utf-8")
    target = VersionTarget(path=f, kind="gemspec")
    with pytest.raises(RuntimeError, match="Could not find"):
        read_version_string(target)


def test_replace_gemspec_version(tmp_path: Path) -> None:
    f = tmp_path / "mygem.gemspec"
    f.write_text(
        'Gem::Specification.new do |spec|\n  spec.version = "1.2.3"\nend\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="gemspec")
    replace_version_in_file(target, "1.3.0", dry_run=False)
    assert 'spec.version = "1.3.0"' in f.read_text()


# ---------------------------------------------------------------------------
# csproj – read and replace
# ---------------------------------------------------------------------------


def test_read_csproj_version(tmp_path: Path) -> None:
    f = tmp_path / "MyApp.csproj"
    f.write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <Version>1.2.3</Version>\n  </PropertyGroup>\n</Project>\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="csproj")
    assert read_version_string(target) == "1.2.3"


def test_read_csproj_version_missing_raises(tmp_path: Path) -> None:
    f = tmp_path / "MyApp.csproj"
    f.write_text('<Project Sdk="Microsoft.NET.Sdk">\n</Project>\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="csproj")
    with pytest.raises(RuntimeError, match="Could not find"):
        read_version_string(target)


def test_replace_csproj_version(tmp_path: Path) -> None:
    f = tmp_path / "MyApp.csproj"
    f.write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <Version>1.2.3</Version>\n  </PropertyGroup>\n</Project>\n',
        encoding="utf-8",
    )
    target = VersionTarget(path=f, kind="csproj")
    replace_version_in_file(target, "2.0.0", dry_run=False)
    assert "<Version>2.0.0</Version>" in f.read_text()


# ---------------------------------------------------------------------------
# VALID_TARGET_KINDS includes all new kinds
# ---------------------------------------------------------------------------


def test_validate_cargo_toml_kind() -> None:
    target = VersionTarget(path=Path("Cargo.toml"), kind="cargo_toml")
    target.validate()


def test_validate_maven_pom_kind() -> None:
    target = VersionTarget(path=Path("pom.xml"), kind="maven_pom")
    target.validate()


def test_validate_gemspec_kind() -> None:
    target = VersionTarget(path=Path("mygem.gemspec"), kind="gemspec")
    target.validate()


def test_validate_csproj_kind() -> None:
    target = VersionTarget(path=Path("MyApp.csproj"), kind="csproj")
    target.validate()


# ---------------------------------------------------------------------------
# update_version_targets_atomic
# ---------------------------------------------------------------------------


def test_update_version_targets_atomic_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from repo_release_tools.version.targets import replace_all_versions_atomic

    f = tmp_path / "__init__.py"
    f.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")

    replace_all_versions_atomic([target], "2.0.0", dry_run=True)

    # File must NOT be written in dry-run mode
    assert f.read_text() == '__version__ = "1.0.0"\n'
    assert "2.0.0" in capsys.readouterr().out


def test_update_version_targets_atomic_writes_file(tmp_path: Path) -> None:
    from repo_release_tools.version.targets import replace_all_versions_atomic

    f = tmp_path / "__init__.py"
    f.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")

    replace_all_versions_atomic([target], "2.0.0", dry_run=False)

    assert "2.0.0" in f.read_text()


def test_update_version_targets_atomic_rollback_on_failure(tmp_path: Path) -> None:
    """If a write fails partway through, already-written files are restored."""
    from unittest.mock import patch

    from repo_release_tools.version.targets import replace_all_versions_atomic

    f1 = tmp_path / "a/__init__.py"
    f1.parent.mkdir()
    f1.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    f2 = tmp_path / "b/__init__.py"
    f2.parent.mkdir()
    f2.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    t1 = VersionTarget(path=f1, kind="python_version")
    t2 = VersionTarget(path=f2, kind="python_version")

    original_write = Path.write_text
    call_count = [0]

    def fail_second(self: Path, data: str, **kwargs: str) -> None:
        call_count[0] += 1
        if call_count[0] == 2:
            raise OSError("disk full")
        original_write(self, data, **kwargs)

    with patch.object(Path, "write_text", fail_second):
        with pytest.raises(OSError, match="disk full"):
            replace_all_versions_atomic([t1, t2], "2.0.0", dry_run=False)

    # f1 should be rolled back to original content
    assert "1.0.0" in f1.read_text()
    assert "1.0.0" in f2.read_text()


# ---------------------------------------------------------------------------
# replace_pin_in_file — pin_target_missing="warn"
# ---------------------------------------------------------------------------


def test_replace_pin_in_file_no_match_error(tmp_path: Path) -> None:
    from repo_release_tools.config import PinTarget
    from repo_release_tools.version.targets import replace_pin_in_file

    f = tmp_path / "README.md"
    f.write_text("no version here\n", encoding="utf-8")
    pin = PinTarget(path=f, pattern=r"(version=)(\d+\.\d+\.\d+)")

    with pytest.raises(RuntimeError, match="Pin pattern did not match"):
        replace_pin_in_file(pin, "2.0.0", dry_run=False, pin_target_missing="error")


# ---------------------------------------------------------------------------
# replace_all_versions_atomic – error paths (lines 116, 130-131)
# ---------------------------------------------------------------------------


def test_replace_all_versions_atomic_same_version_raises(tmp_path: Path) -> None:
    """RuntimeError when current version already equals the target version."""
    f = tmp_path / "__init__.py"
    f.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    target = VersionTarget(path=f, kind="python_version")
    with pytest.raises(RuntimeError):
        replace_all_versions_atomic([target], "1.0.0", dry_run=False)


def test_replace_all_versions_atomic_rollback_oserror_suppressed(tmp_path: Path) -> None:
    """Phase-2 write failure triggers rollback; OSError in rollback is silently ignored."""
    f1 = tmp_path / "a.py"
    f1.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    f2 = tmp_path / "b.py"
    f2.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    target1 = VersionTarget(path=f1, kind="python_version")
    target2 = VersionTarget(path=f2, kind="python_version")

    call_n = [0]
    _real_write = Path.write_text  # type: ignore[attr-defined]

    def _write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> None:
        call_n[0] += 1
        if call_n[0] == 2:
            raise PermissionError("disk full")
        if call_n[0] == 3:
            raise OSError("can't restore")
        _real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    with patch.object(Path, "write_text", _write):
        with pytest.raises(PermissionError, match="disk full"):
            replace_all_versions_atomic([target1, target2], "2.0.0", dry_run=False)
