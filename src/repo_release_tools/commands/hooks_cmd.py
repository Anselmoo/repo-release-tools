"""Install bundled rrt user workflow hook scripts and register them automatically.

## Overview

`rrt hooks` manages installation of the packaged user-facing hook scripts into
tool-specific hook directories and writes managed hook-registration config for
the selected surface. The only implemented subcommand is `install`.

## Target surfaces

The install command can write to local or global hook roots for:

- Claude: `.claude/hooks`
- Codex: `.codex/hooks`
- Copilot: `.github/hooks` (local), `~/.copilot/hooks` (global)
- Gemini: `.gemini/hooks`

Each target receives the same bundled `.py` hook scripts for user-facing `rrt`
workflow checks and a managed hook-registration file in the surface's native
JSON format.

## Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory.
- Refuses to overwrite an existing script file unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
    without writing files.
- Merges managed hook registrations additively, preserving unrelated settings.

## Examples

- `rrt hooks install --target claude-local`
- `rrt hooks install --target claude-local --force`
- `rrt hooks install --dry-run`

## Caveats

- `rrt hooks` requires a subcommand; use `rrt hooks install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Hook registration happens automatically during installation.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from sysconfig import get_path
from typing import Any, cast

from repo_release_tools.ui import DryRunPrinter

HOOK_TARGET_PATHS = {
    "claude-global": lambda cwd, home: home / ".claude" / "hooks",
    "claude-local": lambda cwd, home: cwd / ".claude" / "hooks",
    "codex-global": lambda cwd, home: home / ".codex" / "hooks",
    "codex-local": lambda cwd, home: cwd / ".codex" / "hooks",
    "copilot-global": lambda cwd, home: home / ".copilot" / "hooks",
    "copilot-local": lambda cwd, home: cwd / ".github" / "hooks",
    "gemini-global": lambda cwd, home: home / ".gemini" / "hooks",
    "gemini-local": lambda cwd, home: cwd / ".gemini" / "hooks",
}

HOOKS_EXAMPLES = (
    "  $ rrt hooks install --target claude-local\n"
    "  $ rrt hooks install --target codex-local\n"
    "  $ rrt hooks install --target gemini-local\n"
    "  $ rrt hooks install --target claude-local --force"
)

HOOKS_INSTALL_EXAMPLES = (
    "  $ rrt hooks install --target claude-local\n"
    "  $ rrt hooks install --target claude-local --force --dry-run\n"
    "  $ rrt hooks install --target codex-global\n"
    "  $ rrt hooks install --target copilot-local"
)

SESSION_START_HOOK_FILES = (
    "rrt_user_branch_policy.py",
    "rrt_user_config_sanity.py",
)
PRE_TOOL_HOOK_FILES = (
    "rrt_user_commit_policy.py",
    "rrt_user_changelog_policy.py",
)
STOP_HOOK_FILES = (
    "rrt_user_release_readiness.py",
    "rrt_user_docs_sync_hint.py",
    "rrt_user_dirty_tree_guard.py",
    "rrt_user_version_drift_guard.py",
    "rrt_user_ci_local_preflight.py",
    "rrt_user_security_hygiene_hint.py",
)

COPILOT_MANAGED_HOOKS_FILE = "rrt-managed.json"


def _safe_scheme_path(name: str) -> Path | None:
    """Return a sysconfig path when available, otherwise ``None``."""
    try:
        return Path(get_path(name, vars={}))
    except KeyError:
        return None


def _list_hook_files() -> list[tuple[str, str]]:
    """Return (filename, content) pairs for all bundled hook files."""
    repo_root = Path(__file__).resolve().parents[3]
    candidate_dirs = [repo_root / ".github" / "hooks"]
    if headers_dir := _safe_scheme_path("headers"):
        candidate_dirs.append(headers_dir)
    if data_dir := _safe_scheme_path("data"):
        candidate_dirs.append(data_dir / "hooks")

    for hooks_dir in candidate_dirs:
        if not hooks_dir.is_dir():
            continue
        result: list[tuple[str, str]] = []
        for entry in hooks_dir.iterdir():
            name = entry.name
            if not name.endswith(".py") or name == "__init__.py":
                continue
            content = entry.read_text(encoding="utf-8")
            result.append((name, content))
        if result:
            return sorted(result, key=lambda t: t[0])

    searched = ", ".join(str(path) for path in candidate_dirs)
    raise FileNotFoundError(f"Could not locate bundled hook scripts. Searched: {searched}")


def _dedupe_targets(targets: Iterable[str]) -> list[str]:
    """Return targets in first-seen order without duplicates."""
    seen: set[str] = set()
    ordered: list[str] = []
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def _display_path(path: Path, *, cwd: Path, home: Path) -> str:
    """Render *path* relative to cwd or home when possible."""
    with contextlib.suppress(ValueError):
        return str(path.relative_to(cwd))
    with contextlib.suppress(ValueError):
        return f"~/{path.relative_to(home)}"
    return str(path)


def _emit_install_error(message: str) -> int:
    p = DryRunPrinter(False)
    p.line(message, ok=False, stream=sys.stderr)
    return 1


def _resolve_install_plan(
    targets: list[str],
    *,
    cwd: Path,
    home: Path,
) -> list[tuple[str, Path, list[tuple[str, str]]]]:
    """Resolve target names into (target, hooks_dir, hook_files) triples."""
    hook_files = _list_hook_files()
    result = []
    for target in _dedupe_targets(targets):
        hooks_dir = HOOK_TARGET_PATHS[target](cwd, home)
        result.append((target, hooks_dir, hook_files))
    return result


def _target_surface(target: str) -> str:
    return target.split("-", maxsplit=1)[0]


def _config_path_for_target(target: str, *, cwd: Path, home: Path) -> Path:
    """Return the managed registration file for a hook install target."""
    match target:
        case "claude-global":
            return home / ".claude" / "settings.json"
        case "claude-local":
            return cwd / ".claude" / "settings.json"
        case "codex-global":
            return home / ".codex" / "hooks.json"
        case "codex-local":
            return cwd / ".codex" / "hooks.json"
        case "copilot-global":
            return home / ".copilot" / "hooks" / COPILOT_MANAGED_HOOKS_FILE
        case "copilot-local":
            return cwd / ".github" / "hooks" / COPILOT_MANAGED_HOOKS_FILE
        case "gemini-global":
            return home / ".gemini" / "settings.json"
        case "gemini-local":
            return cwd / ".gemini" / "settings.json"
        case _:
            raise KeyError(target)


def _python_command_for_script(target: str, filename: str, *, hooks_dir: Path) -> str:
    surface = _target_surface(target)
    is_local = target.endswith("local")

    if surface == "codex" and is_local:
        return f'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/{filename}"'
    if surface == "gemini" and is_local:
        return f'python3 "$GEMINI_PROJECT_DIR/.gemini/hooks/{filename}"'
    if is_local:
        local_prefix = {
            "claude": ".claude/hooks",
            "copilot": ".github/hooks",
        }.get(surface, hooks_dir.name)
        return f"python3 {local_prefix}/{filename}"
    return f'python3 "{(hooks_dir / filename).as_posix()}"'


def _powershell_command_for_script(target: str, filename: str, *, hooks_dir: Path) -> str:
    surface = _target_surface(target)
    is_local = target.endswith("local")
    if is_local:
        local_prefix = {
            "claude": ".claude/hooks",
            "copilot": ".github/hooks",
            "codex": ".codex/hooks",
            "gemini": ".gemini/hooks",
        }.get(surface, hooks_dir.name)
        return f"py {local_prefix}/{filename}"
    return f'py "{(hooks_dir / filename).as_posix()}"'


def _group_entries_for_files(
    target: str,
    filenames: tuple[str, ...],
    *,
    hooks_dir: Path,
    timeout: int,
) -> list[dict[str, object]]:
    return [
        {
            "type": "command",
            "command": _python_command_for_script(target, filename, hooks_dir=hooks_dir),
            "timeout": timeout,
        }
        for filename in filenames
    ]


def _copilot_entries_for_files(
    target: str,
    filenames: tuple[str, ...],
    *,
    hooks_dir: Path,
    timeout: int,
    matcher: str | None = None,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for filename in filenames:
        entry: dict[str, object] = {
            "type": "command",
            "bash": _python_command_for_script(target, filename, hooks_dir=hooks_dir),
            "command": _python_command_for_script(target, filename, hooks_dir=hooks_dir),
            "powershell": _powershell_command_for_script(target, filename, hooks_dir=hooks_dir),
            "timeoutSec": timeout,
        }
        if matcher is not None:
            entry["matcher"] = matcher
        result.append(entry)
    return result


def _managed_registration_payload(target: str, *, hooks_dir: Path) -> dict[str, Any]:
    surface = _target_surface(target)
    match surface:
        case "copilot":
            return {
                "version": 1,
                "hooks": {
                    "SessionStart": _copilot_entries_for_files(
                        target,
                        SESSION_START_HOOK_FILES,
                        hooks_dir=hooks_dir,
                        timeout=30,
                    ),
                    "PreToolUse": _copilot_entries_for_files(
                        target,
                        PRE_TOOL_HOOK_FILES,
                        hooks_dir=hooks_dir,
                        timeout=30,
                        matcher="bash",
                    ),
                    "Stop": _copilot_entries_for_files(
                        target,
                        STOP_HOOK_FILES,
                        hooks_dir=hooks_dir,
                        timeout=60,
                    ),
                },
            }
        case "gemini":
            return {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "*",
                            "hooks": _group_entries_for_files(
                                target,
                                SESSION_START_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=30000,
                            ),
                        },
                    ],
                    "BeforeTool": [
                        {
                            "matcher": "run_shell_command|bash",
                            "hooks": _group_entries_for_files(
                                target,
                                PRE_TOOL_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=30000,
                            ),
                        },
                    ],
                    "AfterAgent": [
                        {
                            "matcher": "*",
                            "hooks": _group_entries_for_files(
                                target,
                                STOP_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=60000,
                            ),
                        },
                    ],
                },
            }
        case _:
            return {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "",
                            "hooks": _group_entries_for_files(
                                target,
                                SESSION_START_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=30,
                            ),
                        },
                    ],
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": _group_entries_for_files(
                                target,
                                PRE_TOOL_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=30,
                            ),
                        },
                    ],
                    "Stop": [
                        {
                            "matcher": "",
                            "hooks": _group_entries_for_files(
                                target,
                                STOP_HOOK_FILES,
                                hooks_dir=hooks_dir,
                                timeout=60,
                            ),
                        },
                    ],
                },
            }


def _load_existing_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _merge_grouped_hooks(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged_hooks = cast("dict[str, Any]", merged.setdefault("hooks", {}))
    if not isinstance(merged_hooks, dict):
        raise ValueError("Top-level 'hooks' must be a JSON object.")
    addition_hooks = cast("dict[str, Any]", additions.get("hooks", {}))
    if not isinstance(addition_hooks, dict):
        raise ValueError("Managed hook additions must expose a 'hooks' object.")

    for event, addition_groups in addition_hooks.items():
        if not isinstance(addition_groups, list):
            raise ValueError(f"Hook event '{event}' must be a JSON array.")
        existing_groups = cast("list[dict[str, Any]]", merged_hooks.setdefault(event, []))
        if not isinstance(existing_groups, list):
            raise ValueError(f"Hook event '{event}' must be a JSON array.")
        for addition_group in addition_groups:
            if not isinstance(addition_group, dict):
                raise ValueError(f"Hook group for '{event}' must be a JSON object.")
            matcher = addition_group.get("matcher", "")
            matching_group = next(
                (
                    group
                    for group in existing_groups
                    if isinstance(group, dict)
                    and group.get("matcher", "") == matcher
                    and isinstance(group.get("hooks"), list)
                ),
                None,
            )
            if matching_group is None:
                existing_groups.append(addition_group)
                continue
            existing_commands = {
                hook.get("command")
                for hook in matching_group["hooks"]
                if isinstance(hook, dict) and hook.get("command")
            }
            for hook in cast("list[dict[str, Any]]", addition_group.get("hooks", [])):
                if not isinstance(hook, dict):
                    raise ValueError(f"Hook entry for '{event}' must be a JSON object.")
                command = hook.get("command")
                if command in existing_commands:
                    continue
                matching_group["hooks"].append(hook)
                existing_commands.add(command)

    return merged


def _merge_copilot_hooks(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["version"] = 1
    merged_hooks = cast("dict[str, Any]", merged.setdefault("hooks", {}))
    if not isinstance(merged_hooks, dict):
        raise ValueError("Top-level 'hooks' must be a JSON object.")
    addition_hooks = cast("dict[str, Any]", additions.get("hooks", {}))
    if not isinstance(addition_hooks, dict):
        raise ValueError("Managed hook additions must expose a 'hooks' object.")

    for event, addition_entries in addition_hooks.items():
        if not isinstance(addition_entries, list):
            raise ValueError(f"Copilot hook event '{event}' must be a JSON array.")
        existing_entries = cast("list[dict[str, Any]]", merged_hooks.setdefault(event, []))
        if not isinstance(existing_entries, list):
            raise ValueError(f"Copilot hook event '{event}' must be a JSON array.")
        existing_signatures = {
            (
                entry.get("matcher"),
                entry.get("bash"),
                entry.get("command"),
            )
            for entry in existing_entries
            if isinstance(entry, dict)
        }
        for entry in addition_entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Copilot hook entry for '{event}' must be a JSON object.")
            signature = (entry.get("matcher"), entry.get("bash"), entry.get("command"))
            if signature in existing_signatures:
                continue
            existing_entries.append(entry)
            existing_signatures.add(signature)

    return merged


def _merge_managed_registration(
    target: str,
    existing: dict[str, Any],
    additions: dict[str, Any],
) -> dict[str, Any]:
    if _target_surface(target) == "copilot":
        return _merge_copilot_hooks(existing, additions)
    return _merge_grouped_hooks(existing, additions)


def _write_registration_file(config_path: Path, rendered: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(rendered, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _show_available_install_targets(*, cwd: Path, home: Path) -> None:
    p = DryRunPrinter(True)
    p.blank_line()
    p.header("Hook install")
    p.section("Available targets")
    for target_name, resolver in sorted(HOOK_TARGET_PATHS.items()):
        hooks_dir = resolver(cwd, home)
        config_path = _config_path_for_target(target_name, cwd=cwd, home=home)
        try:
            hook_files = _list_hook_files()
        except FileNotFoundError:
            # Skip targets that don't have hook files packaged
            continue
        for filename, _ in hook_files:
            location = _display_path(hooks_dir / filename, cwd=cwd, home=home)
            p.would_install(filename, target_name, location)
        p.would_write(
            _display_path(config_path, cwd=cwd, home=home),
            f"managed hook registration for {target_name}",
        )
    p.blank_line()
    p.footer("pass --target DEST to install (see targets above)")


def cmd_install(args: argparse.Namespace) -> int:
    """Install bundled hook scripts into one or more hook directories."""
    cwd = Path.cwd()
    home = Path.home()
    if not args.targets:
        if args.dry_run:
            _show_available_install_targets(cwd=cwd, home=home)
            return 0
        available = ", ".join(sorted(HOOK_TARGET_PATHS))
        return _emit_install_error(
            f"No --target specified. Pass --target DEST (e.g. --target claude-local). Available: {available}.",
        )

    install_plan = _resolve_install_plan(args.targets, cwd=cwd, home=home)

    p = DryRunPrinter(args.dry_run)
    p.blank_line()
    total_files = sum(len(hook_files) for _, _, hook_files in install_plan)
    p.header(
        "Hook install",
        Files=str(total_files),
        Targets=str(len(install_plan)),
    )

    conflicts: list[tuple[str, str, Path]] = []
    for target_name, hooks_dir, hook_files in install_plan:
        for filename, _ in hook_files:
            destination = hooks_dir / filename
            if destination.exists() and not args.force:
                conflicts.append((target_name, filename, destination))

    if conflicts:
        for target_name, filename, destination in conflicts:
            location = _display_path(destination, cwd=cwd, home=home)
            return _emit_install_error(
                f"{target_name} already has {filename} at {location}. Use --force to overwrite it.",
            )

    if args.dry_run:
        for target_name, hooks_dir, hook_files in install_plan:
            for filename, _ in hook_files:
                destination = hooks_dir / filename
                location = _display_path(destination, cwd=cwd, home=home)
                p.would_install(filename, target_name, location)
            config_path = _config_path_for_target(target_name, cwd=cwd, home=home)
            p.would_write(
                _display_path(config_path, cwd=cwd, home=home),
                f"managed hook registration for {target_name}",
            )
        p.blank_line()
        p.footer("no files were modified")
        return 0

    for target_name, hooks_dir, hook_files in install_plan:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in hook_files:
            destination = hooks_dir / filename
            try:
                destination.write_text(content.rstrip() + "\n", encoding="utf-8")
            except OSError as exc:
                location = _display_path(destination, cwd=cwd, home=home)
                return _emit_install_error(
                    f"Could not install {filename} to {target_name} ({location}): {exc}",
                )
            location = _display_path(destination, cwd=cwd, home=home)
            p.ok(f"Installed {filename} to {target_name}: {location}")

        config_path = _config_path_for_target(target_name, cwd=cwd, home=home)
        try:
            existing = _load_existing_json(config_path)
            managed = _managed_registration_payload(target_name, hooks_dir=hooks_dir)
            merged = _merge_managed_registration(target_name, existing, managed)
            _write_registration_file(config_path, merged)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            location = _display_path(config_path, cwd=cwd, home=home)
            return _emit_install_error(
                f"Could not update hook registration for {target_name} ({location}): {exc}",
            )
        location = _display_path(config_path, cwd=cwd, home=home)
        p.ok(f"Updated hook registration for {target_name}: {location}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the hooks command group."""
    parser = subparsers.add_parser(
        "hooks",
        help="Install bundled rrt user workflow hook scripts and register them.",
        description="Install bundled rrt user workflow hook scripts into one or more local hook directories and update the surface's hook registration JSON.",
        epilog=HOOKS_EXAMPLES,
    )
    hooks_sub = parser.add_subparsers(
        dest="hooks_command",
        metavar="<hooks_command>",
        parser_class=type(parser),
        required=True,
    )

    install_parser = hooks_sub.add_parser(
        "install",
        help="Install bundled rrt hook scripts into hook directories and register them.",
        description="Install bundled rrt user workflow hook .py scripts into one or more local hook directories and update the native hook-registration JSON for that surface.",
        epilog=HOOKS_INSTALL_EXAMPLES,
    )
    install_parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=False,
        choices=sorted(HOOK_TARGET_PATHS),
        metavar="DEST",
        help=(
            "Install target. Repeat to install into multiple locations: "
            "claude-local, claude-global, codex-local, codex-global, "
            "copilot-local, copilot-global, gemini-local, gemini-global."
        ),
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files.",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing hook files.",
    )
    install_parser.set_defaults(handler=cmd_install)
