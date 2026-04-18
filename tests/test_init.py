from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from repo_release_tools.commands.init import cmd_init
from repo_release_tools.config import (
    recommend_init_config,
    recommend_init_config_for_go,
    recommend_init_section_for_cargo,
    recommend_init_section_for_node,
    recommend_init_section_for_pyproject,
)


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


# ---------------------------------------------------------------------------
# recommend_init_section_for_pyproject
# ---------------------------------------------------------------------------


def test_recommend_init_section_for_pyproject_pep621(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    rendered = recommend_init_section_for_pyproject(tmp_path)

    assert rendered.startswith("[tool.rrt]")
    assert 'kind = "pep621"' in rendered
    assert 'path = "pyproject.toml"' in rendered


def test_recommend_init_section_for_pyproject_fallback(tmp_path: Path) -> None:
    # No version file → falls back to the generic Python example
    rendered = recommend_init_section_for_pyproject(tmp_path)

    assert "[tool.rrt]" in rendered


# ---------------------------------------------------------------------------
# recommend_init_section_for_cargo
# ---------------------------------------------------------------------------


def test_recommend_init_section_for_cargo_detected(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mylib"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )

    rendered = recommend_init_section_for_cargo(tmp_path)

    assert rendered.startswith("[package.metadata.rrt]")
    assert "[[package.metadata.rrt.version_targets]]" in rendered
    assert 'path = "Cargo.toml"' in rendered


def test_recommend_init_section_for_cargo_fallback(tmp_path: Path) -> None:
    # No Cargo.toml → falls back to the generic Rust example
    rendered = recommend_init_section_for_cargo(tmp_path)

    assert "[tool.rrt]" in rendered  # RUST_TOOL_RRT_EXAMPLE still uses [tool.rrt]


# ---------------------------------------------------------------------------
# cmd_init --target pyproject
# ---------------------------------------------------------------------------


def test_cmd_init_pyproject_appends_section(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="pyproject"))

    assert result == 0
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project]" in content  # original content preserved
    assert "[tool.rrt]" in content
    assert "[[tool.rrt.version_targets]]" in content


def test_cmd_init_pyproject_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    original = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=True, force=False, target="pyproject"))

    captured = capsys.readouterr()
    assert result == 0
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original
    assert "Would append to pyproject.toml" in captured.out


def test_cmd_init_pyproject_refuses_when_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="pyproject"))

    captured = capsys.readouterr()
    assert result == 1
    assert "pyproject.toml does not exist" in captured.err


def test_cmd_init_pyproject_refuses_if_already_present(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "1.0.0"\n\n[tool.rrt]\nrelease_branch = "main"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="pyproject"))

    captured = capsys.readouterr()
    assert result == 1
    assert "already contains rrt configuration" in captured.err


def test_cmd_init_pyproject_force_appends_even_if_present(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "1.0.0"\n\n[tool.rrt]\nrelease_branch = "main"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=True, target="pyproject"))

    assert result == 0
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    # Two [tool.rrt] occurrences (original + appended)
    assert content.count("[tool.rrt]") == 2


# ---------------------------------------------------------------------------
# cmd_init --target cargo
# ---------------------------------------------------------------------------


def test_cmd_init_cargo_appends_section(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mylib"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="cargo"))

    assert result == 0
    content = (tmp_path / "Cargo.toml").read_text(encoding="utf-8")
    assert "[package]" in content  # original content preserved
    assert "[package.metadata.rrt]" in content
    assert "[[package.metadata.rrt.version_targets]]" in content


def test_cmd_init_cargo_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mylib"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )
    original = (tmp_path / "Cargo.toml").read_text(encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=True, force=False, target="cargo"))

    captured = capsys.readouterr()
    assert result == 0
    assert (tmp_path / "Cargo.toml").read_text(encoding="utf-8") == original
    assert "Would append to Cargo.toml" in captured.out


def test_cmd_init_cargo_refuses_when_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="cargo"))

    captured = capsys.readouterr()
    assert result == 1
    assert "Cargo.toml does not exist" in captured.err


def test_cmd_init_cargo_refuses_if_already_present(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mylib"\nversion = "0.2.0"\n\n[package.metadata.rrt]\nrelease_branch = "main"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="cargo"))

    captured = capsys.readouterr()
    assert result == 1
    assert "already contains rrt configuration" in captured.err


# ---------------------------------------------------------------------------
# recommend_init_section_for_node
# ---------------------------------------------------------------------------


def test_recommend_init_section_for_node_detected(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{\n  "name": "myapp",\n  "version": "1.0.0"\n}\n',
        encoding="utf-8",
    )

    result = recommend_init_section_for_node(tmp_path)

    assert isinstance(result, dict)
    assert "version_targets" in result
    targets = result["version_targets"]
    assert any(t.get("path") == "package.json" for t in targets)


def test_recommend_init_section_for_node_fallback(tmp_path: Path) -> None:
    result = recommend_init_section_for_node(tmp_path)

    assert isinstance(result, dict)
    assert result["version_targets"][0]["kind"] == "package_json"


# ---------------------------------------------------------------------------
# recommend_init_config_for_go
# ---------------------------------------------------------------------------


def test_recommend_init_config_for_go_with_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/mymod\n\ngo 1.22\n", encoding="utf-8")

    result = recommend_init_config_for_go(tmp_path)

    assert "[tool.rrt]" in result
    assert "go_version" in result or "go" in result.lower()


def test_recommend_init_config_for_go_fallback(tmp_path: Path) -> None:
    result = recommend_init_config_for_go(tmp_path)

    assert "[tool.rrt]" in result
    assert "go_version" in result


# ---------------------------------------------------------------------------
# cmd_init --target node
# ---------------------------------------------------------------------------


def test_cmd_init_node_merges_rrt_key(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{\n  "name": "myapp",\n  "version": "1.0.0"\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="node"))

    assert result == 0
    import json

    data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert "name" in data  # original content preserved
    assert "rrt" in data
    assert "version_targets" in data["rrt"]


def test_cmd_init_node_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
    original = '{\n  "name": "myapp",\n  "version": "1.0.0"\n}\n'
    (tmp_path / "package.json").write_text(original, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=True, force=False, target="node"))

    captured = capsys.readouterr()
    assert result == 0
    assert (tmp_path / "package.json").read_text(encoding="utf-8") == original
    assert 'Would add "rrt" key to package.json' in captured.out


def test_cmd_init_node_refuses_when_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="node"))

    captured = capsys.readouterr()
    assert result == 1
    assert "package.json does not exist" in captured.err


def test_cmd_init_node_refuses_if_rrt_key_exists(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "package.json").write_text(
        '{\n  "name": "myapp",\n  "version": "1.0.0",\n  "rrt": {"release_branch": "main"}\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="node"))

    captured = capsys.readouterr()
    assert result == 1
    assert '"rrt" key' in captured.err or "already contains" in captured.err


def test_cmd_init_node_force_overwrites_rrt_key(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{\n  "name": "myapp",\n  "version": "1.0.0",\n  "rrt": {"release_branch": "old"}\n}\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=True, target="node"))

    assert result == 0
    import json

    data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert "version_targets" in data["rrt"]  # replaced with full template


# ---------------------------------------------------------------------------
# cmd_init --target go
# ---------------------------------------------------------------------------


def test_cmd_init_go_writes_rrt_toml_with_go_template(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/mymod\n\ngo 1.22\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="go"))

    assert result == 0
    content = (tmp_path / ".rrt.toml").read_text(encoding="utf-8")
    assert "[tool.rrt]" in content
    assert "go_version" in content or "go" in content.lower()


def test_cmd_init_go_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=True, force=False, target="go"))

    captured = capsys.readouterr()
    assert result == 0
    assert not (tmp_path / ".rrt.toml").exists()
    assert "Would write .rrt.toml" in captured.out


def test_cmd_init_go_fallback_no_go_mod(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = cmd_init(Namespace(dry_run=False, force=False, target="go"))

    assert result == 0
    content = (tmp_path / ".rrt.toml").read_text(encoding="utf-8")
    assert "[tool.rrt]" in content
    assert "go_version" in content
