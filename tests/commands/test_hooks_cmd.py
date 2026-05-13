from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import pytest

from repo_release_tools.commands.hooks_cmd import (
    COPILOT_MANAGED_HOOKS_FILE,
    HOOK_TARGET_PATHS,
    _config_path_for_target,
    _dedupe_targets,
    _display_path,
    _list_hook_files,
    _managed_registration_payload,
    _merge_copilot_hooks,
    _merge_grouped_hooks,
    _merge_managed_registration,
    _powershell_command_for_script,
    _python_command_for_script,
    _resolve_install_plan,
    _safe_scheme_path,
    cmd_install,
    register,
)

EXPECTED_HOOK_FILES = {
    "rrt_user_branch_policy.py",
    "rrt_user_commit_policy.py",
    "rrt_user_changelog_policy.py",
    "rrt_user_release_readiness.py",
    "rrt_user_config_sanity.py",
    "rrt_user_docs_sync_hint.py",
    "rrt_user_dirty_tree_guard.py",
    "rrt_user_version_drift_guard.py",
    "rrt_user_ci_local_preflight.py",
    "rrt_user_security_hygiene_hint.py",
}


def _mock_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr("repo_release_tools.commands.hooks_cmd.Path.home", lambda: home)


def test_list_hook_files_returns_python_files() -> None:
    files = _list_hook_files()
    names = {name for name, _ in files}
    assert names == EXPECTED_HOOK_FILES
    assert all(name.endswith(".py") for name in names)
    assert all(content for _, content in files)


def test_cmd_install_writes_local_hooks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=False, force=False)

    result = cmd_install(args)

    assert result == 0
    hooks_dir = tmp_path / ".claude" / "hooks"
    assert hooks_dir.exists()
    expected_files = _list_hook_files()
    for filename, content in expected_files:
        installed = hooks_dir / filename
        assert installed.exists()
        assert installed.read_text(encoding="utf-8") == content.rstrip() + "\n"

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"]["SessionStart"][0]["hooks"]
    assert settings["hooks"]["PreToolUse"][0]["hooks"]
    assert settings["hooks"]["Stop"][0]["hooks"]


def test_cmd_install_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)
    args = Namespace(targets=["claude-local"], dry_run=True, force=False)

    result = cmd_install(args)

    assert result == 0
    assert not (tmp_path / ".claude" / "hooks").exists()
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_cmd_install_no_targets_dry_run_shows_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")
    args = Namespace(targets=None, dry_run=True, force=False)

    result = cmd_install(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "claude-local" in out


def test_cmd_install_no_targets_without_dry_run_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")
    args = Namespace(targets=None, dry_run=False, force=False)

    result = cmd_install(args)

    assert result == 1


def test_cmd_install_refuses_existing_hook_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    existing = hooks_dir / "rrt_user_branch_policy.py"
    existing.write_text("original content", encoding="utf-8")

    args = Namespace(targets=["claude-local"], dry_run=False, force=False)
    result = cmd_install(args)

    assert result == 1
    assert existing.read_text(encoding="utf-8") == "original content"


def test_cmd_install_force_overwrites_existing_hook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    first_name, first_content = _list_hook_files()[0]
    existing = hooks_dir / first_name
    existing.write_text("old content", encoding="utf-8")

    args = Namespace(targets=["claude-local"], dry_run=False, force=True)
    result = cmd_install(args)

    assert result == 0
    assert existing.read_text(encoding="utf-8") == first_content.rstrip() + "\n"


def test_cmd_install_writes_copilot_managed_hooks_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    result = cmd_install(Namespace(targets=["copilot-local"], dry_run=False, force=False))

    assert result == 0
    managed_path = tmp_path / ".github" / "hooks" / COPILOT_MANAGED_HOOKS_FILE
    rendered = json.loads(managed_path.read_text(encoding="utf-8"))
    assert rendered["version"] == 1
    assert rendered["hooks"]["SessionStart"]
    assert rendered["hooks"]["PreToolUse"]
    assert rendered["hooks"]["Stop"]


def test_cmd_install_merges_existing_claude_settings_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/hooks/custom.py",
                                    "timeout": 10,
                                },
                            ],
                        },
                    ],
                },
            },
        )
        + "\n",
        encoding="utf-8",
    )

    assert cmd_install(Namespace(targets=["claude-local"], dry_run=False, force=False)) == 0
    assert cmd_install(Namespace(targets=["claude-local"], dry_run=False, force=True)) == 0

    rendered = json.loads(settings_path.read_text(encoding="utf-8"))
    session_start_commands = [
        hook["command"] for hook in rendered["hooks"]["SessionStart"][0]["hooks"]
    ]
    assert "python3 .claude/hooks/custom.py" in session_start_commands
    assert session_start_commands.count("python3 .claude/hooks/rrt_user_branch_policy.py") == 1


def test_cmd_install_returns_one_for_os_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, home)

    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    first_name = _list_hook_files()[0][0]
    blocker = hooks_dir / first_name
    blocker.mkdir()

    args = Namespace(targets=["claude-local"], dry_run=False, force=True)
    result = cmd_install(args)

    assert result == 1


def test_python_and_powershell_commands_cover_local_codex_and_gemini_targets(
    tmp_path: Path,
) -> None:
    codex_hooks = tmp_path / ".codex" / "hooks"
    gemini_hooks = tmp_path / ".gemini" / "hooks"

    assert _python_command_for_script("codex-local", "hook.py", hooks_dir=codex_hooks) == (
        'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/hook.py"'
    )
    assert _python_command_for_script("gemini-local", "hook.py", hooks_dir=gemini_hooks) == (
        'python3 "$GEMINI_PROJECT_DIR/.gemini/hooks/hook.py"'
    )
    assert _powershell_command_for_script("codex-local", "hook.py", hooks_dir=codex_hooks) == (
        "py .codex/hooks/hook.py"
    )
    assert _powershell_command_for_script("gemini-local", "hook.py", hooks_dir=gemini_hooks) == (
        "py .gemini/hooks/hook.py"
    )
    assert _python_command_for_script(
        "claude-global", "hook.py", hooks_dir=tmp_path / ".claude" / "hooks"
    ) == (f'python3 "{(tmp_path / ".claude" / "hooks" / "hook.py").as_posix()}"')
    assert (
        _powershell_command_for_script(
            "claude-global", "hook.py", hooks_dir=tmp_path / ".claude" / "hooks"
        )
        == f'py "{(tmp_path / ".claude" / "hooks" / "hook.py").as_posix()}"'
    )


def test_managed_registration_payload_covers_gemini_and_default_surfaces(
    tmp_path: Path,
) -> None:
    gemini_payload = _managed_registration_payload(
        "gemini-local", hooks_dir=tmp_path / ".gemini" / "hooks"
    )
    assert gemini_payload["hooks"]["BeforeTool"][0]["matcher"] == "run_shell_command|bash"
    assert gemini_payload["hooks"]["AfterAgent"][0]["hooks"]

    default_payload = _managed_registration_payload(
        "claude-local", hooks_dir=tmp_path / ".claude" / "hooks"
    )
    assert default_payload["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert default_payload["hooks"]["Stop"][0]["hooks"]


def test_merge_helpers_cover_new_groups_and_validation_errors() -> None:
    merged = _merge_grouped_hooks(
        {"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"command": "python3 a"}]}]}},
        {"hooks": {"SessionStart": [{"matcher": "new", "hooks": [{"command": "python3 b"}]}]}},
    )
    assert {group["matcher"] for group in merged["hooks"]["SessionStart"]} == {"", "new"}

    with pytest.raises(ValueError, match="Hook event 'SessionStart' must be a JSON array."):
        _merge_grouped_hooks({"hooks": {}}, {"hooks": {"SessionStart": {"matcher": "bad"}}})

    with pytest.raises(ValueError, match="Hook event 'SessionStart' must be a JSON array."):
        _merge_grouped_hooks(
            {"hooks": {"SessionStart": {"matcher": "bad"}}},
            {"hooks": {"SessionStart": [{"matcher": "new", "hooks": [{"command": "python3 b"}]}]}},
        )

    with pytest.raises(ValueError, match="Hook event 'SessionStart' must be a JSON array."):
        _merge_grouped_hooks(
            {"hooks": {"SessionStart": {"matcher": "bad"}}},
            {"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"command": "python3 b"}]}]}},
        )

    with pytest.raises(ValueError, match="Top-level 'hooks' must be a JSON object."):
        _merge_grouped_hooks({"hooks": []}, {"hooks": {}})

    with pytest.raises(ValueError, match="Hook group for 'SessionStart' must be a JSON object."):
        _merge_grouped_hooks(
            {"hooks": {}},
            {"hooks": {"SessionStart": [["bad entry"]]}},
        )

    copilot_merged = _merge_copilot_hooks(
        {
            "version": 1,
            "hooks": {
                "SessionStart": [{"matcher": "", "command": "python3 a", "bash": "python3 a"}],
            },
        },
        {
            "hooks": {
                "SessionStart": [
                    {"matcher": "", "command": "python3 a", "bash": "python3 a"},
                    {"matcher": "x", "command": "python3 b", "bash": "python3 b"},
                ]
            }
        },
    )
    assert len(copilot_merged["hooks"]["SessionStart"]) == 2

    with pytest.raises(ValueError, match="Copilot hook event 'SessionStart' must be a JSON array."):
        _merge_copilot_hooks({"hooks": {}}, {"hooks": {"SessionStart": {"bad": True}}})

    with pytest.raises(ValueError, match="Copilot hook event 'SessionStart' must be a JSON array."):
        _merge_copilot_hooks(
            {"hooks": {"SessionStart": {"matcher": "bad"}}},
            {
                "hooks": {
                    "SessionStart": [
                        {"matcher": "new", "command": "python3 b", "bash": "python3 b"}
                    ]
                }
            },
        )

    with pytest.raises(ValueError, match="Copilot hook event 'SessionStart' must be a JSON array."):
        _merge_copilot_hooks(
            {"hooks": {"SessionStart": {"matcher": "bad"}}},
            {
                "hooks": {
                    "SessionStart": [{"matcher": "", "command": "python3 b", "bash": "python3 b"}]
                }
            },
        )

    with pytest.raises(ValueError, match="Top-level 'hooks' must be a JSON object."):
        _merge_copilot_hooks({"hooks": []}, {"hooks": {}})

    assert _merge_managed_registration(
        "copilot-local",
        {"version": 1, "hooks": {}},
        {"version": 1, "hooks": {}},
    ) == {"version": 1, "hooks": {}}
    assert _merge_managed_registration("claude-local", {"hooks": {}}, {"hooks": {}}) == {
        "hooks": {}
    }


def test_merge_helpers_cover_remaining_validation_edges() -> None:
    with pytest.raises(ValueError, match="Managed hook additions must expose a 'hooks' object."):
        _merge_grouped_hooks({"hooks": {}}, {"hooks": []})

    with pytest.raises(ValueError, match="Hook entry for 'SessionStart' must be a JSON object."):
        _merge_grouped_hooks(
            {"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"command": "python3 a"}]}]}},
            {"hooks": {"SessionStart": [{"matcher": "", "hooks": ["bad entry"]}]}},
        )

    with pytest.raises(ValueError, match="Managed hook additions must expose a 'hooks' object."):
        _merge_copilot_hooks({"hooks": {}}, {"hooks": []})

    with pytest.raises(
        ValueError, match="Copilot hook entry for 'SessionStart' must be a JSON object."
    ):
        _merge_copilot_hooks(
            {
                "hooks": {
                    "SessionStart": [{"matcher": "", "command": "python3 a", "bash": "python3 a"}]
                }
            },
            {"hooks": {"SessionStart": ["bad entry"]}},
        )


def test_cmd_install_handles_missing_hook_files_and_registration_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _mock_home(monkeypatch, tmp_path / "home")

    def _raise_missing_bundle() -> list[tuple[str, str]]:
        raise FileNotFoundError("missing bundle")

    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd._list_hook_files",
        _raise_missing_bundle,
    )
    assert cmd_install(Namespace(targets=None, dry_run=True, force=False)) == 0

    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd._list_hook_files",
        _list_hook_files,
    )

    def _raise_registration_write(config_path: Path, rendered: dict[str, object]) -> None:
        raise OSError("boom")

    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd._write_registration_file",
        _raise_registration_write,
    )
    assert cmd_install(Namespace(targets=["claude-local"], dry_run=False, force=False)) == 1


def test_dedupe_targets_preserves_order_and_drops_duplicates() -> None:
    result = _dedupe_targets(["claude-local", "codex-local", "claude-local"])
    assert result == ["claude-local", "codex-local"]


def test_display_path_uses_cwd_home_and_absolute(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    local_path = cwd / ".claude" / "hooks" / "rrt_user_branch_policy.py"
    home_path = home / ".claude" / "hooks" / "rrt_user_branch_policy.py"
    abs_path = tmp_path / "other" / "rrt_user_branch_policy.py"

    assert (
        _display_path(local_path, cwd=cwd, home=home) == ".claude/hooks/rrt_user_branch_policy.py"
    )
    assert (
        _display_path(home_path, cwd=cwd, home=home) == "~/.claude/hooks/rrt_user_branch_policy.py"
    )
    assert _display_path(abs_path, cwd=cwd, home=home) == str(abs_path)


def test_resolve_install_plan_includes_hook_files(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"
    plan = _resolve_install_plan(["claude-local"], cwd=cwd, home=home)
    assert len(plan) == 1
    target_name, hooks_dir, hook_files = plan[0]
    assert target_name == "claude-local"
    assert hooks_dir == cwd / ".claude" / "hooks"
    assert {name for name, _ in hook_files} == EXPECTED_HOOK_FILES


def test_hook_target_paths_map_is_not_empty() -> None:
    assert "claude-local" in HOOK_TARGET_PATHS
    assert "codex-local" in HOOK_TARGET_PATHS
    assert "copilot-local" in HOOK_TARGET_PATHS
    assert "gemini-global" in HOOK_TARGET_PATHS


def test_config_path_for_target_uses_documented_surfaces(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    home = tmp_path / "home"

    assert (
        _config_path_for_target("claude-local", cwd=cwd, home=home)
        == cwd / ".claude" / "settings.json"
    )
    assert (
        _config_path_for_target("codex-local", cwd=cwd, home=home) == cwd / ".codex" / "hooks.json"
    )
    assert (
        _config_path_for_target("copilot-local", cwd=cwd, home=home)
        == cwd / ".github" / "hooks" / COPILOT_MANAGED_HOOKS_FILE
    )
    assert (
        _config_path_for_target("gemini-global", cwd=cwd, home=home)
        == home / ".gemini" / "settings.json"
    )


def test_config_path_for_target_rejects_unknown_target(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _config_path_for_target("unknown-target", cwd=tmp_path, home=tmp_path)


def test_register_adds_hooks_install_parser() -> None:
    main_parser = argparse.ArgumentParser()
    subparsers = main_parser.add_subparsers(dest="command")
    register(subparsers)

    args = main_parser.parse_args(["hooks", "install", "--target", "claude-local"])
    assert args.targets == ["claude-local"]
    assert not args.dry_run
    assert not args.force
    assert args.handler is cmd_install


def test_safe_scheme_path_returns_none_on_missing_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_key_error(*_args: object, **_kwargs: object) -> str:
        raise KeyError("missing")

    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd.get_path",
        _raise_key_error,
    )

    assert _safe_scheme_path("headers") is None


def test_list_hook_files_raises_when_no_candidates_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd._safe_scheme_path",
        lambda _name: None,
    )
    monkeypatch.setattr(Path, "is_dir", lambda self: False)

    with pytest.raises(FileNotFoundError):
        _list_hook_files()


def test_list_hook_files_uses_headers_and_filters_non_py(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    headers_dir = tmp_path / "headers"
    headers_dir.mkdir()
    (headers_dir / "README.txt").write_text("ignore", encoding="utf-8")
    (headers_dir / "hook.py").write_text("print('ok')\n", encoding="utf-8")

    repo_hooks = Path(__file__).resolve().parents[2] / ".github" / "hooks"
    original_is_dir = Path.is_dir
    monkeypatch.setattr(
        Path,
        "is_dir",
        lambda self: False if self == repo_hooks else original_is_dir(self),
    )
    monkeypatch.setattr(
        "repo_release_tools.commands.hooks_cmd._safe_scheme_path",
        lambda name: headers_dir if name == "headers" else None,
    )

    files = _list_hook_files()
    assert files == [("hook.py", "print('ok')\n")]
