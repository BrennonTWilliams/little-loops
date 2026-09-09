---
id: ENH-3427
type: ENH
title: Host-resolution seam — --host flag, both-spellings probe, and session_start host injection
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
  `TestBackfillArgs::test_backfill_host_choices_list`.
  > ⚠ Superseded — class is `TestArgumentParsing`, not `TestBackfillArgs`
- New precedence tests for each of the 3 CLIs' `--host` flag (flag > env > union).
- Capturing-stub variant of `test_enh_3166_qwen_normalizer.py`'s `TestSessionStartHookPassesHost`.

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
- `/ll:refine-issue` - 2026-09-09T22:42:52 - `b161ecdd-c676-4054-8cf9-0319c0089035.jsonl`
- `/ll:format-issue` - 2026-09-09T22:02:48 - `ede486c5-d33a-435b-bb10-2223277286b2.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:07 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
