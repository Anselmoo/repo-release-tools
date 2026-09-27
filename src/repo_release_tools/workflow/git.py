"""Git workflow helpers for repository status, commit, sync, and history operations.

## Overview

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair. The tool group favors compact,
human-readable summaries with explicit safety checks before any destructive
operation.

Most commands are designed to run from a Git work tree and emit a short
summary first, followed by the details needed to act on the result.

## Workflow map

- **Inspect**: `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits**: `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync**: `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows**: `rrt branch new`, `rescue`, `rename`
- **Publish**: `rrt git publish-snapshot` force-pushes a single-commit,
  no-history snapshot of tracked content to a secondary remote (e.g. a public
  mirror); `--exclude` drops specific paths (secrets, internal docs) from
  that snapshot. `rrt git backport-from-target` is the read-only counterpart:
  it fetches a publish target and lists commits pending backport to the
  primary, along with the exact commands to cherry-pick them manually.

## Responsibilities

- provide a high-level API for common Git operations used in release flows
- enforce repository policies during commit drafting and branch management
- automate repetitive tasks like auto-stashing during branch switches
- generate human-friendly summaries of repository state and history
- ensure safe operation through dry-run modes and state validation

## Notable behavior

- **Commit Drafting**: `rrt git commit` infers the commit type from the current
  branch only when the branch follows the conventional `type/slug` format.
- **State Management**: `sync` and `move` automatically stash local changes
  before execution and restore them afterward.
- **History Repair**: `undo-safe` and `rebootstrap` provide controlled ways to
  rewrite history, with `rebootstrap` requiring explicit confirmation.
- **Validation**: Refuses to continue in unsafe states, such as unresolved
  conflicts or in-progress merges.
- **Latest tag lookup**: `latest_tag` and `latest_final_tag` pick a group's
  newest release tag. Only tags starting with the group's `tag_prefix` count.
  The remainder must parse as SemVer or CalVer; anything else is skipped.
  Tags sort by version precedence, so `v1.0.0` beats `v1.0.0-rc.2`.
  `latest_final_tag` ignores pre-releases. `rrt bump`, `rrt release notes` and
  `rrt tag` all share this lookup.

## Examples

- `rrt git status`
- `rrt git commit "refresh help examples"`
- `rrt git sync --dry-run`
- `rrt git squash-local --base-ref origin/main "ship parser"`
- `rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run`

## Caveats

- `undo-safe` and `rebootstrap` rewrite repository history. `rebootstrap`
  requires explicit confirmation before it destroys anything.
- `sync` and `move` stash your local changes automatically and restore them
  afterwards. The working tree is touched even on a run you expected to be
  read-only.
- `rrt git commit` only infers the commit type from the branch when that
  branch follows the conventional `type/slug` format.
- These commands refuse to continue in unsafe states, such as unresolved
  conflicts or an in-progress merge.
- The latest-tag lookup matches the prefix literally, not as a glob. With
  prefix `v`, a tag named `vnext` is ignored rather than breaking the range.
  Build metadata never decides precedence; equal versions fall back to tag name.

## Related docs

- [Conventional branches](/repo-release-tools/commands/branch/)
- [Generated CLI reference](/repo-release-tools/commands/rrt-cli/)
"""

from __future__ import annotations

import datetime as dt
import posixpath
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
from repo_release_tools.version import CalVersion, Version
from repo_release_tools.version.semver import SortKey

# Ordered source-owned topic docs for future generic docs generation.
# The page renders under docs/.../commands/, where the publisher injects the
# H1 from TITLE_OVERRIDES, so the docstring ships verbatim.
GIT_DOC = __doc__ or ""

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("git", GIT_DOC),)


def _failure_detail(stdout: str, stderr: str) -> str:
    """Pick the actionable reason from a failed command's captured output.

    Pre-commit's hook summary lines end in "...Passed" or "...Failed"; naively
    taking the last output line breaks when a later hook happens to pass after
    an earlier one failed, surfacing the wrong line as the reason. Scan
    backward through stderr, then stdout, for the last line ending in
    "Failed" and return it plus any detail lines pre-commit prints
    immediately after (e.g. "- files were modified by this hook") up to the
    next blank line. Fall back to the plain last line of either stream if no
    such marker is found, so a caller still sees *something*.
    """
    for text in (stderr, stdout):
        lines = text.strip().splitlines()
        for idx in range(len(lines) - 1, -1, -1):
            if lines[idx].rstrip().endswith("Failed"):
                detail_lines = [lines[idx]]
                for follow in lines[idx + 1 :]:
                    if not follow.strip():
                        break
                    detail_lines.append(follow.strip())
                return " ".join(detail_lines)
    tail = stderr.strip().splitlines() or stdout.strip().splitlines()
    return tail[-1] if tail else ""


def run(
    cmd: list[str],
    cwd: Path,
    *,
    dry_run: bool,
    label: str,
    suppress_announce: bool = False,
) -> str:
    """Run a command in a repository."""
    pretty = " ".join(cmd)
    if dry_run:
        p = DryRunPrinter(dry_run=True)
        p.would_run(pretty)
        return ""
    if not suppress_announce:
        p = VerbosePrinter()
        p.action(f"$ {pretty}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        p = VerbosePrinter()
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                p.action(line)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                p.warn(line, stream=None)
        detail_text = _failure_detail(result.stdout, result.stderr)
        detail = f": {detail_text}" if detail_text else ""
        raise RuntimeError(f"{label} failed (exit {result.returncode}){detail}")
    if result.stdout.strip():
        p = VerbosePrinter()
        for line in result.stdout.strip().splitlines():
            p.action(line)
    return result.stdout.strip()


def capture(cmd: list[str], cwd: Path) -> str:
    """Capture command output."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def capture_checked(cmd: list[str], cwd: Path) -> str:
    """Capture command output, raising RuntimeError on non-zero exit."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        label = " ".join(cmd)
        detail_text = _failure_detail(result.stdout, result.stderr)
        detail = f": {detail_text}" if detail_text else ""
        raise RuntimeError(f"{label} failed (exit {result.returncode}){detail}")
    return result.stdout.strip()


def list_tags(cwd: Path) -> list[str]:
    """Return every tag name in the repository, in git's default (name) order.

    Outside a Git work tree ``git tag`` prints nothing, so the result is empty.
    """
    out = capture(["git", "tag"], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _tag_sort_key(tag: str, prefix: str) -> SortKey | None:
    """Return the version precedence key for *tag*, or ``None`` when it does not count.

    A tag counts when it starts with *prefix* (a literal ``startswith``, never a
    glob) and the remainder parses as SemVer (:meth:`Version.parse`) or, failing
    that, as CalVer (:meth:`CalVersion.parse`).  A CalVer tag maps onto the same
    key shape as :meth:`Version.sort_key` -- ``(year, month, day or 0, 1,
    micro identifiers)`` -- so both schemes order consistently under one prefix.
    The fourth element is ``1`` for a final release and ``0`` for a pre-release.
    """
    if not tag.startswith(prefix):
        return None
    remainder = tag[len(prefix) :]
    try:
        return Version.parse(remainder).sort_key()
    except ValueError:
        pass
    try:
        cal = CalVersion.parse(remainder)
    except ValueError:
        return None
    micro = ((0, cal.micro, ""),) if cal.micro is not None else ()
    return (cal.year, cal.month, cal.day or 0, 1, micro)


def _latest_matching_tag(cwd: Path, prefix: str, *, final_only: bool) -> str | None:
    """Return the highest-precedence tag carrying *prefix*, optionally finals only."""
    candidates: list[tuple[SortKey, str]] = []
    for tag in list_tags(cwd):
        key = _tag_sort_key(tag, prefix)
        if key is None or (final_only and key[3] == 0):
            continue
        candidates.append((key, tag))
    if not candidates:
        return None
    return max(candidates)[1]


def latest_tag(cwd: Path, prefix: str = "v") -> str | None:
    """Return the newest tag starting with *prefix*, by version precedence.

    Tags whose remainder after *prefix* is not a SemVer or CalVer version are
    skipped.  A final release outranks its own pre-releases (``v1.0.0`` beats
    ``v1.0.0-rc.2``), while a newer core's pre-release outranks an older final
    (``v1.1.0-rc.1`` beats ``v1.0.0``).  Versions equal in precedence (they
    differ only in build metadata) are ordered by tag name, so the result is
    deterministic.  Returns ``None`` when no tag qualifies.
    """
    return _latest_matching_tag(cwd, prefix, final_only=False)


def latest_final_tag(cwd: Path, prefix: str = "v") -> str | None:
    """Return the newest non-pre-release tag starting with *prefix*.

    Same selection rules as :func:`latest_tag`, restricted to final releases,
    so ``v1.0.0`` wins over a later ``v1.1.0-rc.1``.  Returns ``None`` when no
    final tag qualifies.
    """
    return _latest_matching_tag(cwd, prefix, final_only=True)


def current_branch(cwd: Path) -> str:
    """Return the current branch name."""
    return capture(["git", "branch", "--show-current"], cwd)


def branch_exists(cwd: Path, branch: str) -> bool:
    """Return whether a local branch exists."""
    return bool(capture(["git", "branch", "--list", "--", branch], cwd))


def working_tree_clean(cwd: Path) -> bool:
    """Return whether the repository has no uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def commits_ahead(cwd: Path, base_ref: str) -> list[str]:
    """Return short log lines for commits on HEAD not in the base ref.

    Raises ``ValueError`` if *base_ref* starts with ``-``: the range expression
    ``<base_ref>..HEAD`` is a single positional argument to ``git log`` that
    cannot be guarded with a ``--`` separator (git would then treat the range
    as a pathspec instead of a revision range), so a leading dash is rejected
    outright to prevent option-injection (CWE-88).
    """
    if base_ref.startswith("-"):
        raise ValueError(f"base_ref must not start with '-': {base_ref!r}")
    out = capture(["git", "log", f"{base_ref}..HEAD", "--pretty=format:%h %s"], cwd)
    return [line for line in out.splitlines() if line]


def ahead_behind(cwd: Path, base_ref: str) -> tuple[int, int]:
    """Return commits ahead/behind relative to a base ref."""
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{base_ref}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (0, 0)
    raw = result.stdout.strip().split()
    if len(raw) != 2:
        return (0, 0)
    return (int(raw[0]), int(raw[1]))


def status_porcelain(cwd: Path, *, include_branch: bool = False) -> list[str]:
    """Return git status lines in porcelain format."""
    command = ["git", "status", "--short"]
    if include_branch:
        command.append("--branch")
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git status --short failed (exit {result.returncode})")
    return [line for line in result.stdout.splitlines() if line]


def upstream_branch(cwd: Path) -> str | None:
    """Return the configured upstream ref for the current branch, if any."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def ref_exists(cwd: Path, ref: str) -> bool:
    """Return whether *ref* resolves to an object in this repository.

    Returns ``False`` (rather than invoking git) if *ref* starts with ``-``:
    ``git rev-parse --verify`` parses its positional argument as an option
    when it looks like one even after a ``--`` separator, so a leading dash
    is rejected outright to prevent option-injection (CWE-88) instead of
    being passed through to the subprocess.
    """
    if ref.startswith("-"):
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def git_dir(cwd: Path) -> Path | None:
    """Return the resolved .git directory for the current work tree, if available."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def in_progress_operation(cwd: Path) -> str | None:
    """Return the current merge/rebase operation name, if one is in progress."""
    directory = git_dir(cwd)
    if directory is None:
        return None
    if (directory / "rebase-merge").exists() or (directory / "rebase-apply").exists():
        return "rebase"
    if (directory / "MERGE_HEAD").exists():
        return "merge"
    return None


def merge_base(cwd: Path, left: str, right: str = "HEAD") -> str | None:
    """Return the merge-base sha for two refs, if one exists."""
    result = subprocess.run(
        ["git", "merge-base", left, right],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def remote_names(cwd: Path) -> list[str]:
    """Return configured remote names."""
    out = capture(["git", "remote"], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def remote_url(cwd: Path, name: str) -> str | None:
    """Return the configured URL for a remote, or None if it doesn't exist."""
    result = subprocess.run(
        ["git", "remote", "get-url", name],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


_SCP_STYLE_RE = re.compile(r"^(?:[\w.-]+@)?([\w.-]+):(.+)$")


def normalize_remote_url(url: str) -> str:
    """Normalize a git remote URL to a scheme-and-case-insensitive host/path form.

    Used only for the publish-snapshot origin-equality guard, never for the
    actual push (which always uses the raw configured/flag value). Collapses
    ``..``/``.`` path segments so a same-repo URL padded with redundant path
    traversal still compares equal to its canonical form.
    """
    value = url.strip()
    for scheme in ("ssh://", "https://", "http://", "git://", "file://"):
        if value.startswith(scheme):
            value = value[len(scheme) :]
            break
    else:
        scp_match = _SCP_STYLE_RE.match(value)
        if scp_match:
            value = f"{scp_match.group(1)}/{scp_match.group(2)}"

    if "@" in value.split("/", 1)[0]:
        value = value.split("@", 1)[1]

    value = value.removesuffix(".git").rstrip("/")
    host, sep, path = value.partition("/")
    if sep:
        path = posixpath.normpath(f"/{path}").lstrip("/")
    return f"{host.lower()}/{path}"


def primary_remote_conflict(cwd: Path, remote: str, primary_remote: str = "origin") -> str | None:
    """Return an error message if *remote* resolves to the same URL as *primary_remote*, else None."""
    primary_url = remote_url(cwd, primary_remote)
    remote_url_value = remote_url(cwd, remote) or remote
    if primary_url is not None and normalize_remote_url(primary_url) == normalize_remote_url(
        remote_url_value
    ):
        return f"--remote {remote!r} resolves to the same URL as {primary_remote} ({primary_url})."
    return None


def unique_snapshot_branch_name(
    cwd: Path,
    *,
    prefix: str = "rrt-snapshot-tmp",
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> str:
    """Return a local branch name for a publish-snapshot temp branch, avoiding collisions."""
    stamp = now().strftime("%Y%m%d%H%M%S")
    base = f"{prefix}-{stamp}"
    if not branch_exists(cwd, base):
        return base
    suffix = 1
    while branch_exists(cwd, f"{base}-{suffix}"):
        suffix += 1
    return f"{base}-{suffix}"


def is_git_repository(cwd: Path) -> bool:
    """Return whether cwd is inside a Git work tree."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def classify_status_line(line: str) -> tuple[str, str]:
    """Classify a git porcelain status line into a compact diff category.

    Returns a ``(kind, path_text)`` tuple where *kind* is one of:
    ``"added"``, ``"removed"``, ``"modified"``, ``"renamed"`,
    ``"conflict"``, or ``"untracked"``.
    """
    status_code = line[:2]
    path_text = line[3:] if len(line) > 3 else line
    if status_code == "??":
        return ("untracked", path_text)
    if "U" in status_code or status_code in {"AA", "DD"}:
        return ("conflict", path_text)
    if "R" in status_code or "C" in status_code:
        return ("renamed", path_text)
    if "A" in status_code:
        return ("added", path_text)
    if "D" in status_code:
        return ("removed", path_text)
    return ("modified", path_text)
