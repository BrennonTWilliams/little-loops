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
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: false
verify_verdict: VALID
---

# ENH-3204: Record the credential scope a run was granted for after-the-fact audit

## Summary

Nothing anywhere records what authority a given run held. Once a task can declare a credential scope, an audit should be able to answer after the fact what a given run could reach.

Record the declared scope with the run. The record stores **scope and variable *names* only — never values**.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no declaration code has landed yet. The enforcement chokepoint is ENH-3233; the declaration surface this issue records is ENH-3235 (`StateConfig.scopes`, the loop-YAML path). `blocked_by` is ENH-3233 + ENH-3235 only (ENH-3234 dropped 2026-09-04): the record is written from `FSMExecutor`, which never sees an `ActionSpec`. Recording for the `ll-action`/`ll-queue` path is a follow-on once ENH-3234 lands, not a prerequisite.

## Current Behavior

No table, column, or log line records the authority a run held. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped for this.

## Expected Behavior

Each run records the capability and variable names it was granted, queryable after the fact. Names only — a record that could leak a credential value is worse than no record.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` is currently **46** (line 25, re-verified 2026-09-04), so a new migration is **v47**. Confirm the current value before writing the migration; it moves (it already drifted from 40, then 45, since this issue was written).
- `scripts/little_loops/session_store/writers.py` — new `write_credential_scope()` in the `write_research_triage()` shape (fail-soft, names only).
- `scripts/little_loops/fsm/executor.py` — the dispatch call site (`:2495-2505`, immediately before `self.action_runner.run(...)`) is the **write site**: it holds `self.run_id`, the state name, and `state.scopes`. **Not** `host_runner.py` — the projection helper has no run context (see Decision 3, resolved).
  > ⚠ Superseded — wrong call site; real target is `self.action_runner.run(...)` at `:2563-2573`

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestSchemaV47CredentialScopeEvents` mirroring the v46 class (columns, indexes, upgrade-from-46, kind registration, rebuild-exclusion) + bump in `test_schema_version_matches_migrations_length`.
- `scripts/tests/test_session_store_writers.py` — `TestWriteCredentialScope` incl. `test_graceful_when_store_unwritable`.
- **Names-only test**: plant `GH_TOKEN=SENTINEL_VALUE_9f3a` in `os.environ` (monkeypatch), run one declaring state through `FSMExecutor` with a mock runner, then assert `SENTINEL_VALUE_9f3a` appears nowhere in the raw bytes of the written row (`SELECT * FROM credential_scope_events` serialized via `json.dumps`). The writer signature makes this structurally impossible (it takes only name-sets), but the test guards against a future "helpful" refactor.
- Executor test: an undeclared state writes no row; a declaring state writes exactly one row per dispatch with the correct `run_id`/`state`/`scopes`.

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- **Shared dispatch fixture.** The corrected write site (`fsm/executor.py:2563-2573`,
  `self.action_runner.run(...)`, the default/else branch — not the `_contributed_actions`
  branch at 2486-2505) is covered by one shared test double, `MockActionRunner`
  (`scripts/tests/test_fsm_executor.py:47-138`, used at 60+ call sites). **ENH-3235 wires
  `scopes=` into the same call site and the same fixture** — if ENH-3235 lands first and
  already added a `scopes` capture list to `MockActionRunner`, reuse it for this issue's
  executor test rather than adding a parallel one.

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
- `write_credential_scope(db_path: Path | str, *, run_id: str, state: str, scopes: frozenset[str], var_names: frozenset[str], ts: str | None = None) -> bool` — takes a **`db_path`**, not a store handle, matching `write_research_triage()`/`write_advisor_consult()` (`writers.py:1898`, `1823`); returns `False` on `sqlite3.Error`. No value-bearing parameter may exist. (Corrected 2026-09-06: earlier text wrote `write_credential_scope(store, ...)`.) The executor resolves the path the way the per-state `record_prepatch_evidence(_history_db, ...)` call does (`fsm/executor.py:1977`) — do not open a persistent store handle at dispatch.
- **`var_names` is the *effective* granted set**, not only the registry resolution: it must include every key ENH-3205 injects via `extra=` (`GH_TOKEN`, `GH_CONFIG_DIR`) and the `LL_PYTHON` extra, so the audit row reports what the child could actually reach. Practically: the shell-branch helper that builds `(env_allow, extra)` from `scopes` returns the resolved names, and the executor records `resolve_scopes(scopes) | extra.keys()`. Baseline names are *not* recorded (they are constant and non-credential; recording them adds noise, not audit value).

### Call Path
`FSMExecutor` dispatch (`fsm/executor.py:2563-2573`, holds `self.run_id` + `state.name` + `state.scopes`) → `resolve_scopes(state.scopes)` (ENH-3233's pure registry function → `frozenset[str]` of var names) plus the injected `extra` keys (ENH-3205) → `write_credential_scope(db_path, run_id=..., state=..., scopes=..., var_names=...)` → new `credential_scope_events` table (v47) → `self.action_runner.run(..., scopes=state.scopes)` proceeds as ENH-3235 wires it.

Ordering caveat: the executor writes *before* the spawn, but `GH_TOKEN`/`GH_CONFIG_DIR` are added inside the runner's shell branch. Either the executor derives the same injected-name set from `scopes` via a shared pure helper (preferred — a `scope_injected_names(scopes) -> frozenset[str]` beside the registry, no tempdir needed to know the *names*), or the runner returns them on `ActionResult` and the write moves after the spawn. Prefer the former; the record must describe the grant, not the outcome.

The write happens *before* the spawn and independently of it — the record says what the state was granted, which is fully determined by the declaration, not by anything the child does.

### Decision Rules
- Names only, never values — enforced by test, not convention.
- No record is written for undeclared states (`state.scopes is None`), since there is no scope to report.
- The write must **not** live inside `project_child_env()` itself: it is a pure helper with ~18 call sites, several of which have no run context at all (`worktree_utils.py`, `git_operations.py`, `mcp_call.py`). It also must not live in `fsm/runners.py` — the runner has no `run_id` either. The executor is the only frame that holds both the run identity and the declaration.
- Writer is fail-soft (`try/except sqlite3.Error: logger.warning(...); return False`) — an audit write must never fail a loop run.

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

## Decisions (resolved 2026-09-04, pre-implementation epic review)

1. **Where does the record land?** — **New table `credential_scope_events`** in `.ll/history.db`, migration v47, following the `research_triage_events` (v46) shape: `id`, `run_id`, `state`, `ts`, `scopes` (JSON array of scope names), `var_names` (JSON array of env-var names), with an index on `run_id`. Not a `loop_events` column: the record is per-dispatch, and `loop_events` is per-run.
2. **Per-run or per-spawn granularity?** — **Per-dispatch** (one row per declaring state execution). Falls out of Decision 3: the executor writes at each dispatch, so a run that re-enters a state N times gets N rows, each stamped with the same `run_id`. Per-run views are a `GROUP BY run_id` away.
3. **How does the writer obtain a run identifier?** — **Write from `FSMExecutor` at dispatch** (`fsm/executor.py:2495-2505`), where `self.run_id` (`:575`), `state.name`, and `state.scopes` (ENH-3235) all already exist. Neither option previously listed is needed: no `run_id` parameter is threaded down through `ActionRunner.run()`/`run_claude_command()`, and no PID keying. The executor already writes `run_id`-stamped rows at archive time (`:4031`, `:4060`), so the store handle and pattern are in scope there. Consequence: this issue covers the loop-YAML path only; `ll-action`/`ll-queue` recording is a follow-on after ENH-3234 (no run identity exists on that path today).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis (retained; superseded by Decision 3 above):_

- No confirmed call site into `project_child_env()`/`_apply_automation_env()` holds a genuine run identifier; `FSMExecutor.run_id` (`fsm/executor.py:575`) is the only one in the chain. This is why the write moved up to the executor rather than down to a spawn site.

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

## Review Notes (2026-09-04, pre-implementation epic review)

- All three Open Decisions resolved (new v47 table; per-dispatch; write from `FSMExecutor` at
  dispatch). `decision_needed` flipped to `false`.
- `blocked_by` narrowed to ENH-3233 + ENH-3235; ENH-3234 removed (executor path never sees an
  `ActionSpec`). ENH-3234's `## Blocks` updated to match.
- Files to Modify corrected: write site is `fsm/executor.py`, not `host_runner.py`.
- Tests section made concrete, including the names-only sentinel test.

## Review Notes (2026-09-06, pre-implementation cross-issue review)

- Writer signature corrected to take `db_path` (sibling-writer convention), resolved per state
  like `record_prepatch_evidence`; no persistent store handle at dispatch.
- `var_names` pinned as the *effective* granted set including ENH-3205's injected `GH_TOKEN`/
  `GH_CONFIG_DIR` and `LL_PYTHON`, derived via a shared pure name helper so the pre-spawn write
  stays a record of the grant.
- Call Path citation updated to the corrected dispatch site (`:2563-2573`).

## Session Log
- `/ll:wire-issue` - 2026-09-07T03:48:29 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:06:11 - `af073d2f-8e64-47da-8b0b-406331feaae4.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:32:09 - `d28ffd7a-ae9c-48b9-8cda-76e95a2c6507.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
