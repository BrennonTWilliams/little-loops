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
verify_verdict: VALID
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

`detect_sessions`/`_project_folder_for_layout_host` **and** `get_project_folder` probe both the
resolved and as-recorded cwd spelling (resolved wins) via one shared spellings helper, so the
public seam and the session_start hook agree with `detect_sessions` on symlinked cwds.
`REGISTERED_HOSTS` (the existing ordered tuple, re-exported unchanged) is importable from
`little_loops.session_store` and sources the `choices=` list for `ll-messages --host`,
`ll-ctx-stats --host`, all 9 session-touching `ll-logs` subcommands' `--host`, and the retrofitted
`ll-session backfill --host` — all registered through one `add_host_arg(parser)` helper in
`cli_args.py`. Host resolution is `_resolve_host(flag, *, default=None)` = `--host` >
`LL_HOOK_HOST` env > `default` (`None` = union); the three-tier precedence is tested once on the
helper. Each CLI accepts the flag (every one of the 9 `ll-logs` subcommands) and rejects an invalid
value via argparse `SystemExit`. `hooks/session_start.py:162` passes `host=_resolve_host(event.host,
default="claude-code")` to `get_project_folder`, with `_backfill_host` (178) reusing the same
hoisted value; the other inlined flag-or-env-default copies (`user_messages.py:395,442`,
`cli/session.py:636`) collapse onto the same helper with `default="claude-code"`. No CLI's
session-enumeration behavior changes yet — the `--host` flags are additive and unconsumed until
ENH-3428/3429/3430 land.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Scope Boundaries

**In scope:**

1. **Both-spellings probe** (`session_store/sessions.py` **and** `user_messages.py`): the
   resolved-only encoding lives in exactly three places — `_detect_claude_sessions`
   (`sessions.py:245`), the opencode/pi/qwen branch of `_project_folder_for_layout_host`
   (`sessions.py:339`; the kimi/gemini/omp branches pass raw `cwd` to their probes and are
   unaffected), and the public `get_project_folder` (`user_messages.py:400`). Add one shared
   helper (e.g. `_cwd_spellings(cwd) -> list[str]`: `str(cwd.resolve())` first,
   `str(cwd.absolute())` second — `absolute()` rather than `str(cwd)` so a relative `Path`
   argument doesn't encode a relative fragment; it never resolves symlinks — deduped when equal)
   and apply it at all three sites — probe each spelling in order, first hit wins. Mirrors what
   the codex path already does (`sessions.py:131` DB match, `:174` scan match).
   **Scope inside `get_project_folder`**: the single `path_str` at line 400 feeds the
   `claude-code`, `opencode`, `pi`, and `qwen` branches (and `codex`, which returns `None`
   regardless). The probe must loop spellings for **every** encoded-path branch, not just
   `claude-code` — otherwise `_project_folder_for_layout_host`'s opencode/pi/qwen probe (which
   does get the loop) and `get_project_folder`'s would disagree, breaking the docstring's
   "matches that public seam exactly" promise. Restructure as: for each spelling, encode, call
   the host's probe, return the first non-`None`.
   Covering `get_project_folder` too is deliberate: `_project_folder_for_layout_host`'s docstring
   promises it "matches that public seam exactly", and the session_start hook plus every
   pre-ENH-3430 `ll-logs` call site still go through `get_project_folder` — leaving it
   resolved-only would make `detect_sessions` and the hook disagree on symlinked cwds. This is a
   prerequisite for `TestDiscover` passing on macOS in ENH-3430, since `test_ll_logs.py:109`'s
   `_make_project_dir` helper encodes an unresolved path. Add a `test_session_discovery.py` case:
   a Claude project dir encoded from an unresolved symlinked cwd is found by
   `detect_sessions(unresolved_cwd, "claude-code", home=...)`, and a `test_user_messages.py` case
   for the same via `get_project_folder(unresolved_cwd, host="claude-code")` (patch `Path.home`).
2. **`REGISTERED_HOSTS` export**: re-export `sessions._REGISTERED_HOSTS` (268-277) as
   `REGISTERED_HOSTS` from `little_loops.session_store` (add to `__all__`) so every `--host` flag's
   `choices=` sources from one place instead of copied literals. It is an **ordered tuple**
   (`claude-code` first — identical order to the hand-written list at `cli/session.py:213`), not a
   frozenset; re-export it unchanged and wrap as `list(REGISTERED_HOSTS)`, the `VALID_KINDS`
   precedent (`cli/session.py:120,132`). Do **not** `sorted()` it — that would alphabetize the
   existing `ll-session backfill --help` output, a visible change to the one CLI this issue
   promises stays untouched.
3. **`_resolve_host` helper** (new, `user_messages.py` beside `get_project_folder`):
   `_resolve_host(flag: str | None, *, default: str | None = None) -> str | None` =
   `flag or os.environ.get("LL_HOOK_HOST") or default`. The three CLIs call it with the default
   `None`, meaning union across all registered hosts. The `default` kwarg exists because the
   single-host sites (`get_project_folder:394-395`, `get_sessions_folder:442`,
   `session_start.py:178`, `cli/session.py:636`) fall back to `"claude-code"`, not union —
   `get_sessions_folder` feeds the result straight into `host_layout_for`, which cannot take
   `None`. Collapse all four onto `_resolve_host(x, default="claude-code")` so the codebase has one
   precedence expression. Docstring note: `LL_HOOK_HOST` is exported only by the hook adapter
   shims into the hook subprocess environment, so the env tier effectively never fires for an
   interactive CLI run — it exists for automation contexts that inherit that env.
   **Typing (mypy)**: a flat `-> str | None` return fails `python -m mypy` at all three
   `default="claude-code"` callers — `cli/session.py:636` annotates `_backfill_host: str`,
   `get_sessions_folder` passes the result to `host_layout_for(host: str)`
   (`writers.py:2527`, call at `user_messages.py:448`), and `session_start.py:179` extends a
   `list[str]` with it. Declare the helper with `typing.overload`: `(flag, *, default: str) ->
   str` and `(flag, *, default: None = None) -> str | None`, so single-host callers get a plain
   `str` without an `assert`/`cast` at each site.
4. **`--host` flag on all three CLIs**, default `None`, `choices=list(REGISTERED_HOSTS)`, registered
   through one public `add_host_arg(parser: argparse.ArgumentParser) -> None` helper in
   `scripts/little_loops/cli_args.py` (every existing sibling — `add_json_arg`, `add_window_args`,
   `add_corpus_target_args` — is a public `add_*_arg` there, so no underscore and not inside
   `cli/logs.py`). One helper = one choices source across all four consumers. Two constraints on
   the helper itself:
   - **Help text must be parameterised**: `ll-session backfill` defaults to `"claude-code"`
     (single host) while the three new CLIs default to union, so a single hard-coded help string
     is wrong for one of them. Give the helper a `help_text` kwarg with a union-accurate default
     (e.g. "Restrict to one host (default: LL_HOOK_HOST if set, else all registered hosts)"), the
     same shape as `add_json_arg(parser, help_text=...)` (`cli_args.py:324`) and
     `add_skip_arg(parser, help_text=...)` (`cli_args.py:57`); the backfill retrofit passes its
     existing wording.
   - **Lazy-import `REGISTERED_HOSTS` inside the function body**, not at `cli_args.py` module
     level. `cli_args.py` has zero `little_loops` imports today and 53 importers; a top-level
     `from little_loops.session_store import REGISTERED_HOSTS` would pull sqlite, `writers.py`,
     and `host_runner` into every CLI's startup path. Precedent: `user_messages.py:446` already
     lazy-imports `host_layout_for` from `session_store` for the same reason.
   - `ll-messages` and `ll-ctx-stats` are flat parsers — call the helper on the top-level parser.
   - `ll-logs` is a subparser CLI; call the helper at each of the 9 session-touching subcommands'
     registration sites (`discover`, `extract`, `sequences`, `stats`, `scan-failures`,
     `dead-skills`, `eval-export`, `loop-fleet`, `fleet-review`) — not `tail` (loop log files) or
     `diff` (resolves sessions via the history DB `sessions` table, `_resolve_session_log` 1697,
     never via project-folder discovery). ENH-3430 reads `getattr(args, "host", None)`, so
     subcommands without the flag stay safe.
   - Retrofit `cli/session.py:211-216`'s hand-written 8-item `choices=` list to the same helper,
     so it can't drift from the seam (the help text may change wording; the choices order does not).
5. **`hooks/session_start.py:162`**: hoist `_backfill_host = _resolve_host(event.host,
   default="claude-code")` above line 162, pass `host=_backfill_host` to `get_project_folder(cwd)`,
   and reuse it at 178 rather than duplicating the literal. (`LLHookEvent.host` is a required
   non-Optional `str`, so the `event.host or ...` fallback only fires for tests that construct the
   event with `host=""` — keep it for parity with the existing line 178.) Add a capturing-stub test
   asserting `get_project_folder`'s call receives a `host=` kwarg (model on
   `test_enh_3166_qwen_normalizer.py:577-638`'s `TestSessionStartHookPassesHost`, which uses a
   `*a, **kw`-swallowing lambda today and needs a capturing variant).
6. **Tests for resolution and flag registration**: the flag is inert on every CLI until
   ENH-3428/3429/3430 consume it, so there is nothing observable at the CLI level to assert
   precedence against. Test the three tiers **once**, directly on `_resolve_host` (flag beats env,
   env beats default, neither → default; plus `default="claude-code"` returning that). Per CLI
   (`ll-logs` × 9 subcommands, `ll-messages`, `ll-ctx-stats`, `ll-session backfill`), test only:
   `--host codex` parses and populates `args.host`, and an invalid value raises `SystemExit` —
   model on `test_ll_session.py::TestArgumentParsing::test_backfill_host_choices_list` (41-61).
   CLI-level precedence assertions (resolved host reaching `detect_sessions`) belong to the three
   children.

**Out of scope:** actually routing any CLI's session enumeration through `detect_sessions`/
`iter_events` — that is ENH-3428 (ll-messages), ENH-3429 (ll-ctx-stats), and ENH-3430 (ll-logs).
The `--host` flags added here are inert until those children consume the resolved host.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Naming collision to avoid: `host_runner.py:2292` already defines a **public** `resolve_host(env=None) -> HostRunner` — orchestration host-CLI resolution, an unrelated concept from this issue's new **private** `_resolve_host(flag) -> str | None` (session-discovery host resolution). `test_host_runner.py`'s `TestResolveHost` class covers the existing one; keep the new function's tests, docstring, and any prose clearly distinct from that name.
- `host_runner.py:2292`'s `resolve_host()` is the only existing precedence resolver in the codebase whose docstring states precedence as a numbered list — the closest available shape precedent for `_resolve_host`'s docstring. It reads env only (no `flag` parameter), consistent with the issue's own finding that no prior function here takes an explicit flag argument for this kind of precedence.
- Every existing shared argparse-flag helper (`add_json_arg`, `add_window_args`, `add_corpus_target_args`, `cli_args.py`) is named **without** a leading underscore and lives in `cli_args.py`, not beside its consuming CLI module. Resolved (review 2026-09-09): the helper is `add_host_arg` in `cli_args.py`, matching every sibling.
- `choices=` wrapper convention tracks the constant's container type: `list(CONST)` appears only where CONST is an ordered sequence (`VALID_KINDS`, `cli/session.py:120,132`); `sorted(CONST)` appears where CONST is a `set`/`frozenset` (`VALID_PRIORITIES` at `cli/issues/create.py:516`; `_DEFERRAL_REASON_CODES | _CLOSED_REASON_CODES` at `cli/issues/__init__.py:883`). Corrected (review 2026-09-09): `sessions._REGISTERED_HOSTS` is an ordered **tuple** (`sessions.py:268-277`), not a frozenset, so the matching precedent is `list(VALID_KINDS)`.
- Package-constant re-export precedent: `session_store/__init__.py:112-119,202-205` re-exports `VALID_KINDS` from `schema.py` by importing it by name into the package's multi-line `from ... import (...)` block and listing it in `__all__` at the same relative position. `session_store/__init__.py:130-144` already has an adjacent `from little_loops.session_store.sessions import (...)` block — the natural site to extend for `REGISTERED_HOSTS`.
- Capturing-stub tests for a specific kwarg reaching a mocked function have no single canonical shape in this codebase — four distinct capture-container idioms coexist: `dict.update(kwargs)` (`test_fsm_runners.py:639`), `list.append(dict)` (`test_prepatch_check.py:461`), `dict[key] = value` (`test_feat3310_artifact_extract.py:281`), and the `_FakePopen.__init__`-args-list variant used by the issue's own named precedent (`test_enh_3166_qwen_normalizer.py:581`).
- Precedence-test structuring also has two coexisting shapes: one test method per tier inside a class (`test_host_runner.py:381` `TestResolveHost`), and one test function per tier at module level named `test_..._<tier>_wins`/`..._beats_...` (`test_enh_3171_mcp_project_root.py:65`, `test_feat3310_artifact_extract.py:281`). Neither is dominant — an open choice for whichever of the 3 new CLI precedence tests get written.
- Confirmed via repo-wide search: `add_host_arg` and a public (non-underscore) `REGISTERED_HOSTS` do not exist anywhere in the tree yet — both are genuinely new symbols, no existing partial implementation to reconcile with. `_REGISTERED_HOSTS` has no importers outside `sessions.py`.

## Program Design

### Types

- No new data types — `_resolve_host` returns the existing `str | None` host-id shape used
  throughout `session_store`.

### Signatures

- `_resolve_host(flag: str | None, *, default: str | None = None) -> str | None` (new,
  `user_messages.py`) — `flag or os.environ.get("LL_HOOK_HOST") or default`; declared via two
  `@overload`s so `default: str` narrows the return to `str` (see Scope Boundaries item 3)
- `_cwd_spellings(cwd: Path) -> list[str]` (new, `user_messages.py`; imported by `sessions.py`) —
  `[str(cwd.resolve()), str(cwd.absolute())]` deduped, resolved first
- `add_host_arg(parser: argparse.ArgumentParser, *, help_text: str = <union default>) -> None`
  (new, `cli_args.py`; lazy-imports `REGISTERED_HOSTS` in the body)
- `REGISTERED_HOSTS: tuple[str, ...]` (re-exported unchanged, `session_store/__init__.py`, sourced
  from `sessions._REGISTERED_HOSTS`)

### Call Path

`ll-messages`/`ll-ctx-stats`/`ll-logs`/`ll-session backfill` argparse setup -> `add_host_arg`
(`choices=list(REGISTERED_HOSTS)`) -> `args.host` (unconsumed on the three CLIs until
ENH-3428/3429/3430; `cli/session.py:636` consumes it via `_resolve_host(args.host,
default="claude-code")`). `hooks/session_start.py:162` -> `_resolve_host(event.host,
default="claude-code")` -> `get_project_folder(cwd, host=...)` -> `_cwd_spellings` probe.
`detect_sessions` -> `_detect_claude_sessions` / `_project_folder_for_layout_host` -> the same
`_cwd_spellings` probe.

## Files to Modify

- `scripts/little_loops/session_store/sessions.py` (`_detect_claude_sessions` 245,
  `_project_folder_for_layout_host` 339 — both-spellings probe; docstrings at 239-244 and
  332-337; `detect_sessions` docstring 301-304 justifies the union default with "none of the
  eventual consumers has a `--host` flag" — reword now that they do)
- `scripts/little_loops/session_store/__init__.py` (`REGISTERED_HOSTS` re-export + `__all__`)
- `scripts/little_loops/user_messages.py` (new `_resolve_host` and `_cwd_spellings` helpers;
  `get_project_folder:394-395,400` and `get_sessions_folder:442` refactored onto them)
- `scripts/little_loops/cli_args.py` (new `add_host_arg` helper)
- `scripts/little_loops/cli/messages.py`, `scripts/little_loops/cli/ctx_stats.py`,
  `scripts/little_loops/cli/logs.py` (flag registration only, via `add_host_arg`)
- `scripts/little_loops/cli/session.py:211-216` (retrofit to `add_host_arg`), `:636`
  (`_resolve_host(args.host, default="claude-code")`)
- `scripts/little_loops/hooks/session_start.py:162,178`

### Tests

- `scripts/tests/test_session_discovery.py` — both-spellings probe case via `detect_sessions`.
- `scripts/tests/test_user_messages.py` — both-spellings probe case via `get_project_folder`;
  `_resolve_host` three-tier precedence + `default=` behaviour.
- `scripts/tests/test_ll_session.py` — `choices=` retrofit still locked by
  `TestArgumentParsing::test_backfill_host_choices_list`.
- Per-CLI flag-registration tests (`ll-messages`, `ll-ctx-stats`, all 9 `ll-logs` subcommands):
  `--host codex` parses; invalid value → `SystemExit`. No CLI-level precedence tests here (flag is
  inert until the children consume it).
- Capturing-stub variant of `test_enh_3166_qwen_normalizer.py`'s `TestSessionStartHookPassesHost`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_session_start.py` (lines 273, 299, 312, 340) — `TestSessionStartBackfillSpawn`/`TestSessionStartRebuild` stub `get_project_folder` with a `lambda *a, **kw: ...` that discards all arguments; none assert the `host=` value received, the same blind spot as the one instance already named above. Not required for the single capturing-stub test in the Acceptance Criteria, but worth the same treatment if convenient.
- To exercise the `event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` fallback branch at `session_start.py:162/178`, the capturing-stub test must construct `LLHookEvent(host="", ...)` directly and call `handle()` — the direct-construction-then-`handle()` idiom is already the dominant pattern in this file (`test_hook_session_start.py:29,73,373` construct `LLHookEvent(host=..., intent="session_start", payload=...)` directly), but no existing test anywhere constructs `LLHookEvent` with a falsy `host`, so this is a genuinely new case, not a copy of an existing one.
- Model the new `REGISTERED_HOSTS` importability test on the existing `VALID_KINDS` re-export precedent: `test_session_store_schema.py:1012-1015` and `test_ll_session.py:191-193` both import the constant `from little_loops.session_store import ...` and assert plain membership (`"x" in CONST`), not order or exact-list identity — the same shape works for `REGISTERED_HOSTS`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/user_messages.py:442` (`get_sessions_folder`) — computes `effective_host = host if host is not None else os.environ.get("LL_HOOK_HOST", "claude-code")`, the identical flag-or-env-default shape as `get_project_folder` (lines 394-395, already known) in the same file `_resolve_host` is planned to live in. Refactor to `_resolve_host(host, default="claude-code")` — **not** the bare `_resolve_host(host)`, which would return `None` with no env set and break the `host_layout_for(effective_host)` call on line 448.
- `scripts/little_loops/cli/logs.py:189-190` (`discover_all_projects`) and `:649` (`_collect_sequences`) — each independently reads `_os.environ.get("LL_HOOK_HOST", "claude-code")` inline, in the same file gaining the new `--host` flag on 9 subcommands. `discover_all_projects` already accepts `host: str | None = None` as a parameter but none of its 9 call sites (lines 664, 780, 1075, 1364, 1639, 2335, 2782, 3235) pass one; `_collect_sequences` has no `host` parameter at all. FYI only — threading a CLI-resolved host into either is session-enumeration routing, explicitly out of scope here per Scope Boundaries (deferred to ENH-3430).
- `scripts/little_loops/config/core.py:176` — reads `LL_HOOK_HOST` for a distinct concern (`.codex/ll-config.json`-style config-file discovery, not session/log discovery). Same env var, unrelated call path — no action needed, noted only to avoid confusion with the session-discovery seam.
- `scripts/little_loops/hooks/__init__.py:204` — `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), ...)` inside `main_hooks()`'s dispatch entry is the **sole** Python construction site of `LLHookEvent` (confirmed by repo-wide search); it is a 4th independently-inlined copy of the flag-or-env-default expression, upstream of `session_start.py:162/178`. Since `LLHookEvent.host` (`hooks/types.py:40`) is a required, non-Optional `str` field, `event.host` reaching `session_start.py` through this dispatcher is never falsy, so the planned `event.host or os.environ.get(...)` fallback only ever fires when a caller constructs `LLHookEvent` directly with a falsy `host` (tests do this — see Tests below). FYI only, no code change required here.
- `scripts/little_loops/fsm/continuity.py:43` (`project_folder = get_sessions_folder(working_dir or Path.cwd())`) — unhosted call site, not covered by any of ENH-3428/3429/3430 (none of the three blocked children are FSM continuity, only the three CLIs). Out of scope for this issue; flagged since no follow-up issue currently claims it.
- `scripts/little_loops/cli/ctx_stats.py:355` and `scripts/little_loops/cli/messages.py:173` — unhosted `get_sessions_folder(cwd)` / `get_project_folder(cwd)` call sites in the same two files gaining `--host` flag registration here. Parity with the already-noted `cli/logs.py` FYI entries — threading the CLI-resolved host into these calls is session-enumeration routing, deferred to ENH-3429 (ll-ctx-stats) and ENH-3428 (ll-messages) respectively.
- `scripts/little_loops/config-schema.json` (`hooks.host` enum, `["claude-code", "opencode", "codex"]`) — a different, pre-existing host enum (FEAT-1116 hook-intent adapter selection) unrelated to `REGISTERED_HOSTS`/`LL_HOOK_HOST`. Not read or written by anything in this issue; noted only as a naming-collision risk for anyone grepping the schema for "host" while implementing.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` has no `--host` row yet in the `ll-messages` flags table (lines 3580-3598), the `ll-ctx-stats` flags list (lines 473-479), or any of the 9 `ll-logs` subcommand flag tables gaining `--host` (`discover` 3640, `extract` 3653, `sequences` 3667, `stats` 3683, `dead-skills` 3695, `scan-failures` 3708, `eval-export` 3731, `loop-fleet` 3742, `fleet-review` 3757). Add a `--host HOST` row to each, matching the choices list already documented at line 3940 for `ll-session backfill --host`.
- `docs/reference/API.md:9608` states Claude Code resolution "reads `home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))` directly" — this becomes stale once the both-spellings probe lands (it will probe both the resolved and as-recorded spelling). The `get_project_folder` docstring in API.md needs the same update since the probe now covers it too.
- No exhaustive flag-parity test exists (`test_wiring_cli_registry.py`/`test_wiring_reference_docs.py` only substring-check that CLI names appear in `docs/reference/CLI.md`, not full flag coverage) — skipping these doc updates won't fail CI, but will leave CLI.md/API.md inaccurate about the new public surface.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Refactor the four inlined flag-or-env-default copies (`user_messages.py:394-395,442`, `cli/session.py:636`, `hooks/session_start.py:178`) onto `_resolve_host(x, default="claude-code")` once the helper exists — each keeps its `"claude-code"` fallback, never the union default.
- Add a `--host HOST` row to `docs/reference/CLI.md`'s flag tables for `ll-messages`, `ll-ctx-stats`, and all 9 `ll-logs` subcommands gaining the flag.
- Update `docs/reference/API.md:9608`'s Claude Code resolution description to reflect the both-spellings probe.
- Use `list(REGISTERED_HOSTS)` for every `--host` `choices=` list (via `add_host_arg`) — the constant is an ordered tuple, so iteration order is deterministic and preserves the existing `ll-session backfill --help` ordering. (An earlier wiring pass mandated `sorted()` on the mistaken premise that it was a frozenset; withdrawn.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed importers of `session_store/sessions.py` (needs the `REGISTERED_HOSTS` re-export too): `session_store/__init__.py:130` (existing `sessions` import block).
- Confirmed importers of `user_messages.py` (home of the new `_resolve_host` and existing `get_project_folder`): `session_store/sessions.py:44`, `session_log.py:15`, `fsm/continuity.py:22`, `cli/logs.py:35`, `cli/ctx_stats.py:34`, `cli/session.py:71`, and tests `test_ll_logs.py:60`, `test_session_log.py:19`, `test_fsm_continuity.py:16`, `test_cli_ctx_stats.py:32`, `test_cli_messages.py:26`, `test_user_messages.py:20`.
- Convention: shared per-subcommand argparse-flag helpers (`add_json_arg`, `add_window_args`, `add_corpus_target_args`) live in `scripts/little_loops/cli_args.py`, not inside the CLI module they're applied to, and each subparser calls the helper individually at its own registration site (`cli/logs.py:2932,2953,2959,...`) rather than looping over a collected parser list. Resolved: `add_host_arg` lives in `cli_args.py` and is called per registration site.
- Convention: existing `choices=` lists sourced from a shared constant wrap it as `list(CONST)` (`cli/session.py:120,132` against `session_store/schema.py:27`'s `VALID_KINDS`) or `sorted(CONST)` (`cli/issues/create.py:516`). The current `ll-session backfill --host` choices list (`cli/session.py:213`) is the one site in the codebase that still hand-writes the literal instead of wrapping a constant — confirms the issue's premise for the retrofit.
- No flag>env precedence helper exists anywhere in the codebase today; three call sites independently inline the same `flag or os.environ.get("LL_HOOK_HOST", "claude-code")` expression: `cli/session.py:636`, `hooks/session_start.py:178`, and inside `get_project_folder` itself (`user_messages.py:394-395`) — no prior art `_resolve_host` would need to reconcile with.

## Acceptance Criteria

- `detect_sessions(cwd, "claude-code")`, the opencode/pi/qwen layout-host branch, and
  `get_project_folder(cwd, host="claude-code")` each find a project folder encoded from either the
  resolved or the as-recorded spelling of `cwd` (resolved probed first), asserted by a
  `test_session_discovery.py` case and a `test_user_messages.py` case using a symlinked tmp dir.
- `REGISTERED_HOSTS` is importable from `little_loops.session_store`, is the same ordered tuple as
  `sessions._REGISTERED_HOSTS`, and is the `choices=` source (via `cli_args.add_host_arg`) for all
  three new `--host` flags and the retrofitted `ll-session backfill --host`, whose `--help` choices
  order is unchanged.
- `_resolve_host(flag, *, default=None)` resolves `--host` > `LL_HOOK_HOST` > `default`, with a
  test per tier plus one for `default="claude-code"`. Every one of the 9 named `ll-logs`
  subcommands, `ll-messages`, and `ll-ctx-stats` accepts `--host <registered>` and rejects an
  invalid value via argparse `SystemExit`.
- `hooks/session_start.py:162` passes `host=` to `get_project_folder`, asserted by a
  capturing-stub test; `_backfill_host` (178) reuses the hoisted value rather than duplicating it.
  `user_messages.py:394-395,442` and `cli/session.py:636` no longer inline the
  flag-or-env-default expression (grep for `LL_HOOK_HOST", "claude-code"` in those files is empty).
- No existing CLI behavior changes: the `--host` flags are additive and unconsumed by session
  enumeration until ENH-3428/3429/3430 land; every single-host fallback still resolves to
  `"claude-code"` with no flag and no env.

## Impact

- **Priority**: P2 - Foundation for three blocked children (ENH-3428/3429/3430); not itself
  user-facing until they land.
- **Effort**: Medium - Touches 8 files across `session_store`, `user_messages`, `cli_args`, three
  CLIs plus `ll-session`, and the session_start hook, but each change is additive (new
  flag/export/helper) or a same-behavior refactor onto the helper, not a rewrite.
- **Risk**: Low - No existing CLI behavior changes; `--host` flags are additive and unconsumed
  until the dependent children route through them.
- **Breaking Change**: No

## Dependencies

Blocks ENH-3428, ENH-3429, ENH-3430 (each consumes `_resolve_host`/`REGISTERED_HOSTS` from here).
Relates to ENH-3420 and FEAT-3417 (both `done`, built the underlying seam this issue's flags
resolve against).

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (correction below applied in the same pass, so the
issue as it now reads is up to date — this section is a record of what was wrong and fixed, not
an outstanding action item).

- Graph: provider=`codegraph` freshness=`stale` — not relied on for the checks below beyond a
  lead; all findings were confirmed by direct file/grep reads.
- Every file/line citation checked (`sessions.py:236-288,331-352`, `user_messages.py:373-448`,
  `session_store/__init__.py:108-144,202-205`, `cli/session.py:205-217,628-636`,
  `hooks/session_start.py:150-190`, `hooks/__init__.py:198-208`, `fsm/continuity.py:38-46`,
  `cli/ctx_stats.py:350-358`, `cli/messages.py:168-176`, `config/core.py:170-180`,
  `config-schema.json:1562` for the `hooks.host` enum, `host_runner.py:2292` for `resolve_host`)
  matched the current code exactly, including negative claims (`REGISTERED_HOSTS`/`add_host_arg`
  confirmed absent everywhere, no `"digest"` subcommand in `cli/logs.py`).
- One citation was wrong: Scope Boundaries item 6 modeled the per-CLI flag test on
  `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list` — no `TestBackfillArgs`
  class exists in that file; the test lives under `TestArgumentParsing` (confirmed both by the
  file itself and by the Tests section two paragraphs below, which already cited it correctly).
  Corrected in place.
- `ll-verify-evidence` returned clean (no fabricated evidence spans). No active required decision
  rules exist to check against. Dependency references (`blocked_by`/`blocks`/parent) all resolve
  and backlink correctly with ENH-3419/3428/3429/3430.

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-10T00:40:45 - `71fb98cc-4ad6-4857-8a2d-91b008deb266.jsonl`
- manual review - 2026-09-09 - added `@overload` typing for `_resolve_host` (mypy at the three `default="claude-code"` callers); `add_host_arg` gets a `help_text` kwarg and lazy-imports `REGISTERED_HOSTS` (keeps `cli_args.py` a leaf); both-spellings probe explicitly covers every encoded-path branch of `get_project_folder`; `_cwd_spellings` uses `absolute()` for the second spelling; `detect_sessions` docstring 301-304 added to Files to Modify; dropped dangling `digest` finding
- `/ll:verify-issues` - 2026-09-10T00:15:40 - `8cef5fbd-618e-46ee-a7cc-dbfb9095952c.jsonl`
- manual review - 2026-09-09 - corrected `REGISTERED_HOSTS` type (tuple, drop `sorted()`); added `default=` to `_resolve_host` so single-host sites don't fall to union; replaced untestable per-CLI precedence ACs with helper-level tests + per-CLI registration tests; resolved `add_host_arg` placement to `cli_args.py`; extended both-spellings probe to `get_project_folder` via shared `_cwd_spellings`; fixed API.md line ref (9608)
- `/ll:wire-issue` - 2026-09-09T23:40:07 - `f26a7fac-7d40-43e0-b983-b0f480089473.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:24:12 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
- `/ll:confidence-check` - 2026-09-09T23:14:31 - `3b2ac682-44d5-44ea-8169-6d1077282b71.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T23:11:45 - `bdbe7e7e-9a12-43b3-8bee-5b8d90b97f70.jsonl`
- `/ll:wire-issue` - 2026-09-09T23:03:18 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T22:49:21 - `a5a46f1d-6d28-431d-9f96-7d68b9b6445d.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:42:52 - `b161ecdd-c676-4054-8cf9-0319c0089035.jsonl`
- `/ll:format-issue` - 2026-09-09T22:02:48 - `ede486c5-d33a-435b-bb10-2223277286b2.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:07 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
