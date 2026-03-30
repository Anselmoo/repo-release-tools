"""Validators and entrypoints for branch and commit naming conventions."""

from __future__ import annotations

import argparse
import re
import sys

from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.changelog import parse_conventional_commit
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, SLUG_MAX, normalize_commit_type
from repo_release_tools.versioning import Version


ALLOWED_BRANCH_NAMES = ("main", "master", "develop")
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
    try:
        normalize_commit_type(type_part)
    except argparse.ArgumentTypeError:
        allowed = ", ".join(CONVENTIONAL_TYPES)
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
            f"Allowed types: {', '.join(CONVENTIONAL_TYPES)}.",
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


def run_commit_msg(message_path: Path) -> int:
    """Validate the commit subject during commit-msg."""
    subject = read_commit_subject(message_path)
    return run_commit_subject_check(
        subject,
        title="Commit blocked by commit message policy.",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for git hook execution."""
    parser = argparse.ArgumentParser(prog="python -m repo_release_tools.hooks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre_commit_parser = subparsers.add_parser("pre-commit", help="Validate the active branch.")
    pre_commit_parser.add_argument("filenames", nargs="*", help=argparse.SUPPRESS)

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

    parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if parsed.command == "pre-commit":
        return run_pre_commit(Path.cwd())
    if parsed.command == "commit-msg":
        return run_commit_msg(Path(parsed.message_file))
    if parsed.command == "check-branch-name":
        return run_branch_name_check(parsed.branch, title="Branch name validation failed.")
    return run_commit_subject_check(parsed.subject, title="Commit subject validation failed.")


if __name__ == "__main__":
    raise SystemExit(main())
