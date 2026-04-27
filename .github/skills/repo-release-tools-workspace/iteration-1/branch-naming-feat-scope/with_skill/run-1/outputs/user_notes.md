# Caveat

Use a full rebuild when changing the scope from `cli` to `config`:

```bash
rrt branch rename --scope config "add parser caching"
```

Do **not** use `rrt branch rename --scope config` by itself for this case. Scope-only rename preserves the existing slug and prepends the new scope, which would produce `feat/config-cli-add-parser-caching` instead of the desired `feat/config-add-parser-caching`.
