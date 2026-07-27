# Phase 3.7: Prose Dependency Gate (FEAT-2849)

Run `ll-issues format-check [ISSUE-ID] --format json`. A non-empty
`prose_dep_drift` (prose claims a dependency on an active issue absent from
`blocked_by`/`depends_on`) is missing wiring: add it to `MUST_AUDIT` (tier
`hard`) so Phase 4 agents and the Integration Map's Dependent Files section
record it, and add `ll-issues link [ISSUE-ID] blocked_by [BLOCKER-ID]` to
Implementation Steps. A non-empty `stale_prose_dep` is not a wiring gap —
report it for `/ll:refine-issue`/`/ll:ready-issue` to clean up the prose, but
do not add a `blocked_by` edge for it.
