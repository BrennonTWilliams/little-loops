---
id: ENH-3358
type: ENH
title: Convert MR-11-marked interpolation sites to safe forms (ENH-3342 corpus triage)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-29'
captured_at: '2026-08-29T19:44:17Z'
---

# ENH-3358: Convert MR-11-marked interpolation sites to safe forms (ENH-3342 corpus triage)

## Summary

ENH-3342 widened MR-11 (drop the fixed seven-key allowlist, add the
`captured`/`prev` namespaces, and delegate to `interp_sweep.classify_site()`).
Running the widened rule across the built-in loop corpus surfaced 665
pre-existing findings across 60 loop YAML files — far more than ENH-3342's
own triage step could convert in that session without risking dozens of
production automation loops. Per ENH-3342's `# ll-lint: mr11-ok(<var>)
<reason>` marker mechanism (added for exactly this situation), every one of
those 665 sites was marked with a well-formed marker citing this issue, so
the corpus stays `ll-loop validate`-clean while the actual conversion work is
tracked here.

## Current Behavior

665 `# ll-lint: mr11-ok(...)` markers across 60 files, citing this issue
(ENH-3358), each suppressing one otherwise-live MR-11 WARNING.

## Expected Behavior

Zero `# ll-lint: mr11-ok(...)` markers in `scripts/little_loops/loops/**`;
`ll-loop validate` stays clean because every site is actually safe, not
because it is marked.

## Motivation

ENH-3342's own Impact section: "if the residual marker set comes out large,
that is a signal to convert more, not to accept it." 665 is large. This issue
is the accepted deviation from ENH-3342's original AC 8 ("triaged... in this
issue") — recorded as a deliberate follow-up rather than silently absorbed
into ENH-3342's own session, per user decision on 2026-08-29.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

Convert the marked sites (one loop file, or one logical group of sites, per
pass) to a safe interpolation form and remove the marker at each site:

- bash-token position: add the `:shell` suffix (`${captured.run_dir.output:shell}`),
  or wrap in a single-quoted string / quoted heredoc where that fits the
  existing shape better.
- inside a Python literal (heredoc or `python3 -c "..."` body): hoist the
  value to an `LL_ARG_X=...` environment binding on the `python3` invocation
  line and read it via `os.environ` inside the body, per
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s documented idiom.

Enumerate the current marker set with:

```
grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/
```

As each site converts, its marker is removed. When the corpus's marker count
reaches zero, `test_builtin_loops.py`'s enumerated marker-set assertion
(ENH-3342 AC 8c) drives that to completion — a removed marker with no
corresponding literal-set update fails that test, keeping this issue's
progress and the checked-in enumeration in lockstep.

## Status

**Open** | Created: 2026-08-29 | Priority: P3
