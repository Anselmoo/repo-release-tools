from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from repo_release_tools.commands.init import cmd_init
from repo_release_tools.config import recommend_init_config


def test_recommend_init_config_for_pep621_repo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    rendered = recommend_init_config(tmp_path)

    assert "[tool.rrt]" in rendered
    assert 'changelog_file = "CHANGELOG.md"' in rendered
    assert 'lock_command = ["uv", "lock", "-U"]' in rendered
    assert 'generated_files = ["uv.lock"]' in rendered
    assert 'path = "pyproject.toml"' in rendered
    assert 'kind = "pep621"' in rendered
    assert 'ci_format = "pep440"' in rendered


def test_recommend_init_config_for_hybrid_repo_sets_version_source(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example-web",\n  "version": "0.1.0"\n}\n',
        encoding="utf-8",
    )

    rendered = recommend_init_config(tmp_path)

    assert 'version_source = "pyproject.toml"' in rendered
    assert 'path = "pyproject.toml"' in rendered
    assert 'path = "package.json"' in rendered
    assert "lock_command =" not in rendered
    assert "generated_files =" not in rendered


def test_cmd_init_writes_rrt_toml(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "1.2.3"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False))

    assert result == 0
    content = (tmp_path / ".rrt.toml").read_text(encoding="utf-8")
    assert 'path = "package.json"' in content
    assert 'kind = "package_json"' in content


def test_cmd_init_dry_run_does_not_write_file(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "example"\nversion = "0.4.0"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=True, force=False))

    captured = capsys.readouterr()
    assert result == 0
    assert not (tmp_path / ".rrt.toml").exists()
    assert "Would write .rrt.toml" in captured.out
