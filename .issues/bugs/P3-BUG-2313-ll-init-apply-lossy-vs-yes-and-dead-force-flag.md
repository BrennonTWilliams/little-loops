---
id: BUG-2313
title: "ll-init apply is lossy vs --yes; apply --force is an unused no-op"
type: BUG
status: open
priority: P3
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
decision_needed: false
labels:
- init
- apply
---

# BUG-2313: ll-init apply is lossy vs --yes; apply --force is an unused no-op

## Summary

The `ll-init --plan` → `ll-init apply` round-trip does not reproduce a full init,
even though the docs present it as the headless apply path. Separately, the `apply`
subcommand's `--force` flag is parsed but never used.

## Motivation

Users following the documented `--plan`/`apply` two-phase workflow (e.g., for CI/CD,
dry-run review, or scripted provisioning) receive a silently incomplete install. The
missing steps (`CLAUDE.md`, design tokens, issue templates, host adapters, dependency
validation) are critical to a functioning little-loops installation. The presence of
`--force` in help output implies functionality that is absent, eroding CLI trust.

## Current Behavior

`_run_apply` (`scripts/little_loops/init/cli.py:420-464`) writes only:
config + issue dirs + goals + gitignore + settings.

It **skips** steps `_run_yes` performs: `write_claude_md`,
`make_learning_tests_dir`, `deploy_design_tokens`, `deploy_issue_templates`,
host-adapter dispatch (`_dispatch_host_adapters`), and `validate_deps`. So
`ll-init --plan > p.json && ll-init apply -c p.json` yields a materially different
result than `ll-init --yes`.

The `--force` argument is declared on the apply subparser (`cli.py:594-599`) and
threaded into `_run_apply(force=...)` (`cli.py:620-625`), but the body of
`_run_apply` never references `force` — so `apply --force` is a silent no-op.

## Steps to Reproduce

1. Run `ll-init --plan -o plan.json` on any project
2. Run `ll-init apply -c plan.json`
3. Compare the resulting directory against `ll-init --yes` output
4. Observe: `CLAUDE.md`, design tokens, issue templates, host adapters, and
   learning-tests dir are absent from the `apply` path
5. Run `ll-init apply --force -c plan.json` — observe no change in behavior vs.
   without `--force`

## Expected Behavior

`apply` produces the same on-disk result as `--yes` for the same config (modulo
install/upgrade checks), or the docs/help clearly scope `apply` as a config-only
operation. `apply --force` either does something meaningful or is removed.

## Root Cause

`_run_apply` was implemented as a reduced subset of `_run_yes`'s write sequence
and the `force` parameter was wired through without a use site.

## Proposed Solution

Either (a) factor the shared write sequence out of `_run_yes` and reuse it in
`_run_apply` (preferred — single source of truth), or (b) explicitly document
`apply` as config+dirs+goals+gitignore+settings only. Remove `--force` from the
apply subparser if it has no semantics, or implement it (e.g. gate codex-adapter
overwrite / existing-file overwrite).

## Implementation Steps

**Option (a) — Full parity (preferred):**
> **Selected:** Option (a) — Full parity — `_apply_config()` in `tui.py` is a working template (same imports, call order, `force` forwarding); reuse score 3/3; zero new infrastructure required.
1. Add `plugin_root: Path` and `hosts: list[str]` parameters to `_run_apply` signature (`cli.py:420`); update the call site at `cli.py:619–625` to pass `plugin_root` (already computed at line 604) and `hosts` (already computed at lines 610–617)
2. Add the missing writer imports to `_run_apply`'s import block: `write_claude_md` (`writers.py:333`), `make_learning_tests_dir` (`writers.py:222`), `deploy_design_tokens` (`writers.py:269`), `deploy_issue_templates` (`writers.py:306`), plus `validate_deps` from `little_loops.init.validate`
3. After the existing five write calls in `_run_apply`, add the missing conditional calls following `_run_yes`'s pattern: `deploy_design_tokens` (if `config.design_tokens.enabled`), `deploy_issue_templates` (if `config.issues.deploy_templates`), `make_learning_tests_dir` (if `config.learning_tests.enabled`), `write_claude_md` (unconditional), `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)` (which gives `force` its use site), `validate_deps`
4. Fix `merge_settings` call in `_run_apply` to pass `extra_permissions=["Skill(ll:explore-api)"]` when `learning_tests` is enabled (matches `_run_yes` behavior at line 334–335)
5. Update `test_apply_from_plan` (`test_init_core.py:1335`) to assert full artifact parity: CLAUDE.md, `.ll/design-tokens/profiles/`, `.ll/templates/`, `.ll/learning-tests/.gitkeep`; model new assertions after `test_yes_deploys_design_tokens_when_enabled` (line 1361) and `test_yes_deploys_issue_templates_when_enabled` (line 1385)
6. Run `python -m pytest scripts/tests/test_init_core.py -v -k "apply"` to verify

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/CLI.md` line 61 — change apply `--force` description from "Accepts `--force` to overwrite existing configuration" to reflect the actual adapter-file-overwrite semantic (gates `.codex/hooks.json` overwrite in `install_codex_adapter`)
8. Write `test_apply_deploys_design_tokens_when_enabled` in `test_init_core.py` (`TestMainInit`) — use plan-then-apply two-phase setup; assert `(.ll/design-tokens/profiles).is_dir()`
9. Write `test_apply_deploys_issue_templates_when_enabled` — assert `(.ll/templates).is_dir()` and `≥4 *-sections.json`
10. Write `test_apply_creates_learning_tests_dir_when_enabled` — assert `(.ll/learning-tests/.gitkeep).exists()`
11. Write `test_apply_writes_claude_md` — assert `(.claude/CLAUDE.md).exists()`
12. Write `test_apply_adds_explore_api_permission_when_learning_tests` — assert `Skill(ll:explore-api)` in settings allow list
13. Write `test_apply_force_overwrites_codex_adapter` — write stub `.codex/hooks.json`, apply with `--force --hosts codex`, assert overwritten
14. Write `test_apply_installs_codex_adapter_when_host_detected` — assert `(.codex/hooks.json).exists()` after apply with `--hosts codex`
15. Write `test_plan_apply_produces_same_artifacts_as_yes` in `test_init_e2e.py` (`TestInitHeadlessEndToEnd`) — end-to-end parity test comparing `--yes` artifact tree vs `--plan`→`apply` artifact tree

**Option (b) — Explicit limited-scope + remove --force:**
1. Remove `--force` from apply subparser (`cli.py:594–599`)
2. Remove `force` parameter from `_run_apply` signature (`cli.py:424`) and the `force=getattr(args, "force", False)` kwarg from the call site (`cli.py:624`)
3. Update `docs/reference/CLI.md` and `docs/reference/COMMANDS.md` to explicitly state apply is config+dirs+goals+gitignore+settings only
4. Update `.claude/CLAUDE.md` `ll-init` entry to scope the `--plan`/`apply` path accordingly

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option (a) — Full parity (preferred)

**Reasoning**: The codebase already contains `_apply_config()` in `tui.py` as a near-exact template for the change: same writer imports, same call order, `force` forwarded to `_dispatch_host_adapters`, and `extra_permissions` conditioned on `learning_tests.enabled`. Every required writer function exists and is already tested on the `_run_yes` path. The fix is call-site wiring — adding `plugin_root` and `hosts` to `_run_apply`'s signature and threading them from `main_init` — not new infrastructure. Option (b) avoids code changes but permanently breaks the semantic contract of "apply" and leaves the documented `--plan`/`apply` headless workflow crippled.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option (a) — Full parity | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option (b) — Limited scope | 1/3 | 3/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
- Option (a): `_apply_config()` in `tui.py` (lines 808–881) is a working template; `plugin_root` and `hosts` are already computed in `main_init` before the `apply` branch; all writers are reusable; `test_apply_from_plan` (line 1335) and `test_yes_deploys_design_tokens_when_enabled` (line 1361) give assertion models.
- Option (b): Simplest code change (remove `--force`, update docs) but breaks the documented `--plan`/`apply` headless install workflow and contradicts the TUI's `_apply_config()` precedent, which does perform full parity.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_run_apply` (lines 420–464), `_run_yes` (lines 128–351), apply subparser (lines 583–599), `main_init` call site (lines 619–625)
- `scripts/little_loops/init/writers.py` — no changes needed; all writer functions used by `_run_yes` already exist and are reusable

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:620` — only call site for `_run_apply`, inside `main_init()` guarded by `args.command == "apply"`; `plugin_root` (line 604) and `hosts` (lines 610–617) are computed here but not currently threaded into `_run_apply`

### Similar Patterns
- `_run_yes` (lines 128–351) — the reference write sequence; imports 9 writers from `little_loops.init.writers` plus calls `_dispatch_host_adapters` and `validate_deps`
- `_apply_config()` in `scripts/little_loops/init/tui.py` — **already an extraction of the shared write sequence**; called by the TUI path and accepts `(config, project_root, ll_dir, config_path, templates_dir, plugin_root, hosts, settings_target, force, console, claude_md_opt_in)`; calls the same writer functions as `_run_yes`; differs only in taking a Rich `console` object and `claude_md_opt_in` bool — this is a direct precedent for extracting a headless equivalent
- `install_codex_adapter` in `writers.py` — the downstream consumer of `force`; guards `.codex/hooks.json` overwrite with `if dest.exists() and not force: return False`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py:1335` — `test_apply_from_plan` exists but only asserts `.ll/ll-config.json` is present; needs parity assertions for CLAUDE.md, design tokens, issue templates, learning-tests dir — **update existing test**
- `scripts/tests/test_init_core.py:1361` — `test_yes_deploys_design_tokens_when_enabled` — model for parallel apply-path tests (no changes needed)
- `scripts/tests/test_init_core.py:1385` — `test_yes_deploys_issue_templates_when_enabled` — model for parallel apply-path tests (no changes needed)
- `scripts/tests/test_init_core.py:1410` — `test_yes_adds_explore_api_permission_when_learning_tests` — model for `apply` path `extra_permissions` test (no changes needed)
- `scripts/tests/test_init_core.py:1612` — `test_hosts_codex_installs_adapter` — model for `apply --hosts codex` test (no changes needed)
- `scripts/tests/test_init_core.py:927` — `test_overwrites_with_force` — low-level writer test for `force=True`; confirms writer already handles it (no changes needed)
- `scripts/tests/integration/test_init_e2e.py:39` — `test_dry_run_writes_nothing_then_apply_generates_config` exercises `--yes`, not the `apply` subcommand; no `apply` subcommand coverage here — **no change needed but gap noted**

**New tests to write** (in `scripts/tests/test_init_core.py`, class `TestMainInit`):
- `test_apply_deploys_design_tokens_when_enabled` — assert `(.ll/design-tokens/profiles).is_dir()` after apply with `design_tokens.enabled`; model after `test_yes_deploys_design_tokens_when_enabled` + plan-then-apply two-phase setup from `test_apply_from_plan`
- `test_apply_deploys_issue_templates_when_enabled` — assert `(.ll/templates).is_dir()` and `≥4 *-sections.json` files; model after `test_yes_deploys_issue_templates_when_enabled`
- `test_apply_creates_learning_tests_dir_when_enabled` — assert `(.ll/learning-tests/.gitkeep).exists()`; model after `TestMakeLearningTestsDir` (line 785)
- `test_apply_writes_claude_md` — assert `(.claude/CLAUDE.md).exists()` after apply
- `test_apply_adds_explore_api_permission_when_learning_tests` — assert `Skill(ll:explore-api)` in settings allow list when `learning_tests.enabled`; model after `test_yes_adds_explore_api_permission_when_learning_tests`
- `test_apply_force_overwrites_codex_adapter` — write stub `.codex/hooks.json`, apply with `--force`, assert overwritten; model at writer level from `test_overwrites_with_force` (line 927)
- `test_apply_installs_codex_adapter_when_host_detected` — assert `(.codex/hooks.json).exists()` after apply with `--hosts codex`; model after `test_hosts_codex_installs_adapter` (line 1612)

**New integration test** (in `scripts/tests/integration/test_init_e2e.py`, class `TestInitHeadlessEndToEnd`):
- `test_plan_apply_produces_same_artifacts_as_yes` — run `--yes` in one dir, `--plan`→`apply` in another, assert same key artifacts (CLAUDE.md, design-tokens, issue templates, learning-tests dir, settings)

### Documentation
- `docs/reference/CLI.md` — documents `ll-init` `--plan`, `--yes`, `--force`, and `apply` subcommand options; **line 61 specifically describes `apply --force` as "Accepts `--force` to overwrite existing configuration"** — this prose needs updating to reflect the actual narrower semantic (`force` gates `.codex/hooks.json` overwrite via `install_codex_adapter`; it does not overwrite configuration broadly)
- `docs/reference/COMMANDS.md` — includes `ll-init` entry in Common Workflows section; describes `/ll:init` skill flags, not the `apply` subcommand — no change required
- `docs/reference/API.md` — Python API docs for the init module; update if `_run_apply` signature changes are surfaced in public API
- `.claude/CLAUDE.md` — `ll-init` entry documents `--plan`/`apply` as the headless apply path; current description already matches the intended post-fix state — no change required

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md:90` — `--force` table row describes flag for the `--yes` path only ("Reset to template defaults"); after fix, `--force` also has meaning on `apply` path but with different narrower semantics — optional clarification update

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct code analysis:_

**Writer parity table** (`_run_yes` vs `_run_apply`):

| Writer / function | `_run_yes` | `_run_apply` |
|---|---|---|
| `write_config` | ✓ | ✓ |
| `make_issue_dirs` | ✓ | ✓ |
| `deploy_goals` (conditional) | ✓ | ✓ |
| `update_gitignore` | ✓ | ✓ |
| `merge_settings` | ✓ (with `extra_permissions` when `learning_tests.enabled`) | ✓ (no `extra_permissions`, always) |
| `deploy_design_tokens` (conditional) | ✓ | ✗ **MISSING** |
| `deploy_issue_templates` (conditional) | ✓ | ✗ **MISSING** |
| `make_learning_tests_dir` (conditional) | ✓ | ✗ **MISSING** |
| `write_claude_md` (unconditional) | ✓ | ✗ **MISSING** |
| `_dispatch_host_adapters` | ✓ | ✗ **MISSING** |
| `validate_deps` | ✓ | ✗ **MISSING** |

**`force` data flow**: `_run_yes` forwards `force` to `_dispatch_host_adapters` (line 339), which passes it to `install_codex_adapter` in `writers.py`. `install_codex_adapter` uses it to guard `.codex/hooks.json` overwrites. In `_run_apply`, `force` is received at line 424 but never forwarded anywhere.

**Signature gap in `_run_apply`**: The function currently accepts `(plan_config, project_root, templates_dir, force)`. To support option (a), it needs two additional parameters: `plugin_root: Path` (for `_dispatch_host_adapters`) and `hosts: list[str]` (for host-adapter dispatch). Both are available in `main_init` at the call site (lines 604 and 617) and just need to be threaded through.

**apply subparser gap**: The apply subparser (lines 583–599) has no `--hosts` argument. The `main_init` already computes `hosts` via `_detect_hosts()` before dispatching to `_run_apply`, so no new subparser argument is needed — hosts just need to be passed in the `_run_apply` call at lines 619–625.

## Impact

- **Priority**: P3 — Affects users of the documented `--plan`/`apply` workflow; silent failure makes debugging difficult
- **Effort**: Small — Refactoring `_run_apply` to reuse `_run_yes`'s write sequence; no new logic required
- **Risk**: Low — Fix only affects the broken `apply` path; the `--yes` path is untouched
- **Breaking Change**: No

## Labels

- init, apply

## Session Log
- `/ll:wire-issue` - 2026-06-26T22:32:54 - `f021f33c-5e61-4358-a597-9532143b16da.jsonl`
- `/ll:decide-issue` - 2026-06-26T22:20:54 - `3416107d-7c94-4246-a2a6-aa66474de885.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:13:00 - `bb00a6b3-bb99-4165-8a0d-44506e20bca0.jsonl`
- `/ll:format-issue` - 2026-06-26T22:03:51 - `afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
