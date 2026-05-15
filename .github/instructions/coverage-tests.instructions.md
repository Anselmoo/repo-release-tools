---
applyTo: "tests/**/*.py"
description: "Full coverage discipline for writing tests in repo-release-tools — expands the summary in copilot-instructions.md"
---

# Coverage-complete test writing

When writing or extending tests for this repo, every uncovered line must be
reached before declaring work done. The coverage summary in
`copilot-instructions.md` is the brief version — these are the actionable rules.

## Rules

- Before writing any assertion, read the SUT source to understand what it
  actually returns — never assume the output equals the input.
- Run `uv run pytest <test_file> -q --cov=<module> --cov-report=term-missing --no-header`
  and confirm `Missing:` is empty before declaring a file complete.
- After adding each new test, re-run with `--cov-report=term-missing` to verify
  the target line now appears in the covered set — not just that the test passes.
- For each uncovered line, identify the guard condition that blocks it (`if not x`,
  `isinstance`, exhaustive `if/elif` above it, etc.) before writing the test.
- Reach dead-code-by-construction branches by patching the dependency, not the SUT:
  `monkeypatch.setattr(_module, "_private_fn", lambda ...: <trigger_value>)`.
- When the SUT imports a dependency directly into its module namespace, patch the
  symbol where it is used — not the provider module — so the test actually intercepts
  the call.
- When overriding a module-level registry or tuple for a regression test, prefer
  `monkeypatch.setattr(..., raising=False)` over direct assignment so the override is
  both temporary and type-checker friendly.
- When a test needs a fake `ModuleType` shim with ad-hoc attributes, cast the shim
  to `Any` before attaching those attributes; avoid broad `ty: ignore` comments on
  the whole test when a narrower shim cast will do.
- When testing command handlers typed with `argparse.Namespace`, build helper args
  with `argparse.Namespace(...)` instead of `types.SimpleNamespace(...)` so `ty`
  checks remain valid across call sites.
- To make a monkeypatched function raise an exception, use the generator throw pattern:
  `lambda *a, **kw: (_ for _ in ()).throw(SomeError("msg"))`.
- When asserting exception messages with `pytest.raises(..., match=...)`, escape regex metacharacters in literal text (especially `[` and `]`) or use `re.escape(...)`.
- Add module-level imports for private symbols used in two or more tests; otherwise
  import inside the single test function that needs the symbol.
- After two failed attempts to cover a line, determine whether it is structurally
  unreachable (contradictory state, type already proven above, exhaustive enum). If so,
  add a comment in the test file noting the line is dead code and stop.
- Any `Path(__file__).resolve().parents[N]` used to anchor repo-root paths must count
  from the test file's actual location in the subdirectory tree — after moving a test
  from `tests/` to `tests/<subdir>/`, increment the `parents` index by 1.
- Always add `@pytest.mark.runtime` tests to `tests/integration/` for subprocess/git
  e2e coverage; do not use `--no-commit` as a substitute for testing the real git commit
  path.

## Test folder structure

Tests are organized in subdirectories that mirror the source tree. New test files belong
in the matching subdirectory:

| Subdirectory | Source modules covered |
|---|---|
| `tests/commands/` | `src/repo_release_tools/commands/` |
| `tests/core/` | `changelog.py`, `cli.py`, `config/`, `state.py` |
| `tests/docs/` | `src/repo_release_tools/docs/` |
| `tests/eol/` | `src/repo_release_tools/eol/` |
| `tests/folders/` | `src/repo_release_tools/folders/` |
| `tests/hooks/` | `src/repo_release_tools/workflow/hooks.py` |
| `tests/integration/` | Real-subprocess e2e tests (`@pytest.mark.runtime`) |
| `tests/ui/` | `src/repo_release_tools/ui/` |
| `tests/version/` | `src/repo_release_tools/version/` |
| `tests/workflow/` | `src/repo_release_tools/workflow/git.py` |

The structure is enforced by `rrt folder check` rules in `pyproject.toml` under
`[tool.rrt.folders]`.

When adding command-focused support tests (for example, docstring checks or CLI wiring
helpers), place them under `tests/commands/` instead of the `tests/` root so the
`tests-root` folder rule stays valid.

## Do not

- Declare coverage done based on a passing test alone — coverage and correctness
  are separate checks; verify both explicitly.
- Mock the module under test — only mock its *dependencies*.
- Assert on a raw input value when the SUT transforms it (truncation, encoding,
  formatting). E.g. `sha[:7]` truncates — assert the 7-character prefix, not the
  full input string.
- Attempt to reach the same unreachable branch more than twice before flagging it.
