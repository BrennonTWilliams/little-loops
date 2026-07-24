---
id: BUG-2759
type: bug
priority: P2
status: done
captured_at: '2026-07-24T19:36:28Z'
completed_at: '2026-07-24T20:09:45Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2759: ll-doctor always exits 1 on claude-code (contradictory json_schema entry)

## Summary

`ll-doctor` exits `1` on the primary host (`claude-code`) even when the host is
fully healthy. `ClaudeCodeRunner.describe_capabilities()` emits two capability
entries describing the *same* `--json-schema` flag with opposite verdicts:
`json_schema` is hardcoded `"unsupported"` while `structured_output` is
`"full"`. ENH-2627 added the second entry (and flipped
`HostCapabilities.structured_output=True`) but left the older, now-false
`json_schema` entry in place. Since `main_doctor` exits non-zero if *any*
capability is `"unsupported"`, the stale entry permanently poisons the exit
code.

## Steps to Reproduce

1. On a machine with the `claude` CLI installed, run `ll-doctor` from the repo root.
2. Observe the capability table shows both:
   - `✗  json_schema  claude CLI does not accept an inline schema flag; parameter is silently dropped`
   - `✓  structured_output  claude CLI honors an inline --json-schema flag; ...`
3. Run `ll-doctor >/dev/null 2>&1; echo $?` — prints `1`.

## Current Behavior

- Two mutually contradictory entries for one flag.
- Exit code `1` on a fully-supported host, so the documented health contract is
  broken. `docs/codex/usage.md:96` and `docs/reference/HOST_COMPATIBILITY.md:312`
  both treat "exits non-zero if any capability is unsupported" as the CI signal,
  which makes `ll-doctor` unusable as a preflight gate for claude-code.

## Expected Behavior

- One entry per real capability, agreeing with `HostCapabilities`.
- `ll-doctor` exits `0` on a healthy `claude-code` host.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: `in ClaudeCodeRunner.describe_capabilities()`
- **Cause**: The `CapabilityEntry("json_schema", "unsupported", ...)` predates
  ENH-2627's `CapabilityEntry("structured_output", "full", ...)`. Both describe
  the inline `--json-schema` flag; only the newer one is accurate. Exit-code
  logic in `scripts/little_loops/cli/doctor.py` (`main_doctor`, final return)
  treats any `"unsupported"` as failure.

## Motivation

`ll-doctor` is the documented preflight/CI gate for host capability support and
is referenced from `docs/guides/LOOPS_GUIDE.md` as the check to run before
relying on `suppress_catalog` / `suppress_claude_md`. A gate that always fails
on the default host trains users and automation to ignore it, which defeats the
purpose of the whole capability-reporting layer.

## Proposed Solution

Preferred: delete the stale `json_schema` entry so `structured_output` is the
single source of truth for the flag.

Alternative if the `json_schema` name is load-bearing for a consumer (check
`ll-action capabilities` and `docs/reference/HOST_COMPATIBILITY.md` before
choosing): keep the name but correct its status to `"full"` and merge the notes,
retiring the redundant `structured_output` entry instead.

Either way, decide deliberately whether the two names are one capability or two —
the current state asserts both.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

This decision was already made once, in ENH-2627 (status `done`), which
selected "Option A: keep both entries, correct the stale `json_schema`
note/status so the two surfaces agree." Only the "add `structured_output`"
half of that decision shipped — the "correct `json_schema`" half was never
applied. No consumer keys off the literal name `json_schema` (see Integration
Map), so implementing the second half of the already-selected option (correct
`json_schema`'s status/note on `ClaudeCodeRunner` to agree with
`structured_output`, rather than deleting it) is lower-risk than reopening the
delete-vs-keep decision, and stays consistent with ENH-2627's stated intent
that the two names serve genuinely different diagnostic purposes
(`json_schema` also covers the separately-dropped `build_blocking_json()`
parameter, unrelated to the FSM evaluators' inline-flag path).

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.describe_capabilities()`,
  lines 366-403. The stale entry is exactly:
  `CapabilityEntry("json_schema", "unsupported", "claude CLI does not accept an
  inline schema flag; parameter is silently dropped")` (lines 377-381), sitting
  directly beside `CapabilityEntry("structured_output", "full", ...)` (lines
  385-390, added by ENH-2627).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py` — `main_doctor()` line 150:
  `return 0 if not any(c.status == "unsupported" for c in report.capabilities) else 1`.
  This is a flat, name-blind scan — any single `"unsupported"` entry anywhere in
  the list flips the whole exit code, which is exactly why the stale entry alone
  poisons it. `_print_report()` (lines 59-98) renders entries generically by
  `status`/`note`, never by `name` — no code change needed there.
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()` (line 339), a
  second render surface (`ll-action capabilities`) that serializes
  `describe_capabilities()` output the same generic way; auto-fixed once the
  runner method is corrected, no code change needed.
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured`,
  `evaluate_blind_comparator`, `evaluate_contract` gate their `--json-schema`
  append on `invocation.capabilities.structured_output` (the boolean flag, not
  the string `CapabilityEntry`), so they are unaffected by this fix either way.

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/bugs/P3-BUG-2760-capability-report-hooks-never-populated.md` — sibling
  bug in the same `EPIC-2765` epic, also touching `describe_capabilities()` /
  `_print_report()`; coordinate if implemented in parallel to avoid merge
  conflicts on the same functions.

### Similar Patterns
- Checked all other runners' `describe_capabilities()` for the same
  contradiction — none have it:
  - `CodexRunner` (lines 642-698): `json_schema="partial"`,
    `structured_output="unsupported"` — consistent (temp-file `--output-schema`
    bridge partially works; inline flag doesn't).
  - `GeminiRunner` (lines 1006-1048) / `OmpRunner` (lines 1173-1220): both
    `json_schema="unsupported"` and `structured_output="unsupported"` — consistent.
  - `OpenCodeRunner` (759-771) / `PiRunner` (832-844): only emit a single
    `"host"` stub entry (both raise `HostNotConfigured`); no pair to compare.
  - **`ClaudeCodeRunner` is the only runner where the two entries disagree.**

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Root cause is a known-but-unresolved decision, not an oversight.**
  ENH-2627 (`.issues/enhancements/P3-ENH-2627-structured-output-capability-gate-json-schema.md`,
  status `done`) explicitly surfaced this exact contradiction during its own
  refinement pass and selected **"Option A"**: keep the string-keyed
  `json_schema` `CapabilityEntry` as a diagnostic surface, add the separate
  `structured_output` boolean for call-site gating, and *"correct the stale
  claude `json_schema` note (or leave it) so the two surfaces agree."* The
  `structured_output` flag/entry was added, but the `json_schema` note/status
  correction was never applied — that's precisely the gap this bug reports.
  This means the preferred fix is the corrective half of Option A: fix the
  `json_schema` entry's status/note on `ClaudeCodeRunner` to agree with
  `structured_output`, not necessarily delete it (deleting would partially
  undo ENH-2627's deliberate "keep both, for different purposes" design —
  `json_schema` also intentionally documents that
  `ClaudeCodeRunner.build_blocking_json()`'s `json_schema` *parameter* is
  separately dropped, lines 314-343, `_ = json_schema`).
- **No production consumer keys off the literal name `"json_schema"`** —
  confirmed by grep across `scripts/little_loops/`. `main_doctor` and
  `_print_report` iterate generically by `status`. The only places that
  reference the name are tests (`test_cli_doctor.py:203`, hand-built fixture;
  `test_host_runner.py:1067,1095,1107`, asserting Codex/Gemini/Omp values —
  none assert `ClaudeCodeRunner`'s `json_schema` value specifically). Renaming,
  correcting, or removing the `ClaudeCodeRunner` entry is safe from a
  consumer-coupling standpoint.
- **Existing test gap**: `test_host_runner.py`'s
  `test_claude_code_runner_all_core_capabilities_full` (~line 1026) asserts
  `structured_output == "full"` but never asserts anything about
  `json_schema` for `ClaudeCodeRunner` — this is why the contradiction shipped
  without a failing test.

### Tests
- `scripts/tests/test_cli_doctor.py` — exit-code test pattern
  (`test_exit_zero_when_all_capabilities_supported`,
  `test_exit_one_when_critical_capability_missing`, lines 38-84) uses
  hand-built `CapabilityReport` fixtures, so it won't catch this bug as-is; add
  a new test using the *real* `ClaudeCodeRunner` (not a mock) to exercise the
  actual regression.
- `scripts/tests/test_host_runner.py` — `TestDescribeCapabilities` class
  (~line 1014); extend with an assertion that no two entries in
  `ClaudeCodeRunner().describe_capabilities()` disagree on the same underlying
  flag, e.g. `assert not any(c.status == "unsupported" for c in report.capabilities)`.
- `scripts/tests/test_action.py` — `cmd_capabilities()` tests (lines 359-418)
  render the same report; confirm they don't hardcode an expectation of the
  stale `json_schema` status.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py` — asserts `structured_output`/
  `json_schema` gating behavior in `evaluate_llm_structured`/
  `evaluate_blind_comparator`/`evaluate_contract`; confirm it keys off the
  `HostCapabilities.structured_output` boolean (unaffected) and not the
  `CapabilityEntry` string this fix corrects.
- New test to add (no existing test asserts this):
  `test_host_runner.py::TestDescribeCapabilities::test_claude_code_json_schema_matches_structured_output`
  — `by_name["json_schema"].status == by_name["structured_output"].status` on
  a real (non-mocked) `ClaudeCodeRunner().describe_capabilities()` call.
- New test to add: `test_cli_doctor.py` — a sibling to
  `test_exit_zero_when_all_capabilities_supported` built on the *real*
  `ClaudeCodeRunner().describe_capabilities()` report (wrapped through the
  file's `_make_runner` helper) rather than a hand-built `CapabilityReport`,
  since a synthetic report can never reproduce this exact cross-field
  regression.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — capability matrix rows at lines
  128-136 show `json_schema` (✗) vs `structured_output` (✓) for Claude Code;
  update alongside the code fix. Exit-code contract referenced at line 312.
- `docs/codex/usage.md:96,115-128` — exit-code note and a `### json_schema`
  section explaining schema-support differences across hosts; may need a
  one-line update once Claude Code's entry is corrected.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `HostCapabilities.structured_output` field
  description and `CapabilityEntry`/`describe_capabilities()` docs; also the
  `GeminiRunner` row in the **Concrete runners** table cross-references
  Claude Code's json_schema-drop behavior ("`json_schema` is silently dropped
  like `ClaudeCodeRunner`") — verify this comparison stays accurate.
- `docs/reference/CLI.md` — `### ll-doctor` section's example JSON enumerates
  `json_schema`/`structured_output` entries; update if the example output
  changes.
- `docs/ARCHITECTURE.md` — `CapabilityReport` consumer note (low risk, no
  field-name specifics, but mentions the same contract).
- `CONTRIBUTING.md` (~line 666) — manual pre-release `ll-doctor` sanity-check
  instructions describe expected "clean" output; update if the fix changes
  what a healthy report looks like.

### Configuration
- N/A

## Implementation Steps

1. Confirm no consumer keys off the literal name `json_schema`; pick merge vs. delete.
2. Remove or correct the entry in `ClaudeCodeRunner.describe_capabilities()`;
   audit the other runners for the same duplication.
3. Update the capability matrix in `HOST_COMPATIBILITY.md`.
4. Add a regression test asserting `ll-doctor` exits `0` for a `claude-code`
   report with no genuinely-unsupported capabilities, and that no two entries
   describe the same flag with conflicting statuses.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/API.md` — check the `GeminiRunner` row's cross-reference
   to Claude Code's json_schema-drop behavior still holds after the fix.
6. Update `docs/reference/CLI.md` — `ll-doctor` example JSON output if it changes.
7. Spot-check `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` (~line 666) for stale
   references to the old contradictory report shape.
8. Note coordination risk with sibling `BUG-2760` (same `EPIC-2765`, same
   `describe_capabilities()`/`_print_report()` functions) if worked in parallel.

## Impact

- **Priority**: P2 - The documented preflight/CI gate is permanently red on the
  default host; low fix cost, high signal-restoration value.
- **Effort**: Small - Delete/correct one entry plus test and doc updates.
- **Risk**: Low - Narrows a false-negative; the only behavior change is the exit
  code and one table row. Verify no CI/automation currently depends on the
  always-1 exit.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Capability matrix and exit-code contract |
| `docs/reference/API.md#capabilityreport` | `CapabilityReport` data model |

## Resolution

Corrected the corrective half of ENH-2627's "Option A" decision instead of
deleting `json_schema`: `ClaudeCodeRunner.describe_capabilities()`'s
`json_schema` entry now reports `"full"`, agreeing with `structured_output`,
with its note clarifying that only `build_blocking_json()`'s separate
`json_schema` parameter is still silently dropped. Updated
`HOST_COMPATIBILITY.md`'s matrix row/footnote, `API.md`'s `GeminiRunner`
cross-reference, and `CLI.md`'s example output to match. Added
`test_claude_code_json_schema_matches_structured_output` (asserts the two
entries never disagree) and `test_exit_zero_on_real_claude_code_report` (a
real, non-mocked `ClaudeCodeRunner` run through `main_doctor`) so the
regression is caught by CI going forward.

## Session Log
- `/ll:manage-issue` (fix) - 2026-07-24T20:09:01Z - `9011fd25-bf92-4159-a529-61f1828a9755.jsonl`
- `/ll:confidence-check` - 2026-07-24T20:15:00 - `41de0e1b-fb32-4039-aba7-2bae41d16e54.jsonl`
- `/ll:wire-issue` - 2026-07-24T20:02:19 - `297f783d-4ca5-44fb-9ac0-275ec41f557f.jsonl`
- `/ll:refine-issue` - 2026-07-24T19:57:43 - `7f73ef49-23cc-45fa-8bf9-7ec473e8ecad.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
