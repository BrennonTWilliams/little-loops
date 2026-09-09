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

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Scope

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
- New precedence tests for each of the 3 CLIs' `--host` flag (flag > env > union).
- Capturing-stub variant of `test_enh_3166_qwen_normalizer.py`'s `TestSessionStartHookPassesHost`.

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

## Dependencies

Blocks ENH-3428, ENH-3429, ENH-3430 (each consumes `_resolve_host`/`REGISTERED_HOSTS` from here).
Relates to ENH-3420 and FEAT-3417 (both `done`, built the underlying seam this issue's flags
resolve against).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-09T21:57:07 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
