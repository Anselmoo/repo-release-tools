"""Validators and entrypoints for branch, commit, and changelog policy checks."""

from __future__ import annotations

import argparse
import re
import sys

from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.changelog import SECTION_MAP, parse_conventional_commit
from repo_release_tools.config import DEFAULT_CHANGELOG
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, SLUG_MAX, normalize_commit_type
from repo_release_tools.versioning import Version


ALLOWED_BRANCH_NAMES = ("main", "master", "develop")
MAGIC_BRANCH_TYPES = ("claude", "codex", "copilot")
ALLOWED_BRANCH_TYPES = (*CONVENTIONAL_TYPES, *MAGIC_BRANCH_TYPES)
BRANCH_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_branch_name(branch_name: str) -> str | None:
    """Validate the current branch name."""
    if not branch_name:
        return None

    if branch_name in ALLOWED_BRANCH_NAMES:
        return None

    if branch_name.startswith("release/v"):
        version = branch_name.removeprefix("release/v")
        try:
            Version.parse(version)
        except ValueError:
            return f"Release branch {branch_name!r} must use release/v<semver>."
        return None

    if "/" not in branch_name:
        return f"Branch {branch_name!r} must use <type>/<kebab-case-description>."

    type_part, slug = branch_name.split("/", 1)
    if type_part not in MAGIC_BRANCH_TYPES:
        try:
            normalize_commit_type(type_part)
        except argparse.ArgumentTypeError:
            allowed = ", ".join(ALLOWED_BRANCH_TYPES)
            return f"Branch type {type_part!r} is invalid. Choose one of: {allowed}."

    if len(slug) > SLUG_MAX:
        return f"Branch slug {slug!r} is too long ({len(slug)} > {SLUG_MAX})."

    if not BRANCH_SLUG_RE.fullmatch(slug):
        return (
            f"Branch slug {slug!r} must be normalized kebab-case using only lowercase "
            "letters, digits, and hyphens."
        )

    return None


def read_commit_subject(message_file: Path) -> str:
    """Read the first non-empty line from a commit message file."""
    for line in message_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def validate_commit_subject(subject: str) -> str | None:
    """Validate a commit subject against the project's conventional commit rules."""
    if not subject:
        return "Commit message is empty."

    if subject.startswith("Merge "):
        return None

    if subject.startswith(("fixup! ", "squash! ")):
        _, _, rewritten = subject.partition(" ")
        if parse_conventional_commit(rewritten) is not None:
            return None

    if parse_conventional_commit(subject) is not None:
        return None

    allowed = ", ".join((*CONVENTIONAL_TYPES, "deps"))
    return (
        "Commit subject must follow Conventional Commits, for example "
        f"'feat(cli): add hook installer'. Allowed types: {allowed}."
    )


def _parse_subject_for_changelog(subject: str):
    """Parse a commit subject while tolerating fixup and squash prefixes."""
    candidate = subject
    if candidate.startswith(("fixup! ", "squash! ")):
        _, _, candidate = candidate.partition(" ")
    return parse_conventional_commit(candidate)


def commit_type_requires_changelog(commit_type: str, *, breaking: bool = False) -> bool:
    """Return whether a conventional commit type should update the changelog."""
    if breaking:
        return True
    section = SECTION_MAP.get(commit_type.lower())
    return section is not None and section != "Maintenance"


def branch_requires_changelog(branch_name: str) -> bool:
    """Return whether a branch type should stage a changelog update."""
    if not branch_name or branch_name in ALLOWED_BRANCH_NAMES or branch_name.startswith("release/v"):
        return False
    if "/" not in branch_name:
        return False

    type_part, _ = branch_name.split("/", 1)
    try:
        normalized_type = normalize_commit_type(type_part)
    except argparse.ArgumentTypeError:
        return False
    return commit_type_requires_changelog(normalized_type)


def commit_subject_requires_changelog(subject: str) -> bool:
    """Return whether a commit subject should include a changelog update."""
    parsed = _parse_subject_for_changelog(subject)
    if parsed is None:
        return False
    return commit_type_requires_changelog(parsed.type, breaking=parsed.breaking)


def _normalize_repo_path(path: str, *, cwd: Path) -> str:
    """Normalize a path for comparisons against git output."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(cwd)
        except ValueError:
            pass
    normalized = candidate.as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def staged_files(cwd: Path) -> list[str]:
    """Return staged files for the current index."""
    out = git.capture(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files_for_ref(cwd: Path, ref: str) -> list[str]:
    """Return files changed by a single git ref, typically HEAD."""
    out = git.capture(["git", "diff-tree", "--no-commit-id", "--name-only", "--root", "-r", ref], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def changelog_is_updated(changed_files: list[str], *, changelog_file: str, cwd: Path) -> bool:
    """Return whether the changelog file is included in the changed files."""
    target = _normalize_repo_path(changelog_file, cwd=cwd)
    return any(_normalize_repo_path(path, cwd=cwd) == target for path in changed_files)


def emit_failure(title: str, details: list[str]) -> int:
    """Render a hook failure message and return a non-zero exit code."""
    print(output.warning(title, indent=0), file=sys.stderr)
    for detail in details:
        print(output.status(output.GLYPHS.bullet.dot, detail), file=sys.stderr)
    return 1


def run_branch_name_check(branch_name: str, *, title: str) -> int:
    """Validate an explicit branch name."""
    problem = validate_branch_name(branch_name)
    if problem is None:
        return 0

    return emit_failure(
        title,
        [
            problem,
            "Expected: <type>/<kebab-case-description>.",
            (
                "Allowed types: "
                f"{', '.join(ALLOWED_BRANCH_TYPES)} "
                "(including AI helper branches: claude, codex, copilot)."
            ),
            f"Also allowed: {', '.join(ALLOWED_BRANCH_NAMES)}, release/v<semver>.",
        ],
    )


def run_commit_subject_check(subject: str, *, title: str) -> int:
    """Validate an explicit commit subject."""
    problem = validate_commit_subject(subject)
    if problem is None:
        return 0

    return emit_failure(
        title,
        [
            problem,
            f"Found subject: {subject!r}.",
        ],
    )


def run_pre_commit(cwd: Path) -> int:
    """Validate the active branch during pre-commit."""
    branch_name = git.current_branch(cwd)
    return run_branch_name_check(
        branch_name,
        title="Commit blocked by branch naming policy.",
    )


def run_pre_commit_changelog(cwd: Path, *, changelog_file: str = DEFAULT_CHANGELOG) -> int:
    """Validate staged changelog updates during pre-commit."""
    branch_name = git.current_branch(cwd)
    if not branch_requires_changelog(branch_name):
        return 0

    changed_files = staged_files(cwd)
    if changelog_is_updated(changed_files, changelog_file=changelog_file, cwd=cwd):
        return 0

    normalized_path = _normalize_repo_path(changelog_file, cwd=cwd)
    return emit_failure(
        "Commit blocked by changelog policy.",
        [
            f"Branch {branch_name!r} requires a staged changelog update.",
            f"Stage {normalized_path} before committing.",
            f"Currently staged files: {', '.join(changed_files) if changed_files else '<none>'}.",
        ],
    )


def run_commit_msg(message_path: Path) -> int:
    """Validate the commit subject during commit-msg."""
    subject = read_commit_subject(message_path)
    return run_commit_subject_check(
        subject,
        title="Commit blocked by commit message policy.",
    )


def run_changelog_check(
    subject: str,
    *,
    cwd: Path,
    changelog_file: str = DEFAULT_CHANGELOG,
    changed_files: list[str] | None = None,
    ref: str = "HEAD",
    title: str,
) -> int:
    """Validate that changelog-relevant commits update the changelog file."""
    if not commit_subject_requires_changelog(subject):
        return 0

    effective_changed_files = changed_files if changed_files is not None else changed_files_for_ref(cwd, ref)
    if changelog_is_updated(effective_changed_files, changelog_file=changelog_file, cwd=cwd):
        return 0

    normalized_path = _normalize_repo_path(changelog_file, cwd=cwd)
    return emit_failure(
        title,
        [
            f"Commit subject {subject!r} requires a changelog update.",
            f"Expected {normalized_path} to be part of the change set.",
            (
                "Changed files: "
                f"{', '.join(effective_changed_files) if effective_changed_files else '<none>'}."
            ),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for git hook execution."""
    parser = argparse.ArgumentParser(prog="python -m repo_release_tools.hooks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre_commit_parser = subparsers.add_parser("pre-commit", help="Validate the active branch.")
    pre_commit_parser.add_argument("filenames", nargs="*", help=argparse.SUPPRESS)

    changelog_pre_commit_parser = subparsers.add_parser(
        "pre-commit-changelog",
        help="Validate staged changelog updates for the active branch.",
    )
    changelog_pre_commit_parser.add_argument("filenames", nargs="*", help=argparse.SUPPRESS)
    changelog_pre_commit_parser.add_argument(
        "--changelog-file",
        default=DEFAULT_CHANGELOG,
        help="Changelog path to enforce.",
    )

    commit_msg_parser = subparsers.add_parser("commit-msg", help="Validate a commit message file.")
    commit_msg_parser.add_argument("message_file", help="Path to the commit message file.")

    branch_check_parser = subparsers.add_parser(
        "check-branch-name",
        help="Validate an explicit branch name.",
    )
    branch_check_parser.add_argument("--branch", required=True, help="Branch name to validate.")

    subject_check_parser = subparsers.add_parser(
        "check-commit-subject",
        help="Validate an explicit commit subject.",
    )
    subject_check_parser.add_argument(
        "--subject", required=True, help="Commit subject to validate."
    )

    changelog_check_parser = subparsers.add_parser(
        "check-changelog",
        help="Validate that a changelog-relevant commit updates the changelog.",
    )
    changelog_check_parser.add_argument(
        "--subject",
        required=True,
        help="Commit subject to evaluate for changelog enforcement.",
    )
    changelog_check_parser.add_argument(
        "--changelog-file",
        default=DEFAULT_CHANGELOG,
        help="Changelog path to enforce.",
    )
    changelog_check_parser.add_argument(
        "--changed-file",
        action="append",
        dest="changed_files",
        help="Explicit changed file path. May be provided multiple times.",
    )
    changelog_check_parser.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref whose changed files should be inspected when --changed-file is omitted.",
    )

    parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if parsed.command == "pre-commit":
        return run_pre_commit(Path.cwd())
    if parsed.command == "pre-commit-changelog":
        return run_pre_commit_changelog(Path.cwd(), changelog_file=parsed.changelog_file)
    if parsed.command == "commit-msg":
        return run_commit_msg(Path(parsed.message_file))
    if parsed.command == "check-branch-name":
        return run_branch_name_check(parsed.branch, title="Branch name validation failed.")
    if parsed.command == "check-commit-subject":
        return run_commit_subject_check(parsed.subject, title="Commit subject validation failed.")
    return run_changelog_check(
        parsed.subject,
        cwd=Path.cwd(),
        changelog_file=parsed.changelog_file,
        changed_files=parsed.changed_files,
        ref=parsed.ref,
        title="Changelog validation failed.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
