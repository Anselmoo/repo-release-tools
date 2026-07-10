"""Characterization tests for semver ordering (C11/D1) and MCP/CLI parity (D9, D4/D6).

Pins the behavior contract from ``analysis/the/MODERNIZATION_BRIEF.md`` §5:

- **C11 + D1** (``version/semver.py:104-126``): stable outranks its own pre-release in
  ``Version.sort_key()``; ``newer_versions()`` returns only strictly-newer candidates; the
  4th/5th sort-key elements order pre-release labels *lexically*, which is not SemVer 2.0
  precedence (``rc.10`` sorts before ``rc.2``) — pinned as-is per the brief's SME
  recommendation to pin D1 initially (§7-Q2).
- **D9** (``mcp/tools/version_tools.py:68-105`` vs. ``commands/bump.py``'s full pipeline):
  the MCP ``rrt_bump`` tool only rewrites ``group.version_targets`` — it never touches pin
  targets, never promotes ``[Unreleased]``, and performs no git branch/commit. This is a
  known, non-atomic partial pipeline; Phase 5 unifies it onto ``perform_bump`` and MUST flip
  these assertions (brief §5, defect D9; Phase 5 exit criteria).
- **D4/D6** (``mcp/tools/publish_tools.py:27-142``): ``rrt_publish_snapshot`` defaults
  ``dry_run=True`` and treats ``dry_run=False`` alone as the destructive confirmation — there
  is no separate ``confirm`` flag on this surface, unlike the CLI's explicit
  ``publish-snapshot`` confirmation flag (C3). Pinned as-is; Phase 5 adds parity.
- **MCP/CLI parity seed**: today's overlap/divergence of reported target files between
  ``rrt bump --dry-run`` (CLI) and the MCP dry-run ``rrt_bump`` tool on the same fixture repo,
  which becomes the Phase 5 parity gate.

Conventions: see ``tests/e2e/conftest.py``. MCP-dependent tests additionally carry
``@pytest.mark.mcp`` and call ``pytest.importorskip("fastmcp")`` so the module (including
the fastmcp-free C11/D1 semver tests) collects and runs regardless of whether the ``[mcp]``
extra is installed.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from harness import git, rrt, run_ok

from repo_release_tools.version.semver import Version, newer_versions

pytestmark = pytest.mark.e2e

RepoFactory = Callable[..., Path]

# ---------------------------------------------------------------------------
# C11 / D1 — semver ordering (in-process; sys.path includes src under pytest)
# ---------------------------------------------------------------------------


def test_c11_stable_outranks_its_own_prerelease() -> None:
    """A stable release always sorts after its own pre-release of the same core.

    version/semver.py:104-126 — the 4th sort_key element is 0 for pre-release,
    1 for stable, so ``1.2.0-rc.1`` < ``1.2.0`` for any pre-release label.
    """
    pre = Version.parse("1.2.0-rc.1")
    stable = Version.parse("1.2.0")

    assert pre.sort_key() < stable.sort_key(), (
        f"expected pre-release {pre} to sort before stable {stable}; "
        f"got sort keys {pre.sort_key()!r} >= {stable.sort_key()!r}"
    )
    assert sorted([stable, pre], key=Version.sort_key) == [pre, stable], (
        "sorting [stable, pre] by Version.sort_key should yield [pre, stable]; "
        f"got {[str(v) for v in sorted([stable, pre], key=Version.sort_key)]}"
    )


def test_c11_stable_outranks_prerelease_across_all_channels() -> None:
    """Every pre-release channel (alpha/beta/rc) is outranked by the stable core version."""
    stable = Version.parse("2.0.0")
    for channel in ("alpha.1", "beta.1", "rc.1", "rc.99"):
        pre = Version.parse(f"2.0.0-{channel}")
        assert pre.sort_key() < stable.sort_key(), (
            f"expected 2.0.0-{channel} to sort before 2.0.0; "
            f"got sort keys {pre.sort_key()!r} >= {stable.sort_key()!r}"
        )


def test_c11_newer_versions_returns_only_strictly_newer_ascending() -> None:
    """``newer_versions()`` filters to strictly-newer candidates, ascending by version.

    version/semver.py:122-126 — candidates equal to or older than *current* (including
    the current version's own pre-release) are excluded; survivors are sorted ascending.
    """
    current = Version.parse("1.2.0")
    candidates = [
        Version.parse(v) for v in ["1.2.0-rc.1", "1.2.0", "1.2.1", "1.3.0", "1.1.9", "0.9.0"]
    ]

    result = newer_versions(current, candidates)
    result_strs = [str(v) for v in result]

    assert result_strs == ["1.2.1", "1.3.0"], (
        f"newer_versions(current={current}, candidates={[str(c) for c in candidates]}) "
        f"expected ['1.2.1', '1.3.0'] (strictly newer, ascending); got {result_strs}"
    )


def test_c11_newer_versions_excludes_current_prerelease_of_itself() -> None:
    """A candidate equal to *current* is never "newer" — even a pre-release of the same core."""
    current = Version.parse("1.0.0")
    candidates = [Version.parse("1.0.0-rc.1"), Version.parse("1.0.0")]

    result = newer_versions(current, candidates)

    assert result == [], (
        f"newer_versions(1.0.0, [1.0.0-rc.1, 1.0.0]) expected [] (neither is strictly "
        f"newer than 1.0.0); got {[str(v) for v in result]}"
    )


def test_d1_prerelease_label_ordering_is_lexical_not_semver() -> None:
    """Pre-release numeric label comparison is lexical string comparison, not numeric.

    version/semver.py:104-110 — the 5th sort_key element is the raw pre-release string
    (``self.pre or ""``), compared lexically by Python tuple comparison. SemVer 2.0 §11
    requires numeric identifiers to compare numerically, so ``rc.2`` must precede
    ``rc.10``. This implementation instead sorts the pre-release *label* as a plain
    string, so ``"rc.10" < "rc.2"`` lexically (the character '1' < '2').

    # D1: lexical label comparison — 'rc.10' sorts before 'rc.2'; pinned as-is,
    # SME ruling: pin (violates SemVer 2.0 precedence)
    """
    rc2 = Version.parse("1.0.0-rc.2")
    rc10 = Version.parse("1.0.0-rc.10")

    # NOTE(P1): this is the D1 defect itself — SemVer 2.0 requires rc.2 < rc.10
    # (numeric identifier comparison), but this implementation sorts rc.10 first.
    assert rc10.sort_key() < rc2.sort_key(), (
        f"D1 defect check: expected the (as-is, lexical) sort_key of {rc10} to sort "
        f"*before* {rc2} because '1' < '2' lexically in the pre-release string; "
        f"got {rc10.sort_key()!r} vs {rc2.sort_key()!r} — behavior changed, D1 may be fixed"
    )
    assert sorted([rc2, rc10], key=Version.sort_key) == [rc10, rc2], (
        "D1: lexical pre-release ordering — 'rc.10' sorts before 'rc.2'; pinned as-is, "
        "SME ruling: pin (violates SemVer 2.0 precedence). Sorting [rc.2, rc.10] should "
        f"(as-is) yield [rc.10, rc.2]; got "
        f"{[str(v) for v in sorted([rc2, rc10], key=Version.sort_key)]}"
    )


def test_d1_newer_versions_lexical_ordering_propagates() -> None:
    """``newer_versions()``'s ascending sort inherits D1's lexical pre-release ordering.

    # D1: lexical label comparison — 'rc.10' sorts before 'rc.2'; pinned as-is,
    # SME ruling: pin (violates SemVer 2.0 precedence)
    """
    current = Version.parse("1.0.0-alpha.1")
    candidates = [Version.parse("1.0.0-rc.2"), Version.parse("1.0.0-rc.10")]

    result = newer_versions(current, candidates)
    result_strs = [str(v) for v in result]

    # NOTE(P1): D1 defect — numerically rc.2 (2) < rc.10 (10), but the lexical sort_key
    # orders "rc.10" before "rc.2" because '1' < '2' as characters.
    assert result_strs == ["1.0.0-rc.10", "1.0.0-rc.2"], (
        f"newer_versions ascending order should (as-is, lexically) place rc.10 before "
        f"rc.2; got {result_strs}"
    )


# ---------------------------------------------------------------------------
# D9 — MCP partial bump divergence (in-process MCP tool call, non-dry-run)
# ---------------------------------------------------------------------------

_PIN_PYPROJECT = """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.pin_targets]]
path = "docs/action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\\d+\\.\\d+\\.\\d+)()'

[project]
name = "e2e-fixture"
version = "0.1.0"
requires-python = ">=3.12"
"""


def _make_pin_repo(factory: RepoFactory) -> Path:
    """Build a fixture repo with a pin target and non-empty [Unreleased], then commit it."""
    repo = factory(pyproject=_PIN_PYPROJECT)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "action.md").write_text(
        "- uses: Anselmoo/repo-release-tools@v0.1.0\n", encoding="utf-8"
    )
    git("add", "-A", cwd=repo)
    git("commit", "-m", "chore: add pin target doc", cwd=repo)
    return repo


@pytest.mark.mcp
def test_d9_mcp_bump_updates_version_targets_only(
    e2e_repo_factory: RepoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP ``rrt_bump`` (non-dry-run) writes version targets but leaves pins/changelog/git alone.

    # D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto
    # perform_bump and MUST flip these assertions.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    repo = _make_pin_repo(e2e_repo_factory)
    pin_doc = repo / "docs" / "action.md"
    changelog = repo / "CHANGELOG.md"
    pyproject = repo / "pyproject.toml"

    original_changelog = changelog.read_text(encoding="utf-8")
    original_pin_doc = pin_doc.read_text(encoding="utf-8")

    monkeypatch.chdir(repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            result = await client.call_tool("rrt_bump", {"level": "patch", "dry_run": False})
            return result.data

    data = asyncio.run(_call())
    output = repr(data)

    assert isinstance(data, list) and len(data) == 1, f"expected one group result; got {output}"
    bump_result = data[0]
    assert bump_result.error is None, f"unexpected MCP bump error: {output}"
    assert bump_result.applied is True, f"expected applied=True for dry_run=False: {output}"
    assert bump_result.new == "0.1.1", f"expected new version 0.1.1: {output}"

    # Version target WAS updated (this is the part D9 gets "right").
    pyproject_text = pyproject.read_text(encoding="utf-8")
    assert "0.1.1" in pyproject_text, (
        f"D9: expected pyproject.toml version target to be updated to 0.1.1; "
        f"content:\n{pyproject_text}\nMCP result: {output}"
    )

    # D9: pin targets are NOT updated by the MCP bump tool (unlike commands/bump.py's
    # apply_version, which applies group.pin_targets + config.global_pin_targets).
    pin_doc_text = pin_doc.read_text(encoding="utf-8")
    assert pin_doc_text == original_pin_doc, (
        f"D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto "
        f"perform_bump and MUST flip this assertion. Expected docs/action.md to be "
        f"UNCHANGED (still v0.1.0) after MCP rrt_bump; got:\n{pin_doc_text}"
    )

    # D9: [Unreleased] is NOT promoted by the MCP bump tool.
    changelog_text = changelog.read_text(encoding="utf-8")
    assert changelog_text == original_changelog, (
        f"D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto "
        f"perform_bump and MUST flip this assertion. Expected CHANGELOG.md to be "
        f"UNCHANGED (still [Unreleased]) after MCP rrt_bump; got:\n{changelog_text}"
    )
    assert "[Unreleased]" in changelog_text, (
        f"D9: [Unreleased] heading must survive untouched; got:\n{changelog_text}"
    )
    assert "[0.1.1]" not in changelog_text, (
        f"D9: no [0.1.1] section should have been created by MCP bump; got:\n{changelog_text}"
    )


@pytest.mark.mcp
def test_d9_mcp_bump_creates_no_git_branch_or_commit(
    e2e_repo_factory: RepoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP ``rrt_bump`` (non-dry-run) never branches or commits, unlike the CLI's full pipeline.

    # D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto
    # perform_bump and MUST flip these assertions.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    repo = _make_pin_repo(e2e_repo_factory)

    before_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip()
    before_log = git("log", "--oneline", cwd=repo).stdout

    monkeypatch.chdir(repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            result = await client.call_tool("rrt_bump", {"level": "patch", "dry_run": False})
            return result.data

    data = asyncio.run(_call())

    after_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip()
    after_log = git("log", "--oneline", cwd=repo).stdout
    branch_list = git("branch", "--list", cwd=repo).stdout
    status = git("status", "--short", cwd=repo).stdout

    assert after_branch == before_branch == "main", (
        f"D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto "
        f"perform_bump and MUST flip this assertion. Expected to remain on 'main'; "
        f"was {before_branch!r}, now {after_branch!r}. MCP result: {data!r}"
    )
    assert "release/v0.1.1" not in branch_list, (
        f"D9: no release branch should be created by MCP bump; branches:\n{branch_list}"
    )
    assert after_log == before_log, (
        f"D9: MCP bump is a partial pipeline — pinned as-is; Phase 5 unifies it onto "
        f"perform_bump and MUST flip this assertion. Expected no new commit; "
        f"before:\n{before_log}\nafter:\n{after_log}"
    )
    assert "pyproject.toml" in status, (
        f"D9: the version-target write should be left as an uncommitted, unstaged change "
        f"(no git add/commit happens); git status --short:\n{status}"
    )


# ---------------------------------------------------------------------------
# D4/D6 — MCP publish-snapshot confirmation shape
# ---------------------------------------------------------------------------


def _init_bare_remote(tmp_path: Path) -> Path:
    """Create a local bare git repo to use as a safe force-push target."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    run_ok(["git", "init", "--bare", "-q"], cwd=bare)
    return bare


@pytest.mark.mcp
def test_d4_publish_snapshot_dry_run_defaults_true(
    e2e_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rrt_publish_snapshot`` defaults to ``dry_run=True`` when the argument is omitted.

    # D4/D6: weaker than CLI's explicit confirm flag — pinned as-is; Phase 5 adds parity.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    bare = _init_bare_remote(tmp_path)
    git("remote", "add", "snapshot", str(bare), cwd=e2e_repo)

    monkeypatch.chdir(e2e_repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            # dry_run intentionally omitted: pin the *default*.
            result = await client.call_tool(
                "rrt_publish_snapshot", {"remote": "snapshot", "branch": "main"}
            )
            return result.data

    data = asyncio.run(_call())

    assert data.dry_run is True, (
        f"D4/D6: expected dry_run to default to True when omitted; got {data!r}"
    )
    assert data.published is False, f"dry-run-by-default must not publish; got {data!r}"

    branches = git("branch", "-a", "--list", cwd=bare).stdout
    assert branches.strip() == "", (
        f"D4/D6: default dry_run=True must push nothing to the remote; "
        f"bare repo branches:\n{branches!r}"
    )


@pytest.mark.mcp
def test_d4_publish_snapshot_dry_run_true_pushes_nothing(
    e2e_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``dry_run=True`` (explicit) previews the publish but pushes nothing to the remote.

    # D4/D6: weaker than CLI's explicit confirm flag — pinned as-is; Phase 5 adds parity.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    bare = _init_bare_remote(tmp_path)
    git("remote", "add", "snapshot", str(bare), cwd=e2e_repo)

    monkeypatch.chdir(e2e_repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            result = await client.call_tool(
                "rrt_publish_snapshot",
                {"remote": "snapshot", "branch": "main", "dry_run": True},
            )
            return result.data

    data = asyncio.run(_call())

    assert data.published is False, f"expected published=False for dry_run=True; got {data!r}"
    assert data.error is None, f"expected no error for a clean dry-run preview; got {data!r}"

    branches = git("branch", "-a", "--list", cwd=bare).stdout
    assert branches.strip() == "", (
        f"D4/D6: dry_run=True must push nothing to the remote; "
        f"bare repo branches after call:\n{branches!r}"
    )


@pytest.mark.mcp
def test_d6_publish_snapshot_dry_run_false_alone_is_the_confirmation(
    e2e_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``dry_run=False`` alone force-pushes — there is no separate ``confirm`` parameter.

    Exercised against a local bare repo only, never a real remote.

    # D4/D6: weaker than CLI's explicit confirm flag — pinned as-is; Phase 5 adds parity.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server
    from repo_release_tools.mcp.tools import publish_tools

    # NOTE(P1) D4/D6: confirm there is no separate confirmation parameter on this tool by
    # inspecting the registered function's signature directly (belt-and-braces alongside
    # the behavioral proof below).
    class _Capture:
        def __init__(self) -> None:
            self.fn: Any = None

        def tool(self, *_args: object, **_kwargs: object) -> Callable[[Any], Any]:
            def _decorator(fn: Any) -> Any:
                if fn.__name__ == "rrt_publish_snapshot":
                    self.fn = fn
                return fn

            return _decorator

    capture = _Capture()
    publish_tools.register(cast("Any", capture))  # duck-typed FastMCP stand-in
    assert capture.fn is not None
    param_names = set(inspect.signature(capture.fn).parameters)
    assert "confirm" not in param_names, (
        f"D4/D6: expected no separate 'confirm' parameter on rrt_publish_snapshot "
        f"(dry_run=False alone is the destructive confirmation); got params {param_names}"
    )

    bare = _init_bare_remote(tmp_path)
    git("remote", "add", "snapshot", str(bare), cwd=e2e_repo)

    monkeypatch.chdir(e2e_repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            # No 'confirm' kwarg exists on this surface — dry_run=False is the only gate.
            result = await client.call_tool(
                "rrt_publish_snapshot",
                {"remote": "snapshot", "branch": "main", "dry_run": False},
            )
            return result.data

    data = asyncio.run(_call())

    assert data.published is True, (
        f"D4/D6: dry_run=False alone (no separate confirm flag) must force-push; got {data!r}"
    )
    assert data.error is None, f"expected a clean publish; got {data!r}"

    branches = run_ok(["git", "branch", "--list", "main"], cwd=bare).stdout
    assert "main" in branches, (
        f"D4/D6: expected the snapshot to land on {bare}'s main branch; branches:\n{branches!r}"
    )


# ---------------------------------------------------------------------------
# MCP/CLI parity seed
# ---------------------------------------------------------------------------


@pytest.mark.mcp
def test_parity_cli_and_mcp_dry_run_agree_on_bumped_version(
    e2e_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI ``rrt bump patch --dry-run`` and MCP dry-run ``rrt_bump`` agree on the new version.

    Both surfaces read the same current version (0.1.0) and compute the same next
    version (0.1.1) for a patch bump on the same fixture repo. This is the narrowest
    possible parity claim; the wider divergence (changelog/pins/git) is pinned by the
    D9 tests above and becomes the Phase 5 parity gate.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    cli_result = rrt("bump", "patch", "--dry-run", cwd=e2e_repo)
    assert cli_result.returncode == 0, (
        f"CLI dry-run bump failed.\nstdout:\n{cli_result.stdout}\nstderr:\n{cli_result.stderr}"
    )
    assert "0.1.1" in cli_result.stdout, (
        f"expected CLI dry-run to report new version 0.1.1; stdout:\n{cli_result.stdout}"
    )

    monkeypatch.chdir(e2e_repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            result = await client.call_tool("rrt_bump", {"level": "patch", "dry_run": True})
            return result.data

    mcp_data = asyncio.run(_call())
    mcp_result = mcp_data[0]

    assert mcp_result.current == "0.1.0", (
        f"MCP dry-run should read the same current version as the CLI (0.1.0); got {mcp_result!r}"
    )
    assert mcp_result.new == "0.1.1", (
        f"MCP dry-run should compute the same new version as the CLI (0.1.1); "
        f"got {mcp_result!r}. CLI stdout:\n{cli_result.stdout}"
    )
    assert mcp_result.applied is False, f"MCP dry-run must not apply; got {mcp_result!r}"


@pytest.mark.mcp
def test_parity_cli_reports_more_target_files_than_mcp_dry_run(
    e2e_repo_factory: RepoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Divergence seed: CLI dry-run mentions pins/changelog/git; MCP dry-run reports only targets.

    This is today's overlap/divergence baseline. The CLI's dry-run output surfaces the
    changelog file and pin-target files as "would update" targets; the MCP ``rrt_bump``
    dry-run response only ever reports ``group.version_targets`` (never pins, never
    changelog). Phase 5's MCP/CLI parity gate must make these two surfaces agree.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from repo_release_tools.mcp.server import create_server

    repo = _make_pin_repo(e2e_repo_factory)

    cli_result = rrt("bump", "patch", "--dry-run", cwd=repo)
    assert cli_result.returncode == 0, (
        f"CLI dry-run bump failed.\nstdout:\n{cli_result.stdout}\nstderr:\n{cli_result.stderr}"
    )
    # CLI dry-run surfaces the pin-target doc and the changelog as planned updates.
    assert "action.md" in cli_result.stdout, (
        f"expected CLI dry-run to mention the pin-target file docs/action.md; "
        f"stdout:\n{cli_result.stdout}"
    )
    assert "CHANGELOG.md" in cli_result.stdout, (
        f"expected CLI dry-run to mention CHANGELOG.md; stdout:\n{cli_result.stdout}"
    )

    monkeypatch.chdir(repo)

    async def _call() -> Any:
        server = create_server()
        async with Client(server) as client:
            result = await client.call_tool("rrt_bump", {"level": "patch", "dry_run": True})
            return result.data

    mcp_data = asyncio.run(_call())
    output = repr(mcp_data)

    # MCP's BumpGroupResult carries no per-file target list at all — only group/current/new.
    assert len(mcp_data) == 1, f"expected a single group result; got {output}"
    assert not hasattr(mcp_data[0], "targets"), (
        f"MCP BumpGroupResult unexpectedly grew a per-file targets field: {output}"
    )
    # NOTE(P1): today the MCP dry-run response has no field enumerating which files would
    # change (pin targets, changelog) the way the CLI's dry-run narration does — this is
    # exactly the divergence Phase 5's "MCP rrt_bump result ≡ CLI bump result" contract
    # test (brief §5 Phase 5 exit criteria) must close.
