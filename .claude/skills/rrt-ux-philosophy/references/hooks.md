# Hook Architecture

The rrt UX contract is enforced at three independent layers. All three must
stay in sync.

---

## Three enforcement layers

| Layer | Mechanism | Strength |
|---|---|---|
| 1 | `pytest_collection_finish` in `tests/conftest.py` | Hard fail before any test runs |
| 2 | `UserPromptSubmit` hook — `rrt_ux_guard.py` | Context injection (reminder + file scan) |
| 3 | `PreToolUse` hook — `rrt_ux_write_guard.py` | Hard block on raw ANSI in new content |

---

## Layer 1 — pytest entrypoint guard (conftest.py)

`conftest.py` parses the module docstring of `test_user_experience_simulator.py`
to extract the "Affected entrypoints" list and compares it against the live
subcommand names from `cli.build_parser()`. If they diverge, the suite fails
before a single test runs:

```
[rrt-ux-contract] Entrypoint mismatch — fix before running tests.
  CLI subcommands missing from the test docstring: audit
  → Add them under 'Affected entrypoints' in tests/test_user_experience_simulator.py
```

**Triggers when:** a new subcommand is added to `cli.build_parser()` without
updating the test docstring.

---

## Layer 2 — UserPromptSubmit hook (rrt_ux_guard.py)

**Fires:** Once per user turn, before Claude processes the prompt.

**Does two things:**

1. Extracts Python file paths mentioned in the prompt, reads them from disk,
   and scans them for existing violations. Claude sees a targeted report
   before writing a single line.

2. When the prompt contains UI-related keywords, injects the full UX contract
   reminder as `additionalContext`.

**Violation severities scanned:**

| Severity | Pattern |
|---|---|
| `HARD` | Raw `\x1b[` or `\033[` escapes |
| `MIGRATE` | `output.banner()`, `output.panel()`, `output.ok()`, `output.info()`, etc. |
| `WARN` | `from repo_release_tools import output` |

**Always exits 0** — this hook never blocks.

---

## Layer 3 — PreToolUse hook (rrt_ux_write_guard.py)

**Fires:** Before every `Write`, `Edit`, `MultiEdit`, or `str_replace_based_edit`
tool call on files inside `src/repo_release_tools/` or `tests/`.

**Enforces:**

- **Hard block (exit 2):** Raw ANSI escapes (`\x1b[`, `\033[`) in the new
  content stop the write entirely. Claude sees the stderr message and must
  fix the violation before the file can be saved.

- **Soft warn (exit 0 + context):** Deprecated `output.*` calls in new
  content are flagged but allowed through. Claude sees the warning and
  knows to flag the migration in the PR.

**Scope guard:** Only activates for files matching `src/repo_release_tools/`
or `tests/`. All other files pass through unchanged.

---

## settings.json structure

```jsonc
{
    "hooks": {
        "UserPromptSubmit": [
            {
                "type": "command",
                "command": "python3 .github/hooks/rrt_ux_guard.py",
                "timeout": 5
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Write|Edit|MultiEdit|str_replace_based_edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 .github/hooks/rrt_ux_write_guard.py",
                        "timeout": 5
                    }
                ]
            }
        ]
    }
}
```

---

## Testing the hooks manually

```bash
# Test UserPromptSubmit — should emit a file scan + contract reminder
echo '{"prompt": "fix the output.ok calls in commands/branch.py"}' \
  | python3 .github/hooks/rrt_ux_guard.py | python3 -m json.tool

# Test PreToolUse — should BLOCK (exit 2)
echo '{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "src/repo_release_tools/commands/branch.py",
    "content": "print(\"\\x1b[32mDone\\x1b[0m\")"
  }
}' | python3 .github/hooks/rrt_ux_write_guard.py
echo "Exit: $?"   # should be 2

# Test PreToolUse — should WARN but allow (exit 0)
echo '{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "src/repo_release_tools/commands/branch.py",
    "new_string": "print(output.ok(\"Done.\"))"
  }
}' | python3 .github/hooks/rrt_ux_write_guard.py | python3 -m json.tool
echo "Exit: $?"   # should be 0
```

---

## Extending the hooks

### Add a new hard-block pattern

In `rrt_ux_write_guard.py`, add to `_HARD_BLOCKS`:

```python
_HARD_BLOCKS: list[tuple[re.Pattern[str], str]] = [
    # existing …
    (
        re.compile(r'sys\.stdout\.write\s*\(\s*["\'].*\\x1b'),
        "sys.stdout.write() with inline ANSI escape",
    ),
]
```

### Add a new keyword trigger

In `rrt_ux_guard.py`, extend `_UI_KEYWORDS`:

```python
_UI_KEYWORDS = re.compile(
    r"\b(… | new_keyword)\b"
    r"|new_module\.py",
    re.IGNORECASE,
)
```
