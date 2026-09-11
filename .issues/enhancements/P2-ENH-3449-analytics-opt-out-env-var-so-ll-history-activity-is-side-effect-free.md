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

- `main_history()` (`scripts/little_loops/cli/history.py:65`) wraps the entire command — argparse included — in `cli_event_context(DEFAULT_DB_PATH, "ll-history", sys.argv[1:])` and passes no `config`.
- In `cli_event_context` (`scripts/little_loops/session_store/writers.py:484`), `config=None` leaves `gate_open=True`, so every invocation calls `_pkg.connect(effective_path)` (creating `.ll/history.db` when absent) and inserts a `cli_events` row.
- Consequence (a): a read command authors a history.db where none existed, so the activity reader's `db_missing` branch can never fire for the local repo (acknowledged by the fallback comment at `history.py:684-686`).
- Consequence (b): under 30s polling, ~2,880 `cli_events` rows/day/project of analytics pollution.
- The `analytics.capture.cli_commands` glob gate (ENH-2932) is dead for `ll-history` because `config` is never passed.

## Expected Behavior

- `LL_ANALYTICS_CAPTURE` set to a falsy value (`0`/`false`/`off`, case-insensitive) makes `cli_event_context` and `skill_event_context` skip `resolve_history_db`/`connect` entirely — no file creation, no `cli_events` row — while the wrapped body still runs.
- With the env var set, `ll-history activity --format json` on a repo with no `.ll/history.db` exits 0, reports the local member as `status: db_missing`, `ok: false`, `instrumented: false`, and leaves no `.ll/history.db` behind. JSON output shape otherwise unchanged.
- Unset or any other value: behavior byte-identical to today (row still inserted).
- With `config=` wired in `main_history()`, the `analytics.capture.cli_commands` gate in `.ll/ll-config.json` actually applies to `ll-history`.

## Motivation

**Verified in code:**

- `main_history()` (`scripts/little_loops/cli/history.py:65`) wraps the *entire* command, argparse included, in `cli_event_context(DEFAULT_DB_PATH, "ll-history", sys.argv[1:])` and passes no `config`.
- In `cli_event_context` (`scripts/little_loops/session_store/writers.py:484`), `config=None` leaves `gate_open=True`, so every invocation calls `_pkg.connect(effective_path)` (creating `.ll/history.db` when absent) and inserts a `cli_events` row.
- Consequence (a): a read command authors a history.db where none existed, so the activity reader's `db_missing` branch can never fire for the local repo. The fallback comment at `history.py:684-686` acknowledges this.
- Consequence (b): under 30s polling, ~2,880 `cli_events` rows/day/project of analytics pollution.
- The already-shipped `analytics.capture.cli_commands` glob gate (ENH-2932) is dead for `ll-history` because `config` is never passed.

## Proposed Solution

Add an environment-variable kill switch upstream of the config gate (the context manager opens before argparse runs, so a CLI flag cannot suppress the enter-INSERT):

1. **`LL_ANALYTICS_CAPTURE` short-circuit** — a module-private helper `_analytics_capture_disabled() -> bool` in `session_store/writers.py` reads `os.environ`; falsy values (`0`/`false`/`off`, case-insensitive) set `gate_open=False` in `cli_event_context` and `skill_event_context` *before* `resolve_history_db`/`connect`, so nothing touches the filesystem. Fixes all ~46 `cli_event_context` call sites at once and is per-invocation, which is what a polling consumer needs.
2. **Wire `config=` into `main_history()`** using the same project-config loader other CLIs use, so the `analytics.capture.cli_commands` gate (ENH-2932) applies. Audit other `cli/*.py` callers omitting `config`; fix in this issue only if trivial.

Full behavior contract in Decisions §1–3; signatures in Program Design.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Loader constraint for step 2: use the guarded raw-dict shape (`resolve_config_path` + except-guarded `json.loads` -> `dict | None`, per `hooks/user_prompt_submit.py:56-64` / `cli/history_context.py:229-239`); `BRConfig`'s base-config `json.load` (`config/core.py:307-308`) is unguarded — a malformed `ll-config.json` would raise out of `main_history()` before argparse, breaking the never-fail enter contract

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — add `_analytics_capture_disabled()`, gate short-circuit in `cli_event_context` (:484) and `skill_event_context` (:601)
- `scripts/little_loops/cli/history.py` — load project config in `main_history()` (:65), pass `config=`; update the fallback comment at :684-686 (comment-only edit)

### Dependent Files (Callers/Importers)
- All ~46 `cli_event_context(...)` call sites in `scripts/little_loops/cli/*.py` (grep: config.py, docs.py, action.py, code.py, logs.py, messages.py, ctx_stats.py, ...) — behavior unchanged unless env var set
- `skill_event_context` callers (hooks-layer skill analytics)

### Similar Patterns
- `analytics.capture.cli_commands` glob gate already inside `cli_event_context` (ENH-2932) — the env check slots ahead of it
- Env-var overrides like `LL_HOST_CLI` in `resolve_host()` (`scripts/little_loops/host_runner.py`)

### Tests
- `scripts/tests/test_session_store_writers.py` — unit tests: env var set → no connect, no row; unset → row written
- `scripts/tests/test_cli_history.py` — `LL_ANALYTICS_CAPTURE=0 ll-history activity` on db-less repo: exit 0, `db_missing` member, no `.ll/history.db` created
- Test hygiene (review 2026-09-11): tests asserting a row IS written must `monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)`; the db-less test must `delenv("LL_HISTORY_DB", raising=False)` so db resolution anchors at the tmp project regardless of the developer's shell. Follow the existing in-process pattern (`patch.object(sys, "argv", ...)` + `patch("pathlib.Path.cwd", return_value=tmp_path)`, e.g. `test_cli_history.py` `test_absent_flag_single_repo_result`). The AC4 config-gate test's tmp project must live under the OS tmp dir, not under this repo — the upward `resolve_config_path` walk would find this repo's `cli_commands: ["*"]` and leak it into the test.

### Documentation
- `docs/reference/CLI.md` — ll-history section: document `LL_ANALYTICS_CAPTURE`
- `docs/reference/API.md` — analytics/session-store writers section
- `docs/guides/HISTORY_SESSION_GUIDE.md` — env-var mention alongside `LL_HISTORY_DB` (:55) and the config table (:660)
- `docs/reference/HOST_COMPATIBILITY.md` — env-var table (:729, where `LL_HISTORY_DB` lives)
- `cli_event_context` / `skill_event_context` docstrings in `session_store/writers.py` — describe the env-var short-circuit (API.md mirrors these docstrings)

### Configuration
- `.ll/ll-config.json` → `analytics.capture.cli_commands` (now effective for ll-history via `config=` wiring)
- New env var: `LL_ANALYTICS_CAPTURE`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Tree-wide caller audit (pre-computed for Decisions §2): zero production call sites pass `config=` to `cli_event_context`/`skill_event_context`; matches exist only in `scripts/tests/test_session_store_writers.py:564,572-576,603-607,974-975,987-992` — the ENH-2932 gate is dead for every `ll-*` binary, not just ll-history
- Call-site census (grep `cli_event_context(` excluding the def): 54 lines across 51 files, ~47 under `scripts/little_loops/cli/` (one call per `main_*` entry point; `docs.py` carries 4); the balance is `init/cli.py` plus re-export/reference lines in `session_store/schema.py`, `session_store/__init__.py`, `mcp_server/__init__.py`
- Config-loader precedents that yield the raw dict `config=` wants: `_load_config(cwd) -> dict | None` (`hooks/user_prompt_submit.py:56-64`, mirrored `hooks/post_tool_use.py:41`) — `resolve_config_path` (pure lookup, `config/core.py:157-181`) + `json.loads` guarded by `except (OSError, json.JSONDecodeError): return None`; inline variants at `cli/learning_tests.py:43-51` and `cli/history_context.py:229-239`
- Test seam: the `_pkg` indirection at `writers.py:38-47` exists so tests can `monkeypatch.setattr(session_store, "connect", ...)` — the locked-db tests at `test_session_store_writers.py:490-514` show the pattern an env-var "no connect" assertion can reuse

## Program Design

### Types

- No new types — pure gate logic returning `bool`.

### Signatures

- `_analytics_capture_disabled() -> bool` — module-private, `session_store/writers.py`; true iff `os.environ.get("LL_ANALYTICS_CAPTURE", "").strip().lower()` ∈ `{"0", "false", "off"}`
- `cli_event_context(db_path=DEFAULT_DB_PATH, source=..., argv=None, config=None)` — signature unchanged; gate logic gains the env-var short-circuit before `resolve_history_db`/`connect`
- `skill_event_context(...)` — same env-var short-circuit
- `main_history()` — gains project-config load and `config=` pass-through to `cli_event_context`

### Call Path

`main_history` -> `cli_event_context(config=<project config>)` -> `_analytics_capture_disabled()` (env check, first) -> [`resolve_history_db` -> `_pkg.connect` -> INSERT, all skipped when gate closed]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Zero-filesystem insertion point: the env check must run before `resolve_history_db` (`writers.py:524` cli / `:625` skill) — `resolve_history_db` (`db.py:121-132`) is read-only (upward root walk + `ll-config.json` read; honors `LL_HISTORY_DB` at `db.py:107-109`) but does touch the filesystem; file creation happens only in `ensure_db` (`schema.py:1546-1584`, `mkdir` at `:1577`) via `connect` (`schema.py:1587-1596`), already under `if gate_open:` (`writers.py:534-541`)
- Exit path needs no new guard: both exit UPDATEs are guarded by `conn is not None and row_id is not None` (`writers.py:564`, `:673`), set only on a successful gated INSERT — there is no path today where enter is suppressed but exit writes; a body raise still re-raises after recording `exit_code=1` with the UPDATE in `finally`
- Constraint: `_analytics_capture_disabled()` must be a non-raising pure `os.environ` read — `skill_event_context`'s gate/resolution sit outside any try (its INSERT handler catches only `sqlite3.Error`, `writers.py:650`), unlike `cli_event_context` whose whole enter prefix is inside `except Exception` (`writers.py:542`)
- No shared Python env-falsy helper exists; closest precedents are the FSM YAML shell sets `("0","false","no","off")` (`loops/rn-implement.yaml:603,1097`) and the YAML-field parse at `cli/help.py:152` — the issue's `{"0","false","off"}` set has no Python precedent; `LL_HOST_CLI` (`host_runner.py:2292-2336`) is exact-string with no case folding
- db_missing contract confirmed end-to-end: `_gate_member` (`workspace_quality.py:140-141`) -> `RepoActivity(status=DB_MISSING, instrumented=False)` (`issue_history/workspace_activity.py:269-281`) -> `to_dict` emits `ok: false` (`:87`) -> `aggregate_workspace_activity` never raises (`:254-256`) -> exit 0 (`history.py:710`)
- Reader-safety confirmed (review 2026-09-11): the activity read path never authors a db — `_gate_member` checks `db_path.exists()` (`workspace_quality.py:140-141`) then `_open_member_readonly` (`:117-120`) opens `file:...?mode=ro` with `PRAGMA query_only=ON`; `feature_enabled_for` (`config/features.py:63`) operates on the raw config dict, so the guarded loader's output plugs straight into `config=`

## Scope Boundaries

- No argparse `--no-analytics` flag — the context manager opens before argparse runs (Decisions §1)
- No JSON output-shape changes to `ll-history activity`
- No pruning/compaction of existing `cli_events` rows — history.db deletion/compaction stays a manual CLI action only
- Other `cli/*.py` callers omitting `config=`: audit + Session Log list only; fixed here only if trivial (Decisions §2)
- `has_history` any-rows-ever signal → sibling ENH-3450, not this issue

## Implementation Steps

1. Add a small helper in `session_store/writers.py` (e.g. `_analytics_capture_disabled() -> bool`) reading `os.environ.get("LL_ANALYTICS_CAPTURE")`.
2. In `cli_event_context` and `skill_event_context`, short-circuit `gate_open=False` when the helper returns true, *before* `resolve_history_db`/`connect`.
3. In `cli/history.py`, load project config and pass `config=` to `cli_event_context`. The load sits before the `with cli_event_context(...)` at `history.py:65`, anchored on cwd (`resolve_config_path(Path.cwd())` + guarded `json.loads`) — `project_root` is only derived at `history.py:440`, inside argparse, so `args.config` cannot participate.
4. Rewrite the fallback comment at `history.py:684-686` to describe the new contract.
5. Document the env var in `docs/reference/CLI.md` (ll-history section), `docs/reference/API.md` (analytics section), `docs/guides/HISTORY_SESSION_GUIDE.md`, and the `docs/reference/HOST_COMPATIBILITY.md` env-var table; update both context-manager docstrings in `writers.py`. Cover: kill-switch only (no force-enable), empty string = unset, per-invocation usage over shell-profile export.
6. Tests (see AC).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Test-coverage constraints: the existing gate-closed test `test_cli_event_context_gate_disabled` (`test_session_store_writers.py:599-612`) passes an explicit tmp db path and does NOT assert db non-existence — the new env-var tests should pin no-create explicitly (pattern: the `LL_HISTORY_DB` tests at `:476-488` use `monkeypatch.setenv` + `assert not env_db.exists()`); skill-side gate-closed coverage is `test_gate_disabled_still_yields_completion` (`:982-996`)

## Impact

- **Priority**: P2 - Unblocks a downstream consumer's (little-loops-hermes) polling integration, which otherwise regresses its never-author-a-db invariant; not a defect in shipped behavior.
- **Effort**: Small - One helper + gate short-circuit + one config wiring; tests extend existing files (`test_session_store_writers.py`, `test_cli_history.py`).
- **Risk**: Low - Additive env var; unset or non-falsy values leave behavior byte-identical; no interface or output-shape changes.
- **Breaking Change**: No

## Decisions (resolved, do not re-derive)

1. **Seam is an environment variable, not an argparse flag.** The context manager opens before argparse runs, so a `--no-analytics` flag cannot suppress the enter-INSERT. `LL_ANALYTICS_CAPTURE` is read inside `cli_event_context` and `skill_event_context`: value `0`, `false`, or `off` (case-insensitive) sets `gate_open=False` before `resolve_history_db`/`connect`, so nothing touches the filesystem; the wrapped body still runs. This fixes all ~46 `cli_event_context` call sites at once and is per-invocation, which is what a polling consumer needs. Unset or any other value: unchanged behavior.
2. **Wire `config=` into `ll-history`'s `cli_event_context` call** using the same project-config loader other CLIs use, so the `analytics.capture.cli_commands` gate actually applies. Audit other `cli/*.py` callers that omit `config` and list them in the Session Log; fix in this issue only if trivial.
3. **Behavior contract.** With `LL_ANALYTICS_CAPTURE=0`, `ll-history activity` on a repo with no `.ll/history.db` exits 0, reports the local member as `status: db_missing`, `ok: false`, `instrumented: false`, and leaves no `.ll/history.db` behind. JSON output shape is otherwise unchanged.
4. **Kill-switch semantics** (review 2026-09-11). The falsy set is exactly `{"0", "false", "off"}` (case-insensitive after `strip()`); set-but-empty (`LL_ANALYTICS_CAPTURE=""`) counts as unset — capture stays on. One-way kill switch only: no truthy value force-enables capture past a config-gate exclusion ("any other value" = today's behavior). The minimal set is deliberate — the only sibling precedent (FSM shell sets `("0","false","no","off")` in `rn-implement.yaml`) governs shell exports, not env parsing, and the polling consumer sets the var programmatically. Docs must state: set per-invocation (polling consumers), not in a shell profile — a global export also disables hooks-layer `skill_events` capture in every project.

## API/Interface

- New env var `LL_ANALYTICS_CAPTURE` (falsy values: `0`/`false`/`off`, case-insensitive; set-but-empty = unset) honored by `cli_event_context` and `skill_event_context`. Kill-switch only: no truthy value force-enables capture past a config-gate exclusion.
- `main_history()` passes `config=<loaded project config>` to `cli_event_context`.
- No new CLI flags. No JSON output-shape change.

## Acceptance Criteria

- [ ] `LL_ANALYTICS_CAPTURE=0 ll-history activity --format json` in a tmp project with no history.db: exit 0, local member `status: db_missing`, and the test asserts `.ll/history.db` does not exist after the run.
- [ ] Same command without the env var still inserts a `cli_events` row (existing behavior preserved).
- [ ] Unit tests for `cli_event_context` and `skill_event_context`: env var set → no connect, no row written; row-written tests `delenv` the var so they don't depend on the developer's shell.
- [ ] Case-insensitivity: `LL_ANALYTICS_CAPTURE=OFF` (or `False`) suppresses the row the same as `0`.
- [ ] `analytics.capture.cli_commands` excluding `ll-history` in `.ll/ll-config.json` suppresses the row for `ll-history`.
- [ ] Fallback comment at `history.py:684-686` updated.
- [ ] `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, and `docs/reference/HOST_COMPATIBILITY.md` document `LL_ANALYTICS_CAPTURE`.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- FEAT-3445, FEAT-3446 (shipped `ll-history activity`), ENH-2932 (capture gate), EPIC-1707 (graceful degradation contract).
- Sibling: ENH-3450 (`has_history` signal on `RepoActivity`), same consumer.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-11T20:49:17 - `3e633d12-e9f0-40e1-8e84-6924e6006790.jsonl`
- `/ll:format-issue` - 2026-09-11T20:30:31 - `29719eda-e34b-4588-9e6c-a4b50bf277cf.jsonl`
- `/ll:capture-issue` - 2026-09-11T20:26:49 - `d2544764-cca3-4cd1-bd27-85b0d1d0f3c3.jsonl`
