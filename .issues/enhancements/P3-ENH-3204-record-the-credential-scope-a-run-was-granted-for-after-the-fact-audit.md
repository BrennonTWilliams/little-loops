---
id: ENH-3204
type: ENH
title: Record the credential scope a run was granted for after-the-fact audit
priority: P3
status: open
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3233
- ENH-3234
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: true
verify_verdict: VALID
---

# ENH-3204: Record the credential scope a run was granted for after-the-fact audit

## Summary

Nothing anywhere records what authority a given run held. Once a task can declare a credential scope, an audit should be able to answer after the fact what a given run could reach.

Record the declared scope with the run. The record stores **scope and variable *names* only — never values**.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no declaration code has landed yet. The enforcement chokepoint is ENH-3233; the declaration surfaces this issue records arrive with ENH-3234 (`ActionSpec`) and ENH-3235 (`StateConfig`). All three are in `blocked_by`; scope *names* in the record only exist once at least one declaration surface ships.

## Current Behavior

No table, column, or log line records the authority a run held. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped for this.

## Expected Behavior

Each run records the capability and variable names it was granted, queryable after the fact. Names only — a record that could leak a credential value is worse than no record.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` is currently **46** (line 25, verified 2026-09-03), so a new migration is **v47**. Confirm the current value before writing the migration; it moves (it already drifted from 40, then 45, since this issue was written).
- The projection helper in `scripts/little_loops/host_runner.py` — emits the granted-names record at spawn time.

### Tests
- `scripts/tests/` — migration round-trip, plus a test asserting no credential *value* can reach the record.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Spawn-site audit (2026-09-03): none of the 8 confirmed call sites into `project_child_env()`/`_apply_automation_env()` currently hold a genuine loop/spawn run identifier. The 6 `build_streaming()` methods (`host_runner.py:410,718,1127,1319,1515,1715`) are pure `HostInvocation`-construction factories with no run_id parameter; `run_blocking_json()` (`host_runner.py:2178`) and `verify_epic_branch_before_merge()` (`worktree_utils.py:721`) hold no loop-run context either. `FSMExecutor.run_id` (set at `fsm/executor.py:570`) is the nearest genuine run identifier, several stack frames above the actual spawn — it is not threaded down as a parameter today. See Open Decisions.
- `subprocess_utils.run_claude_command()` (`subprocess_utils.py:422-445`) is the site closest to holding both a spawn context and the actual PID: it calls `project_child_env(invocation, extra=extra_env)` at line 529, then `subprocess.Popen(...)` at line 534-543 in the same function — but its signature has no `run_id` param, only `extra_env` and an `on_process_start` callback invoked with the live `Popen`.
- Candidate writer-function siblings already in this codebase: `write_advisor_consult()` (`session_store/writers.py:1823-1897`) and `write_research_triage()` (`session_store/writers.py:1898-1942`) — both new-dedicated-table, live-write-only, fail-soft (`try/except sqlite3.Error: logger.warning(...); return False`) writers; a scope-record writer would follow this same shape.
- Tests: migration test class shape is `TestSchemaV46ResearchTriageEvents` (`scripts/tests/test_session_store_schema.py:2653-2751` — columns, indexes, CHECK-constraint rejection, upgrade-from-prior-version, kind registration, rebuild-exclusion) and `test_schema_version_matches_migrations_length()` (`test_session_store_schema.py:2132`), both needing a v47 counterpart. Writer test shape is `TestWriteResearchTriage`/`TestWriteAdvisorConsult` (`test_session_store_writers.py:2712-2858`), including a `test_graceful_when_store_unwritable` fail-soft case.
- No existing runtime helper or test enforces "value never leaks" anywhere in this codebase — `pii.py`/`redact_pii()` targets SFT-corpus text (email/phone/SSN), not env-var credentials, and no test of the form "assert secret value not in serialized record" exists today. The "names only" test this issue requires has no precedent to follow.

## Program Design

### Types
- No existing per-run authority record exists to extend. `loop_events` rows are the nearest per-run ledger shape.

### Signatures
- `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None` — the existing shared env-injection helper the projection helper sits beside (`host_runner.py:1882`, signature updated by ENH-3095's `AutomationContext` refactor); the new writer is invoked from the same spawn-time seam.
- The writer itself takes a run identifier plus two `frozenset[str]` name-sets (scopes, variables) and returns `None`. Indicative shape; no value-bearing parameter may exist.

### Call Path
Spawn site (holds run identifier) → `project_child_env()` result (ENH-3233 chokepoint) → scope-record writer → `loop_events` (or new table, per Open Decision #1)

### Decision Rules
- Names only, never values — enforced by test, not convention.
- No record is written for undeclared specs, since there is no scope to report.
- The write must **not** live inside `project_child_env()` itself: it is a pure helper with ~18 call sites, several of which have no run context at all (`worktree_utils.py`, `git_operations.py`, `mcp_call.py`). Invoke the writer from spawn sites that hold a run identifier.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- `_apply_automation_env()` has moved again: now at `host_runner.py:1898-1915` (previously cited 1882 — this section already anticipated drift). Signature confirmed unchanged: `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None`.
- `_apply_automation_env()` and `project_child_env()` are never called from the same call site: `_apply_automation_env()` runs inside each host runner's `build_streaming()` (populating `HostInvocation.env` at build time); `project_child_env()` runs later, in a different function, on the resulting `HostInvocation` (e.g. `subprocess_utils.py:529`, after `build_streaming()` already ran at line 517). They share no call relationship.
- `HostInvocation` (`host_runner.py:156-173`) has 5 fields today (`binary`, `args`, `env`, `capabilities`, `cleanup_paths`) — no `env_allow` field exists yet (ENH-3233 unimplemented). `ActionSpec` (`runner_spec.py:84-95`, drifted from previously-cited 77-89) likewise has no `scopes` field yet (ENH-3234 unimplemented).
- `project_child_env(invocation=None, *, extra=None) -> dict[str, str]` (`host_runner.py:1865-1895`) returns a flat variable-name to value dict with no separate "declared scope name" information, today or under ENH-3233's planned shape — the writer cannot derive scope names from this return value alone. It needs the caller to pass through both name-sets explicitly, which matches this section's existing "the writer itself takes ... two frozenset[str] name-sets" line.
- Call Path correction: the existing "Spawn site (holds run identifier) -> ..." line assumes a run identifier is available at the spawn site. Confirmed: none of `run_claude_command()`, `DefaultActionRunner.run()`, `run_blocking_json()`, or `verify_epic_branch_before_merge()` currently accept or hold a loop/spawn run identifier. `FSMExecutor.run_id` (`fsm/executor.py:570`) is the only genuine run identifier in the chain, set several stack frames above the actual spawn and not threaded down today. See Open Decisions.

## Scope Boundaries

Explicitly **out of scope**:

- **The declaration mechanism itself** — ENH-3203.
- **Spawn-site centralization** — ENH-3184.
- **Retention, pruning, or compaction of the new record.** Per project policy, `raw_events`-style deletion stays a manually-run CLI action; this issue adds no automatic pruning.
- **Any surfacing UI or `ll-*` query command.** Follow-on if wanted.

## Open Decisions

1. **Where does the record land?** A column on the existing `loop_events` ledger, or a new `.ll/history.db` table. `loop_events` is closest; a dedicated table is cleaner if the record is per-spawn rather than per-run.
2. **Per-run or per-spawn granularity?** A single loop run makes many spawns with potentially different declarations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

3. **How does the writer obtain a run/spawn identifier?** No confirmed call site into `project_child_env()`/`_apply_automation_env()` today holds a genuine run identifier (see Program Design → Codebase Research Findings). `FSMExecutor.run_id` exists (`fsm/executor.py:570`) but is not threaded down to `DefaultActionRunner.run()`/`run_claude_command()`/`run_blocking_json()`. Options: (a) thread `run_id` as a new parameter down this call chain to the actual spawn site, or (b) key the record by something already available at the spawn site (e.g. PID via `run_claude_command()`'s existing `on_process_start` callback, or a freshly-generated per-write identifier) instead of `FSMExecutor.run_id`. This is a prerequisite decision, not an implementation detail — it determines whether "per-run" granularity (Open Decision #2) is reachable without a signature change to `DefaultActionRunner.run()`.

## Impact

- **Priority**: P3 — audit value only; no runtime behaviour depends on it, and it is meaningless until ENH-3203 lands.
- **Effort**: Small — one migration, one write path, two tests.
- **Risk**: Low, with one sharp edge: a record that stores values instead of names inverts the issue's purpose. Test for it explicitly.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P3

## Verification Notes (2026-09-03)

- `SCHEMA_VERSION` corrected 45→46; next migration is v47, not v46.
- Re-verified: `SCHEMA_VERSION` still 46 (v47 claim holds). All three `blocked_by` issues (ENH-3233/3234/3235) confirmed open with correct `Blocks` backlinks to this issue. `HostInvocation`/`ActionSpec` field-absence claims (no `env_allow`, no `scopes`), `DefaultActionRunner.run()`'s missing `run_id` param, `_apply_automation_env()`/`project_child_env()` no-shared-call-site claim, and the writer/test precedent citations (`write_advisor_consult`/`write_research_triage`, `TestSchemaV46ResearchTriageEvents`, `TestWriteAdvisorConsult`/`TestWriteResearchTriage`) all confirmed accurate at current line numbers except `ActionSpec` (corrected 77-89 → 84-95 above). No active required decisions-log rules apply. `ll-verify-evidence` reports clean.

## Session Log
- `/ll:verify-issues` - 2026-09-03T20:06:11 - `af073d2f-8e64-47da-8b0b-406331feaae4.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:32:09 - `d28ffd7a-ae9c-48b9-8cda-76e95a2c6507.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
