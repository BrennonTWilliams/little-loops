---
id: BUG-1634
title: ll-loop list omits nested runnable loops (oracles/)
type: bug
priority: P3
status: open
labels: [cli, loops, discoverability]
---

# ll-loop list omits nested runnable loops

## Problem

`ll-loop list` enumerates only top-level YAMLs under `scripts/little_loops/loops/`. Nested runnable loops — currently `oracles/oracle-capture-issue.yaml` — are validatable and runnable but invisible from the listing:

```bash
$ ll-loop validate oracles/oracle-capture-issue
oracles/oracle-capture-issue is valid     # runnable

$ ll-loop list | grep -i oracle
# (no output)                              # not discoverable
```

Effect: users have no way to discover runnable nested loops without reading the filesystem. Anything we add under `oracles/` (or future subdirs) is dark.

## Reproduction

See above. Compare against `ll-loop validate` accepting the nested path — the runner clearly supports nested loops; only listing doesn't.

## Acceptance criteria

- [ ] `ll-loop list` includes runnable loops under nested subdirectories of `loops/`
- [ ] Library fragments under `loops/lib/` remain excluded (they're not valid FSMs)
- [ ] Nested loops display with their relative path (`oracles/oracle-capture-issue`) so users can copy/paste into `ll-loop run`
- [ ] Category grouping in the listing still works for nested loops (assign by frontmatter category or by subdirectory)
- [ ] Test coverage: a nested-runnable-loop fixture appears in `ll-loop list` output; a library-fragment fixture does not

## Notes

Found during `/ll:audit-docs` (2026-05-23). Shares a root cause with [[BUG-1633]] (non-recursive enumeration), but lives in CLI listing rather than doc verification. Fix the two together if convenient — they may share a "discover runnable loops" helper.
