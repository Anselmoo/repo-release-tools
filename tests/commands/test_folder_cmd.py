from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from repo_release_tools.commands import folder
from repo_release_tools.config import load_config_from_path
from repo_release_tools.folders import resolve_template_catalog


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "root": ".",
        "template": [],
        "report_only": False,
        "format": "text",
        "force": False,
        "dry_run": False,
        "name": "captured-template",
        "selector": ".",
        "loose": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_builtin_template_catalog_has_expected_breadth() -> None:
    catalog = resolve_template_catalog()

    assert len(catalog) >= 12
    assert "cargo-inspired" in catalog
    assert "python-package" in catalog
    assert "loose-starter" in catalog
    assert "loose-validate" in catalog


def test_load_config_with_folder_policy(tmp_path: Path) -> None:
    config_file = tmp_path / ".rrt.toml"
    config_file.write_text(
        """
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.folders]
mode = "strict"

[[tool.rrt.folders.rules]]
name = "root"
selector = "."
templates = ["python-package"]
exact = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    config = load_config_from_path(tmp_path, config_file)

    assert config.folders is not None
    assert config.folders.mode == "strict"
    assert len(config.folders.rules) == 1
    assert config.folders.rules[0].templates == ("python-package",)


def test_load_config_rejects_invalid_folder_mode(tmp_path: Path) -> None:
    config_file = tmp_path / ".rrt.toml"
    config_file.write_text(
        """
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.folders]
mode = "chaos"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tool\\.rrt\\.folders\\.mode"):
        load_config_from_path(tmp_path, config_file)


def test_folder_check_passes_for_python_package_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "src" / "package").mkdir(parents=True)
    (tmp_path / "src" / "package" / "__init__.py").write_text(
        '"""Example package."""\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_check(
        _args(root=str(tmp_path), template=["python-package"], format="json"),
    )

    assert rc == 0


def test_folder_check_fails_on_unexpected_entry_in_exact_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / ".rrt.toml"
    config_file.write_text(
        """
[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.folders]
mode = "strict"

[[tool.rrt.folders.rules]]
name = "workspace"
selector = "."
templates = ["monorepo-workspace"]
exact = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Docs\n", encoding="utf-8")
    (tmp_path / "packages" / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "rogue.txt").write_text("oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_check(_args(root=str(tmp_path)))

    assert rc == 1
    assert "Unexpected entry 'rogue.txt'" in capsys.readouterr().err


def test_folder_check_report_only_downgrades_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_check(
        _args(root=str(tmp_path), template=["docs-only"], report_only=True, format="json"),
    )

    assert rc == 0


def test_folder_scaffold_dry_run_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_scaffold(_args(root=str(tmp_path), template=["docs-only"], dry_run=True))

    assert rc == 0
    assert not (tmp_path / "docs").exists()
    assert "[dry-run] mkdir docs" in capsys.readouterr().out


def test_folder_scaffold_writes_expected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_scaffold(_args(root=str(tmp_path), template=["docs-only"]))

    assert rc == 0
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / "docs" / "index.md").exists()


def test_folder_scaffold_force_overwrites_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_scaffold(_args(root=str(tmp_path), template=["docs-only"], force=True))

    assert rc == 0
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# Documentation\n"


def test_folder_design_emits_toml_snippet(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")

    rc = folder.cmd_folder_design(_args(root=str(tmp_path), name="captured", selector="projects/*"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "[tool.rrt.folders]" in out
    assert 'name = "captured"' in out
    assert 'selector = "projects/*"' in out


def test_folder_design_loose_sets_loose_strictness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "scripts").mkdir()

    rc = folder.cmd_folder_design(_args(root=str(tmp_path), name="captured", loose=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert 'strictness = "loose"' in out
    assert "exact = false" in out


def test_folder_check_json_output_is_machine_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = folder.cmd_folder_check(_args(root=str(tmp_path), template=["docs-only"], format="json"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["mode"] == "strict"
    assert payload["ok"] is False
    assert payload["violation_count"] >= 1
