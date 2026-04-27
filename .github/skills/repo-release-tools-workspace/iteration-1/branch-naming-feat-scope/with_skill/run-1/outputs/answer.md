# Branch guidance for this task

Use a feature branch with the `cli` scope.

- **Suggested branch name:** `feat/cli-add-parser-caching`
- **Create it with:**

```bash
rrt branch new feat "add parser caching" --scope cli
```

If you later realize the scope should be `config`, rebuild the branch name instead of using `--scope` alone:

```bash
rrt branch rename --scope config "add parser caching"
```

That renames the current branch to `feat/config-add-parser-caching` while keeping the current type (`feat`).

If the branch was already pushed, update the remote after the local rename:

```bash
git push origin :feat/cli-add-parser-caching feat/config-add-parser-caching
git push --set-upstream origin feat/config-add-parser-caching
```
