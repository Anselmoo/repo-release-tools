#!/usr/bin/env python3
"""Render BUSINESS_RULES.md from the modernize-extract-rules workflow result.

Re-runnable: point WF_OUTPUT at the workflow task output JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WF_OUTPUT = (
    "/private/tmp/claude-502/-Users-hahn-LocalDocuments-GitHub-Forks-repo-release-tools/"
    "662db51b-0f5e-45c7-900f-182e4a408df1/tasks/w81pa3418.output"
)
HERE = Path(__file__).resolve().parent

# Behavior-contract (P0) selection, adjudicated in the main session because the
# workflow's P0 panel hit a usage limit. Criterion for THIS system: the rule
# guards the integrity of the user's repository or gates a destructive /
# irreversible operation. Keyword filter over name+source, reviewed by hand.
P0_PATTERNS = [
    r"publish[- ]snapshot",
    r"force[- ]push",
    r"rebootstrap",
    r"atomic",
    r"rollback",
    r"tag .*(refus|exist|overwrit)|refuses? to .*tag",
    r"preflight|pre-flight",
    r"dirty[- ]tree",
    r"promot",  # [Unreleased] promotion
    r"dedup",   # changelog dedup on squash
]


def is_p0(rule: dict) -> bool:
    hay = (rule.get("name", "") + " " + rule.get("plainEnglish", "")).lower()
    return any(re.search(p, hay) for p in P0_PATTERNS)


def clip(text: str, n: int = 420) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def card(rule: dict, idx: str) -> str:
    lines = [f"### {idx} — {rule['name']}", ""]
    lines.append(
        f"**Category:** {rule.get('category')} · **Priority:** {rule.get('priority')} "
        f"· **Confidence:** {rule.get('confidence')}  "
    )
    lines.append(f"**Source:** `{rule.get('source')}`")
    lines.append("")
    lines.append(rule.get("plainEnglish", "").strip())
    lines.append("")
    lines.append(f"- **Given** {rule.get('given')}")
    lines.append(f"- **When** {rule.get('when')}")
    lines.append(f"- **Then** {rule.get('then')}")
    if rule.get("parameters") and str(rule["parameters"]).strip() not in ("N/A", ""):
        lines.append(f"- **Parameters:** {clip(rule['parameters'], 300)}")
    for ec in (rule.get("edgeCases") or [])[:4]:
        lines.append(f"- **Edge case:** {clip(ec, 300)}")
    if rule.get("suspectedDefect"):
        lines.append(f"- ⚠️ **Suspected defect:** {clip(rule['suspectedDefect'])}")
    if rule.get("smeQuestion"):
        lines.append(f"- ❓ **SME question:** {clip(rule['smeQuestion'])}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    result = json.load(open(WF_OUTPUT))["result"]
    rules = result["confirmedRules"]
    rejected = result["rejectedRules"]

    p0 = [r for r in rules if is_p0(r)]
    p0_names = {r["name"] for r in p0}

    by_cat: dict[str, list[dict]] = {}
    for r in rules:
        by_cat.setdefault(r.get("category", "Other"), []).append(r)

    defects = [r for r in rules if r.get("suspectedDefect")]

    out = []
    out.append("# Business Rules — repo-release-tools (`src/repo_release_tools`)\n")
    out.append(
        "*Generated 2026-07-10 by `/modernize-extract-rules` (4 extraction rounds, "
        "per-rule citation verification by independent referee agents) and rendered by "
        "`render_business_rules.py`. "
        f"{len(rules)} rules confirmed, {len(rejected)} rejected by referees.*\n"
    )
    out.append("## Methodology & caveats\n")
    out.append(
        "- Three lens-scoped extractor agents per round (calculations / validations / "
        "lifecycle), loop-until-dry; **extraction stopped at the 4-round cap before "
        "running dry** — round 4 still surfaced 66 new rules, so a tail of "
        "lower-value rules likely remains uncatalogued.\n"
        "- Every rule below was confirmed by a referee agent that re-read the cited "
        "source location. 6 rules failed refereeing and are listed at the end.\n"
        "- **P0 adjudication caveat:** the workflow's independent P0 judging panel hit a "
        "usage limit and did not complete. The Behavior Contract section below was "
        "adjudicated in the coordinating session by a stated criterion (see there) and "
        "**requires SME confirmation before any phase ships against it.** The panel "
        "verdicts that did complete consistently re-tiered pure version arithmetic "
        "away from P0 (no money, no regulation) — that reasoning is applied here.\n"
        "- One **prompt-injection attempt** was detected in tool output during "
        "verification (a fabricated 'MCP Server Instructions' block not present in any "
        "repo file). The verifying agent disregarded it; no rule cites it. Recorded "
        "here because rule text mined from untrusted code is data, not instructions.\n"
    )

    out.append("## Behavior Contract (P0 candidates)\n")
    out.append(
        "**Criterion:** for a release tool, 'moves money / regulatory / data "
        "integrity' translates to: *guards the integrity of the user's repository "
        "(files, git history, published artifacts) or gates a destructive, "
        "irreversible operation.* These rules must be pinned by characterization "
        "tests and proven equivalent before any modernization phase ships. "
        f"{len(p0)} rules qualify:\n"
    )
    for i, r in enumerate(sorted(p0, key=lambda x: x["source"]), 1):
        out.append(card(r, f"P0-{i:02d}"))

    out.append("## Suspected defects (verified citations, behavior questioned)\n")
    out.append(
        "These are places where the *implemented* behavior is confirmed but the "
        "referee flagged it as probably not the *intended* behavior — issue-#140-class "
        "candidates. Each needs an SME ruling: fix (new behavior) or pin (characterize "
        "as-is):\n"
    )
    for i, r in enumerate(defects, 1):
        marker = " *(also in Behavior Contract)*" if r["name"] in p0_names else ""
        out.append(f"{i}. **{r['name']}**{marker} — `{r['source']}`  ")
        out.append(f"   {clip(r['suspectedDefect'])}\n")

    for cat in ("Calculation", "Validation", "Policy", "Lifecycle"):
        cat_rules = by_cat.get(cat, [])
        out.append(f"\n## {cat} rules ({len(cat_rules)})\n")
        for i, r in enumerate(sorted(cat_rules, key=lambda x: x["source"]), 1):
            out.append(card(r, f"{cat[:3].upper()}-{i:03d}"))

    out.append("\n## Rejected by referees (do not treat as behavior)\n")
    for r in rejected:
        out.append(f"- **{r.get('name')}** — `{r.get('source')}`")
    out.append("")

    (HERE / "BUSINESS_RULES.md").write_text("\n".join(out), encoding="utf-8")
    print(f"BUSINESS_RULES.md written: {len(rules)} rules, {len(p0)} P0 candidates, "
          f"{len(defects)} suspected defects")
    print("P0 candidates:")
    for r in sorted(p0, key=lambda x: x["source"]):
        print(f"  - {r['name']}  [{r['source']}]")


if __name__ == "__main__":
    main()
