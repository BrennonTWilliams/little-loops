---
id: BUG-2312
title: ll-init --dry-run preview diverges from actual --yes actions
type: BUG
status: done
priority: P2
captured_at: '2026-06-26T21:55:52Z'
completed_at: '2026-06-27T00:46:19Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
decision_needed: false
labels:
- init
- dry-run
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 23
---

# BUG-2312: ll-init --dry-run preview diverges from actual --yes actions

## Summary

`ll-init --dry-run` prints a preview that does not match what `--yes` actually
does: it lists issue subdirectories that are never created, omits one that is, and
skips several real write actions. A dry-run that misrepresents the plan defeats
its purpose.

## Motivation

Users rely on `--dry-run` to audit what an `ll-init` run will change before
committing. A mismatched preview either causes users to skip the safety check
entirely (since it appears unreliable) or leads them to proceed trusting a plan
that misrepresents what will actually happen — both outcomes undermine the
feature's purpose.

## Current Behavior

`_print_dry_run` (`scripts/little_loops/init/cli.py:354-381`):

- Line 370 iterates `("bugs", "features", "enhancements", "completed", "deferred")`
  for `[mkdir]` lines — but `make_issue_dirs` actually creates
  `_ISSUE_SUBDIRS = ("bugs", "features", "enhancements", "epics")`
  (`scripts/little_loops/init/writers.py:55`). So the preview shows
  `completed`/`deferred` (never made) and hides `epics` (made).
- The preview omits actions `_run_yes` performs when enabled:
  `make_learning_tests_dir`, `deploy_design_tokens`, `deploy_issue_templates`,
  and the `Skill(ll:explore-api)` permission added to settings when
  learning_tests is enabled.

## Steps to Reproduce

1. Run `ll-init --dry-run` in any project directory
2. Note the listed `[mkdir]` lines in the preview output
3. Run `ll-init --yes` in the same directory (or a scratch copy)
4. Compare actual directories created against the dry-run preview
5. Observe: preview shows `.issues/completed` and `.issues/deferred` (never
   created), omits `.issues/epics` (actually created), and skips
   learning-tests dir, design-token profiles, issue section templates, and
   the explore-api permission write

## Expected Behavior

Dry-run output enumerates exactly the directories and files `--yes` would create,
including learning-tests dir, design-token profiles, issue section templates, and
the explore-api permission (when those features are enabled).

## Root Cause

`_print_dry_run` hardcodes a stale subdir list and a partial action list instead
of deriving them from the same helpers `_run_yes` calls (`make_issue_dirs` uses
`_ISSUE_SUBDIRS`; the deploy/permission steps are gated on config flags).

## Proposed Solution

Drive the preview from `writers._ISSUE_SUBDIRS` rather than a literal, and mirror
the same config-gated branches `_run_yes` uses (learning_tests, design_tokens,
deploy_templates, explore-api permission). Consider routing dry-run through the
real writer functions with `dry_run=True` (they already support it) so preview and
execution share one code path and cannot drift again.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_print_dry_run()`: hardcoded subdir list and missing config-gated action branches

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/writers.py` — source of truth for `_ISSUE_SUBDIRS`, `make_issue_dirs`, `make_learning_tests_dir`, `deploy_design_tokens`, `deploy_issue_templates`
- `scripts/little_loops/init/cli.py` — `_run_yes()`: authoritative action list that `_print_dry_run` must mirror

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/__init__.py` — `__all__` exports the writer/validate symbols but **not** `_print_dry_run` (it is module-private); deleting `_print_dry_run` requires **no** `__all__` change. Confirmed: `_print_dry_run` has no callers outside `cli.py` (only prose references in `.ll/decisions.yaml` and `.issues/` files). [Agent 1+2 finding — verified]
- `scripts/little_loops/cli/__init__.py` — imports `main_init` (line 80) as the `ll-init` console-script entry point; Option B does not change `main_init`'s signature or exit-code contract, so no change needed here. [Agent 1+2 finding]
- `scripts/little_loops/init/tui.py` — `_apply_config()` imports `_dispatch_host_adapters` from `cli.py` (line ~823); that symbol stays in `cli.py` under Option B so the import remains valid. NOTE: `_apply_config()` runs the same writer sequence as `_run_yes` without `dry_run` threading — the TUI parity gap already flagged in this issue; out of scope here. [Agent 1+2 finding]

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_init_core.py` — add/update tests verifying dry-run output matches actual writes for each config-gated branch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/integration/test_init_e2e.py` — `TestInitHeadlessEndToEnd.test_dry_run_writes_nothing_then_apply_generates_config` (line 39): runs `--yes --dry-run` then `--yes`, asserts dry-run writes nothing. No stdout assertions → passes under Option B unchanged. Strong candidate to **extend** with the `[mkdir]`/`[write]` stdout-parity check (it already runs both modes). [Agent 1+3 finding]
- `scripts/tests/test_wheel_smoke.py` — `test_ll_init_dry_run_succeeds` (line 156): subprocess smoke test against an installed venv, asserts only `returncode == 0`. Passes under Option B; verify still green after the refactor. [Agent 2 finding]
- `scripts/tests/test_deploy_issue_templates.py` — `test_dry_run` (line 72): exercises `deploy_issue_templates(dry_run=True)` directly and asserts `[write]` in stdout. Unaffected, but confirms the writer already emits the correct token Option B will surface. [Agent 2 finding — supporting evidence]
- **No existing tests break.** Both `test_dry_run_yes_exits_zero` (`test_init_core.py:1215`) and the two `TestHostDispatch` dry-run tests (`:1813`, `:1823`) assert on tokens emitted by writers / `_dispatch_host_adapters`, not by `_print_dry_run`'s headers — all remain valid. [Agent 2+3 finding]

**Test patterns confirmed (model new tests after these):**
- CLI-level dry-run capture: `TestHostDispatch.test_dry_run_codex_shows_write_line` (`test_init_core.py:1813`) — `patch("...cli._plugin_root", return_value=_PROJECT_ROOT)`, call `main_init([...,"--dry-run",...])`, assert token in `capsys.readouterr().out`.
- Feature-flag injection for CLI tests: `TestMainInit.test_yes_deploys_design_tokens_when_enabled` (`:1519`) and `test_yes_adds_explore_api_permission_when_learning_tests` (`:1568`) use a `patched_build` wrapper around `init.core.build_config` to force `design_tokens.enabled`/`learning_tests.enabled` — reuse this for the new `test_dry_run_shows_*_when_enabled` tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Precise anchor locations in `cli.py`:**
- `_print_dry_run()` — lines 354–381; line 370 has the hardcoded tuple; line 374 calls `write_claude_md(project_root, dry_run=True)` (already the "delegate to real writer" pattern — needs to be extended)
- `_run_yes()` — the actual writer-call sequence lives at lines 308–351; the `if dry_run` early-exit branch is at lines 308–310

**Writer functions already support `dry_run=True` (all confirmed):**
- `make_issue_dirs(base_dir, dry_run=False)` — `writers.py:253` — prints `[mkdir] <base_dir>/<subdir>` for each of `_ISSUE_SUBDIRS` and returns without creating dirs
- `make_learning_tests_dir(ll_dir, dry_run=False)` — `writers.py:268` — prints `[mkdir] <path>` and returns
- `deploy_design_tokens(ll_dir, templates_dir, active_profile, dry_run=False)` — `writers.py:315` — prints `[write]` and returns
- `deploy_issue_templates(ll_dir, templates_dir, dry_run=False)` — `writers.py:352` — prints `[write]` and returns
- `merge_settings(..., dry_run=False)` — already has dry-run support; `extra_permissions` argument carries the conditional `Skill(ll:explore-api)` entry
- `_dispatch_host_adapters(hosts, project_root, plugin_root, force, dry_run=False)` — already threads `dry_run` into `install_codex_adapter()` (Pattern 3 confirmed in `cli.py:67–98`)

**`merge_settings` and `extra_permissions` nuance for structural fix:** `extra_permissions` is computed at `_run_yes` line 332–335 (after the current `if dry_run` early-exit at 308–310). Any structural fix that removes the early-exit must ensure `extra_permissions` is computed before the `merge_settings` call so the dry-run preview also reflects the conditional `Skill(ll:explore-api)` permission.

**Test patterns to follow:**
- `TestMainInit.test_dry_run_yes_exits_zero` (`test_init_core.py:1215`) — add `capsys.readouterr().out` assertions to this test or add sibling tests
- `TestHostDispatch.test_dry_run_codex_shows_write_line` (`test_init_core.py:1813`) — canonical shape: call `main_init()` with `--dry-run`, capture stdout, assert token appears and file does not exist

**Missing test names to add inside `TestMainInit`:**
- `test_dry_run_shows_epics_not_completed_deferred` — asserts `"epics"` in stdout, `"completed"` not in stdout, `"deferred"` not in stdout
- `test_dry_run_shows_design_tokens_when_enabled` — asserts design-tokens line in stdout when `design_tokens.enabled=true`
- `test_dry_run_shows_issue_templates_when_enabled` — asserts templates line when `issues.deploy_templates=true`
- `test_dry_run_shows_learning_tests_when_enabled` — asserts learning-tests dir line and `Skill(ll:explore-api)` mention when `learning_tests.enabled=true`
- `test_dry_run_output_matches_yes_writes` — parity test: run `--dry-run`, parse `[mkdir]`/`[write]`/`[update]` paths from stdout; run `--yes` in a separate `tmp_path`; assert the two path sets are equal

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- **Verified no change needed** — these document `--dry-run` only at the user-facing flag level ("preview without writing files"), which Option B preserves. None describe the internal output format (`=== DRY RUN ===` headers, `--- Configuration Preview ---`), so deleting those headers breaks no doc: `docs/reference/CLI.md` (`## ll-init`, flag line ~47, example ~81), `docs/reference/COMMANDS.md` (`/ll:init` flags ~32), `docs/guides/GETTING_STARTED.md` (~91), `docs/codex/getting-started.md` (~38), `commands/help.md` (`/ll:init` flags ~236), `skills/init/SKILL.md` (~56), `.claude/CLAUDE.md` (~219). [Agent 2 finding]
- **Cross-issue consistency note:** `.issues/enhancements/P3-ENH-2043-ll-init-tui-add-claude-md-update-screen.md:138` has an acceptance criterion that `ll-init --yes --dry-run` lists `[write/update] .claude/CLAUDE.md`. This stays satisfied — the `[write]`/`[update]` tokens are emitted by `write_claude_md(dry_run=True)` itself, which Option B still calls. No coordination required, but the implementer should keep `write_claude_md`'s dry-run output intact. [Agent 2 finding]

### Configuration
- N/A — the dry-run output format is not referenced in `config-schema.json`, `docs/reference/API.md`, or any JSON schema (verified by Agent 2; no schema coupling).

## Implementation Steps

1. Replace the hardcoded `("bugs", "features", "enhancements", "completed", "deferred")` tuple in `_print_dry_run` with `writers._ISSUE_SUBDIRS`
2. Add preview lines for each config-gated branch `_run_yes` exercises: learning-tests dir, design-token deploy, template deploy, explore-api permission
3. (Optional) Route dry-run through the actual writer functions with `dry_run=True` to share one code path and prevent future drift
4. Update/add tests confirming dry-run preview matches `--yes` output for all config-flag combinations

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Two concrete implementation options confirmed viable by research:

### Option A — Targeted fix to `_print_dry_run` (lower change surface)

Fix `_print_dry_run` in place (`cli.py:354–381`):

1. Replace line 370 hardcoded tuple with `writers._ISSUE_SUBDIRS` — or call `make_issue_dirs(issues_base, dry_run=True)` directly (writer already prints the correct lines)
2. After line 371, add the three missing config-gated branches (all three writer functions already print the correct `[write]`/`[mkdir]` lines when called with `dry_run=True`):
   ```python
   if config.get("design_tokens", {}).get("enabled"):
       deploy_design_tokens(ll_dir, templates_dir, dry_run=True)
   if config.get("issues", {}).get("deploy_templates"):
       deploy_issue_templates(ll_dir, templates_dir, dry_run=True)
   if config.get("learning_tests", {}).get("enabled"):
       make_learning_tests_dir(ll_dir, dry_run=True)
   ```
3. Update line 373 `[update] .claude/settings.local.json` to conditionally note `Skill(ll:explore-api)` when `learning_tests.enabled`
4. Tradeoff: future writer additions still require manual sync with `_print_dry_run`

### Option B — Structural fix: remove `_print_dry_run`, delegate to writers (eliminates drift risk)

> **Selected:** Option B — single guarded code path eliminates the preview/execution drift class (this bug's recurring root cause) and matches the dominant `dry_run`-threading convention.

1. Delete `_print_dry_run()` entirely (lines 354–381)
2. In `_run_yes()`, remove the early-exit `if dry_run: _print_dry_run(...); return 0` block (lines 308–310)
3. Each existing writer call in `_run_yes` already accepts `dry_run` — thread it through: `make_issue_dirs(issues_base, dry_run=dry_run)`, `deploy_design_tokens(ll_dir, templates_dir, dry_run=dry_run)`, etc.
4. **`extra_permissions` ordering constraint**: compute `extra_permissions = ["Skill(ll:explore-api)"] if config.get("learning_tests", {}).get("enabled") else None` _before_ the `merge_settings` call (currently at line 332, already after the removed early-exit — no reordering needed)
5. `_dispatch_host_adapters` already threads `dry_run` (confirmed at `cli.py:67–98`) — no change needed there
6. `write_claude_md(project_root, dry_run=True)` is already correct in `_print_dry_run` — same call works in `_run_yes`
7. Tradeoff: eliminates the divergence class entirely; any new writer step automatically appears in both dry-run and live output

**Test additions (both options):** Add to `TestMainInit` in `test_init_core.py`:
- `test_dry_run_shows_epics_not_completed_deferred` — check stdout for `"epics"`, absence of `"completed"` and `"deferred"`
- `test_dry_run_shows_design_tokens_when_enabled` — set `design_tokens.enabled=true`, check stdout
- `test_dry_run_shows_learning_tests_when_enabled` — set `learning_tests.enabled=true`, check for learning-tests dir and `Skill(ll:explore-api)` in stdout
- `test_dry_run_output_matches_yes_writes` — parity test: parse `[mkdir]`/`[write]`/`[update]` path tokens from `--dry-run` stdout, run `--yes` in a second `tmp_path`, assert sets are equal; model after `TestHostDispatch.test_dry_run_codex_shows_write_line` (`test_init_core.py:1655`)

**TUI parity note:** Locator agent found `scripts/little_loops/init/tui.py` with `_apply_config()` — may have a parallel divergence (out of scope for this issue but worth noting during implementation review).

### Wiring Phase (added by `/ll:wire-issue`)

_Verified against `cli.py:308–351`. Precise touchpoints for the Option B refactor:_

1. **Thread `dry_run=dry_run` into every writer call in `_run_yes`** (currently none pass it, lines 315–337): `write_config(config, ll_dir, dry_run=dry_run)`, `make_issue_dirs(issues_base, dry_run=dry_run)`, `deploy_goals(ll_dir, templates_dir, dry_run=dry_run)`, `deploy_design_tokens(ll_dir, templates_dir, dry_run=dry_run)`, `deploy_issue_templates(ll_dir, templates_dir, dry_run=dry_run)`, `make_learning_tests_dir(ll_dir, dry_run=dry_run)`, `update_gitignore(project_root, dry_run=dry_run)`, `merge_settings(project_root, extra_permissions=extra_permissions, dry_run=dry_run)`, `write_claude_md(project_root, dry_run=dry_run)`.
2. **`_dispatch_host_adapters` gap (not named in the Option B steps):** the call at `cli.py:339` is `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)` — it does **not** currently pass `dry_run`. Add `dry_run=dry_run`. The function already threads `dry_run` into `install_codex_adapter` and the Pi/codex preview branches, so the host-adapter dry-run output (`.codex/hooks.json`, "not yet available") is reproduced automatically once the argument is passed.
3. **`validate_deps` guard must wrap the print too:** lines 341–347 begin with `print("\nValidating dependencies...")` *before* `validate_deps(...)` (which spawns a subprocess). The `if not dry_run:` guard must enclose **both** the preceding print and the call — guarding only the call leaves a spurious "Validating dependencies..." line in dry-run output. No test asserts on that string, so it is a polish/correctness detail, not a test-break.
4. **Guard the success prints:** lines 349–350 (`"✓ little-loops initialized…"`, `"  Config: …"`) under `if not dry_run:`. The pre-existing config-merge prints (lines ~173–176) are already gated on `not dry_run`, so no change there.
5. **Move the `write_claude_md(dry_run=True)` delegation** out of the deleted `_print_dry_run` (`cli.py:374–376`) — it becomes the threaded `write_claude_md(project_root, dry_run=dry_run)` call in step 1.
6. **No `__init__.py` change** — `_print_dry_run` is not in `__all__`; deletion is local to `cli.py`.
7. **Verify (don't modify) existing tests:** `scripts/tests/integration/test_init_e2e.py::test_dry_run_writes_nothing_then_apply_generates_config` and `scripts/tests/test_wheel_smoke.py::test_ll_init_dry_run_succeeds` must stay green post-refactor.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option B — Structural fix: remove `_print_dry_run`, delegate to writers

**Reasoning**: Option B threads `dry_run` through the real execution path and deletes the
parallel preview function, eliminating the divergence class entirely — the root cause of this
bug, which already recurred once (CHANGELOG:115 records `_ISSUE_SUBDIRS` being updated while
`_print_dry_run` was not). It matches the dominant codebase convention: `_dispatch_host_adapters`
(`cli.py:67–98`), `migrate.py`, `migrate_status.py`, `sync.py`, and `issue_manager.py` all guard a
single path rather than maintain a separate preview. Option A scores higher on contained risk but
perpetuates the exact dual-path structure that caused this bug; its own research notes the
manual-sync requirement will keep recurring on future writer additions.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Targeted fix to `_print_dry_run` | 2/3 | 2/3 | 2/3 | 3/3 | 9/12 |
| Option B — Structural delegate to writers | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: All building blocks exist (`_ISSUE_SUBDIRS`, every writer's `dry_run=True` branch, the `learning_tests → Skill(ll:explore-api)` conditional copy-pasteable from `_run_yes:332–334`), so the change is contained and zero-risk to the write path — but it keeps two parallel code paths that must be hand-synced, which is what drifted to produce this bug.
- Option B: The entire writer layer was designed for this — all 10 writers in `writers.py` accept `dry_run=True` with consistent print-and-return behavior, and `_dispatch_host_adapters` already uses the identical threading pattern. The only added work is two `if not dry_run:` guards around the non-writer steps that the early-exit currently skips: `validate_deps` (`cli.py:341–347`, spawns a subprocess) and the `"✓ little-loops initialized"` success print (`cli.py:349`).

## Impact

- **Priority**: P2 — Directly misleads users who rely on `--dry-run` as a safety check before modifying their project; no data loss but no risk of unexpected writes either since `--dry-run` never writes
- **Effort**: Small — Targeted fix inside `_print_dry_run`; likely < 30 lines changed
- **Risk**: Low — Dry-run path is separate from the write path; changes here carry no risk to actual file creation
- **Breaking Change**: No

## Labels

- init, dry-run

## Session Log
- `/ll:ready-issue` - 2026-06-27T00:29:59 - `5d1547b1-76d6-46c9-8a24-8313f8419fc0.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:30:00 - `4b080503-4c71-4702-a078-09c688f2a45e.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:00:00 - `0738aae2-208f-4800-b6cb-aef4cfec50d1.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:33:12 - `f021f33c-5e61-4358-a597-9532143b16da.jsonl`
- `/ll:decide-issue` - 2026-06-26T22:17:14 - `603866f5-8095-4955-b453-410ab44be55e.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:10:31 - `603866f5-8095-4955-b453-410ab44be55e.jsonl`
- `/ll:format-issue` - 2026-06-26T22:03:31 - `68871b26-546d-4419-8239-1e57f809c714.jsonl`
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
