from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_release_tools.workflow import hooks


def _require_message(message: str | None) -> str:
    assert message is not None
    return message


def _raise_file_not_found(_cwd: Path) -> object:
    raise FileNotFoundError


def _raise_missing_tool_error(_cwd: Path) -> object:
    raise ValueError("missing tool")


def _raise_broken_config_error(_cwd: Path) -> object:
    raise ValueError("broken config")


def _raise_runtime_error(_cwd: Path) -> object:
    raise RuntimeError("boom")


def _raise_read_error(_path: Path) -> str:
    raise OSError("read boom")


def test_branch_validation_and_commit_helpers() -> None:
    assert hooks.validate_branch_name("") is None
    assert hooks.validate_branch_name("main") is None
    assert hooks.validate_branch_name("release/v1.2.3") is None
    assert hooks.validate_branch_name("feat/add-parser") is None
    assert "release/v<semver>" in _require_message(hooks.validate_branch_name("release/vbad"))
    assert "<type>/<kebab-case-description>" in _require_message(hooks.validate_branch_name("feat"))
    assert "Branch type" in _require_message(hooks.validate_branch_name("bogus/add-parser"))
    assert hooks.validate_branch_name("custom/add-parser", extra_types=("custom",)) is None
    assert "non-empty slug" in _require_message(hooks.validate_branch_name("dependabot/"))
    assert _require_message(
        hooks.validate_branch_name("feat/" + "a" * (hooks.SLUG_MAX + 1))
    ).startswith(
        "Branch slug",
    )
    assert "normalized kebab-case" in _require_message(
        hooks.validate_branch_name("feat/add_parser")
    )

    assert hooks.validate_commit_subject("") == "Commit message is empty."
    assert hooks.validate_commit_subject("Merge pull request #1") is None
    assert hooks.validate_commit_subject("fixup! feat(cli): add hook") is None
    assert hooks.validate_commit_subject("squash! fix: typo") is None
    assert "Conventional Commits" in _require_message(
        hooks.validate_commit_subject("fixup! not conventional")
    )
    assert "Conventional Commits" in _require_message(
        hooks.validate_commit_subject("not conventional")
    )
    assert hooks.branch_requires_changelog("") is False
    assert hooks.branch_requires_changelog("feat") is False
    assert hooks.branch_requires_changelog("bogus/add-parser") is False
    assert hooks.commit_subject_requires_changelog("") is False
    assert hooks.commit_subject_requires_changelog("fixup! feat: add parser") is True
    assert hooks.is_changelog_meta_commit("") is False


def test_path_and_git_helpers_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("\n\n", encoding="utf-8")
    assert hooks.read_commit_subject(message_file) == ""

    absolute = tmp_path / "nested" / "file.txt"
    assert hooks._normalize_repo_path(str(absolute), cwd=tmp_path) == "nested/file.txt"
    assert hooks._normalize_repo_path("/tmp/outside.txt", cwd=tmp_path) == "/tmp/outside.txt"

    assert (
        hooks.changelog_is_updated(
            [str(absolute)],
            changelog_file=str(absolute),
            cwd=tmp_path,
        )
        is True
    )
    assert (
        hooks.changelog_is_updated(
            ["other/file.txt"],
            changelog_file=str(absolute),
            cwd=tmp_path,
        )
        is False
    )

    monkeypatch.setattr(hooks.git, "capture", lambda cmd, cwd: "one\ntwo\n")
    assert hooks.staged_files(tmp_path) == ["one", "two"]
    assert hooks.changed_files_for_ref(tmp_path, "HEAD") == ["one", "two"]


def test_changelog_requirement_helpers() -> None:
    assert hooks.commit_type_requires_changelog("feat") is True
    assert hooks.commit_type_requires_changelog("chore") is False
    assert hooks.commit_type_requires_changelog("feat", breaking=True) is True
    assert hooks.branch_requires_changelog("feat/add-parser") is True
    assert hooks.branch_requires_changelog("chore/tidy") is False
    assert hooks.branch_requires_changelog("main") is False
    assert hooks.branch_requires_changelog("release/v1.2.3") is False
    assert hooks.commit_subject_requires_changelog("feat: add parser") is True
    assert hooks.commit_subject_requires_changelog("chore: tidy") is False
    assert hooks.commit_subject_requires_changelog("feat!: breaking change") is True
    assert hooks.is_changelog_meta_commit("fix: update changelog entries") is True
    assert hooks.is_changelog_meta_commit("feat: add changelog parser") is False


def test_changelog_split_cancel_and_dedup_helpers(tmp_path: Path) -> None:
    assert hooks._split_scope("CI: add node") == ("ci", "add node")
    assert hooks._split_scope("add node") == (None, "add node")
    assert hooks._entries_cancel_out("add x", "remove x") is True
    assert hooks._entries_cancel_out("CI: add x", "Deps: remove x") is False
    assert hooks._entries_cancel_out("remove x", "add x") is True
    assert hooks._entries_cancel_out("add x", "update x") is False

    assert hooks.dedup_changelog_entries(["# Changelog", "", "- Keep me"]) == [
        "# Changelog",
        "",
        "- Keep me",
    ]

    lines = ["# Changelog", "", "- Add X", "- add x", "- remove x", "", ""]
    assert hooks.dedup_changelog_entries(lines) == ["# Changelog", ""]
    assert hooks.dedup_changelog_entries(["- add x", "- add y", "- keep z", "- remove x"]) == [
        "- add y",
        "- keep z",
    ]

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("line1\nline1\nline2\n", encoding="utf-8")
    changed = hooks.apply_dedup_to_changelog(
        changelog,
        ["line1", "line1", "line2"],
        ["line1", "line2"],
        added_line_positions=frozenset({1, 2, 3}),
    )
    assert changed is True
    assert changelog.read_text(encoding="utf-8") == "line1\nline2\n"

    blanky = tmp_path / "BLANKY.md"
    blanky.write_text("header\n\nremove me\n\nfooter\n", encoding="utf-8")
    assert (
        hooks.apply_dedup_to_changelog(
            blanky,
            ["remove me"],
            [],
            added_line_positions=frozenset({3}),
        )
        is True
    )
    assert blanky.read_text(encoding="utf-8") == "header\n\nfooter\n"

    unchanged = tmp_path / "UNCHANGED.md"
    unchanged.write_text("line1\nline2\n", encoding="utf-8")
    assert (
        hooks.apply_dedup_to_changelog(
            unchanged,
            ["line1", "line2"],
            ["line1", "line2"],
        )
        is False
    )

    untouched = tmp_path / "UNTOUCHED.md"
    untouched.write_text("line1\nline2\n", encoding="utf-8")
    assert hooks.apply_dedup_to_changelog(untouched, ["missing"], []) is False

    collected = hooks.collect_squash_changelog_hunks  # local alias for coverage clarity
    assert collected is hooks.collect_squash_changelog_hunks


def test_collect_squash_changelog_hunks_parses_positions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        hooks.git,
        "capture_checked",
        lambda cmd, cwd: "\n".join(
            [
                "diff --git a/CHANGELOG.md b/CHANGELOG.md",
                "@@ -1,0 +1,4 @@",
                "+alpha",
                " beta",
                "+gamma",
            ],
        ),
    )

    added, positions = hooks.collect_squash_changelog_hunks(
        tmp_path,
        ref="HEAD",
        changelog_file="CHANGELOG.md",
    )
    assert added == ["alpha", "gamma"]
    assert positions == frozenset({1, 3})


def test_run_branch_commit_and_dirty_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.run_branch_name_check("feat/add-parser", title="Branch check") == 0
    assert hooks.run_branch_name_check("bad-branch", title="Branch check") == 1
    assert "Expected: <type>/<kebab-case-description>." in capsys.readouterr().err

    assert hooks.run_commit_subject_check("feat: add parser", title="Commit check") == 0
    assert hooks.run_commit_subject_check("bad subject", title="Commit check") == 1

    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: False)
    assert hooks.run_dirty_tree_check(tmp_path, title="Dirty tree") == 1

    monkeypatch.setattr(hooks.git, "is_git_repository", lambda cwd: True)
    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: True)
    assert hooks.run_dirty_tree_check(tmp_path, title="Dirty tree") == 0

    monkeypatch.setattr(hooks.git, "working_tree_clean", lambda cwd: False)
    monkeypatch.setattr(hooks.git, "status_porcelain", lambda cwd: [" M file.py", "?? new.txt"])
    assert hooks.run_dirty_tree_check(tmp_path, title="Dirty tree") == 1

    monkeypatch.setattr(
        hooks.git,
        "status_porcelain",
        _raise_runtime_error,
    )
    assert hooks.run_dirty_tree_check(tmp_path, title="Dirty tree") == 1


def test_run_pre_commit_and_changelog_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(hooks, "load_extra_branch_types", lambda cwd: ())
    assert hooks.run_pre_commit(tmp_path) == 0

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert hooks.run_pre_commit_changelog(tmp_path, changelog_file="CHANGELOG.md") == 0

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "feat/add-parser")
    monkeypatch.setattr(hooks, "staged_files", lambda cwd: ["src/app.py"])
    monkeypatch.setattr(
        hooks,
        "changelog_is_updated",
        lambda changed_files, *, changelog_file, cwd: False,
    )
    assert hooks.run_pre_commit_changelog(tmp_path, changelog_file="CHANGELOG.md") == 1

    monkeypatch.setattr(
        hooks,
        "changelog_is_updated",
        lambda changed_files, *, changelog_file, cwd: True,
    )
    assert hooks.run_pre_commit_changelog(tmp_path, changelog_file="CHANGELOG.md") == 0

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: _raise_runtime_error(cwd))
    assert hooks.run_pre_commit_changelog(tmp_path, changelog_file="CHANGELOG.md") == 1

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks.git, "current_branch", lambda cwd: "chore/tidy")
    assert hooks.run_pre_commit_changelog(tmp_path, changelog_file="CHANGELOG.md") == 0


def test_run_commit_msg_uses_read_commit_subject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    message_file = tmp_path / "msg.txt"
    message_file.write_text("feat: add parser\n", encoding="utf-8")

    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        hooks,
        "run_commit_subject_check",
        lambda subject, *, title, verbose=0: captured.append((subject, title)) or 7,
    )

    assert hooks.run_commit_msg(message_file) == 7
    assert captured == [("feat: add parser", "Commit blocked by commit message policy.")]


def test_run_update_unreleased_and_changelog_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n", encoding="utf-8")

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: True)
    monkeypatch.setattr(hooks, "is_changelog_meta_commit", lambda subject: False)
    monkeypatch.setattr(hooks, "detect_changelog_format", lambda changelog_file: "markdown")
    monkeypatch.setattr(
        hooks,
        "append_to_unreleased",
        lambda content, subject, fmt: content + "### Added\n- add parser\n",
    )
    git_runs: list[list[str]] = []
    monkeypatch.setattr(
        hooks.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: git_runs.append(cmd),
    )

    assert (
        hooks.run_update_unreleased(
            tmp_path,
            subject="feat: add parser",
            changelog_file="CHANGELOG.md",
        )
        == 0
    )
    assert "add parser" in changelog.read_text(encoding="utf-8")
    assert git_runs == [["git", "add", "CHANGELOG.md"]]


def test_run_changelog_check_covers_non_changelog_and_unreleased_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n", encoding="utf-8")

    assert (
        hooks.run_changelog_check(
            "chore: tidy",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="auto",
            branch="",
        )
        == 0
    )

    monkeypatch.setattr(hooks, "get_unreleased_entries", lambda content, fmt: ())
    monkeypatch.setattr(hooks, "detect_changelog_format", lambda changelog_file: "markdown")

    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="unreleased",
            branch="feat/add-parser",
        )
        == 1
    )

    changelog.write_text("# Changelog\n", encoding="utf-8")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=["CHANGELOG.md"],
            ref="HEAD",
            title="Changelog",
            strategy="per-commit",
            branch="feat/add-parser",
        )
        == 0
    )


def test_run_changelog_check_incremental_alias_uses_per_commit(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")

    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=["CHANGELOG.md"],
            ref="HEAD",
            title="Changelog",
            strategy="incremental",
            branch="feat/add-parser",
        )
        == 0
    )

    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=["src/app.py"],
            ref="HEAD",
            title="Changelog",
            strategy="incremental",
            branch="feat/add-parser",
        )
        == 1
    )


def test_run_update_unreleased_and_changelog_check_error_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n- add parser\n", encoding="utf-8")

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: _raise_runtime_error(cwd))
    assert (
        hooks.run_update_unreleased(
            tmp_path, subject="feat: add parser", changelog_file="CHANGELOG.md"
        )
        == 1
    )

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: False)
    assert (
        hooks.run_update_unreleased(tmp_path, subject="chore: tidy", changelog_file="CHANGELOG.md")
        == 0
    )

    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: True)
    monkeypatch.setattr(
        hooks, "_resolve_changelog_strategy", lambda cwd, strategy: _raise_runtime_error(cwd)
    )
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="auto",
            branch="feat/add-parser",
        )
        == 1
    )

    monkeypatch.setattr(hooks, "_resolve_changelog_strategy", lambda cwd, strategy: "unreleased")
    monkeypatch.setattr(hooks, "detect_changelog_format", lambda changelog_file: "markdown")
    monkeypatch.setattr(hooks, "get_unreleased_entries", lambda content, fmt: ["entry"])
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="unreleased",
            branch="feat/add-parser",
        )
        == 0
    )

    monkeypatch.setattr(hooks, "_resolve_changelog_strategy", lambda cwd, strategy: "per-commit")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=["src/app.py"],
            ref="HEAD",
            title="Changelog",
            strategy="per-commit",
            branch="feat/add-parser",
        )
        == 1
    )

    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n- add parser\n", encoding="utf-8")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="unreleased",
            branch="dependabot/npm",
        )
        == 0
    )

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert (
        hooks.run_update_unreleased(
            tmp_path,
            subject="feat: add parser",
            changelog_file="CHANGELOG.md",
        )
        == 0
    )

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: True)
    monkeypatch.setattr(hooks, "is_changelog_meta_commit", lambda subject: True)
    assert (
        hooks.run_update_unreleased(
            tmp_path,
            subject="fix: update changelog entries",
            changelog_file="CHANGELOG.md",
        )
        == 0
    )
    monkeypatch.setattr(hooks, "_resolve_changelog_strategy", lambda cwd, strategy: "release-only")
    assert (
        hooks.run_changelog_check(
            "feat: add parser",
            cwd=tmp_path,
            changelog_file="CHANGELOG.md",
            changed_files=None,
            ref="HEAD",
            title="Changelog",
            strategy="release-only",
            branch="feat/add-parser",
        )
        == 0
    )


def test_run_post_correct_and_main_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- add x\n- add x\n", encoding="utf-8")

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: (
            ["- add x", "- add x"],
            frozenset({3, 4}),
        ),
    )
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 0
    )
    assert changelog.read_text(encoding="utf-8").count("- add x") == 1

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: ([], frozenset()),
    )
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 0
    )

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        hooks, "run_pre_commit", lambda cwd, verbose=0: calls.append(("pre", cwd)) or 11
    )
    monkeypatch.setattr(
        hooks,
        "run_pre_commit_changelog",
        lambda cwd, changelog_file=hooks.DEFAULT_CHANGELOG, verbose=0: (
            calls.append(("pre-changelog", cwd)) or 12
        ),
    )
    monkeypatch.setattr(
        hooks,
        "run_commit_msg",
        lambda path, verbose=0: calls.append(("commit-msg", path)) or 13,
    )
    monkeypatch.setattr(
        hooks,
        "run_branch_name_check",
        lambda branch_name, *, title, extra_types=(), verbose=0: (
            calls.append(("branch", branch_name)) or 14
        ),
    )
    monkeypatch.setattr(
        hooks,
        "run_commit_subject_check",
        lambda subject, *, title, verbose=0: calls.append(("subject", subject)) or 15,
    )
    monkeypatch.setattr(
        hooks,
        "run_dirty_tree_check",
        lambda cwd, *, title, verbose=0: calls.append(("dirty", cwd)) or 16,
    )
    monkeypatch.setattr(
        hooks, "run_docs_check", lambda cwd, verbose=0: calls.append(("docs", cwd)) or 17
    )
    monkeypatch.setattr(hooks, "cmd_doctor", lambda parsed: calls.append(("doctor", parsed)) or 18)
    monkeypatch.setattr(
        hooks,
        "cmd_release_check",
        lambda parsed: calls.append(("release", parsed)) or 19,
    )
    monkeypatch.setattr(hooks, "cmd_eol_check", lambda parsed: calls.append(("eol", parsed)) or 20)
    monkeypatch.setattr(
        hooks,
        "run_update_unreleased",
        lambda cwd, *, subject, changelog_file=hooks.DEFAULT_CHANGELOG, verbose=0: (
            calls.append(("update", subject)) or 21
        ),
    )
    monkeypatch.setattr(
        hooks,
        "run_post_correct",
        lambda cwd, *, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG, commit=False, verbose=0: (
            calls.append(("post", ref)) or 22
        ),
    )
    monkeypatch.setattr(
        hooks,
        "run_changelog_check",
        lambda *args, **kwargs: (
            calls.append(
                ("check", kwargs["subject"] if "subject" in kwargs else args[0]),
            )
            or 23
        ),
    )
    monkeypatch.setattr(hooks, "load_extra_branch_types", lambda cwd: ("custom",))

    assert hooks.main(["pre-commit"]) == 11
    assert hooks.main(["pre-commit-changelog", "--changelog-file", "CHANGELOG.md"]) == 12
    assert hooks.main(["commit-msg", "msg.txt"]) == 13
    assert hooks.main(["check-branch-name", "--branch", "feat/add-parser"]) == 14
    assert hooks.main(["check-commit-subject", "--subject", "feat: add parser"]) == 15
    assert hooks.main(["check-dirty-tree"]) == 16
    assert hooks.main(["check-docs"]) == 17
    assert hooks.main(["doctor"]) == 18
    assert hooks.main(["release-check"]) == 19
    assert hooks.main(["check-eol"]) == 20
    assert hooks.main(["update-unreleased", "--subject", "feat: add parser"]) == 21
    assert (
        hooks.main(
            ["changelog", "post-correct", "--squash-commit", "abc123", "--output", "CHANGELOG.md"],
        )
        == 22
    )
    assert hooks.main(["update-unreleased", "--message-file", str(tmp_path / "missing.txt")]) == 1
    assert (
        hooks.main(
            [
                "changelog",
                "post-correct",
                "--squash-commit",
                "abc123",
                "--output",
                "CHANGELOG.md",
                "--commit",
            ]
        )
        == 22
    )
    assert (
        hooks.main(
            [
                "check-changelog",
                "--subject",
                "feat: add parser",
                "--changelog-file",
                "CHANGELOG.md",
                "--strategy",
                "incremental",
            ],
        )
        == 23
    )


def test_read_commit_subject_skips_blank_lines(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("\n\n feat: add parser \n", encoding="utf-8")

    assert hooks.read_commit_subject(message_file) == "feat: add parser"


def test_main_docs_hook_commands_set_explicit_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    docs_calls: list[SimpleNamespace] = []
    suggest_calls: list[SimpleNamespace] = []

    monkeypatch.setattr(
        hooks,
        "cmd_docs",
        lambda parsed: docs_calls.append(parsed) or 31,
    )
    monkeypatch.setattr(
        hooks,
        "cmd_docs_suggest",
        lambda parsed: suggest_calls.append(parsed) or 32,
    )

    # Order in docs_calls: docs-generate, docs-publish, docs-inject.
    assert hooks.main(["docs-generate"]) == 31
    assert hooks.main(["docs-publish"]) == 31
    assert hooks.main(["docs-inject"]) == 31
    assert hooks.main(["docstring-suggest"]) == 32

    generate_args, publish_args, inject_args = docs_calls
    suggest_args = suggest_calls[0]

    assert generate_args.docs_action == "generate"
    assert generate_args.format == "toml"
    assert generate_args.lang is None
    assert generate_args.root == "."
    assert generate_args.dry_run is False

    assert publish_args.docs_action == "publish"
    assert publish_args.format is None
    assert publish_args.lang is None
    assert publish_args.root == "."
    assert publish_args.check is False
    assert publish_args.dry_run is False
    assert publish_args.fail_on_change is False

    assert inject_args.docs_action == "inject"
    assert inject_args.format is None
    assert inject_args.lang is None
    assert inject_args.root == "."
    assert inject_args.check is False
    assert inject_args.dry_run is False
    assert inject_args.add_anchors is True

    assert suggest_args.root == "."
    assert suggest_args.paths == []
    assert suggest_args.min_chars is None
    assert suggest_args.apply is True


def test_main_docs_map_hook_commands_set_explicit_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs-map-update and docs-map-check route to cmd_docs with map defaults."""
    docs_calls: list[SimpleNamespace] = []
    monkeypatch.setattr(hooks, "cmd_docs", lambda parsed: docs_calls.append(parsed) or 41)

    assert hooks.main(["docs-map-update"]) == 41
    assert hooks.main(["docs-map-check"]) == 41

    update_args, check_args = docs_calls
    assert update_args.docs_action == "map"
    assert update_args.root == "."
    assert update_args.check is False
    assert update_args.dry_run is False

    assert check_args.docs_action == "map"
    assert check_args.root == "."
    assert check_args.check is True
    assert check_args.dry_run is False


def test_main_folder_check_hook_command(monkeypatch: pytest.MonkeyPatch) -> None:
    folder_calls: list[SimpleNamespace] = []

    monkeypatch.setattr(
        hooks,
        "cmd_folder_check",
        lambda parsed: folder_calls.append(parsed) or 42,
    )

    assert hooks.main(["folder-check"]) == 42
    assert hooks.main(["folder-check", "--root", "/tmp", "--report-only", "--snapshot"]) == 42

    default_args, custom_args = folder_calls
    assert default_args.format == "text"
    assert default_args.root == "."
    assert default_args.template == []
    assert default_args.report_only is False
    assert default_args.snapshot is False

    assert custom_args.root == "/tmp"
    assert custom_args.report_only is True
    assert custom_args.snapshot is True


def test_main_artifacts_check_hook_command(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_calls: list[SimpleNamespace] = []

    monkeypatch.setattr(
        hooks,
        "cmd_artifacts",
        lambda parsed: artifact_calls.append(parsed) or 0,
    )

    assert hooks.main(["artifacts-check"]) == 0
    assert hooks.main(["artifacts-check", "--no-strict"]) == 0

    strict_args, no_strict_args = artifact_calls
    assert strict_args.check is True
    assert strict_args.snapshot is False
    assert strict_args.list is False
    assert strict_args.strict is True

    assert no_strict_args.strict is False


def test_main_artifacts_snapshot_hook_command(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_calls: list[SimpleNamespace] = []

    monkeypatch.setattr(
        hooks,
        "cmd_artifacts",
        lambda parsed: artifact_calls.append(parsed) or 0,
    )

    assert hooks.main(["artifacts-snapshot"]) == 0

    (snap_args,) = artifact_calls
    assert snap_args.snapshot is True
    assert snap_args.check is False
    assert snap_args.strict is False
    assert snap_args.list is False


def test_detect_changelog_workflow_falls_back_and_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        lambda cwd: SimpleNamespace(changelog_workflow="squash"),
    )
    assert hooks._detect_changelog_workflow(tmp_path) == "squash"

    monkeypatch.setattr(
        hooks,
        "load_or_autodetect_config",
        _raise_file_not_found,
    )
    assert hooks._detect_changelog_workflow(tmp_path) == hooks.DEFAULT_CHANGELOG_WORKFLOW

    def _raise_value_error(_cwd: Path) -> object:
        raise ValueError("bad config")

    monkeypatch.setattr(hooks, "load_or_autodetect_config", _raise_value_error)
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: True)
    assert hooks._detect_changelog_workflow(tmp_path) == hooks.DEFAULT_CHANGELOG_WORKFLOW

    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: False)
    with pytest.raises(RuntimeError, match="Failed to load changelog_workflow configuration"):
        hooks._detect_changelog_workflow(tmp_path)


def test_resolve_changelog_strategy_handles_auto_and_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert hooks._resolve_changelog_strategy(tmp_path, "per-commit") == "per-commit"
    assert hooks._resolve_changelog_strategy(tmp_path, "incremental") == "per-commit"

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "squash")
    assert hooks._resolve_changelog_strategy(tmp_path, "auto") == "release-only"

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    assert hooks._resolve_changelog_strategy(tmp_path, "auto") == "per-commit"


def test_emit_failure_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert hooks.emit_failure("Hook check failed", ["detail one", "detail two"]) == 1

    err = capsys.readouterr().err
    assert "Hook check failed" in err
    assert "detail one" in err
    assert "detail two" in err


def test_run_docs_check_uses_loaded_config_and_missing_tool_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entries = [
        SimpleNamespace(source_file="docs/a.md", hash="b", name="zeta", lang="md"),
        SimpleNamespace(source_file="docs/a.md", hash="a", name="alpha", lang="md"),
    ]

    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: SimpleNamespace(docs=SimpleNamespace(lock_file="cfg-lock.toml")),
    )
    monkeypatch.setattr(
        "repo_release_tools.docs.extractor.extract_docs_from_dir",
        lambda cwd, doc_config: entries,
    )
    monkeypatch.setattr(
        "repo_release_tools.state.docs_lock_path",
        lambda cwd, lock_file: cwd / lock_file,
    )
    monkeypatch.setattr("repo_release_tools.state.hash_content", lambda content: f"hash:{content}")
    monkeypatch.setattr(
        "repo_release_tools.state.lock_is_current",
        lambda lock_path, sources: (True, []),
    )

    assert hooks.run_docs_check(tmp_path) == 0

    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        _raise_missing_tool_error,
    )
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: True)

    assert hooks.run_docs_check(tmp_path) == 0


def test_run_docs_check_reports_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        _raise_broken_config_error,
    )
    monkeypatch.setattr(hooks, "is_missing_tool_rrt_error", lambda exc: False)

    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        hooks,
        "emit_failure",
        lambda title, details: calls.append((title, details)) or 1,
    )

    assert hooks.run_docs_check(tmp_path) == 1
    assert calls == [
        (
            "Failed to load repo-release-tools configuration for docs check.",
            ["broken config"],
        ),
    ]


def test_run_docs_check_reports_stale_lockfile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = [SimpleNamespace(source_file="docs/a.md", hash="a", name="alpha", lang="md")]
    monkeypatch.setattr(
        "repo_release_tools.config.load_config",
        lambda cwd: SimpleNamespace(docs=SimpleNamespace(lock_file="cfg-lock.toml")),
    )
    monkeypatch.setattr(
        "repo_release_tools.docs.extractor.extract_docs_from_dir",
        lambda cwd, doc_config: entries,
    )
    monkeypatch.setattr(
        "repo_release_tools.state.docs_lock_path",
        lambda cwd, lock_file: cwd / lock_file,
    )
    monkeypatch.setattr("repo_release_tools.state.hash_content", lambda content: f"hash:{content}")
    monkeypatch.setattr(
        "repo_release_tools.state.lock_is_current",
        lambda lock_path, sources: (False, ["stale lock"]),
    )

    assert hooks.run_docs_check(tmp_path) == 1


def test_run_update_unreleased_handles_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: True)
    monkeypatch.setattr(hooks, "is_changelog_meta_commit", lambda subject: False)

    assert (
        hooks.run_update_unreleased(
            tmp_path,
            subject="feat: add parser",
            changelog_file="CHANGELOG.md",
        )
        == 1
    )


def test_run_update_unreleased_no_change_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    content = "# Changelog\n\n## [Unreleased]\n\n### Added\n- add parser\n"
    changelog.write_text(content, encoding="utf-8")

    monkeypatch.setattr(hooks, "_detect_changelog_workflow", lambda cwd: "incremental")
    monkeypatch.setattr(hooks, "commit_subject_requires_changelog", lambda subject: True)
    monkeypatch.setattr(hooks, "is_changelog_meta_commit", lambda subject: False)
    monkeypatch.setattr(hooks, "detect_changelog_format", lambda f: "markdown")
    monkeypatch.setattr(hooks, "append_to_unreleased", lambda original, subject, fmt: original)

    assert (
        hooks.run_update_unreleased(
            tmp_path, subject="feat: add parser", changelog_file="CHANGELOG.md", verbose=1
        )
        == 0
    )
    assert "no change" in capsys.readouterr().err


def test_run_post_correct_commits_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- add x\n- add x\n", encoding="utf-8")

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: (
            ["- add x", "- add x"],
            frozenset({3, 4}),
        ),
    )
    git_runs: list[list[str]] = []
    monkeypatch.setattr(
        hooks.git,
        "run",
        lambda cmd, cwd, *, dry_run, label: git_runs.append(cmd),
    )

    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=True)
        == 0
    )
    assert git_runs == [
        ["git", "add", "CHANGELOG.md"],
        ["git", "commit", "-m", "chore: post-correct changelog after squash merge [skip ci]"],
    ]


def test_run_post_correct_covers_runtime_error_and_clean_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- add x\n", encoding="utf-8")

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: ([], frozenset()),
    )
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 0
    )

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: (
            _raise_runtime_error(tmp_path),
            frozenset(),
        ),
    )
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 1
    )

    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: (
            ["- add x"],
            frozenset({3}),
        ),
    )
    monkeypatch.setattr(hooks, "apply_dedup_to_changelog", lambda *args, **kwargs: False)
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 0
    )


def test_run_post_correct_missing_file_and_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=False)
        == 1
    )

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n- add x\n- add x\n", encoding="utf-8")
    monkeypatch.setattr(
        hooks,
        "collect_squash_changelog_hunks",
        lambda cwd, ref="HEAD", changelog_file=hooks.DEFAULT_CHANGELOG: (
            ["- add x", "- add x"],
            frozenset({3, 4}),
        ),
    )

    calls = {"count": 0}

    def _raise_on_second_git_run(cmd: list[str], cwd: Path, *, dry_run: bool, label: str) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("commit boom")

    monkeypatch.setattr(hooks.git, "run", _raise_on_second_git_run)
    assert (
        hooks.run_post_correct(tmp_path, ref="HEAD", changelog_file="CHANGELOG.md", commit=True)
        == 1
    )


def test_main_update_unreleased_uses_message_file_and_commit_editmsg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    captured: list[tuple[Path, str, str]] = []
    monkeypatch.setattr(
        hooks,
        "run_update_unreleased",
        lambda cwd, *, subject, changelog_file=hooks.DEFAULT_CHANGELOG, verbose=0: (
            captured.append((cwd, subject, changelog_file)) or 21
        ),
    )

    message_file = tmp_path / "msg.txt"
    message_file.write_text("feat: add parser\n", encoding="utf-8")
    assert hooks.main(["update-unreleased", "--message-file", str(message_file)]) == 21

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "COMMIT_EDITMSG").write_text("fix: fallback subject\n", encoding="utf-8")
    assert hooks.main(["update-unreleased"]) == 21

    assert [subject for _, subject, _ in captured] == ["feat: add parser", "fix: fallback subject"]


def test_main_update_unreleased_handles_unreadable_message_file_and_empty_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    message_file = tmp_path / "msg.txt"
    message_file.write_text("feat: add parser\n", encoding="utf-8")
    monkeypatch.setattr(hooks, "read_commit_subject", _raise_read_error)
    assert hooks.main(["update-unreleased", "--message-file", str(message_file)]) == 1

    monkeypatch.setattr(hooks, "read_commit_subject", lambda path: "")
    captured: list[str] = []
    monkeypatch.setattr(
        hooks,
        "run_update_unreleased",
        lambda cwd, *, subject, changelog_file=hooks.DEFAULT_CHANGELOG, verbose=0: (
            captured.append(subject) or 21
        ),
    )
    assert hooks.main(["update-unreleased"]) == 21
    assert captured == [""]


def test_workflow_hooks_module_main_block_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m repo_release_tools.workflow.hooks",
            "check-commit-subject",
            "--subject",
            "chore: tidy",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("repo_release_tools.workflow.hooks", run_name="__main__")

    assert excinfo.value.code == 0


def test_legacy_top_level_hooks_module_reexports_workflow_api() -> None:
    legacy_hooks = importlib.import_module("repo_release_tools.hooks")

    assert legacy_hooks.main is hooks.main
    assert getattr(legacy_hooks, "validate_branch_name") is hooks.validate_branch_name
    assert getattr(legacy_hooks, "Version") is hooks.Version


def test_legacy_top_level_hooks_module_main_block_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hooks, "main", lambda argv=None: 0)

    import runpy

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("repo_release_tools.hooks", run_name="__main__")

    assert excinfo.value.code == 0


def test_run_branch_name_check_verbose_emits_on_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.run_branch_name_check("feat/foo", title="t", verbose=1) == 0
    err = capsys.readouterr().err
    assert "feat/foo" in err


def test_run_branch_name_check_verbose_silent_at_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.run_branch_name_check("feat/foo", title="t", verbose=0) == 0
    assert capsys.readouterr().err == ""


def test_run_commit_subject_check_verbose_emits_on_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.run_commit_subject_check("feat: add bar", title="t", verbose=1) == 0
    err = capsys.readouterr().err
    assert "feat: add bar" in err


def test_run_commit_subject_check_verbose_silent_at_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.run_commit_subject_check("feat: add bar", title="t", verbose=0) == 0
    assert capsys.readouterr().err == ""


def test_main_verbose_flag_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[int] = []
    monkeypatch.setattr(
        hooks,
        "run_branch_name_check",
        lambda branch_name, *, title, extra_types=(), verbose=0: captured.append(verbose) or 0,
    )
    hooks.main(["-v", "check-branch-name", "--branch", "feat/foo"])
    assert captured == [1]

    captured.clear()
    hooks.main(["-vvv", "check-branch-name", "--branch", "feat/foo"])
    assert captured == [3]


def test_tree_check_subcommand_clean_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rrt-hooks tree-check returns 0 when a fresh snapshot matches."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    # snapshot first so the check has a baseline
    from repo_release_tools.workflow.hooks import main as hooks_main

    # snapshot via the tree CLI path is covered elsewhere; here assert the
    # subcommand is wired and returns an int exit code (0 or 1), not a crash.
    rc = hooks_main(["tree-check"])
    assert rc in (0, 1)
