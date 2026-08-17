---
id: ENH-3244
type: ENH
title: Split template-placeholder detection out of the hedge scan's capped refine
  budget
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:14:03Z'
relates_to:
- BUG-3245
- ENH-3238
blocked_by:
- BUG-3245
---

# ENH-3244: Split template-placeholder detection out of the hedge scan's capped refine budget

## Summary

`ll-issues check-open-questions` treats literal template placeholders (`TBD`, `[Major phase 1]`) as
hedge vocabulary, so they share `check_hedge_attempts`' one-refine-per-run cap in
`refine-to-ready-issue.yaml` and get waived on the second red reading. Placeholders have a true-zero
target and are deterministically detectable; prose hedges have a genuine noise floor. They should
not share a budget.

## Current Behavior

The detection works. The waiver is what fails.

`\bTBD\b` is a term in `_OPEN_QUESTION_SIGNAL_RE` (`scripts/little_loops/issue_parser.py:1733`) and
`Integration Map` is in `_OPEN_QUESTION_SECTIONS` (`:1746`), so `ll-issues check-open-questions`
correctly returns exit 1 on an issue still carrying template debris.

Observed on the `refine-to-ready-issue` run over ENH-3238
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`, 27 routes):

```
refine_issue → wire_issue → verify_issue → VALID → check_hedges NO → hedge_attempts=1 → refine_followup
             → check_wire_done(=1) → verify_issue → VALID → check_hedges NO → hedge_attempts=2 → PROCEED
             → check_ac_automatable → confidence_check → done
```

`check_hedges` (`refine-to-ready-issue.yaml:301-310`) returned NO on **both** passes. The second red
reading hit `check_hedge_attempts`' cap (`:312-333`, `target: 2`, BUG-3170 — one hedge-forced refine
per run) and routed `on_no` to `check_ac_automatable`, i.e. proceed anyway.

The issue reached the `done` terminal carrying five literal `TBD - requires codebase analysis`
bullets and `1. [Major phase 1] / 2. [Major phase 2] / 3. [Verification approach]`. Downstream
`confidence_check` then scored it 96 readiness / 90 outcome, 25/25 on the ambiguity axis.

### Why the existing `boilerplate` gap class does not catch this

`format-check` already has a `boilerplate` gap class, but it fires only when a **required section's
body equals its `creation_template` in full** (`scripts/little_loops/issue_parser.py:853-856`):

```python
template = section_defs.get(name, {}).get("creation_template", "")
if template and _normalize_whitespace(stripped) == _normalize_whitespace(template):
    gaps.boilerplate.append(name)
```

Any partial fill defeats that whole-body equality test. ENH-3238's `## Integration Map` had
`### Codebase Research Findings` populated with real research while its five sibling subsections
still held `TBD` bullets — so the section body no longer equalled the template, `boilerplate` stayed
silent, and the debris passed. The new check must be **per-placeholder containment**, not
whole-section equality.

## Expected Behavior

An issue cannot reach `done` while its file still contains unfilled template placeholders. That
condition is checked deterministically, outside the hedge scan's capped budget, and reported as a
structural gap rather than as hedge vocabulary.

Prose hedges keep the BUG-3170 cap unchanged.

## Motivation

BUG-3170's cap is justified in-line at `refine-to-ready-issue.yaml:312-317`:

> The scan is an absolute-zero probe over vocabulary with no answer/hedge distinction, so a residual
> count is the steady state for a well-refined issue. One forced refine is worth its cost; a second
> red reading must not spend the shared budget and decompose the issue.

That reasoning is **correct for prose hedges** — "worth confirming", "needs decision", "should be
considered" are ordinary technical English with a genuine noise floor, and demanding zero would
thrash. It is **wrong for literal template placeholders**, which have a true-zero target, no
legitimate residual, and a deterministic fix.

Conflating the two means the noisy signal's justified cap silently waives the clean signal. Every
placeholder in the observed run originated from the shipped template itself (see Current Behavior),
so this is not a rare shape — it is the default state of every freshly created issue, and the gate
that should guarantee it gets filled in is the one being waived.

## Proposed Solution

Split the signal by kind.

1. **Template placeholders become a `format-check` structural gap**, not a hedge term. `ll-issues
   format-check` already exposes deterministic public JSON keys for exactly this style of non-LLM
   routing — `superseded_marker_count` (`issue_parser.superseded_marker_count`) is read by
   `autodev.yaml:1590-1596` to route a gate with no LLM in the chain (MR-1). Add a
   `placeholder_count` (or a `template_placeholders` structural gap) alongside it.

2. **Patterns to detect** — anchored to the literal strings the shipped template emits, so this
   stays a true-zero probe and does not drift into prose matching:
   - `TBD - requires codebase analysis`, `TBD - use grep to find references`,
     `TBD - search for consistency`, `TBD - identify test files to update`,
     `TBD - docs that need updates`, `TBD - requires investigation`
   - `[Major phase 1]`, `[Major phase 2]`, `[Verification approach]`
   - `[P0-P5]`, `[Small/Medium/Large]`, `[Low/Medium/High]`, `[Yes/No]`, `[YYYY-MM-DD]`
   - `[If applicable - describe what currently happens]`, `[What should happen instead]`,
     `[Why this issue matters - ...]`
   - An `_Added by \`/ll:refine-issue\` — <date> — based on codebase analysis:_` provenance stub with
     no bullet following it before the next heading (see BUG-3245, which produces these)

3. **Remove `\bTBD\b` from `_OPEN_QUESTION_SIGNAL_RE`** (`issue_parser.py:1733`) once the structural
   check covers it, so the hedge scan stops double-reporting it and its capped budget is spent only
   on genuine prose hedges. `\bto be determined\b` is prose and stays.

4. **Wire a gate into `refine-to-ready-issue.yaml`.** Uncapped — a placeholder is always a defect —
   but see Scope Boundaries for the interaction with the additive-only retry path, which is scoped
   separately.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_OPEN_QUESTION_SIGNAL_RE:1733` (drop `\bTBD\b`); add the
  placeholder pattern set and a `placeholder_count`-style public accessor next to
  `superseded_marker_count`.
- `scripts/little_loops/cli/issues/format_check.py` — surface the new count as a structural gap and
  in `--format json`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new gate consuming it; see Dependent
  Files for the routing constraint.
- `scripts/little_loops/templates/` — the issue templates that emit these placeholders are the
  authoritative source for the literal pattern list; keep the two in sync.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:301-333` — `check_hedges` /
  `check_hedge_attempts`. Removing `TBD` from the hedge vocabulary changes what this pair fires on;
  the BUG-3170 cap on the remaining prose vocabulary is deliberately left intact.
- `scripts/little_loops/loops/autodev.yaml:1590-1596` — the `superseded_marker_count` precedent this
  change mirrors. Any new key must follow the same "public JSON key read by a shell gate" shape.
- Every consumer of `ll-issues check-open-questions` — the exit-code contract changes meaning
  slightly (fewer true positives, all of them prose).

### Similar Patterns
- `superseded_marker_count` — deterministic count on `format-check --format json`, consumed by a
  non-LLM gate. The model for this change.

### Tests
- `scripts/tests/` — a test asserting a freshly created issue (`ll-issues create --variant full`)
  reports a non-zero placeholder count, and that a filled-in issue reports zero. The fresh-template
  case is the strongest fixture because the template ships the placeholders.
- Existing `check-open-questions` tests that assert on `TBD` will need updating when it moves.

### Documentation
- `docs/reference/CLI.md` — `ll-issues format-check` output keys, if enumerated there.

### Configuration
- N/A

## Implementation Steps

1. Add the placeholder pattern set and public count accessor in `issue_parser.py`, next to
   `superseded_marker_count`.
2. Surface it from `ll-issues format-check` as a structural gap and in `--format json`.
3. Remove `\bTBD\b` from `_OPEN_QUESTION_SIGNAL_RE`; update affected tests.
4. Add the uncapped gate to `refine-to-ready-issue.yaml`, routing a placeholder hit to a repair pass.
5. Add tests per the Tests section, including the fresh-template fixture.
6. `python -m pytest scripts/tests/` exits 0.

## Program Design

### Call Path

`check_open_questions` -> `superseded_marker_count` -> `cmd_format_check`

- `_OPEN_QUESTION_SIGNAL_RE` (`scripts/little_loops/issue_parser.py:1733`) currently carries
  `\bTBD\b`; `_OPEN_QUESTION_SECTIONS` (`:1746`) scopes the scan to seven sections including
  `Integration Map`. Together these make `ll-issues check-open-questions` exit 1 on template debris.
- `superseded_marker_count` (`scripts/little_loops/issue_parser.py`) is the shape to copy: a
  deterministic public count exposed on `ll-issues format-check --format json`.
- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py`) surfaces structural gaps and
  the JSON payload the new count joins.
- `autodev.yaml:1590-1596` consumes `superseded_marker_count` from a shell gate with no LLM in the
  routing chain (MR-1) — the precedent for how the new count gets wired.

### Decision Rules

- **Signal kind**: literal-string containment, not vocabulary matching. The pattern set is anchored
  to the exact strings `scripts/little_loops/templates/` emits, so the probe stays true-zero.
- **Budget**: uncapped. A placeholder is always a defect; there is no legitimate residual, so the
  BUG-3170 cap reasoning does not apply.
- **Boundary with the hedge scan**: prose hedges (`worth confirming`, `needs decision`,
  `to be determined`) stay in `_OPEN_QUESTION_SIGNAL_RE` under the existing cap. Only `\bTBD\b`
  moves.
- **Split-landing rule**: steps 1-3 and 5-6 (detection) may land without step 4 (routing). Detection
  without routing is still useful — `format-check` reports it — and routing depends on an unresolved
  repair-path decision (see Scope Boundaries).

### Signatures
- `superseded_marker_count(issue_path: Path) -> int` — the existing deterministic public accessor at
  `scripts/little_loops/issue_parser.py:1173` whose shape and JSON exposure the new count mirrors.
- `placeholder_count(issue_path: Path) -> int` — proposed new sibling accessor returning the number
  of unfilled template placeholders found in the issue file.

## Impact

- **Priority**: P2 - Silently lets template debris reach `done` and be scored 96/90. Not P1: the
  damage is a degraded issue file, not broken released behavior, and a human reviewing the issue
  catches it.
- **Effort**: Small - a pattern set, a public accessor, one gate, tests. Mirrors an existing
  precedent end to end.
- **Risk**: Low - the patterns are literal strings from the shipped template, so false positives are
  near-impossible. The one real risk is an uncapped gate looping when the repair pass cannot fix the
  placeholder; see Scope Boundaries.
- **Breaking Change**: No

## Scope Boundaries

**The additive-only retry path is deliberately not fixed here.** The observed run's cap spent its one
retry on `refine_followup`, which runs `/ll:refine-issue --auto --gap-analysis` — additive-only by
contract (`refine-to-ready-issue.yaml:177-181`, "Gap-analysis is additive-only (never removes
content)"). A placeholder needs *deleting*, so the only repair mode this loop can invoke is
structurally incapable of clearing what triggered it. Trigger and remedy are mismatched.

That means step 4's gate must route to a repair that can actually remove content, or it will spin.
Choosing that repair path — `/ll:reconcile-issue`, a new narrowly-scoped skill, or a widened
deletion right in `refine-issue` — is a design question with a blast radius beyond this issue and is
scoped separately. **This issue may land its detection half (steps 1-3, 5-6) independently of the
routing half (step 4).**

**Not widening prose-hedge detection.** BUG-3170's cap on genuine prose hedges is correct and stays.

## Related Issues

- BUG-3245 — produces the empty `_Added by_` provenance stubs this issue detects.
- ENH-3238 — the issue whose refine run surfaced this; the same run also passed two substantive
  errors that no gate in the loop could see.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:37 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:16:20 - `33a98a0f-5403-4525-92db-f7737c5401c4.jsonl`
