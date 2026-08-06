---
id: ENH-3068
priority: P2
type: ENH
status: done
discovered_date: 2026-08-05
discovered_by: audit
completed_at: 2026-08-06T00:04:41Z
relates_to:
- ENH-2434
- ENH-2701
labels:
- init
- audit-remediation
- cli
- ux
---

# ENH-3068: Remediate ll-init audit findings (defects, wiring, UX, output layer)

## Summary

Remediate all valid findings from the `ll-init` audit (`thoughts/ll-init-audit-2026-08-05.md`):
4 High-severity confirmed defects, 8 Medium settings/feature-wiring gaps, and 9 UX/output-layer
issues. Every finding was first re-verified against source and by executing the code paths, then
fixed, with new and updated tests and a full-suite regression run.

## Motivation

`ll-init` is the onboarding command — the first thing a new user runs. The audit found that it
silently corrupted user intent in several ways (a requested `--force` reset downgraded to a merge;
a selected worker count was dropped, halving parallelism), crashed on prerelease version strings,
and produced structurally narrower configs when run headlessly versus interactively. It also
bypassed the repo's shared output layer entirely, ignoring `NO_COLOR`/`FORCE_COLOR`/`config.cli.color`
and leaking hardcoded `✓` glyphs into pipes. For the command that *is* the first-run experience,
these are the highest-leverage correctness and polish fixes available.

## Current Behavior

Before this change (all reproduced by executing the code, quoted in the audit):

- `ll-init --force apply -c plan.json` ran a **merge**, not the requested reset, because the
  `apply` subparser re-declared `--force` and argparse let its default overwrite the parent's `True`.
- `ll-init --hosts codex apply -c plan.json` errored with `invalid choice` — `--hosts nargs="+"`
  swallowed the `apply` subcommand.
- `check_version("1.2.0rc1", "1.2.0")` raised `ValueError` (raw traceback); `check_version("1.2","1.2.0")`
  false-positived `OutOfDate`.
- The TUI compared `parallel.max_workers` against a hardcoded sentinel `4` while the schema default
  is `2`, so accepting the wizard's suggested value dropped the key and runtime used 2 workers.
- `build_config()` had no branch for `parallel`/`documents`/`design_tokens`/`sync`/`commands`, so
  headless `--yes` produced a config missing those sections entirely (TUI-only).
- `--enable X --disable X` silently resolved to disabled; `--plan` advertised a config `apply` would
  not produce (no merge preview); `apply` had no `--dry-run`; `host_options` omitted kimi-code.
- `init/` had **zero** `cli.output` usage (vs 27 `configure_output()` sites elsewhere), three
  competing output vocabularies, no next-steps on any path, and a wizard screen counter that started
  at "2 / 7" on a healthy install.

## Expected Behavior

After this change:

- Both `ll-init --force apply …` and `ll-init apply … --force` perform a true reset; `--hosts` no
  longer swallows the subcommand and is repeatable/comma-split.
- Version comparison tolerates `rc`/`dev`/`+local` suffixes and unequal segment counts without
  crashing or false positives; `main_init` exits 1 (not a traceback) on comparison errors.
- The TUI writes `max_workers` when the user's value differs from the schema default; accepting the
  prompt default round-trips correctly.
- Headless `--enable/--disable` covers every section the TUI writes; headless and wizard configs are
  equivalent; schema defaults are the single default source (templates carry only structure).
- `--force` resets config **and** redeploys bundled artifacts; `--plan` and `apply` are contractually
  consistent; `apply --dry-run` previews without writing; explicit host selection persists to
  `orchestration.host_cli`/`hooks.host`.
- `ll-init` honors `NO_COLOR`/`FORCE_COLOR`/`--color`/`--no-color`, uses one output vocabulary, ends
  every path with a summary + next steps, and the wizard screen counter is accurate.

## Scope Boundaries

**In scope:** every High and Medium finding (H-1..H-4, M-1..M-8), the `--force` reset decision (M-4),
the output-layer/UX findings (U-1..U-6), host-selection persistence (rec-13), and the test-coverage
gaps (rec-17), all from the 2026-08-05 audit.

**Out of scope:**
- Collapsing the wizard's Screen-2 `declared`-provenance prompts into a single confirm (rec-15) —
  deferred by explicit decision to keep this pass focused; the screen-counter fix (rec-16) was done.
- Rewriting `/ll:configure` internals (audit scope excluded it).
- The unrelated pre-existing `README.md` "typed CLI tools" count mismatch surfaced by the full-suite
  run (see Resolution) — not caused by, nor part of, this work.

## Implementation Steps

1. Verify every audit claim against source and by execution; confirm all findings reproduce.
2. Fix the four High defects (parser shadowing, `--hosts`, `check_version`, workers sentinel).
3. Close the wiring gaps (`build_config` branches, template cleanup, conflict error, plan/apply
   parity, `apply --dry-run`, `host_options`, host persistence) and widen `--force`.
4. Adopt the shared output layer, unify vocabulary, add next steps + shared summary, fix dry-run
   output and the screen counter, and repair the `/ll:init` skill.
5. Add a dedicated test suite and update existing assertions; run the full suite + ruff.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `--force`/`--dry-run` distinct dests + OR-combine (H-1);
  `--hosts` `action="append"` (H-2); `--enable`/`--disable` conflict → exit 2 (M-5); `_run_plan`
  merge preview + complete `host_options` (M-6/M-8); `_run_apply` `--dry-run` + `requested_upgrade`
  (M-7); `_persist_host_selection` (rec-13); `configure_output` + `--color`/`--no-color` (U-1);
  `_print_next_steps`/`_render_headless_summary` (U-3/rec-11); widened `except (OSError, ValueError, …)` (H-3).
- `scripts/little_loops/init/install_check.py` — `check_version` rebuild: `_version_key` /
  `_pad_version_keys` helpers, PEP 440 build-metadata strip (H-3).
- `scripts/little_loops/init/core.py` — `build_config` branches for `parallel`/`documents`/
  `design_tokens`/`sync`/`confidence_gate`/`tdd` (M-1); `schema_enum` helper; schema-wins precedence
  documented (M-3/rec-14).
- `scripts/little_loops/init/tui.py` — schema-derived workers sentinel + prompt default (H-4);
  schema-derived confidence-gate thresholds; screen-counter fix (U-5); shared summary rows +
  next-steps footer (rec-11/U-3); host persistence (rec-13).
- `scripts/little_loops/init/writers.py` — `force=` on deploy writers (M-4); dry-run output through
  output layer (U-4); `DEFAULT_SETTINGS_FILE` constant (M-8); lazy `info` to avoid circular import.
- `scripts/little_loops/init/summary.py` — **new** shared config-summary extractor feeding both
  headless and TUI completion surfaces (rec-11).
- `scripts/little_loops/cli/output.py` — new `set_use_color()` for explicit `--color`/`--no-color`.
- `scripts/little_loops/templates/*.json` (9 templates) — removed dead `product`/`analytics`/
  `context_monitor` blocks; kept the ARCHITECTURE-096 `parallel` stamp (M-2/M-3).
- `skills/init/SKILL.md` — replaced GNU-only `grep -oP` with POSIX-portable bash parameter
  expansion; clarified `--dry-run` semantics and wizard routing (U-6).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/__init__.py` re-exports `writers` — the lazy `info()` shim avoids the
  `cli.output → cli/__init__ → verify_cli_allowlist → init.writers` circular import.

### Tests
- `scripts/tests/test_init_audit_fixes.py` — **new**, 36 tests covering each finding + schema-coverage guard.
- `scripts/tests/test_init_core.py` — updated dry-run marker assertions, Kimi adapter message, and
  dry-run line-parsing for the new output shape.
- `scripts/tests/test_init_tui.py` — worker-sentinel tests now schema-derived (H-4 regression).
- `scripts/tests/test_deploy_issue_templates.py` — dry-run marker assertion.

### Documentation
- `thoughts/ll-init-audit-2026-08-05.md` — source audit (this issue remediates it).
- `skills/init/SKILL.md` — flag parsing + dry-run semantics.

### Configuration
- `scripts/little_loops/config-schema.json` — read-only reference (`schema_default`/`schema_enum`);
  not modified.

## Program Design

### Signatures
- `schema_enum(dotted_path: str) -> list[str]`
- `check_version(installed: str, latest: str) -> InstallStatus`
- `_version_key(version: str) -> tuple[tuple[int, int, str], ...]`
- `_persist_host_selection(config: dict, hosts: list[str], explicit: bool) -> None`
- `summary_rows(config: dict, project_root: Path, include_features: bool = True) -> list[tuple[str, str]]`
- `set_use_color(enabled: bool) -> None`
- `_run_apply(..., force: bool, dry_run: bool = False, hosts_explicit: bool = False) -> int`

### Call Path
`main_init` -> `_feature_choices_from_args` (conflict check) -> `_run_apply` ->
`_persist_host_selection` + `merge_with_existing` -> writers (`force=`/`dry_run=`) ->
`_dispatch_host_adapters` / `_dispatch_host_upgrade` -> `_print_next_steps`.

## Impact

- **Priority**: P2 — four confirmed High defects include silent correctness loss (`--force`
  downgraded to merge; selected workers dropped) and a crash on common prerelease version strings,
  all on the onboarding command.
- **Effort**: Large — spans 9 source files, 9 templates, 1 skill, and 4 test files; but each fix is
  localized and reuses existing patterns (`schema_default`, `cli.output`, `merge_with_existing`).
- **Risk**: Low/Medium — behavior changes are intentional and covered by 36 new tests; circular-import
  risk in `writers.py` was handled with a lazy-import shim; full-suite run confirms no regressions.
- **Breaking Change**: No public API removed. Dry-run output shape changed (raw JSON dump replaced by
  a planned-write line + summary), and `--force` now also redeploys bundled artifacts — both are the
  intended, documented new behavior.

## Labels

`init`, `audit-remediation`, `cli`, `ux`, `output-layer`, `high-severity-defects`

## Related Documentation

- `thoughts/ll-init-audit-2026-08-05.md` — the audit this issue remediates (findings H-1..H-4,
  M-1..M-8, U-1..U-6, and recommendations 1-18).

---

## Resolution

Implemented 2026-08-05 in a single remediation session. All findings were verified against source
and by execution before fixing.

**High defects (all four):**
- **H-1** — `apply` subparser `--force`/`--dry-run` now use distinct dests (`apply_force`,
  `apply_dry_run`), OR-combined with the parent flags in `main_init`; both flag orders now perform a
  true reset.
- **H-2** — `--hosts` switched from `nargs="+"` to `action="append"` (comma-splitting retained);
  `--hosts codex apply …` no longer swallows the subcommand.
- **H-3** — `check_version` rebuilt (`_version_key`/`_pad_version_keys`): no crash on `rc`/`dev`
  suffixes, semver prerelease ordering, unequal-length padding (`1.2` == `1.2.0`), `+local` build
  metadata ignored; `main_init` except clause widened to `ValueError`.
- **H-4** — workers sentinel and prompt default now `schema_default("parallel.max_workers")` (=2)
  instead of the literal 4; confidence-gate thresholds also schema-derived.

**Wiring (M-1..M-8 + rec-13):**
- `build_config` gained `parallel`/`documents`/`design_tokens`/`sync`/`confidence_gate`/`tdd`
  branches; headless `--enable/--disable` now covers them, with `parallel` carrying the template
  stamp (ARCHITECTURE-096).
- Dead `product`/`analytics`/`context_monitor` blocks removed from all nine templates; schema-wins
  default precedence documented in `core.py` (M-2/M-3/rec-14).
- `--enable X --disable X` → exit 2 usage error (M-5).
- `--plan` runs the same `merge_with_existing` preview `apply` performs (M-6); `apply --dry-run`
  added and `requested_upgrade` honored (M-7); `host_options` completed with kimi/opencode and a
  derived settings path (M-8).
- Explicit host selections persist to `orchestration.host_cli`/`hooks.host` (rec-13).
- `--force` widened to redeploy goals, issue templates, design-token profiles, and learning-tests;
  exact scope documented in help/epilog (M-4/rec-18).

**UX (U-1..U-6):**
- `init/` adopts `cli/output.py` (`configure_output` + new `set_use_color`); `--color`/`--no-color`
  flags added; bracket-idiom vocabulary unified through the output helpers.
- New `init/summary.py` extractor feeds a shared summary across headless and TUI surfaces; a
  next-steps footer (`/ll:scan-codebase`, `ll-doctor`, `/ll:help`) added to every completion path.
- Dry-run now runs dependency validation and prints a closing statement; the raw JSON dump was removed.
- Wizard screen counter fixed (6 screens on a healthy install).
- `/ll:init` skill: GNU-only `grep -oP` replaced with POSIX-portable bash parameter expansion;
  `--dry-run` semantics and wizard routing clarified.

**Tests:** new `test_init_audit_fixes.py` (36 tests) covering every fix plus a schema-coverage guard
(rec-17); 14 dry-run marker assertions, 3 TUI worker-sentinel tests, and the Kimi adapter message
updated to the new behavior.

**Verification:**
- New audit suite: 36/36 pass.
- Init-focused suites (core, tui, install, introspect, audit, deploy-templates, e2e, skill-fixtures):
  456 pass.
- Full suite: **18,434 passed, 42 skipped, 1 failed** — the single failure is pre-existing and
  unrelated: `test_wiring_guides_and_meta.py` expects `README.md` to say "46 typed CLI tools" while
  it reads "47" (bumped by the kimi-code commit without a matching test update). Neither file is
  touched by this work; left for a separate decision.
- `ruff check` and `ruff format --check` clean on all changed files.
- Live smoke tests of all four init paths (dry-run, `--yes`, `--plan`, `apply`) pass.

**Behavioral note:** accepting the TUI's worker prompt now presents **2** (the schema default)
instead of 4.

## Status

Completed.
