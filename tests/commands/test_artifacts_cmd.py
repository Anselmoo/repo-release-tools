from __future__ import annotations

import argparse
import unittest.mock
from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.commands.artifacts_cmd import (
    SOURCE_OWNED_TOPIC_DOCS,
    _add_artifacts_strict_argument,
    _print_artifact_list,
    _target_dicts,
    cmd_artifacts,
    register,
)
from repo_release_tools.config.core import ArtifactTarget, RrtConfig, VersionGroup
from repo_release_tools.state import artifacts_lock_path, build_artifacts_lock, write_lock

_DEFAULT_GROUP = VersionGroup(
    name="default",
    release_branch="release/v{version}",
    changelog_file=Path("CHANGELOG.md"),
    lock_command=[],
    generated_files=[],
    version_targets=[],
)


def _make_config(
    tmp_path: Path | None = None,
    targets: list[dict[str, str]] | None = None,
    artifact_targets: list[ArtifactTarget] | None = None,
) -> RrtConfig:
    root = tmp_path or Path(".")
    if artifact_targets is not None:
        resolved_targets = artifact_targets
    else:
        resolved_targets = [
            ArtifactTarget(path=t["path"], description=t.get("description", ""))
            for t in (targets or [])
        ]
    return RrtConfig(
        root=root,
        config_file=root / "pyproject.toml",
        version_groups=[_DEFAULT_GROUP],
        artifact_targets=resolved_targets,
    )


def _make_args(
    *,
    snapshot: bool = False,
    check: bool = False,
    list_: bool = False,
    regenerate: bool = False,
    dry_run: bool = False,
    strict: bool = False,
    verbose: int = 0,
) -> argparse.Namespace:
    return argparse.Namespace(
        snapshot=snapshot,
        check=check,
        list=list_,
        regenerate=regenerate,
        dry_run=dry_run,
        strict=strict,
        verbose=verbose,
    )


def _write_svg(path: Path, content: str = "<svg/>") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# SOURCE_OWNED_TOPIC_DOCS
# ---------------------------------------------------------------------------


def test_source_owned_topic_docs_has_artifacts_entry() -> None:
    assert any(name == "artifacts" for name, _ in SOURCE_OWNED_TOPIC_DOCS)


# ---------------------------------------------------------------------------
# _target_dicts
# ---------------------------------------------------------------------------


def test_target_dicts_converts_correctly() -> None:
    config = _make_config(targets=[{"path": "foo/*.svg", "description": "Foo SVGs"}])
    result = _target_dicts(config)
    assert result == [{"path": "foo/*.svg", "description": "Foo SVGs", "command": [], "inputs": []}]


def test_target_dicts_empty() -> None:
    assert _target_dicts(_make_config()) == []


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_register_creates_artifacts_subcommand() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)
    args = parser.parse_args(["artifacts"])
    assert hasattr(args, "handler")


def test_register_snapshot_flag() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["artifacts", "--snapshot"])
    assert args.snapshot is True
    assert args.check is False


def test_register_check_and_strict_flags() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["artifacts", "--check", "--strict"])
    assert args.check is True
    assert args.strict is True


# ---------------------------------------------------------------------------
# _add_artifacts_strict_argument (shared spec, opposite polarity per caller)
# ---------------------------------------------------------------------------


def test_add_artifacts_strict_argument_default_false_uses_strict_flag() -> None:
    parser = argparse.ArgumentParser()
    _add_artifacts_strict_argument(parser, default=False)

    assert parser.parse_args([]).strict is False
    assert parser.parse_args(["--strict"]).strict is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--no-strict"])


def test_add_artifacts_strict_argument_default_true_uses_no_strict_flag() -> None:
    parser = argparse.ArgumentParser()
    _add_artifacts_strict_argument(parser, default=True)

    assert parser.parse_args([]).strict is True
    assert parser.parse_args(["--no-strict"]).strict is False
    with pytest.raises(SystemExit):
        parser.parse_args(["--strict"])


def test_register_list_flag() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["artifacts", "--list"])
    assert args.list is True


def test_register_snapshot_and_check_mutually_exclusive() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    with pytest.raises(SystemExit):
        parser.parse_args(["artifacts", "--snapshot", "--check"])


# ---------------------------------------------------------------------------
# cmd_artifacts — no targets configured
# ---------------------------------------------------------------------------


def test_no_targets_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = _make_config()
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_artifacts(_make_args())
    assert rc == 0


def test_no_targets_snapshot_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = _make_config()
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_artifacts(_make_args(snapshot=True))
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_artifacts — config load failure
# ---------------------------------------------------------------------------


def test_config_load_error_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
        side_effect=RuntimeError("no config"),
    ):
        rc = cmd_artifacts(_make_args())
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_artifacts --snapshot
# ---------------------------------------------------------------------------


def test_snapshot_writes_lock_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg")
    config = _make_config(targets=[{"path": "badges/*.svg", "description": "Test badges"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_artifacts(_make_args(snapshot=True))

    assert rc == 0
    lock = tmp_path / ".rrt" / "artifacts.lock.toml"
    assert lock.exists()


def test_snapshot_records_correct_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg", "<svg>github</svg>")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))

    import tomllib

    lock = tmp_path / ".rrt" / "artifacts.lock.toml"
    data = tomllib.loads(lock.read_text())
    assert "badges/github.svg" in data.get("files", {})


# ---------------------------------------------------------------------------
# cmd_artifacts --check (no drift)
# ---------------------------------------------------------------------------


def test_check_no_drift_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        rc = cmd_artifacts(_make_args(check=True))
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_artifacts --check (with drift)
# ---------------------------------------------------------------------------


def test_check_advisory_exits_0_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    badge = _write_svg(tmp_path / "badges" / "github.svg", "<svg>v1</svg>")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        badge.write_text("<svg>v2</svg>")
        rc = cmd_artifacts(_make_args(check=True))
    assert rc == 0


def test_check_strict_exits_1_on_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    badge = _write_svg(tmp_path / "badges" / "github.svg", "<svg>v1</svg>")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        badge.write_text("<svg>v2</svg>")
        rc = cmd_artifacts(_make_args(check=True, strict=True))
    assert rc == 1


# ---------------------------------------------------------------------------
# cmd_artifacts default (no flag) — status summary
# ---------------------------------------------------------------------------


def test_default_no_flag_exits_0_when_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        rc = cmd_artifacts(_make_args())
    assert rc == 0


def test_default_no_flag_exits_0_on_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    badge = _write_svg(tmp_path / "badges" / "github.svg", "<svg>v1</svg>")
    config = _make_config(targets=[{"path": "badges/*.svg"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        badge.write_text("<svg>v2</svg>")
        rc = cmd_artifacts(_make_args())
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_artifacts --list
# ---------------------------------------------------------------------------


def test_list_exits_0_with_no_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg")
    config = _make_config(targets=[{"path": "badges/*.svg", "description": "Test badges"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_artifacts(_make_args(list_=True))
    assert rc == 0


def test_list_exits_0_after_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_svg(tmp_path / "badges" / "github.svg")
    config = _make_config(targets=[{"path": "badges/*.svg", "description": "Test badges"}])
    with patch(
        "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config", return_value=config
    ):
        cmd_artifacts(_make_args(snapshot=True))
        rc = cmd_artifacts(_make_args(list_=True))
    assert rc == 0


# ---------------------------------------------------------------------------
# _print_artifact_list — branch coverage
# ---------------------------------------------------------------------------


def test_print_artifact_list_shows_not_in_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_svg(tmp_path / "badges" / "github.svg")
    targets = [{"path": "badges/*.svg", "description": ""}]
    lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "NOT IN LOCK" in captured.out


def test_print_artifact_list_shows_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_svg(tmp_path / "badges" / "github.svg")
    targets = [{"path": "badges/*.svg", "description": "Badges"}]
    lock_path = artifacts_lock_path(tmp_path)
    data = build_artifacts_lock(targets, tmp_path)
    write_lock(lock_path, data)

    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "✓" in captured.out


def test_print_artifact_list_shows_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    badge = _write_svg(tmp_path / "badges" / "github.svg", "<svg>v1</svg>")
    targets = [{"path": "badges/*.svg", "description": ""}]
    lock_path = artifacts_lock_path(tmp_path)
    data = build_artifacts_lock(targets, tmp_path)
    write_lock(lock_path, data)
    badge.write_text("<svg>v2</svg>")

    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.out


def test_print_artifact_list_no_files_matched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    targets = [{"path": "badges/*.svg", "description": "Empty set"}]
    lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "no files matched" in captured.out


def test_print_artifact_list_no_description_uses_pattern(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_svg(tmp_path / "badges" / "github.svg")
    targets = [{"path": "badges/*.svg"}]
    lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "badges/*.svg" in captured.out


def test_print_artifact_list_skips_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "badges").mkdir()
    (tmp_path / "badges" / "github.svg").mkdir()
    targets = [{"path": "badges/*.svg", "description": ""}]
    lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
    _print_artifact_list(targets, tmp_path, lock_path)
    captured = capsys.readouterr()
    assert "NOT IN LOCK" not in captured.out
    assert "MISMATCH" not in captured.out


# ---------------------------------------------------------------------------
# cmd_artifacts --regenerate
# ---------------------------------------------------------------------------


class TestCmdArtifactsRegenerate:
    """Tests for rrt artifacts --regenerate."""

    def _make_config_with_command(
        self,
        tmp_path: Path,
        command: list[str],
        inputs: list[str] | None = None,
    ) -> RrtConfig:
        """Return config with one artifact target that has a command."""
        target = ArtifactTarget(
            path="*.svg",
            description="badge",
            command=command,
            inputs=inputs or [],
        )
        return _make_config(tmp_path, artifact_targets=[target])

    def test_regenerate_runs_command_and_snapshots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_svg(tmp_path / "badge.svg")
        config = self._make_config_with_command(tmp_path, ["echo", "regenerated"])
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(regenerate=True)
            ret = cmd_artifacts(args)
        assert ret == 0
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        assert lock_path.exists()
        out = capsys.readouterr().out
        assert "regenerat" in out.lower() or "snapshot" in out.lower()

    def test_regenerate_dry_run_does_not_write_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_svg(tmp_path / "badge.svg")
        config = self._make_config_with_command(tmp_path, ["echo", "would-run"])
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(regenerate=True, dry_run=True)
            ret = cmd_artifacts(args)
        assert ret == 0
        assert not (tmp_path / ".rrt" / "artifacts.lock.toml").exists()
        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "would" in out.lower()

    def test_regenerate_skips_targets_without_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from repo_release_tools.config.model import ArtifactTarget

        _write_svg(tmp_path / "badge.svg")
        config = _make_config(
            tmp_path,
            artifact_targets=[
                ArtifactTarget(path="*.svg", description="badge", command=[], inputs=[])
            ],
        )
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(regenerate=True)
            ret = cmd_artifacts(args)
        assert ret == 0  # no targets with command → still exits 0

    def test_regenerate_no_command_targets_does_not_write_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--regenerate with targets that have no command must not overwrite the lock."""
        from repo_release_tools.config.model import ArtifactTarget

        # Write an existing lock to verify it is NOT touched
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text(
            "[meta]\ngenerated_at = '2026-01-01'\nrrt_version = '1.0.0'\n\n[files]\n"
        )
        original_mtime = lock_path.stat().st_mtime

        config = _make_config(
            tmp_path,
            artifact_targets=[
                ArtifactTarget(path="*.svg", description="badges", command=[], inputs=[])
            ],
        )
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(regenerate=True)
            ret = cmd_artifacts(args)

        assert ret == 0
        # Lock must NOT have been rewritten
        assert lock_path.stat().st_mtime == original_mtime

    def test_regenerate_returns_1_when_command_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_svg(tmp_path / "badge.svg")
        config = self._make_config_with_command(tmp_path, ["false"])
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(regenerate=True)
            ret = cmd_artifacts(args)
        assert ret == 1


# ---------------------------------------------------------------------------
# cmd_artifacts --check with inputs staleness
# ---------------------------------------------------------------------------


class TestCmdArtifactsCheckStaleness:
    """Tests for input-staleness detection via --check."""

    def test_check_strict_fails_on_stale_inputs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from repo_release_tools.state import hash_file

        svg = _write_svg(tmp_path / "badge.svg")
        (tmp_path / "gen.py").write_text("# generator")
        target = ArtifactTarget(path="*.svg", description="", command=[], inputs=["*.py"])
        config = _make_config(tmp_path, artifact_targets=[target])

        # Write lock with stale inputs_hash
        lock_path = tmp_path / ".rrt" / "artifacts.lock.toml"
        lock = {
            "meta": {"generated_at": "2026-01-01T00:00:00+00:00", "rrt_version": "1.0.0"},
            "targets": {"*.svg": {"inputs_hash": "sha256:stale"}},
            "files": {
                "badge.svg": {
                    "hash": hash_file(svg),
                    "size": svg.stat().st_size,
                    "description": "",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            },
        }
        write_lock(lock_path, lock)

        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch(
            "repo_release_tools.commands.artifacts_cmd.load_or_autodetect_config",
            return_value=config,
        ):
            args = _make_args(check=True, strict=True)
            ret = cmd_artifacts(args)
        assert ret == 1


# ---------------------------------------------------------------------------
# cmd_artifacts --dry-run validation
# ---------------------------------------------------------------------------


def test_dry_run_without_regenerate_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    # No mocks needed — guard fires before find_repo_root is called.
    ret = cmd_artifacts(_make_args(check=True, dry_run=True))
    assert ret == 1
    err = capsys.readouterr().err
    assert "--dry-run" in err
    assert "--regenerate" in err


def test_dry_run_without_snapshot_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    ret = cmd_artifacts(_make_args(snapshot=True, dry_run=True))
    assert ret == 1
    err = capsys.readouterr().err
    assert "--dry-run" in err
    assert "--regenerate" in err
