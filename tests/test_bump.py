import os
from pathlib import Path

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
            include_maintenance=False,
            base_branch=None,
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
