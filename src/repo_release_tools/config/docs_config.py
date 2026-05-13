"""Docs and EOL config parsing helpers for rrt."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

from .model import DocsConfig, EolConfig, EolOverride, SharedBlock


def _load_eol_config(raw: object) -> EolConfig | None:
    """Parse an optional [tool.rrt.eol] table into an EolConfig."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tool.rrt.eol must be a table")

    d: dict[str, object] = cast("dict[str, object]", raw)

    raw_langs = d.get("languages") or ["python"]
    if not isinstance(raw_langs, list) or not all(isinstance(x, str) for x in raw_langs):
        raise ValueError("tool.rrt.eol.languages must be a list of strings")

    raw_warn = d.get("warn_days")
    warn_days = 180 if raw_warn is None else raw_warn
    if not isinstance(warn_days, int):
        raise ValueError("tool.rrt.eol.warn_days must be an integer")

    raw_error = d.get("error_days")
    error_days = 0 if raw_error is None else raw_error
    if not isinstance(error_days, int):
        raise ValueError("tool.rrt.eol.error_days must be an integer")

    raw_fetch = d.get("fetch_live")
    fetch_live = False if raw_fetch is None else raw_fetch
    if not isinstance(fetch_live, bool):
        raise ValueError("tool.rrt.eol.fetch_live must be a boolean")

    raw_allow = d.get("allow_eol")
    allow_eol = False if raw_allow is None else raw_allow
    if not isinstance(allow_eol, bool):
        raise ValueError("tool.rrt.eol.allow_eol must be a boolean")

    raw_overrides = d.get("overrides") or []
    if not isinstance(raw_overrides, list):
        raise ValueError("tool.rrt.eol.overrides must be an array of tables")

    overrides: list[EolOverride] = []
    for entry in raw_overrides:
        if not isinstance(entry, dict):
            raise ValueError("Each tool.rrt.eol.overrides entry must be a table")
        e = cast("dict[str, object]", entry)
        language = e.get("language")
        cycle = e.get("cycle")
        eol = e.get("eol")
        if not isinstance(language, str) or not language:
            raise ValueError("tool.rrt.eol.overrides[].language must be a non-empty string")
        if not isinstance(cycle, str) or not cycle:
            raise ValueError("tool.rrt.eol.overrides[].cycle must be a non-empty string")
        if not isinstance(eol, str) or not eol:
            raise ValueError("tool.rrt.eol.overrides[].eol must be a non-empty YYYY-MM-DD string")
        overrides.append(EolOverride(language=language, cycle=cycle, eol=eol))

    return EolConfig(
        languages=tuple(cast("list[str]", raw_langs)),
        warn_days=warn_days,
        error_days=error_days,
        fetch_live=fetch_live,
        allow_eol=allow_eol,
        overrides=tuple(overrides),
    )


def _load_docs_config(raw: object, *, root: Path | None = None) -> DocsConfig | None:
    """Parse an optional [tool.rrt.docs] table into a DocsConfig."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tool.rrt.docs must be a table")

    d: dict[str, object] = cast("dict[str, object]", raw)

    raw_mirror = d.get("mirror_src_tree")
    mirror_src_tree = False if raw_mirror is None else raw_mirror
    if not isinstance(mirror_src_tree, bool):
        raise ValueError("tool.rrt.docs.mirror_src_tree must be a boolean")

    raw_docs_dir = d.get("docs_dir")
    docs_dir = "docs" if raw_docs_dir is None else raw_docs_dir
    if not isinstance(docs_dir, str) or not docs_dir:
        raise ValueError("tool.rrt.docs.docs_dir must be a non-empty string")

    raw_src_dir = d.get("src_dir")
    src_dir = "src/repo_release_tools" if raw_src_dir is None else raw_src_dir
    if not isinstance(src_dir, str) or not src_dir:
        raise ValueError("tool.rrt.docs.src_dir must be a non-empty string")

    raw_stubs = d.get("stubs") or []
    if not isinstance(raw_stubs, list) or not all(isinstance(s, str) for s in raw_stubs):
        raise ValueError("tool.rrt.docs.stubs must be a list of strings")

    # Normalize: strip whitespace, reject blanks, deduplicate preserving order.
    seen_stubs: set[str] = set()
    normalized_stubs: list[str] = []
    for s in cast("list[str]", raw_stubs):
        s = s.strip()
        if not s:
            raise ValueError("tool.rrt.docs.stubs must not contain empty entries")
        if s not in seen_stubs:
            seen_stubs.add(s)
            normalized_stubs.append(s)

    return DocsConfig(
        mirror_src_tree=mirror_src_tree,
        docs_dir=docs_dir,
        src_dir=src_dir,
        stubs=tuple(normalized_stubs),
        extraction_mode=_load_extraction_mode(d),
        languages=_load_docs_languages(d),
        lock_file=_load_docs_lock_file(d),
        formats=_load_docs_formats(d),
        source_repo_url=_load_optional_docs_string(d, "source_repo_url"),
        source_ref=_load_optional_docs_string(d, "source_ref"),
        source_url_template=_load_optional_docs_string(d, "source_url_template"),
        shared_blocks=_load_shared_blocks(d, root=root),
    )


_VALID_EXTRACTION_MODES = ("explicit", "implicit", "both")
_VALID_LANGUAGES = ("python", "ts", "js", "go", "rust")
_VALID_FORMATS = ("md", "txt", "rich", "clipboard", "json", "toml")


def _load_extraction_mode(d: dict[str, object]) -> str:
    raw = d.get("extraction_mode")
    if raw is None:
        return "explicit"
    if raw not in _VALID_EXTRACTION_MODES:
        raise ValueError(f"tool.rrt.docs.extraction_mode must be one of {_VALID_EXTRACTION_MODES}")
    return str(raw)


def _load_docs_languages(d: dict[str, object]) -> tuple[str, ...]:
    raw = d.get("languages")
    if raw is None:
        return ("python",)
    if not isinstance(raw, list) or not all(isinstance(lang, str) for lang in raw):
        raise ValueError("tool.rrt.docs.languages must be a list of strings")
    langs = [str(lang).strip().lower() for lang in cast("list[str]", raw)]
    invalid = [lang for lang in langs if lang not in _VALID_LANGUAGES]
    if invalid:
        raise ValueError(
            f"tool.rrt.docs.languages contains unsupported entries: {invalid}. "
            f"Supported: {list(_VALID_LANGUAGES)}",
        )
    return tuple(langs)


def _load_docs_lock_file(d: dict[str, object]) -> str:
    raw = d.get("lock_file")
    if raw is None:
        return ".rrt/docs.lock.toml"
    if not isinstance(raw, str) or not raw:
        raise ValueError("tool.rrt.docs.lock_file must be a non-empty string")
    return raw


def _load_docs_formats(d: dict[str, object]) -> tuple[str, ...]:
    raw = d.get("formats")
    if raw is None:
        return ("md",)
    if not isinstance(raw, list) or not all(isinstance(f, str) for f in raw):
        raise ValueError("tool.rrt.docs.formats must be a list of strings")
    fmts = [str(f).strip().lower() for f in cast("list[str]", raw)]
    if not fmts:
        raise ValueError("tool.rrt.docs.formats must not be empty; at least one format is required")
    invalid = [f for f in fmts if f not in _VALID_FORMATS]
    if invalid:
        raise ValueError(
            f"tool.rrt.docs.formats contains unsupported entries: {invalid}. "
            f"Supported: {list(_VALID_FORMATS)}",
        )
    return tuple(fmts)


def _load_optional_docs_string(d: dict[str, object], key: str) -> str | None:
    raw = d.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"tool.rrt.docs.{key} must be a string when provided")
    if not (value := raw.strip()):
        raise ValueError(f"tool.rrt.docs.{key} must not be empty when provided")
    return value


def _load_shared_blocks(
    d: dict[str, object],
    *,
    root: Path | None = None,
) -> tuple[SharedBlock, ...]:
    raw = d.get("shared_blocks")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tool.rrt.docs.shared_blocks must be an array of tables")
    blocks: list[SharedBlock] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"tool.rrt.docs.shared_blocks[{i}] must be a table")
        item = cast("dict[str, object]", entry)
        anchor_id = item.get("anchor_id")
        if not isinstance(anchor_id, str) or not anchor_id.strip():
            raise ValueError(
                f"tool.rrt.docs.shared_blocks[{i}].anchor_id must be a non-empty string",
            )
        template = item.get("template")
        content = item.get("content")

        if template is not None:
            if not isinstance(template, str) or not template.strip():
                raise ValueError(
                    f"tool.rrt.docs.shared_blocks[{i}].template must be a non-empty string",
                )

            warnings.warn(
                (
                    f"tool.rrt.docs.shared_blocks[{i}].template is deprecated and will be "
                    "removed in a future major version; migrate to inline 'content'"
                ),
                DeprecationWarning,
                stacklevel=2,
            )

            template_path = Path(template)
            if not template_path.is_absolute() and root is not None:
                template_path = root / template_path
            try:
                template_content = template_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ValueError(
                    f"tool.rrt.docs.shared_blocks[{i}].template unreadable: {template_path} ({exc})",
                ) from exc

            if content is None:
                content = template_content

        if content is None:
            raise ValueError(f"tool.rrt.docs.shared_blocks[{i}] must define 'content'")
        if not isinstance(content, str):
            raise ValueError(f"tool.rrt.docs.shared_blocks[{i}].content must be a string")
        raw_targets = item.get("targets")
        if not isinstance(raw_targets, list) or not all(isinstance(t, str) for t in raw_targets):
            raise ValueError(f"tool.rrt.docs.shared_blocks[{i}].targets must be a list of strings")
        block = SharedBlock(
            anchor_id=anchor_id.strip(),
            content=content,
            targets=tuple(cast("list[str]", raw_targets)),
        )
        block.validate()
        blocks.append(block)
    return tuple(blocks)
