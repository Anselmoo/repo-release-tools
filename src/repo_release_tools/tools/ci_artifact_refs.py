"""Find CI call sites that fetch a build artifact from another pipeline.

These are the artifacts a storage cleanup must never delete: the dependency is
declared in the *consuming* job's config, not on the artifact, so nothing on the
forge side can infer it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

CI_GLOBS = (
    ".gitlab-ci.yml",
    ".gitlab/**/*.yml",
    ".gitlab/**/*.yaml",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
)

#: Sentinel ``job`` value recorded for a GitHub ``download-artifact`` step that
#: carries ``run-id:`` but no ``name:`` — standard usage meaning "download every
#: artifact from that run" (common in publish/release jobs). GitHub forbids
#: ``"``, ``:``, ``<``, ``>``, ``|``, ``*``, ``?``, CR, and LF in real artifact
#: names, so ``"*"`` can never collide with an actual artifact and is safe to
#: use as an unambiguous marker. Declare it with ``job = "*"`` in a `consumed`
#: entry to protect it.
DOWNLOAD_ALL_MARKER = "*"

# GitLab: .../jobs/artifacts/<ref>/raw/<path>?job=<name>
_GITLAB_FETCH = re.compile(
    r"jobs/artifacts/(?P<ref>[^/\s]+)/raw/(?P<path>[^\s\"'?]+)\?job=(?P<job>[^\s\"'&]+)"
)
# GitHub: download-artifact pointed at another run
_GH_DOWNLOAD = re.compile(r"actions/download-artifact@")
_GH_RUN_ID = re.compile(r"run-id:\s*(?P<run>\S+)")
_GH_NAME = re.compile(r"name:\s*(?P<name>\S+)")


@dataclass(frozen=True)
class ArtifactFetch:
    """Record of a cross-pipeline artifact fetch in CI configuration."""

    job: str
    ref: str | None
    path: str | None
    source_file: str
    line: int


def _iter_ci_files(root: Path) -> Iterator[Path]:
    for pattern in CI_GLOBS:
        yield from sorted(root.glob(pattern))


def _scan_github(root: Path) -> list[ArtifactFetch]:
    """Scan GitHub Actions workflows for cross-pipeline artifact downloads.

    A download-artifact action only crosses pipelines when it carries run-id,
    so we inspect the step block rather than single lines. Returns [] when
    run-id is absent (same-pipeline case).

    When run-id is present but name is absent — standard GitHub usage meaning
    "download every artifact from this run" — the fetch is still recorded, with
    ``job`` set to :data:`DOWNLOAD_ALL_MARKER` (``"*"``) rather than being
    silently dropped.
    """
    found: list[ArtifactFetch] = []

    # Iterate over GitHub workflow patterns from CI_GLOBS, sorted
    gh_patterns = [p for p in CI_GLOBS if p.startswith(".github/workflows/")]
    for pattern in gh_patterns:
        for path in sorted(root.glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue

            rel = str(path.relative_to(root))
            lines = text.splitlines()

            # Find download-artifact steps
            i = 0
            while i < len(lines):
                line = lines[i]
                if _GH_DOWNLOAD.search(line):
                    # This is a download-artifact action line. Now look for run-id
                    # and name in the following indented block.
                    step_block_start = i
                    run_id_match = None
                    name_match = None

                    # Look ahead for run-id and name in the step block
                    j = i + 1
                    base_indent = len(line) - len(line.lstrip())
                    while j < len(lines):
                        next_line = lines[j]
                        # Stop if we hit a line that's not indented more than the action line
                        # (indicates end of step block)
                        if (
                            next_line.strip()
                            and (len(next_line) - len(next_line.lstrip())) <= base_indent
                        ):
                            break

                        # Check for run-id or name
                        if not run_id_match:
                            run_id_match = _GH_RUN_ID.search(next_line)
                        if not name_match:
                            name_match = _GH_NAME.search(next_line)

                        j += 1

                    # Only record if run-id is present (cross-pipeline). name is
                    # optional — its absence means "download every artifact from
                    # this run", not "no fetch"; record it under the sentinel
                    # DOWNLOAD_ALL_MARKER rather than dropping it silently.
                    if run_id_match:
                        job = name_match["name"] if name_match else DOWNLOAD_ALL_MARKER
                        found.append(
                            ArtifactFetch(
                                job=job,
                                ref=run_id_match["run"],
                                path=None,
                                source_file=rel,
                                line=step_block_start + 1,
                            )
                        )
                i += 1

    return found


def _scan_gitlab(root: Path) -> list[ArtifactFetch]:
    """Scan CI config for GitLab artifact-fetch-by-API call sites.

    Deliberately scans *every* file in :data:`CI_GLOBS`, not only the GitLab
    ones: a job running on GitHub Actions can still ``curl`` an artifact out of
    a GitLab instance, and narrowing this to the ``.gitlab*`` patterns would
    make that fetch invisible — a false negative, which is the failure mode
    this module exists to prevent. Contrast :func:`_scan_github`, which is
    necessarily pattern-scoped because it parses Actions step blocks.
    """
    found: list[ArtifactFetch] = []
    for path in _iter_ci_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            # finditer, not search: chained shell commands (e.g. `curl ... &&
            # curl ...`) can put more than one fetch on a single physical line.
            for match in _GITLAB_FETCH.finditer(line):
                found.append(
                    ArtifactFetch(
                        job=match["job"],
                        ref=match["ref"],
                        path=match["path"],
                        source_file=rel,
                        line=lineno,
                    )
                )
    return found


def scan_ci_config(root: Path) -> list[ArtifactFetch]:
    """Return every cross-pipeline artifact fetch declared under *root*."""
    return [*_scan_gitlab(root), *_scan_github(root)]
