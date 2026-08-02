---
name: ll-help
description: List all available little-loops commands with descriptions
allowed-tools:
  - Bash(ll-help:*)
---

# Little Loops Help

Run `ll-help` and print its output verbatim — the catalog is generated at
runtime from `commands/*.md`/`skills/*/SKILL.md` frontmatter, so it can never
drift from what's actually installed (FEAT-2940).

```bash
ll-help
```

For the full `ll-*` pip-CLI reference (tools with no `/ll:` command/skill
counterpart), see `docs/reference/CLI.md`. For flag conventions and usage
examples, see `CONTRIBUTING.md`.
