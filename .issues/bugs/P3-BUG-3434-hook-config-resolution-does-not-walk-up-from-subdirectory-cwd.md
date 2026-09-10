---
id: BUG-3434
type: BUG
title: Hook config resolution does not walk up from subdirectory cwd
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T19:27:53Z'
---

# BUG-3434: Hook config resolution does not walk up from subdirectory cwd

## Summary

`user_prompt_submit.handle()` (scripts/little_loops/hooks/user_prompt_submit.py:97-98) and
`session_start.py` (lines 73, 94, 105) both call `resolve_config_path(Path.cwd())` directly.
`resolve_config_path()` (scripts/little_loops/config/core.py:157-181) only checks
`<project_root>/.ll/ll-config.json` (and host-specific variants) under the exact path passed
in — it does not walk up parent directories. This is unlike `find_project_root()`
(scripts/little_loops/paths.py:14-42), which walks up to the nearest ancestor with both
`.ll/` and `.git`, and is the pattern used elsewhere in the codebase for cwd resolution.

Consequence: if the tool's cwd is left inside a subdirectory of the project (e.g. after a
`cd scripts/` for a build step) when a UserPromptSubmit hook fires, `resolve_config_path`
looks for `.ll/ll-config.json` directly under that subdirectory. If none exists there — even
though the real project root two levels up has one — `_load_config` returns `None`, and:

1. The hook prints the false warning `[little-loops] No config found. Run ll-init to set up
   little-loops for this project.` even though the project *is* configured.
2. `analytics_active` becomes `False`, so `record_correction`, `record_skill_event`, and
   `record_prompt_opt_event` are all silently skipped for that turn — real data loss, not just
   a cosmetic message.
3. `handle()` returns early at line 142 before ever checking `prompt_optimization.enabled`,
   so prompt optimization is silently disabled for that turn regardless of config.

Reproduced live in little-loops' own repo: after running `hatch build`/`hatch publish` from
`scripts/` (which has a stray `.ll/` holding only `ll-doc-drift-state.json`, no
`ll-config.json`), the next prompt submitted with cwd still at `scripts/` triggered the false
warning. The repo's real config is at `.ll/ll-config.json` two directories up.

## Current Behavior

`user_prompt_submit.handle()` and `session_start.py`'s config-build path call
`resolve_config_path(Path.cwd())` directly. `resolve_config_path()` only checks
`<project_root>/.ll/ll-config.json` (and host-specific variants) under the exact
path passed in — it does not walk up parent directories. If cwd is left inside a
subdirectory of the project (e.g. after a `cd scripts/` for a build step) when a
hook fires, config resolution looks for `.ll/ll-config.json` directly under that
subdirectory instead of the real project root above it.

## Expected Behavior

Hook config resolution should walk up from cwd to the project root before
looking for `.ll/ll-config.json`, consistent with `find_project_root()`
(scripts/little_loops/paths.py:14), which is the pattern used elsewhere in the
codebase for cwd resolution. A subdirectory cwd should resolve the same config
as the project root.

**Known limitation (by design, not a regression)**: `find_project_root()` only
returns a root when an existing `.ll/` directory is found on the walk. A
host-only project whose config lives only under a host state dir (the
`.codex`/`.gemini`/`.omp`/`.kimi-code`/`.qwen` variants that
`_config_candidates` probes) and has no `.ll/` still resolves to `None`, and the hooks fall back to the
bare cwd — exactly today's behavior. The walk-up is `.ll`-gated; extending it
to host state dirs is out of scope here.

## Motivation

- Silent false warning: the hook prints `[little-loops] No config found. Run
  ll-init to set up little-loops for this project.` even though the project
  *is* configured, eroding trust in the tool's own diagnostics.
- Real data loss: `analytics_active` becomes `False` when config resolution
  fails, so `record_correction`, `record_skill_event`, and
  `record_prompt_opt_event` are silently skipped for that turn — not just a
  cosmetic message.
- Silent feature disablement: `handle()` returns early before checking
  `prompt_optimization.enabled`, so prompt optimization is silently disabled
  for that turn regardless of config, with no indication to the user.

## Root Cause

- **File**: `scripts/little_loops/hooks/user_prompt_submit.py`
- **Anchor**: in `handle()` (line 97-98), via `_load_config()` (line 55-63)
- **Cause**: `_load_config(cwd)` passes `cwd` straight into
  `resolve_config_path(cwd)` (scripts/little_loops/config/core.py:157) without
  first resolving it to the project root via `find_project_root()`.
  `scripts/little_loops/hooks/session_start.py` has the identical pattern at
  lines 73/94/105 but is less exposed since SessionStart normally fires once
  at session launch when cwd is still the project root.
- **Dispatcher shares the gap**: `main_hooks()` (scripts/little_loops/hooks/__init__.py:207-215)
  sets `event.cwd = os.getcwd()` and gates hook telemetry on
  `_hooks_telemetry_enabled(cwd)` → `resolve_config_path(cwd)` with no walk-up,
  so `hook_event_context` telemetry is also silently skipped from a subdirectory.
- **Both target hooks ignore `event.cwd`**: the other six hooks in the package
  follow `cwd = Path(event.cwd) if event.cwd else Path.cwd()`; `user_prompt_submit`
  and `session_start` call `Path.cwd()` directly. Today `event.cwd` and
  `Path.cwd()` are the same value, so this is a consistency/testability gap, not
  a separate defect.

## Proposed Solution

Add one shared helper in the hooks package and route every `hooks/`
`resolve_config_path` call site through it, following the codebase's
`find_project_root` convention (bind to `root`, explicit `None` guard):

```python
# scripts/little_loops/hooks/__init__.py (or a small hooks/_root.py)
from little_loops.paths import find_project_root

def resolve_hook_root(event: LLHookEvent) -> Path:
    """Project root for a hook invocation; falls back to the raw cwd."""
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    root = find_project_root(cwd)
    if root is None:
        return cwd
    return root
```

Then in each handler:

```python
root = resolve_hook_root(event)
config = _load_config(root)
```

**Scope decision (recorded)**: use `root` for *every* downstream path in
`user_prompt_submit.py` and `session_start.py`, not only the
`resolve_config_path` argument. Rationale:

- `history.db` paths do **not** relocate as a side effect — see the
  correction under Wiring Phase. Every writer routes `connect()` →
  `ensure_db()` → `_resolve_db_path()`, which treats any `.ll/history.db` as
  default-shaped and re-anchors it at the walked-up root via `resolve_ll_dir`.
  DB writes already land at the project root from a subdirectory today.
- The `session_start.py` uses that do *not* self-resolve — `.ll/ll.local.md`
  lookup (line 114), `get_project_folder` (169), the backfill subprocess cwd
  (204), and `_validate_features`' `project_root` (260) — are the same bug:
  local overrides silently not applying from a subdirectory. They should move
  to `root` too.

**Scope boundary**: fix all eight `hooks/` call sites (the two named handlers,
`main_hooks`, `post_tool_use`, `drift_check`, `sweep_stale_refs`,
`install_learning_gate`, `pre_compact`, `learning_tests_gate`) in this issue —
hooks are the callers that fire from an uncontrolled cwd. The CLI and
`BRConfig(Path.cwd())` call sites catalogued under Integration Map are a
follow-up issue, not this one.

Alternative considered: normalize `event.cwd` to the resolved root once in
`main_hooks()` so every handler inherits it. Rejected for now because it
changes the documented meaning of `LLHookEvent.cwd` ("working directory the
host was operating in"); the helper is lower-risk.

## Program Design

### Signatures

- `find_project_root(start: Path) -> Path | None` (scripts/little_loops/paths.py:14, existing)
- `resolve_config_path(project_root: Path) -> Path | None` (scripts/little_loops/config/core.py:157, existing)
- `_load_config(cwd: Path) -> dict[str, Any] | None` (scripts/little_loops/hooks/user_prompt_submit.py:55, existing — call site to fix)
- `resolve_hook_root(event: LLHookEvent) -> Path` (scripts/little_loops/hooks/__init__.py, **new**) — `find_project_root(Path(event.cwd) or Path.cwd())`, falling back to that cwd when `None`
- `_resolve_db_path(path, *, root=None) -> Path` (scripts/little_loops/session_store/db.py:72, existing) — already re-anchors default-shaped `.ll/history.db` paths at the walked-up root; the reason DB writes do not relocate

### Call Path

`main_hooks()` (hooks/__init__.py:207) -> `root = resolve_hook_root(event)` -> `_hooks_telemetry_enabled(root)` -> `resolve_config_path(root)`

`handle()` (user_prompt_submit.py:97) -> `root = resolve_hook_root(event)` -> `_load_config(root)` -> `resolve_config_path(root)`

`handle()` (session_start.py:73) -> `root = resolve_hook_root(event)`; `root` replaces `cwd` at the three `resolve_config_path` sites (94, 105) and the downstream `ll.local.md` / `get_project_folder` / backfill-cwd / `_validate_features` uses.

The remaining six hooks (`post_tool_use`, `drift_check`, `sweep_stale_refs`,
`install_learning_gate`, `pre_compact`, `learning_tests_gate`) replace their
local `cwd = Path(event.cwd) if event.cwd else Path.cwd()` with
`root = resolve_hook_root(event)` before their `resolve_config_path` call.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/__init__.py` — add `resolve_hook_root()`; use it in `main_hooks()` (lines 207-215) for `_hooks_telemetry_enabled` and the `hook_event_context` DB path
- `scripts/little_loops/hooks/user_prompt_submit.py` (line 97-98, via `_load_config` line 55-63) — switch to `resolve_hook_root(event)`, use `root` for the three `history.db` paths (113, 128, 134)
- `scripts/little_loops/hooks/session_start.py` (lines 73, 94, 105) — switch to `resolve_hook_root(event)`, use `root` at 114, 135/144-147, 169, 204, 260
- `scripts/little_loops/hooks/post_tool_use.py:42,143`
- `scripts/little_loops/hooks/drift_check.py:100,125`
- `scripts/little_loops/hooks/sweep_stale_refs.py:152,170`
- `scripts/little_loops/hooks/install_learning_gate.py:51,94`
- `scripts/little_loops/hooks/pre_compact.py:37,111,180`
- `scripts/little_loops/hooks/learning_tests_gate.py:51,92`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/db.py:59` — does **not** share the gap
  (see wiring correction below); no change.
- `scripts/little_loops/hooks/pre_done.py:144` — already resolves via
  `find_project_root`; the reference implementation for the `root` /
  `if root is None:` convention. Optionally migrate to `resolve_hook_root`
  for uniformity, not required.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction**: `scripts/little_loops/session_store/db.py:59` does NOT share this gap — `resolve_history_db()` already calls `resolve_ll_dir(start=root)`, which resolves via `find_project_root` before falling back to `resolve_config_path(root)` (fixed under BUG-3181). Drop it from the audit-scope list above. [Agent finding]
- **Deeper instance of the same gap**: `BRConfig.__init__`/`_load_config` (`scripts/little_loops/config/core.py:277-305`) never routes through `find_project_root` either — `self.project_root = project_root.resolve()` only canonicalizes an already-given path, it does not walk up. Of ~80 `BRConfig(...)` construction call sites repo-wide, only 2 pre-resolve the root via `find_project_root` first (`scripts/little_loops/hooks/pre_done.py:144`, `scripts/little_loops/workspace.py:115`); the dominant pattern `BRConfig(Path.cwd())` (e.g. `scripts/little_loops/cli/doctor.py:731,1395`, `scripts/little_loops/fsm/persistence.py:84,1234`, `scripts/little_loops/fsm/executor.py:2749,4320`, `scripts/little_loops/mcp_server/policy.py:133`, `scripts/little_loops/advisor.py:248,523`) shares the identical subdirectory-cwd gap one layer below `resolve_config_path`. Out of this issue's stated scope (2 hook files) but the same root cause — candidate for a follow-up issue. [Agent finding]
- Additional direct `resolve_config_path(Path.cwd())`/`resolve_config_path(cwd)` call sites outside `hooks/` sharing the gap, not in the audit list above:
  `scripts/little_loops/cli/session.py:645,776,803,897` (four `ll-session` subcommand branches),
  `scripts/little_loops/cli/compact_session.py:62` (`main_compact_session`),
  `scripts/little_loops/cli/learning_tests.py:43,242`,
  `scripts/little_loops/cli/history_context.py:230`,
  `scripts/little_loops/learning_tests/release_gate.py:24` (`_load_lt_config`, feeds `/ll:manage-release`'s pre-tag gate via `run_release_gate`). [Agent finding]
- A narrower variant of the same gap, bypassing `resolve_config_path` entirely: `scripts/little_loops/cli/ctx_stats.py:675-684` hard-codes `cwd / ".ll" / "ll-config.json"` with no walk-up and no host-dir awareness. [Agent finding]
- The `_load_lt_config(cwd: Path)` helper is duplicated near-identically across 4 modules, only 2 of which are in this issue's audit list: `hooks/learning_tests_gate.py:49` and `hooks/install_learning_gate.py:49` (listed above) plus `learning_tests/release_gate.py:23` and the structurally-similar `cli/ctx_stats.py:675` (not listed above). [Agent finding]

### Similar Patterns
- `find_project_root()` is already the established pattern for cwd-to-root
  resolution elsewhere in the codebase (scripts/little_loops/paths.py:14).

### Tests
- `scripts/tests/test_config.py` (covers `resolve_config_path`/`_config_candidates`)
- No existing test file targets `user_prompt_submit.py` or `session_start.py`
  hook handlers directly by name — new regression test(s) should live
  alongside whichever test module already exercises these hook handlers.

_Wiring pass added by `/ll:wire-issue`:_
- Template for the new subdirectory-cwd regression test in `user_prompt_submit.py`: `scripts/tests/test_hook_user_prompt_submit.py::TestUserPromptSubmitWithSessionStore::test_correction_detected_writes_db` (config/DB setup + `handle()` call shape). [Agent finding]
- Template for `session_start.py`: `scripts/tests/test_hook_session_start.py::TestSessionStartConfigLoad::test_loads_base_config_when_present` plus the local `in_tmp` fixture (`:21-25`). [Agent finding]
- Nested-subdirectory `.git`+`.ll` fixture pattern to combine with the above: `scripts/tests/test_program_design_gate.py::TestFindProjectRoot::test_stray_ll_in_subdirectory_still_resolves_to_repo_root` (`:582-592`), using its local `_init_repo()` helper (`:94-98`) — no shared conftest.py fixture exists for "git root + `.ll/ll-config.json` + nested subdirectory"; every one of 13 test files hand-rolls its own `_init_repo`. [Agent finding]
- Confirmed: no existing test in `test_hook_user_prompt_submit.py`, `test_hook_session_start.py`, `test_hook_intents.py`, or the 6 host-adapter round-trip test files (`test_gemini_adapter.py`, `test_omp_adapter.py`, `test_opencode_adapter.py`, `test_codex_adapter.py`, `test_kimi_adapter.py`, `test_qwen_adapter.py`) will break — all of them exercise the genuinely-unconfigured-project path (no `.ll/` anywhere in the tmp-dir ancestry), not the buggy subdirectory-of-a-configured-project path. [Agent finding]

### Documentation
- N/A — internal cwd-resolution fix, no user-facing behavior change to document.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Naming convention**: every production call site that assigns the return of `find_project_root(...)` binds it to a variable named `root`, never `cwd` — `scripts/little_loops/paths.py:74`, `scripts/little_loops/issues/program_design.py:523,545`, `scripts/little_loops/workspace.py:115`, `scripts/little_loops/hooks/pre_done.py:144`. The Proposed Solution's own `cwd = find_project_root(Path.cwd()) or Path.cwd()` line diverges from this naming convention.
- **`None`-handling convention**: 3 of 4 production sites use an explicit `if root is None:` guard and branch (`program_design.py:523-525`, `workspace.py:115-116`, `pre_done.py:144-146`); only one site, `program_design.py:545`, uses the inline `or Path.cwd()` fallback shape the Proposed Solution follows.
- **Existing test coverage for the two named hook handlers**: `scripts/tests/test_hook_user_prompt_submit.py` and `scripts/tests/test_hook_session_start.py` (fixture `in_tmp`, `test_hook_session_start.py:21-25`) already exercise `user_prompt_submit.handle()`/`session_start.handle()` via `monkeypatch.chdir(tmp_path)`. In both files every existing `monkeypatch.chdir` call chdirs directly into `tmp_path` itself (the would-be project root) — neither file has a test that chdirs into a nested subdirectory, confirming no existing regression coverage for this bug's subdirectory-cwd scenario.
- **`find_project_root()`'s own regression coverage**: lives in `scripts/tests/test_program_design_gate.py::TestFindProjectRoot` (`:579-636`), which calls the function directly with a constructed nested `Path` as `start` and asserts the resolved root — there is no separate `test_paths.py`.
- **No shared git+`.ll/` fixture**: `scripts/tests/conftest.py`'s `temp_project_dir`/`make_project` fixtures (`:575-632`) build `.ll/`-only structures with no git init. Every test module needing a real `.git` ancestor defines its own local `_init_repo(root)` helper via subprocess `git init` — 13 separate files each with their own copy (e.g. `test_stray_ll_regression.py:21-33`, `test_program_design_gate.py:94-103`) — no shared `conftest.py` fixture consolidates this.

## Implementation Steps

1. Add `resolve_hook_root(event)` to `scripts/little_loops/hooks/__init__.py`
   (signature under Program Design). Use it in `main_hooks()` for
   `_hooks_telemetry_enabled` and the `hook_event_context` DB path.
2. In `user_prompt_submit.handle()` replace `cwd = Path.cwd()` with
   `root = resolve_hook_root(event)`; pass `root` to `_load_config` and use it
   for the three `history.db` paths.
3. In `session_start.handle()` replace `cwd = Path.cwd()` with
   `root = resolve_hook_root(event)`; use `root` at both
   `resolve_config_path` sites and every downstream use listed under Wiring
   Phase (local overrides, history.db, `get_project_folder`, backfill cwd,
   `_validate_features`).
4. Migrate the six remaining `hooks/` call sites (`post_tool_use`,
   `drift_check`, `sweep_stale_refs`, `install_learning_gate`, `pre_compact`,
   `learning_tests_gate`) from their local `Path(event.cwd) ... Path.cwd()`
   idiom to `resolve_hook_root(event)`.
5. Add regression tests (templates under Integration Map → Tests):
   `user_prompt_submit.handle()` and `session_start.handle()` invoked with
   `event.cwd` / chdir set to a nested subdirectory of a git repo whose root
   holds `.ll/ll-config.json`. Assert config is found, no `_NO_CONFIG_MSG`,
   analytics rows land in `<root>/.ll/history.db`, `<root>/.ll/ll.local.md`
   overrides are applied, and no `.ll/` is created under the subdirectory.
   Add a direct unit test for `resolve_hook_root` covering: nested subdir →
   root; no `.ll` anywhere → raw cwd; `event.cwd=None` → `Path.cwd()`.
6. Run `python -m pytest scripts/tests/` to verify no regressions.
7. File a follow-up issue for the CLI / `BRConfig(Path.cwd())` call sites
   catalogued under Integration Map (out of scope here).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Scope decision — resolved (2026-09-10 review)**: bind the resolved root
  to `root` (explicit `if root is None:` guard, per `program_design.py:523-525`
  and `pre_done.py:144-146`) and use `root` for **all** downstream paths in
  both handlers. Rationale recorded under Proposed Solution.
- **Correction to the earlier wiring note**: reassigning the base path does
  **not** relocate `history.db`. `record_prompt_opt_event` /
  `record_correction` / `record_skill_event` all call `_pkg.connect(db_path)`
  → `ensure_db()` → `_resolve_db_path()` (session_store/db.py:72), and
  `_is_default_shaped()` (db.py:18) matches any `.ll/history.db` by
  basename+parent, so the path is discarded and re-anchored via
  `resolve_ll_dir()` → `find_project_root(Path.cwd())`. DB writes from a
  subdirectory already reach `<root>/.ll/history.db` today. The "⚠
  Superseded" markers previously attached to steps 1–2 were based on this
  wrong premise and have been removed.
- In `user_prompt_submit.handle()`, `cwd` (line 97) is reused at lines 113,
  128, 134 to build `.ll/history.db`'s path — switch to `root` for
  consistency; no behavior change per the correction above.
- In `session_start.handle()`, `cwd` (line 73) is reused at lines 114
  (`.ll/ll.local.md`), 135/144-147 (`history.db`), 169
  (`get_project_folder` for backfill), 204 (backfill subprocess cwd), and
  260 (`_validate_features`'s `project_root`, feeding `_find_design_md`).
  All five move to `root`. The `ll.local.md` one is a genuine fix: local
  overrides are currently ignored when the hook fires from a subdirectory.
- Write the new regression test using
  `test_hook_user_prompt_submit.py::TestUserPromptSubmitWithSessionStore::test_correction_detected_writes_db`
  and
  `test_hook_session_start.py::TestSessionStartConfigLoad::test_loads_base_config_when_present`
  as call-shape templates, combined with the nested-subdirectory `.git`+`.ll`
  fixture pattern from
  `test_program_design_gate.py::TestFindProjectRoot::test_stray_ll_in_subdirectory_still_resolves_to_repo_root`
  (its local `_init_repo()` helper). Assert config/DB artifacts land at the
  resolved project root, not the subdirectory passed to `monkeypatch.chdir`.
- ~~Update Integration Map's Dependent Files list: drop
  `scripts/little_loops/session_store/db.py:59`~~ — done in the 2026-09-10
  review; it now sits under Dependent Files as a no-change note.

## Impact

- **Priority**: P3 - real data loss (skipped analytics/prompt-opt events) and
  a false user-facing warning, but requires a specific cwd condition (a build
  step leaving cwd in a subdirectory) to trigger.
- **Effort**: Small - one new ~8-line helper plus a mechanical substitution
  at eight `hooks/` call sites, reusing an existing utility
  (`find_project_root`).
- **Risk**: Low - `find_project_root` is already used elsewhere for the same
  purpose; falling back to the raw cwd when no root is found preserves
  current behavior for unconfigured directories and for host-only projects
  without a `.ll/` (see Expected Behavior's known limitation).
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-10 | Priority: P3

## Steps to Reproduce

1. In a little-loops project with `.ll/ll-config.json` at the project root, `cd` into a subdirectory that has no `.ll/ll-config.json` of its own (e.g. `cd scripts/` — reproduced with a stray `.ll/` there holding only `ll-doc-drift-state.json`, no `ll-config.json`).
2. Run a build step from that subdirectory (e.g. `hatch build`/`hatch publish`) so cwd remains at the subdirectory.
3. Submit a prompt with cwd still at the subdirectory, triggering the UserPromptSubmit hook.
4. Observe: the hook prints the false warning `[little-loops] No config found. Run ll-init to set up little-loops for this project.` even though `.ll/ll-config.json` exists two directories up, and `record_correction`/`record_skill_event`/`record_prompt_opt_event` are silently skipped for that turn.

## Error Messages

`[little-loops] No config found. Run ll-init to set up little-loops for this project.`

## Environment

## Frequency

## Location

- **File**: `scripts/little_loops/hooks/user_prompt_submit.py`
- **Line(s)**: 97-98 (via `_load_config` at 55-63)
- **Anchor**: in function `handle()`
- **Code**:
```python
cwd = Path.cwd()
config = _load_config(cwd)
```

## Session Log
- `/ll:wire-issue` - 2026-09-10T19:54:14 - `7febd81a-0c8b-40ff-bcac-1caebbdf68db.jsonl`
- `/ll:refine-issue` - 2026-09-10T19:42:20 - `5cd3d4a5-9327-4e89-b2f9-8ae0356518ce.jsonl`
- `/ll:format-issue` - 2026-09-10T19:37:03 - `87695830-9308-4502-b17f-1f94c56ad7d0.jsonl`
- `/ll:capture-issue` - 2026-09-10T19:28:01 - `0827d96d-3211-4f52-b581-bef5a439a36a.jsonl`
