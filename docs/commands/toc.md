# Table of Contents — `rrt toc`

Generate a Markdown table of contents from the ATX headings in a file.
The TOC can be printed to stdout or injected in-place into a target file via
the anchor system shared with `rrt tree --inject`.

<!-- rrt:auto:start:toc-cmd-ref -->
<!-- rrt:auto:end:toc-cmd-ref -->

## Usage

```
rrt toc FILE [--min-level N] [--max-level N]
rrt toc FILE --inject TARGET --anchor ID [--min-level N] [--max-level N] [--dry-run]
```

`FILE` is parsed for headings.  Without `--inject`, the generated TOC is printed
to stdout.  With `--inject` and `--anchor`, the anchored block inside `TARGET`
is replaced in-place.

## Options

| Flag | Default | Description |
|---|---|---|
| `FILE` | — | Markdown file to parse for headings |
| `--inject FILE` | — | Target file to update in-place |
| `--anchor ID` | — | Anchor ID inside the inject target |
| `--min-level N` | 1 | Shallowest heading level to include (`#`) |
| `--max-level N` | 6 | Deepest heading level to include (`######`) |
| `--dry-run` | — | Print result instead of writing (requires `--inject`) |

`--inject` and `--anchor` must always be used together.

## Anchor markers

Place a pair of HTML comments inside the target file:

```markdown
<!-- rrt:auto:start:my-toc -->
<!-- rrt:auto:end:my-toc -->
```

Everything between the markers is replaced on every run.  Content outside the
markers is preserved unchanged.  The markers are invisible in rendered Markdown.

## Examples

Print a TOC for `README.md` to stdout:

```bash
rrt toc README.md
```

Include only level-2 and level-3 headings:

```bash
rrt toc README.md --min-level 2 --max-level 3
```

Inject the TOC into `README.md` itself using the anchor `toc`:

```bash
rrt toc README.md --inject README.md --anchor toc
```

Preview without writing:

```bash
rrt toc README.md --inject README.md --anchor toc --dry-run
```

## GitHub-flavoured anchor algorithm

Anchors are generated following GitHub's rules:

1. Lowercase the heading title.
2. Replace spaces with `-`.
3. Remove every character that is not `[a-z0-9-]`.
4. Append `-1`, `-2`, … for duplicate headings.

## Fenced code blocks

Headings inside fenced code blocks (`` ``` `` or `~~~`) are never included in
the TOC, so code examples with `#!` shebangs or comment lines are ignored.
