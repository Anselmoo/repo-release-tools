"""Tests for the rrt sync command."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from repo_release_tools.commands import sync_cmd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYPROJECT_BASE = (
    '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
    '[project]\nname = "x"\nversion = "0.5.0"\n'
)

_PYPROJECT_WITH_UPSTREAM = _PYPROJECT_BASE + '[tool.rrt.upstream]\npackage = "ruff"\n'

_PYPROJECT_WITH_PROVIDER = (
    '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
    '[project]\nname = "x"\nversion = "0.5.0"\n'
    '[tool.rrt.upstream]\npackage = "mypackage"\nprovider = "npm"\n'
)

# pyproject with upstream and custom commit_message
_PYPROJECT_WITH_COMMIT_MSG = (
    '[tool.rrt]\nrelease_branch = "release/v{version}"\n'
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
    '[project]\nname = "x"\nversion = "0.5.0"\n'
    '[tool.rrt.upstream]\npackage = "ruff"\ncommit_message = "rel {version}"\n'
)


def _ns(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "dry_run": False,
        "group": None,
        "json": False,
        "verbose": 0,
        "bump": False,
        "commit": False,
        "tag": False,
        "commit_message": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _init_git(path: Path) -> None:
    """Initialise a minimal git repository so git commit/tag work."""
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=path, check=True, capture_output=True
    )


def _git_log_subjects(path: Path) -> list[str]:
    """Return commit subjects in reverse-chronological order."""
    result = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_tags(path: Path) -> list[str]:
    """Return sorted list of tags."""
    result = subprocess.run(
        ["git", "tag", "--sort=version:refname"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [t.strip() for t in result.stdout.splitlines() if t.strip()]


def _write_and_commit_initial(path: Path, content: str) -> None:
    """Write pyproject.toml and create the initial commit."""
    (path / "pyproject.toml").write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "pyproject.toml"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initial"],
        cwd=path,
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Test 1: lists newer versions, filters out older/equal
# ---------------------------------------------------------------------------


def test_cmd_sync_lists_newer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.5.0", "0.6.0", "0.5.1"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.5.1" in out
    assert "0.6.0" in out
    assert "0.4.0" not in out
    assert "0.5.0" not in out


# ---------------------------------------------------------------------------
# Test 2: --json emits a JSON array
# ---------------------------------------------------------------------------


def test_cmd_sync_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.5.0", "0.6.0", "0.5.1"],
    )
    rc = sync_cmd.cmd_sync(_ns(json=True))
    out = capsys.readouterr().out.strip()
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert "0.5.1" in data
    assert "0.6.0" in data
    assert "0.4.0" not in data


# ---------------------------------------------------------------------------
# Test 3: no upstream_package configured → returns 1
# ---------------------------------------------------------------------------


def test_cmd_sync_errors_without_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert sync_cmd.cmd_sync(_ns()) == 1


# ---------------------------------------------------------------------------
# Test 4: provider other than pypi is passed through to fetch_versions
# ---------------------------------------------------------------------------


def test_cmd_sync_passes_provider_to_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_PROVIDER,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    received: list[tuple[str, str]] = []

    def _fake_fetch(pkg: str, provider: str) -> list[str]:
        received.append((pkg, provider))
        return ["0.6.0"]

    monkeypatch.setattr(sync_cmd, "fetch_versions", _fake_fetch)

    rc = sync_cmd.cmd_sync(_ns())
    capsys.readouterr()  # consume output
    assert rc == 0
    assert len(received) == 1
    assert received[0] == ("mypackage", "npm")


# ---------------------------------------------------------------------------
# Test 5: empty result when no newer versions → still returns 0
# ---------------------------------------------------------------------------


def test_cmd_sync_no_newer_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.3.0"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# Test 6: non-semver tags are skipped without error
# ---------------------------------------------------------------------------


def test_cmd_sync_skips_non_semver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.6.0rc1", "not-a-version", "0.7.0", "1.0.0a1"],
    )
    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.7.0" in out
    # non-semver entries silently dropped
    assert "not-a-version" not in out


# ---------------------------------------------------------------------------
# Test 7: unknown --group name → returns 1, does not raise
# ---------------------------------------------------------------------------


def test_cmd_sync_bad_group_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_WITH_UPSTREAM,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = sync_cmd.cmd_sync(_ns(group="nonexistent"))
    assert rc == 1


# ---------------------------------------------------------------------------
# NEW TESTS — --bump flag
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 8: --bump with no newer versions → no-op, exits 0, nothing written
# ---------------------------------------------------------------------------


def test_bump_no_newer_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When there are no newer versions, --bump is a no-op that exits 0."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_cmd, "fetch_versions", lambda pkg, provider: ["0.4.0", "0.3.0"])

    rc = sync_cmd.cmd_sync(_ns(bump=True))
    capsys.readouterr()
    assert rc == 0
    # Version file must be untouched
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.5.0"' in content


# ---------------------------------------------------------------------------
# Test 9: --bump rewrites version target for each newer version in ascending order
# ---------------------------------------------------------------------------


def test_bump_applies_each_newer_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump applies 0.6.0 then 0.7.0 to the version target file."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0", "0.4.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True))
    capsys.readouterr()
    assert rc == 0
    # Final state must be 0.7.0
    content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.7.0"' in content


# ---------------------------------------------------------------------------
# Test 10: --bump --commit creates one commit per version
# ---------------------------------------------------------------------------


def test_bump_commit_creates_per_version_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump --commit creates commits 'Mirror: 0.6.0' and 'Mirror: 0.7.0'."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True))
    capsys.readouterr()
    assert rc == 0

    subjects = _git_log_subjects(tmp_path)
    assert "Mirror: 0.6.0" in subjects
    assert "Mirror: 0.7.0" in subjects


# ---------------------------------------------------------------------------
# Test 11: --bump --commit --commit-message overrides the default template
# ---------------------------------------------------------------------------


def test_bump_commit_message_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--commit-message 'rel {version}' overrides the default mirror message."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, commit_message="rel {version}"))
    capsys.readouterr()
    assert rc == 0

    subjects = _git_log_subjects(tmp_path)
    assert "rel 0.6.0" in subjects
    assert "rel 0.7.0" in subjects
    # default message must NOT appear
    assert "Mirror: 0.6.0" not in subjects


# ---------------------------------------------------------------------------
# Test 12: --bump --commit uses group.upstream_commit_message from config
# ---------------------------------------------------------------------------


def test_bump_commit_uses_config_commit_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """group.upstream_commit_message from pyproject.toml is used when --commit-message is absent."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_COMMIT_MSG)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True))
    capsys.readouterr()
    assert rc == 0

    subjects = _git_log_subjects(tmp_path)
    assert "rel 0.6.0" in subjects


# ---------------------------------------------------------------------------
# Test 13: --bump --tag creates per-version tags
# ---------------------------------------------------------------------------


def test_bump_tag_creates_per_version_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump --tag creates v0.6.0 and v0.7.0 annotated tags."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0"],
    )

    # --commit needed so each version gets its own commit before tagging
    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, tag=True))
    capsys.readouterr()
    assert rc == 0

    tags = _git_tags(tmp_path)
    assert "v0.6.0" in tags
    assert "v0.7.0" in tags


# ---------------------------------------------------------------------------
# Test 14: --bump --tag without --commit still tags the version on same commit
# ---------------------------------------------------------------------------


def test_bump_tag_without_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump --tag without --commit still creates the tag for the final version."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.7.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, tag=True))
    capsys.readouterr()
    assert rc == 0

    tags = _git_tags(tmp_path)
    assert "v0.7.0" in tags


# ---------------------------------------------------------------------------
# Test 15: --bump --dry-run writes nothing, makes no commit/tag, prints plan
# ---------------------------------------------------------------------------


def test_bump_dry_run_no_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump --dry-run prints a plan but does not write or commit anything."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0"],
    )

    original_content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, tag=True, dry_run=True))
    out = capsys.readouterr().out
    assert rc == 0

    # File must be unchanged
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original_content

    # No new commits
    log = _git_log_subjects(tmp_path)
    assert "Mirror: 0.6.0" not in log
    assert "Mirror: 0.7.0" not in log

    # No tags
    assert _git_tags(tmp_path) == []

    # Plan output must mention what would happen
    assert "0.6.0" in out or "Plan" in out
    assert "dry" in out.lower() or "DRY" in out


# ---------------------------------------------------------------------------
# Test 16: existing list/--json behavior unchanged when --bump is absent
# ---------------------------------------------------------------------------


def test_list_behavior_unchanged_without_bump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --bump, cmd_sync still lists versions one-per-line."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0", "0.7.0"],
    )

    rc = sync_cmd.cmd_sync(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    assert "0.6.0" in lines
    assert "0.7.0" in lines


def test_list_json_behavior_unchanged_without_bump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --bump, --json still emits a JSON array."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(json=True))
    out = capsys.readouterr().out.strip()
    assert rc == 0
    data = json.loads(out)
    assert "0.6.0" in data


# ---------------------------------------------------------------------------
# Test 17: --bump --dry-run plan mentions would-bump and would-commit lines
# ---------------------------------------------------------------------------


def test_bump_dry_run_plan_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run output includes would-bump and would-commit lines."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, tag=True, dry_run=True))
    out = capsys.readouterr().out
    assert rc == 0
    # Must mention the version in dry-run context
    assert "0.6.0" in out
    # Must communicate nothing was done
    assert "no changes" in out.lower() or "dry" in out.lower() or "DRY" in out


# ---------------------------------------------------------------------------
# Test 18: --bump --dry-run with NO newer versions prints no-versions message
# ---------------------------------------------------------------------------


def test_bump_dry_run_no_newer_versions_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bump --dry-run with no newer versions prints the no-op dry-run message."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.4.0", "0.3.0"],  # all older
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, tag=True, dry_run=True))
    out = capsys.readouterr().out
    assert rc == 0
    # Must include the dry-run header and no-newer message
    assert "DRY RUN" in out or "dry-run" in out.lower()
    assert "No newer" in out or "nothing to do" in out.lower()


# ---------------------------------------------------------------------------
# Test 19: --bump --tag returns error code when cmd_tag_create fails
# ---------------------------------------------------------------------------


def test_bump_tag_failure_propagates_error_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When cmd_tag_create returns non-zero, cmd_sync propagates that exit code."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    # Patch cmd_tag_create to simulate a failure (e.g. tag already exists)
    monkeypatch.setattr(sync_cmd, "cmd_tag_create", lambda ns: 1)

    rc = sync_cmd.cmd_sync(_ns(bump=True, tag=True))
    capsys.readouterr()
    assert rc == 1


# ---------------------------------------------------------------------------
# Test 20: bad commit-message template with unknown placeholder → ValueError
# ---------------------------------------------------------------------------


def test_bump_commit_bad_template_raises_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--commit-message with an unknown placeholder raises ValueError naming the template."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    with pytest.raises(ValueError, match=r"Mirror: \{foo\}"):
        sync_cmd.cmd_sync(_ns(bump=True, commit=True, commit_message="Mirror: {foo}"))


# ---------------------------------------------------------------------------
# Test 21: bad template in dry-run also raises ValueError immediately
# ---------------------------------------------------------------------------


def test_bump_commit_bad_template_raises_in_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bad --commit-message template raises ValueError even in --dry-run mode."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_UPSTREAM, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    with pytest.raises(ValueError, match=r"only the \{version\} placeholder"):
        sync_cmd.cmd_sync(_ns(bump=True, commit=True, dry_run=True, commit_message="rel {0}"))


# ---------------------------------------------------------------------------
# Test 22: valid custom template still works (confirm _render_commit_message happy path)
# ---------------------------------------------------------------------------


def test_bump_commit_valid_custom_template_works(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A well-formed custom template 'rel {version}' renders correctly."""
    _init_git(tmp_path)
    _write_and_commit_initial(tmp_path, _PYPROJECT_WITH_UPSTREAM)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sync_cmd,
        "fetch_versions",
        lambda pkg, provider: ["0.5.0", "0.6.0"],
    )

    rc = sync_cmd.cmd_sync(_ns(bump=True, commit=True, commit_message="rel {version}"))
    capsys.readouterr()
    assert rc == 0

    subjects = _git_log_subjects(tmp_path)
    assert "rel 0.6.0" in subjects
