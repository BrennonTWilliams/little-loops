---
type: ENH
id: ENH-517
priority: P4
effort: low
risk: low
---

# Document `--background` flag for `ll-loop run` in README

## Summary

Add documentation for the `--background` daemon mode flag to the README's `ll-loop` section, reflecting the feature added in v1.25.0 (commit 6d4d58c).

## Motivation

The `--background` flag enables `ll-loop run` to execute as a background daemon, which is a significant feature. The README's ll-loop section currently lists all subcommands but doesn't mention this flag in the usage examples. While "Run `ll-loop --help` for all options" is stated, notable features like daemon mode deserve explicit mention.

## Proposed Solution

Add a `--background` example to the `ll-loop run` usage block in `README.md`:

```bash
ll-loop run <loop-name> --background  # Run as background daemon
```

### Integration Map

| File | Change |
|------|--------|
| `README.md` | Add `--background` example to ll-loop section (~line 251) |

## Implementation Steps

1. Add example line showing `--background` flag usage to the ll-loop run examples in README.md

## Source

Discovered by `/ll:audit-docs` on 2026-02-27.
