---
id: BUG-3147
type: BUG
title: autodev pre-deferral GATE_MARKER regex misses common gated-issue phrasing
priority: P3
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-10'
captured_at: '2026-08-10T23:09:48Z'
completed_at: '2026-08-11T05:52:07Z'
labels:
- loops
- autodev
relates_to:
- BUG-3146
- ENH-3148
decision_needed: false
verify_verdict: VALID
size: Very Large
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3147: autodev pre-deferral GATE_MARKER regex misses common gated-issue phrasing

## Summary

The pre-deferral remedy dispatcher in `scripts/little_loops/loops/autodev.yaml`
(state `recheck_after_size_review`, ~line 2059) detects an "explicit unresolved
measurement/proof gate" in the issue body with a fixed three-alternative grep:

```bash
grep -qiE 'do not start otherwise|measurement \(gate\)|pre-implementation measurement' "$ISSUE_FILE"
```

Per the ENH-2978 rationale in the surrounding comment, the intent is: an issue
whose body says "don't begin until this gate opens" has an unproven-mechanism
readiness gap, so route it to `spike` regardless of which subscore is weakest.

The pattern set is too narrow to carry that intent. In run
`.loops/runs/autodev-20260810T171140/`, FEAT-3145's body carries the heading
`## ⚠ Gated — do not implement before the tier-3 evidence gate opens` — the
same condition in different words — and matched none of the three alternatives.
`GATE_MARKER` stayed `false` and the issue fell through to the subscore
fallback.

Note this defect compounds with the `min(others)` zero-floor bug: the fallback
that the miss routes into is itself broken for zero-coverage issues.

Widening the alternation is the obvious fix (e.g. `do not implement before`,
`gate opens`, `evidence gate`, `gated —`), but the pattern list is now large
enough that it may be worth promoting to a named constant / small helper with
test coverage rather than growing an inline regex, so the intent is testable
rather than restated at each call site.


## Current Behavior

`GATE_MARKER` is computed from a fixed three-alternative grep. An issue that
states its gate in any other wording is scored `false` and falls through to the
subscore fallback, which is itself broken for zero-coverage issues (BUG-3146).

## Expected Behavior

An issue body that explicitly says work must not begin until an external gate
opens is detected regardless of phrasing, and routes to `spike` per the
ENH-2978 intent.

## Motivation

The grep encodes a semantic intent ("this issue is gated on unproven evidence")
as three literal strings. Issue bodies are written by humans and by
`/ll:refine-issue`, neither of which is constrained to those strings, so the
detector misses the general case. FEAT-3145 is a concrete miss observed in run
`.loops/runs/autodev-20260810T171140/`.

## Proposed Solution

Two parts:

1. Widen the alternation to cover the common phrasings — `do not implement
   before`, `evidence gate`, `gate opens`, `⚠ Gated`.
2. Promote the pattern list out of the inline regex. It is now referenced by
   this state and, if ENH-3148 lands, by a pre-dequeue check as well — a third
   independent copy of the same concept is the failure mode to avoid. A named
   constant plus a small helper in the Python package (callable from the FSM
   action) makes the intent testable rather than restated per call site.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

Part 2 of this issue's proposed solution (extract the pattern list to a shared, tested Python helper) conflicts with an explicit prior decision on this exact code path. ENH-2978 — the issue that introduced the current three-literal grep — recorded a Decision Rationale (`.issues/enhancements/P3-ENH-2978-...md:209-255`) choosing to keep the check as an inline `grep -qiE` rather than extract it to a shared phrase-list module, scoring inline 12/12 vs extraction 5/12 on Consistency/Simplicity/Testability/Risk. Its stated reasoning: the inline grep idiom is already established twice elsewhere (`recursive-refine.yaml:557-564`, `autodev.yaml:911-925` and `:1298-1312`), is localized to the one state with the bug, requires no change to `dispatch_pre_deferral_remedy` (which already treats `REMEDY` as opaque), and fits the existing substring/ordering test style. A newer, structurally different precedent now exists for the extraction path: `design_gate_failed()` / `ll-issues check-design` (`scripts/little_loops/issue_parser.py:322-336`, `scripts/little_loops/cli/issues/check_design.py:19-39`) — a Python predicate wrapped by a CLI subcommand, consumed by the FSM as a plain shell conditional, built specifically to replace repeated inline `python3 -c` duplication in `autodev.yaml`. Both precedents are real; they were not evaluated against each other because `check_design.py` postdates ENH-2978's decision.

> **Selected:** Option A — widen the inline grep in place; matches the established idiom at three other call sites and avoids building shared infrastructure for a second caller (ENH-3148) that is still speculative.

**Option A**: Widen the inline `grep -qiE` alternation in place (`autodev.yaml:2059-2062`), consistent with ENH-2978's explicit prior decision. No new module, no CLI subcommand, `test_marker_literals_present_in_action`-style tests continue to work with an updated literal list.

**Option B**: Extract the pattern list to a shared, tested Python helper (e.g. a phrase tuple + predicate in `issue_parser.py` or `set_flags.py`, wrapped by a new CLI subcommand following the `check_design.py`/`cmd_check_design` shape — no such subcommand exists yet, it would be new), consumed by `autodev.yaml` and, if ENH-3148 lands, by its pre-dequeue check as well.

**Recommended**: Not resolved by this research pass — ENH-2978's own decision record directly contradicts this issue's stated Proposed Solution part 2, and that conflict should be adjudicated explicitly (e.g. via `/ll:decide-issue`) rather than defaulted either way.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-11:_

**Selected: Option A** — widen the inline `grep -qiE` alternation in place; do not extract to a shared Python helper/CLI subcommand at this time.

**Reasoning**: Option A matches an idiom already established at 7+ call sites across five loop YAMLs (`autodev.yaml:1004-1005,1382-1383,2274`, `recursive-refine.yaml:571-577`, `cua-agent-desktop.yaml:352,871,886`, `lib/common.yaml:331`, `rlhf-svg-evaluate.yaml:561`), reaffirming ENH-2978's own prior 12/12-vs-5/12 scoring for this exact code path. The counter-evidence for extraction — the `design_gate_failed()`/`check_design.py` precedent and ENH-3148's stated intent to reuse this matcher — is real but not yet a firm second caller: ENH-3148 is a freshly captured, undesigned P3 enhancement whose own preferred detection signal is structural (EPIC frontmatter), with prose matching only a fallback. Building a shared module now for a speculative, possibly-unused consumer is the premature abstraction this project's conventions explicitly warn against (see CLAUDE.md: "Don't design for hypothetical future requirements"). If ENH-3148 lands and commits to prose matching as its detection signal, that is the concrete trigger point for extraction — not before.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — widen inline grep | 3 | 3 | 3 | 3 | **12/12** |
| B — extract to Python helper + CLI | 1 | 1 | 2 | 1 | **5/12** |

**Key evidence**:
- ENH-2978's own Decision Rationale (`.issues/enhancements/P3-ENH-2978-...md:209-255`) scored this exact inline-vs-extract tradeoff 12/12 vs 5/12 in favor of inline, for a functionally analogous (though not identical) extraction target.
- `design_gate_failed()`/`cmd_check_design()` is a real, working precedent for extraction — but its trigger condition (a second concrete, committed caller) is not yet met; ENH-3148 is undesigned and may not end up using prose matching at all.
- No FSM state in this codebase currently shells out to a dedicated Python helper purely for phrase-list matching against issue body text — every existing instance of this exact check-shape uses inline grep.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — widen the `GATE_MARKER` inline
  `grep -qiE` alternation in place in state `recheck_after_size_review`
  (lines 2059-2062); no new/extracted module (Decision Rationale: Option A).
- `scripts/tests/test_autodev_loop.py` — update `test_marker_literals_present_in_action`
  (lines 689-696) for the widened literal set.
- `scripts/tests/test_builtin_loops.py:6403-6416` — update
  `test_recheck_after_size_review_measurement_gate_precedes_ambiguity_fallback`
  for the widened literal set.

### Dependent Files (Callers/Importers)
- ENH-3148 will consume the same matcher if implemented; coordinate so both use
  one definition.

### Similar Patterns
- The `stale_file_ref` / boilerplate detectors in `issue_parser.py` are the
  existing precedent for "pattern list over issue body text, with tests".

### Tests
- `scripts/tests/test_builtin_loops.py` or a new test beside the helper —
  assert FEAT-3145's actual heading text matches, and that a non-gated body
  does not.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:6403-6416` —
  `test_recheck_after_size_review_measurement_gate_precedes_ambiguity_fallback`
  asserts the three current literals (`do not start otherwise`,
  `measurement \(gate\)`, `pre-implementation measurement`) appear verbatim in
  the compiled action string. This test **will break** as soon as the
  alternation is widened and must be updated alongside
  `test_autodev_loop.py:684-763`'s `test_marker_literals_present_in_action`
  (already listed above) — both assert on the same literal set from two
  different angles (compiled YAML action string vs. extracted REMEDY
  selector) and must be kept in sync.

### Documentation
- None expected.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- `scripts/little_loops/loops/autodev.yaml` state `recheck_after_size_review` — full action block spans lines 1901-2105; `GATE_MARKER` (lines 2059-2062) feeds a `REMEDY=$(... | python3 -c "...")` selector (lines 2067-2083) that prints `spike` when `os.environ.get('GATE_MARKER') == 'true'`, else falls to the `amb < min(others)` subscore comparison (BUG-3146's target). The block only runs one-shot per issue per run, guarded by `autodev-pre-deferral-remedy-fired`.
- Existing precedent for extracting inline FSM logic into an owned, tested Python predicate + `ll-issues` CLI subcommand: `design_gate_failed()` (`scripts/little_loops/issue_parser.py:322-336`), wrapped by `cmd_check_design()` (`scripts/little_loops/cli/issues/check_design.py:19-39`), consumed at `autodev.yaml:1937` as `if ll-issues check-design "$ID"; then ...`. Its docstring frames it as replacing three inline `python3 -c` duplicates plus prose restatements — the same "N independent copies of one concept" failure mode this issue names.
- Existing precedent for a phrase-list-as-data module with FSM-callable CLI wrapper: `_SPIKE_NEEDED_PHRASES` / `FlagRule` / `apply_flags_from_notes()` in `scripts/little_loops/cli/issues/set_flags.py` — case-insensitive substring match (`phrase.lower() in lowered`) against a `tuple[str, ...]` constant, exposed via `ll-issues set-flags`.
- Existing precedent for a closed phrase-list constant with a paired presence-query function, no dedicated CLI: `_SUPERSEDED_CORRECTION_PHRASES` (`scripts/little_loops/issue_parser.py:823-836`) consumed inside `check_format_gaps()` (`:775-788`), with sibling public query `superseded_marker_count()` (`:925`).
- No FSM state in this codebase currently shells out to a dedicated Python helper purely for "match issue body against a phrase set" — every existing instance (`recursive-refine.yaml:571-577`'s `check_decision_needed`, `autodev.yaml:911-925`, `:1298-1312`, `cua-agent-desktop.yaml:350,869,884`, `lib/common.yaml:318`) uses inline `grep -q[iE]` against the resolved issue file path, matching the current (buggy) shape of the code this issue targets.
- Real gate-phrasing vocabulary found across `.issues/` (confirms Implementation Step 1's intent, no separate collection pass needed): `⚠ Gated`, `do not implement before`, `evidence gate`, `gate opens`, `is explicitly gated` (`.issues/features/P3-FEAT-3145-tasks-run-dispatch-surface-via-add-request-handler.md`, `.issues/enhancements/P3-ENH-3148-autodev-should-skip-explicitly-gated-issues-before-spending-refine-cycles.md`, `.issues/epics/P3-EPIC-3127-ll-mcp-mcp-server-as-little-loops-host-agnostic-serving-layer.md`); `work-evidence gate` (`.issues/bugs/P2-BUG-2409-ll-auto-plan-detection-short-circuits-before-uncommitted-work-check.md:67,323`, different subsystem, same noun-phrase construction); the current three literals (`do not start otherwise`, `measurement (gate)`, `pre-implementation measurement`) originate at `.issues/enhancements/P3-ENH-2978-pre-deferral-remedy-heuristic-ignores-measurement-gates.md:39,49,137-138,162-164,181-182`.
- Test location correction: the issue's own Tests section cites `scripts/tests/test_builtin_loops.py` as a possibility, but the actual current home for this state's tests is `scripts/tests/test_autodev_loop.py`, class `TestRecheckAfterSizeReviewMeasurementGateBranch` (lines 684-763). Its `_run_pre_deferral_remedy_selector()` helper (lines ~635-681) extracts the embedded `python3 -c` REMEDY-selector out of the YAML action string and runs it via `subprocess.run` with `GATE_MARKER`/`CONTRA_ONLY` passed through `env=` — it takes a pre-computed `"true"`/`"false"` string, so it does not itself exercise the grep/matcher; only `test_marker_literals_present_in_action` (lines 689-696) asserts the literal grep alternatives appear verbatim in the action string, and would need to change if the matcher moves out of the inline grep.

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

### Conventions in Force (pattern-finder)

- Inline `grep -qiE 'a|b|c'` alternations in this codebase stay on one physical line inside the `if`, with rationale (if any) in a comment above the `if`, not interleaved in the pattern string. The largest same-shape precedent is `scripts/little_loops/loops/lib/common.yaml:331` (`ll_auto_auth_check`), a 6-alternative single-line pattern with no wrapping — establishing that widening `GATE_MARKER`'s current 3-alternative pattern to 6-8 alternatives stays within the existing convention; no line-wrapping or variable-hoisting precedent exists in this codebase for a fixed (non-branch-varying) pattern of this size. Evidence: `scripts/little_loops/loops/lib/common.yaml:317-338`, `scripts/little_loops/loops/cua-agent-desktop.yaml:352,871,886`.
- Parenthesis/metacharacter literals inside an alternative are backslash-escaped in place (e.g. `measurement \(gate\)` at `autodev.yaml:2060`), not restructured — the same escaping approach applies to any new alternative containing regex metacharacters (e.g. `⚠ Gated` has none, but any future addition with `(`, `)`, `.`, etc. would need the same in-place escaping).
- Assigning the alternation to a shell variable first (`rlhf-svg-evaluate.yaml:540-561`'s `KEYWORDS` pattern) is used only where the pattern varies by `case` branch — not applicable here, since `GATE_MARKER`'s pattern is fixed regardless of issue content.

### Test-update convention (pattern-finder)

- Both existing tests that assert on `GATE_MARKER`'s literal pattern text (`scripts/tests/test_autodev_loop.py:689-696` `test_marker_literals_present_in_action`, `scripts/tests/test_builtin_loops.py:6403-6416`) use plain `assert "<literal>" in action` substring checks against the compiled YAML action string — no regex-aware or grep-simulation assertion machinery exists. Widening the alternation only requires *adding* new `assert "<new literal>" in action` lines (or new tuple entries in the `test_marker_literals_present_in_action` loop); it does not require rewriting the three existing assertions, since the existing three literals are not being removed. Evidence: `scripts/tests/test_autodev_loop.py:634-715`, `scripts/tests/test_builtin_loops.py:6403-6416`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

### Signatures
- Current inline check has no Python signature — it is a bash boolean test, `grep -qiE '...' "$ISSUE_FILE"`, inside `autodev.yaml:2059-2062`.
- `design_gate_failed(gaps: FormatGaps) -> bool` — existing predicate at `scripts/little_loops/issue_parser.py:322-336`, nearest signature shape if the fix follows the extraction (Option B) route.
- `apply_flags_from_notes(config: BRConfig, issue_id: str, notes: str | None, dry_run: bool) -> FlagResult` — alternate existing signature shape at `scripts/little_loops/cli/issues/set_flags.py`, for a phrase-list-driven check if that module is reused instead.

### Call Path
Option A (widen in place): `recheck_after_size_review`'s inline grep against `$ISSUE_FILE` stays the only step — no new call path.

Option B (extract, precedent shape): `design_gate_failed` -> `cmd_check_design` -> `autodev.yaml` shell conditional (mirrors the existing `ll-issues check-design` extraction at `autodev.yaml:1937`). Alternate existing shape: `apply_flags_from_notes` (`set_flags.py`'s phrase-list-as-data precedent).

### Decision Rules
- Gate condition (unchanged by this fix): an issue body containing any gate-phrase match sets `GATE_MARKER=true`, which forces `REMEDY=spike` regardless of subscore comparison — this precedence is existing ENH-2978 behavior, not new.
- New in this fix: the phrase set itself widens from 3 literals to cover the vocabulary catalogued in Integration Map (`⚠ Gated`, `do not implement before`, `evidence gate`, `gate opens`, `is explicitly gated`, plus the existing 3). No numeric threshold or proximity rule — matching remains case-insensitive substring/regex-alternation over the whole issue file body, with no dismissal/escape hatch (a false-positive match routes to `spike`, which is a one-shot, already-bounded remedy per BUG-3147's own Impact/Risk assessment).
- Whether the phrase set lives inline (Option A) or in an extracted, shared module (Option B) is the open decision surfaced under Proposed Solution — unresolved by this pass.

## Implementation Steps

1. Widen the inline `grep -qiE` alternation at `autodev.yaml:2059-2062` in
   place to add the additional gate phrasings already catalogued by codebase
   research (`⚠ Gated`, `do not implement before`, `evidence gate`,
   `gate opens`, `is explicitly gated`), alongside the existing three literals
   — per Decision Rationale's selected Option A, no separate phrase-collection
   pass or extraction to a shared module is needed.
2. Update `scripts/tests/test_autodev_loop.py`'s `test_marker_literals_present_in_action`
   (lines 689-696) and `scripts/tests/test_builtin_loops.py:6403-6416` to
   assert the new literals appear in the compiled action string, alongside
   the existing three.
3. Verify with `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_builtin_loops.py:6403-6416` — the widened
  alternation breaks this test's literal-substring assertions the same way it
  breaks `test_autodev_loop.py`'s `test_marker_literals_present_in_action`;
  both must be updated together to the new phrase set.

## Impact

- **Priority**: P3 - Mis-routes a remedy rather than corrupting state; the
  compounding partner (BUG-3146) is the more severe half.
- **Effort**: Small - Pattern widening plus extraction and a test.
- **Risk**: Low - A wider match sends more issues to `spike`, already bounded
  one-shot per issue per run.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-10 | Priority: P3

## Steps to Reproduce

1. Take an issue whose body contains `## ⚠ Gated — do not implement before the
   tier-3 evidence gate opens` (FEAT-3145).
2. Run `ll-loop run autodev FEAT-3145` so it reaches `recheck_after_size_review`
   below the readiness threshold.
3. Observe `GATE_MARKER` evaluates `false` and the dispatcher takes the
   subscore fallback instead of routing to `spike`.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `GATE_MARKER` computation in state `recheck_after_size_review`
- **Cause**: The detector matches three literal phrasings rather than the
  concept; semantically equivalent wording is not recognized.

## Location

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Line(s)**: 2057-2061 (at scan commit: 83b6d51b)
- **Anchor**: `GATE_MARKER` computation inside `recheck_after_size_review`
- **Code**:
```bash
          GATE_MARKER="false"
          if [ -n "$ISSUE_FILE" ] && grep -qiE 'do not start otherwise|measurement \(gate\)|pre-implementation measurement' "$ISSUE_FILE" 2>/dev/null; then
            GATE_MARKER="true"
          fi
```

## Session Log
- `/ll:manage-issue` - 2026-08-11T05:51:42 - `e5343417-b154-4262-99a7-5d0478e57f71.jsonl`
- `/ll:confidence-check` - 2026-08-11T05:12:09 - `2d7d4b50-f432-491c-9325-81d4aa29473e.jsonl`
- `/ll:reconcile-issue` - 2026-08-11T05:10:31 - `110dc9fa-4624-4e93-bf35-7258aafe609d.jsonl`
- `/ll:verify-issues` - 2026-08-11T05:06:32 - `e59017b2-ef6b-4f13-b3c7-af9d5a9d08b4.jsonl`
- `/ll:refine-issue` - 2026-08-11T05:04:18 - `1cfcf525-4265-46d7-8cb8-b4189e37fb8c.jsonl`
- `/ll:verify-issues` - 2026-08-11T05:01:26 - `9c6a5e35-85f4-40b8-9764-315971eac3ef.jsonl`
- `/ll:wire-issue` - 2026-08-11T04:59:49 - `8b07fe12-b5fe-4a57-9c51-43270b725a39.jsonl`
- `/ll:decide-issue` - 2026-08-11T04:57:52 - `d3b551d3-4de8-4a4a-873c-2b9e194ffef2.jsonl`
- `/ll:refine-issue` - 2026-08-11T04:51:07 - `59b7ebfe-8af3-45c9-a37b-9a470be85ef6.jsonl`
- `/ll:capture-issue` - 2026-08-10T23:10:11 - `81255c48-5bc6-4004-a8cd-3f14858f5cb5.jsonl`
