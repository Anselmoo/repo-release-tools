from pathlib import Path
from unittest.mock import patch

from repo_release_tools.tools.ci_artifact_refs import DOWNLOAD_ALL_MARKER, scan_ci_config


def _raise_os_error(self: Path, *args: object, **kwargs: object) -> str:
    """Stand-in for `Path.read_text` that always raises `OSError`.

    `chmod(0o000)` is a no-op under elevated privileges (root, many CI
    containers) and behaves inconsistently on Windows, so it cannot reliably
    force a read failure; patching `Path.read_text` directly is
    platform/privilege independent. Mirrors the idiom at
    `tests/version/test_version_targets.py:840-848`.
    """
    raise OSError("permission denied")


GITLAB_SNIPPET = """
build:docs:
  script:
    - |
      curl --fail --location --silent \\
        --header "JOB-TOKEN: $CI_JOB_TOKEN" \\
        "$CI_API_V4_URL/projects/$CI_PROJECT_ID/jobs/artifacts/$CI_DEFAULT_BRANCH/raw/artifacts/manifest.json?job=build:report_html" \\
        --output /tmp/benchmark-manifest.json
"""


def test_finds_gitlab_artifact_fetch(tmp_path: Path) -> None:
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "65-docs.yml").write_text(GITLAB_SNIPPET)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build:report_html"
    assert fetches[0].ref == "$CI_DEFAULT_BRANCH"
    assert fetches[0].path == "artifacts/manifest.json"
    assert fetches[0].source_file.endswith("65-docs.yml")


def test_ignores_same_pipeline_needs(tmp_path: Path) -> None:
    """`needs:` is an intra-pipeline dependency, not a cross-pipeline fetch."""
    (tmp_path / ".gitlab-ci.yml").write_text(
        "build:docs:\n  needs:\n    - job: setup\n      artifacts: true\n"
    )
    assert scan_ci_config(tmp_path) == []


def test_handles_job_names_with_multiple_colons(tmp_path: Path) -> None:
    """Job names can contain multiple colons (e.g., build:report_html:bundle)."""
    gitlab_snippet_multi_colon = """
build:pages:
  script:
    - curl "$CI_API_V4_URL/projects/$CI_PROJECT_ID/jobs/artifacts/main/raw/output.txt?job=build:report_html:bundle"
"""
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "60-pages.yml").write_text(gitlab_snippet_multi_colon)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build:report_html:bundle"
    assert fetches[0].ref == "main"
    assert fetches[0].path == "output.txt"
    assert fetches[0].source_file.endswith("60-pages.yml")


def test_github_download_artifact_with_run_id(tmp_path: Path) -> None:
    """GitHub download-artifact with run-id is a cross-pipeline fetch."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: build-output
          run-id: 12345
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build-output"
    assert fetches[0].ref == "12345"
    assert fetches[0].path is None


def test_github_download_artifact_without_run_id(tmp_path: Path) -> None:
    """GitHub download-artifact without run-id is same-pipeline (ignored)."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: build-output
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert fetches == []


def test_github_download_artifact_run_id_without_name_is_recorded(tmp_path: Path) -> None:
    """Regression: `run-id:` without `name:` means "download every artifact from
    the run" — standard GitHub usage, not "no fetch". Before the fix this was
    silently dropped (`scan_ci_config` returned []), making the fetch invisible
    to the artifact-protection lens.
    """
    github_snippet = """
name: Build
on: push
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          run-id: 999
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == DOWNLOAD_ALL_MARKER
    assert fetches[0].job == "*"
    assert fetches[0].ref == "999"
    assert fetches[0].path is None


def test_gitlab_two_fetches_on_one_physical_line_both_found(tmp_path: Path) -> None:
    """Regression: chained shell commands (`curl ... && curl ...`) on one line
    are ordinary style. Before the fix `_GITLAB_FETCH.search()` found only the
    first match per line, silently dropping the second fetch.
    """
    chained = (
        "build:docs:\n"
        "  script:\n"
        '    - curl ".../jobs/artifacts/main/raw/a.txt?job=job-a" '
        '&& curl ".../jobs/artifacts/main/raw/b.txt?job=job-b"\n'
    )
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "ci.yml").write_text(chained)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 2
    assert fetches[0].job == "job-a"
    assert fetches[0].path == "a.txt"
    assert fetches[1].job == "job-b"
    assert fetches[1].path == "b.txt"
    # Both fetches are on the same physical line.
    assert fetches[0].line == fetches[1].line == 3


def test_gitlab_yaml_extension_at_top_level_is_scanned(tmp_path: Path) -> None:
    """Regression: `.gitlab/*.yaml` (not just `.yml`) was never scanned.

    GitLab's `include: local:` accepts any filename.
    """
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "inc.yaml").write_text(
        'build:docs:\n  script:\n    - curl ".../jobs/artifacts/main/raw/a.txt?job=job-a"\n'
    )
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "job-a"
    assert fetches[0].source_file.endswith("inc.yaml")


def test_gitlab_nested_subdirectory_is_scanned(tmp_path: Path) -> None:
    """Regression: the `.gitlab/` scan was single-level (non-recursive).

    Nested subdirectories under `.gitlab/` are ordinary GitLab CI layout.
    """
    (tmp_path / ".gitlab" / "includes").mkdir(parents=True)
    (tmp_path / ".gitlab" / "includes" / "nested.yml").write_text(
        'build:docs:\n  script:\n    - curl ".../jobs/artifacts/main/raw/a.txt?job=job-a"\n'
    )
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "job-a"
    assert fetches[0].source_file.endswith("includes/nested.yml")


def test_gitlab_file_read_error_handled(tmp_path: Path) -> None:
    """OSError during file read is silently skipped."""
    (tmp_path / ".gitlab").mkdir()
    gitlab_file = tmp_path / ".gitlab" / "ci.yml"
    gitlab_file.write_text(GITLAB_SNIPPET)

    with patch.object(Path, "read_text", _raise_os_error):
        # Should not raise, just skip the unreadable file
        fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 0


def test_gitlab_line_without_match_skipped(tmp_path: Path) -> None:
    """Lines without artifact fetch patterns are skipped without error."""
    gitlab_snippet_no_match = """
build:docs:
  script:
    - echo "This line has no artifact fetch"
    - echo "Neither does this one"
"""
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "ci.yml").write_text(gitlab_snippet_no_match)
    fetches = scan_ci_config(tmp_path)
    assert fetches == []


def test_multiple_gitlab_fetches_same_file(tmp_path: Path) -> None:
    """Multiple artifact fetches in one file are all found."""
    multi_fetch = """
build:docs:
  script:
    - curl "$CI_API_V4_URL/projects/$CI_PROJECT_ID/jobs/artifacts/main/raw/doc1.txt?job=job1"
    - curl "$CI_API_V4_URL/projects/$CI_PROJECT_ID/jobs/artifacts/v1.0/raw/doc2.txt?job=job2"
"""
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "ci.yml").write_text(multi_fetch)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 2
    assert fetches[0].job == "job1"
    assert fetches[0].ref == "main"
    assert fetches[1].job == "job2"
    assert fetches[1].ref == "v1.0"


def test_github_file_read_error_handled(tmp_path: Path) -> None:
    """OSError during GitHub workflows file read is silently skipped."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: build-output
          run-id: 12345
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    github_file = tmp_path / ".github" / "workflows" / "ci.yml"
    github_file.write_text(github_snippet)

    with patch.object(Path, "read_text", _raise_os_error):
        # Should not raise, just skip the unreadable file
        fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 0


def test_github_step_block_boundary_detection(tmp_path: Path) -> None:
    """Step block ends when indentation returns to same level as action line."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: output
          run-id: 999
      - uses: actions/upload-artifact@v4
        with:
          name: result
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    # Should only find the first download-artifact with run-id
    assert len(fetches) == 1
    assert fetches[0].job == "output"
    assert fetches[0].ref == "999"


def test_github_yaml_workflow_support(tmp_path: Path) -> None:
    """GitHub workflows with .yaml extension are scanned."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: compiled-artifacts
          run-id: 54321
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "build.yaml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "compiled-artifacts"
    assert fetches[0].ref == "54321"
    assert fetches[0].source_file.endswith("build.yaml")


# ---------------------------------------------------------------------------
# Fix A (NEW-1): idiomatic `- name:` / `uses:` / `with:` step form
# ---------------------------------------------------------------------------


def test_github_idiomatic_name_then_uses_step_is_scanned(tmp_path: Path) -> None:
    """The idiomatic step form (`- name:` first, `uses:` nested) must still be found.

    Before the fix, `_scan_github` anchored the step block on `uses:`'s own
    indent. In this form `with:` sits at the *same* indent as `uses:` (both
    are sibling keys of the step mapping), so the look-ahead broke
    immediately and the fetch was silently dropped — `scan_ci_config`
    returned `[]` even though a real cross-pipeline fetch was present.
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Download build output
        uses: actions/download-artifact@v4
        with:
          run-id: 12345
          name: build-output
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build-output"
    assert fetches[0].ref == "12345"
    assert fetches[0].path is None


def test_github_step_layout_copied_from_this_repos_own_cicd_workflow(tmp_path: Path) -> None:
    """A step block copied verbatim from `.github/workflows/cicd.yml`'s own style.

    This repo's CI writes every `download-artifact` step as `- name:` then
    `uses:` then `with:` (see e.g. lines 242-245 of cicd.yml). Those specific
    steps never carry `run-id:` (they're same-pipeline), so this fixture adds
    one to prove the scanner detects a cross-pipeline fetch written in this
    project's own real-world layout.
    """
    github_snippet = """
name: CI/CD
on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7
      - name: Download wheel
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: python-package-distributions
          path: dist/
          run-id: 987654321
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "cicd.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "python-package-distributions"
    assert fetches[0].ref == "987654321"


def test_github_extra_keys_before_uses_are_skipped(tmp_path: Path) -> None:
    """`id:`, `if:`, and `continue-on-error:` before `uses:` don't break detection."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Download build output
        id: dl
        if: always()
        continue-on-error: true
        uses: actions/download-artifact@v4
        with:
          run-id: 555
          name: build-output
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build-output"
    assert fetches[0].ref == "555"


def test_github_idiomatic_step_without_with_block_finds_nothing(tmp_path: Path) -> None:
    """A `- name:`/`uses:` step with no `with:` block at all yields no fetch, no crash."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    assert scan_ci_config(tmp_path) == []


def test_github_multiple_idiomatic_steps_both_found(tmp_path: Path) -> None:
    """Multiple `- name:`-first download-artifact steps in one job are all found."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Download A
        uses: actions/download-artifact@v4
        with:
          run-id: 111
          name: artifact-a
      - name: Download B
        uses: actions/download-artifact@v4
        with:
          run-id: 222
          name: artifact-b
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 2
    assert fetches[0].job == "artifact-a"
    assert fetches[0].ref == "111"
    assert fetches[1].job == "artifact-b"
    assert fetches[1].ref == "222"


def test_github_idiomatic_step_boundary_does_not_over_read_into_next_step(
    tmp_path: Path,
) -> None:
    """A step following the target step must not leak its content into the block.

    Regression: with the fix anchored on the step's own `- ` indent, the
    following `- uses: actions/upload-artifact@v4` step (a different action
    entirely) must correctly terminate the first step's block rather than
    being scanned for run-id/name too.
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Download output
        uses: actions/download-artifact@v4
        with:
          run-id: 999
          name: output
      - name: Upload result
        uses: actions/upload-artifact@v4
        with:
          name: result
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "output"
    assert fetches[0].ref == "999"


def test_github_uses_line_with_no_preceding_list_marker_does_not_crash(
    tmp_path: Path,
) -> None:
    """A `uses:` key reached with no `- ` marker anywhere above it in the file.

    Not valid GitHub Actions syntax (a real step is always a sequence item),
    but `_step_item_indent`'s backward scan must degrade gracefully rather
    than raising when it reaches the top of the file without ever finding a
    list marker — exercising the defensive fallback.
    """
    github_snippet = """name: Build
on: push
jobs:
  deploy:
    uses: actions/download-artifact@v4
    with:
      run-id: 123
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    # No `- ` marker precedes `uses:` anywhere in the file, so the fallback
    # (uses:'s own indent) applies — `with:` then sits at that same indent,
    # ending the block before `run-id:` is ever read. Must not raise.
    assert scan_ci_config(tmp_path) == []


def test_github_step_label_name_not_mistaken_for_artifact_name(tmp_path: Path) -> None:
    """A step's own `name:` key (outside `with:`) must never leak into `job`.

    Regression introduced by anchoring the step block on the `- ` indent
    (Fix A): once the block correctly reaches past `uses:`, a `name:` key
    that is a *step* attribute (not nested under `with:`) must still be
    ignored — otherwise the human-readable step label would be mistaken for
    the artifact's `name:` input.
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        name: Download build output
        with:
          run-id: 12345
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    # No `name:` was found *inside* `with:`, so it must fall back to the
    # "download everything" marker, not the step's human-readable label.
    assert fetches[0].job == DOWNLOAD_ALL_MARKER
    assert fetches[0].ref == "12345"


# ---------------------------------------------------------------------------
# Fix C: `_GH_DOWNLOAD` must anchor to the `uses:` key, not match anywhere
# ---------------------------------------------------------------------------


def test_github_download_artifact_string_in_run_command_not_scanned(tmp_path: Path) -> None:
    """A `run:` command that merely mentions the action string is not a step.

    Before the fix, `_GH_DOWNLOAD` matched the substring anywhere on a line,
    with no requirement that it follow a `uses:` key. Written as `- run:`
    (dash and `run:` on the same line), the substring-bearing line's own
    leading-whitespace indent happens to equal the true step indent — the
    same coincidence that let the pre-fix `- uses:` form work at all — so
    the look-ahead does *not* break immediately and instead descends into
    the following `env:` block, producing a phantom
    `ArtifactFetch(job='bogus-name', ref='4242')` from a line that performs
    no artifact fetch whatsoever.
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "migrate off actions/download-artifact@v3"
        env:
          run-id: 4242
          name: bogus-name
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    assert scan_ci_config(tmp_path) == []


def test_github_download_artifact_string_in_comment_not_scanned(tmp_path: Path) -> None:
    """A comment that merely mentions the action string is not a step.

    Unlike the `run:` case above, a bare comment alone did not trigger the
    pre-fix over-match either (the very next line breaks the look-ahead) —
    this is a belt-and-suspenders assertion for the anchored regex, not a
    RED-proving fixture by itself.
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      # TODO: switch to actions/download-artifact@v4 eventually
      - name: Noop
        run: echo hi
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    assert scan_ci_config(tmp_path) == []


# ---------------------------------------------------------------------------
# Fix B: quoted values and the `_GH_NAME` truncation-at-first-space bug
# ---------------------------------------------------------------------------


def test_github_double_quoted_values_have_quotes_stripped(tmp_path: Path) -> None:
    """`run-id:`/`name:` values wrapped in double quotes must not keep the quotes.

    Before the fix, `job` and `ref` came out as `'"build-output"'` and
    `'"12345"'` — quotes and all — which fails to match a correctly declared
    `consumed` entry and, when re-emitted as a fix-it TOML snippet, produces
    invalid TOML (`job = ""build-output""`).
    """
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: "build-output"
          run-id: "12345"
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build-output"
    assert fetches[0].ref == "12345"


def test_github_single_quoted_values_have_quotes_stripped(tmp_path: Path) -> None:
    """`run-id:`/`name:` values wrapped in single quotes must not keep the quotes."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: 'build-output'
          run-id: '12345'
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build-output"
    assert fetches[0].ref == "12345"


def test_github_name_with_spaces_unquoted_is_captured_in_full(tmp_path: Path) -> None:
    """A `name:` value containing spaces must not be truncated at the first space."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: build output bundle
          run-id: 12345
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build output bundle"


def test_github_name_with_spaces_quoted_is_captured_and_unquoted(tmp_path: Path) -> None:
    """A quoted `name:` value containing spaces is captured in full and unquoted."""
    github_snippet = """
name: Build
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: "build output bundle"
          run-id: 12345
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == "build output bundle"


def test_github_download_all_marker_survives_quoted_run_id(tmp_path: Path) -> None:
    """`run-id:`-without-`name:` still records the `"*"` marker when run-id is quoted."""
    github_snippet = """
name: Build
on: push
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          run-id: "999"
"""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(github_snippet)
    fetches = scan_ci_config(tmp_path)
    assert len(fetches) == 1
    assert fetches[0].job == DOWNLOAD_ALL_MARKER
    assert fetches[0].ref == "999"
