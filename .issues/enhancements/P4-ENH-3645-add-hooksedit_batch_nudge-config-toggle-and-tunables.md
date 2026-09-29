---
id: ENH-3645
type: ENH
title: Add hooks.edit_batch_nudge config toggle and tunables
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T22:47:49Z'
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3645: Add hooks.edit_batch_nudge config toggle and tunables

## Summary

The `edit_batch_nudge` PostToolUse hook (`scripts/little_loops/hooks/edit_batch_nudge.py`, wired at `hooks/hooks.json` on the `Edit|Write|MultiEdit` matcher) has no user-facing config. `config-schema.json` has no `edit_batch_nudge`/`nudge` key, and the handler reads no config: `_NUDGE_THRESHOLD` (3) and `_BATCH_WINDOW_SECONDS` (3.0) are hardcoded constants. The only way to disable it today is removing the matcher entry from `hooks/hooks.json` or overriding it in the host's own settings.

Add a `hooks.edit_batch_nudge` object to `config-schema.json` (under the existing `hooks` block) with:
- `enabled` (bool, default `true`) — when `false`, the handler is a silent no-op (exit 0, no state write)
- `threshold` (int, default 3) — consecutive unbatched edits before the nudge fires
- `window_seconds` (number, default 3.0) — gap below which two edits count as batched

The handler should read these at call time via the project config, falling back to the current constants when the key or project is absent.

## Context

ENH-2499 and ENH-2503 both explicitly scoped config out ("No new `ll-config.json` keys"; ENH-2499 noted the constants "could be promoted to config if desired"). This captures that deferred follow-up. Found while checking whether the hook could be toggled per-project.

## Current Behavior

The handler's `handle()` in `scripts/little_loops/hooks/edit_batch_nudge.py` compares against the module constants `_NUDGE_THRESHOLD` (3) and `_BATCH_WINDOW_SECONDS` (3.0) and never reads `.ll/ll-config.json` or `.ll/ll.local.md`. `config-schema.json` declares no key for it, so setting one is either rejected by schema validation or silently ignored. Disabling the nudge requires editing `hooks/hooks.json` (plugin-owned) or the host's own settings.

## Expected Behavior

`hooks.edit_batch_nudge.enabled: false` in `.ll/ll-config.json` or `.ll/ll.local.md` makes the handler return `LLHookResult(exit_code=0)` before any state read or write. `threshold` and `window_seconds` override the constants when set. When the config file, project, or key is absent, or a value is invalid, behavior is identical to today.

## Motivation

- Per-project control: a project whose workflow is inherently sequential (dependent edits) or whose users find the reminder noisy can turn it off without patching plugin-owned `hooks/hooks.json`.
- Tuning: the 3-edit / 3.0s heuristic is a guess; slower hosts or models may need a larger window to avoid false "unbatched" runs.
- Consistency: sibling hooks already expose `hooks.stale_ref_fix` and `hooks.doc_drift_throttle_days`; this is the only hook with tunables and no config surface.

## Success Metrics

- Config surface: `hooks.edit_batch_nudge` keys present in schema: 0 → 3 (`enabled`, `threshold`, `window_seconds`).
- Disable path: with `enabled: false`, state file writes per edit: 1 → 0 (asserted in test).
- Regression: existing `scripts/tests/test_edit_batch_hook.py` cases pass unchanged with no config present.

## Scope Boundaries

- **In scope**: the three keys above; schema entry; config read in the handler; `docs/reference/CONFIGURATION.md` table rows; tests.
- **Out of scope**: changing the nudge text; the once-per-session latch; state-file format or location; per-tool thresholds; a `ll-config` CLI/`/ll:configure` wizard entry; host-side hook wiring in `hooks/hooks.json` or the Codex `hooks.json`.

## Proposed Solution

1. Add `edit_batch_nudge` under `hooks.properties` in `scripts/little_loops/config-schema.json` (after `doc_drift_throttle_days`), `additionalProperties: false`, with `enabled` (boolean, default `true`), `threshold` (integer, `minimum: 1`, default 3), and `window_seconds` (number, `minimum: 0`, default 3.0).
2. In `edit_batch_nudge.py`, extract a side-effect-free `_resolve_project_root(cwd) -> Path | None`: `Path(CLAUDE_PROJECT_DIR)` when set, else `find_project_root(cwd)`. It never creates a directory. Refactor `_resolve_state_path` to take the resolved root and do only the `.ll/` `mkdir` + filename join, so config and state are resolved from one root by construction (not two parallel derivations that can drift).
3. Add a `_load_settings(root)` helper that returns `(enabled, threshold, window_seconds)`: read `hooks.edit_batch_nudge` from the merged config, coerce and validate each value per the Decision Rules, and fall back to `_NUDGE_THRESHOLD` / `_BATCH_WINDOW_SECONDS` / `True` on any miss or error.
4. To honor the `.ll/ll.local.md` acceptance criterion, merge the local override frontmatter over the base config. `post_tool_use._load_config` reads the base file only, so reuse `resolve_config_path`, `parse_local_override_frontmatter`, and `deep_merge` from `little_loops.config.core` (as `BRConfig._load_config` does) rather than copying that helper. The override path is always `<root>/.ll/ll.local.md` (matching `BRConfig`), even when `resolve_config_path` returns a config from a host dir such as `.codex/`. Avoid a full `BRConfig` construction: it loads `.env` and parses every section on each edit. (`config.core`, including `yaml`, is already imported via the dispatch table's `drift_check` import, so the per-edit cost is two small file reads.)
5. In `handle()`, after the `_EDIT_TOOLS` check: resolve the root (`None` → exit 0, as today), call `_load_settings(root)`, return `LLHookResult(exit_code=0)` when disabled, and only then call `_resolve_state_path(root)` (the only step that may `mkdir`). Use the resolved threshold and window in place of the constants.
6. Keep the module constants as the defaults so `test_edit_batch_hook.py` imports keep working.

## API/Interface

N/A - No public Python API changes. New config surface only:

```json
{
  "hooks": {
    "edit_batch_nudge": {
      "enabled": true,
      "threshold": 3,
      "window_seconds": 3.0
    }
  }
}
```

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json` — add `hooks.edit_batch_nudge` object
- `scripts/little_loops/hooks/edit_batch_nudge.py` — `_load_settings()` helper; use in `handle()`
- `docs/reference/CONFIGURATION.md` — `hooks` section (~line 1497): add `hooks.edit_batch_nudge.*` rows and example

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — three fixed-value spots plus config table: summary-table row (:68), `### Edit-batch nudge` prose (:355–384, `_BATCH_WINDOW_SECONDS` at :378), `## Configuration Reference` rows beside `hooks.stale_ref_fix` (:569–570) [Agent 2 finding; promotes the refine-pass "missing from Files to Modify" note]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` `## Safe by Default` (:122–133; opt-out knobs at :130–131) and `## Turning Hooks Off` (:525–543; JSON example :529–535 lists only `prompt_optimization`, `context_monitor`, `history.session_digest`) — add `hooks.edit_batch_nudge.enabled` as an opt-out; this is the only config-based disable route for the nudge [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` `### hooks` JSON example (:1523–1541, under `#### hooks.pre_compact.rubric`) — the only `hooks` example block; add the new object beside `doc_drift_throttle_days` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `hooks/adapters/claude-code/edit-batch-nudge.sh` — invokes the handler via the hooks dispatcher (no change)
- `hooks/hooks.json` (matcher `Edit|Write|MultiEdit`) and `scripts/little_loops/hooks/adapters/codex/hooks.json` — wiring unchanged
- `scripts/little_loops/config/core.py` — `resolve_config_path`, `parse_local_override_frontmatter`, `deep_merge` reused, not modified

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` (:184, `"edit_batch_nudge": edit_batch_nudge.handle`), intent→event map (:99), `_USAGE` banner (:137); `handle` signature unchanged, no edit [Agent 1 finding]
- `scripts/little_loops/hooks/adapters/{codex,qwen}/edit-batch-nudge.sh`, `qwen-extension.json:97-98`, `scripts/little_loops/hooks/adapters/qwen/settings-block.json:97-98` — route to the same `handle`; unchanged [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py` (:40–42, :123–125) — the only hook that already does `parse_local_override_frontmatter` → `deep_merge`; the precedent to mirror. Its `merged_config` JSON stdout (:234) will echo any user-set `hooks.edit_batch_nudge` block into session context — no change needed [Agent 1/2 finding]
- `scripts/little_loops/hooks/drift_check.py` `_throttle_days()` (:97–110) — read/coerce/fallback precedent (`OSError`/`JSONDecodeError`/`ValueError`/`TypeError` → default); also holds same-named private `_STATE_FILENAME`-style copies (:52, :84) that are independent of this handler [Agent 1/2 finding]
- `scripts/little_loops/hooks/sweep_stale_refs.py` `handle()` (:171–181) and `scripts/little_loops/hooks/pre_compact.py` `_load_rubric_config()` (:36–49) — further raw-JSON `hooks.*` readers; convention reference only [Agent 1/2 finding]
- `scripts/little_loops/text_utils.py:214` and `config-schema.json:268` — list `.ll/ll-edit-batch-state.json` (gitignore defaults); state file unchanged, so no edit [Agent 2 finding]
- `docs/qwen/hook-events.md:19`, `docs/codex/getting-started.md:45,116`, `hooks/adapters/{qwen,codex}/README.md` — describe adapter wiring only; not affected [Agent 1/2 finding]

### Similar Patterns
- `scripts/little_loops/hooks/post_tool_use.py` `_load_config` — hook-local config read (base file only; no local-override merge)
- `hooks.stale_ref_fix` and `hooks.doc_drift_throttle_days` in `config-schema.json` — sibling scalar hook settings

### Tests
- `scripts/tests/test_edit_batch_hook.py` — add cases for disabled (no state file written), custom threshold, custom window, invalid values falling back to defaults, and `.ll/ll.local.md` override
- `scripts/tests/` schema/config tests that enumerate `hooks` keys — verify they still pass with the new key

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — new `test_edit_batch_nudge_in_schema` beside `test_doc_drift_throttle_days_in_schema` (:760); model the nested object on `test_hooks_pre_compact_rubric_in_schema` (:1104): `enabled` boolean/`True`, `threshold` integer/3/`minimum: 1`, `window_seconds` number/3.0/`minimum: 0`, `additionalProperties` False on the block. `test_hooks_in_schema` (:720) needs no change (asserts only `host` + `additionalProperties: False`) [Agent 3 finding]
- `scripts/tests/test_edit_batch_hook.py` — reuse the `clock` fixture (chdir `tmp_path`, unset `CLAUDE_PROJECT_DIR`, create `.ll/`) and `TestStatefulNudge._edit()` with `clock.advance(gap)`; write config with the `test_drift_check.py::TestThrottle::test_custom_throttle_days_from_config` (:235) shape and `ll.local.md` with the `test_hook_session_start.py` `_write_local` (:117) shape. Assert disabled via `not (tmp_path/".ll"/_STATE_FILENAME).exists()`, as in `test_drift_check.py::TestOptOut::test_env_var_disable_skips_entirely` (:63) — that test lives in `test_drift_check.py`; `test_edit_batch_hook.py` has no `TestOptOut` class [Agent 3 finding]
- `scripts/tests/test_edit_batch_hook.py` `TestNoStrayDirCreation::test_claude_project_dir_anchors_state_there` — shape for the missing root-consistency test (config under `CLAUDE_PROJECT_DIR`/`project_root/.ll`, cwd in a subdir) and for a disabled-with-no-project case asserting no `.ll/` is created (cf. `test_no_project_and_no_claude_project_dir_is_noop`) [Agent 3 finding]
- `scripts/tests/test_edit_batch_hook.py` `TestRobustness::test_state_write_failure_passes_through` — monkeypatches `edit_batch_nudge.atomic_write_json`; keep `_load_settings` from reusing that name, and keep `_now`, `_STATE_FILENAME`, `_load_state`, `_NUDGE_THRESHOLD`, `_BATCH_WINDOW_SECONDS` importable (line 19–22, 236, 249) [Agent 3 finding]
- `scripts/tests/test_hook_intents.py` `test_dispatch_edit_batch_nudge_happy_path` (:406) / `..._codex_host` (:442) — run `python -m little_loops.hooks edit_batch_nudge` with `cwd=tmp_path` and no config, so they should pass unchanged; the Codex variant sets `LL_HOOK_HOST=codex` so `resolve_config_path` probes `.codex/` first, finds nothing, falls through. Optional new subprocess case: `.ll/ll-config.json` with `enabled: false` → empty stdout/stderr, no state file [Agent 3 finding]
- **Test isolation — scrub `CLAUDE_PROJECT_DIR`**: both `test_hook_intents.py` subprocess cases inherit `os.environ` (the Codex one via `env={**os.environ, ...}`, the other implicitly), and `scripts/tests/conftest.py` does not scrub `CLAUDE_PROJECT_DIR`. When pytest runs inside a Claude Code session the handler already writes state to the developer's real project `.ll/`; after this change it would also *read* that project's `ll-config.json` / `ll.local.md`, so a local `enabled: false` would fail the happy-path assertions. Pass an env with `CLAUDE_PROJECT_DIR` removed to both existing cases and to any new subprocess case
- `scripts/tests/test_sweep_stale_refs.py` `_write_config` (:37–42) and `scripts/tests/test_pre_compact.py` `_write_rubric_config` (:293) — sibling config-writing helpers; pattern reference only [Agent 3 finding]
- `scripts/tests/test_config.py` `test_to_dict_never_modelled_sections_empty_when_absent` (:1372–1382) and `test_config_schema.py::TestSchemaValueParity` — assert `hooks` passes through `to_dict()` raw; will not check the new defaults and stay green unless a `hooks` dataclass is introduced (then register it in `_DATACLASS_SECTION_MAP`, :1387) [Agent 2/3 finding]
- `scripts/tests/test_docs_audience_gate.py::test_user_docs_are_end_user_facing[CONFIGURATION.md]` / `[BUILTIN_HOOKS_GUIDE.md]` — fails on `scripts/tests/…` paths or "this repo" wording in the new doc text [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py` — optional: add a `(doc, must-contain, ENH-3645)` tuple so the new `CONFIGURATION.md` rows are pinned; no existing tuple mentions `hooks.` or `edit_batch`. `test_wiring_guides_and_meta.py::test_hook_coverage_matches_guide` (:458) is unaffected (wiring unchanged) [Agent 3 finding]

### Documentation
- `docs/reference/CONFIGURATION.md` — key table and JSON example (see above)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — see Files to Modify above (:68, :122–133, :355–384, :525–543, :569–570)
- `docs/reference/API.md:10662` — documents only the `drift_check` throttle key and has no `edit_batch_nudge` section; no change needed [Agent 1/2 finding]
- `site/reference/CONFIGURATION/index.html`, `site/search/search_index.json` — tracked built copies of `CONFIGURATION.md`; regenerate via the docs build rather than hand-editing [Agent 1 finding]

### Configuration
- `scripts/little_loops/config-schema.json`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **`docs/guides/BUILTIN_HOOKS_GUIDE.md`** (now listed under Files to Modify by the wiring pass) presents the window and threshold as fixed values. Both it and `CONFIGURATION.md` are end-user docs, so `test_docs_audience_gate.py` applies (no `scripts/tests/…` paths, no "this repo").
- **Dependents beyond the Claude Code shim**: `scripts/little_loops/hooks/adapters/codex/edit-batch-nudge.sh`, `scripts/little_loops/hooks/adapters/qwen/edit-batch-nudge.sh`, and the Qwen/Codex hook manifests all route to the same `handle`; `hooks/hooks.json` gives the entry `timeout: 5`. `hooks/__init__.py` `_dispatch_table()` (`"edit_batch_nudge": edit_batch_nudge.handle`) is a second importer alongside `scripts/tests/test_edit_batch_hook.py:20`; `scripts/tests/test_hook_intents.py` imports `_NUDGE_THRESHOLD` in its `test_dispatch_edit_batch_nudge_*` cases.
- **Convention — hook-side `hooks.*` readers**: each handler reads its own keys from raw JSON via `resolve_config_path(root)` + `json.loads`, coerces inside `try`, and falls back to a module default (`drift_check._throttle_days`, `hooks/drift_check.py:97`, is the closest scalar-tunable sibling; `pre_compact._load_rubric_config`, `learning_tests_gate._load_lt_config`, `sweep_stale_refs.handle` share the rule). None of them merge `ll.local.md`; the only hook that does is `hooks/session_start.py` (`parse_local_override_frontmatter` → `deep_merge`, ~:123–125), so honoring the local-override criterion means adopting that second precedent, not the sibling one.
- **Convention — `hooks` has no dataclass**: `BRConfig.to_dict()` passes `hooks` through raw (BUG-3012 never-modelled sections), so `TestSchemaValueParity` contributes no `hooks` leaves and will not check the new defaults. If a `@dataclass` is introduced in `config/features.py`, `config/automation.py`, or `config/core.py`, it must be registered in `_DATACLASS_SECTION_MAP` in `scripts/tests/test_config_schema.py` (hook-loaded classes such as `PreCompactRubricConfig` map to `None` with a "loaded directly by hooks" comment) or `TestDataclassSectionMapCompleteness` fails.
- **Constraint — schema is mandatory**: the `hooks` block sets `additionalProperties` to false (`test_hooks_in_schema`, `scripts/tests/test_config_schema.py:720`, asserts it), so the new key must be declared; per-key structural tests exist as the shape to extend (`test_doc_drift_throttle_days_in_schema`, :760). No `hooks.*` leaf carries `minimum`/`maximum` today; bounds elsewhere sit on the leaf (`prepatch_check.timeout_s`, `minimum: 1`).
- **Constraint — root consistency**: state root and config root must agree. `_resolve_state_path` prefers `CLAUDE_PROJECT_DIR` and payload `cwd`, but `hooks/__init__.py` `resolve_hook_root(event)` (~:68) uses only `event.cwd` (`os.getcwd()`) and ignores both — reusing it can read config from a different project than the state file is written to. `drift_check.handle` sidesteps this with `root = state_path.parent.parent`, but `_resolve_state_path` `mkdir`s `.ll/` as a side effect, which would violate "disabled ⇒ no `.ll/` created" if the `enabled` check ran after it. Resolved by the shared `_resolve_project_root` helper (Proposed Solution step 2). Note the `mkdir` risk is confined to the `CLAUDE_PROJECT_DIR` branch: `resolve_ll_dir(create=True)` only resolves a root that already has `.ll/`, so the upward-walk branch never fabricates one.
- **Constraint — polarity**: `feature_enabled(config_data, dot_path)` (`config/features.py`) returns `False` for a missing key, so it cannot back a default-`true` toggle; an absent `enabled` must mean enabled.
- **Constraint — current invalid-value behavior**: with any config-sourced value, a non-numeric `threshold`/`window_seconds` raises `TypeError` inside `handle`'s outer `except Exception` → exit 0 with no state write, i.e. indistinguishable from disabled; `bool` is an `int` subclass (`True` behaves as threshold 1); `threshold <= 1` already nudges on the first unbatched edit; `window_seconds <= 0` means only `MultiEdit` resets the run (timing never batches, barring clock skew).
- **Related, reconciled**: ENH-2471 (`status: done`) anticipated a top-level `edit_batch_nudge.enabled`, default **off**, mirroring `learning_tests.enabled` (its Configuration section and a `/ll:configure edit-batch-nudge` area mapping). Nothing landed in `config-schema.json`; this issue's placement (`hooks.edit_batch_nudge.*`) and polarity (default **on**, preserving shipped behavior) supersede it. Verified no consumer of ENH-2471's key: `grep -rn "edit.batch" skills/ commands/ scripts/little_loops/init/` returns nothing, so no dangling references need updating.
- **Test shape evidence**: `scripts/tests/test_edit_batch_hook.py` `clock` fixture chdirs into `tmp_path`, unsets `CLAUDE_PROJECT_DIR`, and creates `.ll/` (without a resolvable project every assertion sees a silent exit 0); no test there writes config yet. Config-driven precedent: `scripts/tests/test_drift_check.py::test_custom_throttle_days_from_config` (:235); opt-out precedent asserting the state file is absent: `TestOptOut::test_env_var_disable_skips_entirely`; `ll.local.md` precedent: `scripts/tests/test_hook_session_start.py` `_write_local` (:117) / `test_local_overrides_deep_merge` (:121). `docs/reference/API.md` had uncommitted working-tree changes when this was researched.

## Program Design

### Types
- `hooks.edit_batch_nudge: {enabled: bool, threshold: int, window_seconds: float}` — raw config sub-dict; every key optional, absent or invalid → module default
- `LLHookResult(exit_code=0)` — the disabled return; `LLHookEvent` and `LLHookResult` in `little_loops.hooks.types` are unchanged

### Signatures
- `handle(event: LLHookEvent) -> LLHookResult` — existing entry in `scripts/little_loops/hooks/edit_batch_nudge.py`; gains the `enabled` gate and reads threshold/window from resolved settings
- `_resolve_project_root(cwd: Path) -> Path | None` — new in `scripts/little_loops/hooks/edit_batch_nudge.py`; `CLAUDE_PROJECT_DIR` when set, else `find_project_root(cwd)`; pure lookup, never creates a directory
- `_load_settings(root: Path) -> tuple[bool, int, float]` — new; merged `hooks.edit_batch_nudge` read, per-key validate, per-key fallback to defaults; never raises
- `_resolve_state_path(root: Path) -> Path | None` — existing, refactored to take the resolved root; the only step that `mkdir`s `.ll/`, so it runs after the `enabled` gate
- `find_project_root(start: Path) -> Path | None` — existing in `little_loops.paths`
- `resolve_config_path(project_root: Path) -> Path | None` — existing in `little_loops.config.core`
- `parse_local_override_frontmatter(content: str) -> dict[str, Any]` — existing in `little_loops.config.core`
- `deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]` — existing in `little_loops.config.core`; explicit `None` removes a key
- `_throttle_days(cwd: Path) -> int` — existing in `scripts/little_loops/hooks/drift_check.py`; the read/coerce/fallback contract a scalar `hooks.*` tunable already follows

### Call Path
`main_hooks` -> `handle` -> `_resolve_project_root` -> `_load_settings` -> `resolve_config_path` -> `parse_local_override_frontmatter` -> `deep_merge` -> (disabled → return) -> `_resolve_state_path` -> `_persist_state`

### Decision Rules
- `enabled`: only an explicit `false` disables; absent, non-bool, or unreadable config → enabled. A truthiness helper that treats absent as `False` (`feature_enabled`) would silently disable the hook on every unconfigured project
- `threshold`: must be a true `int` (reject `bool`), `>= 1`; anything else → `_NUDGE_THRESHOLD`
- `window_seconds`: must be an `int` or `float` (reject `bool`; JSON `3` parses to `int` and is accepted), finite (`math.isfinite` — reject YAML `.inf`/`.nan` and Python-JSON `NaN`/`Infinity`, which would silently disable nudging via the tunable rather than via `enabled`), and `>= 0`; anything else → `_BATCH_WINDOW_SECONDS`; `0` is valid and means timing never batches (only `MultiEdit` resets the run)
- Per-key fallback: an invalid value falls back for that key only; valid sibling keys still apply
- Escape hatch: a missing, unreadable, or malformed config file or `ll.local.md` never raises and never disables — it yields the defaults, keeping the hook's never-raise contract
- Ordering: config root and state root are the same `Path` returned by `_resolve_project_root` (`CLAUDE_PROJECT_DIR` first, else upward from payload `cwd`); `_load_settings` and the `enabled` gate run before `_resolve_state_path`, so a disabled hook never `mkdir`s. When no project resolves the hook remains a silent no-op that creates no `.ll/`

## Implementation Steps

1. Add the `hooks.edit_batch_nudge` schema entry with defaults and bounds.
2. Extract `_resolve_project_root()` and refactor `_resolve_state_path` to take the resolved root; add `_load_settings(root)`, honoring `.ll/ll.local.md` overrides and falling back to the constants on any failure.
3. Wire `enabled`, `threshold`, and `window_seconds` into `handle()`; return before state resolution when disabled.
4. Add tests to `scripts/tests/test_edit_batch_hook.py` and update `docs/reference/CONFIGURATION.md`.
5. Verify: `python -m pytest scripts/tests/test_edit_batch_hook.py`, then the full suite, `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — summary row (:68), `### Edit-batch nudge` prose (:355–384; replace "fixed" window/threshold wording with the config keys), `## Safe by Default` (:130–131), `## Turning Hooks Off` JSON example (:529–535), and `## Configuration Reference` rows (:569–570); end-user wording only (`test_docs_audience_gate.py`)
- Update `docs/reference/CONFIGURATION.md` `### hooks` JSON example (:1523–1541) in addition to the key-table rows
- Add `test_edit_batch_nudge_in_schema` to `scripts/tests/test_config_schema.py` (model: `test_hooks_pre_compact_rubric_in_schema`, :1104)
- Add a root-consistency test (config under `CLAUDE_PROJECT_DIR`, cwd in a subdir) and a disabled-without-project test (no `.ll/` created) to `scripts/tests/test_edit_batch_hook.py`, following `TestNoStrayDirCreation`
- Scrub `CLAUDE_PROJECT_DIR` from the subprocess env in `scripts/tests/test_hook_intents.py` `test_dispatch_edit_batch_nudge_happy_path` / `..._codex_host` (and any new subprocess case) so the developer's real project config cannot leak into them
- Keep `_load_settings` from shadowing `atomic_write_json` (monkeypatched by `TestRobustness::test_state_write_failure_passes_through`) and preserve `_NUDGE_THRESHOLD`, `_BATCH_WINDOW_SECONDS`, `_STATE_FILENAME`, `_load_state`, `_now` as importable names
- Do not add a `hooks` dataclass; if one is introduced anyway, register it in `_DATACLASS_SECTION_MAP` (`test_config_schema.py:1387`)
- Rebuild `site/` (tracked HTML copy of `CONFIGURATION.md`) only if the docs build is part of the normal flow; no skill/command edits, so no `ll-adapt` mirror regeneration and no README copy sync are needed

## Acceptance Criteria

- [ ] `config-schema.json` declares `hooks.edit_batch_nudge.{enabled,threshold,window_seconds}` with the defaults above
- [ ] `enabled: false` in `.ll/ll-config.json` (or `.ll/ll.local.md`) suppresses the nudge and writes no state
- [ ] Unset config preserves current behavior exactly
- [ ] Tests cover disabled, custom threshold, and custom window
- [ ] Invalid values (`bool`, non-numeric, below minimum, non-finite `window_seconds`) fall back per key to the defaults, and valid sibling keys still apply
- [ ] `.ll/ll.local.md` overrides the base config in both directions: base `enabled: true` + local `enabled: false` disables; local `enabled: null` removes the key → enabled
- [ ] Config under `CLAUDE_PROJECT_DIR` is honored when the event cwd is a subdirectory (config root == state root)
- [ ] Disabled with `CLAUDE_PROJECT_DIR` pointing at a dir without `.ll/` creates no `.ll/`; no resolvable project remains a silent no-op
- [ ] `test_hook_intents.py` edit-batch subprocess cases run with `CLAUDE_PROJECT_DIR` scrubbed from the env

## Impact

- **Priority**: P4 - opt-out convenience for an advisory hook; workaround exists (edit `hooks/hooks.json`).
- **Effort**: Small - one schema block, one helper, a few tests, and doc rows.
- **Risk**: Low - all failure paths fall back to today's constants; the hook already never raises.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-09-28T23:26:33 - `26f1a780-b8a8-48d2-b65b-ebdb4c979b54.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:25:16 - `9ca36230-dd1a-44b4-a07d-03fa387b0f53.jsonl`
- `/ll:wire-issue` - 2026-09-28T23:23:41 - `5c1a0a11-8672-4aa4-af3e-98f5a6fb7409.jsonl`
- `/ll:refine-issue` - 2026-09-28T23:18:14 - `848f28ad-b795-4137-a127-970c923dc55c.jsonl`
- `/ll:format-issue` - 2026-09-28T23:12:02 - `9ae0c62d-86f2-4b99-bec8-a37f55d04521.jsonl`
- `/ll:capture-issue` - 2026-09-28T22:47:54 - `f34adacb-fb88-4876-a098-8175948c7ff2.jsonl`
