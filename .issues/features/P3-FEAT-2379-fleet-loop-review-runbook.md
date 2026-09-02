---
id: FEAT-2379
type: FEAT
title: 'Fleet loop-review runbook + `make` target — continuous improvement of built-in loops from cross-project logs'
priority: P3
status: open
captured_at: '2026-06-28T20:54:00Z'
discovered_date: 2026-06-28
discovered_by: user-report
parent: EPIC-1918
labels:
- docs
- tooling
- ll-loop
- ll-logs
- meta-loop
- workflow
relates_to:
- BUG-2377
- ENH-2378
decision_needed: false
confidence_score: 75
verify_verdict: VALID
---

# FEAT-2379: Fleet loop-review runbook + repeatable target

## Summary

Turn "use other projects' logs to continuously fix and improve this repo's built-in loops"
into a repeatable, documented cycle: a runbook at `docs/runbooks/FLEET_LOOP_REVIEW.md` plus a
`make fleet-loop-review` entry point that harvests fleet-wide loop outcomes from other
projects on the machine, attributes failures to specific built-in loops, and writes a dated
diagnostic report with a baseline diff against the prior run.

## Current Behavior

Cross-project loop-review happens ad hoc: someone manually runs `ll-logs loop-fleet`,
`scan-failures`, `sequences`, and `dead-skills` against other projects, eyeballs the output,
and fixes a loop if something looks wrong. There is no fixed cycle, no recorded baseline, and
no dated report — so there is no way to mechanically confirm afterward that a fix actually
reduced the fleet's failure rate for that loop.

## Expected Behavior

A single repeatable entry point (`make fleet-loop-review` or equivalent) chains the four
HARVEST-phase `ll-logs` commands and the per-loop `ll-loop` diagnose commands, attributes
flagged failures to built-in loops, and writes a dated report under
`.loops/diagnostics/fleet-review-<date>.md`. The report stores per-loop failure counts so the
next run can diff against it, making "did this fix help?" a mechanical re-measurement rather
than a fresh manual investigation. The cycle and its commands are documented in
`docs/runbooks/FLEET_LOOP_REVIEW.md`.

## Goal

Make "use other projects' logs to continuously fix and improve this repo's built-in loops" a
**repeatable, documented cycle** rather than an ad-hoc investigation. Other projects on the
machine act as a *test fleet* for the 77 shipped loops; their run traces feed improvements
back here, and each fix is validated against the fleet's next-cycle failure delta.

## The cycle

```
HARVEST (cross-project, read-only)
  → ATTRIBUTE each failure/stall to a built-in loop
    → DIAGNOSE + FIX (in this repo)
      → RE-MEASURE (next harvest's failure delta = acceptance signal)
```

The final arrow is mandatory: per the meta-loop rules in `.claude/CLAUDE.md`, a harness
"improvement" is only proven when an *external* measure moves — here, the fleet's failure
rate for that loop. Other-projects' logs are the unbiased oracle a self-grade cannot be.

## Deliverables

1. **A runbook** at `docs/runbooks/FLEET_LOOP_REVIEW.md` documenting the cycle, the commands at
   each phase, how to attribute, how to record a baseline, and the in-scope rule (fix only
   built-ins here; other projects' own loops are fixed in place). This is the **first runbook**;
   it establishes the `docs/runbooks/` home and the runbook header convention (see "Runbook
   conventions" below) for future operational procedures.
2. **A repeatable entry point** — a `make fleet-loop-review` / `just` target (or a thin
   `scripts/` wrapper) that chains:
   - `ll-logs loop-fleet -j` (ENH-2378) — run outcomes per built-in loop.
   - `ll-logs scan-failures --all --window-days N -j` — CLI-level failure clusters.
   - `ll-logs sequences --all` — how loops chain / where they stall.
   - `ll-logs dead-skills` — built-in loops with zero fleet invocations.
   - `ll-loop validate` / `diagnose-evaluators` / `calibrate-budget` over the flagged loops.
   The target writes a dated report under `.loops/diagnostics/fleet-review-<date>.md`.
3. **A baseline record** so re-measurement is mechanical: the report stores per-loop failure
   counts; the next run diffs against the prior report to show whether shipped fixes helped.

## Scope decisions (from capture conversation)

- **Mechanism**: repeatable runbook + harvester command, run on demand (not a scheduled
  cron, not a built-in meta-loop — those were the alternatives considered and deferred).
- **Target**: this repo's **built-in** loops only. Cross-project data is *evidence*; fixes to
  other projects' `.loops/` happen in those projects, not back-ported here.

## Runbook conventions (location decision)

This is the first **runbook** in the repo, so it establishes the artifact class. A *guide*
(`docs/guides/*`) explains a feature; a *runbook* documents an **operational procedure executed
on a cadence**, with a checklist and a recorded baseline. To keep the classes distinct:

- **Home**: runbooks live under `docs/runbooks/`, not `docs/guides/`. Create the directory with
  this issue.
- **Header convention**: every runbook leads with these sections, in order —
  **Purpose · Cadence · Phases · Baseline / Re-measure contract · In-scope rule**. The
  re-measure contract is mandatory (it is what makes a procedure a runbook rather than a guide).
- Future operational procedures (release drills, fleet sweeps, recurring audits) follow the same
  location and header convention.

## Integration Map

### Files to Modify
- `docs/runbooks/FLEET_LOOP_REVIEW.md` — new file; `docs/runbooks/` does not exist yet in the tree (confirmed: zero matches for the directory or for `Cadence`/`Re-measure`/`In-scope rule` as an existing doc-header shape anywhere in the repo).
- Repeatable entry point — no `Makefile` or `justfile` exists anywhere in this repo today (the only `Makefile` hit repo-wide is a vendored `node_modules/json-stringify-safe/Makefile`, unrelated). Three existing conventions this entry point could follow, each already present in the repo for a different reason:
  - a standalone `scripts/*.sh` wrapper — the only existing standalone-script convention (`scripts/verify_learning_citations.sh`: usage banner, `set -euo pipefail`, exit-code contract).
  - a registered `ll-*` Python CLI subcommand — every `ll-logs`/`ll-loop` subcommand is wired via `subparsers.add_parser()` inside one module plus a `[project.scripts]` entry in `scripts/pyproject.toml:74-114` (e.g. `ll-logs = "little_loops.cli:main_logs"`).
  - an LLM-driven skill/command — `skills/audit-loop-run/SKILL.md` is the only existing precedent in this repo for "issue a sequence of `ll-*`/`ll-issues`/`git` calls and synthesize a markdown report" as numbered prose steps rather than orchestration code; a repo-wide search for `subprocess.run(["ll-` returns zero hits, so no Python module anywhere chains `ll-*` CLIs programmatically today.
- `.loops/diagnostics/fleet-review-<date>.md` — generated output, not a source file to create by hand. `.loops/diagnostics/` already exists and holds differently-named one-off reports (`audit-interactive-component-generator-2026-06-28.md`, `vega-viz-20260702T025053Z.md`, `general-task-20260707T152654Z.md`); no file matching `fleet-review-*` exists there yet, and the directory's only established writer today is the `loop-specialist` agent itself (`agents/loop-specialist.md`), which writes directly via its own tool calls — no Python helper function writes into this directory.

_Wiring pass added by `/ll:wire-issue`:_
- **Conditional — only if a new top-level `ll-*` console script is chosen for the entry point**: `scripts/pyproject.toml:74-119` `[project.scripts]` block — add one `ll-<name> = "little_loops.cli:main_<name>"` line following the existing 46-line convention (e.g. `ll-logs = "little_loops.cli:main_logs"` at line 103). Per `CONTRIBUTING.md:393-417` this also requires a new `### ll-<toolname>` section in `docs/reference/CLI.md` (enforced by `test_wiring_cli_registry.py::test_cli_entry_point_coverage`, see Tests below), a `skills/configure/areas.md` "Authorize all ll- commands" preset entry, and `"Bash(ll-<toolname>:*)"` in `little_loops/init/writers.py::_LL_PERMISSIONS` — all gated by `ll-verify-cli-allowlist` (BUG-2764). This entire bullet does not apply if the shell-script or LLM-skill mechanism is chosen instead. [Agent finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` (holds all four HARVEST-phase subcommands) is imported by `scripts/little_loops/cli/__init__.py:75`, `scripts/little_loops/cli/ctx_stats.py:20`, `scripts/little_loops/cli/loop/_helpers.py:19`, and tested by `scripts/tests/test_ll_logs.py:16`, `scripts/tests/test_enh_3166_qwen_normalizer.py:32`, `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:31`, `scripts/tests/test_cli_ctx_stats.py:13` — none require modification for this issue; listed to confirm `logs.py`'s current consumer surface is stable and won't be disturbed by adding a new orchestrator on top of it.
- `agents/loop-specialist.md` — the agent this issue's runbook must link (per Acceptance Criteria); also asserted by `scripts/tests/test_wiring_skills_and_commands.py` to reference `.loops/diagnostics/` and `FEAT-1532`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/loop-specialist-eval.yaml` (lines 4-35, 50-56) — a separate file from `agents/loop-specialist.md` that independently encodes the same `.loops/diagnostics/<loop>-<ts>.md` naming/section convention as an eval pass/fail criterion. Its filename pattern (`<loop>-<ts>.md`, no `fleet-review-` prefix) does not collide with this issue's `fleet-review-<date>.md`, but the report writer should be aware this second file exists and shares the directory. [Agent finding]
- `scripts/little_loops/session_store/writers.py::update_loop_run_diagnostics` (lines 1556-1574) and `docs/reference/CLI.md:4721` (`ll-session export --shareable` excludes `diagnostics_path`) — the existing mechanism for linking a `.loops/diagnostics/` artifact to session history is `run_id`-scoped (one `run_id` → one `diagnostics_path`). A fleet-wide report spanning many loops' runs has no single natural `run_id` to key on — this issue's report writer should NOT attempt to route through `update_loop_run_diagnostics`; it is a structural mismatch, not a missing wiring target. [Agent finding]
- `scripts/tests/test_fsm_validation_meta_rules.py::test_mr3_does_not_fire_for_diagnostics_dir` (lines 330-334) — confirms the FSM validator's MR-3 artifact-isolation rule already carves out `.loops/diagnostics/` writes generically; no FSM validator change is needed regardless of which entry-point mechanism is chosen. [Agent finding]

### Conventions in Force
- All four HARVEST-phase `ll-logs` subcommands share three argparse helpers — `add_corpus_target_args()`, `add_window_args()`, `add_json_arg()` (`scripts/little_loops/cli_args.py`) — confirming `--all`, `--window-days N`, and `-j`/`--json` exist exactly as this issue's Deliverable #2 assumes, uniformly across `loop-fleet`, `scan-failures`, `sequences`, and `dead-skills`.
- `ll-loop validate`, `diagnose-evaluators`, and `calibrate-budget` each take exactly one positional `loop` argument (`cmd_validate`, `cmd_diagnose_evaluators`, `cmd_calibrate_budget` in `scripts/little_loops/cli/loop/`) — there is no batch/glob form on the `ll-loop` side, so "run over the flagged loops" requires one invocation per flagged loop name.
- The only existing "diff current data against a stored baseline" mechanism in the codebase is `regressions()` / `write_baseline()` in `scripts/little_loops/cli/verify_private_refs.py:446-474`, which stores per-file **counts** in a checked-in JSON (`.ll/private-refs-baseline.json`, with an explanatory `_comment` field) and regenerates via a `--update-baseline` flag. This is a count-diff pattern over a JSON baseline, not a diff between two dated markdown reports — the closest analog found for the re-measurement contract, not a drop-in fit.
- `docs/guides/*.md` (the class this issue's runbook is meant to read differently from) share a `# Title` + `> **When to use this**:` blockquote + `## Contents` TOC shape (e.g. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:1-34`, `docs/guides/LOOPS_GUIDE.md:1-33`) — none use a labeled Purpose/Cadence/Phases header. `docs/observability/*.md` (e.g. `realized-savings-verification.md`, `des-audit.md`) is a third, already-in-use header shape (title + dated prose + results table) for one-off audit/closure reports — distinct from both `docs/guides/` and this issue's proposed runbook convention, so no doc in the repo currently uses the Purpose · Cadence · Phases · Baseline/Re-measure · In-scope header this issue proposes.

### Tests
- `scripts/tests/test_ll_logs.py` — existing coverage for the four HARVEST-phase subcommands: `test_loop_fleet_*` (~lines 4990-5345), `test_scan_failures_*` (~2989-3104), `test_sequences_*` (~785-1447), `test_dead_skills_*` (~2550-2641).
- `scripts/tests/test_cli.py` — end-to-end argv-level invocations at ~line 3005 (`scan-failures --all`), ~3047 (`dead-skills --all --sort name`), ~3084 (`loop-fleet`).
- No test file exists yet for the new entry point or report writer this issue proposes, since neither is implemented.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — add `docs/runbooks/FLEET_LOOP_REVIEW.md` to the `DOC_FILES_MUST_EXIST` list (lines 400-423, `(file_path, issue_id)` tuples) and to the `DOC_STRINGS_PRESENT` list (lines 27-336, `(doc_path, expected_string, issue_id)` tuples) with a needle proving it links `loop-specialist` and states the in-scope rule — following the exact convention already used for `("agents/loop-specialist.md", ".loops/diagnostics/", "FEAT-1532")` at line 192. No existing test asserts *ordered* section headers (Purpose · Cadence · Phases · Baseline/Re-measure · In-scope rule); every doc-wiring test in this family checks unordered substring presence only. [Agent finding]
- **Conditional — if a new top-level `ll-*` console script is chosen**: `scripts/tests/test_wiring_cli_registry.py::test_cli_entry_point_coverage` (lines 216-235) will fail until a matching `### ll-<toolname>` section exists in `docs/reference/CLI.md` — add both together. Follow `scripts/tests/test_ll_logs.py`'s subcommand test shape: a parse-only test (`test_dead_skills_subcommand_parsed`, lines 2550-2556), a `--project`/`--all` mutual-exclusion test (`test_dead_skills_project_and_all_mutually_exclusive`, lines 2623-2627), and a behavioral test patching `sys.argv`+`builtins.print` (`test_dead_skills_window_days_behavioral`, lines 2569-2621), plus a `test_cli.py` smoke test. [Agent finding]
- **Conditional — if a shell-script entry point is chosen**: model the pytest gate after `scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` (lines 53-79) — `shutil.which()` guard, `pytest.skip()` if the tool is absent, `subprocess.run(..., capture_output=True, timeout=N)`, assert `returncode == 0`. No existing pytest wraps `scripts/verify_learning_citations.sh` to copy directly (its only caller is the FSM loop `integrate-sdk.yaml`, not a test). [Agent finding]
- Baseline-diff pattern for the re-measurement contract (resolves part of the Decision Rules gap below): two independent precedents exist, not one. `scripts/tests/test_verify_private_refs.py::TestBaseline` models a count-per-path baseline (doesn't survive renames); `scripts/tests/test_verify_evidence.py::TestBaseline`/`TestBaselineKeying` models a set-of-hashes-per-stable-ID baseline (survives renames). Since loop names are stable identifiers that don't get renamed the way issue files do, the count-per-key shape (`test_verify_private_refs.py`'s pattern, keyed on loop name instead of file path) is the structurally closer fit for a per-loop failure-count baseline. [Agent finding]

### Documentation
- `docs/reference/CLI.md` — `ll-logs` subcommand table (~lines 3459-3472), flags (~3510-3536), examples (~3599-3620); `ll-loop validate` (~904), `diagnose-evaluators` (~1228), `calibrate-budget` (~1247) — the flag names/defaults this issue's Deliverable #2 assumes are already documented there and match the implementation.

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` lines 192-228 — the repo's human-facing docs index: a "Guides" table (196-213, `docs/guides/*.md`) and a "Reference" table (220-228, e.g. `CLI Reference` → `docs/reference/CLI.md`). Neither has a "runbooks" row/category; add one once `docs/runbooks/FLEET_LOOP_REVIEW.md` exists. Not test-enforced (`scripts/tests/test_readme_structure.py` only checks README stays a "hero page," not that this index matches the `docs/` tree). [Agent finding]
- `CONTRIBUTING.md:192-221` — directory-tree listing of `docs/` subdirectories (`reference/`, `guides/`, `development/`, `research/`, `claude-code/`, `codex/`, `demo/`); no `runbooks/` line exists. Add one. [Agent finding]
- `mkdocs.yml:65-100` — the `nav:` block has `Guides:`/`Reference:`/etc. sections (e.g. `guides/GETTING_STARTED.md`) but no `Runbooks:` section or `runbooks/` path; add one so the new doc surfaces in the built docs site. [Agent finding]

### Configuration
N/A — no `.ll/ll-config.json` key, `config-schema.json` entry, or `.ll.local.md` field references `fleet-review`, `fleet_loop_review`, or a `loop-fleet` output path today.

_Wiring pass added by `/ll:wire-issue`:_
- No config key is required by this issue's own scope, but if the implementer's chosen mechanism needs settings (e.g. default `--window-days`, output path, baseline path), the closest existing analogs are `orchestration.composer`/`orchestration.cluster` in `config-schema.json:1711-1749` (per-built-in-loop orchestration settings, e.g. `max_plan_nodes`, `max_batch_size`) if framed as a loop-orchestration feature, or the top-level `automation` block (`config-schema.json:237`, "Sequential automation script settings (`ll-auto`)") if framed as a standalone script. [Agent finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a `docs/runbooks/` entry to `CONTRIBUTING.md`'s docs directory tree (lines 192-221) and to `mkdocs.yml`'s `nav:` block (lines 65-100).
- Add a "runbooks" row/category to `README.md`'s Guides/Reference index tables (lines 192-228).
- Add `docs/runbooks/FLEET_LOOP_REVIEW.md` to `DOC_FILES_MUST_EXIST` and `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_skills_and_commands.py`, following the existing `agents/loop-specialist.md` row.
- Resolve the Decision Rules baseline-shape gap using the count-per-loop-name model (closer fit than the hash-per-ID model — see Tests above), then model its test on `scripts/tests/test_verify_private_refs.py::TestBaseline`.
- **If** a new top-level `ll-*` console script is chosen: register it in `scripts/pyproject.toml`'s `[project.scripts]`, add a `### ll-<toolname>` section to `docs/reference/CLI.md`, and add coverage in `scripts/tests/test_wiring_cli_registry.py` + `scripts/tests/test_ll_logs.py`-style subcommand tests (parse/mutual-exclusion/behavioral). **If** a shell script is chosen instead: add a `test_policy_builder_node_gate.py`-style pytest wrapper (`shutil.which()` guard, `subprocess.run`, assert exit 0). Do not do both.
- Do not route the fleet-wide report through `session_store/writers.py::update_loop_run_diagnostics` — it is `run_id`-scoped and does not fit a multi-loop report (see Dependent Files above).

## Program Design

### Types
N/A — no new persistent data type. The two artifacts this issue introduces are a markdown runbook doc and a generated markdown report; the report's *shape* (what fields per flagged loop, what the diff table looks like) is not specified anywhere yet — see Decision Rules below.

### Signatures
- `_cmd_loop_fleet(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/logs.py:2108`) — implements `ll-logs loop-fleet`, the HARVEST phase's core data source.
- `_cmd_scan_failures(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/logs.py:1193`) — implements `ll-logs scan-failures`.
- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` (`scripts/little_loops/cli/loop/config_cmds.py`) — single-loop, no batch form.
- `ll-logs loop-fleet [--project DIR | --all] [--loop NAME] [--window-days D | --since DATE] [--until DATE] [--existing-only] [--sort {success,name}] [--limit N] [-j|--json]` — `_cmd_loop_fleet()` (`scripts/little_loops/cli/logs.py:2108`). `--json` output is a **flat list of per-run records** — `{"loop_name","project","run_folder","final_state","iterations","outcome","ts","attribution"}` — not aggregated per loop; success-rate/median-iterations/top-outcome aggregation exists only in the human-table branch of `_cmd_loop_fleet`, not in `--json`. Any orchestrator consuming `-j` output must re-derive per-loop aggregates itself.
- `ll-logs scan-failures [--project DIR | --all] [--window-days D | --since DATE] [--until DATE] [--capture] [--capture-foreign] [--limit N] [--skill NAME] [-j|--json]` — `_cmd_scan_failures()` (`:1193`). `--json` → list of `{"tool","count","normalized_sig","sample_error","session_ids","skills"}` clusters keyed by `(cwd_path, tool_name, normalized_error_sig)` — clusters carry no loop-name field, so attributing a cluster to a specific built-in loop is not mechanical.
- `ll-logs sequences [--project DIR | --all] [--min-len N] [--min-count N] [--top N] [--window-days D | --since DATE] [--until DATE] [-j|--json]` — `_cmd_sequences()` (`:630`).
- `ll-logs dead-skills [--project DIR | --all] [--window-days D | --since DATE] [--until DATE] [--threshold N] [--sort {tier,name}] [-j|--json]` — `_cmd_dead_skills()` (`:1039`). `--json` → `{"skill","invocations","tier"}` where `tier` is `"never"` (0 invocations) or `"rarely"` (`<= --threshold`, default 3).
- `ll-loop validate <loop> [-j|--json]`, `ll-loop diagnose-evaluators <loop> [--threshold F] [--min-runs N] [-j|--json]`, `ll-loop calibrate-budget <loop> [--threshold F] [--min-runs N] [-j|--json]` — `cmd_validate`/`cmd_diagnose_evaluators`/`cmd_calibrate_budget` (`scripts/little_loops/cli/loop/config_cmds.py`, `scripts/little_loops/cli/loop/info.py`) — each takes exactly one positional `loop` (name or path); no fleet-wide/batch form exists on the `ll-loop` side.

### Call Path
entry point -> one call each of `ll-logs loop-fleet -j`, `ll-logs scan-failures --all --window-days N -j`, `ll-logs sequences --all`, `ll-logs dead-skills` -> ATTRIBUTE (classification logic, see Decision Rules — not yet specified) -> per flagged loop name: `ll-loop validate <loop>`, `ll-loop diagnose-evaluators <loop>`, `ll-loop calibrate-budget <loop>` -> writes `.loops/diagnostics/fleet-review-<date>.md` -> re-measure diff against the prior dated report (no existing helper for this; closest analog is `regressions()`/`write_baseline()`, `scripts/little_loops/cli/verify_private_refs.py:446-474`, which diffs current-vs-baseline **counts** in a checked-in JSON file, not two markdown reports).

### Decision Rules
- **Unspecified — genuine gap, not resolved by research.** The ATTRIBUTE phase needs a concrete rule for which loops get "flagged" for DIAGNOSE, drawn from three differently-shaped data sources: `loop-fleet`'s per-run records (success-rate/outcome aggregation is not present in `--json`, only in the human-table code path — see Signatures above), `scan-failures`'s clusters (keyed by `(cwd, tool, normalized_error_sig)`, with no loop-name field to join on), and `dead-skills`'s never/rarely tiers. Neither this issue's text nor the codebase research specifies: the exact success-rate or failure-count threshold that makes a loop "flagged," how a `scan-failures` cluster gets attributed to a specific built-in loop name, or a dismissal/escape hatch for a loop that is flagged but judged a false positive on review. This is left for the implementer to define.

## Use Case

**Who**: A little-loops maintainer investigating why one of the 77 shipped loops keeps
stalling or failing across the projects that use it.

**Context**: They currently have to manually chain `ll-logs loop-fleet`, `scan-failures`,
`sequences`, and `dead-skills` against every other project, eyeball the output, and guess
whether a fix actually helped — with no recorded baseline to check against later.

**Goal**: Run one command (`make fleet-loop-review`) to harvest fleet-wide outcomes for all
built-in loops, get a list of flagged loops with diagnose-tool output, fix the worst offender,
then run the same command again next cycle.

**Outcome**: The second run's dated report diffs against the first, showing the failure-count
delta for the fixed loop — proving the fix worked (or didn't) against real fleet data instead
of a self-graded claim.

## Acceptance Criteria

- `make fleet-loop-review` (or documented equivalent) runs end-to-end and produces a dated
  diagnostic report with: per-built-in-loop fleet outcomes, flagged loops, and a baseline diff
  vs. the previous report.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` documents the four phases and the re-measurement contract.
- The runbook explicitly states the in-scope rule and links the diagnose tools and
  `loop-specialist` agent.
- Running the cycle twice (before/after a deliberate built-in-loop fix) demonstrates the
  failure-delta acceptance signal.

## Impact

- **Priority**: P3 - process/tooling improvement for maintainers, not user-facing or blocking.
- **Effort**: Medium - chains existing `ll-logs`/`ll-loop` CLIs (no new data source), but the
  ATTRIBUTE-phase flagging rule and the baseline-diff shape are an open Decision Rules gap the
  implementer must resolve.
- **Risk**: Low - the HARVEST phase is read-only; the only mutating step (fixing a flagged
  built-in loop) already goes through normal review.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-28 | Priority: P3

## Dependencies

Both prerequisites have landed — this issue is unblocked (`blocked_by` cleared).

- **BUG-2377** (done) — parseable `ll-logs` output.
- **ENH-2378** (done) — `ll-logs loop-fleet` harvester, the HARVEST phase's core data source
  (implemented in `scripts/little_loops/cli/logs.py`).

## Future extension (out of scope here)

If the on-demand runbook proves valuable, promote it to a scheduled capture
(`scan-failures --capture-foreign` on a cron) and/or a built-in `fleet-loop-improve.yaml`
meta-loop following `diagnose → propose → apply → measure-externally`. Captured here so the
path is recorded, not built.

## Related Key Documentation

- `.claude/CLAUDE.md` — the runbook's harvest phase chains `ll-logs`/`ll-loop` CLI tools documented in the CLAUDE.md catalog, and the "measure-externally" re-measurement contract directly invokes the meta-loop rules (diagnosis-first, non-LLM evaluator) this doc defines.

## Session Log
- `/ll:format-issue` - 2026-09-02T19:54:35 - `972ffda4-3540-46cc-931f-997ebd4d75a3.jsonl`
- `/ll:wire-issue` - 2026-09-02T19:12:27 - `d3f3386b-13e9-4c55-8779-7f6afaf007ab.jsonl`
- `/ll:refine-issue` - 2026-09-02T19:00:54 - `ac9b1a09-d320-4fd9-96b4-3dcc47985b24.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:31 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Parented to EPIC-1918 (was unparented; assigned per /ll:create-epics-from-unparented sweep).
- `/ll:audit-issue-conflicts` - 2026-06-29T01:47:32 - `0f8f08b1-212f-4f62-9ad9-264556960322.jsonl`
