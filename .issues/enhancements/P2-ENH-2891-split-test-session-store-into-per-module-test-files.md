---
id: ENH-2891
status: done
priority: P2
parent: EPIC-2789
blocked_by: []
labels:
- enhancement
- architecture
- refactoring
- tests
relates_to:
- ENH-2772
confidence_score: 92
outcome_confidence: 78
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 15
score_change_surface: 23
completed_at: '2026-07-28T11:04:41Z'
---

# ENH-2891: Split test_session_store.py into per-module test files

## Summary

`scripts/tests/test_session_store.py` (~6,900 lines, ~75 `class Test*` groups
organized by feature/schema-version, not by module boundary) should be split
into flat test files mirroring the `session_store/` subpackage created by
ENH-2890: `test_session_store_schema.py`, `test_session_store_queries.py`,
`test_session_store_lifecycle.py`, `test_session_store_db.py` (or similar),
following the existing `fsm/`/`issue_history/` convention of flat
`test_<package>_<concern>.py` files under `scripts/tests/` — no new
`scripts/tests/session_store/` mirror directory.

## Current Behavior

`scripts/tests/test_session_store.py` is a single 6,843-line file containing
80 `class Test*` groups organized by feature/schema-version, mirroring the
pre-ENH-2890 monolithic `session_store.py`. It no longer reflects the module
boundaries (`schema.py`, `db.py`, `lifecycle.py`, `queries.py`, `writers.py`)
that ENH-2890 established in `scripts/little_loops/session_store/`, making it
hard to locate the tests for a given module and slow to navigate/diff.

## Expected Behavior

`test_session_store.py` is replaced by flat, module-scoped test files
(`test_session_store_schema.py`, `test_session_store_db.py`,
`test_session_store_lifecycle.py`, `test_session_store_queries.py`,
`test_session_store_writers.py`, adjusted per triage) following the
`test_fsm_*.py`/`test_issue_history_*.py` naming precedent, with every test
and private-name import preserved and the full suite passing with an
unchanged test count.

## Impact

Low runtime risk (test-only reorganization; no production code changes), but
meaningful maintainability payoff: faster navigation, smaller diffs per
module change, and parity with the `fsm/`/`issue_history/` test-layout
convention already used elsewhere in `scripts/tests/`. Leaving it unsplit
means every future `session_store` change keeps touching a single
6,800+ line file regardless of which module it actually affects.

## Scope Boundaries

In scope: splitting `test_session_store.py` into per-module test files,
relocating the file-local `_module_tmp_parent`/`tmp_path` fixture pair (see
Implementation Steps), and updating the stale prose reference in
`test_enh_2497_agent_type.py:28`. Out of scope: any change to
`scripts/little_loops/session_store/*.py` production code, `conftest.py`'s
shared fixtures beyond the fixture-pair decision this issue must make, and
`scripts/tests/test_verify_kinds.py` (explicitly preserved unchanged per
Proposed Solution step 3).

## Parent Issue

Decomposed from ENH-2772: Split session_store.py god module into a subpackage.
ENH-2890 has landed (test classes are triaged against the actual
`schema.py`/`queries.py`/`lifecycle.py`/`db.py`/`writers.py` module boundaries
it created).

## Proposed Solution

1. Manually triage each of the ~75 `class Test*` groups in
   `test_session_store.py` against the module boundaries ENH-2890 created —
   no mechanical move exists since the classes are grouped by
   feature/schema-version, not by module.
2. Move private-name imports (`test_session_store.py:16-40`: `_KIND_TABLE`,
   `_derive_transition`, `_estimate_tokens`, `_pack_payload`,
   `_summarize_block`, `_unpack_payload`, `SCHEMA_VERSION`, `VALID_KINDS`) to
   whichever new test file uses them; all must remain resolvable off the
   top-level `session_store` package per ENH-2890's re-export surface.
3. Preserve `scripts/tests/test_verify_kinds.py` unchanged — it exercises the
   `_MIGRATIONS`/`_KIND_TABLE` attribute-access path and isn't part of this
   split.
4. No new `conftest.py` needed beyond the existing shared root fixture file,
   per the `fsm/`/`issue_history/` precedent.
5. Run the full suite (`python -m pytest scripts/tests/`) after the split and
   confirm `scripts/tests/conftest.py:615-655`'s `_guard_real_history_db`
   autouse fixture still passes for every new file (it patches
   `session_store.sqlite3.connect`, a suite-wide setup dependency — the
   highest-risk regression point, already hardened by ENH-2890 but worth an
   explicit check here since the fixture now applies across multiple files).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The `session_store/` subpackage created by ENH-2890 has **five** modules,
  not four: `schema.py` (1,059 lines), `db.py` (95 lines), `lifecycle.py`
  (1,382 lines), `queries.py` (193 lines), and **`writers.py` (2,696 lines —
  the largest module, entirely unmentioned in the original Proposed
  Solution)**. `writers.py` holds all `record_*_event()` writer functions
  (`record_correction`, `record_skill_event`, `record_commit_event`,
  `record_verdict_event`, `record_review_event`, `record_context_pressure_event`,
  `record_subagent_run_start/stop`, `SQLiteTransport`, etc.) plus the majority
  of the private helpers the issue calls out. A 5th test file —
  `test_session_store_writers.py` — should be added to the split target list.
- The private-name-to-module mapping (relevant to step 2 of Proposed
  Solution): `SCHEMA_VERSION`, `VALID_KINDS`, `_KIND_TABLE`, `_MIGRATIONS` →
  `schema.py`; `_estimate_tokens`, `_summarize_block` → `lifecycle.py`;
  `_pack_payload`, `_unpack_payload` (`writers.py:58,63`), `_derive_transition`
  (`writers.py:1768`) → `writers.py` (not `lifecycle.py`, despite `_pack_payload`
  historically living near summary code). All are re-exported from
  `scripts/little_loops/session_store/__init__.py:72-215`.
- Actual count: **80** `class Test*` groups in
  `scripts/tests/test_session_store.py` (verified via
  `grep -c '^class Test'`), not "~75" as stated in the Summary — e.g.
  `TestPackageReexportSurface` at line 6814 is the final class and exercises
  `__init__.py`'s re-export surface directly, a natural fit for whichever new
  file also covers `schema.py`/`db.py` package-level concerns, or a small
  standalone file if none fits cleanly.
- Naming precedent confirmed: `scripts/tests/test_fsm_*.py` (15 files, e.g.
  `test_fsm_executor.py`, `test_fsm_validation.py`) and
  `scripts/tests/test_issue_history_*.py` (8 files, e.g.
  `test_issue_history_analysis.py`) both use flat
  `test_<package>_<concern>.py` naming directly under `scripts/tests/` with no
  package-mirroring subdirectory — matches this issue's stated approach.
- `scripts/tests/conftest.py:615-655`'s `_guard_real_history_db` fixture
  patches `sqlite3.connect` on the `little_loops.session_store` package module
  object (a singleton `sqlite3` reference), so it transparently covers opens
  from any of the five submodules — no per-file fixture changes needed beyond
  what already exists.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh_2497_agent_type.py:28` — prose comment references "the helper in `test_session_store.py`" (i.e. `_bootstrap_schema_at`); update to point at whichever new file `_bootstrap_schema_at` lands in once triaged. Not an executable import, so it won't break the suite, but will be stale documentation if left as-is.

### Implementation Steps (additional consideration)

_Wiring pass added by `/ll:wire-issue`:_
- `test_session_store.py:46-64` defines a **file-local, non-conftest fixture pair** unique to this file: `_module_tmp_parent` (module-scoped `tmp_path_factory.mktemp("session_store")`) and an override `tmp_path` fixture that shadows pytest's builtin to consolidate all of the file's per-test temp dirs under one module parent (ENH-2529, to reduce macOS `launchservicesd` churn — see [[project_test_suite_beachball_fix]] memory). The `test_fsm_*`/`test_issue_history_*` precedent has no equivalent construct to copy, so triage must explicitly decide: duplicate this fixture pair into each of the 5 new files (simplest, but reintroduces 5 separate `tmp_path_factory.mktemp()` calls), keep it in only one file and have the others use plain `tmp_path` (loses the churn mitigation for 4/5 files), or promote it to `scripts/tests/conftest.py` as a shared fixture (most consistent, but changes fixture scope/behavior for other test files too — verify it doesn't affect the beachball-mitigation intent, which was scoped module-by-module for a reason). This directly affects whether Acceptance Criterion "no test lost or silently skipped" and "full suite passes" hold on macOS — the fixture exists specifically to prevent test-runner instability, not just to be tidy.

## Acceptance Criteria

- `scripts/tests/test_session_store.py` no longer exists as a single flat
  file; its ~75 test classes are distributed across
  `test_session_store_schema.py`, `test_session_store_queries.py`,
  `test_session_store_lifecycle.py`, `test_session_store_db.py` (adjust
  naming/grouping as triage reveals better boundaries).
- Every test that imported a private name directly continues to do so
  successfully from its new file.
- `python -m pytest scripts/tests/` passes in full, with no test lost or
  silently skipped during the move (test count before == test count after).

## Resolution

`scripts/tests/test_session_store.py` (6,843 lines, 80 `class Test*` groups)
was triaged against the five `session_store/` submodules (ENH-2890) by
scoring which module-defined names each class body actually referenced, then
split into `test_session_store_schema.py` (29 classes), `test_session_store_writers.py`
(26), `test_session_store_lifecycle.py` (20), `test_session_store_queries.py` (4),
and `test_session_store_db.py` (1), following the flat `test_<package>_<concern>.py`
naming used by `test_fsm_*.py`/`test_issue_history_*.py`. All private-name imports
resolve from the `session_store` package re-export surface per file. The
`_module_tmp_parent`/`tmp_path` fixture pair (ENH-2529) was duplicated into
each new file rather than promoted to `conftest.py`, preserving its
per-file churn-mitigation scope. The `_bootstrap_schema_at` and
`_make_completed`/`_llm_response` module-level test helpers were likewise
duplicated into every file that uses them (schema+writers; lifecycle,
respectively). `test_enh_2497_agent_type.py:28`'s stale prose reference was
updated to point at `test_session_store_schema.py`. Test count before/after:
402/402 (`python -m pytest scripts/tests/test_session_store_*.py`, 402 passed).
Full suite: `python -m pytest scripts/tests/` — 16,825 passed, 7 pre-existing
failures unrelated to this change (confirmed identical on `main` pre-split:
`test_prose_dep_sweep_gate`, `test_enh494_skill_companions`, and 5 others in
`test_general_task_loop.py`/`test_builtin_loops.py`/`test_rn_refine.py`).

## Session Log
- `/ll:manage-issue` - 2026-07-28T11:03:53 - `e559c8fd-889d-4dca-a677-bf3d9b1331a9.jsonl`
- `/ll:ready-issue` - 2026-07-28T10:56:01 - `6b4a38a1-47c1-4860-9a28-51a9f76cb04c.jsonl`
- `/ll:wire-issue` - 2026-07-28T10:53:13 - `2ac5a980-a0f3-4ff1-a7fb-4a8680e779ab.jsonl`
- `/ll:refine-issue` - 2026-07-28T10:47:23 - `be1a582f-5452-4cdc-b8cc-584428475c5d.jsonl`
- `/ll:refine-issue` - 2026-07-28T10:47:19 - `be1a582f-5452-4cdc-b8cc-584428475c5d.jsonl`
- `/ll:issue-size-review` - 2026-07-28T00:00:00 - `b1c96f1a-23da-4c31-89fd-9b68894245c4.jsonl`

---

## Status

**Open** | Created: 2026-07-28 | Priority: P2
