---
id: ENH-3449
type: ENH
title: Analytics opt-out env var so ll-history activity is side-effect-free
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T20:26:37Z'
---

# ENH-3449: Analytics opt-out env var so ll-history activity is side-effect-free

## Summary

`ll-history activity` is a read command, but every invocation writes a `cli_events` row to the project's `.ll/history.db` and creates that file if it does not exist. A downstream consumer (little-loops-hermes) wants to poll `ll-history activity --since <ts> --format json` in single-repo mode every ~30s per project, replacing its own `mode=ro` sqlite reads; it has a test asserting it never authors a missing db. That swap currently regresses the consumer's invariants.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

**Verified in code:**

- `main_history()` (`scripts/little_loops/cli/history.py:65`) wraps the *entire* command, argparse included, in `cli_event_context(DEFAULT_DB_PATH, "ll-history", sys.argv[1:])` and passes no `config`.
- In `cli_event_context` (`scripts/little_loops/session_store/writers.py:484`), `config=None` leaves `gate_open=True`, so every invocation calls `_pkg.connect(effective_path)` (creating `.ll/history.db` when absent) and inserts a `cli_events` row.
- Consequence (a): a read command authors a history.db where none existed, so the activity reader's `db_missing` branch can never fire for the local repo. The fallback comment at `history.py:684-686` acknowledges this.
- Consequence (b): under 30s polling, ~2,880 `cli_events` rows/day/project of analytics pollution.
- The already-shipped `analytics.capture.cli_commands` glob gate (ENH-2932) is dead for `ll-history` because `config` is never passed.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Add a small helper in `session_store/writers.py` (e.g. `_analytics_capture_disabled() -> bool`) reading `os.environ.get("LL_ANALYTICS_CAPTURE")`.
2. In `cli_event_context` and `skill_event_context`, short-circuit `gate_open=False` when the helper returns true, *before* `resolve_history_db`/`connect`.
3. In `cli/history.py`, load project config and pass `config=` to `cli_event_context`.
4. Rewrite the fallback comment at `history.py:684-686` to describe the new contract.
5. Document the env var in `docs/reference/CLI.md` (ll-history section) and the analytics section of `docs/reference/API.md`.
6. Tests (see AC).

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Decisions (resolved, do not re-derive)

1. **Seam is an environment variable, not an argparse flag.** The context manager opens before argparse runs, so a `--no-analytics` flag cannot suppress the enter-INSERT. `LL_ANALYTICS_CAPTURE` is read inside `cli_event_context` and `skill_event_context`: value `0`, `false`, or `off` (case-insensitive) sets `gate_open=False` before `resolve_history_db`/`connect`, so nothing touches the filesystem; the wrapped body still runs. This fixes all ~46 `cli_event_context` call sites at once and is per-invocation, which is what a polling consumer needs. Unset or any other value: unchanged behavior.
2. **Wire `config=` into `ll-history`'s `cli_event_context` call** using the same project-config loader other CLIs use, so the `analytics.capture.cli_commands` gate actually applies. Audit other `cli/*.py` callers that omit `config` and list them in the Session Log; fix in this issue only if trivial.
3. **Behavior contract.** With `LL_ANALYTICS_CAPTURE=0`, `ll-history activity` on a repo with no `.ll/history.db` exits 0, reports the local member as `status: db_missing`, `ok: false`, `instrumented: false`, and leaves no `.ll/history.db` behind. JSON output shape is otherwise unchanged.

## API/Interface

- New env var `LL_ANALYTICS_CAPTURE` (falsy values: `0`/`false`/`off`, case-insensitive) honored by `cli_event_context` and `skill_event_context`.
- `main_history()` passes `config=<loaded project config>` to `cli_event_context`.
- No new CLI flags. No JSON output-shape change.

## Acceptance Criteria

- [ ] `LL_ANALYTICS_CAPTURE=0 ll-history activity --format json` in a tmp project with no history.db: exit 0, local member `status: db_missing`, and the test asserts `.ll/history.db` does not exist after the run.
- [ ] Same command without the env var still inserts a `cli_events` row (existing behavior preserved).
- [ ] Unit tests for `cli_event_context` and `skill_event_context`: env var set → no connect, no row written.
- [ ] `analytics.capture.cli_commands` excluding `ll-history` in `.ll/ll-config.json` suppresses the row for `ll-history`.
- [ ] Fallback comment at `history.py:684-686` updated.
- [ ] `docs/reference/CLI.md` and `docs/reference/API.md` document `LL_ANALYTICS_CAPTURE`.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- FEAT-3445, FEAT-3446 (shipped `ll-history activity`), ENH-2932 (capture gate), EPIC-1707 (graceful degradation contract).
- Sibling: ENH-3450 (`has_history` signal on `RepoActivity`), same consumer.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-11T20:26:49 - `d2544764-cca3-4cd1-bd27-85b0d1d0f3c3.jsonl`
