"""Multi-language doc extraction engine for rrt docs.

Supports extracting named documentation blocks from source files across
Python, TypeScript/JavaScript, Go, Rust, Bash/Zsh, Fish, and PowerShell
using static regex analysis — no runtime AST parsers required.

## Extraction modes

Configured via ``DocsConfig.extraction_mode``:

- ``explicit`` — only grab blocks preceded by a ``# sym: NAME``
  (or language-equivalent) marker.
- ``implicit`` — only grab language-native docstrings / comment blocks.
- ``both`` — explicit markers take priority; fall back to implicit.

## Supported languages

| Slug        | Extensions               | Implicit convention                     |
|-------------|--------------------------|------------------------------------------|
| python      | .py                      | Triple-quoted string docstrings          |
| ts          | .ts, .tsx                | JSDoc ``/** … */`` blocks                |
| js          | .js, .mjs, .cjs, .jsx    | JSDoc ``/** … */`` blocks                |
| go          | .go                      | ``//`` comment blocks before declarations|
| rust        | .rs                      | ``///`` doc-comment blocks               |
| bash        | .sh, .bash, .zsh         | ``##`` file header; ``#`` before ``func``|
| fish        | .fish                    | ``##`` file header; ``#`` before ``function``|
| powershell  | .ps1, .psm1, .psd1       | ``<# … #>`` comment-based help blocks   |
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
    "bash": (".sh", ".bash", ".zsh"),
    "fish": (".fish",),
    "powershell": (".ps1", ".psm1", ".psd1"),
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
    # Bash/Zsh: # sym: NAME  (same as Python single-line comment; hyphens allowed)
    "bash": re.compile(r"^[ \t]*#\s*sym:\s*([\w-]+)\s*$", re.MULTILINE),
    # Fish: # sym: NAME  (Fish uses # for all comments; hyphens are common in function names)
    "fish": re.compile(r"^[ \t]*#\s*sym:\s*([\w-]+)\s*$", re.MULTILINE),
    # PowerShell: # sym: NAME  OR  <# sym: NAME #>  (Verb-Noun style needs hyphens)
    "powershell": re.compile(
        r"^[ \t]*(?:#\s*sym:\s*([\w-]+)|<#\s*sym:\s*([\w-]+)\s*#>)\s*$", re.MULTILINE
    ),
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
    r"SOURCE_OWNED_TOPIC_DOCS\s*[^=]*=\s*\(([\s\S]*?)^\)",
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
                ),
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
                ),
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
                ),
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
                ),
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
                ),
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
        # PowerShell uses two alternation groups (# sym: and <# sym: #>);
        # for all other languages there is exactly one capture group.
        name = (m.group(1) or m.group(2)) if lang == "powershell" else m.group(1)
        if not name:  # pragma: no cover — regex requires a capture group to match
            continue
        marker_end = m.end()
        remainder = source[marker_end:]
        line_no = source[: m.start()].count("\n") + 2  # line after marker

        content: str | None = None

        match lang:
            case "python":
                # Find the next triple-quoted string assignment
                string_m = _PY_STRING_AFTER_MARKER.search(remainder)
                if string_m:
                    content = (string_m.group(1) or string_m.group(2) or "").strip()
            case "bash" | "fish":
                # Bash/Fish: collect consecutive # comment lines after marker
                comment_lines: list[str] = []
                for raw_line in remainder.splitlines():
                    stripped = raw_line.strip()
                    if stripped.startswith("#"):
                        comment_lines.append(re.sub(r"^[ \t]*#+\s?", "", raw_line).rstrip())
                    elif stripped == "":
                        if comment_lines:
                            break
                    else:
                        break
                if comment_lines:
                    content = "\n".join(comment_lines).strip()
            case "powershell":
                # PowerShell: next block may be <# ... #> (non-nested) or # comment lines
                ps_block_m = re.match(r"\s*<#((?:[^#]|#(?!>))*)#>", remainder)
                if ps_block_m:
                    content = ps_block_m.group(1).strip()
                else:
                    ps_lines: list[str] = []
                    for raw_line in remainder.splitlines():
                        stripped = raw_line.strip()
                        if stripped.startswith("#"):
                            ps_lines.append(re.sub(r"^[ \t]*#+\s?", "", raw_line).rstrip())
                        elif stripped == "":
                            if ps_lines:
                                break
                        else:
                            break
                    if ps_lines:
                        content = "\n".join(ps_lines).strip()
            case _:
                # JS/TS/Go/Rust: next line may be a string assignment or // comment block
                str_m = re.match(
                    r"\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*[:=][^=][^\n]*?"
                    r'(?:`([\s\S]*?)`|"([\s\S]*?)"|\'([\s\S]*?)\')',
                    remainder,
                )
                if str_m:
                    content = (str_m.group(1) or str_m.group(2) or str_m.group(3) or "").strip()
                else:
                    # Go/Rust: collect // comment lines until blank/code
                    slash_lines: list[str] = []
                    for raw_line in remainder.splitlines():
                        stripped = raw_line.strip()
                        if stripped.startswith("//"):
                            slash_lines.append(
                                re.sub(r"^[ \t]*(?:///|//)\s?", "", raw_line).rstrip()
                            )
                        elif stripped == "":
                            if slash_lines:
                                break
                        else:
                            break
                    if slash_lines:
                        content = "\n".join(slash_lines).strip()

        if content:
            entries.append(
                DocEntry(
                    name=name,
                    lang=lang,
                    content=content,
                    source_file=source_file,
                    line=line_no,
                    hash=hash_content(content),
                ),
            )

    return entries


# ---------------------------------------------------------------------------
# Python SOURCE_OWNED_TOPIC_DOCS detection
# ---------------------------------------------------------------------------


def _extract_python_source_owned(
    source: str,
    source_file: str,
    module_vars: dict[str, str],
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
                    ),
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
# Bash/Zsh implicit extraction
# ---------------------------------------------------------------------------


def _extract_bash_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract Bash/Zsh doc comment blocks (implicit mode).

    Two kinds of blocks are extracted:

    1. **Script header** — ``##`` comment block at the very top of the file
       (after an optional shebang line).  The block must start with ``##``.
    2. **Function comments** — consecutive ``#`` comment lines immediately
       preceding ``function name {`` or ``name() {`` declarations.
    """
    entries: list[DocEntry] = []

    # --- Script-level header: consecutive ## lines at file top ---------------
    lines = source.splitlines()
    start_idx = 0
    if lines and lines[0].startswith("#!"):
        start_idx = 1  # skip shebang

    header_lines: list[str] = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith("##"):
            header_lines.append(re.sub(r"^[ \t]*#{2,}\s?", "", line).rstrip())
        else:
            break
    if header_lines:
        content = "\n".join(header_lines).strip()
        if content:
            entries.append(
                DocEntry(
                    name="script",
                    lang="bash",
                    content=content,
                    source_file=source_file,
                    line=start_idx + 1,
                    hash=hash_content(content),
                ),
            )

    # --- Function-level comments: # lines immediately before function --------
    for m in re.finditer(
        r"((?:^[ \t]*#[^\n]*\n)+)[ \t]*(?:function\s+(\w+)\s*\{|(\w+)\s*\(\s*\)\s*\{)",
        source,
        re.MULTILINE,
    ):
        raw = m.group(1)
        func_name = m.group(2) or m.group(3)
        content = re.sub(r"^[ \t]*#+\s?", "", raw, flags=re.MULTILINE).strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=func_name,
                    lang="bash",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                ),
            )
    return entries


# ---------------------------------------------------------------------------
# Fish shell implicit extraction
# ---------------------------------------------------------------------------


def _extract_fish_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract Fish shell doc comment blocks (implicit mode).

    Fish functions are declared as ``function name`` (no braces, terminated
    by ``end``).  Two kinds of blocks are extracted:

    1. **Script header** — ``##`` comment block at the very top of the file
       (after an optional shebang line).  The block must start with ``##``.
    2. **Function comments** — consecutive ``#`` comment lines immediately
       preceding a ``function name`` declaration.
    """
    entries: list[DocEntry] = []

    # --- Script-level header: consecutive ## lines at file top ---------------
    lines = source.splitlines()
    start_idx = 1 if lines and lines[0].startswith("#!") else 0

    header_lines: list[str] = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith("##"):
            header_lines.append(re.sub(r"^[ \t]*#{2,}\s?", "", line).rstrip())
        else:
            break
    if header_lines:
        content = "\n".join(header_lines).strip()
        if content:
            entries.append(
                DocEntry(
                    name="script",
                    lang="fish",
                    content=content,
                    source_file=source_file,
                    line=start_idx + 1,
                    hash=hash_content(content),
                ),
            )

    # --- Function-level comments: # lines immediately before `function name` -
    # Fish function syntax: `function name [--options ...]`  (no braces)
    for m in re.finditer(
        r"((?:^[ \t]*#[^\n]*\n)+)[ \t]*function\s+([\w\-]+)",
        source,
        re.MULTILINE,
    ):
        raw = m.group(1)
        func_name = m.group(2)
        content = re.sub(r"^[ \t]*#+\s?", "", raw, flags=re.MULTILINE).strip()
        if content:
            line = source[: m.start()].count("\n") + 1
            entries.append(
                DocEntry(
                    name=func_name,
                    lang="fish",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                ),
            )
    return entries


# ---------------------------------------------------------------------------
# PowerShell implicit extraction
# ---------------------------------------------------------------------------


def _extract_powershell_implicit(source: str, source_file: str) -> list[DocEntry]:
    """Extract PowerShell doc comment blocks (implicit mode).

    Two kinds of blocks are extracted:

    1. **Module-level comment-based help** — a ``<# ... #>`` block at the top
       of the script/module (before any ``function`` declarations).
    2. **Function-level help** — a ``<# ... #>`` block or consecutive ``#``
       lines immediately preceding a ``function`` declaration.
    """
    entries: list[DocEntry] = []

    # Pattern for a single <# ... #> block (no crossing of #> boundaries).
    # (?:[^#]|#(?!>))* matches any character except an unescaped block close:
    #   - [^#]   → any non-hash character
    #   - #(?!>) → a hash that is NOT followed by '>' (avoids prematurely closing)
    # This prevents the regex from spanning multiple <# ... #> blocks.
    _ps_block_re = re.compile(r"<#((?:[^#]|#(?!>))*)#>", re.MULTILINE)

    # Build a position-indexed list of all block matches for quick lookup
    blocks = list(_ps_block_re.finditer(source))

    # --- Module-level: first block before any function declaration -----------
    # Only emit as module-level if the block is NOT immediately adjacent to the
    # first function (a gap-less block is the function's own doc, not the module's).
    first_func_m = re.search(r"(?m)^[ \t]*function\s+\w", source)
    first_func_pos = first_func_m.start() if first_func_m else len(source)

    for blk in blocks:
        if blk.start() < first_func_pos:
            gap = source[blk.end() : first_func_pos]
            # Block is immediately before the first function → function's doc, not module's
            if gap.strip() == "":
                break
            content = blk.group(1).strip()
            if content:
                line = source[: blk.start()].count("\n") + 1
                entries.append(
                    DocEntry(
                        name="module",
                        lang="powershell",
                        content=content,
                        source_file=source_file,
                        line=line,
                        hash=hash_content(content),
                    ),
                )
            break  # only emit one module-level entry

    # --- Function-level: block or # lines immediately before `function Name` -
    for func_m in re.finditer(
        r"(?m)^[ \t]*function\s+([\w-]+)",
        source,
    ):
        func_name = func_m.group(1)
        func_pos = func_m.start()
        line = source[:func_pos].count("\n") + 1

        # Look for the nearest block ending just before this function
        content: str | None = None
        for blk in reversed(blocks):
            if blk.end() > func_pos:
                continue
            # Check that only whitespace separates block end from function start
            gap = source[blk.end() : func_pos]
            if gap.strip() == "":
                content = blk.group(1).strip()
                break
            break  # nearest non-matching block → fall through to # lines

        if content is None:
            # Fall back: consecutive # lines immediately before function
            before = source[:func_pos]
            ps_lines: list[str] = []
            for raw_line in reversed(before.splitlines()):
                stripped = raw_line.strip()
                if stripped.startswith("#"):
                    ps_lines.insert(0, re.sub(r"^[ \t]*#+\s?", "", raw_line).rstrip())
                elif stripped == "" and not ps_lines:
                    continue
                else:
                    break
            if ps_lines:
                content = "\n".join(ps_lines).strip()

        if content:
            entries.append(
                DocEntry(
                    name=func_name,
                    lang="powershell",
                    content=content,
                    source_file=source_file,
                    line=line,
                    hash=hash_content(content),
                ),
            )
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_docs(
    path: Path,
    config: DocsConfig,
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
        match lang:
            case "python":
                for e in _extract_python_implicit(source, source_file):
                    _add(e)
            case "ts" | "js":
                for e in _extract_ts_js_implicit(source, source_file, lang):
                    _add(e)
            case "go":
                for e in _extract_go_implicit(source, source_file):
                    _add(e)
            case "rust":
                for e in _extract_rust_implicit(source, source_file):
                    _add(e)
            case "bash":
                for e in _extract_bash_implicit(source, source_file):
                    _add(e)
            case "fish":
                for e in _extract_fish_implicit(source, source_file):
                    _add(e)
            case "powershell":
                for e in _extract_powershell_implicit(source, source_file):
                    _add(e)

    return entries


def extract_docs_from_dir(
    root: Path,
    config: DocsConfig,
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
