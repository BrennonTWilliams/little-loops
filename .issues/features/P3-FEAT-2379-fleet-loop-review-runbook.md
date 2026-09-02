---
id: FEAT-2379
type: FEAT
title: 'Fleet loop-review runbook + `ll-logs fleet-review` — continuous improvement of built-in loops from cross-project logs'
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
into a repeatable, documented cycle: a runbook at `docs/runbooks/FLEET_LOOP_REVIEW.md` plus an
`ll-logs fleet-review` subcommand that harvests fleet-wide loop outcomes from other projects
on the machine, flags built-in loops by a fixed rule, and writes a dated diagnostic report
with a baseline diff against the prior run's JSON sidecar.

## Current Behavior

Cross-project loop-review happens ad hoc: someone manually runs `ll-logs loop-fleet`,
`scan-failures`, and `sequences` against other projects, eyeballs the output,
and fixes a loop if something looks wrong. There is no fixed cycle, no recorded baseline, and
no dated report — so there is no way to mechanically confirm afterward that a fix actually
reduced the fleet's failure rate for that loop.

## Expected Behavior

A single repeatable entry point (`ll-logs fleet-review`) runs the HARVEST-phase collectors
in-process, flags built-in loops by a fixed rule over `loop-fleet` aggregates, validates the
flagged loops, and writes a dated report under `.loops/diagnostics/fleet-review-<date>.md`
plus a JSON sidecar holding per-loop counts. The next run diffs against the newest prior
sidecar, making "did this fix help?" a mechanical re-measurement rather than a fresh manual
investigation. The cycle, its commands, and the cross-project DIAGNOSE step are documented in
`docs/runbooks/FLEET_LOOP_REVIEW.md`.

## Goal

Make "use other projects' logs to continuously fix and improve this repo's built-in loops" a
**repeatable, documented cycle** rather than an ad-hoc investigation. Other projects on the
machine act as a *test fleet* for all runnable built-in loops (the set returned by
`_get_builtin_loop_names()` in `scripts/little_loops/cli/logs.py` — every `*.yaml` under the
package `loops/` dir except `lib/` fragments; 89 at time of writing, do not hard-code the
number); their run traces feed improvements back here, and each fix is validated against the
fleet's next-cycle failure delta.

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
2. **A repeatable entry point** — `ll-logs fleet-review` (see "Decisions" below for why this
   mechanism) that, in-process, runs:
   - the `loop-fleet` collector (ENH-2378) over `--all` projects — run outcomes per built-in
     loop; this is the **only flagging input**.
   - the `scan-failures` and `sequences` collectors over the same window — emitted as
     **unattributed context appendices** in the report (they carry no loop-name key; see
     Decisions).
   - a **zero-run built-ins** section derived as `_get_builtin_loop_names()` minus the loop
     names present in the `loop-fleet` records. (`ll-logs dead-skills` does **not** cover
     loops — it enumerates the `skills/` catalog only — and `loop-fleet` never emits loops
     with zero runs, so this must be derived.)
   - `ll-loop validate <loop>` for each flagged loop (runs here; validate reads the YAML, not
     history).
   The command writes `.loops/diagnostics/fleet-review-<date>.md` plus a machine-readable
   sidecar `.loops/diagnostics/fleet-review-<date>.json` (see Deliverable 3).
   The runbook's DIAGNOSE phase then directs the maintainer to run `ll-loop
   diagnose-evaluators <loop>` / `calibrate-budget <loop>` **from inside the project that
   produced the failing runs** (the `project` field of each `loop-fleet` record) — see
   Decisions for why they cannot run here.
3. **A baseline record** so re-measurement is mechanical: the JSON sidecar stores per-loop
   `{runs, converged, success_pct, top_outcome, projects}`; the next run loads the newest prior
   sidecar and renders a delta table in the report. Never parse the prior markdown.

## Scope decisions (from capture conversation)

- **Mechanism**: repeatable runbook + harvester command, run on demand (not a scheduled
  cron, not a built-in meta-loop — those were the alternatives considered and deferred).
- **Target**: this repo's **built-in** loops only. Cross-project data is *evidence*; fixes to
  other projects' `.loops/` happen in those projects, not back-ported here. This filter is
  **mechanical**: every `loop-fleet` record carries `attribution: "builtin" | "custom"`
  (`logs.py:2055`), so only `builtin` records feed flagging.

## Decisions (resolved 2026-09-02 review)

1. **Mechanism — `ll-logs fleet-review` subcommand**, not a Makefile/justfile, shell script, or
   LLM skill. Rationale: it lives in `scripts/little_loops/cli/logs.py` beside the four
   collectors it consumes, calls them **in-process** (no `subprocess` chaining of `ll-*`
   CLIs — none exists in the repo today), inherits `add_corpus_target_args()` /
   `add_window_args()` / `add_json_arg()` for free, follows the existing subcommand test shape,
   and avoids the new-console-script chain (`pyproject.toml` `[project.scripts]`, permission
   allowlist, `ll-verify-cli-allowlist`, CLI-registry test). A Makefile would be the repo's
   first; if a `make fleet-loop-review` alias is still wanted later, it is a three-line wrapper
   around this command and out of scope here. **The conditional shell-script and console-script
   wiring branches below no longer apply.**
2. **Flagging rule (ATTRIBUTE phase)** — computed from `loop-fleet` aggregates only. A loop is
   flagged when **all** of: `attribution == "builtin"`, `runs >= --min-runs` (default 3), and
   (`success_pct < --threshold` (default 50) **or** `top_outcome in {"error", "max-steps",
   "cycle"}`). Both knobs are flags on `fleet-review`, not config keys. There is no dismissal
   list in v1: a false positive is handled by the maintainer skipping it in DIAGNOSE and noting
   why in the report's "Reviewed, not fixed" section (free-text, written by hand after the run).
3. **`scan-failures` / `sequences` are context, not flagging inputs.** `scan-failures` clusters
   are keyed on `(cwd, tool, normalized_error_sig)` with no loop-name field; joining them to
   loops via `session_ids` → run folders would be a new feature. They are rendered verbatim as
   appendix tables under the flagged-loop section so the maintainer can eyeball them.
4. **Baseline is a JSON sidecar, machine-local.** `.loops/diagnostics/fleet-review-<date>.json`
   with `{"generated": ISO-ts, "window_days": N, "loops": {name: {runs, converged, success_pct,
   top_outcome, projects}}}`. The delta is computed by loading the lexically-newest prior sidecar
   — the count-per-stable-key shape of `write_baseline()`/`regressions()` in
   `scripts/little_loops/cli/verify_private_refs.py:446-474`, keyed on loop name. `.loops/` is
   gitignored and excluded from `ll-verify-private-refs` (`_EXCLUDED_DIRS`), so the baseline is
   per-machine by design and may quote other projects' paths; the runbook's "Baseline /
   Re-measure contract" section must say this explicitly.
5. **`diagnose-evaluators` / `calibrate-budget` run in the source project, not here.** Both read
   `.loops/.history/*-<loop>/` under the *current* project's config-resolved `loops_dir`
   (`scripts/little_loops/cli/loop/info.py:1301-1380`), and `ll-loop` has no `--project` /
   `--loops-dir` flag. Run from this repo they print "No history" for any loop that only ran
   elsewhere. The runbook's DIAGNOSE step is therefore `cd <project> && ll-loop
   diagnose-evaluators <loop>`, using the `project` field of the flagged loop's records (the
   report lists them). Other projects' `.loops/.history/` is gitignored and prunable, so
   diagnose promptly after harvest. Adding `--project DIR` to those two subcommands is a
   reasonable follow-up ENH, not in scope here.
6. **Report home is `.loops/diagnostics/`, not `postmortems/`.** CLAUDE.md routes ad-hoc run
   forensics to `postmortems/`; this report is a recurring, tool-generated artifact adjacent to
   the `loop-specialist` agent's per-loop diagnostics, and both dirs are gitignored and
   private-refs-exempt. Chosen for adjacency; recorded so a reviewer doesn't re-litigate it.
7. **Pre-step: extract `loop-fleet` aggregation.** The success-rate / median-iterations /
   top-outcome math exists only in the human-table branch of `_cmd_loop_fleet`
   (`logs.py:2165-2183`). Extract it to `_aggregate_fleet_runs(runs: list[_LoopRunRecord]) ->
   list[_LoopFleetAggregate]` and have both the table branch and `fleet-review` call it, so the
   two cannot drift. Adding `--aggregate` to `loop-fleet -j` is optional.

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
- `scripts/little_loops/cli/logs.py` — **decided** (see Decisions #1): add a `fleet-review` subcommand via `subparsers.add_parser()` next to `loop-fleet`, with `_cmd_fleet_review(args, logger) -> int`; extract `_aggregate_fleet_runs()` from `_cmd_loop_fleet` first (Decisions #7). No `Makefile`/`justfile`/shell wrapper/skill (the alternatives considered: `scripts/verify_learning_citations.sh` is the only standalone-script precedent; `skills/audit-loop-run/SKILL.md` the only "chain `ll-*` calls in prose" precedent; neither is chosen).
- `.loops/diagnostics/fleet-review-<date>.md` + `.loops/diagnostics/fleet-review-<date>.json` — generated output, not source files to create by hand. `.loops/diagnostics/` already exists and holds differently-named one-off reports (`audit-interactive-component-generator-2026-06-28.md`, `vega-viz-20260702T025053Z.md`, `general-task-20260707T152654Z.md`); no file matching `fleet-review-*` exists there yet, and the directory's only established writer today is the `loop-specialist` agent itself (`agents/loop-specialist.md`), which writes directly via its own tool calls — no Python helper function writes into this directory.

_Wiring pass added by `/ll:wire-issue`:_
- ~~Conditional new top-level `ll-*` console script wiring~~ — **does not apply**: `fleet-review` is a subcommand of the existing `ll-logs` entry point, so no `pyproject.toml` `[project.scripts]`, `_LL_PERMISSIONS`, `skills/configure/areas.md`, or `ll-verify-cli-allowlist` change is needed (Decisions #1). Only the `ll-logs` subcommand table in `docs/reference/CLI.md` needs a row. [Resolved 2026-09-02]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` (holds all four HARVEST-phase subcommands) is imported by `scripts/little_loops/cli/__init__.py:75`, `scripts/little_loops/cli/ctx_stats.py:20`, `scripts/little_loops/cli/loop/_helpers.py:19`, and tested by `scripts/tests/test_ll_logs.py:16`, `scripts/tests/test_enh_3166_qwen_normalizer.py:32`, `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:31`, `scripts/tests/test_cli_ctx_stats.py:13` — none require modification for this issue; listed to confirm `logs.py`'s current consumer surface is stable and won't be disturbed by adding a new orchestrator on top of it.
- `agents/loop-specialist.md` — the agent this issue's runbook must link (per Acceptance Criteria); also asserted by `scripts/tests/test_wiring_skills_and_commands.py` to reference `.loops/diagnostics/` and `FEAT-1532`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/loop-specialist-eval.yaml` (lines 4-35, 50-56) — a separate file from `agents/loop-specialist.md` that independently encodes the same `.loops/diagnostics/<loop>-<ts>.md` naming/section convention as an eval pass/fail criterion. Its filename pattern (`<loop>-<ts>.md`, no `fleet-review-` prefix) does not collide with this issue's `fleet-review-<date>.md`, but the report writer should be aware this second file exists and shares the directory. [Agent finding]
- `scripts/little_loops/session_store/writers.py::update_loop_run_diagnostics` (lines 1556-1574) and `docs/reference/CLI.md:4723` (`ll-artifact dashboard`'s default `shareable` mode excludes `diagnostics_path`) — the existing mechanism for linking a `.loops/diagnostics/` artifact to session history is `run_id`-scoped (one `run_id` → one `diagnostics_path`). A fleet-wide report spanning many loops' runs has no single natural `run_id` to key on — this issue's report writer should NOT attempt to route through `update_loop_run_diagnostics`; it is a structural mismatch, not a missing wiring target. [Agent finding]
- `scripts/tests/test_fsm_validation_meta_rules.py::test_mr3_does_not_fire_for_diagnostics_dir` (lines 330-334) — confirms the FSM validator's MR-3 artifact-isolation rule already carves out `.loops/diagnostics/` writes generically; no FSM validator change is needed regardless of which entry-point mechanism is chosen. [Agent finding]

### Conventions in Force
- All four HARVEST-phase `ll-logs` subcommands share three argparse helpers — `add_corpus_target_args()`, `add_window_args()`, `add_json_arg()` (`scripts/little_loops/cli_args.py`) — confirming `--all`, `--window-days N`, and `-j`/`--json` exist exactly as this issue's Deliverable #2 assumes, uniformly across `loop-fleet`, `scan-failures`, `sequences`, and `dead-skills`.
- `ll-loop validate`, `diagnose-evaluators`, and `calibrate-budget` each take exactly one positional `loop` argument (`cmd_validate`, `cmd_diagnose_evaluators`, `cmd_calibrate_budget` in `scripts/little_loops/cli/loop/`) — there is no batch/glob form on the `ll-loop` side, so "run over the flagged loops" requires one invocation per flagged loop name. **`diagnose-evaluators` and `calibrate-budget` additionally read only the current project's `.loops/.history/`** (`info.py:1301-1380`) and `ll-loop` has no `--project`/`--loops-dir` flag — they must be run from inside the project that produced the runs (Decisions #5). Only `validate` (YAML-only) runs from this repo.
- `ll-logs dead-skills` enumerates the `skills/` catalog via `_aggregate_skill_stats()` (`logs.py:1039-1093`); it has **no loop coverage** and is not part of this issue's HARVEST phase.
- The only existing "diff current data against a stored baseline" mechanism in the codebase is `regressions()` / `write_baseline()` in `scripts/little_loops/cli/verify_private_refs.py:446-474`, which stores per-file **counts** in a checked-in JSON (`.ll/private-refs-baseline.json`, with an explanatory `_comment` field) and regenerates via a `--update-baseline` flag. This is a count-diff pattern over a JSON baseline, not a diff between two dated markdown reports — the closest analog found for the re-measurement contract, not a drop-in fit.
- `docs/guides/*.md` (the class this issue's runbook is meant to read differently from) share a `# Title` + `> **When to use this**:` blockquote + `## Contents` TOC shape (e.g. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:1-34`, `docs/guides/LOOPS_GUIDE.md:1-33`) — none use a labeled Purpose/Cadence/Phases header. `docs/observability/*.md` (e.g. `realized-savings-verification.md`, `des-audit.md`) is a third, already-in-use header shape (title + dated prose + results table) for one-off audit/closure reports — distinct from both `docs/guides/` and this issue's proposed runbook convention, so no doc in the repo currently uses the Purpose · Cadence · Phases · Baseline/Re-measure · In-scope header this issue proposes.

### Tests
- `scripts/tests/test_ll_logs.py` — existing coverage for the four HARVEST-phase subcommands: `test_loop_fleet_*` (~lines 4990-5345), `test_scan_failures_*` (~2989-3104), `test_sequences_*` (~785-1447), `test_dead_skills_*` (~2550-2641).
- `scripts/tests/test_cli.py` — end-to-end argv-level invocations at ~line 3005 (`scan-failures --all`), ~3047 (`dead-skills --all --sort name`), ~3084 (`loop-fleet`).
- No test file exists yet for the new entry point or report writer this issue proposes, since neither is implemented.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — add `docs/runbooks/FLEET_LOOP_REVIEW.md` to the `DOC_FILES_MUST_EXIST` list (lines 400-423, `(file_path, issue_id)` tuples) and to the `DOC_STRINGS_PRESENT` list (lines 27-336, `(doc_path, expected_string, issue_id)` tuples) with a needle proving it links `loop-specialist` and states the in-scope rule — following the exact convention already used for `("agents/loop-specialist.md", ".loops/diagnostics/", "FEAT-1532")` at line 192. No existing test asserts *ordered* section headers (Purpose · Cadence · Phases · Baseline/Re-measure · In-scope rule); every doc-wiring test in this family checks unordered substring presence only. [Agent finding]
- `scripts/tests/test_ll_logs.py` — new `test_fleet_review_*` tests following the subcommand test shape already there: a parse-only test (`test_dead_skills_subcommand_parsed`, lines 2550-2556), a `--project`/`--all` mutual-exclusion test (`test_dead_skills_project_and_all_mutually_exclusive`, lines 2623-2627), and a behavioral test patching `sys.argv`+`builtins.print` (`test_dead_skills_window_days_behavioral`, lines 2569-2621), plus a `test_cli.py` smoke test. `test_cli_entry_point_coverage` is unaffected (no new console script). Also add a unit test for the extracted `_aggregate_fleet_runs()` asserting the table branch and `fleet-review` agree on `success_pct`/`top_outcome` for the same run list.
- **Flagging-rule tests**: table-driven over synthetic `_LoopRunRecord` lists — below `--min-runs` never flags; `custom` attribution never flags; `success_pct` exactly at threshold does not flag; each of `error`/`max-steps`/`cycle` as `top_outcome` flags regardless of `success_pct`.
- **Baseline / delta tests** (this replaces the un-runnable "run the cycle twice on the live fleet" acceptance criterion): two fixture JSON sidecars in `tmp_path`, the second with one loop's `converged` count raised — assert the rendered delta table shows the positive delta for that loop, unchanged for the rest, and a "no prior baseline" line when the dir is empty. Model on `scripts/tests/test_verify_private_refs.py::TestBaseline` (count-per-stable-key; loop names don't get renamed the way issue files do, so `test_verify_evidence.py`'s hash-per-ID shape is not needed).
- ~~Conditional shell-script pytest gate~~ — does not apply (Decisions #1).

### Documentation
- `docs/reference/CLI.md` — `ll-logs` subcommand table (~lines 3459-3472), flags (~3510-3536), examples (~3599-3620): add a `fleet-review` row, its `--threshold`/`--min-runs` flags, and one example. `ll-loop validate` (~904), `diagnose-evaluators` (~1228), `calibrate-budget` (~1247) are already documented and match the implementation; the runbook links them rather than re-documenting.

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` lines 192-228 — the repo's human-facing docs index: a "Guides" table (196-213, `docs/guides/*.md`) and a "Reference" table (220-228, e.g. `CLI Reference` → `docs/reference/CLI.md`). Neither has a "runbooks" row/category; add one once `docs/runbooks/FLEET_LOOP_REVIEW.md` exists. Not test-enforced (`scripts/tests/test_readme_structure.py` only checks README stays a "hero page," not that this index matches the `docs/` tree). [Agent finding]
- `CONTRIBUTING.md:192-221` — directory-tree listing of `docs/` subdirectories (`reference/`, `guides/`, `development/`, `research/`, `claude-code/`, `codex/`, `demo/`); no `runbooks/` line exists. Add one. [Agent finding]
- `mkdocs.yml:65-100` — the `nav:` block has `Guides:`/`Reference:`/etc. sections (e.g. `guides/GETTING_STARTED.md`) but no `Runbooks:` section or `runbooks/` path; add one so the new doc surfaces in the built docs site. [Agent finding]

### Configuration
N/A — no `.ll/ll-config.json` key, `config-schema.json` entry, or `.ll.local.md` field references `fleet-review`, `fleet_loop_review`, or a `loop-fleet` output path today.

_Wiring pass added by `/ll:wire-issue`:_
- No config key. `--threshold`, `--min-runs`, and `--window-days` are CLI flags only (Decisions #2); the output dir is fixed at `.loops/diagnostics/`. (Analogs if this ever changes: `orchestration.composer`/`orchestration.cluster` in `config-schema.json:1711-1749`.) [Agent finding, narrowed 2026-09-02]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a `docs/runbooks/` entry to `CONTRIBUTING.md`'s docs directory tree (lines 192-221) and to `mkdocs.yml`'s `nav:` block (lines 65-100).
- Add a "runbooks" row/category to `README.md`'s Guides/Reference index tables (lines 192-228).
- Add `docs/runbooks/FLEET_LOOP_REVIEW.md` to `DOC_FILES_MUST_EXIST` and `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_skills_and_commands.py`, following the existing `agents/loop-specialist.md` row.
- Baseline is the JSON sidecar, count-per-loop-name (Decisions #4); test it on the `scripts/tests/test_verify_private_refs.py::TestBaseline` shape.
- Register `fleet-review` as an `ll-logs` subcommand in `logs.py` (Decisions #1) and add its row/flags/example to the `ll-logs` section of `docs/reference/CLI.md`. No new console script, no shell script.
- Extract `_aggregate_fleet_runs()` from `_cmd_loop_fleet` before writing `_cmd_fleet_review` (Decisions #7).
- Do not route the fleet-wide report through `session_store/writers.py::update_loop_run_diagnostics` — it is `run_id`-scoped and does not fit a multi-loop report (see Dependent Files above).
- The runbook's DIAGNOSE step must instruct `cd <project>` before `diagnose-evaluators`/`calibrate-budget` (Decisions #5) and link `agents/loop-specialist.md` for the fix step.

## Program Design

### Types
- `_LoopFleetAggregate` (new `@dataclass` in `logs.py`, next to `_LoopRunRecord` at `:1164`) — `loop_name: str`, `attribution: str`, `runs: int`, `converged: int`, `success_pct: int`, `median_iterations: int`, `top_outcome: str`, `projects: list[str]`. Produced by `_aggregate_fleet_runs()`; consumed by the `loop-fleet` table branch, the flagging rule, and the JSON sidecar.
- JSON sidecar `.loops/diagnostics/fleet-review-<date>.json` — `{"generated": ISO-ts, "window_days": int, "loops": {loop_name: {runs, converged, success_pct, top_outcome, projects}}}`. Read back by the next run as the baseline (Decisions #4). Not a Python type; a `dict` round-tripped through `json`.
- Report `.loops/diagnostics/fleet-review-<date>.md` sections, in order: **Summary** (window, project count, run count, prior baseline used or "none") · **Flagged loops** (table: loop, runs, success%, top outcome, projects; then per loop the `ll-loop validate` output and the `cd <project> && ll-loop diagnose-evaluators <loop>` command to run) · **Delta vs baseline** (table: loop, prior success%, current success%, Δconverged; loops absent from prior marked `new`) · **Zero-run built-ins** · **Appendix: scan-failures clusters** · **Appendix: sequences** · **Reviewed, not fixed** (empty heading for the maintainer to fill by hand).

### Signatures
- `_aggregate_fleet_runs(runs: list[_LoopRunRecord]) -> list[_LoopFleetAggregate]` — new; extracted from the table branch of `_cmd_loop_fleet` (`logs.py:2165-2183`).
- `_flag_loops(aggs: list[_LoopFleetAggregate], *, threshold: int, min_runs: int) -> list[_LoopFleetAggregate]` — new; the Decisions #2 rule, pure function so it is table-testable.
- `_load_prior_baseline(diagnostics_dir: Path) -> dict | None` / `_write_baseline(path: Path, aggs: list[_LoopFleetAggregate], *, window_days: int) -> None` — new; newest prior sidecar by lexical filename order.
- `_cmd_fleet_review(args: argparse.Namespace, logger: Logger) -> int` — new `ll-logs fleet-review [--project DIR | --all] [--window-days D | --since DATE] [--until DATE] [--threshold N=50] [--min-runs N=3] [--existing-only] [-j|--json]`; `--json` prints the sidecar dict to stdout instead of writing the markdown.
- `_cmd_loop_fleet(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/logs.py:2108`) — implements `ll-logs loop-fleet`, the HARVEST phase's core data source.
- `_cmd_scan_failures(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/logs.py:1193`) — implements `ll-logs scan-failures`.
- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` (`scripts/little_loops/cli/loop/config_cmds.py`) — single-loop, no batch form.
- `ll-logs loop-fleet [--project DIR | --all] [--loop NAME] [--window-days D | --since DATE] [--until DATE] [--existing-only] [--sort {success,name}] [--limit N] [-j|--json]` — `_cmd_loop_fleet()` (`scripts/little_loops/cli/logs.py:2108`). `--json` output is a **flat list of per-run records** — `{"loop_name","project","run_folder","final_state","iterations","outcome","ts","attribution"}` — not aggregated per loop; success-rate/median-iterations/top-outcome aggregation exists only in the human-table branch of `_cmd_loop_fleet`, not in `--json`. Any orchestrator consuming `-j` output must re-derive per-loop aggregates itself.
- `ll-logs scan-failures [--project DIR | --all] [--window-days D | --since DATE] [--until DATE] [--capture] [--capture-foreign] [--limit N] [--skill NAME] [-j|--json]` — `_cmd_scan_failures()` (`:1193`). `--json` → list of `{"tool","count","normalized_sig","sample_error","session_ids","skills"}` clusters keyed by `(cwd_path, tool_name, normalized_error_sig)` — clusters carry no loop-name field, so attributing a cluster to a specific built-in loop is not mechanical.
- `ll-logs sequences [--project DIR | --all] [--min-len N] [--min-count N] [--top N] [--window-days D | --since DATE] [--until DATE] [-j|--json]` — `_cmd_sequences()` (`:630`).
- `ll-logs dead-skills [--project DIR | --all] [--window-days D | --since DATE] [--until DATE] [--threshold N] [--sort {tier,name}] [-j|--json]` — `_cmd_dead_skills()` (`:1039`). `--json` → `{"skill","invocations","tier"}` where `tier` is `"never"` (0 invocations) or `"rarely"` (`<= --threshold`, default 3).
- `ll-loop validate <loop> [-j|--json]`, `ll-loop diagnose-evaluators <loop> [--threshold F] [--min-runs N] [-j|--json]`, `ll-loop calibrate-budget <loop> [--threshold F] [--min-runs N] [-j|--json]` — `cmd_validate`/`cmd_diagnose_evaluators`/`cmd_calibrate_budget` (`scripts/little_loops/cli/loop/config_cmds.py`, `scripts/little_loops/cli/loop/info.py`) — each takes exactly one positional `loop` (name or path); no fleet-wide/batch form exists on the `ll-loop` side.

### Call Path
`ll-logs fleet-review --all --window-days N` -> `_cmd_fleet_review` -> `discover_all_projects()` -> per project the existing `loop-fleet` collector (`_collect_loop_runs`, `logs.py:2017`) -> `_aggregate_fleet_runs()` -> `_flag_loops()` (Decisions #2) -> per flagged loop: `cmd_validate(loop, ...)` called in-process -> zero-run set = `_get_builtin_loop_names()` − seen names -> `scan-failures` / `sequences` collectors run once for the appendices -> `_load_prior_baseline()` -> render markdown + `_write_baseline()`. The runbook (not the command) then drives DIAGNOSE: `cd <project> && ll-loop diagnose-evaluators <loop>` / `calibrate-budget <loop>` (Decisions #5) -> fix via `loop-specialist` -> next `fleet-review` run shows the delta.

### Decision Rules
- **Flag** iff `attribution == "builtin"` AND `runs >= min_runs` AND (`success_pct < threshold` OR `top_outcome in {"error", "max-steps", "cycle"}`). Defaults `threshold=50`, `min_runs=3`. `success_pct` is `round(converged / runs * 100)`; `top_outcome` is `Counter(outcomes).most_common(1)`, ties broken by the existing `Counter` order (first seen). (Decisions #2)
- **Not a flagging input**: `scan-failures` clusters, `sequences`, and anything from `dead-skills`. (Decisions #3)
- **Delta**: for each loop in the current aggregates, `Δconverged = converged_now − converged_prior` and prior/current `success_pct` side by side; loops with no prior entry are marked `new`; loops in prior but absent now are listed under "dropped out of window". No prior sidecar → "no prior baseline" line, no table. (Decisions #4)
- **False positive**: no dismissal list; the maintainer records it under "Reviewed, not fixed" in the report by hand. (Decisions #2)
- **Zero-run built-in**: `_get_builtin_loop_names()` minus the set of `loop_name` values across all records, regardless of window. Listed, never flagged.

## Use Case

**Who**: A little-loops maintainer investigating why one of the shipped built-in loops keeps
stalling or failing across the projects that use it.

**Context**: They currently have to manually chain `ll-logs loop-fleet`, `scan-failures`, and
`sequences` against every other project, eyeball the output, and guess whether a fix actually
helped — with no recorded baseline to check against later.

**Goal**: Run one command (`ll-logs fleet-review --all`) to harvest fleet-wide outcomes for all
built-in loops, get a list of flagged loops with `validate` output and the exact `cd <project>
&& ll-loop diagnose-evaluators <loop>` commands to run next, fix the worst offender, then run
the same command again next cycle.

**Outcome**: The second run's dated report diffs against the first, showing the failure-count
delta for the fixed loop — proving the fix worked (or didn't) against real fleet data instead
of a self-graded claim.

## Acceptance Criteria

- `ll-logs fleet-review --all` runs end-to-end from this repo and writes a dated
  `.loops/diagnostics/fleet-review-<date>.md` with the sections listed under Program Design →
  Types (flagged loops, delta vs baseline, zero-run built-ins, appendices) plus the JSON sidecar.
- `_aggregate_fleet_runs()` is extracted and the `loop-fleet` human table is produced from it
  (existing `test_loop_fleet_*` tests still pass).
- `_flag_loops()` is a pure function with table-driven tests covering the rule's boundaries
  (below `min_runs`, `custom` attribution, `success_pct == threshold`, each terminal
  `top_outcome`).
- Two fixture sidecars in a test prove the delta table shows a positive Δconverged for the
  improved loop, unchanged for the rest, and a "no prior baseline" line on an empty dir.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` exists with the Purpose · Cadence · Phases · Baseline /
  Re-measure contract · In-scope rule header; the re-measure section states that the baseline
  is a machine-local, gitignored JSON sidecar; the DIAGNOSE phase says to `cd` into the source
  project before `diagnose-evaluators`/`calibrate-budget`; the in-scope rule is stated and
  `agents/loop-specialist.md` is linked.
- `docs/reference/CLI.md`, `README.md`, `CONTRIBUTING.md`, `mkdocs.yml`, and
  `test_wiring_skills_and_commands.py` are updated per the Wiring Phase.
- One real first-cycle run is performed on this machine and its report path is recorded in the
  Session Log. The live before/after re-measurement is **not** an acceptance criterion (it needs
  fleet re-runs between cycles); it is the runbook's steady-state use.

## Impact

- **Priority**: P3 - process/tooling improvement for maintainers, not user-facing or blocking.
- **Effort**: Medium - composes existing `ll-logs` collectors in-process (no new data source);
  the flagging rule, baseline shape, mechanism, and report layout are decided above, so the
  remaining work is the aggregation extraction, one subcommand, the runbook, and wiring.
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
- pre-implementation review - 2026-09-02 - Verified tool claims against code; corrected `dead-skills` (skills only) and `diagnose-evaluators`/`calibrate-budget` (local history only) assumptions; decided mechanism (`ll-logs fleet-review`), flagging rule, JSON baseline, report layout; replaced live-fleet AC with fixture-based tests.
- `/ll:format-issue` - 2026-09-02T19:54:35 - `972ffda4-3540-46cc-931f-997ebd4d75a3.jsonl`
- `/ll:wire-issue` - 2026-09-02T19:12:27 - `d3f3386b-13e9-4c55-8779-7f6afaf007ab.jsonl`
- `/ll:refine-issue` - 2026-09-02T19:00:54 - `ac9b1a09-d320-4fd9-96b4-3dcc47985b24.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:31 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Parented to EPIC-1918 (was unparented; assigned per /ll:create-epics-from-unparented sweep).
- `/ll:audit-issue-conflicts` - 2026-06-29T01:47:32 - `0f8f08b1-212f-4f62-9ad9-264556960322.jsonl`
