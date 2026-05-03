"""Multi-language doc extraction engine for rrt docs.

Supports extracting named documentation blocks from source files across
Python, TypeScript/JavaScript, Go, and Rust using static regex analysis —
no runtime AST parsers required.

Extraction modes (configured via DocsConfig.extraction_mode):
  explicit  — only grab blocks preceded by a ``# sym: NAME`` marker
  implicit  — only grab language-native docstrings / comment blocks
  both      — explicit markers take priority; fall back to implicit
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_release_tools.config import DocsConfig

from repo_release_tools.state import hash_content

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocEntry:
    """A single extracted documentation block."""

    name: str
    lang: str
    content: str
    source_file: str  # relative or absolute string path
    line: int  # 1-based line number of the doc block start
    hash: str  # sha256:…

    def to_dict(self) -> dict[str, object]:
        """Serialise entry to a plain dict for lock/format output."""
        return {
            "name": self.name,
            "lang": self.lang,
            "content": self.content,
            "source_file": self.source_file,
            "line": self.line,
            "hash": self.hash,
        }


# ---------------------------------------------------------------------------
# Language ↔ file-extension mapping
# ---------------------------------------------------------------------------

_LANG_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "ts": (".ts", ".tsx"),
    "js": (".js", ".mjs", ".cjs", ".jsx"),
    "go": (".go",),
    "rust": (".rs",),
}

# Reverse map: extension → lang
_EXT_TO_LANG: dict[str, str] = {
    ext: lang for lang, exts in _LANG_EXTENSIONS.items() for ext in exts
}


def lang_for_path(path: Path) -> str | None:
    """Return the language slug for *path*, or None if unrecognised."""
    return _EXT_TO_LANG.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# Explicit marker patterns — ``# sym: NAME`` style
# ---------------------------------------------------------------------------
#
# The explicit marker must appear on its own line immediately preceding the
# opening of the doc block.  The name captured by group 1 is used as the
# DocEntry.name.

_EXPLICIT_PATTERNS: dict[str, re.Pattern[str]] = {
    # Python: # sym: NAME  (or ## sym: NAME)
    "python": re.compile(r"^[ \t]*#+\s*sym:\s*(\w+)\s*$", re.MULTILINE),
    # JS / TS / Go / Rust: // sym: NAME
    "ts": re.compile(r"^[ \t]*//\s*sym:\s*(\w+)\s*$", re.MULTILINE),
    "js": re.compile(r"^[ \t]*//\s*sym:\s*(\w+)\s*$", re.MULTILINE),
    "go": re.compile(r"^[ \t]*//\s*sym:\s*(\w+)\s*$", re.MULTILINE),
    "rust": re.compile(r"^[ \t]*//\s*sym:\s*(\w+)\s*$", re.MULTILINE),
}

# Python: match the content that follows the explicit marker.
# Captures: (optional-leading-spaces)(triple-quote-content)
_PY_STRING_AFTER_MARKER = re.compile(
    r"^[ \t]*\w+\s*=\s*(?:r|b|rb|br|f|fr|rf)?"
    r'(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')',
    re.MULTILINE,
)

# Python: SOURCE_OWNED_TOPIC_DOCS first-class extraction
_PY_SOURCE_OWNED = re.compile(
    r"SOURCE_OWNED_TOPIC_DOCS\s*[^=]*=\s*\(([\s\S]*?)\)",
    re.MULTILINE,
)
_PY_TUPLE_ENTRY = re.compile(r'\(\s*"([^"]+)"\s*,\s*(?:[A-Z_][A-Z0-9_]*)\s*\)')


# ---------------------------------------------------------------------------
# Implicit extraction patterns
# ---------------------------------------------------------------------------


def _extract_python_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract module/class/function docstrings (implicit mode)."""
    entries: list[DocEntry] = []

    # Module-level docstring (first triple-quoted string at top of file)
    module_doc = re.match(
        r'^[ \t]*(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')',
        source,
    )
    if module_doc:
        content = (module_doc.group(1) or module_doc.group(2) or "").strip()
        if content:
            entries.append(
                DocEntry(
                    name="module",
                    lang="python",
                    content=content,
                    source_file=source_file,
                    line=1,
                    hash=hash_content(content),
                )
            )

    # class / def docstrings
    for m in re.finditer(
        r"^[ \t]*(?:class|def|async def)\s+(\w+)[^\n]*:\s*\n"
        r'[ \t]*(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')',
        source,
        re.MULTILINE,
    ):
        content = (m.group(2) or m.group(3) or "").strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=m.group(1),
                    lang="python",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                )
            )
    return entries


def _extract_ts_js_implicit(source: str, source_file: str, lang: str) -> list[DocEntry]:
    """Extract JSDoc /** … */ blocks (implicit mode for TS/JS)."""
    entries: list[DocEntry] = []
    for m in re.finditer(
        r"/\*\*([\s\S]*?)\*/\s*\n[ \t]*(?:export\s+)?(?:class|function|const|let|var)\s+(\w+)",
        source,
        re.MULTILINE,
    ):
        raw = m.group(1)
        # Strip leading * on each line
        content = re.sub(r"^\s*\*\s?", "", raw, flags=re.MULTILINE).strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=m.group(2),
                    lang=lang,
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                )
            )
    return entries


def _extract_go_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract Go doc-comment blocks (lines starting with // before func/type/var/const)."""
    entries: list[DocEntry] = []
    for m in re.finditer(
        r"((?:^[ \t]*//[^\n]*\n)+)[ \t]*(?:func|type|var|const)\s+(\w+)",
        source,
        re.MULTILINE,
    ):
        raw = m.group(1)
        content = re.sub(r"^[ \t]*//\s?", "", raw, flags=re.MULTILINE).strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=m.group(2),
                    lang="go",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                )
            )
    return entries


def _extract_rust_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract Rust /// doc-comment blocks before pub fn / pub struct / const."""
    entries: list[DocEntry] = []
    for m in re.finditer(
        r"((?:^[ \t]*///[^\n]*\n)+)[ \t]*(?:pub\s+)?(?:fn|struct|enum|const|type)\s+(\w+)",
        source,
        re.MULTILINE,
    ):
        raw = m.group(1)
        content = re.sub(r"^[ \t]*///\s?", "", raw, flags=re.MULTILINE).strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=m.group(2),
                    lang="rust",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                )
            )
    return entries


# ---------------------------------------------------------------------------
# Explicit extraction
# ---------------------------------------------------------------------------


def _extract_explicit(source: str, source_file: str, lang: str) -> list[DocEntry]:
    """Extract blocks that are preceded by a ``# sym: NAME`` or ``// sym: NAME`` marker."""
    pattern = _EXPLICIT_PATTERNS.get(lang)
    if pattern is None:
        return []

    entries: list[DocEntry] = []

    for m in pattern.finditer(source):
        name = m.group(1)
        marker_end = m.end()
        remainder = source[marker_end:]
        line_no = source[: m.start()].count("\n") + 2  # line after marker

        content: str | None = None

        if lang == "python":
            # Find the next triple-quoted string assignment
            string_m = _PY_STRING_AFTER_MARKER.search(remainder)
            if string_m:
                content = (string_m.group(1) or string_m.group(2) or "").strip()
        else:
            # JS/TS/Go/Rust: next line may be the doc or assignment
            # Look for a string literal or comment block immediately after
            # Try: JS/TS string assignment
            str_m = re.match(
                r"\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*[:=][^=][^\n]*?"
                r'(?:`([\s\S]*?)`|"([\s\S]*?)"|\'([\s\S]*?)\')',
                remainder,
            )
            if str_m:
                content = (str_m.group(1) or str_m.group(2) or str_m.group(3) or "").strip()
            else:
                # Go/Rust: collect comment lines until blank/code
                comment_lines: list[str] = []
                for raw_line in remainder.splitlines():
                    stripped = raw_line.strip()
                    if stripped.startswith("//"):
                        comment_lines.append(re.sub(r"^[ \t]*(?:///|//)\s?", "", raw_line).rstrip())
                    elif stripped == "":
                        if comment_lines:
                            break
                    else:
                        break
                if comment_lines:
                    content = "\n".join(comment_lines).strip()

        if content:
            entries.append(
                DocEntry(
                    name=name,
                    lang=lang,
                    content=content,
                    source_file=source_file,
                    line=line_no,
                    hash=hash_content(content),
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Python SOURCE_OWNED_TOPIC_DOCS detection
# ---------------------------------------------------------------------------


def _extract_python_source_owned(
    source: str, source_file: str, module_vars: dict[str, str]
) -> list[DocEntry]:
    """Detect SOURCE_OWNED_TOPIC_DOCS and resolve variable references to their content."""
    entries: list[DocEntry] = []
    m = _PY_SOURCE_OWNED.search(source)
    if not m:
        return entries
    tuple_body = m.group(1)
    for entry_m in _PY_TUPLE_ENTRY.finditer(tuple_body):
        slug = entry_m.group(0)
        # get the variable name that follows the slug string
        var_name_m = re.search(r'\(\s*"[^"]+"\s*,\s*([A-Z_][A-Z0-9_]*)\s*\)', entry_m.group(0))
        if var_name_m:
            var_name = var_name_m.group(1)
            content = module_vars.get(var_name, "")
            if content:
                line = source[: m.start()].count("\n") + 1
                entries.append(
                    DocEntry(
                        name=var_name,
                        lang="python",
                        content=content,
                        source_file=source_file,
                        line=line,
                        hash=hash_content(content),
                    )
                )
        del slug
    return entries


def _extract_python_module_string_vars(source: str) -> dict[str, str]:
    """Return a mapping of NAME → string content for all top-level triple-quoted assignments."""
    result: dict[str, str] = {}
    for m in re.finditer(
        r"^([A-Z_][A-Z0-9_]*)\s*=\s*(?:r|b|rb|br|f|fr|rf)?"
        r'(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')',
        source,
        re.MULTILINE,
    ):
        content = (m.group(2) or m.group(3) or "").strip()
        result[m.group(1)] = content
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_docs(
    path: Path,
    config: "DocsConfig",
    *,
    relative_to: Path | None = None,
) -> list[DocEntry]:
    """Extract documentation entries from *path* according to *config*.

    Parameters
    ----------
    path:
        Source file to scan.
    config:
        DocsConfig controlling extraction mode and languages.
    relative_to:
        If provided, ``source_file`` in each entry will be relative to this root.
    """
    lang = lang_for_path(path)
    if lang is None or lang not in config.languages:
        return []

    source = path.read_text(encoding="utf-8")
    source_file = str(path.relative_to(relative_to) if relative_to else path)
    mode = config.extraction_mode

    entries: list[DocEntry] = []
    seen_names: set[str] = set()

    def _add(e: DocEntry) -> None:
        if e.name not in seen_names:
            seen_names.add(e.name)
            entries.append(e)

    # Always extract SOURCE_OWNED_TOPIC_DOCS for Python (first-class)
    if lang == "python":
        module_vars = _extract_python_module_string_vars(source)
        for e in _extract_python_source_owned(source, source_file, module_vars):
            _add(e)

    if mode in ("explicit", "both"):
        for e in _extract_explicit(source, source_file, lang):
            _add(e)

    if mode in ("implicit", "both"):
        if lang == "python":
            for e in _extract_python_implicit(source, source_file):
                _add(e)
        elif lang in ("ts", "js"):
            for e in _extract_ts_js_implicit(source, source_file, lang):
                _add(e)
        elif lang == "go":
            for e in _extract_go_implicit(source, source_file):
                _add(e)
        elif lang == "rust":
            for e in _extract_rust_implicit(source, source_file):
                _add(e)

    return entries


def extract_docs_from_dir(
    root: Path,
    config: "DocsConfig",
) -> list[DocEntry]:
    """Recursively extract docs from all matching source files under *root*.

    Hidden directories (starting with ``.``) and ``__pycache__`` are skipped.
    """
    all_entries: list[DocEntry] = []
    valid_exts = {ext for lang in config.languages for ext in _LANG_EXTENSIONS.get(lang, ())}
    src_dir = root / config.src_dir

    for path in sorted(src_dir.rglob("*")):
        # Skip hidden dirs and pycache
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        if path.suffix in valid_exts and path.is_file():
            all_entries.extend(extract_docs(path, config, relative_to=root))

    return all_entries
