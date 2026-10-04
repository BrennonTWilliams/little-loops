---
id: FEAT-3716
type: FEAT
title: 'Loop portability tiers: classify ecosystem dependencies in ll-loop validate,
  list and show'
priority: P3
status: open
decision_needed: false
reconcile_attempted: true
verify_verdict: NON_VALID
discovered_by: portability-review
discovered_date: '2026-10-03'
captured_at: '2026-10-03T22:42:15Z'
labels:
- loops
- validation
- portability
relates_to:
- FEAT-2248
- EPIC-3581
- FEAT-2354
- FEAT-3717
---

# FEAT-3716: Loop portability tiers: classify ecosystem dependencies in ll-loop validate, list and show

## Summary

Add a portability check to `ll-loop validate` that classifies every loop into a **portability tier**, based on what it needs at runtime beyond the `little-loops` wheel and a host CLI. Show the tier in `ll-loop list` / `ll-loop show`, and run it over the shipped catalog in CI. This turns the existing convention "a general-purpose loop must not couple its core to the Issue system; Issue integration is an optional adapter" (FEAT-2248 § Portability, EPIC-3581 § Out of scope, ENH-2862) into a check a machine can fail. Today the rule exists only in issue prose and project memory. No in-repo doc states it, and nothing checks it.

## Context

Captured 2026-10-03 from a portability review (ll-product hub session) of making FSM loops runnable standalone in a user's repo, with brainstorm as the pilot. Source-verified findings:

- The runtime already supports standalone runs. `ll-loop run <path>` works in a bare `git init` repo with no `ll-init` and no plugin (`fsm/loop_paths.py:46-48` explicit-path resolution; `.loops/` and `.ll/` created on demand at `cli/loop/run.py:390` and `session_store/schema.py:1722`). `import:` fragments fall back to the wheel's built-in library (`fsm/fragments.py:99-110`).
- `LL_PYTHON` is injected unconditionally into every shell-action env as `sys.executable` (`fsm/runners.py:333`, `runner_spec.py:335`). So `$${LL_PYTHON:-python3} -m little_loops.<mod>` always reaches the wheel's interpreter, and a bare `python3 -m little_loops.<mod>` reaches whatever `python3` is on PATH.
- **The coupling is invisible.** Census at `8baa8a471` (`grep -lE '/ll:|ll-issues|\.issues/'`): **39 of 97** top-level built-in loops reference `/ll:*` commands, the `ll-issues` CLI, or `.issues/` paths. Three `lib/` fragments (`cli.yaml`, `policy-router.yaml`, `prompt-fragments.yaml`) and three oracles (`oracle-capture-issue`, `resolve-decision`, `verify-confidence-scores`) do too. Nobody can tell which loops are portable without reading them.
- **The interpreter bug this rule guards against has already happened once (fixed in `21583aae3`).** Three shipped loops called package modules through a bare interpreter: `fleet-loop-improve.yaml` (9 shell sites, `little_loops.fleet_improve`), `autodev.yaml` `finalize_done` / `finalize_step_capped` (`autodev_summary`), and `oracles/integrate-node.yaml` `try-pop` / `mark-complete` (`rn_synth_queue`). Under `uvx`, `pipx`, or any venv where PATH `python3` is not the wheel's interpreter, they failed with `ModuleNotFoundError`. The author's setup hid the bug, because a `.pth` lets system `python3` import the checkout. `21583aae3` converted all 13 sites to `$${LL_PYTHON:-python3}` and proved the fix with an executor run from a bare repo with a broken PATH `python3`. The catalog now has zero bare calls, and this issue adds the warning that keeps it that way.

Strategy tie-in (hub): B1 is "give away the loops, sell the trust", and the catalog sits on the open side of the open-core line (hub ENH-039, decided 2026-09-05). Today that is only partly true, because ~40% of the catalog needs the plugin and issue system. The hub's on-the-stack analysis names `ll-loops` (catalog extraction) as a candidate repo split. A tier stored as loop metadata survives that split; a tier that only exists in `validate` output does not.

## Current Behavior

- `ll-loop validate` checks structure, evaluators, reachability and shell safety (`fsm/validation/`). It does not classify external dependencies. The nearest check is the `/ll:<skill>` regex (`fsm/validation/_base.py:192`), which is used only for `tools:` allowlist consistency (`evaluator_rules.py:259-350`).
- `ll-loop list` entries carry `name, path, builtin, description, category, labels, visibility` (`cli/loop/info.py:395-403`). They have no dependency or portability field.
- Bare `python3 -m little_loops.*` passes validation silently. The catalog is clean as of `21583aae3`, but nothing stops a new loop from reintroducing it.

## Expected Behavior

Each loop resolves to one tier. The tier is computed over the loop **after** fragment and `from:` resolution, so imported fragments and inherited states count, and it includes the tiers of its sub-loops (`loop:` references), taking the highest:

| Tier | Meaning | Detected by |
|---|---|---|
| `portable` | Needs only the wheel + a host CLI | none of the below |
| `requires-plugin` | Invokes plugin surface | `/ll:<name>` in prompt/action text |
| `requires-issues` | Needs an initialized issue system | `ll-issues` / other issue-system `ll-*` CLIs, `.issues/` paths, `scope:` containing `.issues/` |

- **Declared and verified.** An optional top-level `portability:` field (schema enum: the three tiers). When the field is present, `validate` errors if the detected tier is higher than the declared one, because a loop declared portable must stay portable. When it is absent, `validate` reports the detected tier at info level only, so existing loops do not break.
- **Optional-adapter states.** States reachable only from a declared adapter route (for example, brainstorm's `sink_issue` / `sink_decision` behind `route_sink` with default `sink: none`) do not raise the core tier. The loop reports `portable (adapters: requires-plugin)`. Declare these with a state-level `adapter: true` marker rather than guessing from reachability.
- **Interpreter rule.** A shell action that invokes `python`/`python3 -m little_loops.` without `LL_PYTHON` is a validation **warning** for every loop, whatever its tier, with a fix hint pointing at `$${LL_PYTHON:-python3}`.
- `ll-loop list` shows the tier (a column, plus `--json` field, plus a `--portability <tier>` filter). `ll-loop show` prints the tier and the evidence lines that set it.
- A CI corpus check over `scripts/little_loops/loops/` prints the tier distribution and fails if any loop declared `portable` regresses.

## Motivation

- Makes the decoupling rule enforceable. Today it depends on reviewers remembering a memory entry.
- Gives users a visible answer to "which loops can I run in my repo without adopting the issue system?"
- It is a prerequisite for `ll-loop export` (FEAT-3717), which has to know what it can bundle cleanly.
- It keeps out a class of interpreter bug that has already shipped once (three loops, fixed in `21583aae3`) and that the author's own environment hides.

## Proposed Solution

New rule module `fsm/validation/portability_rules.py` with `classify_portability(fsm, loops_dir) -> PortabilityReport(tier, adapter_tier, evidence: list[(state, field, match)])`. It reuses `_SKILL_INVOKE_RE` and walks resolved state text (`action`, `prompt`, evaluator prompts, `scope`). Sub-loop tiers are resolved through `resolve_loop_path` with a visited set to guard against cycles. Wire it into `load_and_validate`'s rule list, `cmd_validate` output, and the `info.py` catalog entry. Add `portability` (top-level enum) and `adapter` (state-level bool) to `fsm-loop-schema.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

**Option A**: Add `INFO = "info"` to `ValidationSeverity` (`fsm/validation/_base.py`) and emit the detected tier as an `INFO` `ValidationError`, so "info level only" is literal and flows through `violations`.

**Option B**: Keep `ValidationSeverity` at `ERROR`/`WARNING`; treat the detected tier as a separate report channel — a `Portability:` line in `cmd_validate` output and a top-level `portability` object in `--json` (already required by the AC), with only the declared-vs-detected mismatch and the bare-interpreter rule emitted as `ValidationError`s.

> **Selected:** Option B — separate report channel; avoids widening a two-value severity enum that every consumer and the documented JSON contract assume (score 10/12 vs 5/12).

**Recommended**: Option B — the AC already requires a separate `portability` key in `--json`; `INFO` would be a new severity every existing consumer (`cmd_validate`, `cli/doctor.py`, `cli/logs.py`, `policy_revision.py`, `scaffold_verify.py`, `scaffold_eval.py`) and the documented `"error"|"warning"` JSON contract (`docs/reference/CLI.md`) would need to learn, to carry a datum that is not a violation.

### Decision Rationale

**Selected:** Option B — keep `ValidationSeverity` at `ERROR`/`WARNING`; report the tier on a separate channel.

**Reasoning:** Option A looks cheap but `load_and_validate` (`structural_rules.py`) buckets only ERROR and WARNING, so an `INFO` item would be silently dropped unless a third bucket is added, and with `raise_on_error=True` any non-error item is logged via `logger.warning` (printing `[INFO]` as a warning on every `ll-loop run`). `scaffold_verify`/`scaffold_eval` would list INFO items in their `errors` strings, `logs.py` would print `[INFO]` lines in fleet-review markdown, and always-emitting a tier would break the `violations == []` clean-loop contract (`test_ll_loop_commands.py:225`, `CLI.md:1173`). No precedent exists for non-violation data in `ValidationError`; `ll-doctor` keeps informational data on a separate axis. Option B is additive: `docs/reference/json-output-contracts.md` states new optional keys are non-breaking, and sibling-key-plus-`violations` output has precedent (`cli/docs.py` skill budget, `doctor.py`).

**Implementation notes for B:**
- `load_and_validate` returns a 2-tuple at 9+ call sites, so `cmd_validate` calls `classify_portability(fsm, loops_dir)` itself after loading (classifier runs twice per validate: once in the rule for mismatch/bare-interpreter errors, once for the report; accept the repeat sub-loop walk or pass a cached report).
- `portability` is absent from the two early-error `--json` shapes in `cmd_validate`; document that in `CLI.md:1173` (which currently pins the key set and says there is no extra key) and add a `validate --json` shape test.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — `INFO` severity | 1 | 1 | 2 | 1 | 5/12 |
| B — separate channel | 2 | 2 | 3 | 3 | 10/12 |

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation/portability_rules.py` (new): `classify_portability()`, `PortabilityReport`
- `scripts/little_loops/fsm/validation/structural_rules.py`: register the rule in `load_and_validate` (runs after `resolve_fragments`)
- `scripts/little_loops/fsm/fsm-loop-schema.json`: top-level `portability` enum, state-level `adapter` bool, `portability_ignore`
- `scripts/little_loops/cli/loop/config_cmds.py`: `cmd_validate` output and `--json`
- `scripts/little_loops/cli/loop/info.py`: catalog entry field (~:395-403), `list` column and `--portability` filter, `show` evidence
- `scripts/little_loops/cli/loop/__init__.py`: `--portability` flag on `list`
- `scripts/little_loops/loops/brainstorm.yaml`: `adapter: true` on `sink_issue` / `sink_decision` (coordinate with FEAT-3582)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.portability` field + `from_dict` / `to_dict` (omit when `None`); `StateConfig.adapter` / `portability_ignore` + `from_dict` / `to_dict`. Not named in the original list, though Program Design requires it [Agent 1 finding]
- `scripts/little_loops/fsm/validation/_base.py` — add `portability` to `KNOWN_TOP_LEVEL_KEYS` (else an `Unknown top-level keys` WARNING fires on every declared loop); add a `VALID_PORTABILITY` frozenset next to `VALID_VISIBILITY` (:78) [Agent 1 finding]
- `scripts/little_loops/fsm/validation/__init__.py` — re-export the new rule function(s) and `PortabilityReport`/`classify_portability`, add to `__all__`, and add `portability_rules` to the "Package layout" module-docstring list (ENH-2774 convention) [Agent 1 + Agent 2 finding]
- `scripts/little_loops/fsm/validation/meta_rules.py` — `_GATE_COMPLETENESS_TABLES` (:463) registers `VALID_VISIBILITY`; decide whether `VALID_PORTABILITY` joins it (gate-completeness exhaustiveness check) [Agent 3 finding]
- `scripts/little_loops/mcp_server/tools.py` — `types.Tool(name="loop_list")` `input_schema` (:943, `additionalProperties: False`) needs a `portability` property and `_tool_loop_list` must forward it to `enumerate_loop_catalog`; `to_json_item()` additions reach this tool automatically [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/loop/info.py` — three more edit points beyond "catalog entry field": both return dicts of `_load_loop_meta` (normal + `except Exception` fallback), all three `LoopCatalogEntry(**meta)` sites in `enumerate_loop_catalog`, and the hand-built `all_loops` dict list in `cmd_list` that feeds `_badge_for`, `_emit_grid_section`, `_emit_long_section` / `_emit_row` [Agent 2 finding]
- `scripts/little_loops/cli/logs.py:_validate_builtin_loop` (:2323) — mirrors `cmd_validate`'s `--json` branch; decide whether it carries the `portability` key (fleet-review markdown prints every violation as `- [SEVERITY] path: message`, so new WARNINGs appear there) [Agent 1 + Agent 2 finding]
- `skills/review-loop/reference.md` — "First-Pass Checks (from `ll-loop validate`)" table (:17-55) is a hand-maintained mirror of validator rules; add the declared-vs-detected and bare-interpreter rows [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — "Finding the right loop" callout (:7-12) describes which `ll-loop list` flags surface which loops; add `--portability` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `fsm/validation/_base.py:192` `_SKILL_INVOKE_RE` (reuse, don't fork)
- `fsm/fragments.py` `resolve_fragments` / `resolve_inheritance`; `fsm/loop_paths.py` `resolve_loop_path` (sub-loop tier walk)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` (sub-loop dispatch, `load_and_validate(loop_path, raise_on_error=False)` at :1163) — imports `_SKILL_INVOKE_RE` from `fsm.validation`; the new rule runs on every sub-loop state execution via this call, and a declared-vs-detected ERROR in the child is swallowed (`raise_on_error=False`) here but raises for `run` [Agent 1 + Agent 2 finding]
- `scripts/little_loops/fsm/loop_paths.py:load_loop` / `load_loop_with_spec` (:104, :128) — wrap `load_and_validate`; a new ERROR blocks `run`, `resume`, `test`, `simulate`, `edit-routes`, `cmd_show` for the offending loop. These are also the fragment-resolving loaders `cmd_list` would use [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/doctor.py:_loop_validity_data` (:987, call at :1022) — aggregates `load_and_validate` over every runnable loop and counts ERRORs; a new portability ERROR surfaces in `ll-doctor` [Agent 1 + Agent 2 finding]
- `scripts/little_loops/fleet_improve.py:validate_loop` (:396), `warning_count` (:408), `gate` (:657) — parse `ll-loop validate --json` `violations`, compare warning counts to `gate-baseline.json`, and fail on any `severity == "error"`; a new WARNING class on shipped loops shifts baselines. A top-level `portability` key is ignored [Agent 2 finding]
- `scripts/little_loops/loops/workflow-generator.yaml` (`validate_artifact`, shrink-pass probes reading `payload["violations"]`, `promote` reading `list --json` `name`) and `docs/reference/loops.md:209-213` — consume `validate`/`list` output; unknown JSON keys are safe [Agent 2 finding]
- `scripts/little_loops/loops/loop-router.yaml` (`discover_loops`) and `scripts/little_loops/loops/lib/composer.yaml` (`discover_loops` fragment) — run `ll-loop list --json --visibility public` and read `name/description/category/built_in` via `.get`; additive `portability` key is safe, but note they are the natural consumers if routers should prefer `portable` loops [Agent 2 finding]
- `scripts/little_loops/cli/loop/_scaffold_core.py:dump_fsm_yaml` (:60) — serializes `fsm.to_dict()` back to YAML for `scaffold-eval` / `scaffold-verify`; a field `to_dict` fails to emit is dropped from scaffolded YAML, so `portability` / `adapter` / `portability_ignore` round-trip matters here [Agent 2 finding]
- `scripts/little_loops/cli/loop/scaffold_verify.py:340`, `scaffold_eval.py:278` — call `validate_fsm(fsm)` in-process with no path or loops dir, so a rule registered only in `load_and_validate` (needing `loops_dir`) is invisible to them. Do **not** add a `loops_dir` parameter to `validate_fsm` (see spike test under Tests) [Agent 2 finding]
- `scripts/little_loops/cli/artifact/policy_revision.py` (:95) — validates a tmp-dir path, so sub-loop resolution in the tier walk is relative to the tmp dir (built-in fallback via `resolve_loop_path` still applies) [Agent 2 finding]
- `scripts/little_loops/fsm/topology.py:load_fsm` (:119-128) — calls `FSMLoop.from_dict`; `topology_dict` hand-picks state keys, so unaffected [Agent 1 finding]
- Name collision: `adapter` is already used for HITL communication adapters (`fsm/communication_adapter.py`, `fsm/adapters/*`, `executor.py:resolve_communication_adapter`); no existing loop-YAML state key `adapter:` — keep the state-level key meaning distinct in docs [Agent 2 finding]

### Similar Patterns
- `fsm/validation/evaluator_rules.py:259-350`: the existing `/ll:<skill>` vs `tools:` allowlist check
- `fsm/validation/reachability.py:70`: sub-loop `loop:` reference validation (walk pattern)

### Tests
- `scripts/tests/test_fsm_validation*.py` / new `test_portability_rules.py`: tier fixtures (direct, via fragment, via `from:`, via sub-loop, adapter-only, dynamic sub-loop, comment false-positive)
- `scripts/tests/test_builtin_loops.py`: corpus check (declared tiers validate; distribution recorded)

_Wiring pass added by `/ll:wire-issue`:_

Existing tests to update / extend:
- `scripts/tests/test_fsm_schema.py` — `TestStateConfig` / `TestFSMLoop` round-trip + omitted-when-default for the three new fields (model: `TestSingleton`, `TestScopesStateConfig`, `TestGateCompletenessOk`); schema-presence test modelled on `TestTamperGuard.test_schema_json_declares_state_and_loop_level_tamper_guard` (`schema["definitions"]["stateConfig"]["properties"]` + `schema["properties"]`); `"portability" in KNOWN_TOP_LEVEL_KEYS` (model: `test_feat3033_idle_timeout.py`) [Agent 3 finding]
- `scripts/tests/test_fsm_validation_structural.py` — add `TestPortabilityValidation` modelled on `TestVisibilityValidation` (`_BASE` YAML + `_write_yaml`; parametrized valid values, invalid value → diagnostic at `path == "portability"`, no `Unknown top-level keys` warning) [Agent 3 finding]
- `scripts/tests/test_fsm_validation_shell_safety.py` — bare-interpreter rule unit tests in the `_simple_fsm(action)` + `make_state(action=..., action_type="shell")` shape; assert `path == "states.<name>.action"`, severity WARNING, `$${LL_PYTHON:-python3}` form passes, description-prose text not flagged, and a `test_*_wired_into_validate_fsm`-style test (model: `TestBashDefaultInterpolation.test_mr7_wired_into_validate_fsm`) [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdValidate`: `Portability:` line and `--json` `portability` key (model: `test_validate_json_output_valid_loop`); add the early-error `--json` shape test the Decision Rationale requires (the two early-error shapes carry no `portability` key; `test_validate_json_every_exit_path_produces_parseable_json`). `TestCmdList` / `TestLoopListVisibilityFilter` sibling: `--portability` filter test (bare `argparse.Namespace`, patch `little_loops.cli.loop.info.get_builtin_loops_dir`). `TestCmdShow` / `TestCmdShowJson`: evidence lines (human) — `--json` is `fsm.to_dict()` so evidence needs its own assertion [Agent 3 finding]
- `scripts/tests/test_cli_loop_dispatch.py:TestMainLoopListFlagForwarding` — add `test_portability_forwarded` next to `test_list_category_forwarded` (:~898-924) [Agent 2 + Agent 3 finding]
- `scripts/tests/test_json_output_contracts.py:TestLoopListJsonContract` — add the tier key to `REQUIRED_FIELDS` / `test_full_shape_with_builtin_loop`; add an allowed-values check in the style of `test_visibility_is_known_tier` [Agent 3 finding]
- `scripts/tests/test_feat_3352_mcp_loop_list.py` — `test_loop_list_json_contract_parity_with_cmd_list` subset fields, plus an MCP-side `portability` argument test using `_write_loop(loops_dir, rel_name, **fields)` [Agent 3 finding]
- `scripts/tests/test_brainstorm.py:TestBrainstormYaml` — assert `sink_issue` / `sink_decision` carry `adapter: true` and core states do not; `TestBrainstormDryRun.test_all_states_reachable` already shells out to `ll-loop validate brainstorm` (exit 0, no "unreachable") and `test_no_ratcheted_category_warnings` guards new warning categories; `test_no_issue_system_writes_in_core_states` (:116-140) is the existing core/adapter boundary test [Agent 2 + Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:TestValidatorWarningBudget` — add a `CATEGORY_PATTERNS` entry for the bare-interpreter WARNING so it is ratcheted (otherwise a message matching no pattern is ignored); `test_brainstorm.py:TestBrainstormDryRun` keeps a local copy of 7 of the patterns — mirror it there [Agent 2 + Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:TestMr11MarkerSet` — model for an enumeration test over `adapter:` / `portability_ignore:` markers (new and stale entries both fail) [Agent 3 finding]
- `scripts/tests/test_fsm_validation_meta_rules.py` — `_GATE_COMPLETENESS_TABLES` tests, only if `VALID_PORTABILITY` is registered there [Agent 3 finding]

Tests that may break:
- `scripts/tests/test_ll_loop_commands.py:TestCmdValidate.test_validate_json_output_valid_loop` — `violations == []` on a minimal terminal-only loop; any finding emitted for undeclared plain loops breaks it (reinforces Option B) [Agent 2 + Agent 3 finding]
- `scripts/tests/test_fsm_schema.py:TestLoadAndValidate.test_load_valid_yaml` (`warnings == []`) and the `test_evaluate_unknown_key_sweep_builtin_loops_clean` corpus sweep — break if the new rule emits warnings or errors for a valid/built-in loop [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py:TestLoopListFormatting` (`test_row_fits_terminal_with_wide_labels`, `test_row_width_invariant_across_label_counts`, `test_long_description_row_fills_to_terminal_width`, `test_column_alignment_names_padded`, `test_column_alignment_across_subgroups_and_flat_tail`), `TestCmdListENH2539Polished` (`test_default_terminal_width_120`, `test_rollup_badge_in_header`), `TestCmdListENH2572ScanningFirst` (`test_kind_column_removed_badge_for_exceptions`, `test_builtin_tag_absent_project_marker_present`) — a tier column/badge on every row changes widths; a badge containing the word "built-in" collides with `"built-in" not in out` assertions [Agent 2 + Agent 3 finding]
- `scripts/tests/test_cli_loop_layout.py` (`_category_rollup` ~:781-819, `_detect_subgroups` ~:858-881) and `test_ll_loop_commands.py` (`_detect_subgroups` ~:3456, `_smart_truncate` ~:3392) — pass minimal dicts to the `cmd_list` render helpers; a required new key in those dicts breaks them, so read it with `.get()` [Agent 2 finding]
- `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py:TestNoRealPathAvailableAtCallSites` — asserts `validate_fsm`'s parameter set is exactly `{fsm, orchestration_request_path, host_cli, model_hints}` and that no `FSMLoop` field name has a `path`/`file`/`source` token; do not add `loops_dir` to `validate_fsm`, and avoid such names for the new field [Agent 2 + Agent 3 finding]
- `scripts/tests/test_portability_gate.py` — line-scans `scripts/little_loops/loops/**/*.yaml` for BSD/GNU shell hazards (`ll-portability-ok:`); the brainstorm `adapter: true` edit and any new loop-YAML text fall under that scan [Agent 2 finding]

New tests to write:
- `scripts/tests/test_fsm_validation_portability.py` (new) — tier fixtures per the existing list; model files: `test_fsm_validation_shell_safety.py` (rule-function-direct), `test_fsm_inheritance.py:test_circular_chain_raises` (cycle-guard precedent — no cross-file `loop:` walker with a visited set exists anywhere in the repo, searched by capability) [Agent 3 finding]
- Fragment-resolving catalog load: no catalog test exercises `import:` fragments (`test_from_inheritance_resolves_category` covers `from:` only), so add one for the `list` tier path [Agent 3 finding]
- Bare-interpreter regression fixture: none exists in `scripts/tests/` (pre-`21583aae3` form survives only in stale `.claude/worktrees/agent-*/` copies, not tracked — inline the literal action text in the fixture rather than reading those). `LL_PYTHON` is scrubbed per-test by `conftest.py` (`test_bug3689_gate_env.py`), so tests that execute actions must set it explicitly [Agent 3 finding]
- Corpus distribution test: no existing test asserts a metadata-field distribution across the built-in corpus; follow the `TestBuiltinLoopFiles` / `TestMr11MarkerSet` shape (collect offenders, assert on list, guard against vacuous pass) [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md`: decoupling rule and tiers (first in-repo statement of the rule)
- `docs/guides/LOOPS_REFERENCE.md`: `portability`, `adapter`, `portability_ignore` fields

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-loop list` flag table (:1181-1194, incl. the `--json` row enumerating entry keys) gains `--portability` + the tier key; `ll-loop show` flag table (:1341-1348) / evidence; `ll-loop validate` JSON contract (~:1173) and one rule bullet per new rule (bare-interpreter WARNING, declared-vs-detected ERROR, each ending with suppression + issue ID); MCP tool list (~:5983-5985) [Agent 1 + Agent 2 finding]
- `docs/reference/json-output-contracts.md` — `## ll-loop list --json` example + field table (:22-46) gains the tier key; note `portability` is absent from validate's early-error JSON shapes [Agent 2 finding]
- `docs/reference/API.md` — `FSMLoop` dataclass listing (:5785-5834), `StateConfig` listing (:5934-5978), "Checks performed" bullets under `validate_fsm` (:6707-6731); `ValidationError.severity` comment (:6684) stays "ERROR or WARNING" under Option B [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `fsm/validation/` module tree (:253-259) has no row for `portability_rules.py` [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — "Optional Loop-Level Settings" YAML field reference (:362-388) gains `portability`; state-level fields `adapter`, `portability_ignore` [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — design-rules table (:92-113, holds non-MR rules too) and prose at :442 / :455 enumerating rules `validate` enforces as ERROR vs WARNING [Agent 2 finding]
- `docs/guides/MCP_SERVER_GUIDE.md` (:~352, :380-381) — `loop_list` "same shape as `--json`" claim and filter arguments [Agent 1 + Agent 2 finding]
- `skills/create-loop/reference.md` — "Advanced State Configuration" per-field subsections (:425-1122) gain `adapter` / `portability_ignore`; `skills/review-loop/SKILL.md` Step 2a parses `[ERROR]` / `[WARNING]` / `⚠` / `✓` from `validate` stdout, so the `Portability:` line must not begin with one of those markers [Agent 2 finding]
- `README.md` / `scripts/README.md` — mention `ll-loop list`/`validate` only as examples; if either is edited, mirror with `command cp -f README.md scripts/README.md`. Any `skills/` edit also requires `ll-adapt --host <gemini|kimi-code|qwen> --apply` if host mirrors exist for the touched skill (none found for loop skills in this checkout) [Agent 1 + Agent 2 finding]
- Doc-string presence gates: add rows to `scripts/tests/test_wiring_reference_docs.py:DOC_STRINGS_PRESENT` (and `test_wiring_guides_and_meta.py` / `test_wiring_skills_and_commands.py`) for the new rule names; `test_docs_audience_gate.py` forbids `scripts/tests/` paths in `docs/guides/`, `docs/reference/`, `skills/` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Resolved-state text lives in one field.** After `load_and_validate()` (`fsm/validation/structural_rules.py`) the `FSMLoop` has no separate `prompt` field: shell, slash-command and prompt text all sit in `StateConfig.action` (`fsm/schema.py`), discriminated by `action_type`. The other text carriers are `EvaluateConfig.prompt` / `EvaluateConfig.scope` (via `StateConfig.evaluate`) and the top-level `FSMLoop.scope: list[str]`. `from:` and `flow:` are stripped before parsing; `import:` fragments are expanded into the states (`StateConfig.fragment_name` survives). So a classifier over the parsed `FSMLoop` already sees inherited and imported text, and `ll-*` CLI names from `loops/lib/cli.yaml` / `lib/policy-router.yaml` reach a loop only through that expansion.
- **No `INFO` severity exists.** `ValidationSeverity` (`fsm/validation/_base.py`) has only `ERROR` and `WARNING`; `docs/reference/CLI.md` (`ll-loop validate`) documents the JSON `severity` as `"error"|"warning"`; consumers test `== ERROR` (`cli/loop/config_cmds.py:cmd_validate`, `cli/doctor.py`, `cli/logs.py:_validate_builtin_loop`, `cli/artifact/policy_revision.py`) and `cli/loop/scaffold_verify.py` / `scaffold_eval.py` format `severity.value`. The issue's "report the detected tier at info level" therefore has no existing channel — see the Option A/B decision under Proposed Solution.
- **`ll-loop validate` human output prints no warnings itself.** `cmd_validate` calls `load_and_validate(..., raise_on_error=not as_json)`; in human mode warnings are emitted only by `logger.warning(str(w))` inside `load_and_validate`, and `cmd_validate` then prints `States` / `Initial` / `Max steps` after `logger.success("<name> is valid")`. A `Portability:` line has to be added in `cmd_validate` itself. `--json` emits `{loop, valid, violations:[{severity,path,message}]}` and has no other top-level keys today.
- **Rules needing a loops dir get `path.parent`, not the catalog root.** The four filesystem-aware rules (`_validate_with_bindings` and `_validate_fragment_bindings` in `structural_rules.py`; `_validate_loop_references` and `_validate_artifact_output_subloop_reachability` in `fsm/validation/reachability.py`) are registered in `load_and_validate` after `FSMLoop.from_dict` and receive `path.parent`. `resolve_loop_path(name, loops_dir)` (`fsm/loop_paths.py`) falls through project dir → built-in dir → `runs/*/workflow.yaml`, so a sub-loop tier walk resolves built-in children regardless of the dir passed.
- **Sub-loop walking has no cross-file visited-set precedent.** `_validate_with_bindings` recurses one hop at a time by calling `load_and_validate(loop_path, raise_on_error=False)` on the child, with no visited set and a blanket `except Exception: continue`; `_validate_loop_references` skips any `state.loop` containing `"${"` and never loads the child; `resolve_inheritance(raw, loop_dir, _seen: tuple[str, ...])` is the only cycle guard over loop *names* (raises `ValueError("Circular `from:` chain: …")`). Calling `load_and_validate` from inside a rule that itself runs under `load_and_validate` re-runs every rule per child, and with no visited set can loop on cyclic `loop:` references.
- **Dynamic sub-loop names are real in the shipped catalog.** `loop: "${...}"` appears in `goal-cluster`, `loop-composer`, `loop-composer-adaptive`, `proof-first-task`, `spike-gate`, `loop-router`, `outer-loop-eval` and `rn-build` (`scripts/little_loops/loops/`). All of them land on the `unknown (dynamic sub-loop)` path, so what that outcome does to a *declared* tier is a rule the corpus test depends on — see Program Design → Decision Rules.
- **`ll-loop list` does not parse loops through the validator.** `_load_loop_meta` (`cli/loop/info.py`) reads raw YAML plus `resolve_inheritance` only — no `resolve_fragments`, no `FSMLoop`. A tier computed "after fragment resolution" for every catalog entry needs the heavier load per loop (≈100 built-ins + project loops), and `from:`-only stubs must still count (`is_runnable_loop`, `structural_rules.py`). `enumerate_loop_catalog()` builds `LoopCatalogEntry` objects whose `to_json_item()` is the single wire shape shared with the MCP `loop_list` tool (`mcp_server/tools.py:_tool_loop_list`, documented as byte-identical to `ll-loop list --json`), and `cmd_list` then rebuilds a second `all_loops` dict list for human rendering (`info.py`, ~:399-410) — a new field must reach both. `--portability` has to slot into the documented category → label → visibility filter order (`hidden_counts` depends on it).
- **A new top-level field touches five places, a new state field four.** Top-level (precedent `visibility`, `singleton`): `KNOWN_TOP_LEVEL_KEYS` (`fsm/validation/_base.py`; otherwise an `Unknown top-level keys` WARNING fires), the `FSMLoop` dataclass field, `FSMLoop.from_dict`, `FSMLoop.to_dict` (conditionally emitted when non-default), `fsm-loop-schema.json`. State-level (precedent `terminal`, `failure`, `context_passthrough`): `StateConfig` field, `from_dict`, `to_dict`, `definitions.stateConfig.properties`. `StateConfig.from_dict` silently drops unknown keys and there is no state-level unknown-key validator, so a typo'd `adapter:` is invisible until a test asserts it. The schema's `additionalProperties: false` applies to both levels but nothing enforces the schema at load time (only `scripts/tests/test_fsm_schema.py` reads it).
- **MCP / contract surfaces ride along.** `scripts/tests/test_json_output_contracts.py:TestLoopListJsonContract` (`REQUIRED_FIELDS`) and `docs/reference/json-output-contracts.md` pin the `ll-loop list --json` shape; `scripts/tests/test_feat_3352_mcp_loop_list.py` covers the MCP tool, whose `input_schema` has its own `label` / `visibility` properties — adding a CLI filter and adding it to MCP are separate edits. `ll-loop show --json` is `fsm.to_dict()` (`info.py:cmd_show`), so a `portability` field serialized from `FSMLoop.to_dict` surfaces there for free, but evidence lines do not.
- **Name collision.** "portability" already names (a) BSD/GNU/bash-3.2 shell portability (`scripts/tests/test_portability_gate.py`, suppression token `ll-portability-ok:`, ENH-3539) and (b) host-portable `model_hint` (`scripts/tests/test_model_hints.py:TestPortabilityProof`, `adapters/core.py`). The new `portability:` loop field, `portability_ignore`, and any grep-based docs/tests keyed on the word are a third sense; avoid reusing the `ll-portability-ok:` token.
- **Sequencing (frontmatter-visible).** `brainstorm.yaml` currently has `route_sink` → `sink_issue` / `sink_decision` (lines ~351-392), no `adapter:` key; FEAT-3582 and FEAT-3667 are both `open` and rewrite that loop (EPIC-3581), so the AC "brainstorm's `sink_issue` / `sink_decision` marked `adapter: true`" must be satisfied against whichever version of the loop is current when this lands.

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

Conventions in force (rule first, files as evidence):
- Validation rules are plain `_validate_*` functions returning `list[ValidationError]`, re-exported by name from `fsm/validation/__init__.py` (`__all__`, "for test access"); messages are prefixed `[state: <name>]`, end with an issue/rule tag, and name the suppression mechanism — evidence: `shell_safety._validate_bash_default_interpolation`, `_validate_overescaped_shell`.
- Shell-action rules gate on `action_type in ("shell", None)` and `not action.lstrip().startswith("/")` before matching — evidence: `shell_safety._validate_overescaped_shell`, MR-11. This matters here because two shipped descriptions still contain a bare `python3 -m little_loops` (`loops/fleet-loop-improve.yaml` ~:25, `loops/oracles/integrate-node.yaml` ~:16); a rule that scans anything but shell-action text would break the "zero warnings across shipped loops" AC.
- Rule severity is chosen per rule; rules that could hard-fail consumers' pre-existing loops at upgrade are WARNING — evidence: `_validate_unsafe_context_interpolation` docstring. Contested: MR-7/MR-9 are ERROR.
- Bare-bool `<x>_ok` suppression is loop-wide and its reason lives in an adjacent YAML comment (`loops/general-task.yaml:10`); the only *enforced*-reason hatch is the `# ll-lint: mr11-ok(<key>) <reason with issue ID>` comment marker (`shell_safety._parse_mr11_marker`). No state-level `*_ok` bool exists. The issue's state-level `portability_ignore:` with a required reason is a third shape — a decision the implementer makes knowingly (and it needs its own validation that the reason is non-empty).
- Corpus tests loop over `BUILTIN_LOOPS_DIR.rglob("*.yaml")` filtered by `is_runnable_loop` inside one test body, collect offenders, assert on the list, and guard against vacuous passes; allow-lists are bidirectional (new *and* stale entries fail) — evidence: `scripts/tests/test_builtin_loops.py` (`TestBuiltinLoopFiles`, `TestValidatorWarningBudget`, `TestMr11MarkerSet`). No existing test asserts a metadata-field *distribution* across the corpus.
- Field tests per addition: round-trip + omitted-when-default (`test_fsm_schema.py:TestGateCompletenessOk`), schema-presence membership (`test_fsm_schema.py`, `schema["definitions"]["stateConfig"]["properties"]`), recognized-as-top-level-key via `tmp_path` + `load_and_validate` (`test_fsm_validation_shell_safety.py`). Contested: `KNOWN_TOP_LEVEL_KEYS` is not in lockstep with `FSMLoop` fields or the schema (e.g. `visibility` is absent from the schema) and nothing tests the lockstep, so "present in the schema" is not a reliable signal that the keys set is complete.
- `ll-loop list` filters: argparse in `cli/loop/__init__.py` (`--category`, repeatable `--label`, `--visibility` with `choices=`), read with `getattr(args, "x", default)` in `cmd_list` so bare-`Namespace` tests keep working; tested in `test_ll_loop_commands.py` (`TestLoopListCategoryFilter`, `TestLoopListVisibilityFilter`) by seeding `tmp_path/.loops` and patching `little_loops.cli.loop.info.get_builtin_loops_dir`. Human rows are f-string concatenations with width-invariant tests (`test_row_fits_terminal_with_wide_labels` etc.) — there is no column framework.
- Doc-surface gates are string-presence (`test_wiring_reference_docs.py` / `test_wiring_guides_and_meta.py`, `DOC_STRINGS_PRESENT`) and the `ll-loop validate` rule bullets in `docs/reference/CLI.md` (one per rule, ending with suppression flag + issue ID); `docs/guides/LOOPS_GUIDE.md` § "Loop Discovery: category, labels, and visibility" is where list-metadata is documented. Existing doc/code disagreement worth not propagating: `LOOPS_GUIDE.md` says the default `list` output is a name grid, `info.py` / `--grid` help say the detailed table is default.
- Audience gate: `docs/guides/` and `docs/reference/` text must be written for the consuming-project user (no `scripts/tests/` paths) — `scripts/tests/test_docs_audience_gate.py`.

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Registration seam (verified 2026-10-04).** `load_and_validate` (`fsm/validation/structural_rules.py`, ~:2110) runs `resolve_inheritance` → `resolve_flow` → required-field/unknown-key checks → `resolve_fragments` → `FSMLoop.from_dict` → `_validate_evaluate_unknown_keys` → `validate_fsm`, and only then the block of `(fsm, path.parent)` rules (`_validate_with_bindings`, `_validate_loop_references`, `_validate_fragment_bindings`, `_validate_artifact_output_subloop_reachability`, ~:2212-2215). Results are split into errors and warnings there; `raise_on_error=False` returns them concatenated, `True` raises `ValueError` on any error and `logger.warning`s the rest. `validate_fsm` itself has no path/loops-dir and stays that way (spike test pins its parameter set).
- **What survives into the parsed `FSMLoop`.** `StateConfig.action` / `action_type` / `evaluate` / `loop` / `with_` / `fragment_name` / `agent` / `tools` / `params`, `EvaluateConfig.prompt` / `scope`, `FSMLoop.scope` / `imports` / `visibility`. `FSMLoop` has **no** `from`, `fragments` or `state_defs` attribute — only `imports` (the lib paths) survives — so per-fragment provenance is recoverable only through `StateConfig.fragment_name`. Fragment `description:` text is stripped during the merge, which keeps description prose out of the scan without extra work.
- **Un-interpolated text.** `load_and_validate` never interpolates, so the classifier sees action text exactly as authored: the correct interpreter form appears as the escaped `$${LL_PYTHON:-python3}` and a dynamic sub-loop name appears as a literal `${...}` string. A bare-interpreter rule must match against that raw escaped form.
- **Shell-vs-prompt discrimination already exists.** `_is_shell_state` and `_is_prompt_action` (`structural_rules.py`, ~:431 / ~:447) encode "`action_type == "shell"`, or `None` and not starting with `/`". Other rules gate the same way (`shell_safety.py`, `meta_rules.py`). Rule: shell-only checks (command-position `ll-<name>`, bare interpreter) reuse that discrimination rather than re-deriving it.
- **A plugin-surface carrier the Decision Rules' scan list misses.** `StateConfig.agent` is set to a bare agent name in two shipped loops — `agent: loop-specialist` in `loops/fleet-loop-improve.yaml` (:143, :221) and `loops/loop-specialist-eval.yaml` (:37) — an `agents/` plugin definition, with no `/ll:` token anywhere. `_SKILL_INVOKE_RE` cannot see it, so these loops would classify `portable` on action text alone. Whether `agent:` counts as `requires-plugin` is an unstated decision the implementer must make knowingly (no shipped loop sets `tools:`, so that carrier is moot for the corpus today).
- **`ll-*` token population in the shipped loops (occurrence counts across `loops/**/*.yaml`):** `ll-lint` 560, `ll-issues` 195, `ll-loop` 139, `ll-config` 88, `ll-auto` 60, `ll-learning-tests` 17, `ll-artifact` 7, `ll-parallel` 5, `ll-logs` 5, `ll-sprint` 4, `ll-history` 4, `ll-messages` 4, `ll-init` 4. `ll-lint`, `ll-continue-prompt`, `ll-coverage-report`, `ll-dead-code-*`, `ll-test-results` and `ll-root` do not appear in `scripts/pyproject.toml` `[project.scripts]` — they are marker comments (`# ll-lint:`), scratch-file names or similar. A blanket `ll-` prefix match, or a match outside command position, produces false `requires-issues` hits; this is the evidence behind the explicit-allowlist rule.
- **Contested: `ll-history` portability.** Edge Cases and Decision Rules both name `ll-history` as a portable wheel console script, but `cli/history.py` defaults `--directory` to `.issues` (three subcommands, ~:165/:201/:266) and resolves `config.issues.base_dir` (~:479). Other `[project.scripts]` entries whose modules touch issue paths by grep: `ll-sprint`, `ll-sync`, `ll-deps`, `ll-migrate*`, `ll-verify-evidence`, `ll-learning-tests`, `ll-auto`, `ll-parallel`. The allowlist is therefore a per-CLI judgment, and the issue's own example set disagrees with the code on at least one entry.
- **Census caveat.** The 39-of-97 count is a raw-text grep over top-level files (it includes `description:` and comment text and does not follow `import:` / `from:` / `loop:`); 97 is the top-level runnable count (96 with `initial:` plus `deep-research-arxiv`, a `from:` stub). Recursive total is ~109 runnable plus 11 `lib/` fragments. A classifier restricted to scanned fields will not reproduce 39 exactly — Implementation Step 1's "confirm census reproduces" needs the delta explained (description/comment-only hits drop out; fragment-sourced hits come in), not asserted equal.
- **Interpreter-rule corpus facts (verified).** All 13 shipped `-m little_loops.<mod>` shell invocations use `$${LL_PYTHON:-python3}`; the only two bare spellings are prose — `loops/fleet-loop-improve.yaml:25` (`description:`) and `loops/oracles/integrate-node.yaml:16` (a comment). The "zero warnings across shipped loops" AC holds only if the rule scans `action` text, never `description`/comments.
- **`cmd_validate` shape constraints** (`cli/loop/config_cmds.py:14`): the `try` around loading deliberately wraps loading only (BUG-3230 comment, ~:27-32), and both early-error JSON exits (`FileNotFoundError`, `ValueError`/`YAMLError`/`OSError`, ~:49-78) emit exactly `{loop, valid, violations}`. Classification for the `Portability:` line / `--json` `portability` key therefore has to run outside that `try` (or its failure lands in an error handler). The human path loads with `raise_on_error=True`, so a declared-vs-detected ERROR surfaces as `"<loop> is invalid: ..."` and no `Portability:` line prints on that path; dynamic-sub-loop and bare-interpreter WARNINGs reach human output only via `load_and_validate`'s own `logger.warning`.
- **Catalog line drift.** `cli/loop/info.py` anchors have moved from the issue's earlier numbers: `LoopCatalogEntry` ~:111 (`to_json_item` ~:126), `enumerate_loop_catalog` ~:151 (the three `LoopCatalogEntry(**meta)` sites ~:214/:219/:224; filter order category → label → visibility ~:230-247), `cmd_list` ~:254 (catalog call ~:372; rebuilt `all_loops` dict list ~:399-410, not ~:395-403). `hidden_counts` is tallied only when `visibilities == {"public"}` (~:241-245), so a portability filter applied after that tally leaves hidden-counts semantics intact. `_load_loop_meta` (~:63) swallows every exception into an empty-default dict, so a classification added there inherits that silent-fallback behavior unless handled separately.
- **Other catalog consumers.** `cli/logs.py:_validate_builtin_loop` (~:2323) walks built-ins via `_builtin_loop_paths()` (excludes any path with a `lib` part) and calls `load_and_validate` directly, without `resolve_loop_path`; `cli/doctor.py:_loop_validity_data` (~:987) walks the built-in dir plus `Path.cwd()/"loops"` (not `.loops`). Both pick up a rule registered in `load_and_validate` automatically.
- **`resolve_loop_path` lookup order** (`fsm/loop_paths.py`, ~:40): literal path → `<loops_dir>/<n>.fsm.yaml` → `<loops_dir>/<n>.yaml` → built-in dir → `runs/<n>/workflow.yaml` → scan of `runs/*/workflow.yaml` by internal name. A sub-loop walk keyed on the resolved path for cycle detection therefore also covers compiled `.fsm.yaml` and run-workflow targets.

## Program Design

### Types
- `PortabilityReport` (new dataclass in `fsm/validation/portability_rules.py`) — fields `tier: str`, `adapter_tier: str | None`, `evidence: list[tuple[str, str, str]]` (state, field, match), plus an `unknown` marker for dynamic sub-loops.
- `FSMLoop.portability: str | None` (`fsm/schema.py`) — optional declared tier; omitted from `to_dict` when `None`.
- `StateConfig.adapter: bool` (`fsm/schema.py`) — default `False`, omitted from `to_dict` when false.
- `StateConfig.portability_ignore: str | None` (`fsm/schema.py`) — required-reason string.

### Signatures
- `classify_portability(fsm: FSMLoop, loops_dir: Path) -> PortabilityReport` — new; classifies a parsed (post-fragment, post-`from:`) loop and its sub-loops.
- `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints: dict | None = None) -> tuple[FSMLoop, list[ValidationError]]` — existing; the portability rule is registered after `FSMLoop.from_dict`, alongside `_validate_loop_references(fsm, path.parent)`.
- `cmd_validate(loop_name: str, args, loops_dir: Path, logger) -> int` — existing; prints `Portability:` and adds the `--json` `portability` object.
- `enumerate_loop_catalog(*, loops_dir, category, label, visibilities, builtin_only)` — existing; gains a `portability` filter slotted after the visibility filter without disturbing `hidden_counts`.
- `LoopCatalogEntry.to_json_item() -> dict` — existing; gains the tier field (also reaches the MCP `loop_list` tool).
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path` — existing; the sub-loop walk resolves children through it.

### Call Path
`cmd_validate` -> `load_and_validate` -> `classify_portability` -> `resolve_loop_path` (recursively per `state.loop`, visited set keyed on resolved path)

`cmd_list` -> `enumerate_loop_catalog` -> `classify_portability` (via a fragment-resolving load, since `_load_loop_meta` stops before `resolve_fragments`)

`cmd_show` -> `load_loop_with_spec` -> `classify_portability` -> evidence lines

### Decision Rules
- **Inputs scanned**: `StateConfig.action` (all `action_type`s), `EvaluateConfig.prompt`, `EvaluateConfig.scope`, and `FSMLoop.scope`. Not scanned: `description:`, YAML comments, `context:` values.
- **`requires-plugin`**: `_SKILL_INVOKE_RE` (`/ll:([a-zA-Z0-9_-]+)`, `fsm/validation/_base.py`) matches in a scanned field.
- **`requires-issues`**: a command-position `ll-<name>` token in a *shell* action where `<name>` is in an explicit issue-system allowlist (not a blanket `ll-` prefix — `ll-loop`, `ll-history` and other wheel console scripts stay `portable`), or a `.issues/` path in any scanned field, or `.issues/` in `scope`. Allowlist contents are an open decision for the implementer; the loop must not pick it by grep of `ll-issues` alone, since `ll-auto`/`ll-sprint`/`ll-parallel` also assume an issue tree.
- **Precedence**: `requires-issues` > `requires-plugin` > `portable`; a loop's tier is the max over its own non-adapter states and its resolved sub-loops' tiers; states with `adapter: true` contribute to `adapter_tier` only.
- **Declared vs detected**: when `FSMLoop.portability` is set and detected tier ranks higher, emit an `ERROR` at `states.<name>.action` (or the matching field path) naming state and match. Absent declaration → never an error.
- **Dynamic sub-loop (`"${"` in `state.loop`)**: report `unknown (dynamic sub-loop)`. For a loop that *declares* a tier this must not silently pass or hard-fail; the rule has to say which (warning recommended, since 8 shipped loops are in this shape and the corpus test cannot otherwise assert on them).
- **Unresolvable sub-loop (`FileNotFoundError`)**: already an `ERROR` from `_validate_loop_references`; the classifier must not duplicate it.
- **Cycle guard**: visited set of resolved sub-loop paths; a revisit contributes nothing and is not an error.
- **Escape hatch**: `portability_ignore: <reason>` on a state exempts that state's matches; an empty or whitespace reason is itself an error. Distinct from `ll-portability-ok:` (shell-portability gate).
- **Bare-interpreter rule (all loops, any tier)**: `WARNING` when a shell-action line invokes `python`/`python3` followed by `-m little_loops.` and that invocation is not `$${LL_PYTHON:-python3}` (the `$$` escape is the FSM interpolation form; bare `${…}` is MR-7 territory). Scope is `-m little_loops.` only; heredoc `python3 - <<EOF` bodies that `import little_loops` are not covered by the issue text. Fix hint names `$${LL_PYTHON:-python3}`.

## Implementation Steps

1. Classifier + schema fields + fixtures (no CLI wiring); confirm census reproduces (39/97 top-level).
2. Interpreter warning, with a regression fixture taken from the pre-`21583aae3` form of `fleet-loop-improve`'s `measure_externally` action.
3. Wire into `validate` / `list` / `show`; mark brainstorm adapter states.
4. Corpus CI check; docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/schema.py` — add `FSMLoop.portability`, `StateConfig.adapter`, `StateConfig.portability_ignore` with `from_dict` / `to_dict` (omit when default); avoid field names containing `path`/`file`/`source` tokens (spike test constraint)
- Update `scripts/little_loops/fsm/validation/_base.py` — `KNOWN_TOP_LEVEL_KEYS` += `portability`; add `VALID_PORTABILITY`; re-export from `fsm/validation/__init__.py` and extend its "Package layout" docstring
- Register the portability rule in `load_and_validate` only (needs `loops_dir`); keep `validate_fsm`'s signature unchanged (`test_file_param.py` pins it). Consequence to document: `scaffold_verify` / `scaffold_eval` (in-process `validate_fsm`) will not see the rule
- Update `scripts/little_loops/cli/loop/info.py` — add the tier to both `_load_loop_meta` return dicts (incl. the `except Exception` fallback), the three `LoopCatalogEntry(**meta)` sites, `to_json_item`, and the `cmd_list` `all_loops` dict list; read new keys with `.get()` so layout-helper tests keep passing; pick a fragment-resolving loader (`load_loop` / `load_and_validate`, not `_load_loop_meta`) for the list-time classification and apply the `--portability` filter after the visibility filter so `hidden_counts` is unchanged
- Update `scripts/little_loops/cli/loop/__init__.py` — `--portability` on the `list` parser with `choices=`; read with `getattr(args, "portability", None)` in `cmd_list`
- Update `scripts/little_loops/mcp_server/tools.py` — `portability` property in the `loop_list` `input_schema` and forward it in `_tool_loop_list`
- Update `scripts/little_loops/cli/logs.py:_validate_builtin_loop` — decide on parity with `cmd_validate --json` (new `portability` key) and confirm fleet-review markdown tolerates the new WARNING class
- Update `scripts/little_loops/fleet_improve.py` baselines only if the bare-interpreter WARNING fires on any shipped loop (expected zero since `21583aae3`); confirm via `gate-baseline.json` comparison
- Update tests: `test_fsm_schema.py`, `test_fsm_validation_structural.py`, `test_fsm_validation_shell_safety.py`, `test_ll_loop_commands.py` (validate / list / show + early-error JSON shape), `test_cli_loop_dispatch.py`, `test_json_output_contracts.py`, `test_feat_3352_mcp_loop_list.py`, `test_brainstorm.py`, `test_builtin_loops.py` (`CATEGORY_PATTERNS` ratchet entry); add `test_fsm_validation_portability.py`
- Update docs: `docs/reference/CLI.md`, `docs/reference/json-output-contracts.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/generalized-fsm-loop.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/MCP_SERVER_GUIDE.md`, `skills/review-loop/reference.md`, `skills/create-loop/reference.md`, `scripts/little_loops/loops/README.md`; add `DOC_STRINGS_PRESENT` rows in `test_wiring_reference_docs.py`

## Impact

- **Priority**: P3. Small, and protects an existing invariant. The latent interpreter bug it would have caught has been fixed directly (`21583aae3`), so nothing here is urgent. Sequence it after the EPIC-3581 core chain (FEAT-3667 → FEAT-3582) so the brainstorm adapter marker lands with the rewrite rather than against the old loop.
- **Effort**: Small–medium. Most of it reuses fragment resolution and the existing regex.
- **Risk**: Low. Info-level for undeclared loops, so nothing existing breaks.
- **Breaking Change**: No.

## Use Case

A developer browsing `ll-loop list` wants a loop they can run in a client repo that has never run `ll-init`. Today they have to open each YAML and grep for `/ll:` and `ll-issues`. With tiers, `ll-loop list --portability portable` answers immediately. A loop author who declares `portability: portable` learns at `validate` time, not from a user's bug report, that a new state they added pulls in `/ll:capture-issue`.

## Acceptance Criteria

- [ ] `ll-loop validate <loop>` prints `Portability: <tier>` (plus adapter tier when present); `--json` includes `portability` with evidence.
- [ ] Declared `portability: portable` on a loop that references `/ll:capture-issue` in a non-adapter state → validation error naming the state and match.
- [ ] Tier accounts for imported fragments, `from:` inheritance and sub-loops (fixture: a portable-looking loop whose imported fragment calls `ll-issues` → `requires-issues`).
- [ ] Bare `python3 -m little_loops.X` in a shell action → warning with fix hint. A corpus test asserts zero such warnings across shipped loops (true since `21583aae3`).
- [ ] Brainstorm's `sink_issue` / `sink_decision` marked `adapter: true`. `ll-loop validate brainstorm` reports `portable (adapters: requires-plugin)`. Coordinate the marker with FEAT-3582 so the rewritten loop keeps it.
- [ ] `ll-loop list` shows the tier column and supports `--portability`. `ll-loop show` lists evidence lines.
- [ ] The MCP `loop_list` tool accepts a `portability` argument (new `input_schema` property forwarded by `_tool_loop_list`) and filters exactly like `ll-loop list --portability <tier>`. Verified by an MCP-side test in `test_feat_3352_mcp_loop_list.py` that passes `portability` and asserts the returned entries match the CLI `--json` filter result, and that entries carry the tier key.
- [ ] A state with `portability_ignore: <non-empty reason>` is exempted from tier detection (its matches add no evidence and do not trip a declared-vs-detected error); an empty or whitespace-only reason is a validation error. Verified by fixtures in `test_fsm_validation_portability.py` covering the exempted, empty-reason and whitespace-reason cases.
- [ ] A loop that declares `portability:` and contains a dynamic sub-loop (`loop: ${...}`) gets a validation **warning** (not an error, not silent) stating the tier is `unknown (dynamic sub-loop)`; an undeclared loop reports the unknown outcome with no violation. Verified by a fixture in `test_fsm_validation_portability.py`, and by the corpus test passing with the 8 shipped dynamic-sub-loop loops (`goal-cluster`, `loop-composer`, `loop-composer-adaptive`, `proof-first-task`, `spike-gate`, `loop-router`, `outer-loop-eval`, `rn-build`) producing no errors.
- [ ] CI corpus test asserts that every loop with a declared tier validates, and records the tier distribution.
- [ ] Loop authoring docs (`docs/guides/LOOPS_GUIDE.md`) state the decoupling rule and the tiers. This is the rule's first in-repo home.

## Edge Cases

- `/ll:` text inside a comment, a `description:`, or an example in a prompt that says "do not run /ll:..." gives false positives. Match only action/prompt bodies, and allow a per-state `portability_ignore:` escape hatch with a required reason.
- Interpolated sub-loop names (`loop: ${context.child}`) cannot be resolved statically, so report the tier as `unknown (dynamic sub-loop)` rather than guessing.
- `ll-*` CLIs that are wheel console scripts (e.g. `ll-loop`, `ll-history`) are portable. Only issue-system and plugin-dependent commands raise the tier, so keep an explicit allowlist rather than flagging every `ll-` prefix.

## Related Key Documentation

- FEAT-2248 § Portability (origin of the decoupling rule)
- EPIC-3581 § Out of scope ("Core must stay decoupled from the Issue system")
- FEAT-2354 § Portability & Lock-in Analysis
- FEAT-3717: `ll-loop export` (consumes this classification)
- Hub: `ll-product/docs/architecture/little-loops-on-the-stack/` §2 (EPIC-397 "advertised surface not mechanically checked"), §6 `ll-loops` extraction

## Labels

`loops`, `validation`, `portability`

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-04T02:15:17 - `7338e0e0-45bb-417c-9acd-76d793d69fe6.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-04T02:12:21 - `e92024fd-e3f0-4727-b856-b77ba777115a.jsonl`
- `/ll:reconcile-issue` - 2026-10-04T02:02:28 - `ff3c4eb4-2263-4904-8752-da1b86a5b6a0.jsonl`
- `/ll:wire-issue` - 2026-10-04T01:59:31 - `03599537-a8c3-4077-be10-3fe84481da10.jsonl`
- `/ll:decide-issue` - 2026-10-04T01:41:39 - `dfdca29c-b349-4087-8e1f-8022626b9966.jsonl`
- `/ll:refine-issue` - 2026-10-04T01:38:39 - `9cf7f744-4459-4907-b6cf-6671c4a04f78.jsonl`
