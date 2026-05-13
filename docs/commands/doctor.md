---
title: "rrt doctor"
permalink: "/commands/doctor/"
---

# rrt doctor

Validate the core automation health of the resolved rrt configuration.

## Overview

`rrt doctor` is the basics-first repository health check. It focuses on the
shared automation wiring around the resolved configuration — local hooks, CI
workflows, and guidance to the feature-specific checks that own deeper policy
validation.

## What it checks

The command checks the automation surfaces that tell you whether repository
basics are wired correctly:

- `.pre-commit-config.yaml` when present
- `lefthook.yml` when present
- `.github/workflows/*.yml` / `.yaml` when present

The checks are intentionally light-touch: they verify presence, readability,
and whether the file appears to reference repo-release-tools policy checks.
They do **not** replace the deeper feature validators.

## Output and severity

The command prints one grouped report for the core automation surfaces and an
overall status at the end.

- unreadable automation files are errors
- missing optional integration surfaces are warnings
- surfaces that exist but do not appear to reference repo-release-tools are warnings
- readable, recognized surfaces are reported as OK

At the end, `rrt doctor` also points you to the feature-specific commands that
own deeper validation, such as `rrt release check`, `rrt docs check`, and
`rrt eol`.

## Config discovery behavior

If no config file can be found, the command prints repository guidance and
exits with an error.

If a config is auto-detected, the command emits a notice on stderr before the
main report so you can tell that rrt did not use an explicitly selected file.

## Examples

```bash
rrt doctor
```

## Caveats

- The command reports core automation health for the resolved configuration,
    not just the visible file in the current directory.
- Feature-specific checks belong to their own surfaces: `rrt release check`,
    `rrt docs check`, and `rrt eol`.
- A warning does not fail the command; only error-level findings do.

## Related docs

- [Runtime EOL tracking](eol.md)
- [rrt eol (CLI)](rrt-cli.md)
- [rrt release check](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
