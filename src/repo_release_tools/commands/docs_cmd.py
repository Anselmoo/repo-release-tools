"""rrt docs — extract and manage source-owned documentation blocks.

## Overview

`rrt docs` provides a specialized toolset for managing documentation that lives
directly within the source code. By extracting inline blocks from multiple
programming languages and verifying them against a cryptographic lockfile, the
tool ensures that your documentation stays accurate, up-to-date, and tightly
coupled with the implementation.

It supports a variety of languages including Python, TypeScript, Go, Rust, and
several shell dialects, using regex-based extraction that doesn't require
heavyweight AST parsers.

## Responsibilities

- extract inline documentation blocks from source files recursively
- generate documentation in multiple formats (Markdown, JSON, TOML, Rich)
- maintain a documentation lockfile (`docs.lock.toml`) to detect drift in CI
- emit machine-readable indices of CLI commands and arguments
- suggest or scaffold missing module docstrings for project alignment

## Sub-actions

- **generate**: Scans the source tree and emits documentation. Use `--format toml`
  to write or update the documentation lockfile.
- **check**: Validates that the current documentation lockfile matches the
  source tree. Exits with a non-zero status if drift is detected.
- **publish**: Generates the complete Markdown reference documentation from
  the live CLI parser.
- **inject**: Synchronizes shared anchor blocks (headers, footers) across
  multiple Markdown files.
- **suggest**: Analyzes Python modules for missing or thin docstrings and
  provides scaffolded improvements.
- **api**: Emits a structured index of all `rrt` commands for use in
  external tooling.

## Extraction modes

Controlled by `[tool.rrt.docs] extraction_mode` in config:

- `explicit` (default): only extract blocks preceded by a ``# sym: NAME``
  (Python/Bash/PowerShell) or ``// sym: NAME`` (JS/TS/Go/Rust) marker.
  PowerShell also supports ``<# sym: NAME #>``.
- `implicit`: extract language-native docstrings / comment blocks.
- `both`: explicit markers take priority; fall back to implicit.

## Supported languages

| Slug        | Extensions               |
|-------------|--------------------------|
| python      | .py                      |
| ts          | .ts, .tsx                |
| js          | .js, .mjs, .cjs, .jsx    |
| go          | .go                      |
| rust        | .rs                      |
| bash        | .sh, .bash, .zsh         |
| fish        | .fish                    |
| powershell  | .ps1, .psm1, .psd1       |

## Lockfile

`rrt docs generate --format toml` writes `.rrt/docs.lock.toml` (default),
a human-readable TOML file tracking each source file's SHA-256 hash and the
symbols it exports.  Use `rrt docs check` or the `rrt-docs-check` pre-commit
hook to fail fast when docs drift from source.

## Examples

```bash
rrt docs generate --format rich            # colourised terminal preview
rrt docs generate --format toml --dry-run  # show lock without writing
rrt docs check                             # exits 1 if lockfile is stale
rrt docs api --format json                 # machine-readable API index
```

## Related docs

- [CLI reference](rrt-cli.md)
- [Project tree command](tree.md)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools.commands.docs_suggest import cmd_docs_suggest
from repo_release_tools.config import (
    DocsConfig,
    RrtConfig,
    is_missing_tool_rrt_error,
    load_config,
)
from repo_release_tools.docs.extractor import DocEntry, extract_docs_from_dir
from repo_release_tools.docs.formats import render
from repo_release_tools.state import build_lock, docs_lock_path, lock_is_current
from repo_release_tools.tools.inject import ANCHOR_START_TOKEN as _MD_ANCHOR_START_TOKEN
from repo_release_tools.tools.inject import (
    MDX_ANCHOR_START_TOKEN,
    _detect_inject_format,
    apply_generated_docs,
    ensure_anchor_stub,
    insert_anchor_stub_str,
    replace_anchored_block,
)
from repo_release_tools.tools.platform import (
    PLATFORM_URL_TEMPLATES,
    detect_platform,
    render_badge,
)
from repo_release_tools.tools.toc import parse_headings, render_toc
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter

# ---------------------------------------------------------------------------
# Source-owned topic docs
# ---------------------------------------------------------------------------

SOURCE_OWNED_TOPIC_DOCS = (("docs", __doc__ or ""),)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_for_cwd(cwd: Path) -> DocsConfig:
    cfg = load_config(cwd)
    return cfg.docs if cfg.docs is not None else DocsConfig()


def _build_docs_lock_sources(entries: list[DocEntry]) -> list[dict[str, object]]:
    """Group extracted doc entries into the lockfile source schema."""
    from collections import defaultdict

    from repo_release_tools.state import hash_content

    by_file: dict[str, list[DocEntry]] = defaultdict(list)
    for entry in entries:
        by_file[entry.source_file].append(entry)

    sources: list[dict[str, object]] = []
    for src_file, src_entries in by_file.items():
        sorted_entries = sorted(src_entries, key=lambda e: e.name)
        combined = "".join(e.hash for e in sorted_entries)
        sources.append(
            {
                "source_file": src_file,
                "hash": hash_content(combined),
                "symbols": [e.name for e in sorted_entries],
                "lang": src_entries[0].lang,
            },
        )
    return sources


# ---------------------------------------------------------------------------
# generate sub-action
# ---------------------------------------------------------------------------


def _cmd_generate(args: argparse.Namespace) -> int:
    verbose: int = getattr(args, "verbose", 0) or 0
    cwd = Path(args.root)
    p = DryRunPrinter(dry_run=args.dry_run, verbose=verbose)
    p.header("rrt docs generate")

    config = _config_for_cwd(cwd)

    # Override languages / formats from CLI if provided
    if getattr(args, "lang", None):
        raw_langs = [l.strip().lower() for l in args.lang.split(",") if l.strip()]  # noqa: E741
        from repo_release_tools.config import _VALID_LANGUAGES

        if invalid := [ln for ln in raw_langs if ln not in _VALID_LANGUAGES]:
            p.line(
                f"Unsupported languages: {invalid}. Supported: {list(_VALID_LANGUAGES)}",
                ok=False,
                stream=sys.stderr,
            )
            return 1
        from dataclasses import replace as dc_replace

        config = dc_replace(config, languages=tuple(raw_langs))

    fmt = getattr(args, "format", None) or config.formats[0]

    p.section("Scanning sources")
    entries = extract_docs_from_dir(cwd, config)
    if not entries:
        p.warn("No documentation entries found.")
        return 0

    p.ok(f"Found {len(entries)} doc entries")

    p.section(f"Rendering ({fmt})")

    if args.dry_run and fmt == "toml":
        # In dry-run mode: build lock but don't write
        sources = _build_docs_lock_sources(entries)
        build_lock(sources)  # validate structure; don't write
        lock_path = docs_lock_path(cwd, config.lock_file)
        p.would_write(str(lock_path), "docs lockfile (dry-run, not written)")
        return 0

    output = render(fmt, entries, config, root=cwd)

    match fmt:
        case "toml":
            lock_path = docs_lock_path(cwd, config.lock_file)
            p.ok(f"Lockfile written: {lock_path}")
        case "md" | "txt" | "json":
            sys.stdout.write(output)
        case "rich":
            sys.stdout.write(output + "\n")
        case "clipboard":
            sys.stdout.write(output)
            p.ok("Output written to stdout (pipe to clipboard utility if needed)")

    p.footer("Done.")
    return 0


# ---------------------------------------------------------------------------
# check sub-action
# ---------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    verbose: int = getattr(args, "verbose", 0) or 0
    cwd = Path(args.root)
    p = VerbosePrinter(verbose=verbose)
    config = _config_for_cwd(cwd)

    lock_file = getattr(args, "lock_file", None) or config.lock_file
    lock_path = docs_lock_path(cwd, lock_file)

    entries = extract_docs_from_dir(cwd, config)

    sources = _build_docs_lock_sources(entries)

    is_current, messages = lock_is_current(lock_path, sources)
    if is_current:
        p.ok("docs lockfile is current")
        return 0

    p.line("docs lockfile is stale:", ok=False, stream=sys.stderr)
    for msg in messages:
        p.warn(msg, stream=sys.stderr)
    p.line(
        "Run 'rrt docs generate --format toml' to regenerate the lockfile.",
        ok=False,
        stream=sys.stderr,
    )
    return 1


# ---------------------------------------------------------------------------
# Publish (generate + write CLI reference docs)
# ---------------------------------------------------------------------------


def _cmd_publish(args: argparse.Namespace) -> int:
    """Write all generated CLI-reference doc files to disk (or check for staleness)."""
    verbose: int = getattr(args, "verbose", 0) or 0
    from repo_release_tools.docs import publisher as docs_publisher  # noqa: PLC0415

    check: bool = getattr(args, "check", False)
    dry_run: bool = getattr(args, "dry_run", False)
    fail_on_change: bool = getattr(args, "fail_on_change", False)
    root = Path(getattr(args, "root", ".")).resolve()

    cfg = None
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        pass

    rendered_targets: list[tuple[docs_publisher.DocTarget, str]] = []
    consistency_issues: list[str] = []
    for target in docs_publisher.iter_generated_doc_targets():
        rendered = target.render()
        rendered_targets.append((target, rendered))
        consistency_issues.extend(docs_publisher.validate_generated_page(target, rendered))

    if consistency_issues:
        for issue in consistency_issues:
            sys.stderr.write(f"{issue}\n")
        return 1

    if dry_run:
        p = DryRunPrinter(dry_run=True, verbose=verbose)
        for target, _rendered in rendered_targets:
            p.would_write(str(target.output_path))
        return 0

    exit_code = 0
    for target, content in rendered_targets:
        full_content = (
            _embed_shared_blocks_in_content(content, target.output_path, root, cfg)
            if target.anchor_id is None
            else content
        )
        full_content = _embed_toc_in_content(full_content, target.output_path)
        exit_code = max(
            exit_code,
            apply_generated_docs(
                full_content,
                output_path=target.output_path,
                check=check,
                write=not check,
                fail_on_change=fail_on_change,
                stdout=sys.stdout,
                stderr=sys.stderr,
                anchor_id=target.anchor_id,
            ),
        )
    return exit_code


# ---------------------------------------------------------------------------
# Inject (shared anchor blocks from config)
# ---------------------------------------------------------------------------


def _effective_platform(docs: DocsConfig) -> str:
    """Return the effective platform, auto-detecting from source_repo_url if needed."""
    if docs.platform:
        return docs.platform
    if docs.source_repo_url:
        return detect_platform(docs.source_repo_url)
    return "generic"


def _effective_source_url_template(docs: DocsConfig, platform: str) -> str:
    """Return the source URL template, defaulting to the per-platform template."""
    if docs.source_url_template:
        return docs.source_url_template
    return PLATFORM_URL_TEMPLATES.get(platform, PLATFORM_URL_TEMPLATES["generic"])


def _badge_assets_dir_for_target(docs: DocsConfig) -> str:
    """Return the root-absolute badge assets URL path for *docs*.

    Astro serves everything under a project's ``public/`` directory at the
    site root, so the physical ``docs/public/...`` prefix is stripped and the
    configured ``base_url`` (e.g. an Astro/Starlight ``base:`` path such as
    ``/repo-release-tools``) is prepended. The result is a single root-absolute
    URL path that is valid regardless of which page embeds the badge — unlike
    the old Jekyll-era approach, no per-target-location depth math is needed.

    Args:
        docs: Docs configuration holding badge style, configured assets dir,
            and the site's ``base_url``.

    Returns:
        A POSIX-style, root-absolute path string suitable for markdown image
        links from any page in the site.
    """
    if docs.badge_style != "svg":
        return docs.badge_assets_dir

    assets_path = Path(docs.badge_assets_dir)
    public_prefix = Path("docs/public")
    try:
        served_path = assets_path.relative_to(public_prefix)
    except ValueError:
        served_path = assets_path

    base_url = docs.base_url.rstrip("/")
    return f"{base_url}/{served_path.as_posix()}"


def _expand_platform_vars(content: str, docs: DocsConfig) -> str:
    """Expand {platform}, {platform_label}, {platform_badge}, {platform_badge_inline}."""
    from repo_release_tools.tools.platform import get_display_label  # noqa: PLC0415

    platform = _effective_platform(docs)
    label = get_display_label(platform)
    repo_url = docs.source_repo_url or ""
    badge_assets_dir = _badge_assets_dir_for_target(docs)

    if "{platform_badge}" in content or "{platform_badge_inline}" in content:
        badge_linked = render_badge(
            platform,
            repo_url=repo_url,
            badge_style=docs.badge_style,
            badge_assets_dir=badge_assets_dir,
            badge_variant=docs.badge_variant,
            label=label,
            linked=True,
        )
        badge_inline = render_badge(
            platform,
            repo_url=repo_url,
            badge_style=docs.badge_style,
            badge_assets_dir=badge_assets_dir,
            badge_variant=docs.badge_variant,
            label=label,
            linked=False,
        )
        content = content.replace("{platform_badge}", badge_linked)
        content = content.replace("{platform_badge_inline}", badge_inline)

    # Expand specific variants if requested
    for variant in [
        "color",
        "dark",
        "light",
        "reto_dark",
        "reto_light",
        "adaptive",
        "adaptive_reto",
    ]:
        var_name = f"{{platform_badge_{variant}}}"
        actual_variant = variant.replace("_", "-")
        if var_name in content:
            badge = render_badge(
                platform,
                repo_url=repo_url,
                badge_style=docs.badge_style,
                badge_assets_dir=badge_assets_dir,
                badge_variant=actual_variant,
                label=label,
                linked=True,
            )
            content = content.replace(var_name, badge)

    content = content.replace("{platform}", platform)
    content = content.replace("{platform_label}", label)
    return content


def _cmd_inject(args: argparse.Namespace) -> int:
    """Inject or verify all shared anchor blocks from [tool.rrt.docs.shared_blocks]."""
    verbose: int = getattr(args, "verbose", 0) or 0
    from repo_release_tools import __version__ as rrt_version  # noqa: PLC0415

    check: bool = getattr(args, "check", False)
    dry_run: bool = getattr(args, "dry_run", False)
    add_anchors: bool = getattr(args, "add_anchors", False)
    root = Path(getattr(args, "root", ".")).resolve()

    cfg = None
    try:
        cfg = load_config(root)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        if not is_missing_tool_rrt_error(exc):
            raise

    if cfg is None:
        p = VerbosePrinter(verbose=verbose)
        p.action("No rrt config found; skipping shared_blocks injection.")
        return 0

    if cfg.docs is not None and cfg.docs.shared_blocks:
        if dry_run:
            p = DryRunPrinter(dry_run=True, verbose=verbose)
            for block in cfg.docs.shared_blocks:
                p.would_write(", ".join(block.targets), detail=f"anchor: {block.anchor_id!r}")
            return 0

        repo_url = (cfg.docs.source_repo_url or "") if cfg.docs else ""
        p = VerbosePrinter(verbose=verbose)

        exit_code = 0
        for block in cfg.docs.shared_blocks:
            content = block.content.rstrip("\n")

            content = content.replace("{version}", rrt_version)
            content = content.replace("{repo_url}", repo_url)

            matched = sorted({p for pattern in block.targets for p in root.glob(pattern)})
            if not matched:
                p.warn(f"SharedBlock {block.anchor_id!r}: no target files matched.")
                continue

            for target_path in matched:
                rendered_content = content
                if cfg.docs:
                    rendered_content = _expand_platform_vars(rendered_content, cfg.docs)
                if add_anchors:
                    _prepend_anchor_if_missing(
                        target_path,
                        block.anchor_id,
                        position=block.position,
                        before_blank_lines=block.before_blank_lines,
                        after_blank_lines=block.after_blank_lines,
                    )
                exit_code = max(
                    exit_code,
                    apply_generated_docs(
                        rendered_content,
                        output_path=target_path,
                        check=check,
                        write=not check,
                        fail_on_change=False,
                        stdout=sys.stdout,
                        stderr=sys.stderr,
                        anchor_id=block.anchor_id,
                        stale_hint="rrt docs inject --check",
                    ),
                )

        return exit_code

    return 0


def _embed_shared_blocks_in_content(
    content: str,
    target_output_path: Path,
    root: Path,
    cfg: RrtConfig | None,
) -> str:
    """Return *content* with all matching shared blocks embedded in-memory.

    For each shared block whose target glob matches *target_output_path*, an
    anchor stub is inserted and immediately filled with the expanded block
    content.  This lets ``rrt docs publish`` produce the complete expected file
    state — including header/footer regions — so that ``publish --check`` and
    a subsequent ``rrt docs inject`` are both consistent.
    """
    from repo_release_tools import __version__ as rrt_version  # noqa: PLC0415

    if not (cfg and cfg.docs and cfg.docs.shared_blocks):
        return content

    repo_url = cfg.docs.source_repo_url or ""
    abs_target = (root / target_output_path).resolve()

    for block in cfg.docs.shared_blocks:
        matched = {p.resolve() for pattern in block.targets for p in root.glob(pattern)}
        if abs_target not in matched:
            continue

        block_content = block.content.rstrip("\n")
        block_content = block_content.replace("{version}", rrt_version)
        block_content = block_content.replace("{repo_url}", repo_url)
        block_content = _expand_platform_vars(block_content, cfg.docs)

        content = insert_anchor_stub_str(
            content,
            block.anchor_id,
            position=block.position,
            before_blank_lines=block.before_blank_lines,
            after_blank_lines=block.after_blank_lines,
        )
        replaced = replace_anchored_block(content, anchor_id=block.anchor_id, content=block_content)
        if replaced is not None:
            content = replaced

    return content


_TOC_ANCHOR = "toc"


def _embed_toc_in_content(
    content: str,
    output_path: Path,
    *,
    min_level: int = 2,
    max_level: int = 3,
) -> str:
    fmt = _detect_inject_format(output_path)
    toc_start = (
        f"{{/* {MDX_ANCHOR_START_TOKEN}{_TOC_ANCHOR} */}}"
        if fmt == "mdx"
        else f"<!-- {_MD_ANCHOR_START_TOKEN}{_TOC_ANCHOR} -->"
    )
    if toc_start not in content:
        return content
    headings = parse_headings(content)
    if not headings:
        return content
    toc = render_toc(headings, min_level=min_level, max_level=max_level)
    try:
        replaced = replace_anchored_block(content, anchor_id=_TOC_ANCHOR, content=toc, fmt=fmt)
    except ValueError:
        return content
    return replaced if replaced is not None else content


def _restore_shared_block_stubs(root: Path, rendered_targets: list) -> None:
    """Re-add anchor stubs for full-replacement targets after publish."""
    cfg = None
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        return
    if not (cfg and cfg.docs and cfg.docs.shared_blocks):
        return
    for target, _content in rendered_targets:
        if target.anchor_id is not None:
            continue
        abs_target = (root / target.output_path).resolve()
        for block in cfg.docs.shared_blocks:
            matched = {p.resolve() for pattern in block.targets for p in root.glob(pattern)}
            if abs_target in matched:
                _prepend_anchor_if_missing(
                    abs_target,
                    block.anchor_id,
                    position=block.position,
                    before_blank_lines=block.before_blank_lines,
                    after_blank_lines=block.after_blank_lines,
                )


def _prepend_anchor_if_missing(
    path: Path,
    anchor_id: str,
    *,
    position: str = "prepend",
    before_blank_lines: int = 0,
    after_blank_lines: int = 1,
) -> None:
    """Ensure an empty anchor pair exists using the requested placement."""
    ensure_anchor_stub(
        path,
        anchor_id,
        position=position,
        before_blank_lines=before_blank_lines,
        after_blank_lines=after_blank_lines,
    )


# ---------------------------------------------------------------------------
# Badges (generate platform SVG badge files)
# ---------------------------------------------------------------------------


def _cmd_badges(args: argparse.Namespace) -> int:
    """Generate platform SVG badge files into docs/public/assets/badges/."""
    verbose: int = getattr(args, "verbose", 0) or 0
    from repo_release_tools.tools.platform import KNOWN_LABEL_KEYS, get_badge_svg  # noqa: PLC0415

    check: bool = getattr(args, "check", False)
    dry_run: bool = getattr(args, "dry_run", False)
    root = Path(getattr(args, "root", ".")).resolve()
    output_dir_arg: str | None = getattr(args, "output_dir", None)
    all_platforms: bool = getattr(args, "all_platforms", False)
    platform_arg: str | None = getattr(args, "platform", None)
    variant_arg: str | None = getattr(args, "variant", None)

    cfg = None
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        pass

    docs = (cfg.docs if cfg and cfg.docs else None) or DocsConfig()
    assets_dir = output_dir_arg or docs.badge_assets_dir
    output_path = root / assets_dir

    if all_platforms or platform_arg is None:
        platforms = list(KNOWN_LABEL_KEYS)
    else:
        platforms = [platform_arg]

    variants = (
        ["color", "dark", "light", "reto-dark", "reto-light"]
        if variant_arg is None
        else [variant_arg]
    )

    p = DryRunPrinter(dry_run=dry_run, verbose=verbose)
    p.header("rrt docs badges")

    exit_code = 0
    for plat in platforms:
        for variant in variants:
            svg = get_badge_svg(plat, variant)
            suffix = f"-{variant}" if variant != "color" else ""
            dest = output_path / f"{plat}{suffix}.svg"
            if dry_run:
                p.would_write(str(dest), detail=f"platform: {plat!r}, variant: {variant!r}")
                continue
            exit_code = max(
                exit_code,
                apply_generated_docs(
                    svg,
                    output_path=dest,
                    check=check,
                    write=not check,
                    fail_on_change=False,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    stale_hint="rrt docs badges",
                ),
            )

    return exit_code


# ---------------------------------------------------------------------------
# API index sub-action
# ---------------------------------------------------------------------------


def _cmd_api(args: argparse.Namespace) -> int:
    """Emit a structured index of all rrt CLI commands and arguments."""
    verbose: int = getattr(args, "verbose", 0) or 0
    from repo_release_tools.cli import build_parser  # noqa: PLC0415
    from repo_release_tools.docs.api_index import (  # noqa: PLC0415
        build_api_index,
        load_hooks,
        render_api_json,
        render_api_md,
        render_api_txt,
    )

    fmt: str = getattr(args, "format", None) or "md"
    output_arg: str | None = getattr(args, "output", None)
    dry_run: bool = getattr(args, "dry_run", False)
    root = Path(getattr(args, "root", ".")).resolve()

    p = DryRunPrinter(dry_run=dry_run, verbose=verbose)

    # When the rendered payload goes directly to stdout, suppress the status
    # header/footer so callers can safely pipe output (e.g. to `jq`).
    emit_to_stdout = not output_arg

    if not emit_to_stdout:
        p.header("rrt docs api")

    hook_map = load_hooks(root)
    parser = build_parser()
    entries = build_api_index(parser, hook_map=hook_map)

    match fmt:
        case "md":
            rendered = render_api_md(entries)
        case "txt":
            rendered = render_api_txt(entries)
        case "json":
            rendered = render_api_json(entries)
        case _:
            p.line(
                f"Unsupported API format {fmt!r}. Use md, txt, or json.",
                ok=False,
                stream=sys.stderr,
            )
            return 1

    if output_arg and not dry_run:
        output_path = Path(output_arg)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        p.ok(f"API index written: {output_path}")
    elif dry_run and output_arg:
        output_path = Path(output_arg)
        if not output_path.is_absolute():
            output_path = root / output_path
        p.would_write(str(output_path), detail=f"rrt API index ({fmt})")
    else:
        sys.stdout.write(rendered)

    if not emit_to_stdout:
        p.footer("Done.")
    return 0


# ---------------------------------------------------------------------------
# Suggest docstrings (scaffold + lint)
# ---------------------------------------------------------------------------


def _cmd_suggest(args: argparse.Namespace) -> int:
    """Suggest or apply rich module docstrings for command modules."""
    return cmd_docs_suggest(args)


# ---------------------------------------------------------------------------
# Map (per-directory purpose docs)
# ---------------------------------------------------------------------------


def _cmd_map(args: argparse.Namespace) -> int:
    """Generate or check per-directory purpose docs via `rrt docs map`."""
    from repo_release_tools.commands.docs_map import generate  # noqa: PLC0415
    from repo_release_tools.commands.docs_map_lock import (  # noqa: PLC0415
        detect_drift,
        refresh_lockfile,
    )

    verbose: int = getattr(args, "verbose", 0) or 0
    cwd = Path(args.root)
    docs_cfg = _config_for_cwd(cwd)
    p = DryRunPrinter(dry_run=getattr(args, "dry_run", False), verbose=verbose)

    if docs_cfg.map is None:
        p.line(
            "[tool.rrt.docs.map] is not configured.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    map_cfg = docs_cfg.map
    check: bool = getattr(args, "check", False)

    if check:
        drift = detect_drift(map_cfg, cwd)
        if not drift:
            p.ok("docs map is up-to-date.")
            return 0
        p.line(
            f"docs map is stale: {len(drift)} drift item(s).",
            ok=False,
            stream=sys.stderr,
        )
        for item in drift:
            p.line(
                f"{item.kind}: {item.directory}",
                ok=None,
                stream=sys.stderr,
            )
        p.action(
            "Run `rrt docs map` (or `rrt-hooks docs-map-update`) to refresh.",
            stream=sys.stderr,
        )
        return 1

    p.header(
        "Generating purpose docs",
        Root=str(cwd / map_cfg.root),
        File=map_cfg.file_name,
        on_conflict=map_cfg.on_conflict,
    )
    p.section("Results")

    results = generate(map_cfg, cwd, dry_run=p.dry_run)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        rel = r.file_path.relative_to(cwd).as_posix()
        if p.dry_run:
            p.would_write(rel, detail=r.status)
        else:
            p.action(f"{r.status}: {rel}")

    if not p.dry_run:
        lockfile = refresh_lockfile(map_cfg, cwd)
        p.blank_line()
        p.ok(f"Lockfile refreshed: {lockfile.relative_to(cwd)}")

    summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    p.footer(f"Done. {summary or 'no target directories'}")
    return 0


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def cmd_docs(args: argparse.Namespace) -> int:
    """Dispatch rrt docs sub-actions."""
    verbose: int = getattr(args, "verbose", 0) or 0
    sub = getattr(args, "docs_action", "generate")
    match sub:
        case "generate":
            return _cmd_generate(args)
        case "check":
            return _cmd_check(args)
        case "publish":
            return _cmd_publish(args)
        case "inject":
            return _cmd_inject(args)
        case "suggest":
            return _cmd_suggest(args)
        case "badges":
            return _cmd_badges(args)
        case "api":
            return _cmd_api(args)
        case "map":
            return _cmd_map(args)
    p = VerbosePrinter(verbose=verbose)
    p.line(f"Unknown docs action: {sub!r}", ok=False, stream=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

_FORMATS = ["md", "txt", "rich", "clipboard", "json", "toml"]

DOCS_EPILOG = """\
Examples:
  rrt docs generate                         # explicit mode, md output to stdout
  rrt docs generate --format toml           # write .rrt/docs.lock.toml
  rrt docs generate --format rich           # colourised terminal preview
    rrt docs check                            # exits 1 if lockfile is stale
    rrt docs suggest                          # suggest rich module docstrings
  rrt docs generate --lang python,go        # multi-language extraction
  rrt docs api                              # emit rrt API index (Markdown)
  rrt docs api --format json                # emit rrt API index as JSON
"""


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the docs command."""
    parser = subparsers.add_parser(
        "docs",
        help="Extract and manage source-owned documentation blocks.",
        description=(
            "Scan source files and extract inline documentation blocks\n"
            "across Python, TypeScript/JavaScript, Go, Rust, Bash/Zsh, Fish, and PowerShell.\n\n"
            "Sub-actions: generate (default), check, publish, inject, suggest, api"
        ),
        epilog=DOCS_EPILOG,
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing files.",
    )

    sub = parser.add_subparsers(dest="docs_action")

    # ── generate ──────────────────────────────────────────────────────────
    gen_p = sub.add_parser(
        "generate",
        help="Extract docs and emit in the selected format.",
    )
    gen_p.add_argument(
        "--format",
        choices=_FORMATS,
        default=None,
        help="Output format (default: first format in config, usually md).",
    )
    gen_p.add_argument(
        "--lang",
        default=None,
        metavar="LANGS",
        help="Comma-separated language filter, e.g. python,go (overrides config).",
    )
    gen_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    gen_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing files.",
    )

    # ── check ─────────────────────────────────────────────────────────────
    chk_p = sub.add_parser(
        "check",
        help="Exit 1 if the docs lockfile is stale.",
    )
    chk_p.add_argument(
        "--lock-file",
        default=None,
        metavar="PATH",
        help="Path to the lock file (default: from config or .rrt/docs.lock.toml).",
    )
    chk_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )

    parser.set_defaults(handler=cmd_docs)
    gen_p.set_defaults(handler=cmd_docs)
    chk_p.set_defaults(handler=cmd_docs)

    # ── publish ───────────────────────────────────────────────────────────
    pub_p = sub.add_parser(
        "publish",
        help="Write CLI-reference docs from the live rrt parser.",
    )
    pub_p.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Fail if any generated file is stale; do not write.",
    )
    pub_p.add_argument(
        "--fail-on-change",
        action="store_true",
        default=False,
        help="Exit 1 after writing (for pre-commit hook workflows).",
    )
    pub_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print which files would be written without doing so.",
    )
    pub_p.set_defaults(handler=cmd_docs)

    # ── inject ────────────────────────────────────────────────────────────
    inj_p = sub.add_parser(
        "inject",
        help="Inject shared anchor blocks defined in [tool.rrt.docs.shared_blocks].",
    )
    inj_p.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Fail if any anchor block is stale; do not write.",
    )
    inj_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    inj_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print which files would be updated without writing.",
    )
    inj_p.add_argument(
        "--add-anchors",
        action="store_true",
        default=False,
        help="Prepend missing anchor stubs to target files (first-time setup).",
    )
    inj_p.set_defaults(handler=cmd_docs)

    # ── suggest ───────────────────────────────────────────────────────────
    sug_p = sub.add_parser(
        "suggest",
        help="Suggest or scaffold rich module docstrings for Python files.",
    )
    sug_p.add_argument(
        "paths",
        nargs="*",
        default=(),
        help="Optional files or directories to scan; defaults to the command modules.",
    )
    sug_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    sug_p.add_argument(
        "--min-chars",
        type=int,
        default=None,
        metavar="N",
        help="Minimum docstring length to accept (default: config or 150).",
    )
    sug_p.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write scaffold docstrings back into the target files.",
    )
    sug_p.set_defaults(handler=cmd_docs)

    # ── badges ────────────────────────────────────────────────────────────
    bdg_p = sub.add_parser(
        "badges",
        help="Generate platform SVG badge files into docs/public/assets/badges/.",
    )
    bdg_p.add_argument(
        "--platform",
        default=None,
        metavar="PLATFORM",
        help="Generate badge for a single platform (e.g. github, gitlab).",
    )
    bdg_p.add_argument(
        "--all-platforms",
        action="store_true",
        default=False,
        help="Generate badges for all known platforms (default when --platform is omitted).",
    )
    bdg_p.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help="Override output directory (default: badge_assets_dir from config).",
    )
    bdg_p.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Fail if any badge file is stale; do not write.",
    )
    bdg_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    bdg_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print which files would be written without doing so.",
    )
    bdg_p.add_argument(
        "--variant",
        default=None,
        choices=["color", "dark", "light", "reto-dark", "reto-light"],
        help="Generate only one visual variant (default: all available).",
    )
    bdg_p.set_defaults(handler=cmd_docs)

    # ── api ───────────────────────────────────────────────────────────────
    api_p = sub.add_parser(
        "api",
        help="Emit a structured index of all rrt CLI commands and arguments.",
    )
    api_p.add_argument(
        "--format",
        choices=["md", "txt", "json"],
        default="md",
        help="Output format for the API index (default: md).",
    )
    api_p.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write output to FILE instead of stdout.",
    )
    api_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    api_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be written without writing files.",
    )
    api_p.set_defaults(handler=cmd_docs)

    # ── map ───────────────────────────────────────────────────────────────
    map_p = sub.add_parser(
        "map",
        help="Generate per-directory purpose docs from [tool.rrt.docs.map].",
    )
    map_p.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Fail if any directory's purpose doc disagrees with the lockfile.",
    )
    map_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    map_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without writing files or the lockfile.",
    )
    map_p.set_defaults(handler=cmd_docs)
