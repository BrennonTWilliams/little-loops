---
id: ENH-3427
type: ENH
title: "Host-resolution seam \u2014 --host flag, both-spellings probe, and session_start\
  \ host injection"
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-09'
captured_at: '2026-09-09T21:54:30Z'
labels:
- multi-host
- observability
parent: ENH-3419
blocked_by: []
blocks:
- ENH-3428
- ENH-3429
- ENH-3430
relates_to:
- ENH-3420
- FEAT-3417
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3427: Host-resolution seam — --host flag, both-spellings probe, and session_start host injection

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). This is the foundation child: it lands the
shared host-resolution primitives that the three per-CLI rewires (ENH-3428/3429/3430) build on.
Nothing here changes any CLI's session-enumeration behavior yet — `--host` is added but the CLIs
still resolve sessions the old way until the dependent children land.

## Current Behavior

`session_store/sessions.py` resolves the Claude project folder by encoding only `cwd.resolve()`
(`_detect_claude_sessions` 236-265, `_project_folder_for_layout_host` 331), so a project dir
encoded from an unresolved symlinked cwd is missed. There is no `--host` flag on `ll-messages`,
`ll-ctx-stats`, or `ll-logs`, and no shared `REGISTERED_HOSTS` export — `cli/session.py:211-216`
hand-writes its own 8-item `choices=` list that can drift from the registered hosts. Neither
`_resolve_host` nor a flag/env/union precedence exists anywhere. `hooks/session_start.py:162`
calls `get_project_folder(cwd)` without a `host=` kwarg.

## Expected Behavior

`detect_sessions`/`_project_folder_for_layout_host` probe both the resolved and as-recorded cwd
spelling (resolved wins). `REGISTERED_HOSTS` is importable from `little_loops.session_store` and
sources the `choices=` list for `ll-messages --host`, `ll-ctx-stats --host`, all 9
session-touching `ll-logs` subcommands' `--host`, and the retrofitted `ll-session backfill
--host`. Host resolution follows `--host` > `LL_HOOK_HOST` env > union (`None`) on all three
CLIs, each with a precedence test; an invalid `--host` exits via argparse `SystemExit`.
`hooks/session_start.py:162` passes `host=event.host or os.environ.get("LL_HOOK_HOST",
"claude-code")` to `get_project_folder`, with `_backfill_host` (178) reusing the same hoisted
expression instead of duplicating it. No CLI's session-enumeration behavior changes yet — the
`--host` flags are additive and unconsumed until ENH-3428/3429/3430 land.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Scope Boundaries

**In scope:**

1. **Both-spellings probe** (`session_store/sessions.py`): `_detect_claude_sessions` (236-265) and
   `_project_folder_for_layout_host` (331) currently encode only `cwd.resolve()`. Probe **both**
   the resolved and the as-recorded spelling (resolved wins), mirroring what the codex path
   already does (`sessions.py:131` DB match, `:174` scan match). This is a prerequisite for
   `TestDiscover` passing on macOS in ENH-3430, since `test_ll_logs.py:109`'s
   `_make_project_dir` helper encodes an unresolved path. Add a `test_session_discovery.py` case:
   a Claude project dir encoded from an unresolved symlinked cwd is found by
   `detect_sessions(unresolved_cwd, "claude-code", home=...)`.
2. **`REGISTERED_HOSTS` export**: re-export `sessions._REGISTERED_HOSTS` (268-277) as
   `REGISTERED_HOSTS` from `little_loops.session_store` (add to `__all__`) so every `--host` flag's
   `choices=` sources from one place instead of copied literals.
3. **`_resolve_host` helper** (new, suggested home `user_messages.py` beside `get_project_folder`):
   `_resolve_host(flag: str | None) -> str | None` = `flag or os.environ.get("LL_HOOK_HOST") or
   None`. `None` means union across all registered hosts.
4. **`--host` flag on all three CLIs**, default `None`, `choices=list(REGISTERED_HOSTS)`:
   - `ll-messages` and `ll-ctx-stats` are flat parsers — add top-level.
   - `ll-logs` is a subparser CLI; add via one `_add_host_arg(parser)` helper applied to the 9
     session-touching subcommands (`discover`, `extract`, `sequences`, `stats`, `scan-failures`,
     `dead-skills`, `eval-export`, `loop-fleet`, `fleet-review`) — not `tail`/`diff`/`digest`.
   - Retrofit `cli/session.py:211-216`'s hand-written 8-item `choices=` list to source from
     `REGISTERED_HOSTS` too, so it can't drift from the seam.
5. **`hooks/session_start.py:162`**: pass `host=event.host or os.environ.get("LL_HOOK_HOST",
   "claude-code")` to `get_project_folder(cwd)`. The same expression is computed as
   `_backfill_host` at line 178 (after the call at 162) — hoist the assignment above line 162 and
   reuse it at 178 rather than duplicating the literal. Add a capturing-stub test asserting
   `get_project_folder`'s call receives a `host=` kwarg (model on
   `test_enh_3166_qwen_normalizer.py:577-638`'s `TestSessionStartHookPassesHost`, which uses a
   `*a, **kw`-swallowing lambda today and needs a capturing variant).
6. **Precedence tests**: one resolution test per CLI (`ll-logs`, `ll-messages`, `ll-ctx-stats`):
   flag beats env, env beats union, neither → union. Model the choices-list/invalid-value shape on
   `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list` (41-61).

**Out of scope:** actually routing any CLI's session enumeration through `detect_sessions`/
`iter_events` — that is ENH-3428 (ll-messages), ENH-3429 (ll-ctx-stats), and ENH-3430 (ll-logs).
The `--host` flags added here are inert until those children consume the resolved host.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Naming collision to avoid: `host_runner.py:2292` already defines a **public** `resolve_host(env=None) -> HostRunner` — orchestration host-CLI resolution, an unrelated concept from this issue's new **private** `_resolve_host(flag) -> str | None` (session-discovery host resolution). `test_host_runner.py`'s `TestResolveHost` class covers the existing one; keep the new function's tests, docstring, and any prose clearly distinct from that name.
- `host_runner.py:2292`'s `resolve_host()` is the only existing precedence resolver in the codebase whose docstring states precedence as a numbered list — the closest available shape precedent for `_resolve_host`'s docstring. It reads env only (no `flag` parameter), consistent with the issue's own finding that no prior function here takes an explicit flag argument for this kind of precedence.
- Every existing shared argparse-flag helper (`add_json_arg`, `add_window_args`, `add_corpus_target_args`, `cli_args.py`) is named **without** a leading underscore and lives in `cli_args.py`, not beside its consuming CLI module. The issue's suggested `_add_host_arg` name and `cli/logs.py` placement diverges from every existing sibling on both the underscore and the location — already flagged as an unresolved placement choice above; this adds that the naming convention diverges too.
- `choices=` wrapper convention tracks the constant's container type: `list(CONST)` appears only where CONST is an ordered sequence (`VALID_KINDS`, `cli/session.py:120,132`); `sorted(CONST)` appears where CONST is a `set`/`frozenset` (`VALID_PRIORITIES` at `cli/issues/create.py:516`; `_DEFERRAL_REASON_CODES | _CLOSED_REASON_CODES` at `cli/issues/__init__.py:883`, which carries an explicit ENH-2870 drift-prevention comment). `REGISTERED_HOSTS` is specified as `frozenset[str]`, so the closer-matching existing example is the `sorted()` family, not `list(VALID_KINDS)`.
- Package-constant re-export precedent: `session_store/__init__.py:112-119,202-205` re-exports `VALID_KINDS` from `schema.py` by importing it by name into the package's multi-line `from ... import (...)` block and listing it in `__all__` at the same relative position. `session_store/__init__.py:130-144` already has an adjacent `from little_loops.session_store.sessions import (...)` block — the natural site to extend for `REGISTERED_HOSTS`.
- Capturing-stub tests for a specific kwarg reaching a mocked function have no single canonical shape in this codebase — four distinct capture-container idioms coexist: `dict.update(kwargs)` (`test_fsm_runners.py:639`), `list.append(dict)` (`test_prepatch_check.py:461`), `dict[key] = value` (`test_feat3310_artifact_extract.py:281`), and the `_FakePopen.__init__`-args-list variant used by the issue's own named precedent (`test_enh_3166_qwen_normalizer.py:581`).
- Precedence-test structuring also has two coexisting shapes: one test method per tier inside a class (`test_host_runner.py:381` `TestResolveHost`), and one test function per tier at module level named `test_..._<tier>_wins`/`..._beats_...` (`test_enh_3171_mcp_project_root.py:65`, `test_feat3310_artifact_extract.py:281`). Neither is dominant — an open choice for whichever of the 3 new CLI precedence tests get written.
- Confirmed via repo-wide search: `_add_host_arg` and a public (non-underscore) `REGISTERED_HOSTS` do not exist anywhere in the tree yet — both are genuinely new symbols, no existing partial implementation to reconcile with.

## Program Design

### Types

- No new data types — `_resolve_host` returns the existing `str | None` host-id shape used
  throughout `session_store`.

### Signatures

- `_resolve_host(flag: str | None) -> str | None` (new, `user_messages.py`)
- `_add_host_arg(parser: argparse.ArgumentParser) -> None` (new, `cli/logs.py`)
- `REGISTERED_HOSTS: frozenset[str]` (re-exported, `session_store/__init__.py`, sourced from
  `sessions._REGISTERED_HOSTS`)

### Call Path

`ll-messages`/`ll-ctx-stats`/`ll-logs` argparse setup -> `_add_host_arg` / inline `--host` flag
(`choices=list(REGISTERED_HOSTS)`) -> `_resolve_host(args.host)` -> (unconsumed until
ENH-3428/3429/3430). `hooks/session_start.py:162` -> `get_project_folder(cwd, host=...)` ->
`_detect_claude_sessions` / `_project_folder_for_layout_host` (both-spellings probe).

## Files to Modify

- `scripts/little_loops/session_store/sessions.py` (`_detect_claude_sessions` 236-265,
  `_project_folder_for_layout_host` 331)
- `scripts/little_loops/session_store/__init__.py` (`REGISTERED_HOSTS` re-export)
- `scripts/little_loops/user_messages.py` (new `_resolve_host` helper)
- `scripts/little_loops/cli/messages.py`, `scripts/little_loops/cli/ctx_stats.py`,
  `scripts/little_loops/cli/logs.py` (flag registration only — `_add_host_arg` helper lives in
  `cli/logs.py`)
- `scripts/little_loops/cli/session.py:211-216` (retrofit `choices=` source)
- `scripts/little_loops/hooks/session_start.py:162,178`

### Tests

- `scripts/tests/test_session_discovery.py` — both-spellings probe case.
- `scripts/tests/test_ll_session.py` — `choices=` retrofit still locked by
  `TestArgumentParsing::test_backfill_host_choices_list`.
- New precedence tests for each of the 3 CLIs' `--host` flag (flag > env > union).
- Capturing-stub variant of `test_enh_3166_qwen_normalizer.py`'s `TestSessionStartHookPassesHost`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_session_start.py` (lines 273, 299, 312, 340) — `TestSessionStartBackfillSpawn`/`TestSessionStartRebuild` stub `get_project_folder` with a `lambda *a, **kw: ...` that discards all arguments; none assert the `host=` value received, the same blind spot as the one instance already named above. Not required for the single capturing-stub test in the Acceptance Criteria, but worth the same treatment if convenient.
- To exercise the `event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` fallback branch at `session_start.py:162/178`, the capturing-stub test must construct `LLHookEvent(host="", ...)` directly and call `handle()` — the direct-construction-then-`handle()` idiom is already the dominant pattern in this file (`test_hook_session_start.py:29,73,373` construct `LLHookEvent(host=..., intent="session_start", payload=...)` directly), but no existing test anywhere constructs `LLHookEvent` with a falsy `host`, so this is a genuinely new case, not a copy of an existing one.
- Model the new `REGISTERED_HOSTS` importability test on the existing `VALID_KINDS` re-export precedent: `test_session_store_schema.py:1012-1015` and `test_ll_session.py:191-193` both import the constant `from little_loops.session_store import ...` and assert plain membership (`"x" in CONST`), not order or exact-list identity — the same shape works for `REGISTERED_HOSTS`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/user_messages.py:442` (`get_sessions_folder`) — computes `effective_host = host if host is not None else os.environ.get("LL_HOOK_HOST", "claude-code")`, the identical flag-or-env-default shape as `get_project_folder` (lines 394-395, already known) in the same file `_resolve_host` is planned to live in. Not counted among the "three independently inlined copies" above — recommend also refactoring this line to call `_resolve_host(host)` for internal consistency once the helper exists.
- `scripts/little_loops/cli/logs.py:189-190` (`discover_all_projects`) and `:649` (`_collect_sequences`) — each independently reads `_os.environ.get("LL_HOOK_HOST", "claude-code")` inline, in the same file gaining the new `--host` flag on 9 subcommands. `discover_all_projects` already accepts `host: str | None = None` as a parameter but none of its 9 call sites (lines 664, 780, 1075, 1364, 1639, 2335, 2782, 3235) pass one; `_collect_sequences` has no `host` parameter at all. FYI only — threading a CLI-resolved host into either is session-enumeration routing, explicitly out of scope here per Scope Boundaries (deferred to ENH-3430).
- `scripts/little_loops/config/core.py:176` — reads `LL_HOOK_HOST` for a distinct concern (`.codex/ll-config.json`-style config-file discovery, not session/log discovery). Same env var, unrelated call path — no action needed, noted only to avoid confusion with the session-discovery seam.
- `scripts/little_loops/hooks/__init__.py:204` — `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), ...)` inside `main_hooks()`'s dispatch entry is the **sole** Python construction site of `LLHookEvent` (confirmed by repo-wide search); it is a 4th independently-inlined copy of the flag-or-env-default expression, upstream of `session_start.py:162/178`. Since `LLHookEvent.host` (`hooks/types.py:40`) is a required, non-Optional `str` field, `event.host` reaching `session_start.py` through this dispatcher is never falsy, so the planned `event.host or os.environ.get(...)` fallback only ever fires when a caller constructs `LLHookEvent` directly with a falsy `host` (tests do this — see Tests below). FYI only, no code change required here.
- `scripts/little_loops/fsm/continuity.py:43` (`project_folder = get_sessions_folder(working_dir or Path.cwd())`) — unhosted call site, not covered by any of ENH-3428/3429/3430 (none of the three blocked children are FSM continuity, only the three CLIs). Out of scope for this issue; flagged since no follow-up issue currently claims it.
- `scripts/little_loops/cli/ctx_stats.py:355` and `scripts/little_loops/cli/messages.py:173` — unhosted `get_sessions_folder(cwd)` / `get_project_folder(cwd)` call sites in the same two files gaining `--host` flag registration here. Parity with the already-noted `cli/logs.py` FYI entries — threading the CLI-resolved host into these calls is session-enumeration routing, deferred to ENH-3429 (ll-ctx-stats) and ENH-3428 (ll-messages) respectively.
- `scripts/little_loops/config-schema.json` (`hooks.host` enum, `["claude-code", "opencode", "codex"]`) — a different, pre-existing host enum (FEAT-1116 hook-intent adapter selection) unrelated to `REGISTERED_HOSTS`/`LL_HOOK_HOST`. Not read or written by anything in this issue; noted only as a naming-collision risk for anyone grepping the schema for "host" while implementing.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` has no `--host` row yet in the `ll-messages` flags table (lines 3580-3598), the `ll-ctx-stats` flags list (lines 473-479), or any of the 9 `ll-logs` subcommand flag tables gaining `--host` (`discover` 3640, `extract` 3653, `sequences` 3667, `stats` 3683, `dead-skills` 3695, `scan-failures` 3708, `eval-export` 3731, `loop-fleet` 3742, `fleet-review` 3757). Add a `--host HOST` row to each, matching the choices list already documented at line 3940 for `ll-session backfill --host`.
- `docs/reference/API.md:9557` states Claude Code resolution "reads `home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))` directly" — this becomes stale once the both-spellings probe lands (it will probe both the resolved and as-recorded spelling).
- No exhaustive flag-parity test exists (`test_wiring_cli_registry.py`/`test_wiring_reference_docs.py` only substring-check that CLI names appear in `docs/reference/CLI.md`, not full flag coverage) — skipping these doc updates won't fail CI, but will leave CLI.md/API.md inaccurate about the new public surface.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Refactor `get_sessions_folder`'s `effective_host` line (`user_messages.py:442`) to call the new `_resolve_host(host)` helper instead of duplicating the flag-or-env-default expression, once `_resolve_host` exists.
- Add a `--host HOST` row to `docs/reference/CLI.md`'s flag tables for `ll-messages`, `ll-ctx-stats`, and all 9 `ll-logs` subcommands gaining the flag.
- Update `docs/reference/API.md:9557`'s Claude Code resolution description to reflect the both-spellings probe.
- Use `sorted(REGISTERED_HOSTS)`, not `list(REGISTERED_HOSTS)`, for every new `--host` `choices=` list and the `cli/session.py:211-216` retrofit — `REGISTERED_HOSTS` is a `frozenset`, so `list()` iteration order varies per-process under Python's default hash randomization (`PYTHONHASHSEED`), making `--help` output and argparse's "choose from" error text non-deterministic across runs. No existing test pins order, but `sorted()` keeps user-facing output stable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed importers of `session_store/sessions.py` (needs the `REGISTERED_HOSTS` re-export too): `session_store/__init__.py:130` (existing `sessions` import block).
- Confirmed importers of `user_messages.py` (home of the new `_resolve_host` and existing `get_project_folder`): `session_store/sessions.py:44`, `session_log.py:15`, `fsm/continuity.py:22`, `cli/logs.py:35`, `cli/ctx_stats.py:34`, `cli/session.py:71`, and tests `test_ll_logs.py:60`, `test_session_log.py:19`, `test_fsm_continuity.py:16`, `test_cli_ctx_stats.py:32`, `test_cli_messages.py:26`, `test_user_messages.py:20`.
- Convention: shared per-subcommand argparse-flag helpers (`add_json_arg`, `add_window_args`, `add_corpus_target_args`) live in `scripts/little_loops/cli_args.py`, not inside the CLI module they're applied to, and each subparser calls the helper individually at its own registration site (`cli/logs.py:2932,2953,2959,...`) rather than looping over a collected parser list. The issue's suggested home for `_add_host_arg` (inside `cli/logs.py` itself) departs from this convention — a placement choice for the implementer, not resolved here.
- Convention: existing `choices=` lists sourced from a shared constant wrap it as `list(CONST)` (`cli/session.py:120,132` against `session_store/schema.py:27`'s `VALID_KINDS`) or `sorted(CONST)` (`cli/issues/create.py:516`). The current `ll-session backfill --host` choices list (`cli/session.py:213`) is the one site in the codebase that still hand-writes the literal instead of wrapping a constant — confirms the issue's premise for the retrofit.
- No flag>env precedence helper exists anywhere in the codebase today; three call sites independently inline the same `flag or os.environ.get("LL_HOOK_HOST", "claude-code")` expression: `cli/session.py:636`, `hooks/session_start.py:178`, and inside `get_project_folder` itself (`user_messages.py:394-395`) — no prior art `_resolve_host` would need to reconcile with.
- `cli/logs.py` has no `"digest"` subcommand/parser by that name today — the Scope Boundaries exclusion list ("not tail/diff/digest") names a subcommand that does not exist in this file; harmless (nothing to exclude), but there is no `digest_parser` to find.

## Acceptance Criteria

- `detect_sessions(cwd, "claude-code")` and the layout-host branch find a project folder encoded
  from either the resolved or the as-recorded spelling of `cwd`, asserted by a
  `test_session_discovery.py` case using a symlinked tmp dir.
- `REGISTERED_HOSTS` is importable from `little_loops.session_store` and is the `choices=` source
  for all three new `--host` flags and the retrofitted `ll-session backfill --host`.
- Host resolution on all three CLIs is `--host` > `LL_HOOK_HOST` > union (`None`), with a
  precedence test for each step; an invalid `--host` exits via argparse `SystemExit`. On `ll-logs`
  the flag is accepted by every one of the 9 named session-touching subcommands.
- `hooks/session_start.py:162` passes `host=` to `get_project_folder`, asserted by a
  capturing-stub test; `_backfill_host` (178) reuses the hoisted expression rather than
  duplicating it.
- No existing CLI behavior changes: the `--host` flags are additive and unconsumed by session
  enumeration until ENH-3428/3429/3430 land.

## Impact

- **Priority**: P2 - Foundation for three blocked children (ENH-3428/3429/3430); not itself
  user-facing until they land.
- **Effort**: Medium - Touches 6 files across `session_store`, three CLIs, and the session_start
  hook, but each change is additive (new flag/export/helper), not a rewrite.
- **Risk**: Low - No existing CLI behavior changes; `--host` flags are additive and unconsumed
  until the dependent children route through them.
- **Breaking Change**: No

## Dependencies

Blocks ENH-3428, ENH-3429, ENH-3430 (each consumes `_resolve_host`/`REGISTERED_HOSTS` from here).
Relates to ENH-3420 and FEAT-3417 (both `done`, built the underlying seam this issue's flags
resolve against).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-09T23:40:07 - `f26a7fac-7d40-43e0-b983-b0f480089473.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:24:12 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
- `/ll:confidence-check` - 2026-09-09T23:14:31 - `3b2ac682-44d5-44ea-8169-6d1077282b71.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T23:11:45 - `bdbe7e7e-9a12-43b3-8bee-5b8d90b97f70.jsonl`
- `/ll:wire-issue` - 2026-09-09T23:03:18 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T22:49:21 - `a5a46f1d-6d28-431d-9f96-7d68b9b6445d.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:42:52 - `b161ecdd-c676-4054-8cf9-0319c0089035.jsonl`
- `/ll:format-issue` - 2026-09-09T22:02:48 - `ede486c5-d33a-435b-bb10-2223277286b2.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:07 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
