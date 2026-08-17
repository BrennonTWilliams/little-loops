---
id: ENH-3223
type: ENH
title: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality
  signal
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:29:07Z'
parent: EPIC-3217
decision_needed: true
testable: true
confidence_score: 60
outcome_confidence: 42
score_complexity: 14
score_test_coverage: 0
score_ambiguity: 10
score_change_surface: 18
---

# ENH-3223: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal

## Summary

> **Not implementation-ready.** This issue still carries `decision_needed: true`, has no `confidence_score`, no Program Design section, and an entirely `TBD` Integration Map — a different maturity tier from its EPIC siblings ENH-3224 (decided, wired, scored 95/79) and ENH-3222. Route it through `/ll:refine-issue` and `/ll:wire-issue` before implementation. The findings below narrow the decision but do not close it.

ENH-3185 shipped `harness_eval_abstention_rate()` in `scripts/little_loops/history_reader.py` (schema v41) so that "a criterion that is abstained on repeatedly becomes visible as a badly written criterion rather than disappearing into a pass/fail number". Nothing reads it. The function has no callers outside its own definition and its tests — no loop, no CLI report, no skill.

**The same is true of its older sibling.** `harness_eval_pass_rate()` (ENH-2741) is *also* unwired into any CLI, despite being documented in `docs/reference/API.md`. This reframes the issue: the Proposed Solution below assumes a place where "pass rate is already reported" that this surface can join, and **no such place exists**. Whatever surface ships here has to introduce both rates, not append abstention to an existing report. That materially enlarges the smallest viable v1.

The persistence half is done and correct (`semantic_passed = NULL` on abstention, excluded from the pass-rate denominator). The signal is recorded and unqueried.

## Current Behavior

`harness_eval_abstention_rate(target, since, ...)` returns `{scored, abstentions, abstention_rate}` or `None` when there are no scored rows. A user learns their abstention rate only by calling the Python API directly.

Meanwhile the loops that exist to diagnose harness quality — `harness-optimize`, `evaluation-quality`, `rubric-refine` — have no access to it, so a criterion the judge cannot evaluate looks the same to them as a criterion that is merely hard to satisfy.

## Expected Behavior

Abstention rate is available as a first-class signal in the two places it can act:

1. **Reporting.** An `ll-history`/`ll-logs` surface reports abstention rate alongside pass rate for a target, so a high-abstention criterion is visible without writing Python.
2. **Meta-loop diagnosis.** `harness-optimize` (and the other harness-quality loops) can gate on it — a criterion above some abstention threshold is a rewrite candidate, distinct from a criterion that fails.

The meta-loop use fits the project's own loop-authoring rules unusually well: abstention rate is a *non-LLM external evaluator* for an LLM-judged gate, which is exactly what the meta-loop design rules require every `check_semantic`/`llm_structured` state to pair with.

## Motivation

The diagnostic value claimed in ENH-3185's rationale is not yet delivered. Abstention data is accumulating in `.ll/history.db` with no path to a user or an automated consumer, so badly-written criteria stay invisible in practice even though the mechanism to see them exists.

## Proposed Solution

Start with the reporting surface, since it is a thin wrapper over an existing query and validates the data shape before anything automated depends on it. Then wire the meta-loop consumer.

Open questions for the implementer:

- ~~Which CLI does this belong to — pick by where pass rate is already reported, so the two appear together.~~ **This question rests on a false premise**: `harness_eval_pass_rate()` is not reported anywhere either (see Summary). There is no existing co-location to pick. Choose the surface on its own merits and expect to introduce both rates there.
- What threshold makes a criterion a rewrite candidate? This should be measured against real data rather than guessed; the first version may report without gating.
- `ll-harness` already distinguishes abstention in its summary and exit code (ABSTAIN = 3). Check whether that summary should also report the historical rate for the target, which would put the signal in front of the user at the moment they are looking at the criterion.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Wire the new report into `ll-harness`'s own per-run summary/exit-code output (`cli/harness.py`). This is exactly what the issue's own text names as the strongest placement ("put the signal in front of the user at the moment they are looking at the criterion") — `_evaluate_and_report()` (`cli/harness.py:580`) already distinguishes abstention via `is_abstention_verdict()` and sets `overall = "ABSTAIN"`/exit code 3; it would gain one additional call to `harness_eval_abstention_rate(target, ...)` and print/attach the historical rate alongside the current run's verdict.

**Option B**: Add a new `ll-session` subcommand mirroring the wiring pattern ENH-3211 established for a structurally similar "reader has no consumers" case (`subagent_tree`/`subagent_retries`/`subagent_budget`). Weaker analogy here: ENH-3211's functions are per-session lookups, while `harness_eval_abstention_rate`/`harness_eval_pass_rate` are per-`target` rollups — `ll-session`'s existing subcommands (`path`, `related`, `recent`) are all session-scoped, not target-scoped, so this would be a new argument shape for that CLI, not a drop-in fit.

**Option C**: Add a new subcommand under `ll-logs` telemetry or `ll-history`. No precedent exists for either module: neither currently imports `history_reader.py`'s `harness_eval_pass_rate`/`harness_eval_abstention_rate` at all, and `harness_eval_pass_rate` (the older, ENH-2741 sibling) is itself unwired into any CLI today despite being documented in `docs/reference/API.md` — so there is no existing "pass rate is already reported here" location to co-locate with, contrary to the Proposed Solution's original assumption that such a location exists.

**Recommended**: Option A for v1 — it is the smallest surface, matches the issue's own stated preference for where the signal is most actionable, and requires no new CLI-location decision. The meta-loop gating consumer (`harness-optimize` and friends) is a separate, later wiring step regardless of which reporting surface ships first, since none of those loops currently reference `harness_events`/`harness_eval_abstention_rate` at all.

#### Two blockers on Option A, found 2026-08-17

Both must be resolved during refinement; neither is fatal to Option A but both change its acceptance criteria.

**1. `target` is not written consistently, so a lookup keyed on `args.target` under-reports.** `harness_eval_abstention_rate(target, ...)` filters `harness_events WHERE target = ?` (`history_reader.py:3092-3096`), but the CLI writes three different things into that column:

- single-task paths: `target=args.target` (`cli/harness.py:738, 753, 783, 826, 867`)
- multi-task DSL paths: `target=str(path)` (`cli/harness.py:917`) and `target=task_file.name` (`cli/harness.py:940`)

So a rate computed from `args.target` inside `_evaluate_and_report()` silently excludes every DSL-path row for the same logical target. Decide during refinement whether to (a) normalize `target` at write time, (b) accept the single-task-only scope and say so in the output, or (c) key the lookup on something stabler such as `target_content_hash`/`target_path` (the ENH-141 content-pin columns, already populated).

**2. Read-before-write ordering must be pinned as an AC, not left incidental.** `_evaluate_and_report()` (`cli/harness.py:580`) runs *before* `_record_harness_event()` (`cli/harness.py:751`), so a rate read inside it naturally excludes the current run. That is the desired behavior — "abstention rate before this run" is the meaningful number — but it is currently an accident of call ordering that a future refactor could invert silently, flipping the reported figure with no test catching it. Add an explicit acceptance criterion and a regression test asserting the current run is excluded.

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Third target mismatch found during Program Design analysis (2026-08-17), not previously named in blocker 1**: inside the DSL per-task call, `_evaluate_and_report()` receives `task_args` (built at `cli/harness.py:956-965` with `target=prompt_text`) — so `args.target` *as read inside `_evaluate_and_report()`* is the raw prompt text, not `task_file.name`, the value actually written to `harness_events.target` by the subsequent `_record_harness_event(..., target=task_file.name, ...)` call (`cli/harness.py:1011`). A rate lookup keyed on `args.target` inside `_evaluate_and_report()` during a DSL per-task run would query on the wrong string entirely, not merely a differently-scoped one. See `## Program Design` → Decision Rules for the resolution: Option A's historical-rate read should key on `args.target` only for the four single-task commands, and must resolve `task_file.name` explicitly (or skip the read) for the DSL per-task path.

## Program Design

### Types
N/A — no new data type. `harness_eval_pass_rate()` already returns `float | None`
and `harness_eval_abstention_rate()` already returns `dict | None`
(`{"abstentions": int, "scored": int, "abstention_rate": float}`) — Option A
reuses both return shapes as-is (`history_reader.py:3030-3063`, `3066-3112`).

### Signatures
- `harness_eval_pass_rate(target: str, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> float | None` — `history_reader.py:3030`. `scored` denominator excludes abstained rows (`semantic_passed IS NULL`).
- `harness_eval_abstention_rate(target: str, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> dict | None` — `history_reader.py:3066`. `scored` denominator here counts pass+fail+abstain rows — a deliberately different question from `harness_eval_pass_rate`'s `scored` (documented in its own docstring).
- `_evaluate_and_report(runner_label: str, result: RunnerResult, args: argparse.Namespace, *, expected_grade: ExpectedGrade | None = None) -> tuple[int, HarnessEvalOutcome]` — `cli/harness.py:580`, the Option A integration point. No DB write occurs anywhere in this function today; its one existing DB read is `_read_prepatch_evidence(getattr(args, "issue_id", None))` at line 640, called with no `try`/`except` wrapper because it (like both `harness_eval_*` functions) uses `_connect_readonly()` internally and never raises — it logs and returns `None` on any `sqlite3.Error`. A new `harness_eval_abstention_rate()`/`harness_eval_pass_rate()` call at the same point inherits this same never-raises contract.
- Neither `harness_eval_pass_rate()` nor `harness_eval_abstention_rate()` accepts a `target_content_hash`/`target_path` parameter today — both filter only on `target = ?` (`history_reader.py:3049`, `3094`). Adding an optional hash/path-keyed filter as an alternative to `target` would require new keyword parameters on both functions plus new `AND target_path = ?` / `AND target_content_hash = ?` SQL clauses; `cmd_cmd`/`cmd_mcp` runs never populate `target_content_hash`/`target_path` (always `NULL`), so a hash/path-keyed lookup only ever matches `skill`, `prompt`, and `dsl`/`dsl-task` runner rows.

### Call Path
`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` (`cli/harness.py:731,766,794,857`) -> `_evaluate_and_report(runner_label, result, args, ...)` (`cli/harness.py:580`, called *before* the current run's row is written) -> [Option A's new call] `harness_eval_abstention_rate(target, ...)` / `harness_eval_pass_rate(target, ...)` (`history_reader.py:3066`, `3030`) -> `_connect_readonly()` (`history_reader.py:422-436`, catches `sqlite3.Error`, returns `None` on failure) -> result folded into `payload`/`status_fields` the same way `prepatch_evidence` already is (`cli/harness.py:671-672`, `684-685`) -> `print_json(payload)` / `status_block(status_fields)` (`cli/output.py`). Separately, and only after `_evaluate_and_report()` returns: `_record_harness_event(runner=..., target=..., ...)` (`cli/harness.py:751` for `cmd_skill`, mirrored at `781-790`/`824-833`/`865-875` for the other single-task commands, `1009-1021` for the DSL per-task loop) -> `record_harness_event()` (`session_store/writers.py:1024`, documented to *raise* on failure — the write side is wrapped in `contextlib.suppress(Exception)` at `cli/harness.py:124-161`, the opposite error posture from the read side).

Confirmed: because step 1 (evaluate/report) always precedes step 2 (record) within each command function — same ordering in `cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`, and the `cmd_dsl` per-task loop — a historical-rate read inside `_evaluate_and_report()` naturally excludes the current run today. This is an artifact of call order, not an enforced contract: neither `harness_eval_*` function has a `WHERE id != ?`-style exclusion, so a future refactor that reorders evaluate/record could silently flip which rows are "historical."

### Decision Rules
- **Blocker 1 resolution (target-key mismatch)**: single-task paths (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`) write `target=args.target` and are self-consistent under repeated invocation with the same skill/command/tool/prompt string — no normalization needed there. DSL paths write `target=str(path)` (aggregate row, `cli/harness.py:917`) or `target=task_file.name` (malformed/per-task rows, `940`, `1011`) — a *different granularity* (one row per task-set run vs. one row per task) by design, not a bug to fix; DSL and single-task target strings never share a string space to begin with (skill names vs. `.yaml` filenames), so there is no single logical target to unify across runner families. **A third mismatch not previously named in this issue**: inside the DSL per-task call, `_evaluate_and_report()` receives `task_args` (built at `cli/harness.py:956-965` with `target=prompt_text`), so `args.target` *as read inside `_evaluate_and_report()`* is the raw prompt text — not `task_file.name`, the value actually written to `harness_events.target` at the subsequent `_record_harness_event(..., target=task_file.name, ...)` call (`cli/harness.py:1011`). A rate lookup keyed on `args.target` inside `_evaluate_and_report()` during a DSL per-task run would therefore query on the wrong string entirely, not merely a differently-scoped one.
- **Scoping requirement**: given the above, Option A's rate lookup should key on `args.target` only for the four single-task commands (self-consistent), and either skip the historical-rate read entirely for the DSL per-task path or resolve `task_file.name` explicitly rather than reading `args.target` — the two are not interchangeable in that call path.
- **Blocker 2 resolution (read-before-write ordering)**: confirmed correct and consistent across every call site (see Call Path above) — "abstention/pass rate before this run" is the accurate label for what a read inside `_evaluate_and_report()` returns. This must be pinned as an explicit acceptance criterion plus a regression test (e.g., assert the current run's row is absent from the queried rate), since nothing today enforces the ordering beyond the accident of these functions being called in this sequence.
- Escape hatch: `harness_eval_pass_rate`/`harness_eval_abstention_rate` already return `None` on missing/locked DB or zero scored rows — Option A's new fields in `payload`/`status_fields` must handle `None` the same way `prepatch_evidence` already does (omit or display as unavailable, never raise).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `_evaluate_and_report()` (580-706) gains a new best-effort read of `harness_eval_abstention_rate()`/`harness_eval_pass_rate()`, inserted between the existing `_read_prepatch_evidence()` call (640) and the `payload`/`status_fields` construction (659+), following the exact pattern `prepatch_evidence` already uses (671-672, 684-685). The DSL per-task call site (956-965, 982-984) needs the target-key fix described in Program Design → Decision Rules before this read is added there, or the read must be skipped for that path.

### Dependent Files (Callers/Importers)
- `cmd_skill` (731), `cmd_cmd` (766), `cmd_mcp` (794), `cmd_prompt` (857), `cmd_dsl` per-task loop (879, evaluate call at 982-984) — every caller of `_evaluate_and_report()`; all pick up the new fields automatically since none currently branch on the function's return shape beyond `(rc, outcome)`.
- `scripts/little_loops/cli/output.py` — `print_json()` (~673) and `status_block()` (~683), the two existing render paths the new fields must be threaded into.

### Similar Patterns
- The existing `_read_prepatch_evidence()` call inside `_evaluate_and_report()` (line 640) is the established convention for "best-effort DB read folded into the per-run report": call directly (no `try`/`except` at the call site, because the read function itself never raises), `None`-check before adding to `payload`/`status_fields`. Option A's new call should follow this same shape rather than introducing new error handling.
- Write-side DB calls in this file follow the opposite, stricter convention: wrap in `contextlib.suppress(Exception)` (`_record_harness_event`, `cli/harness.py:124-161`) because the underlying writer is documented to raise. This convention is not relevant to Option A (a read), but matters if a future pass touches the `target=` write sites for Blocker 1.

### Tests
- `scripts/tests/test_history_reader.py` — `TestHarnessEventReaders` class (2454-2557) already covers `harness_eval_pass_rate`/`harness_eval_abstention_rate` directly; these are the only existing callers of either function today (all three are test callers: 2530, 2549, 2557 for abstention; 2454, 2470, 2479, 2485 for pass rate). No test exercises either function from inside `_evaluate_and_report()` yet — a new test class/cases in `scripts/tests/test_cli_harness.py` is needed for the wiring itself, including a regression test asserting the current run is excluded from the read (Blocker 2's AC).
- `scripts/tests/test_cli_harness.py` — existing suite for `ll-harness` CLI; the file to extend with the new wiring tests (single-task target-key case, DSL per-task target-key case, `None`-handling when history.db is empty/missing).

### Documentation
- `docs/reference/API.md` — already documents both `harness_eval_pass_rate()` and `harness_eval_abstention_rate()` as library functions; needs a note that `ll-harness` is now a consumer, once wired.
- `docs/guides/EVALUATION_GUIDE.md` — covers `ll-harness` one-shot usage and exit codes; the natural place to document the new historical-rate fields in the per-run report.

### Configuration
- N/A — no `.ll/ll-config.json` changes; this is a pure code-level wiring change.

## Implementation Steps

_Still gated — `decision_needed: true` is unresolved (Option A recommended but not
locked via `/ll:decide-issue`), so this section stops short of a route. Program
Design now pins the two blockers below; do not implement from this section until
the decision closes and `/ll:wire-issue` has run._

1. Close the `decision_needed` flag via `/ll:decide-issue` (Option A/B/C in Proposed
   Solution) — the only remaining prerequisite; blockers 1 and 2 below are now
   resolved with concrete answers in Program Design → Decision Rules.
2. Resolved by this pass — see Program Design → Decision Rules: single-task
   `target=args.target` writes are self-consistent and need no normalization; DSL
   `target=str(path)`/`target=task_file.name` are a different granularity by
   design, not a bug; the DSL per-task read path additionally must not read
   `args.target` inside `_evaluate_and_report()` (it holds `prompt_text`, not
   `task_file.name` — the value actually written to `harness_events.target`).
3. Resolved by this pass — see Program Design → Call Path: read-before-write
   ordering is confirmed consistent across every call site. The remaining work is
   only to pin it as an explicit acceptance criterion with a regression test
   (`scripts/tests/test_cli_harness.py`), not to investigate the ordering itself.
4. Run `/ll:wire-issue` after the decision closes to add integration wiring
   (callers, entry points, test hooks) on top of the Integration Map and Program
   Design this pass produced, then `/ll:confidence-check`.

## Scope Boundaries

**In scope**
- One reporting surface that exposes abstention rate (and, per the Summary finding, pass rate — since it has no existing home either)
- Resolving the `target` write inconsistency enough that the reported figure is correct or its limits are stated

**Out of scope**
- **Meta-loop gating.** Wiring `harness-optimize` / `evaluation-quality` / `rubric-refine` to consume the signal is a separate, later step — none of those loops reference `harness_events` at all today, and the threshold that makes a criterion a rewrite candidate should be measured against real data rather than guessed. v1 reports; it does not gate.
- Choosing that threshold
- Any change to the persistence half (`semantic_passed = NULL` on abstention, the pass-rate denominator) — it is already correct
- Backfilling or migrating existing `harness_events` rows

## Impact

Turns recorded-but-unread abstention data into an actionable signal for criterion quality. Additive; no change to existing pass-rate reporting, whose denominator already excludes abstentions.

## Related Key Documentation

- `docs/ARCHITECTURE.md` `## Directory Structure` history-schema table (v31
  `harness_events`, v33 `verdict_events`) — sibling live-write telemetry tables
  with the same recorded-but-unconsumed shape
- `docs/reference/API.md` `little_loops.fsm.executor` section — where
  `harness_eval_abstention_rate()`'s source data (`semantic_passed = NULL`
  on abstention) is produced

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 42/100 → LOW

### Gaps to Address
- **Program Design section is missing entirely** (`ll-issues check-design ENH-3223` exits 1; `format-check`'s `missing` list includes `Program Design`). Populate `## Program Design` with concrete types, signatures, and call path, or run `/ll:refine-issue` / `/ll:wire-issue` to produce one — this is a hard override per project policy and blocks PROCEED regardless of aggregate score.
- Integration Map is entirely `TBD` and Implementation Steps is explicitly marked as a placeholder ("Do not implement from this section").
- `decision_needed: true` is unresolved: the reporting-surface choice (Option A recommended) is not yet closed via `/ll:decide-issue`.
- Two internal blockers flagged by the issue's own research are unresolved: (1) `target` is written inconsistently across single-task vs DSL paths in `cli/harness.py`, so a rate lookup keyed on `args.target` under-reports; (2) the read-before-write ordering that makes "abstention rate before this run" correct is currently accidental and needs an explicit AC + regression test.

### Outcome Risk Factors
- Moderate-depth cross-module work: normalizing `target` writes touches multiple existing call sites in `cli/harness.py` (single-task and DSL paths) with shared state, not a single contained edit.
- No test coverage identified yet for the modified areas (Integration Map's Tests section is `TBD`).
- Several competing design decisions remain open (reporting-surface choice, target-key normalization approach, read-before-write AC) — expect judgment calls during implementation.

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-17T16:58:18 - `d113a1c4-b361-4aaf-8a68-f645d463ffc1.jsonl`
- `/ll:confidence-check` - 2026-08-17T16:17:47 - `c786d9ca-0348-4ed5-812d-bc2de7a34350.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
