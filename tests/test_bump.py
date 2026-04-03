import os
from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands.bump import cmd_bump


def test_cmd_bump_dry_run_from_pep621_config(tmp_path, capsys) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[tool.rrt]
release_branch = \"release/v{version}\"
changelog_file = \"CHANGELOG.md\"
lock_command = [\"uv\", \"lock\", \"-U\"]

[[tool.rrt.version_targets]]
path = \"pyproject.toml\"
kind = \"pep621\"

[project]
name = \"example\"
version = \"0.1.0\"
""",
        encoding="utf-8",
    )

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        args = __import__("argparse").Namespace(
            bump="minor",
            dry_run=True,
            no_commit=True,
            no_changelog=False,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
        result = cmd_bump(args)
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "Version bump" in captured.out
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out
    assert "no files were modified" in captured.out


def test_cmd_bump_dry_run_from_rrt_toml_and_package_json(tmp_path, capsys) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """[tool.rrt]
release_branch = "release/v{version}"

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        """{
  "name": "example",
  "version": "0.1.0"
}
""",
        encoding="utf-8",
    )

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="minor",
                dry_run=True,
                no_commit=True,
                no_changelog=False,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            )
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_stages_generated_files_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []
generated_files = ["package-lock.json", "pnpm-lock.yaml"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        """{
  "name": "example",
  "version": "0.1.0"
}
""",
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    add_calls = [cmd for cmd in calls if cmd[:2] == ["git", "add"]]
    assert result == 0
    assert any("package-lock.json" in cmd for cmd in add_calls)
    assert any("pnpm-lock.yaml" in cmd for cmd in add_calls)
    assert not any("uv.lock" in cmd for cmd in add_calls)


def test_cmd_bump_accepts_legacy_double_escaped_pattern(tmp_path: Path, capsys) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/example/__init__.py"
pattern = '^(\\\\s*__version__\\\\s*=\\\\s*")([^"]+)(")'
""",
        encoding="utf-8",
    )
    init_file = tmp_path / "src" / "example" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            )
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.1.1" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_requires_group_for_multi_group_config(tmp_path: Path, capsys) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]
name = "python"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"

[project]
name = "example"
version = "0.1.0"
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"name":"example","version":"0.1.0"}', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group=None,
            )
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 1
    assert "Multiple version groups configured" in captured.err


def test_cmd_bump_updates_selected_group_only(tmp_path: Path, capsys) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]

[[tool.rrt.version_groups]]
name = "python"
version_source = "pyproject.toml"

[[tool.rrt.version_groups.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_groups]]
name = "web"
release_branch = "release/web/v{version}"
version_source = "package.json"

[[tool.rrt.version_groups.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"name":"example","version":"2.3.4"}', encoding="utf-8")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = cmd_bump(
            Namespace(
                bump="patch",
                dry_run=True,
                no_commit=True,
                no_changelog=True,
                no_update=False,
                include_maintenance=False,
                base_branch=None,
                group="web",
            )
        )
    finally:
        os.chdir(cwd)

    captured = capsys.readouterr()
    assert result == 0
    assert "release/web/v2.3.5" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_no_update_skips_lock_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--no-update must prevent the lock command from running."""
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = ["npm", "install"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "1.0.0"\n}\n', encoding="utf-8"
    )

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    def fake_run(cmd: list[str], root: Path, *, dry_run: bool, label: str) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("repo_release_tools.commands.bump.git.run", fake_run)

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    assert result == 0
    assert not any("npm" in cmd for cmd in calls)


def test_cmd_bump_native_pep621_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bump works on a plain PEP 621 project without [tool.rrt] config."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"example\"\nversion = \"0.3.0\"\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run", lambda cmd, root, *, dry_run, label: ""
    )

    result = cmd_bump(
        Namespace(
            bump="minor",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    assert result == 0
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in content


def test_cmd_bump_native_package_json_no_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bump works on a plain JS project (package.json only) without [tool.rrt] config."""
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "2.0.0"\n}\n', encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: False
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.run", lambda cmd, root, *, dry_run, label: ""
    )

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    assert result == 0
    import json

    pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == "2.0.1"
