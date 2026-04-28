---
name: repo-release-tools CLI and coverage guidance
description: "Apply workspace-specific guidance for repo-release-tools CLI/UI improvements, coverage-aware changes, and research tool usage."
applyTo: "src/**/*.py"
---

This repository enforces coverage and CI policies through `.github/hooks/check_push_coverage.py` and the `uv run pytest -q -m "not runtime"` workflow.

When working in `repo-release-tools`, follow these rules:

- Prefer low-risk, Python-only CLI/UI improvements using existing modules.
- Do not add new runtime dependencies for command-line output or parser UX work.
- For UI and help enhancements, focus on `src/repo_release_tools/cli.py`, `src/repo_release_tools/output.py`, and `src/repo_release_tools/ui/*`.
- Use `fetch_webpage` and `mcp_github_search_code` when researching external examples, issue comments, or PR context before changing behavior.
- Avoid proposing or creating PRs that lower test coverage; if a change is necessary and coverage drops, explain the coverage gap and add tests to restore it.
- The repo currently reports low coverage in `src/repo_release_tools/ui/syntax.py`, `src/repo_release_tools/ui/color.py`, `src/repo_release_tools/ui/layout.py`, `src/repo_release_tools/ui/font.py`, `src/repo_release_tools/cli.py`, and `src/repo_release_tools/output.py`.
- Use existing hook behavior as a guardrail: coverage below 85.71% should be treated as a blocker unless the user explicitly approves a follow-on test expansion.
- When making CLI errors friendlier, preserve argparse semantics and exit codes while improving help text, suggestions, and examples.
- Persist preferences and follow-up context in repo-scoped memory when they are specific to this repository's workflow.
