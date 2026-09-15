---
id: ENH-3480
type: ENH
title: wire-issue first pass misses call sites inside already-known files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T19:28:33Z'
testable: true
program_design_not_applicable: true
reconcile_attempted: true
confidence_score: 85
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3480: wire-issue first pass misses call sites inside already-known files

## Summary

`/ll:wire-issue`'s first pass systematically misses call sites that live inside files the issue already names; a second pass on the same issue then "discovers" them. Observed on BUG-3477 and BUG-3478: pass 1 (2026-09-14, session `bac75f45`) vs pass 2 (2026-09-15, session `6d7823a0`). Most BUG-3477 pass-2 findings were intra-file sites in one of four already-listed files (`scripts/little_loops/cli/harness.py`, `scripts/tests/test_cli_harness.py`, `docs/reference/API.md`, `docs/reference/CLI.md`). A few pass-2 findings (`scripts/tests/test_fsm_evaluators.py`, `docs/generalized-fsm-loop.md`, `scripts/little_loops/loops/lib/common.yaml`, `docs/guides/HISTORY_SESSION_GUIDE.md`) were new-file discoveries from the widened pass-2 `key_symbols` search net, not intra-file misses — a separate phenomenon this fix does not target (see cause 2 below for the scope of the intra-file subset).

Two structural causes in `skills/wire-issue/SKILL.md`:

1. **Key symbols are seeded only from backticked names in the issue text** (Phase 3, `SKILL.md:108-132`). Before pass 1 the BUG-3477 issue named 8 harness symbols. Pass 1's own appended blocks introduced `_report_samples()`, `_run_compare_arm()`, `_run_baseline_phase()`, `BaselineDelta`, `cmd_skill()`; a `/ll:refine-issue` run between passes added more. Pass 2 therefore searched roughly twice the symbol set, and nearly every "new" call site is a caller of a symbol that only entered the issue during pass 1. The skill is self-expanding by one hop per pass.

2. **Agent prompts exclude whole files, and the Phase 5 diff is file-granular.** Agent 1 and Agent 2 of Phase 4 say "Exclude files already in the already-known lists" / "Exclude files already known from the issue" (`SKILL.md:180,212`; Agent 3 has no exclusion wording), and `MISSING_WIRING` categories are all "files ... not in known_*" (`SKILL.md:269-281`). There is no category for additional sites inside a known file, so agents have a standing instruction to skip exactly the files where most remaining call sites live. Pass 2 only surfaced them because the widened symbol set produced grep hits that landed in those files anyway.

Minor contributing factor: `harness.py` grew several hundred lines between passes and the 09-15 refine pass rewrote line citations, so pass-2 agents re-read the file fresh instead of trusting stale anchors.

**Proposed fix (in the skill only, no Python):**

- (0) Add a `known_sites: [path:symbol]` field to Phase 3 `EXISTING_WIRING`, extracted from every existing Integration Map bullet of the form `` `path` — ... `symbol()` ``. This is the dedup key for everything below; without it, intra-file findings are re-reported on every pass.
- (a) Change the Phase 4 exclusion wording in Agent 1 and Agent 2 from "exclude known files" to "exclude already-cited `path:symbol` sites in `known_sites`; report additional call sites, tests, or doc locations inside known files as new." Add a matching new instruction to Agent 3, which has no exclusion wording today.
- (b) Add a `sites_to_add` category to Phase 5 `MISSING_WIRING` (`path:line` + symbol within a known file, filtered against `known_sites`) and render it in Phase 8a with the `_Wiring pass added by \`/ll:wire-issue\`:_` marker (destinations pinned in Proposed Solution).
- (c) Expand `key_symbols` one bounded hop before Phase 4 (required, not optional — it addresses cause 1, which explains most pass-2 findings): for each symbol in `files_to_modify`, grep its callers inside those same files only and add the enclosing function names to the seed set. One hop, no recursion, no files outside `files_to_modify`.

**Acceptance (deterministic gate):** `scripts/tests/test_wiring_skills_and_commands.py` gains `DOC_STRINGS_PRESENT` rows for `sites_to_add` in `skills/wire-issue/SKILL.md`, `docs/reference/COMMANDS.md`, **and `skills/wire-issue/output-report.md`** (so the Wiring Phase's `output-report.md` table-row requirement is itself gated, not just documented), plus a `known_sites` present row and a `DOC_STRINGS_ABSENT` row for the old sentence `Exclude files already in the "already known" lists.`; the full suite passes; `ll-verify-skills` keeps `SKILL.md` at or under 500 lines. **Manual smoke check (not a gate):** running `/ll:wire-issue` twice back-to-back on a freshly refined issue, with no refine run or code change in between, yields "No missing wiring found" for intra-file sites on the second pass.


## Current Behavior

`/ll:wire-issue`'s Phase 4 agent prompts and Phase 5 `MISSING_WIRING`
categorization exclude any file already listed in `files_to_modify`/`known_*`
(`skills/wire-issue/SKILL.md:180,212,270-278`), so call sites inside those
files are never reported on a first pass. Running the skill a second time on
the same issue surfaces those same intra-file sites as "new" findings,
because the interim widened `key_symbols` set (seeded partly by the first
pass's own appended blocks, `SKILL.md:108-132`) produces grep hits landing in
already-known files.

## Expected Behavior

A single `/ll:wire-issue` pass finds intra-file call sites for symbols named
in `files_to_modify`, not just cross-file references. Running the skill twice
on the same freshly refined issue yields "No missing wiring found" on the
second pass for intra-file sites — a second pass should not be needed to
reach the completeness the first pass should have produced.

## Motivation

This enhancement would:
- Eliminate the doubled agent time/cost per issue: BUG-3477 and BUG-3478 each
  needed a full second `/ll:wire-issue` session (pass 1 `bac75f45`, pass 2
  `6d7823a0`) purely to catch intra-file sites the first pass structurally
  cannot report.
- Business value: makes a single `/ll:wire-issue` run authoritative for
  Integration Map completeness, removing the current implicit "run it twice"
  workflow step nothing documents.
- Technical debt: closes a self-expanding blind spot in
  `skills/wire-issue/SKILL.md` where exclusion wording and `MISSING_WIRING`
  categories both key on whole files instead of `path:symbol` sites.

## Proposed Solution

Skill prompt text and its companion files only — no Python beyond the test
table rows:

- (0) **`known_sites` extraction** (Phase 3, `SKILL.md:117-123`): add
  `known_sites: [path:symbol]` to `EXISTING_WIRING`, parsed from existing
  Integration Map bullets (`` `path` — ... `symbol()` ``). Bullets with no
  symbol contribute the bare path only. This is the dedup key for
  `sites_to_add`; the exclusion wording in (a) references it by name.
- (a) **Phase 4 wording**: reword Agent 1 (`SKILL.md:180`) and Agent 2
  (`SKILL.md:212`) from "exclude known files" to "exclude `path:symbol`
  sites already in `known_sites`; report additional call sites, tests, or
  doc locations inside known files as new, citing `path:line` and the
  enclosing symbol." Add the same instruction to Agent 3
  (`SKILL.md:223-253`), which has no exclusion wording today.
- (b) **`sites_to_add` category** (Phase 5, `SKILL.md:269-281`): entries are
  `path:line` + enclosing symbol + which known file, filtered against
  `known_sites`. Render in **Phase 8a** (`SKILL.md:342-398`) with the
  `_Wiring pass added by \`/ll:wire-issue\`:_` marker, routed by the kind of
  known file the site lives in:
  - site in a `files_to_modify` file → `### Files to Modify` (add the marker
    to this subsection's append block, which also fixes the missing marker
    on the existing `registrations_to_add` append at `SKILL.md:356-361`)
  - site in a `known_tests` file (a specific test function) → `### Tests`
  - site in a `known_docs` file (a specific section) → `### Documentation`
  `sites_to_add` entries also feed Phase 8b `### Wiring Phase` bullets, and
  the caller-suitability gate (ENH-3258, `caller-suitability-gate.md`)
  applies to them exactly as it does to `callers_to_add`.
- (c) **Bounded one-hop `key_symbols` expansion** (Phase 3, before Phase 4,
  `SKILL.md:108-132`) — required, not optional, since cause 1 explains most
  pass-2 findings: for each seed symbol, grep its callers inside
  `files_to_modify` only and add the enclosing function names to the seed
  set. Exactly one hop; the expanded names are not themselves expanded; no
  files outside `files_to_modify` are searched. Without this bound the seed
  set grows without limit across passes.
- **Line budget**: `SKILL.md` is at the 500-line cap. Put the `known_sites`
  extraction rules, the one-hop expansion procedure, and the `sites_to_add`
  render templates in a new companion `skills/wire-issue/intra-file-sites.md`,
  and leave one-line pointers in Phases 3, 5, and 8a, following the
  `behavior-parity.md` pattern.
- **Drive-by, same pass**: add the missing `gate_consumers` and
  `conditional_branches` rows to the `output-report.md` "MISSING WIRING
  FOUND" table alongside the new `sites_to_add` row (two lines in a file
  already being edited). `cli_coupling`'s missing Phase 8a render stays out
  of scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Correction to (a): only Agent 1 (`SKILL.md:180`) and Agent 2 (`SKILL.md:212`) carry whole-file exclusion wording to change. Agent 3 (Test Gap Finder, `SKILL.md:223-253`) has no exclusion instruction today — it needs a new instruction to report intra-file test/doc sites, not a rewording of an existing one.
- Correction to (b): the render target is Phase 8a (`### Integration Map Updates`, `SKILL.md:342-398`), not Phase 7. Phase 7 (`SKILL.md:302-332`) only displays a summary/confirmation prompt and performs no file edits; it explicitly skips straight to Phase 8 in Auto Mode.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 3 `key_symbols` seeding
  (lines 108-132), Phase 4 exclusion wording (Agent 1/2: lines 180, 212;
  Agent 3: new instruction, lines 223-253), Phase 5 `MISSING_WIRING` block
  (lines 269-281), Phase 8a rendering (lines 342-398). The file is
  currently exactly 500 lines — at the `ll-verify-skills` cap — so any
  net-additive change here needs an equal-or-greater removal elsewhere or
  extraction to a companion file, following the existing pattern
  (`behavior-parity.md`, `static-coupling-layer.md`,
  `graph-discovery-layer.md`, `prose-dependency-gate.md`,
  `evidence-confirmation.md`, `caller-suitability-gate.md`,
  `learning-targets.md`, `output-report.md`).
- `skills/wire-issue/intra-file-sites.md` — **new** companion file holding
  the `known_sites` extraction rules, the bounded one-hop `key_symbols`
  expansion, and the `sites_to_add` Phase 8a render templates; `SKILL.md`
  keeps one-line pointers to it in Phases 3, 5, and 8a.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/output-report.md` — the Phase 10 "MISSING WIRING FOUND"
  table has one row per `MISSING_WIRING` category (Callers/Importers,
  Registrations/Manifests, Documentation, Tests (update), Tests (new),
  Config/Schema, Impl Step gaps); add a `sites_to_add` row or the new
  category is silently dropped from the end-of-run report even though it's
  rendered into the issue file by Phase 8a. Also add the missing
  `gate_consumers` / `conditional_branches` rows (ENH-3050) in the same
  edit — decided in scope, two table lines.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`,
  `scripts/little_loops/loops/rn-remediate.yaml` — FSM loops that invoke
  `/ll:wire-issue` as a phase; no code change needed, but their expectations
  of a single-pass-complete Integration Map become valid once this lands
- No Python module imports `SKILL.md` directly (skill prompt text only)

### Similar Patterns
- N/A — the known-file exclusion pattern is specific to `wire-issue`'s
  Phase 4/5 prompts; no sibling skill uses the same file-granular exclusion

### Tests
- `scripts/tests/test_wire_issue_static_layer.py` — tests only
  `little_loops.decisions.load_coupling_entries()` (Phase 3.5 static
  coupling layer); unaffected by this change, no edits needed.
- `scripts/tests/test_wiring_skills_and_commands.py` — has parametrized
  `DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT` tables (ENH-3050) but does not
  pin the exact Phase 4 exclusion sentences, the full `MISSING_WIRING`
  category list, or the `_Wiring pass added by...` marker string. Extend
  these tables with entries for the reworded Phase 4 instructions and the
  new `sites_to_add` category; this is additive, not a conflicting-assertion
  change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py:249-251` — the
  ENH-3050 precedent for a new `MISSING_WIRING` category is a pair of
  `DOC_STRINGS_PRESENT` tuples right after the existing
  `gate_consumers`/`conditional_branches` rows: one asserting
  `"sites_to_add"` appears in `skills/wire-issue/SKILL.md`, one asserting it
  appears in `docs/reference/COMMANDS.md` (once the Documentation-section
  bullet above is added). Follow this exact two-tuple shape, plus **a third
  tuple** asserting `"sites_to_add"` appears in
  `skills/wire-issue/output-report.md` (once its Phase 10 table row is
  added) — this closes the gap where the Wiring Phase's `output-report.md`
  requirement was otherwise undocumented by any test row. Also add a
  `("skills/wire-issue/SKILL.md", "known_sites", "ENH-3480")` present row and
  a `DOC_STRINGS_ABSENT` row for the old sentence `Exclude files already in
  the "already known" lists.` so a regression that restores whole-file
  exclusion fails the suite. These rows are the deterministic acceptance
  gate for this issue.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:281-289` — the `/ll:wire-issue` entry's "Wiring
  categories searched" bulleted list documents each `MISSING_WIRING` category
  one bullet at a time (Behavior Parity added at line 287 for ENH-3045;
  `gate_consumers`/`conditional_branches` added at lines 288-289 for
  ENH-3050). Adding `sites_to_add` needs a matching new bullet here following
  the same precedent — currently the only doc surface that enumerates
  wire-issue's categories by name, and it has no entry for this one.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- `skills/wire-issue/SKILL.md` is currently exactly 500 lines (confirmed to EOF) — already at the `ll-verify-skills` cap. Any net-additive change (new `sites_to_add` category, its rendering, wording edits) needs either an equal-or-greater removal elsewhere or extraction to a companion file; the file already uses this pattern for `behavior-parity.md`, `static-coupling-layer.md`, `graph-discovery-layer.md`, `prose-dependency-gate.md`, `evidence-confirmation.md`, `caller-suitability-gate.md`, `learning-targets.md`, `output-report.md`.
- Phase 4's exclusion wording is not uniform across the three agent prompts: Agent 1 (`SKILL.md:180`, Caller and Importer Tracer) and Agent 2 (`SKILL.md:212`, Side-Effect Surface Tracer) each carry an explicit "Exclude files already..." instruction; Agent 3 (Test Gap Finder, prompt lines 223-253) has no exclusion instruction at all — it only supplies `known_tests` as context. Only two prompts need rewording; Agent 3's prompt needs a new instruction to report intra-file test/doc sites, since it has no exclusion wording to remove.
- The `MISSING_WIRING` block (`SKILL.md:269-281`) has 11 categories, not 9 — the range `270-278` cited elsewhere in this issue covers `callers_to_add` through `gate_consumers` but omits `conditional_branches` (279) and `new_impl_steps` (280), both also file-granular and candidates for a matching site-level variant if the granularity change is meant to be complete.
- `cli_coupling` (`SKILL.md:276`) is defined in Phase 5 but has no rendering destination anywhere in Phase 8a — it is never referenced again after its definition. Pre-existing gap, unrelated to intra-file-site detection; a new `sites_to_add` category should not repeat this omission.
- Rendering of `MISSING_WIRING` findings into the issue file happens in **Phase 8a** (`SKILL.md:342-398`, `### Integration Map Updates`), not Phase 7. Phase 7 (`SKILL.md:302-332`) is display/confirmation-only and performs no `Edit` calls — it explicitly skips to Phase 8 in Auto Mode (`SKILL.md:304`).
- The `_Wiring pass added by \`/ll:wire-issue\`:_` marker is not applied uniformly in Phase 8a: it appears for `### Dependent Files (Callers/Importers)`, `### Documentation`, `### Tests`, and `### Configuration` appends, but the `### Files to Modify` append for `registrations_to_add` (`SKILL.md:356-361`) shows no marker, and Phase 8b's `### Wiring Phase` block (`SKILL.md:400-416`) uses different marker text ("_These touchpoints were identified by wiring analysis and must be included in the implementation:_", line 410).
- `scripts/tests/test_wire_issue_static_layer.py` tests only `little_loops.decisions.load_coupling_entries()` (the Phase 3.5 static coupling layer) — no assertions about Phase 4 exclusion wording or Phase 5 `MISSING_WIRING` categories, so it is unaffected by this change.
- `scripts/tests/test_wiring_skills_and_commands.py` has parametrized `DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT` tables asserting `gate_consumers` and `conditional_branches` are present in `SKILL.md` (ENH-3050) but does not pin the exact Phase 4 exclusion sentences, the full `MISSING_WIRING` category list, or the `_Wiring pass added by...` marker string — implementing this issue means extending these tables, not modifying conflicting existing assertions.

## Implementation Steps

1. Create `skills/wire-issue/intra-file-sites.md` with three sections:
   `known_sites` extraction rules, the bounded one-hop `key_symbols`
   expansion procedure, and the `sites_to_add` render templates for
   `### Files to Modify` / `### Tests` / `### Documentation`.
2. Phase 3 (`SKILL.md:108-132`): add `known_sites: [path:symbol]` to the
   `EXISTING_WIRING` block and a one-line pointer to the companion for both
   the extraction rules and the one-hop expansion (run before Phase 4;
   one hop, `files_to_modify` only, no recursion).
3. Reword the Phase 4 exclusion instructions in Agent 1 (`SKILL.md:180`,
   Caller and Importer Tracer) and Agent 2 (`SKILL.md:212`, Side-Effect
   Surface Tracer) to exclude `path:symbol` sites in `known_sites` instead
   of whole known files, and to cite `path:line` + enclosing symbol for
   intra-file finds. Add the same instruction to Agent 3 (Test Gap Finder,
   prompt lines 223-253), which carries no exclusion wording today.
4. Add the `sites_to_add` `MISSING_WIRING` category to the Phase 5 block
   (`SKILL.md:269-281`), filtered against `known_sites`; render it in
   **Phase 8a** (`SKILL.md:342-398`) per the routing in Proposed Solution,
   adding the `_Wiring pass added by \`/ll:wire-issue\`:_` marker to the
   `### Files to Modify` append block; note in Phase 8b that `sites_to_add`
   feeds Wiring Phase bullets under the caller-suitability gate.
5. Reclaim lines so `SKILL.md` stays at or under 500: move the Phase 8a
   example blocks the companion now owns out of `SKILL.md`.
6. Verify (deterministic gate): add the test rows described under Tests;
   run `python -m pytest scripts/tests/test_wiring_skills_and_commands.py
   scripts/tests/test_wire_issue_static_layer.py scripts/tests/test_caller_suitability_gate.py`
   then the full suite; run `ll-verify-skills`.
7. Manual smoke check (not a gate): run `/ll:wire-issue` twice back-to-back
   on a freshly refined issue with no refine or code change in between and
   confirm the second pass reports "No missing wiring found" for intra-file
   sites.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/COMMANDS.md:281-289` — add a `sites_to_add` bullet to the `/ll:wire-issue` entry's "Wiring categories searched" list, matching the Behavior Parity (line 287) / `gate_consumers` (line 288) precedent
- Update `skills/wire-issue/output-report.md` — add a `sites_to_add` row to the Phase 10 "MISSING WIRING FOUND" table so the category isn't silently dropped from the end-of-run report
- Update `scripts/tests/test_wiring_skills_and_commands.py` — add the three `DOC_STRINGS_PRESENT` tuples (`SKILL.md`, `docs/reference/COMMANDS.md`, and `skills/wire-issue/output-report.md`, each asserting `"sites_to_add"`), a `known_sites` present row, and a `DOC_STRINGS_ABSENT` row for the old whole-file exclusion sentence, alongside the existing ENH-3050 rows at lines 249-251

## Impact

- **Priority**: P3 - Wastes agent time/cost on affected issues (a full
  redundant session per occurrence) but has a workaround (run wire-issue
  twice); not blocking.
- **Effort**: Small - Prompt-wording and category changes in
  `skills/wire-issue/SKILL.md` plus one new companion file, doc bullet, and
  test-table rows; no Python logic, no new abstractions.
- **Risk**: Low - Text-only change to agent prompts and a report category;
  existing wire-issue tests provide a regression safety net.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-15 | Priority: P3

## Success Metrics

- Intra-file sites found on second pass: currently ~100% of BUG-3477/3478
  pass-2 findings → target 0 (first pass reaches parity)
- Redundant `/ll:wire-issue` sessions per issue: currently 2 typical → target 1

## Scope Boundaries

- **In scope**: Phase 3 `known_sites` extraction and bounded one-hop
  `key_symbols` expansion (required), Phase 4 exclusion wording for all
  three agents, Phase 5 `MISSING_WIRING` `sites_to_add` category and Phase
  8a/8b rendering (Phase 7 is display/confirmation-only and performs no
  file edits), the new `intra-file-sites.md` companion, the
  `output-report.md` table rows (including the ENH-3050 `gate_consumers` /
  `conditional_branches` drive-by), the `COMMANDS.md` bullet, and the
  test-table rows.
- **Out of scope**: Any Python code change beyond test-table rows; the
  missing Phase 8a render for `cli_coupling`; changes to other skills'
  known-file exclusion patterns; changes to the FSM loops that invoke
  wire-issue; expansion beyond one hop or outside `files_to_modify`.

## API/Interface

N/A - No public API changes (prompt-text and report-category change within
a single skill file, not a code interface)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- ~~Summary overstatement~~ — fixed post-check: Summary now reads "most" and explicitly names the four new-file discoveries as a separate phenomenon from the intra-file-miss fix this issue targets.
- ~~AC-coverage gap~~ — fixed post-check: the Acceptance paragraph and Tests wiring section now specify a third `DOC_STRINGS_PRESENT` tuple asserting `"sites_to_add"` in `skills/wire-issue/output-report.md`, closing the gap where that Wiring Phase item had no deterministic gate.
- Criterion 4 capped at 10 (advisory, not a blocker): `known_sites` and `sites_to_add` are claimed in `scripts/tests/test_wiring_skills_and_commands.py` but don't yet resolve there — expected for forward-looking test-row claims the issue proposes adding, not itself a defect. Re-run `/ll:confidence-check ENH-3480` after implementation to clear this cap.

## Session Log
- `/ll:confidence-check` - 2026-09-15T20:09:12 - `a50e53ee-eaa5-4308-b45d-3ce023bd2a61.jsonl`
- `/ll:verify-issues` - 2026-09-15T20:02:59 - `889d831f-7992-4797-b0a1-b744fe43c6bc.jsonl`
- `/ll:wire-issue` - 2026-09-15T19:43:51 - `ea70bb0b-2e90-4a29-af8a-b28bd4b966d9.jsonl`
- `/ll:reconcile-issue` - 2026-09-15T19:39:29 - `5090e718-cdfc-48c3-9991-3d61d838280d.jsonl`
- `/ll:refine-issue` - 2026-09-15T19:37:17 - `cdbb07d4-56af-4822-8c99-6c7b4578265d.jsonl`
- `/ll:format-issue` - 2026-09-15T19:32:03 - `f46aa9fa-d555-454b-872b-89355e6b8675.jsonl`
- `/ll:capture-issue` - 2026-09-15T19:28:41 - `a935744c-43bf-4d30-9969-892325ab65a6.jsonl`

## Verification Notes

Verdict: **NEEDS_UPDATE**

- **Structural diagnosis and all `SKILL.md` line citations verified accurate.**
  Confirmed against the file at HEAD (500 lines exactly, matching the
  "at the cap" claim): line 180's exact sentence
  ("Exclude files already in the "already known" lists."), line 212's
  ("Exclude files already known from the issue."), Agent 3's prompt
  (223-253) genuinely carries no exclusion instruction, the 11-category
  `MISSING_WIRING` block (269-281, confirming `conditional_branches`/
  `new_impl_steps` are the two the 270-278 range omits), `cli_coupling`
  (276) has no Phase 8a rendering, and the `registrations_to_add` append
  (356-361) lacks the `_Wiring pass added by...` marker that the other
  three Phase 8a appends carry. `docs/reference/COMMANDS.md:281-289` and
  the `test_wiring_skills_and_commands.py:249-251` ENH-3050 precedent for
  the proposed test-row shape both check out as described.

- **Summary's central evidence claim is overstated — the issue's own cited
  evidence contradicts it.** The Summary states "Every BUG-3477 pass-2
  finding was an intra-file site in one of four already-listed files
  (`harness.py`, `test_cli_harness.py`, `docs/reference/API.md`,
  `docs/reference/CLI.md`)." Reading BUG-3477's own `/ll:wire-issue`
  "(second pass)" blocks directly: the Tests second pass also names
  `scripts/tests/test_fsm_evaluators.py:1435` (a file never in the four-file
  list, and not previously known to the issue at all), and the
  Documentation second pass names `docs/generalized-fsm-loop.md:623-651`,
  `scripts/little_loops/loops/lib/common.yaml:23-37`, and
  `docs/guides/HISTORY_SESSION_GUIDE.md:91` — three more files outside the
  four-file list and outside `known_docs` before pass 2. These are new-file
  discoveries from the widened pass-2 `key_symbols` search net, not
  intra-file misses inside already-known files — a different phenomenon
  than the one the whole-file-exclusion mechanism (cause 2) explains. This
  doesn't undermine causes 1/2 or the proposed fix (which only targets
  intra-file misses and doesn't claim to fix cross-file discovery order),
  but the "every finding" framing should be softened to "most findings" or
  scoped explicitly to the intra-file subset, since as written it is
  falsified by the issue's own evidence.

- **Possible AC-coverage gap (check B.6):** the Integration Map's Wiring
  Phase lists `skills/wire-issue/output-report.md` as needing a new
  `sites_to_add` row (plus the drive-by `gate_consumers`/
  `conditional_branches` rows) in its Phase 10 "MISSING WIRING FOUND"
  table, but neither the Proposed Solution's deterministic Acceptance
  paragraph nor the enumerated `DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT`
  test rows mention asserting on `output-report.md`'s content — and
  `test_wiring_skills_and_commands.py` currently has zero assertions
  referencing `output-report.md` at all (confirmed by grep). Without an
  explicit test row, this Wiring Phase item has no deterministic gate and
  could land un-updated with no test catching it. Consider adding a
  `DOC_STRINGS_PRESENT` tuple for `("skills/wire-issue/output-report.md",
  "sites_to_add", "ENH-3480")` alongside the other two, or note explicitly
  why it's out of scope for the deterministic gate.

**Remaining:** the two items above (Summary overstatement, AC-coverage gap)
are not corrected in this pass — verification only, no content rewrite.
