---
id: BUG-3245
type: BUG
title: refine-issue gap-analysis appends duplicate section headers and empty provenance
  stubs
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:14:11Z'
relates_to:
- ENH-3244
- ENH-3238
---

# BUG-3245: refine-issue gap-analysis appends duplicate section headers and empty provenance stubs

## Summary

`/ll:refine-issue --auto --gap-analysis` is not idempotent with respect to section headers. A second
pass re-emits `### Call Path`, `### Dependent Files (Callers/Importers)`, and the
`_Added by /ll:refine-issue_` provenance stub without checking whether an identical heading already
exists, producing duplicate headings and consecutive empty stubs in the issue file.

## Steps to Reproduce

Observed, not synthesized — on the `refine-to-ready-issue` run over ENH-3238
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`).

1. Run `ll-loop run refine-to-ready-issue <ISSUE-ID>` on an issue whose first-pass result trips a
   gate, so `check_refine_limit` routes to `refine_followup`.
2. The run executes `refine_issue` (`--auto`), then `wire_issue`, then `refine_followup`
   (`--auto --gap-analysis`) — confirmed by the run's route trace:
   `refine_issue → wire_issue → verify_issue → check_hedges NO → check_refine_limit → refine_followup`.
3. Read the resulting issue file.

## Current Behavior

After one `refine_issue` + one `wire_issue` + one `refine_followup` pass, ENH-3238's file contained:

```markdown
## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Call Path
```

Three consecutive identical provenance stubs with **no content between them** — each pass emitted
its header and then deposited nothing under it.

Separately, the file carried two `### Call Path` headings (one under `## Program Design` with a bare
symbol arrow, one further down with a different expanded path) and two
`### Dependent Files (Callers/Importers)` headings in different parent sections with different
content.

The duplicate headings were **created by** the retry pass, not merely left unfixed by it —
`refine_followup` ran additively and re-emitted headers without checking for an existing identical
one.

## Expected Behavior

`/ll:refine-issue` is idempotent with respect to section structure:

- The `_Added by_` provenance stub is emitted **only when the pass actually deposits at least one
  finding bullet under it**. A pass with no new findings emits nothing.
- A `### Call Path` / `### Dependent Files (Callers/Importers)` heading that already exists in the
  target section is **merged into**, not duplicated as a sibling.

Running the same refine pass N times over an unchanged codebase produces the same file as running it
once.

## Impact

- **Priority**: P2 - Degrades every issue that takes a retry path, which is the common case for any
  issue that trips a gate. Not P1: the damage is readability and downstream-parser ambiguity, not
  incorrect content.
- **Effort**: Small - a containment check before each header emission, plus deferring the provenance
  stub until a bullet exists.
- **Risk**: Low - the change only suppresses emissions; it never deletes existing content, so it
  needs no widening of `refine-issue`'s deletion rights.
- **Breaking Change**: No

## Root Cause

`commands/refine-issue.md` operates under a **"never remove existing content"** rule, with exactly
one narrow carve-out — the "Bounded marker-removal right" for `⚠ Superseded` markers, which
`commands/reconcile-issue.md:60-72` cites as its own precedent. Under that rule the only safe
primitive is *append*, so each pass appends its section scaffold unconditionally rather than
checking for an existing one.

The rule itself is correct and is not what needs changing. What is missing is a **containment check
before emission** — appending nothing is not removing anything, so idempotent emission is fully
compatible with the never-remove rule and needs no new deletion right.

The empty-stub case is a second, simpler defect: the provenance stub is emitted eagerly (before the
pass knows whether it has findings) instead of lazily (on first bullet).

## Proposed Solution

1. **Lazy provenance stub.** Emit `_Added by \`/ll:refine-issue\` — <date> — based on codebase
   analysis:_` only immediately before the first finding bullet the pass actually writes. No
   findings → no stub.
2. **Containment check before heading emission.** Before writing `### Call Path` or
   `### Dependent Files (Callers/Importers)`, check whether that heading already exists **within the
   same parent section**; if so, append under it rather than emitting a sibling.
3. Do **not** add a deletion right. Existing duplicates already in the backlog are cleaned by
   `/ll:reconcile-issue` (which holds an in-place rewrite mandate over `### Files to Modify` and the
   directive sections) or by hand — out of scope here.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — the emission rules for the provenance stub and the two headings.
- Generated host mirrors are regenerated, never hand-edited — `ll-adapt --host <gemini|qwen|kimi-code>
  --apply`. (See ENH-3238's Integration Map for why the "no DO NOT EDIT banner" test is not evidence
  of hand-authorship.)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:177-191` — `refine_followup`, the state that
  runs the additive `--gap-analysis` pass and therefore triggers this.
- `scripts/little_loops/issues/program_design.py` — the Program Design gate keys on `### Call Path`;
  a duplicated heading makes "which one is current" ambiguous to it and to any other consumer.

### Similar Patterns
- `commands/reconcile-issue.md` — holds the in-place-rewrite mandate and the precedent for how a
  narrow exception to the never-remove rule is authorized. This issue deliberately does not need one.

### Tests
- `scripts/tests/` — assert that running the gap-analysis emission logic twice over an unchanged
  issue produces a byte-identical file (idempotency), and that a pass with zero findings emits no
  provenance stub.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Make the provenance stub lazy (emit on first bullet, not before the pass).
2. Add the same-parent-section containment check before emitting `### Call Path` and
   `### Dependent Files (Callers/Importers)`.
3. Regenerate the three host mirrors with `ll-adapt`.
4. Add the idempotency and empty-stub tests.
5. `python -m pytest scripts/tests/` exits 0.

## Related Issues

- ENH-3244 — proposes detecting the empty `_Added by_` stubs this bug produces as a structural gap.
- ENH-3238 — the issue whose refine run exhibited this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-17T19:16:20 - `33a98a0f-5403-4525-92db-f7737c5401c4.jsonl`
