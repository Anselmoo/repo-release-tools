from pathlib import Path

from repo_release_tools.tools.ci_artifact_refs import DOWNLOAD_ALL_MARKER, scan_ci_config

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
    # Make it unreadable by removing all permissions
    gitlab_file.chmod(0o000)
    try:
        # Should not raise, just skip the unreadable file
        fetches = scan_ci_config(tmp_path)
        assert len(fetches) == 0
    finally:
        # Restore permissions for cleanup
        gitlab_file.chmod(0o644)


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
    # Make it unreadable by removing all permissions
    github_file.chmod(0o000)
    try:
        # Should not raise, just skip the unreadable file
        fetches = scan_ci_config(tmp_path)
        assert len(fetches) == 0
    finally:
        # Restore permissions for cleanup
        github_file.chmod(0o644)


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
