---
id: ENH-2935
title: Tamper guard Python adapter - ll-auto/ll-parallel/ll-sprint coverage
type: ENH
priority: P2
status: open
discovered_date: 2026-07-30
epic: EPIC-2856
parent: EPIC-2856
blocked_by:
- ENH-2933
labels:
- rework
- verification
relates_to:
- ENH-2854
---

# ENH-2935: Tamper guard Python adapter - ll-auto/ll-parallel/ll-sprint coverage

## Parent Issue

Decomposed from ENH-2854: Guard against agent edits to test files during
verification. This child covers the non-FSM half of the guard's surface —
`ll-auto`, `ll-parallel`, and `ll-sprint` verify in plain Python
(`work_verification.py`), never entering the FSM, so no `tamper_guard:`
state key (ENH-2934) can apply to them. It depends on ENH-2933 (the guard
core) landing first, and is independent of ENH-2934 (the FSM adapter) — the
two adapters can proceed in parallel once the core exists.

## Summary

Hook the tamper guard core (ENH-2933) into `work_verification.py`'s shared
verification path, and add the project-global config key that supplies the
guard's default policy for this non-FSM path.

## Motivation

See ENH-2854 for the full origin. `issue_manager.py`'s Phase 3
(`verify_issue_completed()`/`verify_work_was_done()`) and
`worker_pool.py:596` → `_verify_work_was_done()` (which `ll-sprint` inherits
via the shared `ParallelOrchestrator`) both verify without ever entering the
FSM. Without this adapter, an `ll-auto`/`ll-parallel`/`ll-sprint` run can
weaken tests and still report success — the FSM adapter alone does not
close this gap.

## Proposed Solution

1. **Hook**: call `run_tamper_guard` (ENH-2933) from
   `work_verification.py:verify_work_was_done()` (L44), which already
   receives (or derives) the changed-file set the guard needs. Both
   `issue_manager.py:31` and `worker_pool.py:38` already import this
   module, so both orchestrators inherit the guard from one shared hook
   rather than two independent ones.
2. **Config key**: add the non-FSM policy-default key to
   `config-schema.json`, following `code_query.staleness` (~L1296) as the
   shape and location precedent (3-mode enum, default `fail`). Mirror it on
   the Python side — either as a `project.*` field on `ProjectConfig`
   (`scripts/little_loops/config/core.py` ~L148-195: field declaration,
   `from_dict()`, and the reverse-serialization block ~L866-872) or as a
   sibling `CodeQueryConfig`-style field
   (`scripts/little_loops/config/features.py:834-847`) — exactly one
   `config/*.py` dataclass needs the matching field/`from_dict`/
   serialization lines. Smoke-check that the key resolves through
   `BRConfig.resolve_variable()` (`config/core.py:912`), the method
   `ll-config get <key>` wraps.
3. **Precedence**: this config key exists solely to supply (a) the default
   for the non-FSM path and (b) the loop-level fallback default consumed by
   ENH-2934's FSM adapter; it never overrides an explicit state-level
   `tamper_guard:` key. Full precedence: state-level > loop-level default >
   project config key > built-in `fail`.
4. **Revert on the non-FSM path** reuses
   `worker_pool.py:_cleanup_leaked_files()`'s (L1362) git tracked-vs-
   untracked split — the same shape ENH-2933's core already follows, so
   this should fall out of calling the core directly rather than needing a
   second implementation.

## Design Notes

- `verify_work_was_done(logger, changed_files=None, baseline_sha=None)`:
  when `changed_files` is `None` (the `ll-auto` path), it derives the set
  itself from three sequential `git diff` calls (uncommitted, staged,
  committed-since-`baseline_sha`) — intersect that derived set against
  `filter_test_files()` (ENH-2865, via ENH-2933's core) before deciding
  revert/fail/allow.
- `issue_manager.py`'s two call sites needing confirmation: L1072 and L1109
  (Phase 3 spans L1049-1129). `worker_pool.py`'s call site: L596,
  `_verify_work_was_done()` at L1212.
- Three distinct import/patch surfaces resolve to `verify_work_was_done`:
  `little_loops.work_verification.verify_work_was_done`,
  `little_loops.git_operations.verify_work_was_done` (re-exported for
  backward compat, `git_operations.py:15-18`; used directly by
  `scripts/tests/test_subprocess_mocks.py:~451-545`), and
  `"little_loops.issue_manager.verify_work_was_done"` (patched in
  `scripts/tests/test_issue_manager.py:~2632-2932`). Existing tests that
  patch `verify_work_was_done` wholesale will bypass the new
  `run_tamper_guard` call entirely — new tamper-guard tests must patch/
  exercise `run_tamper_guard` itself (or its call site inside
  `verify_work_was_done`), not stub `verify_work_was_done`.

## Program Design

Reuses `TamperPolicy`, `TamperReport`, `run_tamper_guard` from ENH-2933's
`scripts/little_loops/test_tamper_guard.py`. No new core types; the only
new field is the config-schema policy-default key and its `ProjectConfig`
(or `CodeQueryConfig`) mirror.

### Call Path

`verify_work_was_done` (`work_verification.py:44`) → `run_tamper_guard`
(ENH-2933) → `filter_test_files` (ENH-2865) → `snapshot_test_paths` →
`compare_snapshots` → `apply_tamper_policy`, with the policy resolved from
the config key (via `BRConfig`) when no FSM-level override is in play.

## Files to Modify

- `scripts/little_loops/work_verification.py` — call the guard core from `verify_work_was_done()`.
- `scripts/little_loops/issue_manager.py` (~L1049-1129, Phase 3) — confirm the guard fires via the shared `work_verification.py` hook (no independent hook).
- `scripts/little_loops/parallel/worker_pool.py` (~L596, `_verify_work_was_done` L1212) — same confirmation for `ll-parallel`/`ll-sprint`.
- `scripts/little_loops/config-schema.json` — new `project.*` (or `code_query`-sibling) policy-default key, `code_query.staleness` (~L1296) as shape/location precedent.
- `scripts/little_loops/config/core.py` (~L148-195, ~L866-872) or `scripts/little_loops/config/features.py:834-847` — matching dataclass field, `from_dict`, serialization.
- `docs/reference/CONFIGURATION.md` (~L294-305) — new row for the policy key, same shape as the `test_patterns` row.
- `docs/reference/API.md` — `## little_loops.work_verification` section (~L2293-2364, update if the signature changes); `### ProjectConfig` (~L386-406) field row with `# ENH-2935` provenance if the key lands there; module-index row (~L33) for `little_loops.test_tamper_guard` if not already added by ENH-2933.

### Tests
- `scripts/tests/test_work_verification.py:512-539`, `TestVerifyWorkWasDoneIntegration` — add a tamper-guard-tripped scenario (a diff touching only test-pattern-matched files), mocking `subprocess.run` per the existing convention.
- `scripts/tests/test_worker_pool.py:1316-1350` — extend the four existing `_verify_work_was_done` unit tests (`_accepts_code_changes`, `_rejects_no_changes`, `_rejects_excluded_only`, `_respects_config`) to cover the tamper-guard path.
- `scripts/tests/test_config_schema.py:337-357` (`test_health_url_in_schema`) and `:359` (`test_project_test_patterns_in_schema`) — template for the new policy-key schema-presence test.
- New tests must patch/exercise `run_tamper_guard` directly (see Design Notes) rather than stubbing `verify_work_was_done` wholesale, or they silently don't exercise the guard.
- A test covering `ll-auto` end-to-end (`issue_manager.py` Phase 3) where an agent weakened a test trips the guard with no FSM state involved.
- A test covering the full precedence chain for the non-FSM path: loop-level default > config key > built-in `fail`, and confirming the config key never overrides an explicit FSM state-level key when one is present (cross-checked against ENH-2934's state-level test).

## Scope Boundaries

**In scope:** the `work_verification.py` hook, confirming both orchestrator
call sites inherit it, the non-FSM config-default policy key and its
`ProjectConfig`/`CodeQueryConfig` mirror, and the precedence chain's
non-FSM half (loop default > config key > built-in default).

**Out of scope:**
- The guard core itself — ENH-2933, consumed here.
- The `tamper_guard:` FSM state key, its schema/lint, and the
  `executor.py` hook — ENH-2934.
- `project.test_patterns` — ENH-2865.

## Acceptance Criteria

- [ ] `work_verification.verify_work_was_done()` calls `run_tamper_guard` (ENH-2933) against the changed-file set (explicit or self-derived).
- [ ] The guard fires on the non-FSM path: an `ll-auto` run whose agent weakened a test trips it, with no FSM state involved — covered by a direct test.
- [ ] The guard fires for `ll-parallel`/`ll-sprint` via the same `work_verification.py` path, not a second independently-maintained hook.
- [ ] A project-global config key (shape/location precedent: `code_query.staleness`) supplies the default policy for the non-FSM path and the FSM adapter's loop-level fallback; it is documented in `config-schema.json`, mirrored on exactly one `config/*.py` dataclass, and resolves through `BRConfig.resolve_variable()`.
- [ ] The config key never overrides an explicit FSM state-level `tamper_guard:` key — a test covers this precedence level.
- [ ] `revert` on the non-FSM path uses the same git tracked-vs-untracked handling as `worker_pool.py:_cleanup_leaked_files()`, via the shared core (no second revert implementation).
- [ ] New tests exercise `run_tamper_guard`/its call site directly, not a wholesale `verify_work_was_done` stub.
- [ ] `docs/reference/CONFIGURATION.md` and `docs/reference/API.md` are updated per Files to Modify.

## Impact

- **Priority (P2)**: inherited from ENH-2854.
- **Effort**: Medium — one shared hook plus a triple-declared config key (schema + dataclass + docs), but no new core logic.
- **Risk**: Low-Moderate — `work_verification.py` is a shared chokepoint for two orchestrators; the existing test-patching surface fragmentation (three import paths resolving to `verify_work_was_done`) is a real risk of tests silently not exercising the guard if not handled per Design Notes.

## Status

**Open** | Created: 2026-07-30 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-31T03:22:37 - `8a99a216-98a4-4273-8b35-65acee67e859.jsonl`
