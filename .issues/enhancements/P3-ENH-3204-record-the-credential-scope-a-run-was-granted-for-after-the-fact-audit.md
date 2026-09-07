---
id: ENH-3204
type: ENH
title: Record the credential scope a run was granted for after-the-fact audit
priority: P3
status: done
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3395
- ENH-3396
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
completed_at: '2026-09-07T22:18:14Z'
testable: true
decision_needed: false
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# ENH-3204: Record the credential scope a run was granted for after-the-fact audit

## Summary

Nothing anywhere records what authority a given run held. Once a task can declare a credential scope, an audit should be able to answer after the fact what a given run could reach.

Record the declared scope with the run. The record stores **scope and variable *names* only — never values**.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no declaration code has landed yet. The enforcement chokepoint is ENH-3233; the declaration surface this issue records is ENH-3235 (`StateConfig.scopes`, the loop-YAML path). `blocked_by` is ENH-3233 + ENH-3235 only (ENH-3234 dropped 2026-09-04): the record is written from `FSMExecutor`, which never sees an `ActionSpec`. Recording for the `ll-action`/`ll-queue` path is a follow-on once ENH-3234 lands, not a prerequisite.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Blockers landed** (2026-09-07): all three `blocked_by` issues are now `status: done` — ENH-3395 (deny-by-default env projection chokepoint), ENH-3396 (credential-scope registry / `resolve_scopes()`), ENH-3235 (`StateConfig.scopes` declaration + `fsm/runners.py` wiring, commit `1eef27f5e`). The declaration surface this issue was waiting on now exists end-to-end: `FSMExecutor` dispatch (`fsm/executor.py:2563-2578`) passes `scopes=state.scopes` into `DefaultActionRunner.run()`, which resolves it via `resolve_scopes()` (`host_runner.py:166`) into an `env_allow` set consumed by `project_child_env()` (`host_runner.py:2027`). This issue is unblocked.

## Current Behavior

No table, column, or log line records the authority a run held. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped for this.

## Expected Behavior

Each run records the capability and variable names it was granted, queryable after the fact. Names only — a record that could leak a credential value is worse than no record.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

**Option A**: Treat `LL_PYTHON` as baseline and exclude it from `var_names` — consistent with `_is_baseline_allowed()`'s classification (prefix `"LL_"`, non-credential-shaped) and with this issue's own Decision Rules ("Baseline names are not recorded"). `var_names` = `resolve_scopes(state.scopes)` only (plus `GH_TOKEN`/`GH_CONFIG_DIR` once ENH-3205 lands, gated the same way).

> **Selected:** Option A — reuses `_is_baseline_allowed()` unchanged and matches the debug-deny-log precedent (baseline names never named in a name-only report); Option B invents a new "reachable via any mechanism" inclusion criterion with no codebase precedent.

**Option B**: Record `LL_PYTHON` in `var_names` anyway, because it reaches the child via unconditional `extra=` injection — the same mechanism ENH-3205's `GH_TOKEN`/`GH_CONFIG_DIR` will use — not via the baseline ambient-env allow/deny path `_is_baseline_allowed()` governs. The audit record's purpose is "what could the child actually reach," and `LL_PYTHON` is reachable regardless of scope declaration.

**Recommended**: Option A — `_is_baseline_allowed()` is the codebase's own definition of "non-credential, always-present," and `LL_PYTHON`'s value (a Python interpreter path) carries no audit value; recording it on every single row adds noise without adding to what an auditor needs to answer ("what credential-shaped authority did this run hold").

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-07.

**Selected**: Option A — exclude `LL_PYTHON` from `var_names`

**Reasoning**: `_is_baseline_allowed()` (`host_runner.py:2020-2024`) already classifies `LL_PYTHON` as baseline (prefix `"LL_"`, fails `_CREDENTIAL_SHAPE_RE`), and the codebase's one existing name-only audit precedent — the DEBUG `denied` log at `host_runner.py:2112` — never names baseline-classified vars. `LL_PYTHON` is constant across every dispatch, so recording it on every row adds no differentiating audit signal. Option B's "reachable via `extra=`" inclusion criterion has no precedent anywhere in the codebase and directly contradicts this issue's own Decision Rules ("Baseline names are not recorded").

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Evidence for the selected approach: `_is_baseline_allowed()` (`host_runner.py:2002-2024`) classifies `LL_PYTHON` as baseline by prefix + non-credential shape; the existing `denied`-names debug log (`:2112`) already excludes baseline names from its name-only report, the closest codebase precedent for this exact question.
- Evidence against the rejected approach: `extra={"LL_PYTHON": sys.executable}` (`fsm/runners.py:334`) reaches the child unfiltered by `_is_baseline_allowed()`, but no code or doc anywhere treats "delivered via `extra=`" as an audit-inclusion rule — it would be a new criterion invented for this issue alone, and it directly conflicts with the issue's own stated Decision Rules.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` is currently **46** (line 25, re-verified 2026-09-04), so a new migration is **v47**. Confirm the current value before writing the migration; it moves (it already drifted from 40, then 45, since this issue was written).
- `scripts/little_loops/session_store/writers.py` — new `write_credential_scope()` in the `write_research_triage()` shape (fail-soft, names only).
- `scripts/little_loops/fsm/executor.py` — the dispatch call site (`:2495-2505`, immediately before `self.action_runner.run(...)`) is the **write site**: it holds `self.run_id`, the state name, and `state.scopes`. **Not** `host_runner.py` — the projection helper has no run context (see Decision 3, resolved).
  > ⚠ Superseded — wrong call site; real target is `self.action_runner.run(...)` at `:2563-2573`

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- `scripts/little_loops/session_store/schema.py` — add `"credential_scope"` to the `VALID_KINDS` tuple (line 27-53) and `"credential_scope": "credential_scope_events"` to the `_KIND_TABLE` dict (line 55-81), alongside the `"advisor_consult"`/`"research_triage"` sibling entries. **Required**: `scripts/little_loops/cli/verify_kinds.py` fails any `CREATE TABLE` not registered in `_KIND_TABLE` or `_KINDLESS_TABLES` (gated by `scripts/tests/test_verify_kinds.py`). `_KIND_TABLE` registration (not `_KINDLESS_TABLES`, which is for tables with no per-session "recent" concept — see `prepatch_evidence`'s ENH-2997 rationale) is the right branch here: it makes the record `ll-session recent --kind credential_scope`-queryable via the existing generic dispatch with zero new UI code, directly satisfying this issue's own Expected Behavior ("queryable after the fact") without conflicting with the Scope Boundary excluding *new* surfacing commands.
- `scripts/little_loops/session_store/__init__.py` — add `write_credential_scope` to the `.writers` import block (line 166-168) and to `__all__` (line 236-237), matching `write_research_triage`/`write_advisor_consult`.
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate after the v47 migration lands via the documented snippet in `TestSchemaManifest`'s docstring (`scripts/tests/test_session_store_schema.py:2786-2803`); `test_schema_manifest_matches_checked_in_file` (`:2808`) fails on a stale manifest.
- **Open, deferrable sub-decision**: whether to also register `"credential_scope_event": ("credential_scope_events", "ts")` in `_EXPORT_TABLE_MAP` (`session_store/queries.py:89-111`), which backs the generic `ll-session export --tables` / `ll-artifact dashboard --tables` mechanism. If added, it must **also** go into `_EXPORT_DEFAULT_TABLES` (`queries.py:113-134`) — `test_session_store_queries.py`'s `test_message_event_is_the_only_non_default_table` (line 212-223) pins `set(_EXPORT_TABLE_MAP) - set(_EXPORT_DEFAULT_TABLES) == {"message_event"}` as the only exception. Recommend **deferring** this registration: it is optional export surface, not required by the `verify_kinds` gate or by "queryable after the fact" (already satisfied by `_KIND_TABLE`), and adding it pulls in a documentation update (`docs/guides/HISTORY_SESSION_GUIDE.md` § Export tables as JSONL) and a new `test_session_store_queries.py` test class. Leaving it unregistered means `credential_scope_events` is simply absent from export/dashboard output — no test breaks either way as long as it's registered in neither dict, or in both.

### Documentation

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- `docs/ARCHITECTURE.md` § Event Emitters — the schema-migration table (starts ~line 638) has rows through `v45 | advisor_consults` (line 678) and `v46 | research_triage_events` (line 679); add a `v47 | credential_scope_events | ...` row in the same shape.
- `docs/guides/HISTORY_SESSION_GUIDE.md` § What Gets Recorded — the table enumerating every session_store table (starts ~line 112) has rows for `advisor_consults` (line 145) and `research_triage_events` (line 146), each noting "Live-write-only... excluded from `rebuild()`"; add a matching `credential_scope_events` row describing the `run_id`/`state`/`scopes`/`var_names` shape.
- `docs/reference/API.md` § `little_loops.session_store` — the writer import list (~line 9412-9448) includes `write_advisor_consult` (line 9442); add `write_credential_scope` alongside it.
- `docs/reference/CLI.md` § `ll-session recent --kind` choices (line 3773) — this list is already stale (missing `review`/`advisor_consult`/`research_triage`); if `credential_scope` is registered in `_KIND_TABLE` per the Files to Modify entry above, add it here too rather than compounding the drift, though fully repairing the other three missing entries is outside this issue's scope.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register `"credential_scope"` in `VALID_KINDS` + `_KIND_TABLE` (`session_store/schema.py`) — required by the `ll-verify-kinds` gate; also the mechanism that satisfies "queryable after the fact" for free.
- Add `write_credential_scope` to `session_store/__init__.py`'s import block and `__all__`.
- Regenerate `session_store/schema_manifest.json` after the v47 migration DDL is appended.
- Update `docs/ARCHITECTURE.md` and `docs/guides/HISTORY_SESSION_GUIDE.md` event/table listings.
- Decide (and, if yes, implement) `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES` registration; default recommendation is to skip it for this issue.
- Write the executor test against `patch("little_loops.session_store.write_credential_scope")` (mirroring the fail-soft pattern at `scripts/tests/test_fsm_executor.py:3594-3626` and `:3676-3714` for `record_loop_run_summary`/`record_usage_event`, including a `side_effect=RuntimeError` "write failure doesn't fail the run" case) — **not** `MockActionRunner.scopes_seen`, which only captures the `scopes=` kwarg passed to `action_runner.run()` and never touches the session_store write (see superseded marker in Tests above).

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestSchemaV47CredentialScopeEvents` mirroring the v46 class (columns, indexes, upgrade-from-46, kind registration, rebuild-exclusion) + bump in `test_schema_version_matches_migrations_length`.
- `scripts/tests/test_session_store_writers.py` — `TestWriteCredentialScope` incl. `test_graceful_when_store_unwritable`.
- **Names-only test**: plant `GH_TOKEN=SENTINEL_VALUE_9f3a` in `os.environ` (monkeypatch), run one declaring state through `FSMExecutor` with a mock runner, then assert `SENTINEL_VALUE_9f3a` appears nowhere in the raw bytes of the written row (`SELECT * FROM credential_scope_events` serialized via `json.dumps`). The writer signature makes this structurally impossible (it takes only name-sets), but the test guards against a future "helpful" refactor.
- Executor test: an undeclared state writes no row; a declaring state writes exactly one row per dispatch with the correct `run_id`/`state`/`scopes`.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- **Executor test, corrected approach**: patch `little_loops.session_store.write_credential_scope` and assert its call args (`run_id`/`state`/`scopes`/`var_names`), plus a `side_effect=RuntimeError` variant proving the write is best-effort — mirror `test_fsm_executor.py:3594-3626`/`:3676-3714` (`record_loop_run_summary`/`record_usage_event`). `MockActionRunner.scopes_seen` only captures the `scopes=` kwarg threaded to `action_runner.run()`; it never exercises the session_store write and cannot substitute for this test.
- `scripts/tests/test_verify_kinds.py::TestRun::test_clean_state_returns_zero` and `scripts/tests/test_session_store_schema.py:1015` (`assert set(VALID_KINDS) == set(_KIND_TABLE.keys())`) are generic, live-schema assertions — they auto-cover the new `credential_scope` entry once registered; no edit needed to either, but the `VALID_KINDS`/`_KIND_TABLE` registration itself (Files to Modify, above) is what makes them pass.
- No existing DB-row-based "secret value absent from a persisted row" helper exists anywhere in `scripts/tests/` to reuse (closest precedents — `test_host_runner.py:227-234`, `test_runner_spec.py:220-235` — assert against `caplog`/subprocess `stdout`, not a DB row); the names-only sentinel test above is genuinely new, not a duplicate of existing coverage.

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- **Shared dispatch fixture.** The corrected write site (`fsm/executor.py:2563-2573`,
  `self.action_runner.run(...)`, the default/else branch — not the `_contributed_actions`
  branch at 2486-2505) is covered by one shared test double, `MockActionRunner`
  (`scripts/tests/test_fsm_executor.py:47-138`, used at 60+ call sites). **ENH-3235 wires
  `scopes=` into the same call site and the same fixture** — if ENH-3235 lands first and
  already added a `scopes` capture list to `MockActionRunner`, reuse it for this issue's
  executor test rather than adding a parallel one.
  > ⚠ Superseded — scopes_seen doesn't capture the session_store write

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Spawn-site audit (2026-09-03): none of the 8 confirmed call sites into `project_child_env()`/`_apply_automation_env()` currently hold a genuine loop/spawn run identifier. The 6 `build_streaming()` methods (`host_runner.py:410,718,1127,1319,1515,1715`) are pure `HostInvocation`-construction factories with no run_id parameter; `run_blocking_json()` (`host_runner.py:2178`) and `verify_epic_branch_before_merge()` (`worktree_utils.py:721`) hold no loop-run context either. `FSMExecutor.run_id` (set at `fsm/executor.py:570`) is the nearest genuine run identifier, several stack frames above the actual spawn — it is not threaded down as a parameter today. See Open Decisions.
- `subprocess_utils.run_claude_command()` (`subprocess_utils.py:422-445`) is the site closest to holding both a spawn context and the actual PID: it calls `project_child_env(invocation, extra=extra_env)` at line 529, then `subprocess.Popen(...)` at line 534-543 in the same function — but its signature has no `run_id` param, only `extra_env` and an `on_process_start` callback invoked with the live `Popen`.
- Candidate writer-function siblings already in this codebase: `write_advisor_consult()` (`session_store/writers.py:1823-1897`) and `write_research_triage()` (`session_store/writers.py:1898-1942`) — both new-dedicated-table, live-write-only, fail-soft (`try/except sqlite3.Error: logger.warning(...); return False`) writers; a scope-record writer would follow this same shape.
- Tests: migration test class shape is `TestSchemaV46ResearchTriageEvents` (`scripts/tests/test_session_store_schema.py:2653-2751` — columns, indexes, CHECK-constraint rejection, upgrade-from-prior-version, kind registration, rebuild-exclusion) and `test_schema_version_matches_migrations_length()` (`test_session_store_schema.py:2132`), both needing a v47 counterpart. Writer test shape is `TestWriteResearchTriage`/`TestWriteAdvisorConsult` (`test_session_store_writers.py:2712-2858`), including a `test_graceful_when_store_unwritable` fail-soft case.
- No existing runtime helper or test enforces "value never leaks" anywhere in this codebase — `pii.py`/`redact_pii()` targets SFT-corpus text (email/phone/SSN), not env-var credentials, and no test of the form "assert secret value not in serialized record" exists today. The "names only" test this issue requires has no precedent to follow.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- Schema migrations in this codebase are not separate "migration functions" — `_MIGRATIONS` (`session_store/schema.py:122`) is a flat, ordered `list[str]` of raw DDL; `SCHEMA_VERSION` (`:25`) must equal `len(_MIGRATIONS)` (asserted directly in sibling tests). Adding v47 means: append one DDL string to `_MIGRATIONS`, bump `SCHEMA_VERSION` to 47.
- `scripts/tests/test_fsm_executor.py`'s shared `MockActionRunner` (`:48-102`) already has the capture point this issue's executor test needs: `scopes: list[str] | None = None` param (`:72`) and `scopes_seen: list[...] = field(default_factory=list)` (`:60`), appended unconditionally on every `.run()` call (`:98`) — the same mechanism as `working_dirs`/`timeouts`/`calls`. A new test asserting "one row per dispatch of a declaring state" reads `runner.scopes_seen` rather than adding new capture machinery.
- The writer's `test_graceful_when_store_unwritable` precedent (`TestWriteAdvisorConsult`/`TestWriteResearchTriage`, `test_session_store_writers.py:2778`/`:2843`) monkeypatches the package-level re-export `little_loops.session_store.connect` (not `writers._pkg.connect`) to raise `sqlite3.OperationalError`, then asserts the writer returns `False`.
- `self.run_id` is assigned at `fsm/executor.py:622` (`derive_run_id(...)`, inside `run()`, before its dispatch loop) — corrects the line numbers cited elsewhere in this issue (570/575), which have drifted.
- JSON-array columns in this codebase follow a `<field>_json TEXT` naming convention (e.g. `files_json`, `failing_names_json` — `writers.py:861`, `:986-1003`), written via `json.dumps(...)` at the writer call site; `session_store` never deserializes its own JSON columns — callers `json.loads()` at the read site. Decision 1's proposed `scopes`/`var_names` column names should likely be `scopes_json`/`var_names_json` to match.

## Program Design

### Types
- No existing per-run authority record exists to extend. `loop_events` rows are the nearest per-run ledger shape.

### Signatures
- `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None` — the existing shared env-injection helper the projection helper sits beside (`host_runner.py:1882`, signature updated by ENH-3095's `AutomationContext` refactor); the new writer is invoked from the same spawn-time seam.
- `write_credential_scope(db_path: Path | str, *, run_id: str, state: str, scopes: frozenset[str], var_names: frozenset[str], ts: str | None = None) -> bool` — takes a **`db_path`**, not a store handle, matching `write_research_triage()`/`write_advisor_consult()` (`writers.py:1898`, `1823`); returns `False` on `sqlite3.Error`. No value-bearing parameter may exist. (Corrected 2026-09-06: earlier text wrote `write_credential_scope(store, ...)`.) The executor resolves the path the way the per-state `record_prepatch_evidence(_history_db, ...)` call does (`fsm/executor.py:1977`) — do not open a persistent store handle at dispatch.
- **`var_names` is the *effective* granted set**, not only the registry resolution: it must include every credential-shaped key ENH-3205 injects via `extra=` (`GH_TOKEN`, `GH_CONFIG_DIR`), so the audit row reports what credential-shaped authority the child was granted. **Decided 2026-09-07 (Option A — see Proposed Solution → Decision Rationale): `LL_PYTHON` is excluded** — `_is_baseline_allowed()` classifies it as baseline (non-credential, always-present), matching this section's own Decision Rules. Practically: the shell-branch helper that builds `(env_allow, extra)` from `scopes` returns the resolved names, and the executor records `resolve_scopes(scopes) | {k for k in extra if not _is_baseline_allowed(k)}`. Baseline names are *not* recorded (they are constant and non-credential; recording them adds noise, not audit value).

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

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- `LL_PYTHON` is injected unconditionally in the shell branch (`fsm/runners.py:334`, `extra={"LL_PYTHON": sys.executable}`) — independent of `scopes`'s value, not derived from scope resolution. Per `host_runner.py`'s `_is_baseline_allowed()` (prefix `"LL_"` + fails the credential-shape regex), `LL_PYTHON` classifies as a **baseline** name — excluded from `var_names` per the resolved decision (Proposed Solution → Decision Rationale, Option A selected 2026-09-07).
- ENH-3205 (the source of `GH_TOKEN`/`GH_CONFIG_DIR`) is still `status: open` — no code path today injects either name via `extra=`. The "`var_names` must include GH_TOKEN/GH_CONFIG_DIR" clause is forward-looking, not currently testable; today's effective formula is `resolve_scopes(state.scopes) | {"LL_PYTHON"}` (the second term hardcoded, not scope-derived).
- No test in `test_session_store_writers.py`/`test_session_store_schema.py` currently asserts a value-string's absence from a persisted DB row; the closest existing "names only, never values" test precedent (`test_ac6_denied_names_logged_at_debug`, `test_host_runner.py:227-234`) operates on `caplog.text`, not a session_store row. This issue's names-only test has no direct DB-row precedent to follow, confirming the issue's own claim at line 70.

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

## Resolution

Implemented 2026-09-07. v47 migration adds `credential_scope_events` (`session_store/schema.py`),
`write_credential_scope()` (`session_store/writers.py`), re-exported via `session_store/__init__.py`.
`FSMExecutor` writes one fail-soft row per declaring-state dispatch immediately before the spawn
(`fsm/executor.py`, gated on `state.scopes is not None`), recording `resolve_scopes(state.scopes)`
as `var_names` — `LL_PYTHON` excluded per Option A. `schema_manifest.json` regenerated; `ARCHITECTURE.md`,
`HISTORY_SESSION_GUIDE.md`, `API.md`, `CLI.md` updated. Tests: `TestSchemaV47CredentialScopeEvents`,
`TestWriteCredentialScope`, `TestCredentialScopeAudit` (incl. a names-only sentinel test proving no
credential value reaches the row). `_EXPORT_TABLE_MAP` registration deferred per the issue's own
recommendation. As a side effect, fixed two other test suites whose hardcoded `SCHEMA_VERSION == 46`
assertions and a stale line-number allowlist (`test_issue_parser.py`) drifted from this migration.

## Status

**Done** | Created: 2026-08-15 | Priority: P3

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-07_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Decision Cap (ENH-3256): `unapplied_decision` flagged "Program Design still specifies `extra=` (rejected option)" — the Call Path's "plus the injected `extra` keys (ENH-3205)" phrase collides on the `extra=` identifier with rejected Option B's inclusion criterion. Likely a text-overlap false positive (Option B was about recording `LL_PYTHON`, not about the `extra=` mechanism used for `GH_TOKEN`/`GH_CONFIG_DIR`), but caps Criterion C (Ambiguity) at 10 per the gate's own rules. Worth a one-line rewording of the Call Path sentence to drop the bare `extra=` token before implementation, though not blocking.
- Moderate breadth: ~9 distinct change sites (5 code: schema.py, writers.py, executor.py, `__init__.py`, schema_manifest.json regen; 4 doc: ARCHITECTURE.md, HISTORY_SESSION_GUIDE.md, API.md, CLI.md) — mostly mechanical/local per-site, but the count itself lands in the 6-15 "broad" Breadth band.

## Session Log
- `/ll:manage-issue` - 2026-09-07T22:18:14 - `e908c531-4aff-4082-8917-bbb395c857bc.jsonl`
- `/ll:ready-issue` - 2026-09-07T21:59:06 - `28800794-0f5a-4fe8-994e-1989ac72bc83.jsonl`
- `/ll:confidence-check` - 2026-09-07T21:57:02 - `d460e1ad-ce21-49f9-a8ef-58d4aa04e9ff.jsonl`
- `/ll:verify-issues` - 2026-09-07T21:54:17 - `b677110a-ebf1-4560-85d2-9ce07099ddfa.jsonl`
- `/ll:wire-issue` - 2026-09-07T21:52:31 - `3228b131-d6b8-4b25-8749-92916f0668ba.jsonl`
- `/ll:decide-issue` - 2026-09-07T21:42:58 - `5606654e-8187-43bc-9b89-feee2fac8d80.jsonl`
- `/ll:refine-issue` - 2026-09-07T21:36:50 - `200bbfae-4b5d-4fcf-a183-eb7cc4cf633b.jsonl`
- `/ll:wire-issue` - 2026-09-07T03:48:29 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:06:11 - `af073d2f-8e64-47da-8b0b-406331feaae4.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:32:09 - `d28ffd7a-ae9c-48b9-8cda-76e95a2c6507.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
