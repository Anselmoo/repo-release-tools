#!/usr/bin/env python3
"""Grade repo-release-tools skill eval runs for iteration 1."""

from __future__ import annotations

import json
import re
from pathlib import Path


ITERATION_DIR = Path(__file__).resolve().parent


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_json(path: Path) -> dict:
    return json.loads(_read_text(path)) if path.exists() else {}


def _contains(text: str, *needles: str) -> bool:
    lowered = text.lower()
    return all(needle.lower() in lowered for needle in needles)


def _check_eval_0(answer: str) -> list[tuple[bool, str]]:
    branch_match = re.search(r"`(feat/[a-z0-9-]+)`", answer)
    branch_ok = (
        bool(branch_match)
        and "parser" in branch_match.group(1)
        and "caching" in branch_match.group(1)
    )
    create_ok = _contains(answer, "rrt branch new feat")
    rename_ok = _contains(answer, "rrt branch rename", "config")
    return [
        (
            branch_ok,
            f"Found suggested branch name {branch_match.group(1)!r}."
            if branch_ok
            else "No matching `feat/...` branch recommendation for parser caching was found.",
        ),
        (
            create_ok,
            "Answer includes an explicit `rrt branch new feat ...` command."
            if create_ok
            else "Missing explicit `rrt branch new feat ...` command.",
        ),
        (
            rename_ok,
            "Answer explains a `rrt branch rename ...` follow-up that changes scope to config."
            if rename_ok
            else "Missing a valid `rrt branch rename ...` explanation for switching to config scope.",
        ),
    ]


def _check_eval_1(answer: str) -> list[tuple[bool, str]]:
    workflow_ok = _contains(answer, "incremental", "squash") and _contains(
        answer, "skip", "changelog enforcement"
    )
    auto_ok = _contains(answer, "per-commit") and _contains(answer, "release-only")
    config_ok = _contains(answer, "changelog_workflow") and _contains(answer, "version_targets")
    return [
        (
            workflow_ok,
            "Answer contrasts incremental maintenance with squash/release-time changelog behavior."
            if workflow_ok
            else "Answer does not clearly explain the incremental vs squash behavior difference.",
        ),
        (
            auto_ok,
            "Answer states the `auto` mapping, including `per-commit` and `release-only`."
            if auto_ok
            else "Answer does not clearly describe how `changelog-strategy: auto` resolves.",
        ),
        (
            config_ok,
            "Answer includes config text with `changelog_workflow` and a `version_targets` entry."
            if config_ok
            else "Answer is missing a minimal config example with both `changelog_workflow` and `version_targets`.",
        ),
    ]


def _check_eval_2(answer: str) -> list[tuple[bool, str]]:
    precommit_ok = _contains(answer, "rrt-update-unreleased") and _contains(
        answer, "rrt-commit-subject"
    )
    no_conflict = not (
        _contains(answer, "- id: rrt-update-unreleased")
        and _contains(answer, "- id: rrt-changelog")
    )
    lefthook_ok = (
        _contains(answer, "rrt-hooks pre-commit")
        and _contains(answer, "rrt-hooks update-unreleased --message-file {1}")
        and _contains(answer, "rrt-hooks commit-msg {1}")
    )
    path_ok = _contains(answer, "path") and _contains(answer, "rrt-hooks")
    return [
        (
            precommit_ok and no_conflict,
            "Answer gives installed-CLI pre-commit guidance without enabling both changelog hooks together."
            if precommit_ok and no_conflict
            else "Pre-commit guidance is missing required hooks or recommends conflicting changelog hooks together.",
        ),
        (
            lefthook_ok,
            "Answer includes the expected lefthook commands for branch, changelog update, and commit subject checks."
            if lefthook_ok
            else "Lefthook example is missing one or more expected `rrt-hooks` commands.",
        ),
        (
            path_ok,
            "Answer explains the PATH requirement for `rrt-hooks`."
            if path_ok
            else "Answer does not explain when `rrt-hooks` must be on PATH.",
        ),
    ]


CHECKS = {
    0: _check_eval_0,
    1: _check_eval_1,
    2: _check_eval_2,
}


def grade_run(run_dir: Path, eval_id: int, expectations: list[str]) -> None:
    outputs_dir = run_dir / "outputs"
    answer = _read_text(outputs_dir / "answer.md")
    transcript = _read_text(run_dir / "transcript.md")
    notes = _read_text(outputs_dir / "user_notes.md")
    timing = _load_json(run_dir / "timing.json")

    checks = CHECKS[eval_id](answer)
    graded_expectations = [
        {"text": text, "passed": passed, "evidence": evidence}
        for text, (passed, evidence) in zip(expectations, checks, strict=True)
    ]
    passed = sum(1 for item in graded_expectations if item["passed"])
    failed = len(graded_expectations) - passed

    user_notes_summary = {"uncertainties": [], "needs_review": [], "workarounds": []}
    if notes:
        user_notes_summary["needs_review"].append(notes.strip())

    payload = {
        "expectations": graded_expectations,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(graded_expectations),
            "pass_rate": round(passed / len(graded_expectations), 2)
            if graded_expectations
            else 0.0,
        },
        "execution_metrics": {
            "tool_calls": {},
            "total_tool_calls": 0,
            "total_steps": transcript.count("\n1.")
            + transcript.count("\n2.")
            + transcript.count("\n3.")
            + transcript.count("\n4.")
            + transcript.count("\n5."),
            "errors_encountered": 0,
            "output_chars": len(answer),
            "transcript_chars": len(transcript),
        },
        "timing": timing,
        "claims": [],
        "user_notes_summary": user_notes_summary,
        "eval_feedback": {"suggestions": [], "overall": "No suggestions, evals look solid"},
    }

    (run_dir / "grading.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for eval_dir in sorted(
        path for path in ITERATION_DIR.iterdir() if path.is_dir() and path.name != "__pycache__"
    ):
        metadata = _load_json(eval_dir / "eval_metadata.json")
        if not metadata:
            continue
        eval_id = metadata["eval_id"]
        expectations = metadata["assertions"]
        for config_dir in sorted(path for path in eval_dir.iterdir() if path.is_dir()):
            for run_dir in sorted(
                path
                for path in config_dir.iterdir()
                if path.is_dir() and path.name.startswith("run-")
            ):
                answer_path = run_dir / "outputs" / "answer.md"
                if answer_path.exists():
                    grade_run(run_dir, eval_id, expectations)


if __name__ == "__main__":
    main()
