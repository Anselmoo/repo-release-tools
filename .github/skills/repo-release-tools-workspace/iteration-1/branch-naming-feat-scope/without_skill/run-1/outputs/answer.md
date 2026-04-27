Suggested branch name: `feat/cli-parser-caching`

Create it with:

```bash
rrt branch new feat "parser caching" --scope cli
```

If later you realize the work belongs under config instead of cli, rename the current branch with:

```bash
rrt branch rename "parser caching" --scope config
```

That rebuilds the branch name as `feat/config-parser-caching` while keeping the current type (`feat`).
Do **not** use only `rrt branch rename --scope config` for this case — that form prepends a scope to the existing slug instead of replacing `cli`.
