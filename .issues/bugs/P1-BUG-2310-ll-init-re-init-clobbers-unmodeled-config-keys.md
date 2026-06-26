---
id: BUG-2310
title: ll-init re-init clobbers unmodeled config keys despite "Merging" message
type: BUG
status: open
priority: P1
captured_at: '2026-06-26T21:55:52Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
labels:
- init
- config
- data-loss
relates_to:
- ENH-2240
- BUG-2042
confidence_score: 96
outcome_confidence: 76
score_complexity: 21
score_test_coverage: 12
score_ambiguity: 23
score_change_surface: 20
---

# BUG-2310: ll-init re-init clobbers unmodeled config keys despite "Merging" message

## Summary

Re-running `ll-init` on a project that already has `.ll/ll-config.json` **silently
destroys** every config key that `build_config()` does not model. The headless
path prints `"Merging with existing configuration."` but performs no merge — it
rebuilds a fixed subset of keys and overwrites the file wholesale. A
`deep_merge()` with the correct semantics already exists in `config/core.py:44`
but neither init path uses it.

## Motivation

Re-running `ll-init` is a routine operation — users do it after a plugin upgrade
or to enable new feature toggles. Silent data loss on this path is especially
damaging: the misleading "Merging with existing configuration." message causes
users to trust that their settings are preserved, only discovering the loss later
when features stop working. The blast radius covers every config key outside
`build_config`'s fixed set (sprints, confidence gate, documents, scratch_pad,
history compaction, context-monitor threshold) — all common customisations. The
fix is low-effort because `deep_merge()` already exists and just needs wiring in.

## Current Behavior

`_run_yes` (`scripts/little_loops/init/cli.py:303-315`):
1. Loads existing config and pre-populates a **fixed subset** of keys into `choices`.
2. Calls `build_config()`, which only emits keys it knows about.
3. Calls `write_config()`, which does `atomic_write_json` — a full overwrite.

The TUI path (`scripts/little_loops/init/tui.py:628,839`) has the same shape
(pre-populates more keys, but still overwrites wholesale).

Empirically, re-running `ll-init --yes` against this very repo would **delete**:

```
commands.confidence_gate.{enabled,readiness_threshold}
commands.tdd_mode
context_monitor.auto_handoff_threshold = 50
design_tokens.{active,active_theme}
documents.*            (entire section)
history.compaction.*   (entire section)
history.session_digest.char_cap = 1200
scratch_pad.*          (entire detailed section)
sprints.default_max_workers = 2
```

The `"Merging with existing configuration."` message (`cli.py:174`) makes this
worse: the user is told their data is preserved while it is being clobbered.

Note `--force` does **not** gate this: `write_config` runs regardless of `--force`
(it only flips a print message and the codex-adapter overwrite). The advertised
exit code `1 - Error (config exists...)` in the `--help` epilog has no
corresponding code path.

## Steps to Reproduce

1. Create a project with `.ll/ll-config.json` that contains keys not modeled by
   `build_config()` (e.g. `commands.confidence_gate`, `design_tokens`,
   `documents`, `history.compaction`, `scratch_pad`, `sprints.default_max_workers`).
2. Run `ll-init --yes` on the same project directory.
3. Open `.ll/ll-config.json` after the run completes.
4. Observe that all unmodeled keys are absent from the file.
5. Note that the terminal printed `"Merging with existing configuration."` — the
   merge message was shown while the data was silently destroyed.

## Expected Behavior

Re-running `ll-init` preserves any config keys the user set that `build_config`
does not model. The "Merging" message should reflect a real merge.

## Root Cause

`scripts/little_loops/init/cli.py` `_run_yes()` and
`scripts/little_loops/init/tui.py` write path both compute
`config = build_config(template, choices)` and pass it straight to
`write_config()`. `build_config()` (`scripts/little_loops/init/core.py:21`) emits
only `$schema, project, issues, scan, learning_tests, analytics, context_monitor
(enabled only), product, [decisions/scratch_pad/session_capture/prompt_optimization],
history.session_digest, loops.run_defaults`. Everything else in an existing file
is dropped. `deep_merge()` (`scripts/little_loops/config/core.py:44`) — built
precisely for config overlays — is never invoked by init.

## Proposed Solution

In both `_run_yes` and the TUI write path, layer the rebuilt config over the
existing one before writing:

```python
from little_loops.config.core import deep_merge
config = deep_merge(existing_config, build_config(template, choices))
write_config(config, ll_dir)
```

Caveat: `deep_merge` treats a `None` value in the override as a key-removal
sentinel — coordinate with BUG-2311 (null leaves) so `build_config` does not emit
`None` leaves that would delete user keys (e.g. `loops.run_defaults.mode`) on
merge. Either strip `None` leaves in `build_config` or merge on a None-stripped
copy.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_run_yes()` (~line 303–315): add `deep_merge` call before `write_config`
- `scripts/little_loops/init/tui.py` — `_build_final_config()` (line 604, calls `build_config` at 628) and `_apply_config()` (line 808, calls `write_config` at 839): same merge pattern needed; `_apply_config()` receives an already-built config dict and does not load the existing config at all

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/cli.py` — **`_run_apply()` (lines 420–454): THIRD write path with the identical clobber bug.** `ll-init --apply <plan>` (or `apply --config PLAN`) reads `proposed_config` from a `--plan` JSON and calls `write_config(config, ll_dir)` at line 454 with **no merge** — it never loads the existing config. Re-running `--apply` on an existing project clobbers unmodeled keys exactly like `_run_yes`. The issue's Proposed Solution only covers `_run_yes` + the TUI path; this path must get the same `deep_merge(existing_config, ...)` treatment. Note `_run_apply` already receives `force: bool` (line 424). [Agent 1 + verified]
- `scripts/little_loops/init/cli.py` — **`main_init()` argparse epilog (lines 496–498): remove the dead `config exists` clause.** Exit-code line 498 reads `1 - Error (config exists, template missing, etc.)` but no code path exits 1 when a config exists (the issue's Current Behavior already flags this). Clean it up as part of this fix so the `--help` output matches reality. [Agent 2 + verified]

### Behavioral Coupling — `--force` Gating (added by `/ll:wire-issue`)

_The proposed fix is incomplete without gating on `force`:_
- **`deep_merge` MUST be gated on `not force` in all three write paths** (`_run_yes`, TUI `_apply_config`, `_run_apply`). `--force` is documented as "reset to template defaults rather than pre-populating from existing config" (`docs/reference/CLI.md:46`, `docs/guides/GETTING_STARTED.md:90,124`, `skills/init/SKILL.md:55`). An unconditional `deep_merge(existing_config, build_config(...))` would preserve unmodeled keys even under `--force`, directly contradicting that contract. `force` is already in scope at every call site (`_run_yes` line 132, `_run_apply` line 424, `_apply_config` line 817). [Agent 2 + verified]
- **Dead "Overwriting" message (`cli.py:173–176`):** `existing_config` is loaded unconditionally (lines 165–171), so `if existing_config and not dry_run:` prints `"Merging with existing configuration."` even when `--force` is passed — the `elif config_path.exists() and force …:` `"Overwriting existing configuration."` branch at line 175 is unreachable whenever a config file exists. The force-gating fix should also correct this message branch so `--force` prints "Overwriting" and a normal re-init prints "Merging". No test asserts on either string, so the message is free to change. [Agent 2/3 + verified]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — provides `deep_merge()`; no changes needed here
- `scripts/little_loops/init/writers.py` — provides `write_config()` (line 102); no changes needed here (it is a pure overwrite by design — the merge must happen in the caller before passing to `write_config`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `write_config()` signature: `def write_config(config: dict[str, Any], ll_dir: Path, dry_run: bool = False) -> None:` in `scripts/little_loops/init/writers.py:102` — does not read the existing config before writing; delegates straight to `atomic_write_json()` (wholesale overwrite).
- `deep_merge()` signature: `def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:` in `scripts/little_loops/config/core.py:44` — `None` values in the override dict are **key-removal sentinels** (calls `result.pop(key, None)`), not passthrough values.
- **Two `deep_merge` variants exist** — use `little_loops.config.core.deep_merge` (the config-overlay variant). Do **NOT** use `little_loops.fsm.fragments._deep_merge` (a separate implementation where `None` passes through). The correct import: `from little_loops.config.core import deep_merge`.
- Only current production caller of `config.core.deep_merge`: `scripts/little_loops/hooks/session_start.py:111` — `merged_config = deep_merge(base_config, local_overrides)` (applies `ll.local.md` frontmatter on top of `ll-config.json`).
- `_run_yes()` selective extraction block is lines 271–303; `build_config()` call is line 303; `write_config()` call is line 315.

### Similar Patterns
- `scripts/little_loops/config/core.py:deep_merge` — already used in other config overlay scenarios; follow that call pattern exactly

### Tests
- `scripts/tests/test_init_core.py` — **extend** `TestMainInit.test_yes_merges_existing_config` (line 1217) or add a sibling test asserting an unmodeled key survives re-init; the existing test only asserts modeled keys (`project.name`, `project.src_dir`, `analytics.enabled`) — it will not catch a regression in this fix
- `scripts/tests/test_builtin_loops.py` — check for any init-path coverage that needs updating
- `scripts/tests/test_config.py` — `TestDeepMerge` (line 2543) has canonical `deep_merge` unit tests including `test_null_removes_key`; reference for expected merge semantics

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py` — **new test for the TUI re-init path (omitted from the lists above).** `TestExistingConfig` (lines 410–456: `test_existing_config_without_force_pre_populates`, `test_existing_config_pre_populates_defaults`) only verifies the wizard receives existing values as prompt `default=` args — it never asserts unmodeled keys survive the final written config. Add a sibling round-trip test that pre-seeds an unmodeled key, drives `run_tui()`/`_apply_config()`, and asserts the key survives. `_build_final_config()` and `_apply_config()` are currently **untested at the unit level**. [Agent 1/2/3 finding]
- `scripts/tests/test_init_core.py` — **new test for `_run_apply()` re-init** (the third write path): pre-seed `.ll/ll-config.json` with an unmodeled key, run `main_init(["--apply", "<plan-json>", "--root", ...])`, assert the unmodeled key survives. No existing test exercises `_run_apply` against a pre-existing config. [Agent 1 + verified]
- `scripts/tests/test_init_core.py` — **add a `--force` regression test:** assert that `ll-init --yes --force` on a config with an unmodeled key **drops** that key (reset-to-defaults contract), complementing the no-force preservation test. Guards against the merge being applied unconditionally. [Agent 2 finding]
- `scripts/tests/test_init_install.py` — exercises install/version detection only; **not affected** by this fix (listed for completeness — no change expected). [Agent 1 finding]
- _Note:_ no test currently asserts on the `"Merging with existing configuration."` string (grep-confirmed across all test files), so the message branch can be corrected freely.

### Documentation
- `docs/reference/API.md` — `ll-init` section; update re-init behavior description if documented

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — **the canonical re-init doc (issue only listed API.md).** `### ll-init` section already *claims* the post-fix behavior the code doesn't yet deliver: description (line 39) "the headless `--yes` path preserves existing feature toggles and project fields"; `--yes` row (line 45) "Merges existing config values when a config is present"; `--force` row (line 46) "Reset to template defaults rather than pre-populating from existing config"; `apply --config PLAN` row (line 61) "Accepts `--force` to overwrite existing configuration". After the fix these become accurate. **Verify the exit-codes block (line 63) does not re-introduce a `config exists` exit-1 claim** (it currently omits it; keep it that way to match `cli.py`). [Agent 2 + verified]
- `docs/guides/GETTING_STARTED.md` — `### Existing Installation Detection` (line 124) "Use `--force` to reset to template defaults instead of merging" and the `--force` table row (line 90). Both are accurate **only if `--force` actually bypasses the new `deep_merge`** — cross-check after implementing force gating; no text change needed if force gating is done correctly. [Agent 2 + verified]
- `docs/reference/CONFIGURATION.md` — `## Manual Configuration` (lines 1289–1291) lists the fields "not exposed through `ll-init`… edit `.ll/ll-config.json` directly." These are exactly the unmodeled keys BUG-2310 clobbers. Add a one-line note that re-running `ll-init` (without `--force`) now preserves these manually-set values. [Agent 2 + verified]
- `skills/init/SKILL.md` (line ~55) — documents `/ll:init --force` as "reset to template defaults"; confirm it stays consistent with the force-gating behavior. [Agent 2 finding]
- `config-schema.json` — **no change needed** (the fix preserves arbitrary already-present keys; schema validation of pre-existing keys is unaffected). [Agent 2 + verified]

### Configuration
- `.ll/ll-config.json` — the file that is currently clobbered; no schema changes needed

## Implementation Steps

1. Import `deep_merge` from `little_loops.config.core` at the top of `cli.py` and `tui.py` (or the relevant write-path module).
2. In `_run_yes()` (`cli.py`): after loading `existing_config` and computing `new_config = build_config(template, choices)`, apply `config = deep_merge(existing_config, new_config)` before passing to `write_config()`.
3. Apply the identical pattern in the TUI write path.
4. Coordinate with BUG-2311: before merging, strip `None` leaves from `new_config` so they do not trigger `deep_merge`'s key-removal sentinel on keys the user set.
5. Add a round-trip test to `TestMainInit` in `test_init_core.py` following the pattern of `test_yes_merges_existing_config` (line 1217): write a config containing an unmodeled key (e.g. `"my_custom_section": {"key": "value"}`), run `main_init(["--yes", "--root", str(tmp_project)])` with the standard `_plugin_root` + `detect_installation` patch pair, then assert the unmodeled key survives in the written file. The existing test at line 1217 is insufficient — it only checks modeled keys that `_run_yes` explicitly extracts.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. There are **three** write paths, not two, and the merge must be force-gated:_

6. **`_run_apply()` (`cli.py:420–454`):** before `write_config(config, ll_dir)` at line 454, load the existing `.ll/ll-config.json` (it currently does not) and, when `not force`, apply `config = deep_merge(existing_config, None_stripped(config))`. This is the third clobber path (`ll-init --apply <plan>`), missing from the original Proposed Solution.
7. **Force-gate all three merges:** wrap the `deep_merge` in `_run_yes`, `_apply_config`, and `_run_apply` in `if not force:` so `--force` still resets to template defaults per `docs/reference/CLI.md:46`. `force` is already in scope at each call site.
8. **Fix the dead "Overwriting" message (`cli.py:173–176`):** make `--force` print `"Overwriting existing configuration."` and a normal re-init print `"Merging with existing configuration."` (currently the "Merging" branch always wins because `existing_config` is loaded unconditionally).
9. **Clean up the argparse epilog (`cli.py:496–498`):** remove the `config exists` clause from the exit-code-1 description — no code path produces it.
10. **Add TUI re-init test (`test_init_tui.py`):** sibling to `TestExistingConfig` (line 410) asserting an unmodeled key survives a full `run_tui()`/`_apply_config()` round-trip; both functions are currently untested at the unit level.
11. **Add `_run_apply` re-init test and a `--force` reset test (`test_init_core.py`):** one asserting unmodeled-key survival through `--apply`, one asserting `--yes --force` drops the unmodeled key.
12. **Update docs:** add the preservation note to `docs/reference/CONFIGURATION.md` (Manual Configuration, line ~1291); verify `docs/reference/CLI.md` (ll-init `--yes`/`--force`/`apply`/exit-codes) and `docs/guides/GETTING_STARTED.md` (line 124) now read accurately; confirm `skills/init/SKILL.md` (line ~55) stays consistent.

## Impact

- **Priority**: P1 — Silent data loss on a common workflow (plugin upgrades, re-init); all users who customise config are affected
- **Effort**: Small — `deep_merge()` already exists; the core fix is ~3 lines in 2 places; None-stripping adds a small helper
- **Risk**: Medium — Init is a critical path; changing merge semantics could surface edge cases; must coordinate with BUG-2311 to avoid null-leaf key deletion
- **Breaking Change**: No

## Labels

`init`, `config`, `data-loss`

## Session Log
- `/ll:confidence-check` - 2026-06-26T22:35:00Z - `6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:21:26 - `bb00a6b3-bb99-4165-8a0d-44506e20bca0.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:09:59 - `afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`
- `/ll:format-issue` - 2026-06-26T22:03:37 - `be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P1
