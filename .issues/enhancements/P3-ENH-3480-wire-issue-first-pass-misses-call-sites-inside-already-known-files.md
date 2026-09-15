---
id: ENH-3480
type: ENH
title: wire-issue first pass misses call sites inside already-known files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T19:28:33Z'
testable: false
program_design_not_applicable: true
---

# ENH-3480: wire-issue first pass misses call sites inside already-known files

## Summary

`/ll:wire-issue`'s first pass systematically misses call sites that live inside files the issue already names; a second pass on the same issue then "discovers" them. Observed on BUG-3477 and BUG-3478: pass 1 (2026-09-14, session `bac75f45`) vs pass 2 (2026-09-15, session `6d7823a0`). Every BUG-3477 pass-2 finding was an intra-file site in one of four already-listed files (`scripts/little_loops/cli/harness.py`, `scripts/tests/test_cli_harness.py`, `docs/reference/API.md`, `docs/reference/CLI.md`).

Two structural causes in `skills/wire-issue/SKILL.md`:

1. **Key symbols are seeded only from backticked names in the issue text** (Phase 3, `SKILL.md:108-132`). Before pass 1 the BUG-3477 issue named 8 harness symbols. Pass 1's own appended blocks introduced `_report_samples()`, `_run_compare_arm()`, `_run_baseline_phase()`, `BaselineDelta`, `cmd_skill()`; a `/ll:refine-issue` run between passes added more. Pass 2 therefore searched roughly twice the symbol set, and nearly every "new" call site is a caller of a symbol that only entered the issue during pass 1. The skill is self-expanding by one hop per pass.

2. **Agent prompts exclude whole files, and the Phase 5 diff is file-granular.** All three Phase 4 prompts say "Exclude files already in the already-known lists" / "Exclude files already known from the issue" (`SKILL.md:180,212`), and `MISSING_WIRING` categories are all "files ... not in known_*" (`SKILL.md:270-278`). There is no category for additional sites inside a known file, so agents have a standing instruction to skip exactly the files where most remaining call sites live. Pass 2 only surfaced them because the widened symbol set produced grep hits that landed in those files anyway.

Minor contributing factor: `harness.py` grew several hundred lines between passes and the 09-15 refine pass rewrote line citations, so pass-2 agents re-read the file fresh instead of trusting stale anchors.

**Proposed fix (in the skill only, no Python):**

- (a) Change the Phase 4 exclusion wording in all three agent prompts from "exclude known files" to "exclude already-cited `path:symbol` sites; report additional call sites, tests, or doc locations inside known files as new."
- (b) Add a `sites_to_add` category to Phase 5 `MISSING_WIRING` (`path:line` + symbol within a known file) and render it in Phase 7 under the matching Integration Map subsection, with the same `_Wiring pass added by \`/ll:wire-issue\`:_` marker.
- (c) Optionally expand `key_symbols` one hop before Phase 4: for each symbol in `files_to_modify`, grep its callers inside those same files and add the enclosing function names to the seed set, so pass 1 reaches what pass 2 currently does.

**Acceptance:** running `/ll:wire-issue` twice on a freshly refined issue yields an empty second pass ("No missing wiring found") for intra-file call sites; the existing wire-issue skill tests (`scripts/tests/test_wire_issue*.py` or equivalent) still pass, and `ll-verify-skills` stays under the 500-line SKILL.md cap (move new prose to a companion file if needed).


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

In `skills/wire-issue/SKILL.md` only — no Python:

- (a) Change the Phase 4 exclusion wording in all three agent prompts
  (`SKILL.md:180,212`) from "exclude known files" to "exclude already-cited
  `path:symbol` sites; report additional call sites, tests, or doc locations
  inside known files as new."
- (b) Add a `sites_to_add` category to Phase 5 `MISSING_WIRING`
  (`SKILL.md:270-278`) — `path:line` + symbol within a known file — and
  render it in Phase 7 under the matching Integration Map subsection, with
  the same `_Wiring pass added by \`/ll:wire-issue\`:_` marker.
- (c) Optionally expand `key_symbols` one hop before Phase 4
  (`SKILL.md:108-132`): for each symbol in `files_to_modify`, grep its
  callers inside those same files and add the enclosing function names to
  the seed set, so pass 1 reaches what pass 2 currently does.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 3 `key_symbols` seeding
  (lines 108-132), Phase 4 exclusion wording (lines 180, 212), Phase 5
  `MISSING_WIRING` categories (lines 270-278)

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
- `scripts/tests/test_wire_issue_static_layer.py`,
  `scripts/tests/test_wiring_skills_and_commands.py` — existing coverage
  that must keep passing; extend with a case asserting a second pass on a
  fixture issue yields no `sites_to_add` findings

### Documentation
- N/A — `SKILL.md` prompt text is the only user-facing surface; no `docs/`
  page describes wire-issue's exclusion behavior at this level of detail

### Configuration
- N/A

## Implementation Steps

1. Update Phase 4 exclusion wording in all three agent prompts
   (`SKILL.md:180,212`) to exclude cited `path:symbol` sites instead of
   whole known files.
2. Add the `sites_to_add` `MISSING_WIRING` category and its Phase 7
   Integration Map rendering (`SKILL.md:270-278`).
3. Optionally add the one-hop `key_symbols` caller expansion in Phase 3
   (`SKILL.md:108-132`).
4. Verify: run `/ll:wire-issue` twice on a freshly refined issue and confirm
   the second pass reports "No missing wiring found" for intra-file sites;
   run `scripts/tests/test_wire_issue_static_layer.py` and
   `scripts/tests/test_wiring_skills_and_commands.py`; confirm
   `ll-verify-skills` keeps `SKILL.md` under the 500-line cap.

## Impact

- **Priority**: P3 - Wastes agent time/cost on affected issues (a full
  redundant session per occurrence) but has a workaround (run wire-issue
  twice); not blocking.
- **Effort**: Small - Prompt-wording and category changes confined to
  `skills/wire-issue/SKILL.md`; no Python, no new abstractions.
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

- **In scope**: Phase 4 exclusion wording, Phase 5 `MISSING_WIRING`
  `sites_to_add` category and Phase 7 rendering, optional Phase 3
  `key_symbols` one-hop expansion — all confined to
  `skills/wire-issue/SKILL.md`.
- **Out of scope**: Any Python code change (the issue's own proposed fix is
  explicitly skill-prompt-only); changes to other skills' known-file
  exclusion patterns; changes to the FSM loops that invoke wire-issue.

## API/Interface

N/A - No public API changes (prompt-text and report-category change within
a single skill file, not a code interface)


## Session Log
- `/ll:format-issue` - 2026-09-15T19:32:03 - `f46aa9fa-d555-454b-872b-89355e6b8675.jsonl`
- `/ll:capture-issue` - 2026-09-15T19:28:41 - `a935744c-43bf-4d30-9969-892325ab65a6.jsonl`
