---
id: BUG-1995
type: BUG
priority: P2
status: open
captured_at: '2026-06-07T01:32:37Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
labels:
- testing
- session-store
- isolation
confidence_score: 100
outcome_confidence: 80
decision_needed: false
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 20
---

# BUG-1995: pytest opens the real `.ll/history.db` instead of an isolated temp DB

## Summary

During the investigation of the `ll-issues` "table tool_events already exists"
crash, `lsof .ll/history.db` showed **two live `python -m pytest` processes
holding the project's real `.ll/history.db` open** (FDs `11u`/`12r`/`13u`),
alongside the expected `ll-loop` and `ll-auto` runs. Tests should never touch
the real per-project database — some code path or fixture exercised during the
suite opens `DEFAULT_DB_PATH` (`.ll/history.db`) rather than a `tmp_path`-scoped
file.

## Current Behavior

Running `python -m pytest scripts/tests/` opens and holds a connection to the
real `.ll/history.db`. This both **pollutes real session history** with
test-generated rows and **contributes to lock contention** against concurrent
`ll-*` processes (it was one of four processes locking the DB at crash time).

## Expected Behavior

The test suite must be fully isolated from the real project database. No pytest
process should ever open `.ll/history.db`; every test that touches the session
store should write to a `tmp_path`-scoped DB (most already pass an explicit
`db` path — the gap is the code path that defaults to `DEFAULT_DB_PATH`).

## Motivation

- **Data integrity**: test runs silently injecting rows into the real history DB
  corrupts analytics (`ll-history`, `ll-ctx-stats`, correction mining, SFT corpus).
- **Concurrency**: a stray test connection widens the lock-contention window that
  produced the original `ll-issues` crash (see Related).
- **Reproducibility**: tests that read shared state are order-dependent and flaky.

## Steps to Reproduce

1. Start a test run: `python -m pytest scripts/tests/ -q`
2. While it runs, in another shell: `lsof .ll/history.db`
3. Observe one or more `python` (pytest) processes holding the real DB open.

## Root Cause

**Confirmed (candidate #2 below).** The unscoped open is the
`cli_event_context(DEFAULT_DB_PATH, ...)` wrapper that nearly every `ll-*` CLI
`main()` opens around its body, invoked **in-process** by `TestMain*` tests that
do not `monkeypatch.chdir(tmp_path)`. Because `DEFAULT_DB_PATH = Path(".ll/history.db")`
(`scripts/little_loops/session_store.py:76`) is **relative**, it resolves against
the test-process CWD — the repo root during `pytest` — i.e. the real
`.ll/history.db`.

Original candidate hypotheses (kept for context):

- A fixture or test that calls `connect()` / `ensure_db()` / `SQLiteTransport()`
  / `cli_event_context()` / `backfill*()` with no `db_path`, so it defaults to
  `DEFAULT_DB_PATH = .ll/history.db` (`scripts/little_loops/session_store.py`).
- Code-under-test that resolves `DEFAULT_DB_PATH` relative to the CWD instead of
  accepting an injected path, invoked by a test without monkeypatching CWD or the
  default. **← confirmed root cause**
- A hook handler test (e.g. `session_start`) that runs the real hook against the
  project root.

### Confirmed Root Cause

_Added by `/ll:refine-issue` — empirical probe (a temporary pytest plugin that
wrapped `session_store.connect`/`ensure_db` and recorded any open whose resolved
path equalled the real `.ll/history.db`, run across the full suite):_

- **304 tests** open the real `.ll/history.db` during a single
  `python -m pytest scripts/tests/` run.
- **100% of opens use the relative path `.ll/history.db`** (not an absolute or
  tmp path) — confirming the relative-`DEFAULT_DB_PATH` + repo-root-CWD mechanism.
- **Exact call site**: `cli_event_context()` at
  `scripts/little_loops/session_store.py:644-679`. It calls `connect(db_path)`
  (default `DEFAULT_DB_PATH`) on enter and **INSERTs a `cli_events` row + commits**,
  so every wrapped `main()` writes to the DB even for read-only commands.
- **Entry vector**: `with cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:]):`
  wraps **28 CLI `main()` functions** under `scripts/little_loops/cli/` (e.g.
  `action.py:191`, `cli.py`, `docs.py`, `deps.py`, `sync.py`, `session.py`, …).
  `TestMain*` tests call these in-process without chdir.
- **Top offending test files**: `test_cli.py` (60), `test_dependency_mapper.py`
  (34), `test_cli_docs.py` (28), `test_cli_decisions.py` (22),
  `test_history_context_cli.py` (17), `test_cli_doctor.py` (17),
  `test_cli_sync.py` (15), `test_cli_learning_tests.py` (13), … (~30 files total).
- **No isolation fixture exists**: `scripts/tests/conftest.py` (382 lines) has no
  autouse DB-isolation or CWD-pinning fixture.

> ⚠ **Fix constraint (important):** Proposed-Solution option 2 as written
> ("monkeypatch `little_loops.session_store.DEFAULT_DB_PATH`") will **not** redirect
> these 28 sites. Each CLI module does `from ...session_store import DEFAULT_DB_PATH`,
> binding its own module-level reference at import time and passing that name into
> `cli_event_context`. Patching the attribute on `session_store` after import does
> not rebind the copies the CLI modules already hold. `cli_event_context` also honors
> **no env-var override**. See Proposed Solution for fixes that actually reach all sites.

Investigation: `grep -rn "DEFAULT_DB_PATH\|history.db" scripts/tests/` and audit
any session_store entry point called without an explicit `db`/`db_path` argument.

## Proposed Solution

1. Identify the unscoped call site(s) via `lsof` + grep audit above.
2. Either pass an explicit `tmp_path` DB everywhere, or add an autouse fixture in
   `scripts/tests/conftest.py` that monkeypatches
   `little_loops.session_store.DEFAULT_DB_PATH` (and any hook-resolved default)
   to a `tmp_path` location for the whole session, so a missed explicit arg can
   never escape to the real DB.
3. Add a guard test asserting `.ll/history.db` is not opened during the suite
   (e.g. assert the real file's mtime/size is unchanged across a representative
   test, or that `DEFAULT_DB_PATH` points outside the repo during tests).

### Codebase Research Findings

_Added by `/ll:refine-issue` — the probe (see Confirmed Root Cause) shows a single
mechanism behind all 304 opens, so a single-point fix is achievable. Step 2 above is
**insufficient alone** (see Root Cause fix-constraint note). Three approaches that
actually reach all 28 CLI sites — pick one:_

**Option A — env-var resolution in `cli_event_context` (recommended, single source change).**
> **Selected:** Option A — env-var resolution in `cli_event_context` — matches established `LL_*` env-var override convention (LL_HOST_CLI, LL_HOOK_HOST, LL_STATE_DIR); single-point fix at `session_store.py:644`; survives the import-binding problem; adds a real product feature (LL_HISTORY_DB).
Have `session_store.cli_event_context` resolve its DB path at call time from an env
var (e.g. `LL_HISTORY_DB`) when the caller passes the default, falling back to
`DEFAULT_DB_PATH`. Then an autouse `conftest.py` fixture sets
`os.environ["LL_HISTORY_DB"] = str(tmp_path / "history.db")` (session- or
function-scoped). Fixes all 28 sites at one resolution point, survives the
import-binding problem, and gives a real product feature (overridable DB location).
Pairs naturally with the regression guard.

**Option B — autouse `monkeypatch.chdir(tmp_path)` in `conftest.py`.**
Since the leak is the *relative* path resolving against repo-root CWD, pinning CWD
to a temp dir neutralizes it. **Risk:** many `TestMain*` tests rely on CWD = repo
root to read `agents/`, `skills/`, `commands/` (e.g. `test_adapt_agents_for_codex.py`,
`test_adapt_skills_for_codex.py`, `test_cli_docs.py`). A blanket autouse chdir would
break those; would need an opt-out marker or scoping. Lower-confidence.

**Option C — patch `DEFAULT_DB_PATH` in every CLI module namespace.**
An autouse fixture loops the 28 `little_loops.cli.*` modules and
`monkeypatch.setattr(mod, "DEFAULT_DB_PATH", tmp_db)`. Works but brittle: the module
list must be maintained, and any new CLI added later silently regresses.

All three should land alongside the **regression guard** from step 3. The probe
plugin used here (wrap `connect`/`ensure_db`, assert resolved path != real
`.ll/history.db`, fail if any test opens it) is a ready template for a permanent
`conftest.py`-level guard.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-06.

**Selected**: Option A — env-var resolution in `cli_event_context`

**Reasoning**: Option A fits the well-established `LL_*` env-var override convention already used for `LL_HOST_CLI`, `LL_HOOK_HOST`, and `LL_STATE_DIR` throughout the codebase — `monkeypatch.setenv("LL_HISTORY_DB", ...)` in an autouse conftest fixture is a single-point fix that reaches all 29 CLI sites without maintaining any lists. Options B and C both require significant ongoing maintenance burden or break existing tests: B would break ≥7 test files that depend on CWD=repo-root, and C's 29-module hardcoded list silently regresses whenever a new CLI is added.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (env-var in `cli_event_context`) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (autouse `chdir(tmp_path)`) | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |
| Option C (patch `DEFAULT_DB_PATH` per module) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- **Option A**: `LL_HOST_CLI`, `LL_HOOK_HOST`, `LL_STATE_DIR` env-var overrides already exist in `host_runner.py` and `config/core.py` — identical resolution pattern, zero new infrastructure. `conftest.py` currently has no DB isolation at all (382 lines, confirmed).
- **Option B**: The repo-root-relative concern is narrower than first thought — the 28 files that read `agents/`/`skills/`/`commands/` do so via `Path(__file__).parent.parent.parent`-anchored *absolute* paths (e.g. `test_adapt_agents_for_codex.py`, `test_adapt_skills_for_codex.py`) and are immune to chdir. The real blockers: (1) no opt-out marker mechanism exists (`pytest.mark.no_chdir` etc. return zero hits); (2) E2E/integration tests manage their own CWD (`test_cli_e2e.py:244,324,371,…`, `test_hooks_integration.py:40-44`) and would race a blanket autouse chdir; (3) `hooks/user_prompt_submit.py:67` calls bare `Path.cwd()` for config resolution, so a chdir silently changes which config is loaded mid-test. Requires new opt-out infrastructure.
- **Option C**: 28 CLI modules import `DEFAULT_DB_PATH` (confirmed exact via grep). A loop-and-`monkeypatch.setattr` helper exists only as hand-maintained local lists in `test_cli_loop_dispatch.py:51-54` and `test_cli_sprint.py:37-40` (max 8 names, one module) — no autouse/auto-discovery equivalent exists, so the 28-module fixture is all-new infrastructure. **Worse, it's incomplete by construction**: `cli/history.py:294,312` use inline `from ...session_store import DEFAULT_DB_PATH as _SS_DB` re-imports that a module-namespace patch *cannot* reach — Option C would additionally have to patch `session_store.DEFAULT_DB_PATH` directly, and any new CLI with an inline re-import silently regresses.

## Integration Map

- `scripts/little_loops/session_store.py` — `DEFAULT_DB_PATH`, `connect`,
  `ensure_db`, `SQLiteTransport`, `cli_event_context`, `backfill*`.
- `scripts/tests/conftest.py` — candidate location for the isolation fixture.
- Hook handlers under `scripts/little_loops/hooks/` that open the store on
  `session_start`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete files/anchors confirmed by the probe:_

**Primary fix surface**
- `scripts/little_loops/session_store.py:644-679` — `cli_event_context()`: the
  exact leaking call site (`connect(db_path)` + `INSERT cli_events` + commit on
  enter). Option A changes the path resolution here.
- `scripts/little_loops/session_store.py:76` — `DEFAULT_DB_PATH = Path(".ll/history.db")`
  (relative → resolves against CWD).
- `scripts/tests/conftest.py` — add autouse isolation fixture + regression guard
  here (currently 382 lines, no DB isolation present).

**Caller sites (28 CLI `main()` wrappers — all pass the import-bound `DEFAULT_DB_PATH`)**
- `cli/action.py:191`, `cli/sync.py:25`, `cli/session.py:195`, `cli/deps.py:74`,
  `cli/docs.py:23,119,245,321`, `cli/harness.py:354`, `cli/learning_tests.py:48`,
  `cli/gitignore.py:28`, `cli/messages.py:21`, `cli/history_context.py:112`,
  `cli/schemas.py:23`, `cli/migrate_status.py:42`, `cli/migrate_labels.py:92`,
  `cli/create_extension.py:129`, `cli/adapt_skills_for_codex.py:311`,
  `cli/adapt_agents_for_codex.py:168`, … (full set: `grep -rln "cli_event_context(DEFAULT_DB_PATH" scripts/little_loops/cli/`).

**Most-affected tests (≥10 opens each; ~30 files, 304 tests total)**
- `tests/test_cli.py` (60), `tests/test_dependency_mapper.py` (34),
  `tests/test_cli_docs.py` (28), `tests/test_cli_decisions.py` (22),
  `tests/test_history_context_cli.py` (17), `tests/test_cli_doctor.py` (17),
  `tests/test_cli_sync.py` (15), `tests/test_cli_learning_tests.py` (13),
  `tests/test_gitignore_cmd.py` (12), `tests/test_create_extension.py` (11),
  `tests/test_cli_history.py` (11), `tests/test_cli_deps.py` (10).

**Conflicting CWD dependency (relevant to Option B)**
- `tests/test_adapt_agents_for_codex.py`, `tests/test_adapt_skills_for_codex.py`,
  `tests/test_cli_docs.py` — `TestMain*` tests that read repo-relative `agents/`,
  `skills/`, `commands/`; a blanket autouse `chdir` would break these.

**Tests already isolated (model patterns to follow)**
- `tests/test_ll_session.py`, `tests/test_history_context_cli.py` (the tmp_path
  cases), `tests/test_session_store.py` — pass an explicit `tmp_path / "history.db"`.

### Wiring Pass — Additional Surface

_Wiring pass added by `/ll:wire-issue`:_

#### ⚠ Read-path leak sites NOT covered by Option A (fix-completeness gap)

The probe measured only `cli_event_context` (write-side) opens — 304 tests. There
is a **second, smaller leak class** the probe did not count: CLI read paths that
resolve `DEFAULT_DB_PATH` directly and open it with **raw `sqlite3.connect()`**,
bypassing `session_store` entirely. The selected Option A fix (env-var resolution
inside `cli_event_context`) does **not** reach these, and an *optional*
defense-in-depth extension to `session_store.connect`/`ensure_db` would **also**
miss them (they never call those functions):

- `scripts/little_loops/cli/history.py:243` — `db_path = project_root / DEFAULT_DB_PATH`
  (read path); `:294,312` inline `from ...session_store import DEFAULT_DB_PATH as _SS_DB`
  → `:319` `sqlite3.connect(str(db_path))`. [Agent 2 finding]
- `scripts/little_loops/cli/logs.py:1282` — `db_path = DEFAULT_DB_PATH` →
  `_resolve_session_log()` `:1172-1173` `sqlite3.connect(str(db_path))`. [Agent 2 finding]

**Implication for the regression guard (step 4):** the probe-template guard wraps
`session_store.connect`/`ensure_db`, so it is **blind to these raw `sqlite3.connect`
sites** and would pass even while `test_cli_history.py` / `test_ll_logs.py` (the
`diff` subcommand path) still open the real DB. Acceptance step 5 ("`lsof
.ll/history.db` shows no pytest process") will therefore **fail** unless either
(a) these read sites also resolve `LL_HISTORY_DB`, or (b) the guard is broadened to
catch raw `sqlite3.connect` / chdir-pin the suite. Resolve in the Wiring Phase below.

#### Refinement verification (2026-06-06) — anchors re-checked against current code

_Added by `/ll:refine-issue --auto`. All file:line anchors above were re-verified
and remain accurate (`DEFAULT_DB_PATH` `session_store.py:76`; `cli_event_context`
`session_store.py:644`; read sites `cli/history.py:243,294,312`→`:319`,
`cli/logs.py:1173,1282`). Two drift items found:_

- **CLI wrapper count is now 29, not 28.** `grep -rln "cli_event_context(DEFAULT_DB_PATH" scripts/little_loops/cli/`
  returns **29** files (the Decision Rationale already cites "29" — the Root Cause /
  Integration Map "28" is stale). Modules beyond the partial list enumerated above
  include `ctx_stats.py:269`, `auto.py:32`, `parallel.py:43`,
  `verify_triggers.py`, `generate_skill_descriptions.py`, `migrate.py`,
  `migrate_relationships.py`, `sprint/__init__.py`, `issues/__init__.py`,
  `loop/__init__.py`. Option A's single-point fix still covers all 29 (it does not
  depend on the count), so this is a documentation-accuracy correction, not a scope
  change. Treat "29" as authoritative.
- **A third raw `sqlite3.connect` read site exists:** `cli/logs.py:687`
  (`_aggregate_skill_stats`), reached by the `stats` and `dead-skills` subcommands
  (callers `:822`, `:1108`). Unlike the `diff` path, its `db_path` comes from
  `discover_all_projects()` (absolute per-project `… / ".ll" / "history.db"` paths),
  **not** the relative `DEFAULT_DB_PATH` — so it leaks the real DB only for the
  *current* project when the suite runs `ll-logs stats`/`dead-skills` without
  `--project tmp`. `LL_HISTORY_DB` resolution will **not** reach it (the path is
  built from project discovery, not the default). The broadened regression guard
  (Wiring Phase step 7) must therefore also cover this site, or these subcommands'
  tests must pass an explicit `--project <tmp>`.

#### Hook handlers (advisory — already test-isolated, construct cwd-relative path)

These open the store **without** `DEFAULT_DB_PATH` (they build `cwd / ".ll" /
"history.db"` directly), so Option A has zero effect on them — but their tests
already pass a `tmp_path`-rooted `cwd`, so they are not part of the leak. Listed
for completeness; only the optional `connect`/`ensure_db` defense-in-depth would
touch them:
- `scripts/little_loops/hooks/session_start.py:123,130` — `ensure_db(cwd/.ll/history.db)`. [Agent 2 finding]
- `scripts/little_loops/hooks/user_prompt_submit.py:77,85` — `record_correction` / `record_skill_event`. [Agent 2 finding]
- `scripts/little_loops/hooks/post_tool_use.py:161,193` — `connect` / `write_file_event`. [Agent 2 finding]

#### Non-CLI library callers of the default path (advisory)

Beyond the 28 CLI mains, these import/consume the default path; tests for them pass
explicit paths today, so they are not leak sources, but they share the resolution
surface and are worth a glance when changing `DEFAULT_DB_PATH` semantics:
- `scripts/little_loops/issue_manager.py:36` — imports `DEFAULT_DB_PATH`, `SQLiteTransport` (drives `ll-auto`). [Agent 1 finding]
- `scripts/little_loops/history_reader.py:46` — `DEFAULT_DB_PATH`, `ensure_db` defaults. [Agent 1 finding]
- `scripts/little_loops/workflow_sequence/io.py:47` — `connect` fallback when JSONL absent. [Agent 1 finding]
- `scripts/little_loops/cli/backfill_worker.py:36` — `backfill_incremental` (spawned by `session_start`). [Agent 1 finding]
- `scripts/little_loops/__init__.py:44` — public `__all__` exports `SQLiteTransport`. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — `LL_HISTORY_DB` is a new product-visible
env var; document it the same way `LL_HOST_CLI` is ("env var takes precedence if
both are set"):_

- `docs/reference/CONFIGURATION.md` — `events.sqlite.path` block (line ~1174,
  default `.ll/history.db`); note `LL_HISTORY_DB` as the env-var override, mirroring
  the `host_cli`/`LL_HOST_CLI` phrasing at line 977. [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — env-var comparison table (line ~199) lists
  `LL_HOST_CLI`/`LL_HOOK_HOST`/`LL_STATE_DIR`; add an `LL_HISTORY_DB` row. [Agent 2 finding]
- `docs/reference/API.md` — has **no** `## little_loops.session_store` section;
  `cli_event_context` is undocumented. Either add a short section or annotate the
  `### main_session` / `### main_history_context` / `### main_ctx_stats` `--db`
  defaults to mention `LL_HISTORY_DB`. [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `### Components` table row for `cli_event_context()`
  (under "History DB: Producer→Consumer Flow", line ~641); note env-var path
  resolution. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — `## What Is history.db?`; note
  `LL_HISTORY_DB` overrides the default path. [Agent 2 finding]
- `.claude/CLAUDE.md` — `## CLI Tools` section (`ll-session`, `ll-history-context`,
  `ll-ctx-stats` entries cite `default DB .ll/history.db`); note the override.
  [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `tests/test_session_store.py` — `TestCliEventContext` already exercises
  `cli_event_context()` with an explicit `db` (`test_cli_event_roundtrip`, etc.)
  but **never** the no-arg env-var path. Add `test_cli_event_context_respects_LL_HISTORY_DB`
  here following the `monkeypatch.setenv("LL_*")` convention. [Agent 3 finding]
- `tests/test_host_runner.py` — `TestApplyHostCliFromConfig` is the **reference
  pattern** for the new env-var test (`setenv` + assert resolution + `delenv`
  cleanup) and for the conftest fixture shape. [Agent 3 finding]
- `tests/test_cli_history.py`, `tests/test_ll_logs.py` (the `diff` path) — will
  **still open the real DB** via the raw-`sqlite3.connect` read sites above even
  after Option A; verify against the broadened guard. [Agent 2/3 finding]
- `tests/test_config_schema.py:468` — asserts `sqlite.path` default `== ".ll/history.db"`;
  **unaffected** (Option A does not change the schema default). No update needed. [Agent 3 finding]
- Conftest autouse-fixture model patterns: `test_cli_ctx_stats.py` (`_isolate_terminal_width`,
  no-yield monkeypatch) and `test_subprocess_utils.py` (`_patch_resolve_host`, yield). [Agent 3 finding]

### Configuration / Schema

_Wiring pass added by `/ll:wire-issue`:_

- `config-schema.json` — **no change required.** `LL_HISTORY_DB` as a pure env var
  needs no schema field (it parallels `LL_HOST_CLI`, which also has no dedicated
  schema entry beyond the `orchestration.host_cli` config mirror). Only if a
  parallel `events.sqlite` / `orchestration` config key is later added would the
  schema need a field. Recorded so a future pass does not re-investigate. [Agent 1/2 finding —
  Agent 1's separate claim that `config-schema.json` already defines `LL_HISTORY_DB`
  was **verified false**: `grep LL_HISTORY_DB` matches only this issue file.]

## Implementation Steps

1. Audit: `lsof` during a run + grep for default-path entry points called in tests.
2. Add autouse isolation fixture in `conftest.py` (belt-and-suspenders).
3. Fix any test/code that genuinely needs an explicit path.
4. Add a regression guard that fails if the real DB is opened during tests.
5. Run full suite; confirm `lsof .ll/history.db` shows no pytest process.

### Codebase Research Findings

_Added by `/ll:refine-issue` — step 1's audit is already done (see Confirmed Root
Cause); the concrete sequence, assuming Option A:_

1. **(done)** Audit complete: 304 tests open the real DB via
   `cli_event_context(DEFAULT_DB_PATH, ...)` in 28 CLI mains.
2. In `session_store.cli_event_context` (`session_store.py:644`), resolve the path:
   when `db_path` is the default sentinel, prefer `os.environ.get("LL_HISTORY_DB")`
   before `DEFAULT_DB_PATH`. (Optional: do the same in `connect`/`ensure_db` for
   defense in depth.)
3. In `scripts/tests/conftest.py`, add an autouse fixture that sets
   `monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "history.db"))` (function
   scope; use a per-test tmp dir).
4. Add the regression guard test: wrap `session_store.connect`/`ensure_db`, run a
   representative CLI `main()` in-process, and assert no resolved path equals the
   real repo `.ll/history.db` (template: the probe plugin in this issue's history).
5. Verify: `python -m pytest scripts/tests/ -q` then, in another shell during the
   run, `lsof .ll/history.db` shows no `python`/pytest process; and the real DB's
   `mtime`/row counts are unchanged across a full suite run.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included so the
fix actually satisfies acceptance step 5 (`lsof`-clean) and so the new env var ships
documented:_

6. **Close the read-path leak (REQUIRED for `lsof`-clean acceptance).** Option A's
   `cli_event_context` change does **not** cover the raw-`sqlite3.connect` read sites
   at `cli/history.py:243,294,312` (→`:319`) and `cli/logs.py:1282` (→`:1172-1173`).
   Pick one: (a) resolve `LL_HISTORY_DB` at these sites too (route them through a
   shared `resolve_history_db()` helper so the env var is honored everywhere), or
   (b) make the conftest fixture `monkeypatch.chdir(tmp_path)`-pin so the relative
   `DEFAULT_DB_PATH` cannot reach the repo root. Note (b) reintroduces the
   Option-B CWD risks the decision rejected, so (a) is preferred.
7. **Broaden the regression guard (step 4).** The probe template wraps
   `session_store.connect`/`ensure_db` and is **blind to raw `sqlite3.connect`**.
   Either also patch/observe `sqlite3.connect` in the guard, or assert the real
   `.ll/history.db` `mtime` + row counts are unchanged across a representative
   read-path CLI run (`main_history`, `main_logs --diff`). Otherwise the guard
   green-lights a suite that still opens the real DB.
8. **Ensure parent-dir creation for the tmp DB.** The autouse fixture points
   `LL_HISTORY_DB` at `tmp_path / "history.db"` (parent exists) — but if any path
   uses a `.ll/` subdir, confirm `ensure_db`/`cli_event_context` `mkdir(parents=True)`
   before connect so the redirected open does not fail on a missing directory. [Agent 3 finding]
9. **Document `LL_HISTORY_DB`** in the six doc sites listed under Integration Map →
   Documentation (CONFIGURATION.md, HOST_COMPATIBILITY.md, API.md, ARCHITECTURE.md,
   HISTORY_SESSION_GUIDE.md, `.claude/CLAUDE.md`), mirroring the `LL_HOST_CLI`
   "env var takes precedence" phrasing.
10. **Add `test_cli_event_context_respects_LL_HISTORY_DB`** to
    `TestCliEventContext` in `tests/test_session_store.py`, following the
    `tests/test_host_runner.py::TestApplyHostCliFromConfig` setenv/delenv pattern.

## Impact

- **Severity**: real-history pollution + flaky/order-dependent tests; aggravates
  the DB lock-contention class of bugs.
- **Scope**: test suite hygiene + session-store default-path handling.
- **Risk if unfixed**: corrupted analytics and recurring intermittent lock crashes.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopssession_store` | session store public API & defaults |
| `.claude/CLAUDE.md` § Automation: Scratch Pad | per-instance artifact isolation philosophy |

Related: surfaced while fixing the `ll-issues` `table tool_events already exists`
crash (lock-contention race in `session_store._current_version` /
`_apply_migrations`).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-06_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 76/100 → MODERATE

### Concerns
- Root cause is not pinpointed to a specific file:line. Three candidate sources are listed but unconfirmed. Implementation should begin with the `lsof`+grep investigation, not with writing code.

### Gaps to Address
- Run the lsof investigation first: start the test suite in background, then `lsof .ll/history.db` to identify the actual leaking module/test. The grep audit alone (`grep -rn "DEFAULT_DB_PATH\|history.db" scripts/tests/`) won't confirm the active call site.
- Verify that `test_issue_manager.py`'s `config.project_root / ".ll" / "history.db"` usage is within a temp fixture dir and not contributing to the leak (appears safe from fixture analysis but confirm with lsof).
- After lsof identifies the site, confirm whether the autouse conftest monkeypatch alone is sufficient or whether explicit path fixes are also needed.

## Session Log
- `/ll:confidence-check` - 2026-06-06T14:00:00Z - `1cab2d29-91a7-43aa-b71c-cc0209970692.jsonl`
- `/ll:refine-issue` - 2026-06-07T02:12:07 - `d1b83bd2-dc5e-4b2f-8ae5-fe406ad11ab8.jsonl`
- `/ll:confidence-check` - 2026-06-07T02:30:00Z - `4618c901-07ca-4729-b2a0-eb75257e69a0.jsonl`
- `/ll:wire-issue` - 2026-06-07T02:05:47 - `2cb24a85-125e-4b27-a053-03f6a227f78c.jsonl`
- `/ll:decide-issue` - 2026-06-07T01:54:19 - `2e30f14e-9122-44f7-835e-70d8975352d8.jsonl`
- `/ll:refine-issue` - 2026-06-07T01:51:38 - `ea615ab5-cdcf-4f14-a9f5-c2da8768d657.jsonl`
- `/ll:format-issue` - 2026-06-07T01:34:42 - `784755b2-ee36-4dab-b9ae-65246aa23931.jsonl`
- `/ll:capture-issue` - 2026-06-07T01:32:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5141031e-db2a-4193-90dd-496d74847e81.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d80b8-1a92-406b-86d8-7de5a29b6f5b.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
