---
id: ENH-2887
title: Thread action-severity through ll-doctor --full aggregation
type: ENH
parent: EPIC-2872
priority: P2
status: done
discovered_date: 2026-07-28
completed_at: '2026-07-28T08:39:39Z'
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
relates_to:
- ENH-2875
decision_needed: false
confidence_score: 94
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 20
---

# ENH-2887: Thread action-severity through ll-doctor --full aggregation

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

`ll-doctor --full` collapses the entire underlying `VerificationResult`/`LinkCheckResult` into a single `CheckResult` note string, discarding per-finding granularity. Once ENH-2886 adds the `auto`/`mention`/`route` action-severity field to those result types, `ll-doctor --full` needs to thread it through instead of collapsing it, so per-finding action-severity survives to the aggregated output.

## Current Behavior

`scripts/little_loops/cli/doctor.py` — `CheckResult` (lines 32-47) already has a two-tier `severity: Literal["error", "informational"]` field, but it only gates `ll-doctor`'s own exit code via `_exit_code_for()` (lines 98-101) — a different axis from action-severity. `_full_docs_check()` (line 486) and `_full_check_links_check()` (line 760) collapse the entire underlying result into a single `CheckResult` note string, discarding per-finding granularity.

## Expected Behavior

`_full_docs_check()` and `_full_check_links_check()` surface each finding's action-severity (added in ENH-2886) in the `--full` output, without conflating it with `CheckResult`'s existing `error`/`informational` exit-code-governing severity field.

## Impact

- **Priority**: P2 - Completes the action-severity surfacing chain started by ENH-2886; needed before ENH-2888/ENH-2889 can rely on `--full` output distinguishing per-finding severity.
- **Effort**: Small - additive `findings` field on an existing frozen dataclass, following the `CheckResult.severity` precedent already in the file.
- **Risk**: Low - scoped to two `_full_*` adapters; shared `_print_full_section()`/`_full_section_data()` plumbing and all other `register_full_check` adapters are untouched via the `findings=()` default.
- **Breaking Change**: No

## Scope Boundaries

In scope: `_full_docs_check()`/`_full_check_links_check()` aggregation logic and their output shape for action-severity. Out of scope: the action-severity field itself (ENH-2886, a prerequisite), the session-start hook (ENH-2888), `docs-sync.yaml` (ENH-2889).

## Similar Patterns

- `scripts/little_loops/cli/doctor.py` `CheckResult` docstring (~line 36) states it "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape" — this precedent for the existing severity field's design should inform the aggregation shape for action-severity.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

ENH-2886 landed the underlying `action_severity: Literal["auto", "mention", "route"]` field (plus `route_owner: str | None`) on both `doc_counts.CountResult` (`scripts/little_loops/doc_counts.py:37-56`) and `link_checker.LinkResult` (`scripts/little_loops/link_checker.py:60-88`) — both are currently uncommitted working-tree changes, not yet on a merged commit. `format_result_json()` in each module already serializes `action_severity`/`route_owner` per-finding (`doc_counts.py:245-246`, `link_checker.py:536-537`). This issue's job is purely on the `--full` aggregation side in `doctor.py`, which still throws that per-finding detail away:

- `_full_docs_data()` (`doctor.py:475-483`) calls `verify_documentation(Path.cwd())` and, on mismatch, joins `m.category for m in result.mismatches` into a single `note` string — `action_severity` is read nowhere.
- `_full_docs_check()` (`doctor.py:486-489`) wraps that dict into one `CheckResult(name="full:docs", status=..., note=...)` — one `CheckResult` for the whole run, not one per mismatch.
- `_full_check_links_data()` (`doctor.py:734-757`) calls `check_markdown_links()` and reduces to three coarse counts (`result.broken_links`, `result.unreachable_links`, `result.valid_links`) — `action_severity` on individual `LinkResult`s (currently always `"mention"` for broken/unreachable, ENH-2886's `link_checker.py:353,395,408`) is never read.
- `_full_check_links_check()` (`doctor.py:760-770`) wraps that into one `CheckResult(name="full:check_links", ...)`.
- `_print_full_section()` (`doctor.py:773-782`) and `_full_section_data()` (`doctor.py:785-790`) both iterate `_run_full_checks()` and read only `result.status`/`result.note` per `CheckResult` — whatever shape `_full_docs_check`/`_full_check_links_check` return has to flow through these two unchanged, since they're shared by every other `register_full_check` adapter (`_full_skill_budget_check`, `_full_triggers_check`, etc. at lines 508-771) and are out of this issue's scope per Scope Boundaries.
- `CheckResult` itself (`doctor.py:32-47`) is `@dataclass(frozen=True)` with exactly four fields (`name`, `status`, `note`, `severity`) — no field currently carries action-severity. Any new per-finding data must not repurpose `severity` (that axis feeds `_exit_code_for()` at `doctor.py:98-101` and must stay untouched per this issue's Acceptance Criteria).

### Tests

- `scripts/tests/test_cli_doctor_full.py:10-45,162-173` — existing coverage imports and exercises `_full_docs_data`/`_full_check_links_data` directly; new action-severity assertions belong alongside these.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Two viable shapes for surfacing per-finding action-severity through the existing one-`CheckResult`-per-verifier aggregation, given `CheckResult` is frozen and shared by every other `register_full_check` adapter:

**Option A**: Emit one `CheckResult` per mismatch/broken-link instead of one per verifier. `_full_docs_check()`/`_full_check_links_check()` would return a list entry per `CountResult`/`LinkResult` (e.g. `name="full:docs:{category}"`), each carrying its own `action_severity` via a new optional field. `_print_full_section()`/`_full_section_data()` need no change since they already iterate a list — but the printed output goes from one line per verifier to one line per finding, changing today's terse `--full` summary shape (and the `CONTRIBUTING.md` release-checklist string, see Documentation section) for every other check, not just docs/links.

> **Selected:** Option B — additive `findings` field on `CheckResult`, keeping one-`CheckResult`-per-verifier shape

**Option B**: Keep one `CheckResult` per verifier, but add a new optional field (e.g. `findings: tuple[FindingDetail, ...] = ()`, a small frozen dataclass carrying `category`/`action_severity`/`route_owner` or `url`/`action_severity`/`route_owner`) populated only by `_full_docs_check()`/`_full_check_links_check()`. `_print_full_section()` prints the existing summary line unchanged, then (if present) a per-finding sub-line breakdown; `_full_section_data()`'s JSON dict gains a `findings` key alongside `status`/`note`. Every other `register_full_check` adapter is untouched (defaults to `findings=()`).

**Recommended**: Option B — it keeps `--full`'s existing one-line-per-verifier summary shape intact for every other check (least disruption to `CONTRIBUTING.md`'s hand-asserted string and any downstream consumer of today's terse output), and additive optional fields on a frozen dataclass are the same technique `CheckResult.severity` itself already used to layer a second axis onto an existing shape without touching callers that don't set it.

### Decision Rationale

**Selected: Option B** (additive `findings: tuple[FindingDetail, ...] = ()` field on `CheckResult`).

`_print_full_section()` and `_full_section_data()` (`doctor.py:773-790`) are shared by all 11 `register_full_check` adapters and both assume a stable 1:1 verifier-name-to-`CheckResult` mapping. Option A (one `CheckResult` per finding) is well-supported at the `register_full_check`/`_run_full_checks()` plumbing layer (already list-typed and list-flattening), but breaks that shared 1:1 assumption for docs/links only, producing mixed granularity across the `--full` section and failing two existing tests outright (`test_cli_doctor_full.py:189-207`, `209-214`). Option B repeats a pattern already proven twice in this exact file family — `CheckResult.severity` itself was added as an optional field with a default to the same dataclass, and `CountResult`/`LinkResult` already carry `action_severity`/`route_owner` as optional fields with the exact names/types a `FindingDetail` would wrap — so no new field names or types need inventing, and every other adapter compiles/runs unchanged via the `findings=()` default. The only cost is a one-line update to `test_cli_doctor_full.py:214`'s key-set assertion.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 1 | 3 |
| Simplicity | 1 | 2 |
| Testability | 1 | 3 |
| Risk | 1 | 3 |
| **Total** | **4/12** | **11/12** |

Key evidence: `CheckResult.severity` (`doctor.py:47`) is direct precedent for additive-optional-field extension on this exact dataclass; `_print_full_section()`'s docstring (`doctor.py:774`) explicitly documents "one line per verifier," which Option A violates for docs/links only; `CountResult`/`LinkResult` (ENH-2886) already expose `action_severity`/`route_owner` fields with names Option B's `FindingDetail` maps 1:1.

## Acceptance Criteria

- `ll-doctor --full` output distinguishes each finding's action-severity without conflating it with the existing `error`/`informational` exit-code axis.
- `CheckResult`'s existing `error`/`informational` severity axis is untouched.

## Tests

- `scripts/tests/test_cli_doctor.py`, `test_cli_doctor_full.py`, `test_cli_doctor_install_checks.py` — cover `main_doctor()` and `--full` aggregation adapters (`_full_docs_data`, etc.); need new coverage for action-severity surfacing in `--full` output.

## Documentation

- `docs/reference/CLI.md` — update `ll-doctor --full` output documentation for the surfaced action-severity.
- `scripts/little_loops/adapters/capabilities.py` (docstring ~line 20) — the "mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status shape" comment references `CheckResult`'s shape; verify it doesn't need updating once `--full` output changes.
- `CONTRIBUTING.md` (line ~664) — the release checklist hand-asserts a specific `ll-doctor` output string ("{N} tool(s) discovered"); verify the `--full` output-shape change for action-severity doesn't break this assertion.

## Session Log
- `/ll:manage-issue` - 2026-07-28T08:39:00 - `2b1dc26a-f845-4975-99a6-cfb738d84dbb.jsonl`
- `/ll:ready-issue` - 2026-07-28T08:30:11 - `72beb555-0cc4-466a-b489-a0c2cf0dd8bc.jsonl`
- `/ll:decide-issue` - 2026-07-28T08:28:03 - `c11bc1b1-8032-4478-a440-c6b36964cfe7.jsonl`
- `/ll:refine-issue` - 2026-07-28T08:25:04 - `d3d4e805-b479-4213-ac8d-6f327e2aa3c4.jsonl`
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Resolution

Implemented Option B: added a `FindingDetail` frozen dataclass (`label`,
`action_severity`, `route_owner`) and an additive `findings: tuple[FindingDetail, ...] = ()`
field on `CheckResult` (`scripts/little_loops/cli/doctor.py`). `_full_docs_check()`
and `_full_check_links_check()` now populate `findings` from each mismatched
`CountResult`/broken-or-unreachable `LinkResult`'s `action_severity`/`route_owner`.
`_print_full_section()` prints a `- <label>: <action_severity>` sub-line per
finding (with `-> <route_owner>` when routed); `_full_section_data()`'s JSON
`findings` key carries the same data. Every other `register_full_check` adapter
is unchanged via the `findings=()` default. Added coverage in
`test_cli_doctor_full.py` for both adapters' findings population and updated
the existing `_full_section_data` key-set assertion. Verified `docs/reference/CLI.md`'s
`--full` section, `capabilities.py`'s docstring, and `CONTRIBUTING.md`'s release
checklist string per the issue's Documentation section — only `CLI.md` needed
an update (the other two reference unaffected surfaces).

## Status

open
