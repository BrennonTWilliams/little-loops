---
id: ENH-3125
type: ENH
title: Gate learning-test staleness on installed-version drift, not calendar age
priority: P3
status: open
discovered_date: 2026-08-08
discovered_by: ENH-3073
labels:
- learning-tests
- release
- gates
testable: true
decision_needed: false
relates_to:
- ENH-3073
- FEAT-1813
- ENH-2214
confidence_score: 40
outcome_confidence: 40
score_complexity: 60
score_test_coverage: 40
score_ambiguity: 45
score_change_surface: 55
---

# ENH-3125: Gate learning-test staleness on installed-version drift, not calendar age

## Summary

`is_record_stale()` (`scripts/little_loops/learning_tests/gate.py:45-63`) compares
`record.date` against `stale_after_days` (default 30) — a purely temporal check with no
reference to whether the target's API actually changed. ENH-3073 (Option A) fixed the
*symptom* — the release gate's output now names a remediation command for every row — but
the underlying proxy is still weak: a record proven against a dependency whose installed
version has not changed becomes a warning purely by the passage of time, and the same
seven-ish records will cross the 30-day threshold again ~30 days after ENH-3073 re-proves
them.

This is Option B from ENH-3073's Proposed Solution, filed as its own issue per that
issue's "Follow-up for Option B" section and Acceptance Criteria.

## Current Behavior

`is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool`
(`scripts/little_loops/learning_tests/gate.py:45`) computes `age_days = today -
record.date` and returns `age_days > threshold`. It has no parameter for, and never
consults, the dependency's installed version — a record proven against an unchanged
dependency is flagged stale purely because 30 days elapsed.

## Expected Behavior

A record is stale when either (a) no version was captured for it (fallback to today's
age-based check, preserving current behavior for existing records) or (b) a version was
captured and it differs from the currently installed version. A record proven against a
dependency whose installed version hasn't changed should not be flagged stale by age
alone.

## Motivation

Age is a proxy for "the API may have moved." The proxy is weak when the dependency's
installed version has not changed — which is directly observable and currently not
consulted at all.

## Proposed Solution

Record the resolved package version in the learning-test record at prove time; treat a
record as stale when the installed version differs from the proven one, falling back to
age-based staleness when no version was captured (existing records, or targets without a
resolvable installed version).

**Start from `loops/migrate-sdk-version.yaml`'s existing version resolver**, not from
scratch — ENH-3073's research found this loop (FEAT-1813, `done`) already resolves
installed versions for arbitrary third-party targets and classifies the result as
`still-valid` / `needs-upgrade` / `refuted`. `_warn_adapter_staleness` is a related but
narrower precedent, hardcoded to little-loops' own version — it is not directly reusable
for arbitrary third-party dependencies.

### Known costs (from ENH-3073's decision scoring, Option B: 4/12)

- `is_record_stale(record, stale_after_days)`'s signature likely widens to take an
  installed-version input, which ripples through its production call sites:
  `fsm/executor.py:1113,1161`, `hooks/learning_tests_gate.py:28,129`,
  `hooks/install_learning_gate.py:31,122`, `cli/ctx_stats.py:31`,
  `cli/history_context.py`, plus a dedicated test class in
  `scripts/tests/test_learning_tests_discoverability.py` (`TestIsRecordStale`).
- A new schema field on `LearnTestRecord` (the proven-against version) and a migration
  path for existing `.ll/learning-tests/*.md` frontmatter that predates the field.
- `scripts/little_loops/config-schema.json` additions for any new config knobs, plus
  `docs/reference/CONFIGURATION.md:893-905` and `docs/ARCHITECTURE.md:690` updates
  (both identified as Option-B-only in ENH-3073's wiring pass).
- `test_config.py` (`TestLearningTestsConfig`) and `test_install_learning_gate.py` need
  updates for the new field/behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

**Claim-grounding**: `loops/migrate-sdk-version.yaml` (FEAT-1813) does **not** contain a
deterministic version resolver, contrary to this section's framing. Its 8 states
(`list_stale`, `reprove_next`, `classify_outcome`, `apply_update`, `advance_queue`,
`prepare_report_path`, `build_report`, `done`) re-prove a target by shelling out to
`ll-action invoke explore-api --args "$TARGET"` (`reprove_next`, lines 68-122 — an LLM
skill invocation) and classify old-vs-new records via an LLM prompt in `classify_outcome`
(`fragment: llm_gate`, lines 124-154, emitting `CLASSIFY_JSON:{"verdict":
"still-valid"|"needs-upgrade"|"refuted"}`). There is no `importlib.metadata`, `pip show`,
or comparable deterministic version lookup anywhere in the file, and grep across
`scripts/little_loops/loops/` found no such helper elsewhere. FEAT-1813's own issue body
states explicitly that `LearnTestRecord` has no `versions` field and that earlier drafts
referencing one were incorrect — consistent with this finding.

The one generic-ish precedent that does exist is `installed_package_version()`
(`scripts/little_loops/init/install_check.py:23-34`), which wraps
`importlib.metadata.version("little-loops")` — but it is hardcoded to the literal string
`"little-loops"` and takes no package-name argument, so it is not directly reusable for
arbitrary third-party targets either (matches this section's own characterization of
`_warn_adapter_staleness` as "narrower... not directly reusable" — the same limitation
extends one level deeper, to the function `_warn_adapter_staleness` itself wraps).

**Net effect on scope**: a deterministic per-package version resolver (e.g.
`importlib.metadata.version(pkg_name)` parameterized by target, with a fallback for
targets that are not installed Python packages) is absent from the codebase today and
would need to be built new for this issue — it cannot be extracted from
`migrate-sdk-version.yaml`, since that loop's re-proving and classification both run
through the LLM rather than through Python version-comparison code.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Version resolver is a drop-in generalization of an existing wrapper**: `installed_package_version()` (`scripts/little_loops/init/install_check.py:23-34`) is `importlib.metadata.version("little-loops")` wrapped in `try/except importlib.metadata.PackageNotFoundError: return None` — the `"little-loops"` literal is the *only* hardcoded part (no install-path or pyproject read). Generalizing to `installed_package_version(pkg_name: str)` and catching the same `PackageNotFoundError` is the entire resolver change; no new exception-handling shape needs to be invented.
- **`LearnTestRecord.target` has no type discriminator — it is free text, not guaranteed to be a pip package name.** Confirmed via `scripts/little_loops/learning_tests/__init__.py:44-71` (plain `str` field, no enum/literal) and `skills/explore-api/SKILL.md:12-14` ("Free-text description of the system or API to explore", examples like `"Anthropic SDK streaming"`, `"Python pathlib"` — multi-word prose, not installable identifiers). `normalize_target()` (`scripts/little_loops/learning_tests/import_scan.py:57-64`) already works around this by taking only `target.split()[0].lower()` to compare against import-scanned packages, which is itself only a heuristic reduction. A version resolver keyed on `importlib.metadata.version(target)` will `PackageNotFoundError` for any multi-word or non-pip target — this is not an edge case to special-case, it is the common case for existing registry entries, and must route through the Expected Behavior's existing "no version captured → age-based fallback" path rather than being treated as a resolver bug.
- **Where version resolution should live**: at each of the 3 seeded call sites (`cli/learning_tests.py:53` `cmd_check`, `learning_tests/release_gate.py:58` `run_release_gate`, `fsm/executor.py:1164` `_fresh_record`), the target string is already in scope at the `is_record_stale()` call, but `run_release_gate` and `_fresh_record` both loop over multiple records/targets per invocation — resolving version per-call-site would repeat the same `importlib.metadata.version()` lookup logic at 3+ sites. A resolver embedded in or immediately adjacent to `is_record_stale()` (taking `record.target` and returning the comparison internally) avoids duplicating that loop-body resolution across callers, versus requiring each of the 8 call sites to resolve and pass `installed_version` themselves.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py:45-63` — `is_record_stale()` widens to accept an `installed_version` parameter
- `scripts/little_loops/learning_tests/__init__.py:44-71` — `LearnTestRecord` dataclass gains `proven_version` field; `to_dict()`/`from_dict()` (lines 54-71) already round-trip optional keys via `.get()`, so this addition needs no forced migration script for existing `.ll/learning-tests/*.md` frontmatter

### Dependent Files (Callers/Importers) — is_record_stale()
Full call-graph sweep found 7 non-loop call sites plus one loop-embedded call site — 4 more than the issue's Known Costs list names:
- `scripts/little_loops/cli/learning_tests.py:53` — `cmd_check()`, gated on `--stale-aware`
- `scripts/little_loops/learning_tests/release_gate.py:58` — `run_release_gate()`, filters `list_records()` for the release gate
- `scripts/little_loops/fsm/executor.py:1164` — `_execute_learning_state()`'s `_fresh_record()` closure (not lines 1113/1161 as Known Costs states — confirmed anchor is 1152-1167)
- `scripts/little_loops/hooks/learning_tests_gate.py:134` — `gate()` (PreToolUse discoverability hook), not line 28/129 as Known Costs states — confirmed call is inside `gate()` at 91-150
- `scripts/little_loops/hooks/install_learning_gate.py:122` — `gate()` (PostToolUse install-nudge hook), confirmed inside `gate()` at 88-129
- `scripts/little_loops/cli/ctx_stats.py:680` — records-summary stale-bucket counter (not line 31 as Known Costs states)
- `scripts/little_loops/cli/history_context.py:74` — `_render_learning_test_section()`, computes `effective_status` for the `## Learning Test Evidence` table row
- `scripts/little_loops/loops/migrate-sdk-version.yaml:35` — a Python-heredoc inside the `list_stale` state imports and calls `is_record_stale()` directly; not in Known Costs' list at all, and not updatable via a Python signature change alone since it's FSM YAML, not a Python caller

All 8 sites currently call with exactly `(record, stale_after_days)` — none pass version info today, consistent with the proposed optional third parameter.

### Tests
- `scripts/tests/test_learning_tests_discoverability.py:454-498` — `TestIsRecordStale`, 6 tests constructing `LearnTestRecord` via its current 5-field constructor with no `proven_version` — a new field must stay optional/keyword-defaulted or all 6 break
- `scripts/tests/test_learning_tests_gate.py` — additional gate.py coverage
- `scripts/tests/test_release_gate.py`, `scripts/tests/test_install_learning_gate.py`, `scripts/tests/test_cli_learning_tests.py`, `scripts/tests/test_cli_ctx_stats.py`, `scripts/tests/test_history_context_cli.py`, `scripts/tests/test_learning_state.py` — one per caller above
- `scripts/tests/test_config.py::TestLearningTestsConfig` — config schema test

### Configuration
- `scripts/little_loops/config-schema.json` — `learning_tests` block (~line 1046+), `stale_after_days` property (~line 1060+)
- `scripts/little_loops/config/features.py:495-515` — `LearningTestsConfig` dataclass (`stale_after_days: int = 30`)

### Documentation
- `docs/reference/CONFIGURATION.md:893-905`
- `docs/ARCHITECTURE.md:690`
- `docs/guides/LEARNING_TESTS_GUIDE.md` — staleness/record-status section

## Program Design

### Types

- `LearnTestRecord.proven_version: str | None` (new field, alongside existing `target`,
  `date`, `status`, `assertions`, `raw_output_path`)

### Signatures

- `is_record_stale(record: LearnTestRecord, stale_after_days: int, installed_version: str | None = None) -> bool`

### Call Path

`hooks/learning_tests_gate.py`, `hooks/install_learning_gate.py`, `fsm/executor.py`,
`cli/ctx_stats.py`, `cli/history_context.py` -> `is_record_stale()` -> version resolver
adapted from `loops/migrate-sdk-version.yaml` (FEAT-1813)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Call-site invocation shapes (analyzer trace)**: all 3 seeded callers already load `stale_after_days` from config immediately before calling `is_record_stale()`, and none pass version info today (matches Integration Map's "none pass version info" finding). `cmd_check` (`cli/learning_tests.py:53`) and `run_release_gate` (`release_gate.py:58`) both call with `record` already resolved; `_fresh_record` (`fsm/executor.py:1152-1167`) resolves `rec = check_learning_test(target)` inline in a per-target loop (`for target in targets:`, line 1169) and is guarded by a broad `except Exception: pass` around its config load (lines 1130-1142) that silently falls back to a hardcoded `_lt_stale_days = 30` — the same silent-fallback shape should be considered for the new `installed_version` resolution so a resolver failure degrades to the existing age-based path rather than raising.
- **`PackageNotFoundError` is the resolver's primary failure mode, not an edge case**: since `LearnTestRecord.target` is free text (see Proposed Solution → Codebase Research Findings), most existing registry entries will not resolve via `importlib.metadata.version(target)`. The resolver's `except PackageNotFoundError: return None` path (mirroring `installed_package_version()`, `init/install_check.py:23-34`) is what routes these into Expected Behavior's "no version captured → age-based fallback," not a rare failure branch.

### Confirmed current schema and behavior

- `LearnTestRecord` (`scripts/little_loops/learning_tests/__init__.py:44-71`) is exactly
  `target: str, date: str, status: Literal["proven","refuted","stale"], assertions:
  list[Assertion], raw_output_path: str | None`. `to_dict()`/`from_dict()` (54-71) use
  `.get()` with defaults for everything except `target`/`date` — a new `proven_version`
  field added as `data.get("proven_version")` round-trips cleanly through existing
  `.ll/learning-tests/*.md` frontmatter with no forced migration step.
- `is_record_stale()` (`gate.py:45-63`) is a pure leaf function (no callees, confirmed by
  code-graph query and by reading the body): `threshold = max(1, stale_after_days)`;
  unparseable/missing `record.date` → returns `False` (treated as fresh, not an error);
  `age_days > threshold` otherwise.
- Corrected call path — 8 sites, not the 5 named in Known Costs (line numbers there are
  also imprecise; confirmed anchors below):
  `cli/learning_tests.py:53` (`cmd_check`, `--stale-aware` only) · `release_gate.py:58`
  (`run_release_gate`) · `fsm/executor.py:1152-1167` (`_fresh_record` closure inside
  `_execute_learning_state`) · `hooks/learning_tests_gate.py:91-150` (`gate()`, call at
  134) · `hooks/install_learning_gate.py:88-129` (`gate()`, call at 122) ·
  `cli/ctx_stats.py:660-684` (records-summary stale bucket) ·
  `cli/history_context.py:59-90` (`_render_learning_test_section`) ·
  `loops/migrate-sdk-version.yaml:35` (Python-heredoc in the `list_stale` state — an FSM
  YAML caller, not updatable by a Python signature change alone).
- All 8 currently call with exactly `(record, stale_after_days)`; none pass version info
  today, consistent with an optional third parameter.
- Existing coverage: `test_learning_tests_discoverability.py:454-498`
  (`TestIsRecordStale`, 6 tests) constructs `LearnTestRecord` via its current 5-field
  constructor with no `proven_version` — the new field must stay optional/keyword-defaulted
  or all 6 break.
- See § Proposed Solution → Codebase Research Findings: no deterministic version resolver
  currently exists in the codebase (not in `migrate-sdk-version.yaml`, which re-proves via
  LLM) — a per-package resolver (e.g. `importlib.metadata.version(pkg)`-based) is new work,
  not an extraction from FEAT-1813.

## Scope Boundaries

**Out of scope**: anything already shipped by ENH-3073 (per-row remediation text,
`cmd_prove` hardening) — this issue is additive on top of that, not a replacement.

## Impact

- **Priority**: P3 - Closes a known weak point in an existing gate (staleness proxy),
  not a regression or user-facing bug; deferred Option B from ENH-3073.
- **Effort**: Large - Signature change ripples through 5+ call sites plus their tests
  (`TestIsRecordStale`, `TestLearningTestsConfig`, `test_install_learning_gate.py`), a
  new `LearnTestRecord` schema field with a migration path for pre-existing frontmatter,
  and new config-schema/docs updates (see Known Costs above).
- **Risk**: Medium - Touches a shared gate consumed by multiple hooks and CLIs; the
  fallback-to-age-based-staleness path for records without a captured version keeps
  existing behavior for those records, limiting blast radius.
- **Breaking Change**: No - `is_record_stale`'s new parameter is optional
  (`installed_version: str | None = None`), and records without a captured version keep
  today's age-based behavior.

## Related Issues

- ENH-3073 — made re-proving reachable (Option A); this issue is its deferred Option B
- FEAT-1813 — `migrate-sdk-version` loop; source of the version resolver this issue
  should build on
- ENH-2214 — introduced the release gate and `stale_after_days`

## Status

Open. Filed per ENH-3073's Acceptance Criteria requiring a follow-up ENH for Option B
before that issue closes. Not yet researched in depth — confidence/outcome scores are
placeholders pending `/ll:refine-issue`.


## Session Log
- `/ll:refine-issue` - 2026-08-09T20:43:47 - `e57311a1-9572-4b11-8e58-6e191d80f1ea.jsonl`
- `/ll:refine-issue` - 2026-08-09T20:27:31 - `fc23bfa7-fcc2-41bf-90ea-da56edaa284f.jsonl`
- `/ll:format-issue` - 2026-08-09T20:20:28 - `4e8af1cf-955c-4874-8514-ddcca515bcdb.jsonl`
