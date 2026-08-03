# Phase 3.7: Prose Dependency Gate (FEAT-2849)

Run `ll-issues format-check [ISSUE-ID] --format json`. A non-empty
`prose_dep_drift` (prose claims a dependency on an active issue absent from
`blocked_by`/`depends_on`) is missing wiring: add it to `MUST_AUDIT` (tier
`hard`) so Phase 4 agents and the Integration Map's Dependent Files section
record it, and add `ll-issues link [ISSUE-ID] blocked_by [BLOCKER-ID]` to
Implementation Steps. A non-empty `stale_prose_dep` is not a wiring gap —
report it for `/ll:refine-issue`/`/ll:ready-issue` to clean up the prose, but
do not add a `blocked_by` edge for it.

**Canonical dependency phrasing (authoring side).** Any prose *you* write in
Phase 8 that asserts a cross-issue blocker must use a phrasing the extractor
recognizes: `Blocked by <ID>` / `Depends on <ID>` / `Requires <ID>`, or the
synonyms `blocked on`, `gated on`, `waiting on`, `contingent on`, `predicated
on`. Paraphrases ("blocking dependency unmet: BUG-3028 has not landed") parse as
nothing, so this gate stays silent and the edge is never written.
