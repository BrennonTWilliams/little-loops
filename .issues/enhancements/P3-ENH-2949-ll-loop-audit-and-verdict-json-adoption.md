---
id: ENH-2949
title: ll-loop audit <run> --json and VERDICT_JSON adoption in judgment skills
type: ENH
priority: P3
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T11:20:11Z'
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2946
labels:
- cli
- loops
- observability
confidence_score: 98
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2949: `ll-loop audit` + VERDICT_JSON structured-output adoption

## Summary

Two related offloads: (a) `skills/audit-loop-run/SKILL.md` (480 lines) asks the LLM to count events and do arithmetic by hand; (b) `cli/action.py`'s `VERDICT_JSON:` / `REVIEW_JSON:` structured-output contract is only *partially* adopted — the `REVIEW_JSON` half has two emitters, the `VERDICT_JSON` half has none — so verifier telemetry still degrades to coarse exit codes.

## Current Behavior

- audit-loop-run: `ls -d .loops/.history/*-<loop>/ | sort | tail -1` run resolution (L45), `wc -l | awk` event counting (L128), "Count the number of `action_complete` events" (L210), aux-mutation tallies (L218–229), budget-utilization arithmetic (Step 5.6), fixed verdict table (Step 6b). Steps 7–9 (rubric-vs-description audit, sub-loop verdict-laundering detection, ranked improvement proposals) are genuine analysis.
- **Adoption state (verified 2026-07-31, corrects this issue's original "zero skills emit" premise):**
  - `REVIEW_JSON:` **is** emitted by `skills/audit-loop-run/SKILL.md:103,440` and `commands/audit-architecture.md:165`.
  - `VERDICT_JSON:` has **no** emitter — so `_record_verdict` falls back to exit-code-only readings for all 9 `_VERIFIER_SKILLS`.
  - The docstrings at `cli/action.py:74` and `:118` both still assert "No skill currently emits …" — **stale**, and the misinformation that produced this issue's original framing.

## Expected Behavior

- `ll-loop audit <run|--latest LOOP> --json` — resolves the run dir, computes all counters (events by type, per-state tallies, aux mutations, durations, budget utilization) and the deterministic verdict-table inputs; the skill consumes the stats blob and keeps only Steps 7–9 interpretation. **Lives under `ll-loop`, not `ll-logs`**: loop-run artifacts are in `.loops/` history dirs already read by `ll-loop history`/`audit-meta`, while `ll-logs` operates on host session logs. No new entry point (FEAT-2940 stays the epic's only one).
- At least one `_VERIFIER_SKILLS` member touched by EPIC-2938 (confidence-check is the natural first adopter, already slimmed by ENH-2946) emits a final `VERDICT_JSON: {...}` line per the `cli/action.py` contract (`verdict`, `severity_counts`, `findings_count`, `confidence`, `target_id`, `target_kind`), so `_record_verdict` stops degrading to exit codes.
- The stale docstrings at `cli/action.py:74` and `:118` are corrected to state the real adoption position (which skills emit which tag), so the next reader doesn't repeat this issue's original error.

## Proposed Solution

Counters reuse the event-stream access patterns of `ll-loop history`/`audit-meta`; contract shapes come from `output_parsing.extract_tagged_json` and `action.py`'s `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` field expectations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Closest existing precedent for the whole pattern is ENH-2943's `ll-loop cleanup`** (`scripts/little_loops/cli/loop/cleanup.py`) — a standalone module that ports a skill's manual classification/counting logic (`skills/cleanup-loops/SKILL.md` Step 3) into a `@dataclass` + `to_dict()` + `print_json` CLI command, leaving only root-cause narration in the skill. `audit_run()` should live in its own module (e.g. `scripts/little_loops/cli/loop/audit.py`), not inline in `info.py` — mirrors how `cmd_diagnose_evaluators`/`cmd_calibrate_budget` delegate to a shared `little_loops/analytics/variance.py` function rather than embedding logic in the CLI wrapper.
- **`RunAuditStats`/`StateStats` dataclass shape**: model on `scripts/little_loops/analytics/variance.py:10-49` (`EvaluatorVariance`) and `:52-72` (`VarianceReport`) — a top-level report dataclass holding `states: list[...]`, each with its own `to_dict()`, composing into the report's own `to_dict()`. Same two-level nesting the issue's `RunAuditStats.per_state: dict[str, StateStats]` needs.
- **Argparse subparser wiring**: register alongside the `cleanup`/`rename` subcommands in `scripts/little_loops/cli/loop/__init__.py:951-976` (parser) and `:1033-1034` (dispatch `elif args.command == "audit":`); add `audit` to the `known_subcommands` set (`:56-90`) so bare `ll-loop audit <run>` isn't mis-parsed as a loop-name invocation; import `cmd_audit` alongside the existing `from little_loops.cli.loop.info import (...)` lines (`:27-43`). `-j/--json` is the universal flag spelling used by every other `ll-loop` subcommand (`validate`, `list`, `history`, `audit-meta`, `cleanup`, ...).
- **Run resolution precedent**: `_list_archived_runs()` (`cli/loop/info.py:888-967`) already implements the flat `<run_id>-<loop_name>` dir convention under `HISTORY_DIR` (`fsm/persistence.py:44`), matching by `run_dir.name.endswith(f"-{loop_name}")` and sorting `reverse=True` for "latest" — exactly what `resolve_run()` needs (mirrors the SKILL.md Step 1 bash `ls -d .loops/.history/*-<loop>/ | sort | tail -1`).
- **Event/state reading precedent**: `get_archived_events()` (`fsm/persistence.py:1225+`) returns `list[dict]` from `events.jsonl` (empty list if missing); `cmd_audit_meta()` (`cli/loop/info.py:1043-1162`) shows the defensive JSONL-parsing pattern (`try/except json.JSONDecodeError: pass` per line) and the dual human/`--json` (`print_json`) output convention `audit_run()`/`cmd_audit()` should follow. `getattr(args, "json", False)` (not direct attribute access) is the established way CLI functions read the flag.
- **`VERDICT_JSON` trailer wording to add to `skills/confidence-check/SKILL.md`**: follow the exact convention already used by the two `REVIEW_JSON` emitters — `skills/audit-loop-run/SKILL.md:103-107` (refusal path) and `:440-447` (normal completion, immediately after the report block) and `commands/audit-architecture.md:165-173`. Each is a single tagged line emitted after the skill's final report section, built from fields already computed in that report — e.g. `VERDICT_JSON: {"verdict": ..., "severity_counts": {"p0": ..., "p1": ..., "p2": ..., "info": ...}, "findings_count": ..., "confidence": ..., "target_id": ..., "target_kind": "issue"}`, consumed by `_record_verdict()` (`cli/action.py:68-115`) via `extract_tagged_json(output_text, "VERDICT_JSON")`.
- **Stale docstrings to correct**: the `"""..."""` block openers at `cli/action.py:71-78` and `:121-130` both currently read "No skill currently emits a structured verdict dict at this call site..." — false per this issue's own verified-adoption-state note in Current Behavior.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/audit.py` (new) — `resolve_run()`, `audit_run()`, `RunAuditStats`/`StateStats` dataclasses, `cmd_audit()`; mirrors `scripts/little_loops/cli/loop/cleanup.py`'s standalone-module shape (ENH-2943 precedent)
- `scripts/little_loops/cli/loop/__init__.py` — subparser registration (near `cleanup_parser` at lines 951-976), dispatch `elif` branch (near line 1033-1034), import line (near lines 27-43), and `known_subcommands` set entry (lines 56-90)
- `scripts/little_loops/cli/action.py:71-78,121-130` — correct the stale `_record_verdict`/`_record_review` docstrings
- `skills/audit-loop-run/SKILL.md` — slim Steps 5.5/5.6/6a to invoke `ll-loop audit --json` instead of manual counting; keep the existing `REVIEW_JSON` emitters at lines ~103-107 and ~440-447 intact
- `skills/confidence-check/SKILL.md` — add a `VERDICT_JSON:` trailer after its final RECOMMENDATION output (per `rubric.md`'s "Output Format (single issue)" template, lines ~343-393)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/action.py:cmd_invoke()` (line 212) — calls `_record_verdict()`/`_record_review()` after every skill invocation; will start picking up structured `VERDICT_JSON` fields for `confidence-check` once emitted
- `scripts/little_loops/session_store/writers.py:record_verdict_event()` — receives the newly-populated `severity_counts`/`findings_count`/`confidence` fields instead of `None`

### Similar Patterns

- `scripts/little_loops/cli/loop/cleanup.py` — full `RunClass`/`CleanupThresholds`/`CleanupEntry` dataclass + `to_dict()` + `print_json` shape (ENH-2943)
- `scripts/little_loops/analytics/variance.py:10-72` (`EvaluatorVariance`/`VarianceReport`) — two-level dataclass nesting for report → per-item stats
- `scripts/little_loops/cli/loop/info.py:cmd_audit_meta()` (1043-1162) — defensive JSONL parsing + dual human/`--json` output convention

### Tests

- `scripts/tests/test_ll_loop_commands.py:TestCmdAuditMeta` (6229-6344) — fixture-run-dir + `argparse.Namespace` + `capsys` test template to model `TestCmdAudit` after
- `scripts/tests/test_loop_run_analytics.py:TestComputeEvaluatorVariance._make_events_jsonl()` (207-214) — `events.jsonl` fixture-writer helper, needed alongside a `meta-eval.jsonl`-style helper since `audit_run()` reads `events.jsonl`/`state.json`/`summary.json`
- `scripts/tests/test_cli_loop_cleanup.py:1028-1087` — existing `extract_tagged_json` parsing tests (tag-swap template for a `VERDICT_JSON` parsing test)
- `scripts/tests/test_confidence_check_skill.py` — phase-slice assertion convention (`_phase_text()` + `test_delegates_to_*`) to model a new `TestVerdictJsonTrailer` class asserting `"VERDICT_JSON:"` appears in the skill's output-format section
- `scripts/tests/test_action.py` — existing `_record_verdict`/`_record_review` tests; extend to assert non-exit-code-derived fields land in the DB when a `VERDICT_JSON` tag is present

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_audit_loop_run_skill.py` (883 lines) — **breaks, not just extends**: this file substring-slices `## Step 5.5:`/`## Step 5.6:`/`## Step 6:` headers out of `skills/audit-loop-run/SKILL.md` and asserts literal prose fragments (`"git check-ignore"`, `"-newermt"`, `"0.3"`, `"wc -l"`, `"--tail 0"`, `"Shallow-iteration check"`, threshold `"30"`) that live inside the exact steps this issue slims to `ll-loop audit --json` invocations. Slimming Steps 5.5/5.6/6a without updating this file's assertions will fail the suite; either rewrite the affected assertions to check for the new CLI-delegation pattern, or move the corresponding checks into `test_cli_loop_audit.py` against `audit_run()`'s actual output. [Agent 2/3 finding]
- `scripts/tests/test_ll_loop_execution.py` — needs a new `test_audit_subcommand_registered` test, mirroring the existing `test_audit_meta_subcommand_registered` (lines 1774-1785): invokes `ll-loop audit --help` under a mocked `sys.argv` and asserts `SystemExit(0)`, proving `"audit"` is in `known_subcommands` and isn't mis-parsed as a loop name. Sibling subcommands `rename`/`cleanup` (ENH-2943/ENH-2944) never got this registration test — it's not covered by `test_cli_loop_cleanup.py`/`test_cli_loop_rename.py`, which test only the pure functions. [Agent 1/3 finding]

### Documentation

- `docs/reference/API.md` — documents `extract_tagged_json`, `_record_verdict`, `_record_review`; should gain the new `ll-loop audit` entry once implemented (per the `ll-loop` bullet list convention in `.claude/CLAUDE.md`)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — the `ll-loop` bullet-list entry (in the "CLI Tools" section) enumerates `audit-meta`/`promote-baseline`/`edit-routes`/`queue list`/`queue remove` but has no `audit` mention; add a parenthetical per the file's own documented convention. [Agent 2 finding]
- `docs/reference/COMMANDS.md:854-905` (`### /ll:audit-loop-run`) — the `tail` argument description states `"default: all events; auto-scaled via wc -l on the run archive"` (line 859); goes stale once Steps 5.5/5.6/6a stop doing `wc -l` and instead shell out to `ll-loop audit --json` — update to describe the CLI-delegated mechanism. [Agent 2 finding]
- `docs/reference/CLI.md` — has an existing `#### ll-loop audit-meta` section (lines 982-995, 1138-1139) documenting the sibling subcommand's `--json` convention; add a parallel `#### ll-loop audit` section for parity. [Agent 2 finding]

## Implementation Steps

1. `ll-loop audit` + tests (fixture run dirs; counter parity with the skill's current formulas).
2. Slim `skills/audit-loop-run/SKILL.md` to invocation + Steps 7–9.
3. Add the `VERDICT_JSON` trailer to confidence-check (and any other `_VERIFIER_SKILLS` member this epic already touches); verify `ll-action invoke` records structured verdicts (test via `_record_verdict` path). `REVIEW_JSON` needs no new emitters unless a reviewer skill this epic slims lacks one — check `audit-loop-run` retains its trailer after step 2's rewrite.
4. Correct the `cli/action.py:74` / `:118` docstrings to name the actual emitters.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_audit_loop_run_skill.py`'s Step 5.5/5.6/6a substring-slice assertions alongside step 2's rewrite — do this in the same commit as the SKILL.md slimming, not as a follow-up, or the suite goes red between commits.
6. Add `test_audit_subcommand_registered` to `scripts/tests/test_ll_loop_execution.py` (mirrors `test_audit_meta_subcommand_registered`) alongside step 1's CLI wiring.
7. Update `.claude/CLAUDE.md`'s `ll-loop` bullet, `docs/reference/COMMANDS.md:854-905`, and `docs/reference/CLI.md` (new `#### ll-loop audit` section) alongside steps 1–2.

## Program Design

### Types

- `RunAuditStats: dataclass`
  - `run_id: str`
  - `loop: str`
  - `events_total: int`
  - `events_by_type: dict[str, int]`
  - `per_state: dict[str, StateStats]`
  - `aux_mutation_count: int`
  - `budget_utilization: float`
  - `verdict_inputs: dict[str, Any]`
- `StateStats: dataclass`
  - `entries: int`
  - `actions_complete: int`
  - `duration_s: float`

### Signatures

- `resolve_run(run_or_loop: str, latest: bool) -> Path` — `.loops/.history/` resolution now done via `ls | sort | tail`
- `audit_run(run_dir: Path) -> RunAuditStats` — reuses event-stream access from `ll-loop history`/`audit-meta`
- Skill-side contract: final stdout line `VERDICT_JSON: {"verdict": ..., "confidence": ..., "target_id": ..., "target_kind": ...}` / `REVIEW_JSON: {...}` per `cli/action.py` `_record_verdict`/`_record_review` field expectations (parsed by `output_parsing.extract_tagged_json`)

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `resolve_run()` -> `audit_run()`
- `ll-action` invoke path -> `extract_tagged_json()` (existing, `output_parsing.py`) — consumes the new trailers

## Scope Boundaries

- In scope: `ll-loop audit` counters + JSON; slimming audit-loop-run to Steps 7–9 **without dropping its existing `REVIEW_JSON` trailer**; the first `VERDICT_JSON` emitter (confidence-check); correcting the stale `action.py` docstrings.
- Out of scope: new entry points, `ll-logs` (host-session logs — different corpus), retrofitting the trailer to all 16 verifier/reviewer skills (follow-up if >3 skills needed).

## Impact

- **Priority**: P3 - Observability/telemetry quality; nothing else in the epic blocks on it
- **Effort**: Medium - Counters straightforward; trailer adoption spans a few skills
- **Risk**: Low - Read-only audit; trailer is additive to skill output

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] `ll-loop audit --json` reproduces every counter the skill currently computes
- [ ] audit-loop-run contains no counting/arithmetic instructions, and still emits its `REVIEW_JSON` trailer after slimming
- [ ] At least one `_VERIFIER_SKILLS` member emits `VERDICT_JSON:` and `_record_verdict` captures the structured fields (test asserts non-exit-code-derived values land in the DB)
- [ ] `cli/action.py:74` / `:118` docstrings state the real adoption position
- [ ] pytest coverage in `scripts/tests/`

## Notes

(a) and (b) are separable — split if VERDICT adoption touches more than ~3 skills. Soft-dep: land after ENH-2946 so confidence-check is already slimmed.

Review correction (2026-07-31): this issue originally claimed zero skills emit either tag. `REVIEW_JSON` had two emitters at scoping time; only the `VERDICT_JSON` half was genuinely unadopted.


## Session Log
- `/ll:manage-issue` - 2026-08-01T11:20:03 - `4527354a-84fa-4065-9e81-4e50ada09277.jsonl`
- `/ll:confidence-check` - 2026-08-01T11:08:16 - `f365cbbf-547b-49a1-98bd-918efc4d2cbe.jsonl`
- `/ll:wire-issue` - 2026-08-01T11:06:49 - `d6608647-793e-47a6-bf9c-e19ed900003e.jsonl`
- `/ll:refine-issue` - 2026-08-01T11:02:07 - `57dfdf86-2fb2-4ecc-b980-188750c9f66a.jsonl`
