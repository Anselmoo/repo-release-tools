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


def test_cmd_bump_refuses_existing_release_branch_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n', encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: True
    )
    monkeypatch.setattr("repo_release_tools.commands.bump.git.current_branch", lambda root: "main")

    result = cmd_bump(
        Namespace(
            bump="patch",
            dry_run=False,
            force=False,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "already exists" in captured.err


def test_cmd_bump_force_resets_existing_release_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
lock_command = []

[[tool.rrt.version_targets]]
path = "package.json"
kind = "package_json"
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{\n  "name": "example",\n  "version": "0.1.0"\n}\n', encoding="utf-8"
    )

    calls: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.working_tree_clean", lambda root: True
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git.branch_exists", lambda root, branch: True
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
            force=True,
            no_commit=True,
            no_changelog=True,
            no_update=True,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Resetting it with --force" in captured.out
    assert ["git", "checkout", "-B", "release/v0.1.1"] in calls
    assert ["git", "checkout", "-b", "release/v0.1.1"] not in calls


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
        '[project]\nname = "example"\nversion = "0.3.0"\n',
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


def test_cmd_bump_native_cargo_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bump works on a plain Rust project (Cargo.toml only) without explicit rrt config."""
    (tmp_path / "Cargo.toml").write_text(
        """\
[package]
name = "example"
version = "0.3.0"
""",
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
    content = (tmp_path / "Cargo.toml").read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in content


def test_cmd_bump_python_version_kind_explicit_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """bump updates __version__ in a Python file when kind='python_version' is configured."""
    init_file = tmp_path / "src" / "mypkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/mypkg/__init__.py"
kind = "python_version"
""",
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
            dry_run=True,
            no_commit=True,
            no_changelog=True,
            no_update=False,
            include_maintenance=False,
            base_branch=None,
            group=None,
        )
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "release/v0.2.0" in captured.out
    assert "Would update" in captured.out


def test_cmd_bump_python_version_kind_writes_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """bump actually writes the new __version__ when not in dry-run mode."""
    init_file = tmp_path / "src" / "mypkg" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "src/mypkg/__init__.py"
kind = "python_version"
""",
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
    assert '__version__ = "1.0.1"' in init_file.read_text(encoding="utf-8")


def test_cmd_bump_autodetects_python_version_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Zero-config bump auto-detects __version__ in src/<pkg>/__init__.py."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.5.0"\n',
        encoding="utf-8",
    )
    init_file = tmp_path / "src" / "example" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text('__version__ = "0.5.0"\n', encoding="utf-8")

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
    assert 'version = "0.6.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.6.0"' in init_file.read_text(encoding="utf-8")


def test_cmd_bump_go_version_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """bump updates const Version in a Go file when kind='go_version' is configured."""
    ver_file = tmp_path / "internal" / "version" / "version.go"
    ver_file.parent.mkdir(parents=True)
    ver_file.write_text('package version\n\nconst Version = "0.1.0"\n', encoding="utf-8")

    (tmp_path / ".rrt.toml").write_text(
        """\
[tool.rrt]
release_branch = "release/v{version}"
lock_command = []

[[tool.rrt.version_targets]]
path = "internal/version/version.go"
kind = "go_version"
""",
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
            bump="major",
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
    assert 'const Version = "1.0.0"' in ver_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# update_changelog – empty [Unreleased] and health-mode tests
# ---------------------------------------------------------------------------


def test_update_changelog_inserts_after_empty_unreleased(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When [Unreleased] exists but is empty, the generated section goes after it."""
    from repo_release_tools.commands.bump import update_changelog
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

    changelog = tmp_path / "CHANGELOG.md"
    # Simulates state left by promote_unreleased: empty [Unreleased] at the top.
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n\n### Added\n- init\n",
        encoding="utf-8",
    )

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: brand new feature"],
    )

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    # [Unreleased] must still be at the top (after the title).
    assert content.index("## [Unreleased]") < content.index("## [1.1.0]")
    # New version must appear before the old version.
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")


def test_update_changelog_adds_unreleased_placeholder_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When no [Unreleased] section exists the bump adds a health-mode placeholder."""
    from repo_release_tools.commands.bump import update_changelog
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget
    from repo_release_tools.changelog import has_unreleased_section

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [1.0.0] - 2025-01-01\n\n### Added\n- init\n",
        encoding="utf-8",
    )

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    config = RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: something new"],
    )

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    # A fresh [Unreleased] placeholder must now be present (health mode).
    assert has_unreleased_section(content)
    # New version must appear before the old version.
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")


# ---------------------------------------------------------------------------
# update_changelog – changelog_mode tests
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, changelog: Path) -> "object":
    from repo_release_tools.config import RrtConfig, VersionGroup, VersionTarget

    target = VersionTarget(path=tmp_path / "pyproject.toml", kind="pep621")
    group = VersionGroup(
        name="default",
        release_branch="release/v{version}",
        changelog_file=changelog,
        lock_command=[],
        generated_files=[],
        version_targets=[target],
    )
    return RrtConfig(
        root=tmp_path,
        config_file=tmp_path / "pyproject.toml",
        version_groups=[group],
        default_group_name="default",
    )


def test_update_changelog_mode_promote_with_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """promote mode promotes [Unreleased] when entries are present."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- great thing\n\n## [1.0.0] - 2025-01-01\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config, "1.1.0", include_maintenance=False, dry_run=False, changelog_mode="promote"
    )

    content = changelog.read_text(encoding="utf-8")
    assert "## [1.1.0]" in content
    assert "great thing" in content
    assert "## [Unreleased]" in content  # fresh placeholder re-inserted


def test_update_changelog_mode_promote_empty_section_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """promote mode with empty [Unreleased] prints a warning and skips writing."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-01\n"
    changelog.write_text(original, encoding="utf-8")
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config, "1.1.0", include_maintenance=False, dry_run=False, changelog_mode="promote"
    )

    assert changelog.read_text(encoding="utf-8") == original  # unchanged


def test_update_changelog_mode_promote_no_section_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """promote mode with no [Unreleased] section prints a warning and skips writing."""
    from repo_release_tools.commands.bump import update_changelog

    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [1.0.0] - 2025-01-01\n"
    changelog.write_text(original, encoding="utf-8")
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config, "1.1.0", include_maintenance=False, dry_run=False, changelog_mode="promote"
    )

    assert changelog.read_text(encoding="utf-8") == original  # unchanged


def test_update_changelog_mode_generate_ignores_unreleased(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """generate mode always writes from git log, even with a non-empty [Unreleased]."""
    from repo_release_tools.commands.bump import update_changelog

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: from git log"],
    )
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- manual entry\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(
        config, "1.1.0", include_maintenance=False, dry_run=False, changelog_mode="generate"
    )

    content = changelog.read_text(encoding="utf-8")
    assert "from git log" in content
    assert "## [1.1.0]" in content


# ---------------------------------------------------------------------------
# update_changelog – RST format
# ---------------------------------------------------------------------------


def test_update_changelog_generates_rst_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """For a .rst changelog the generated section must use RST underline notation."""
    from repo_release_tools.commands.bump import update_changelog
    from repo_release_tools.changelog import has_unreleased_section, ChangelogFormat

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["feat: rst release"],
    )
    changelog = tmp_path / "CHANGELOG.rst"
    changelog.write_text(
        "Changelog\n=========\n\n1.0.0 - 2025-01-01\n-------------------\n\nAdded\n~~~~~\n\n- init\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "### " not in content
    assert "1.1.0" in content
    assert has_unreleased_section(content, ChangelogFormat.RST)
    assert content.index("Unreleased") < content.index("1.1.0") < content.index("1.0.0")


def test_update_changelog_generates_txt_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """For a .txt changelog the generated section must use RST underline notation."""
    from repo_release_tools.commands.bump import update_changelog

    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag",
        lambda root: ["fix: txt fix"],
    )
    changelog = tmp_path / "CHANGELOG.txt"
    changelog.write_text(
        "Changelog\n=========\n\n1.0.0 - 2025-01-01\n-------------------\n\n- init\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path, changelog)

    update_changelog(config, "1.1.0", include_maintenance=False, dry_run=False)

    content = changelog.read_text(encoding="utf-8")
    assert "## [" not in content
    assert "txt fix" in content


# ---------------------------------------------------------------------------
# pin_targets — integration with cmd_bump
# ---------------------------------------------------------------------------

_BUMP_CONFIG_WITH_PINS = """\
[tool.rrt]
release_branch = "release/v{{version}}"
changelog_file = "CHANGELOG.md"
lock_command = []

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs/action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "example"
version = "0.1.0"
"""


def _setup_pin_bump(tmp_path: Path) -> Path:
    """Create a minimal project with a pin_targets doc file."""
    (tmp_path / "pyproject.toml").write_text(_BUMP_CONFIG_WITH_PINS, encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "action.md"
    doc.write_text("- uses: Anselmoo/repo-release-tools@v0.1.0\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- new feature\n",
        encoding="utf-8",
    )
    return doc


def test_cmd_bump_updates_pin_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """cmd_bump should update pin_targets files to the new version."""
    doc = _setup_pin_bump(tmp_path)

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
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag", lambda root: []
    )

    args = Namespace(
        bump="minor",
        dry_run=False,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=False,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    assert "v0.2.0" in doc.read_text(encoding="utf-8")


def test_cmd_bump_dry_run_does_not_write_pin_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """In dry-run mode, pin_targets files must not be modified."""
    doc = _setup_pin_bump(tmp_path)
    original_doc = doc.read_text(encoding="utf-8")

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
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag", lambda root: []
    )

    args = Namespace(
        bump="minor",
        dry_run=True,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=False,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    # File must be untouched in dry-run
    assert doc.read_text(encoding="utf-8") == original_doc
    assert "Would update" in capsys.readouterr().out


def test_cmd_bump_no_pin_sync_skips_pin_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--no-pin-sync must skip all pin_targets updates."""
    doc = _setup_pin_bump(tmp_path)
    original_doc = doc.read_text(encoding="utf-8")

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
    monkeypatch.setattr(
        "repo_release_tools.commands.bump.git_log_since_latest_tag", lambda root: []
    )

    args = Namespace(
        bump="minor",
        dry_run=False,
        no_commit=True,
        no_changelog=True,
        no_update=True,
        no_pin_sync=True,
        include_maintenance=False,
        base_branch=None,
        group=None,
    )
    result = cmd_bump(args)

    assert result == 0
    # Doc file must be untouched when --no-pin-sync is set
    assert doc.read_text(encoding="utf-8") == original_doc
