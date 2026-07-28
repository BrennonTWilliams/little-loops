---
id: ENH-2891
status: open
priority: P2
parent: ENH-2772
blocked_by: ENH-2890
labels:
- enhancement
- architecture
- refactoring
- tests
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

## Parent Issue

Decomposed from ENH-2772: Split session_store.py god module into a subpackage.
Depends on ENH-2890 landing first (test classes are triaged against the actual
`schema.py`/`queries.py`/`lifecycle.py`/`db.py` module boundaries it creates).

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

## Session Log
- `/ll:issue-size-review` - 2026-07-28T00:00:00 - `b1c96f1a-23da-4c31-89fd-9b68894245c4.jsonl`

---

## Status

**Open** | Created: 2026-07-28 | Priority: P2
