"""Validators and entrypoints for branch, commit, and changelog policy checks."""

from __future__ import annotations

import argparse
import re
import sys

from collections import Counter
from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.changelog import SECTION_MAP, parse_conventional_commit
from repo_release_tools.config import DEFAULT_CHANGELOG
from repo_release_tools.commands.branch import CONVENTIONAL_TYPES, SLUG_MAX, normalize_commit_type
from repo_release_tools.versioning import Version


ALLOWED_BRANCH_NAMES = ("main", "master", "develop")
MAGIC_BRANCH_TYPES = ("claude", "codex", "copilot")
BOT_BRANCH_TYPES = ("dependabot", "renovate")
ALLOWED_BRANCH_TYPES = (*CONVENTIONAL_TYPES, *MAGIC_BRANCH_TYPES, *BOT_BRANCH_TYPES)
BRANCH_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_branch_name(
    branch_name: str,
    *,
    extra_types: tuple[str, ...] = (),
) -> str | None:
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
    passthrough_types = (*MAGIC_BRANCH_TYPES, *BOT_BRANCH_TYPES, *extra_types)
    if type_part not in passthrough_types:
        try:
            normalize_commit_type(type_part)
        except argparse.ArgumentTypeError:
            allowed = ", ".join((*ALLOWED_BRANCH_TYPES, *extra_types))
            return f"Branch type {type_part!r} is invalid. Choose one of: {allowed}."

    # Bot and passthrough branches (dependabot, renovate, extra_branch_types)
    # use externally-generated slugs that may contain slashes and underscores,
    # so skip slug format and length validation for them.
    if type_part in (*BOT_BRANCH_TYPES, *extra_types):
        return None

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
    if (
        not branch_name
        or branch_name in ALLOWED_BRANCH_NAMES
        or branch_name.startswith("release/v")
    ):
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
    out = git.capture(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "--root", "-r", ref], cwd
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def changelog_is_updated(changed_files: list[str], *, changelog_file: str, cwd: Path) -> bool:
    """Return whether the changelog file is included in the changed files."""
    target = _normalize_repo_path(changelog_file, cwd=cwd)
    return any(_normalize_repo_path(path, cwd=cwd) == target for path in changed_files)


# ---------------------------------------------------------------------------
# Post-correction helpers
# ---------------------------------------------------------------------------

_OPPOSITE_VERB_PAIRS: list[tuple[str, str]] = [
    ("add ", "remove "),
    ("adds ", "removes "),
    ("enable ", "disable "),
    ("enables ", "disables "),
    ("include ", "exclude "),
    ("includes ", "excludes "),
    ("upgrade ", "downgrade "),
    ("upgrades ", "downgrades "),
    ("revert ", "apply "),
    ("reverts ", "applies "),
]

# Matches a leading "SCOPE: " prefix in a changelog bullet description.
# Scope identifiers are restricted to alphanumeric characters, underscores,
# and hyphens to avoid false matches on entries that happen to contain a colon.
_SCOPE_PREFIX_RE = re.compile(r"^([A-Za-z0-9_-]+):\s+(.+)$")


def _split_scope(text: str) -> tuple[str | None, str]:
    """Split a bullet description into ``(scope_lower, rest)`` or ``(None, text)``."""
    m = _SCOPE_PREFIX_RE.match(text)
    if m:
        return m.group(1).lower(), m.group(2)
    return None, text


def collect_squash_changelog_hunks(
    cwd: Path,
    ref: str = "HEAD",
    changelog_file: str = DEFAULT_CHANGELOG,
) -> tuple[list[str], frozenset[int]]:
    """Return ``(added_lines, added_line_positions)`` for *changelog_file* in *ref*.

    *added_lines* are the content lines (without the leading ``+``) that the
    commit introduced.  *added_line_positions* is the set of 1-based line
    numbers those additions occupy in the post-commit file, parsed from the
    ``@@ ... @@`` hunk headers so that
    :func:`apply_dedup_to_changelog` can restrict removals to the exact
    squash hunk rather than scanning the whole file.
    """
    out = git.capture_checked(
        ["git", "show", "--format=", ref, "--", changelog_file],
        cwd,
    )
    added: list[str] = []
    positions: set[int] = set()
    current_new_line = 0

    for line in out.splitlines():
        if line.startswith(("diff ", "index ", "--- ", "+++ ")):
            continue
        if line.startswith("@@ "):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                current_new_line = int(m.group(1)) - 1
            continue
        if line.startswith("+"):
            current_new_line += 1
            added.append(line[1:])
            positions.add(current_new_line)
        elif line.startswith(" "):
            current_new_line += 1
        # "-" lines: only in old file; new-file counter does not advance

    return added, frozenset(positions)


def _entries_cancel_out(a: str, b: str) -> bool:
    """Return ``True`` if two bullet-entry descriptions are semantic opposites.

    For example ``"add Node 26"`` / ``"remove Node 26"`` cancel each other
    out, and so do ``"CI: add Node 26"`` / ``"CI: remove Node 26"``.

    Entries with different scope prefixes (e.g. ``"CI: …"`` vs ``"Deps: …"``)
    are never considered cancelling pairs even if their verb+subject match.
    """
    a_scope, a_rest = _split_scope(a)
    b_scope, b_rest = _split_scope(b)
    if a_scope != b_scope:
        return False

    a_lower = a_rest.lower()
    b_lower = b_rest.lower()
    for v1, v2 in _OPPOSITE_VERB_PAIRS:
        rest_a_v1 = a_lower.removeprefix(v1)
        rest_b_v2 = b_lower.removeprefix(v2)
        if rest_a_v1 != a_lower and rest_b_v2 != b_lower and rest_a_v1 == rest_b_v2:
            return True
        rest_a_v2 = a_lower.removeprefix(v2)
        rest_b_v1 = b_lower.removeprefix(v1)
        if rest_a_v2 != a_lower and rest_b_v1 != b_lower and rest_a_v2 == rest_b_v1:
            return True
    return False


def dedup_changelog_entries(added_lines: list[str]) -> list[str]:
    """Remove duplicate and contradicting bullet entries from *added_lines*.

    Non-bullet lines (headers, blank lines, etc.) are preserved as-is.
    Among bullet lines:

    * Exact duplicates (case-insensitive) are collapsed to the first occurrence.
    * Pairs of entries whose descriptions are semantic opposites (e.g.
      ``"add X"`` / ``"remove X"``) are both removed.

    Consecutive blank lines produced by the removal are collapsed to a single
    blank line.
    """
    # Split lines into indices of bullets vs. structural lines
    bullet_indices: list[int] = []
    for i, line in enumerate(added_lines):
        if line.strip().startswith("- "):
            bullet_indices.append(i)

    # Deduplicate bullets (case-insensitive exact match) — keep first occurrence
    seen_keys: set[str] = set()
    duplicate_indices: set[int] = set()
    for i in bullet_indices:
        key = added_lines[i].strip().lower()
        if key in seen_keys:
            duplicate_indices.add(i)
        else:
            seen_keys.add(key)

    # Detect cancelling pairs among the remaining (non-duplicate) bullets
    remaining_bullets = [
        (i, added_lines[i].strip()[2:].strip())
        for i in bullet_indices
        if i not in duplicate_indices
    ]
    cancelled_indices: set[int] = set()
    for pos_a, (i, desc_a) in enumerate(remaining_bullets):
        if i in cancelled_indices:
            continue
        for j, desc_b in remaining_bullets[pos_a + 1 :]:
            if j in cancelled_indices:
                continue
            if _entries_cancel_out(desc_a, desc_b):
                cancelled_indices.add(i)
                cancelled_indices.add(j)
                break

    remove_indices = duplicate_indices | cancelled_indices

    if not remove_indices:
        return list(added_lines)

    result = [line for i, line in enumerate(added_lines) if i not in remove_indices]

    # Collapse consecutive blank lines
    cleaned: list[str] = []
    prev_blank = False
    for line in result:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank

    return cleaned


def apply_dedup_to_changelog(
    changelog_path: Path,
    added_lines: list[str],
    deduped_lines: list[str],
    *,
    added_line_positions: frozenset[int] | None = None,
) -> bool:
    """Rewrite *changelog_path* removing entries that were filtered out.

    Uses a :class:`~collections.Counter` diff to decide how many times each
    line should be removed.  When *added_line_positions* is provided (1-based
    line numbers of the squash-commit additions), removals are restricted to
    those positions so that identical lines in older release sections are never
    accidentally deleted.

    Returns ``True`` when the file was modified, ``False`` when nothing
    changed.
    """
    added_counter = Counter(added_lines)
    deduped_counter = Counter(deduped_lines)
    to_remove = added_counter - deduped_counter

    if not to_remove:
        return False

    content = changelog_path.read_text(encoding="utf-8")
    removal_budget: dict[str, int] = dict(to_remove)

    result_lines: list[str] = []
    for line_idx, raw_line in enumerate(content.splitlines(keepends=True), start=1):
        key = raw_line.rstrip("\n")
        in_hunk = added_line_positions is None or line_idx in added_line_positions
        if in_hunk and removal_budget.get(key, 0) > 0:
            removal_budget[key] -= 1
            continue
        result_lines.append(raw_line)

    # Collapse consecutive blank lines that may result from the removal
    cleaned: list[str] = []
    prev_blank = False
    for line in result_lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank

    new_content = "".join(cleaned)
    if new_content == content:
        return False
    changelog_path.write_text(new_content, encoding="utf-8")
    return True


def emit_failure(title: str, details: list[str]) -> int:
    """Render a hook failure message and return a non-zero exit code."""
    print(output.warning(title, indent=0), file=sys.stderr)
    for detail in details:
        print(output.status(output.GLYPHS.bullet.dot, detail), file=sys.stderr)
    return 1


def _load_extra_branch_types(cwd: Path) -> tuple[str, ...]:
    """Load extra_branch_types from rrt config if available."""
    try:
        from repo_release_tools.config import load_config

        cfg = load_config(cwd)
        return cfg.extra_branch_types
    except (FileNotFoundError, ValueError):
        return ()


def run_branch_name_check(
    branch_name: str,
    *,
    title: str,
    extra_types: tuple[str, ...] = (),
) -> int:
    """Validate an explicit branch name."""
    problem = validate_branch_name(branch_name, extra_types=extra_types)
    if problem is None:
        return 0

    all_types = (*ALLOWED_BRANCH_TYPES, *extra_types)
    return emit_failure(
        title,
        [
            problem,
            "Expected: <type>/<kebab-case-description>.",
            (
                "Allowed types: "
                f"{', '.join(all_types)} "
                "(including AI helper branches: claude, codex, copilot"
                " and bot branches: dependabot, renovate)."
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


def run_dirty_tree_check(cwd: Path, *, title: str) -> int:
    """Validate that the working tree is clean."""
    if not git.is_git_repository(cwd):
        return emit_failure(
            title,
            [f"{cwd} is not inside a Git work tree."],
        )

    if git.working_tree_clean(cwd):
        return 0

    try:
        lines = git.status_porcelain(cwd)
    except RuntimeError as exc:
        return emit_failure(title, [str(exc)])
    return emit_failure(
        title,
        [
            "Working tree has uncommitted changes.",
            (f"Changed entries: {', '.join(lines) if lines else '<unavailable>'}."),
        ],
    )


def run_pre_commit(cwd: Path) -> int:
    """Validate the active branch during pre-commit."""
    branch_name = git.current_branch(cwd)
    extra_types = _load_extra_branch_types(cwd)
    return run_branch_name_check(
        branch_name,
        title="Commit blocked by branch naming policy.",
        extra_types=extra_types,
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

    effective_changed_files = (
        changed_files if changed_files is not None else changed_files_for_ref(cwd, ref)
    )
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


def run_post_correct(
    cwd: Path,
    *,
    ref: str = "HEAD",
    changelog_file: str = DEFAULT_CHANGELOG,
    commit: bool = False,
) -> int:
    """Consolidate fragmented changelog entries after a squash merge.

    Inspects the diff that *ref* introduced to *changelog_file*, removes
    duplicate and semantically-cancelling bullet entries (e.g. ``"add X"``
    followed by ``"remove X"``), rewrites the file in-place, and optionally
    creates a follow-up commit.
    """
    changelog_path = cwd / changelog_file
    if not changelog_path.exists():
        return emit_failure(
            "Changelog post-correction failed.",
            [f"Changelog file {changelog_file!r} not found in {cwd}."],
        )

    try:
        added_lines, positions = collect_squash_changelog_hunks(
            cwd, ref=ref, changelog_file=changelog_file
        )
    except RuntimeError as exc:
        return emit_failure("Changelog post-correction failed.", [str(exc)])
    if not added_lines:
        print(
            output.ok(f"No changelog changes found in {ref!r}. Nothing to correct."),
            file=sys.stderr,
        )
        return 0

    deduped_lines = dedup_changelog_entries(added_lines)

    changed = apply_dedup_to_changelog(
        changelog_path, added_lines, deduped_lines, added_line_positions=positions
    )
    if not changed:
        print(
            output.ok("Changelog is already clean. Nothing to correct."),
            file=sys.stderr,
        )
        return 0

    removed_count = len(added_lines) - len(deduped_lines)
    noun = "entry" if removed_count == 1 else "entries"
    print(
        output.ok(
            f"Post-correction: removed {removed_count} duplicate/contradicting changelog {noun}."
        ),
        file=sys.stderr,
    )

    if commit:
        try:
            git.run(
                ["git", "add", changelog_file],
                cwd,
                dry_run=False,
                label="git add changelog",
            )
            git.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "chore: post-correct changelog after squash merge [skip ci]",
                ],
                cwd,
                dry_run=False,
                label="git commit",
            )
        except RuntimeError as exc:
            return emit_failure("Changelog post-correction commit failed.", [str(exc)])

    return 0


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

    subparsers.add_parser(
        "check-dirty-tree",
        help="Validate that the current working tree is clean.",
    )

    changelog_parser = subparsers.add_parser(
        "changelog",
        help="Changelog management commands.",
    )
    changelog_subparsers = changelog_parser.add_subparsers(
        dest="changelog_command",
        required=True,
    )
    post_correct_parser = changelog_subparsers.add_parser(
        "post-correct",
        help="Consolidate fragmented changelog entries after a squash merge.",
    )
    post_correct_parser.add_argument(
        "--squash-commit",
        default=None,
        metavar="SHA",
        help="Explicit commit SHA to treat as the squash commit (defaults to HEAD).",
    )
    post_correct_parser.add_argument(
        "--output",
        default=DEFAULT_CHANGELOG,
        metavar="PATH",
        help="Changelog file to rewrite (default: CHANGELOG.md).",
    )
    post_correct_parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Create a follow-up commit with the corrected changelog.",
    )

    parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if parsed.command == "pre-commit":
        return run_pre_commit(Path.cwd())
    if parsed.command == "pre-commit-changelog":
        return run_pre_commit_changelog(Path.cwd(), changelog_file=parsed.changelog_file)
    if parsed.command == "commit-msg":
        return run_commit_msg(Path(parsed.message_file))
    if parsed.command == "check-branch-name":
        extra_types = _load_extra_branch_types(Path.cwd())
        return run_branch_name_check(
            parsed.branch,
            title="Branch name validation failed.",
            extra_types=extra_types,
        )
    if parsed.command == "check-commit-subject":
        return run_commit_subject_check(parsed.subject, title="Commit subject validation failed.")
    if parsed.command == "check-dirty-tree":
        return run_dirty_tree_check(Path.cwd(), title="Dirty tree validation failed.")
    if parsed.command == "changelog" and parsed.changelog_command == "post-correct":
        ref = parsed.squash_commit or "HEAD"
        return run_post_correct(
            Path.cwd(),
            ref=ref,
            changelog_file=parsed.output,
            commit=parsed.commit,
        )
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
