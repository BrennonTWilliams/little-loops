---
id: ENH-2367
type: ENH
title: "audit-loop-run \u2014 surface literal captured values and PID-corruption heuristic\
  \ instead of inferring \"interpolation sentinel\""
priority: P2
status: done
captured_at: '2026-06-28T06:35:00Z'
completed_at: '2026-06-28T07:20:27Z'
discovered_date: 2026-06-28
discovered_by: audit-loop-run
labels:
- captured
- skills
- loops
- audit
- observability
relates_to:
- ENH-2366
- BUG-2351
decision_needed: false
confidence_score: 96
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2367: audit-loop-run — surface literal captured values and a PID-corruption heuristic

## Summary

The `audit-loop-run` flow (`skills/audit-loop-run/SKILL.md`, with diagnosis from the
`loop-specialist` agent) produced a **confidently wrong root cause** when auditing
`interactive-component-generator` run `2026-06-28T054140`. It is worth hardening the
flow so a misdiagnosis like this cannot mislabel a P0 — particularly if these audits
feed automated issue creation.

## Current Behavior

The `init` state captured `run_dir.output == "66563(pwd)/66563DIR"`. The audit
concluded:

- the value was an **"interpolation sentinel"** / "unparseable path," and
- the cause was **unescaped** bash (`$(pwd)/$DIR`), recommending *more* escaping.

Both are backwards. Verified empirically against `DefaultActionRunner` +
`interpolate()`:

- `interpolate()` only rewrites `${ns.path}` and `$${` → `${`; it leaves bare
  `$(...)`/`$VAR` untouched and **never emits a numeric sentinel**.
- The runner does `bash -c <action>` with no `$$`→`$` unescape, so the loop's
  **over-escaped** `$$(pwd)/$$DIR` expanded `$$` to the **PID** (`66563` is a PID),
  producing `66563(pwd)/66563DIR`.

So the corruption came from over-escaping, the real fix was to *remove* a `$`, and
`66563` was a PID, not a sentinel. The audit's narrative ("the LLM stripped the
`(pwd)` placeholder") was a post-hoc rationalization of the PID artifact.

## Expected Behavior

When `audit-loop-run` or `loop-specialist` encounters a captured shell value matching
the PID-corruption pattern (`^\d{2,7}\b` prefix where the action used `$$(` or `$$VAR`):

1. Quote the captured value verbatim in the diagnosis (e.g., `"66563(pwd)/66563DIR"`) without inferring "sentinel" or "placeholder" semantics
2. Flag the pattern as **over-escaped shell / PID corruption** (MR-9) and recommend removing the extra `$`
3. Cross-check budget-exhaustion claims: if `steps_consumed / max_steps` is low (< 0.3), reject budget-exhaustion as a root cause before accepting it

The audit flow must never recommend *adding* escaping (`$$`) when the captured value already shows PID-expansion artifacts.

## Motivation

`audit-loop-run` verdicts and `loop-specialist` diagnoses are inputs to issue
creation and to the harness-optimization guidance. A diagnosis that inverts the fix
direction (here: "add escaping" when the fix is "remove escaping") would, if applied,
make the loop *more* broken. This is the same trust problem as [[BUG-2351]]
(audit-loop-run mislabeling), one layer up: the mechanical/LLM signal disagreed with
ground truth.

## Proposed Solution

1. **Surface literal captured values verbatim.** When the audit cites a captured
   value, quote it exactly and avoid inferring "sentinel"/"placeholder" semantics the
   engine does not produce. The interpolation engine emits no numeric sentinels
   (`interpolation.py` — `VARIABLE_PATTERN`, `ESCAPED_PATTERN`, no digit markers).
2. **Add a PID-corruption heuristic.** A captured shell value of the form
   `^\d{2,7}\b` (a bare PID prefix) where the loop's action used `$$(` or `$$VAR`
   should be flagged as **over-escaped shell** (now MR-9), not "unparseable path."
3. **Cross-check diagnose claims against the run budget.** The audit blamed "budget
   exhausted" at 7/120 steps; a numeric guard (`steps_consumed / max_steps`) before
   accepting a budget-exhaustion root cause would have caught the contradiction.

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — add the captured-value-verbatim contract, the
  PID/over-escape heuristic, and the budget cross-check to the diagnosis steps.
- `agents/loop-specialist.md` — extend the failure-mode taxonomy with
  "over-escaped shell / PID corruption" so post-hoc diagnoses name it correctly and
  point at MR-9.

### Dependent Files (Callers/Importers)
- N/A — `SKILL.md` and agent markdown files are not imported by Python code.

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` — skill presence/argument tests; extend with a scenario that feeds a PID-corrupted captured value and asserts the verdict names "over-escaped-shell-pid-corruption"
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — loop-specialist eval tests; add case asserting the new failure-mode name is recognized

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:_validate_overescaped_shell` (MR-9) — the
  shift-left gate; the audit heuristic should reference the same regex signature:
  `_OVERESCAPED_SHELL_RE = re.compile(r"\$\$(?=\(|[A-Za-z_])")` (line 121)

### Documentation
- N/A — no standalone documentation files need updating.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`action_complete.output_preview`** in `events.jsonl` is where literal captured values appear in the JSONL stream — read this field (not just `state.json`) when implementing the PID-corruption heuristic check. Reference: `skills/debug-loop-run/reference.md:35` ("There is no `capture` event in the JSONL stream — read capture output from `action_complete.output_preview`").
- **`scripts/tests/test_fsm_validation.py:TestOverescapedShell`** (line 3147): the `_simple_fsm()` helper (line 3150) is the minimal FSM structure to follow for new audit PID-corruption unit tests. `test_mr9_counts_each_occurrence` at line 3185 (`action: 'echo "$$(pwd)/$$DIR"'` → 2 findings) is the exact pattern from the failing run.
- **`scripts/tests/fixtures/fsm/assess-shallow-iteration.yaml`** — fixture format for heuristic-driven audit-loop-run tests; follow this pattern when adding a synthetic `state.json` fixture for the verification step.
- **`skills/review-loop/reference.md:38–48`** — the MR-* check catalog table does not yet include MR-9. If the review-loop skill should also surface MR-9 cross-references (currently out of scope per Scope Boundaries, but worth noting for a follow-up issue).
- **Verbatim-quote contract pattern**: `skills/create-loop/loop-types.md:815,912,1080,1349` — the established phrasing is "Quote the EXACT line(s) from the output supporting your verdict (verbatim, in quotes). If you cannot find a verbatim quote, your verdict MUST be No." Mirror this phrasing in the Step 4 addition to SKILL.md.

## Implementation Steps

1. **`skills/audit-loop-run/SKILL.md` — Step 4 (line 179): verbatim-quote contract.** After
   the `captured` dict schema note, add: "Quote every `.output` value verbatim when citing
   it; do not infer 'sentinel' or 'placeholder' labels — the interpolation engine emits no
   numeric markers (only `\x00ESCAPED\x00`, an internal placeholder that is never present in
   captured output). Correct the schema comment: dict keys are capture *variable names*
   (from `capture:` declarations), not state names."

2. **`skills/audit-loop-run/SKILL.md` — Step 5 (line 187-194): PID-corruption fault signal.**
   Add to the fault-signal list: "Over-escaped shell / PID corruption: when a captured
   `.output` value matches `^\d{2,7}\b` *and* the action text for that state contains `$$(` or
   `$$[A-Za-z_]` (same pattern as `_OVERESCAPED_SHELL_RE` in `validation.py:121`), flag as
   **over-escaped-shell-pid-corruption** (MR-9) and recommend *removing* the extra `$`, never
   adding more escaping."

3. **`skills/audit-loop-run/SKILL.md` — Step 5 or new Step 5.6: budget-utilization guard.**
   Add: "Before accepting budget-exhaustion as a root cause, compute
   `STEPS_CONSUMED / MAX_STEPS`. Derive `STEPS_CONSUMED` from `loop_complete.iterations`
   in `events.jsonl` (there is no `steps_consumed` field in `state.json`). If the ratio is
   < 0.3, reject budget-exhaustion as the primary cause."

4. **`agents/loop-specialist.md` — Failure-Mode Taxonomy table (line 57-65): add 8th mode.**
   New row: `**over-escaped-shell-pid-corruption** | Captured shell `.output` value begins
   with a PID (`^\d{2,7}\b`) because the action used `$$(` or `$$VAR` — bash expanded `$$`
   to the process PID at `bash -c` time. The interpolation engine never emits numeric
   markers; a digit-prefixed capture is always PID expansion. | Remove the extra `$` (use
   single `$(cmd)` / `$VAR`); run `ll-loop validate` to confirm MR-9 is cleared.`
   Also add `- [ ] over-escaped-shell-pid-corruption` to the diagnosis artifact template
   checklist (same file, "Failure modes observed" section ~line 87).

5. Verify: re-audit run `2026-06-28T054140` (or create a fixture with a `$$(pwd)`-captured
   value in a `state.json`); the flow should classify it as `over-escaped-shell-pid-corruption`
   and recommend single-`$`.

## Scope Boundaries

Out of scope:
- Changes to the FSM interpolation engine (`interpolation.py`) itself
- Changes to how captured values are stored in run artifacts (`.loops/runs/`)
- Backporting re-diagnoses to existing mislabeled issues
- General overhaul of `loop-specialist` failure modes beyond PID-corruption / over-escaped shell
- Changes to MR-9 validation logic in `scripts/little_loops/fsm/validation.py` (already implemented; this issue references it, not modifies it)

## Impact

- **Priority**: P2 — Misdiagnoses feed automated issue creation; wrong fix direction actively worsens loops
- **Effort**: Small — Targeted additions to `SKILL.md` and `agents/loop-specialist.md`; no new systems or data structures
- **Risk**: Low — Additive heuristic checks; existing audit behavior unchanged when no PID pattern is detected
- **Breaking Change**: No

## Success Metrics

Re-audit run `2026-06-28T054140` (or a synthetic fixture with a `$$(pwd)`-captured
value): the flow should classify it as over-escaped shell / PID corruption and
recommend single-`$`, not flag an "interpolation sentinel" or recommend more escaping.

## Status

**Open** | Created: 2026-06-28 | Priority: P2


## Resolution

- Added verbatim-quote contract to Step 4 of `skills/audit-loop-run/SKILL.md`: captured `.output` values must be quoted exactly; corrected `captured` dict schema comment to reflect capture *variable names* (not state names).
- Added `over-escaped-shell-pid-corruption` (MR-9) to the Step 5 fault-signal list with `^\d{2,7}\b` prefix heuristic and recommendation to remove the extra `$`.
- Added Step 5.6 budget-utilization guard: reject budget-exhaustion as root cause when `STEPS_CONSUMED / MAX_STEPS < 0.3`.
- Extended `agents/loop-specialist.md` failure-mode taxonomy with 8th mode `over-escaped-shell-pid-corruption`; added checklist entry to diagnosis artifact template.
- Added `assess-pid-corruption.yaml` fixture and `TestPIDCorruptionDiscriminator` / `TestLoopSpecialistPIDCorruptionMode` test classes.

## Session Log
- `/ll:ready-issue` - 2026-06-28T07:13:51 - `c8ad6ad7-c82b-42e4-8de7-ab2fd3ccb404.jsonl`
- `/ll:confidence-check` - 2026-06-28T00:00:00Z - `7f5f9389-2bdf-4820-ba71-87fd2a007ad2.jsonl`
- `/ll:format-issue` - 2026-06-28T07:08:26 - `37a2d401-2d00-4114-b303-f860dbbb4f51.jsonl`
- `/ll:refine-issue` - 2026-06-28T06:31:08 - `846e532c-b018-45c9-8c76-e4f1186d3d5c.jsonl`
- `/ll:refine-issue` - 2026-06-28T06:30:03 - `ba89e2dc-b6ef-4515-a509-01a6b89cf62c.jsonl`
- `/ll:format-issue` - 2026-06-28T06:22:28 - `bf72d9b6-29c9-40ec-bb42-a2af81be2817.jsonl`
