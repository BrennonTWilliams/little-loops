---
id: ENH-3391
type: ENH
title: 'll-init audit and overhaul: idempotent re-init, unified detection, express-first
  wizard, host persistence, codegraph integration'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-05'
captured_at: '2026-09-05T02:14:57Z'
labels:
- ll-init
- onboarding
- ux
completed_at: '2026-09-05T02:14:58Z'
---

# ENH-3391: ll-init audit and overhaul: idempotent re-init, unified detection, express-first wizard, host persistence, codegraph integration

## Summary

Deep audit and overhaul of `ll-init`, the first command every new little-loops user runs. The audit (code read of `scripts/little_loops/init/*`, `codequery/`, `cli/doctor.py`, tests and docs, plus scratch-project runs of `--yes --dry-run`, `--plan`, re-init and non-TTY) found seven defect groups; all were fixed in six phases, each landing test-green.

## Current Behavior

Before this work:

- The interactive wizard never called `init/introspect.py`, so the default first-run path seeded every prompt from template literals while `--yes` used manifest introspection — the same project got different configs depending on TTY.
- `ll-init --yes` was not idempotent: `cli.py` pre-populated absent sections with `.get("enabled", True)`, so a second run switched `product`/`learning_tests` on, deployed goals, and added a permission.
- Host auto-detection duplicated `host_runner._PROBE_ORDER` (omitting gemini/omp), wrote adapters for every binary on PATH including the user-global `~/.kimi-code/config.toml` with no notice, and never persisted the selection to `orchestration.host_cli`.
- No code-graph integration at all: no detection of the `codegraph` binary or `.codegraph/` index, no `code_query` block, no `.codegraph/` gitignore entry, `ll-code` missing from the CLAUDE.md block, no `ll-doctor` check, and a next-steps footer that wrongly described `/ll:scan-codebase` as "index the codebase".
- ~20 sequential prompts across 6–7 screens with loop diagram mode, `--clear`, session digest and prompt optimization asked of every first-time user; no accept-defaults shortcut.
- Output/robustness: absolute paths in dry-run, silent "Validating dependencies…", silent network probes, non-TTY exit 1, undocumented exit 130, `KeyError` tracebacks from `schema_default`, `apply` not stamping `install_source`, `LL_STATE_DIR` honored on read but not write, drift warnings on `python -m pytest -q` vs `pytest`.
- Docs advertised a `--hosts a b` form that fails, the removed `--codex` flag, and the wrong prompt-optimization default.

## Expected Behavior

`ll-init` is clear, smart (auto-configures test/lint/format/type/build from what the repo declares), fully integrated (offers to install/index codegraph or prints the exact commands), idempotent, and pleasant on first run.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Implementation

- **Phase 1 — defects.** `init/core.py`: `_TOGGLEABLE_FEATURES`, `RECOMMENDED_FEATURES`, `existing_feature_choices`, `reinit_feature_choices` (sub-config sections preserved via merge), `recommended_feature_choices`. `introspect.base_tool_token` + token-aware `_warn_config_drift` (stdout for `--yes`, stderr for `--plan`). `_state_dir` honoring `LL_STATE_DIR`; `apply` stamps `install_source`; friendly `KeyError`; exit 130 in epilog; `writers.display_path/set_display_root` for relative dry-run paths; `_report_dependency_warnings` with "All dependencies found"; PyPI/plugin progress lines; platform-aware `_jq_install_hint`; `_plugin_version` reads the plugin manifest; `write_config` strips None leaves.
- **Phase 2 — one pipeline.** New `init/proposal.py` (`ProposedField`, `Proposal`, `build_proposal`, `to_plan_dict` with additive `fields`/`code_graph`, `_apply_disable_flags`) consumed by `_run_yes`, `_run_plan`, and the wizard. `introspect.py` gained a per-field precedence chain: declared > task-runner targets (Makefile/justfile/tox/nox) > tool config files (tsconfig, eslint/biome, prettier, vitest/jest) > ecosystem conventions (go.mod, Cargo.toml, pom.xml, Gradle, .sln) > template default; `build_cmd`; `packageManager`/`bun.lock`; accurate focus_dirs evidence. `_ask_command` inserts a detected command outside the curated menu and shows evidence as the prompt instruction.
- **Phase 3 — hosts.** `available_hosts` / `default_hosts` built from `_HOST_RUNNER_REGISTRY` (adds gemini/omp; `_ADAPTER_PENDING_HOSTS` never primary; existing `orchestration.host_cli` wins); selection always persisted; `--settings {local,shared,skip}`, `--no-settings`, `--no-claude-md`; Claude files gated on claude-code via `_write_claude_surfaces`; kimi user-global write announced headless / confirmed in the wizard; wizard host list from `_KNOWN_HOSTS` with `[detected]`/`[not on PATH]` and disabled pending hosts; `host_options.available/default/primary`.
- **Phase 4 — code graph.** New `init/codegraph.py` (`CodegraphStatus`, `detect_codegraph`, `manual_commands`, `resolve_code_graph_action`, `install_codegraph` (no sudo; EACCES hint), `index_codegraph` (`codegraph init .`, npx fallback), `run_code_graph_step`); `--code-graph {auto,install,index,commands,skip}` in `--yes`/`apply`/wizard; `build_config` `code_query_enabled`; `.codegraph/` in `_GITIGNORE_ENTRIES`, `text_utils.DEFAULT_UNTRACKED_BY_DESIGN` and the schema default; `ll-code` in `_LL_COMMANDS`; `cli/doctor.py` `_code_query_data/_print_code_query_section/_code_query_check` (informational); `next_steps()` tailored footer (first issue, corrected scan wording, codegraph commands, `git init`, `ll-adapt`, `ll-doctor`, `/ll:help`).
- **Phase 5 — express-first wizard.** `run_tui` rewritten over `WizardAnswers`, `_answers_from_proposal`, `_render_env_line`, `_render_install_status`, `_render_detection_panel` (rich-escaped evidence), Accept/Customize/Cancel fork, `_ask_project/_ask_scan/_ask_features/_ask_hosts/_ask_claude_surfaces/_ask_advanced` (gated), `_ask_code_graph`; non-TTY delegates to `_run_yes`.
- **Phase 6 — docs/skills.** `docs/reference/CLI.md` (flags, plan keys, express flow, exit codes, examples, doctor JSON key), `docs/guides/GETTING_STARTED.md` (what gets created, flags, new Code graph section), `README.md` (+ `scripts/README.md` mirror), `docs/reference/COMMANDS.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/GRAPH_DISCOVERY_GUIDE.md`, `skills/init/SKILL.md` (no `--codex`; passthrough flags; additive plan keys), `skills/configure` (new `code-query` area) with gemini/kimi-code/qwen mirrors re-adapted.

## Acceptance Criteria

- [x] `ll-init --yes` twice writes a byte-identical config; tuned sub-config survives; `--disable` sticks on re-init
- [x] Wizard prompts default to introspected values with evidence; Accept path writes the same config as `--yes`
- [x] Introspection covers task runners, Node tool config files, Go/Rust/Java/.NET conventions, `build_cmd`
- [x] Host selection persisted; gemini detected; pending hosts never primary; kimi user-global write announced/confirmed; Claude files gated on claude-code; `--settings`/`--no-claude-md`
- [x] `--code-graph` step (auto never installs), `code_query` written when indexed, `.codegraph/` ignored, `ll-code` in CLAUDE.md, `ll-doctor` Code Graph section, tailored next steps
- [x] Express-first wizard with advanced gate; non-TTY falls back to headless; exit 130 documented
- [x] Docs/skills updated; mirror gates, `ll-verify-docs`, `ll-check-links`, `ll-verify-cli-allowlist`, `ll-verify-skills` pass

## Verification

- `python -m pytest scripts/tests/ --ignore=scripts/tests/integration`: 23,071 passed, 43 skipped (two pre-existing xdist-flaky tests outside this work pass serially).
- Init suites incl. new `test_init_proposal.py`, `test_init_codegraph.py`, `TestHeadlessIdempotent`, `TestCodeGraphHeadless`, `TestHeadlessSettingsFlags`, `TestAcceptPath`, `TestAdvancedGate`, `TestCodeQueryCheck`: 836 passed; TUI harness rewritten to message-dispatch mocks.
- `ruff check`, `mypy` (387 files), `ll-verify-docs` 15/15, `ll-check-links` 0 unreachable, `ll-verify-cli-allowlist`, `ll-verify-skills`, `ll-adapt --host gemini|kimi-code|qwen --apply`.
- Manual smoke in scratch Python/TypeScript/Go/empty projects: `--yes --dry-run`, `--plan | jq .code_graph`, `--code-graph commands`, `--hosts codex`, `ll-doctor`.

## Resolution

Completed 2026-09-05. Follow-ups filed: FEAT-3388 (new project-type templates for Ruby/PHP/C++/Swift/Deno/monorepos) and ENH-3389 (run `ll-adapt` for adapter hosts at init). Not committed in-session; the working tree holds the change set for review.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-05 | Priority: P2
