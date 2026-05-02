Validate the health of the resolved rrt configuration for the current repository.

## Overview

`rrt doctor` is a repository health check for release automation. It inspects
the active configuration and looks for the kinds of issues that usually cause
release jobs to fail late: missing files, broken patterns, unreadable version
targets, and optional runtime EOL policy problems.

## What it checks

For each resolved version group, the command checks:

- version target files exist
- version target values can be read
- pin target patterns compile as regular expressions
- pin target files contain at least one match
- the group changelog file exists

It also checks any global pin targets, deduplicating repeated path/pattern
pairs so the same target is not reported twice.

If `[tool.rrt.eol]` is configured, the command adds a runtime EOL section that
checks the configured languages against the repository's host runtime and
project minimum versions.

## Output and severity

The command prints a grouped report for each version group and an overall
status at the end.

- missing targets and missing changelog files are errors
- unreadable version content is reported as a warning
- pin patterns that compile but do not match are reported as a warning
- valid matches and readable targets are reported as OK

For EOL checks, the command uses the configured thresholds from `[tool.rrt.eol]`
and reports the host runtime and project minimum for each configured language.

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

- The command reports health for the resolved configuration, not just the
  visible file in the current directory.
- EOL checks are only shown when EOL policy is configured.
- A warning does not fail the command; only error-level findings do.

## Related docs

- [Runtime EOL tracking](eol.md)
- [rrt eol (CLI)](rrt-cli.md)
- [pre-commit / lefthook](pre-commit.md)
- [GitHub Action](github-action.md)
