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
- To make a monkeypatched function raise an exception, use the generator throw pattern:
  `lambda *a, **kw: (_ for _ in ()).throw(SomeError("msg"))`.
- Add module-level imports for private symbols used in two or more tests; otherwise
  import inside the single test function that needs the symbol.
- After two failed attempts to cover a line, determine whether it is structurally
  unreachable (contradictory state, type already proven above, exhaustive enum). If so,
  add a comment in the test file noting the line is dead code and stop.

## Do not

- Declare coverage done based on a passing test alone — coverage and correctness
  are separate checks; verify both explicitly.
- Mock the module under test — only mock its *dependencies*.
- Assert on a raw input value when the SUT transforms it (truncation, encoding,
  formatting). E.g. `sha[:7]` truncates — assert the 7-character prefix, not the
  full input string.
- Attempt to reach the same unreachable branch more than twice before flagging it.
