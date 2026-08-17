---
id: ENH-3223
type: ENH
title: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality
  signal
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:29:07Z'
completed_at: '2026-08-17T18:33:13Z'
parent: EPIC-3217
decision_needed: false
testable: true
confidence_score: 98
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# ENH-3223: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal

## Summary

> **Scope narrowed 2026-08-17 (review pass): this ships a _target-level_ signal, not a criterion-level one.** The title's "criterion-quality" framing overstates what the data model can support. `harness_eval_abstention_rate()` keys on `harness_events.target`; the criterion is the `--semantic` prompt text, which is **never recorded** — the `semantic_prompt` column exists (`session_store/schema.py:715`) and `record_harness_event()` accepts it (`session_store/writers.py:1038`), but no caller anywhere passes it, so it is `NULL` in every row. Running the same target under two different `--semantic` criteria pools both into one rate. v1 therefore answers *"how often is this target abstained on"*, and must say so in its own output and docs. Criterion-level attribution is deliberately Out of Scope (see Scope Boundaries) and needs a separate write-side issue.

ENH-3185 shipped `harness_eval_abstention_rate()` in `scripts/little_loops/history_reader.py` (schema v41) so that "a criterion that is abstained on repeatedly becomes visible as a badly written criterion rather than disappearing into a pass/fail number". Nothing reads it. The function has no callers outside its own definition and its tests — no loop, no CLI report, no skill.

**The same is true of its older sibling.** `harness_eval_pass_rate()` (ENH-2741) is *also* unwired into any CLI, despite being documented in `docs/reference/API.md`. This reframes the issue: the Proposed Solution below assumes a place where "pass rate is already reported" that this surface can join, and **no such place exists**. Whatever surface ships here has to introduce both rates, not append abstention to an existing report. That materially enlarges the smallest viable v1.

The persistence half is done and correct (`semantic_passed = NULL` on abstention, excluded from the pass-rate denominator). The signal is recorded and unqueried.

## Current Behavior

`harness_eval_abstention_rate(target, since, ...)` returns `{scored, abstentions, abstention_rate}` or `None` when there are no scored rows. A user learns their abstention rate only by calling the Python API directly.

Meanwhile the loops that exist to diagnose harness quality — `harness-optimize`, `evaluation-quality`, `rubric-refine` — have no access to it, so a criterion the judge cannot evaluate looks the same to them as a criterion that is merely hard to satisfy.

## Expected Behavior

Abstention rate is available as a first-class signal in the two places it can act:

1. **Reporting (this issue, v1).** `ll-harness`'s own per-run output reports the historical abstention rate — and pass rate — **for the target being run**, so a repeatedly-unjudgeable target is visible without writing Python. Per the Summary, this is a target-level rollup: it identifies *which target* the judge keeps abstaining on, not *which criterion string* caused it.
2. **Meta-loop diagnosis (later, out of scope).** `harness-optimize` (and the other harness-quality loops) can gate on it — a target above some abstention threshold is a rewrite candidate, distinct from one that fails.

The meta-loop use fits the project's own loop-authoring rules unusually well: abstention rate is a *non-LLM external evaluator* for an LLM-judged gate, which is exactly what the meta-loop design rules require every `check_semantic`/`llm_structured` state to pair with.

## Motivation

The diagnostic value claimed in ENH-3185's rationale is not yet delivered. Abstention data is accumulating in `.ll/history.db` with no path to a user or an automated consumer, so a target the judge repeatedly cannot evaluate stays invisible in practice even though the mechanism to see it exists. Narrowing note (2026-08-17): ENH-3185's stated goal — attributing abstention to *a criterion* — is not reachable from the current row shape (see Summary); a target-level rate is the largest true signal available without a write-side change, and it is still enough to point a human at the target whose criteria need rewriting.

## Proposed Solution

Start with the reporting surface, since it is a thin wrapper over an existing query and validates the data shape before anything automated depends on it. Then wire the meta-loop consumer.

Open questions for the implementer:

- ~~Which CLI does this belong to — pick by where pass rate is already reported, so the two appear together.~~ **This question rests on a false premise**: `harness_eval_pass_rate()` is not reported anywhere either (see Summary). There is no existing co-location to pick. Choose the surface on its own merits and expect to introduce both rates there.
- What threshold makes a criterion a rewrite candidate? This should be measured against real data rather than guessed; the first version may report without gating.
- `ll-harness` already distinguishes abstention in its summary and exit code (ABSTAIN = 3). Check whether that summary should also report the historical rate for the target, which would put the signal in front of the user at the moment they are looking at the criterion.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Wire the new report into `ll-harness`'s own per-run summary/exit-code output (`cli/harness.py`). This is exactly what the issue's own text names as the strongest placement ("put the signal in front of the user at the moment they are looking at the criterion") — `_evaluate_and_report()` (`cli/harness.py:580`) already distinguishes abstention via `is_abstention_verdict()` and sets `overall = "ABSTAIN"`/exit code 3; it would gain one additional call to `harness_eval_abstention_rate(target, ...)` and print/attach the historical rate alongside the current run's verdict.

> **Selected:** Option A — matches the existing `_read_prepatch_evidence()` best-effort-read convention exactly (`cli/harness.py:566-577,640,671-672,684-685`) and needs no new CLI-location decision; Options B and C both require inventing new argument shapes with no complete shipped precedent to copy.

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

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-17.

**Selected**: Option A — wire the report into `ll-harness`'s own per-run output (`cli/harness.py`).

**Reasoning**: Option A reuses an already-shipped, already-tested convention (`_read_prepatch_evidence()` folded into `_evaluate_and_report()`'s `payload`/`status_fields`, `cli/harness.py:566-577,640,671-672,684-685`) with no new CLI-location decision required. Options B and C both name precedents that don't actually exist as shipped code — ENH-3211's `ll-session` wiring is itself a `blocked` open issue, and neither `ll-logs` nor `ll-history` has ever called `history_reader.py`'s target-rollup functions — so both would require assembling a new argument shape and new data-access glue from partial analogs rather than mirroring a complete pattern. Option A's own friction (the target-key mismatch across single-task vs. DSL call paths) is real but is already resolved with concrete answers in Program Design → Decision Rules below, and is not avoided by choosing B or C — it would simply be relocated.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option C | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: `_read_prepatch_evidence()` (`cli/harness.py:566-577`) is a working, directly-imitable template — same never-raises `_connect_readonly()` contract, same `None`-check-before-fold idiom, same test pattern (`test_cli_harness.py:479-538`). Friction is contained to the DSL per-task target-key resolution, already scoped in Program Design.
- Option B: cited precedent (ENH-3211's `subagent_tree`/`subagent_retries`/`subagent_budget` wiring) is unimplemented (`status: blocked`); the one real analog in `ll-session` (`skill-stats`) lacks a positional-arg convention to copy, and 13 of 14 existing subcommands are session/issue-id scoped, not target-scoped.
- Option C: neither `ll-logs` nor `ll-history` imports `harness_eval_pass_rate`/`harness_eval_abstention_rate` today; `ll-logs`'s closest rollup analog (`_aggregate_skill_stats`) bypasses `history_reader.py` entirely with hand-rolled SQL, and the `since: str` vs. `--window-days`-derived `datetime` mismatch needs new glue either way.

## Program Design

### Deviations

_2026-08-17 (implementation):_ Program Design's Signatures section states
`harness_eval_pass_rate()`/`harness_eval_abstention_rate()` "reuse both return
shapes as-is" and neither gains new parameters. Implementation kept that (no
signature changes), but two things not anticipated in Program Design were
needed:

1. **AC7's per-rate suppression needs a scored *count*, which neither function
   returns** (`harness_eval_pass_rate()` returns only `float | None`). Rather
   than adding a parameter to either function, `_read_target_history()` (new,
   `cli/harness.py`) calls the already-public `recent_harness_events()` once
   to derive both denominators (`semantic_passed is not None` /
   `semantic_verdict is not None` counts) client-side, then calls the two rate
   functions only when a denominator clears `_HISTORY_MIN_SCORED`. No new
   function or parameter in `history_reader.py`.
2. **A latent DB-path-resolution bug surfaced by testing this against a real
   isolated DB (not mocked).** `harness_eval_pass_rate(db=DEFAULT_DB_PATH)` —
   the exact call shape Program Design specifies — silently read an
   empty/wrong database whenever `LL_HISTORY_DB` (or `history.db_path`
   config) differs from the literal relative path, because
   `_connect_readonly()` discards `ensure_db()`'s resolved return and reopens
   at the original unresolved `db_path`. This pre-dates ENH-3223 and equally
   affects `_read_prepatch_evidence()` (ENH-2998) and every other
   `db=DEFAULT_DB_PATH` reader caller — it was never caught because existing
   wiring tests mock the reader wrapper rather than exercising a real
   env-var-isolated DB. Fixing `_connect_readonly()` itself to always honor
   `ensure_db()`'s resolved path was tried first and reverted: it broke
   `test_enh_3171_mcp_project_root.py`'s root-anchored `history_search`
   contract (BUG-3181), which relies on `_connect_readonly()` opening an
   already-resolved absolute path *verbatim* even though it superficially
   matches the "default-shaped" pattern re-resolution would re-derive
   (incorrectly, since re-resolution has no `root` context) from cwd.
   `_connect_readonly()` was left as originally shipped (open `db_path` as
   given); instead `_read_target_history()` resolves `DEFAULT_DB_PATH` once
   via `session_store.resolve_history_db()` (no `root=`, matching
   `_record_harness_event()`'s own write-side resolution) and passes the
   resolved absolute path to all three reader calls. This is scoped to
   ENH-3223's new code only — `_read_prepatch_evidence()`'s pre-existing
   instance of the same bug is untouched and would need its own fix.

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

_Added by review pass — 2026-08-17. Four further rules, each verified against source:_

- **Target-level, not criterion-level (scope narrowing).** The lookup key is `harness_events.target`. `semantic_prompt` — the column that would allow criterion attribution — is written by nobody: `record_harness_event()` declares the kwarg (`session_store/writers.py:1038`) and the DDL declares the column (`session_store/schema.py:715`), but `cli/harness.py::_record_harness_event()` (124-161) does not even expose it, and a repo-wide grep finds no caller passing it from any path. Every row has `semantic_prompt IS NULL`. Therefore: label the reported figures as target-scoped in both render paths and in the docs, and do **not** describe them as criterion quality. Populating `semantic_prompt` is a separate write-side issue (Out of Scope).
- **The two rates have incompatible denominators and must not share a `scored` label.** `harness_eval_pass_rate`'s denominator is `COUNT(semantic_passed)` (`history_reader.py:3046`); `cli/harness.py` writes `semantic_passed=None if outcome.abstained else outcome.passed` on **every** run, including runs with no `--semantic` flag at all (`753, 783, 826, 867`), where `outcome.passed` is purely exit-code-derived. So its denominator is *all non-abstained runs*. `harness_eval_abstention_rate`'s denominator is `COUNT(semantic_verdict)` (`history_reader.py:3091`), non-NULL only when `--semantic` was supplied — *semantically-evaluated runs only*, a strict subset. Emitting both as `scored` in one status block reads as a contradiction (e.g. `Pass 80% (10 scored) / Abstention 33% (3 scored)`). Use distinct, self-describing field names (e.g. `pass_rate_runs` vs `judged_runs`) and distinct text labels.
- **Fix the false docstring in the same change.** `harness_eval_pass_rate`'s docstring (`history_reader.py:3036-3037`) claims "Only rows with a non-NULL `semantic_passed` (the `check_semantic` verdict path, **not** the plain `exit_code`) count toward the rollup." Per the preceding rule that is untrue for every `ll-harness`-written row. This is a one-line correction, not a behavior change, and it must land here because this issue is what makes the number user-visible for the first time.
- **`since` must be pinned, not defaulted by accident.** Both functions take `since: str | None = None`, i.e. unbounded history. An unbounded rate means a target whose criteria were rewritten months ago carries its old abstention rate forever, which inverts the signal's purpose. v1 passes an explicit bounded `since` (default window; a flag may expose it) and states the window in the output rather than silently reporting all-time.
- **Suppress the figure where it is statistically meaningless.** No query filters on `runner`, only on `target` (`history_reader.py:3049`, `3094`). `cmd_prompt` writes `target=<raw prompt text>` and `cmd_cmd` writes `target=<shell command string>` — keys that in practice never repeat across runs, so those runners would report 0%/100% off a single row; two different runners sharing a target string would also collide into one rate. Require a minimum `scored` count before rendering either field (omit below it, exactly as `None` is omitted), which incidentally makes the `cmd`/`prompt` noise self-suppressing without a runner allowlist.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py:3036-3037` — correct `harness_eval_pass_rate()`'s docstring, which claims the denominator counts only `check_semantic`-path rows; `ll-harness` writes a non-NULL `semantic_passed` on every non-abstained run regardless of `--semantic` (see Program Design → Decision Rules). Docstring-only; no query change.
- `scripts/little_loops/cli/harness.py` — `_evaluate_and_report()` (580-706) gains a new best-effort read of `harness_eval_abstention_rate()`/`harness_eval_pass_rate()`, inserted between the existing `_read_prepatch_evidence()` call (640) and the `payload`/`status_fields` construction (659+), following the exact pattern `prepatch_evidence` already uses (671-672, 684-685). The DSL per-task call site (956-965, 982-984) needs the target-key fix described in Program Design → Decision Rules before this read is added there, or the read must be skipped for that path.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/harness.py:370` — the argparse epilog string documents the JSON payload shape inline (`# includes prepatch_evidence when a bundle exists`); add a parallel note for the new abstention/pass-rate fields, mirroring this existing convention [Agent finding]

### Dependent Files (Callers/Importers)
- `cmd_skill` (731), `cmd_cmd` (766), `cmd_mcp` (794), `cmd_prompt` (857), `cmd_dsl` per-task loop (879, evaluate call at 982-984) — every caller of `_evaluate_and_report()`; all pick up the new fields automatically since none currently branch on the function's return shape beyond `(rc, outcome)`.
- `scripts/little_loops/cli/output.py` — `print_json()` (~673) and `status_block()` (~683), the two existing render paths the new fields must be threaded into.

### Similar Patterns
- The existing `_read_prepatch_evidence()` call inside `_evaluate_and_report()` (line 640) is the established convention for "best-effort DB read folded into the per-run report": call directly (no `try`/`except` at the call site, because the read function itself never raises), `None`-check before adding to `payload`/`status_fields`. Option A's new call should follow this same shape rather than introducing new error handling.
- Write-side DB calls in this file follow the opposite, stricter convention: wrap in `contextlib.suppress(Exception)` (`_record_harness_event`, `cli/harness.py:124-161`) because the underlying writer is documented to raise. This convention is not relevant to Option A (a read), but matters if a future pass touches the `target=` write sites for Blocker 1.

### Tests
- `scripts/tests/test_history_reader.py` — `TestHarnessEventReaders` class (2454-2557) already covers `harness_eval_pass_rate`/`harness_eval_abstention_rate` directly; these are the only existing callers of either function today (all three are test callers: 2530, 2549, 2557 for abstention; 2454, 2470, 2479, 2485 for pass rate). No test exercises either function from inside `_evaluate_and_report()` yet — a new test class/cases in `scripts/tests/test_cli_harness.py` is needed for the wiring itself, including a regression test asserting the current run is excluded from the read (Blocker 2's AC).
- `scripts/tests/test_cli_harness.py` — existing suite for `ll-harness` CLI; the file to extend with the new wiring tests (single-task target-key case, DSL per-task target-key case, `None`-handling when history.db is empty/missing).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_harness.py` — `TestCmdCmd`'s `test_no_issue_id_omits_prepatch_evidence_key`, `test_issue_id_with_no_bundle_omits_key_not_an_error`, `test_issue_id_with_bundle_adds_additive_key` (479-538) are the exact template to mirror: patch the module-level wrapper function directly (mirroring the `little_loops.cli.harness._read_prepatch_evidence` pattern), assert absent/`None`/present cases for `payload`. No existing test covers `cmd_dsl`'s per-task path omitting `prepatch_evidence`-shaped keys — a new test is needed there, since `issue_id=None` is set explicitly in `task_args` (`cli/harness.py:956-965`) and no DSL-path test in the `cmd_dsl` test classes (~1048+) currently asserts on this. [Agent finding]

_Added by review pass — 2026-08-17:_
- `scripts/tests/test_cli_harness.py` also needs cases for the review-pass ACs beyond the `prepatch_evidence` triad: distinct-denominator field names (AC5), `since`-window exclusion of older rows (AC6), and the just-below/just-at minimum-`scored` suppression boundary (AC7). All three are assertions on the `--output json` `payload`, so they extend the same fixture rather than needing new machinery.

### Documentation
- `docs/reference/API.md` — already documents both `harness_eval_pass_rate()` and `harness_eval_abstention_rate()` as library functions; needs a note that `ll-harness` is now a consumer, once wired.
- `docs/guides/EVALUATION_GUIDE.md` — covers `ll-harness` one-shot usage and exit codes; the natural place to document the new historical-rate fields in the per-run report.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-harness` section (178-260) documents exit codes, flags, and `--output FORMAT` (`text`/`json`) but does not currently enumerate JSON payload field names; the issue's own Expected Behavior #1 ("reporting surface... visible without writing Python") makes this the natural place for user-facing discovery of the new field, and it was not previously listed here [Agent finding]

### Configuration
- N/A — no `.ll/ll-config.json` changes; this is a pure code-level wiring change.

## Acceptance Criteria

_Added by review pass — 2026-08-17. Each is independently testable; AC2/AC4/AC5/AC6 pin behavior that is currently only accidental._

1. **AC1 — the rates are reported.** For the four single-task commands (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`), `_evaluate_and_report()` reads `harness_eval_abstention_rate()` and `harness_eval_pass_rate()` for the run's target and folds the results into both render paths: additive keys in the `--output json` `payload`, and additive lines/fields in the default `status_block()` output. No existing key, field, exit code, or `HarnessEvalOutcome` field changes.
2. **AC2 — the current run is excluded (regression guard for the read-before-write ordering).** A test asserts that the rate reported for a run does not include that run's own `harness_events` row: e.g. with exactly one prior abstention and the current run also abstaining, the reported figure reflects 1 prior row, not 2. This must fail if a future refactor moves `_record_harness_event()` above `_evaluate_and_report()`.
3. **AC3 — absent, never fatal.** When `.ll/history.db` is missing, locked, or has zero matching rows, both readers return `None` and the new fields are simply omitted from `payload`/`status_fields`. The command's exit code is identical to what it would be with the fields present. Mirrors the `prepatch_evidence` absent/`None`/present test triad (`test_cli_harness.py:479-538`).
4. **AC4 — the DSL per-task path does not query on the wrong key.** In `cmd_dsl`'s per-task loop, `_evaluate_and_report()` receives `task_args` whose `target` is `prompt_text` (`cli/harness.py:956-965`), while the row is written with `target=task_file.name` (`1011`). A test asserts the per-task path either omits the new fields entirely or resolves `task_file.name` explicitly — and specifically that no lookup is issued keyed on the raw prompt text.
5. **AC5 — the two denominators are distinguishable in the output.** Pass rate and abstention rate are rendered under distinct field names and labels that do not both read as `scored`, because their denominators are different populations (all non-abstained runs vs. semantically-evaluated runs only — see Decision Rules). A test asserts the two counts appear under different keys in the JSON payload.
6. **AC6 — the window is explicit and bounded.** The read passes a non-`None` `since`, and the reported window is visible to the user (in the JSON payload and the text output). A test asserts rows older than the window are excluded from the reported figures.
7. **AC7 — meaningless rates are suppressed.** Below a minimum `scored` count, the fields are omitted rather than rendered, so single-row `cmd`/`prompt` targets do not display a 0%/100% figure. A test covers the just-below and just-at-threshold cases.
8. **AC8 — the output does not claim criterion attribution.** The rendered labels, the argparse epilog note (`cli/harness.py:370`), and the doc updates describe the figures as target-scoped. A test asserts the emitted JSON key names are target-scoped rather than criterion-scoped.
9. **AC9 — the stale docstring is corrected.** `harness_eval_pass_rate()`'s docstring (`history_reader.py:3036-3037`) no longer claims its denominator counts only `check_semantic`-path rows.
10. **AC10 — docs updated.** `docs/reference/CLI.md`'s `### ll-harness` section enumerates the new JSON payload fields (it currently enumerates none), `docs/guides/EVALUATION_GUIDE.md` documents the new per-run fields and their window, and `docs/reference/API.md` notes `ll-harness` is now a consumer of both readers.
11. **AC11 — suite green.** `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

_Ready to implement. `decision_needed` is closed (Option A, `/ll:decide-issue`
2026-08-17); Program Design and Integration Map are populated; the 2026-08-17
review pass narrowed scope to a target-level signal and added Acceptance
Criteria. Prior blockers 1-3 are resolved in Program Design → Decision Rules._

1. Correct `harness_eval_pass_rate()`'s docstring (`history_reader.py:3036-3037`) — AC9.
2. Add the best-effort read in `_evaluate_and_report()` between the existing
   `_read_prepatch_evidence()` call (640) and the `payload`/`status_fields`
   construction (659+), following that function's exact never-raises,
   `None`-check-before-fold shape. Pass an explicit bounded `since`; apply the
   minimum-`scored` suppression; use distinct field names for the two
   denominators — AC1, AC5, AC6, AC7.
3. Scope the read to the four single-task commands; for the `cmd_dsl` per-task
   path either skip it or resolve `task_file.name` explicitly — never read
   `args.target` there (it holds `prompt_text`) — AC4.
4. Add the epilog note at `cli/harness.py:370` with target-scoped wording — AC8.
5. Write the tests in `scripts/tests/test_cli_harness.py`, mirroring `TestCmdCmd`'s
   `prepatch_evidence` absent/`None`/present triad (479-538), plus the
   current-run-exclusion regression test and the new DSL-path test — AC2, AC3, AC4.
6. Update `docs/reference/CLI.md`, `docs/guides/EVALUATION_GUIDE.md`, and
   `docs/reference/API.md` — AC10.
7. Run `python -m pytest scripts/tests/` — AC11.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/harness.py:370` — add a parallel epilog note for the new abstention/pass-rate fields, mirroring the existing `# includes prepatch_evidence when a bundle exists` note
- Write `scripts/tests/test_cli_harness.py` tests mirroring `TestCmdCmd`'s `test_no_issue_id_omits_prepatch_evidence_key`/`test_issue_id_with_no_bundle_omits_key_not_an_error`/`test_issue_id_with_bundle_adds_additive_key` (479-538) for the new fields, plus a new `cmd_dsl` per-task test asserting the new keys are absent/correctly scoped (no existing DSL-path test covers this)
- Update `docs/reference/CLI.md`'s `### ll-harness` section (178-260) to document the new JSON payload fields, since it currently has no payload field enumeration at all

## Scope Boundaries

**In scope**
- One reporting surface that exposes abstention rate (and, per the Summary finding, pass rate — since it has no existing home either), scoped to `ll-harness`'s own per-run output
- Resolving the `target` write inconsistency enough that the reported figure is correct or its limits are stated
- A **target-level** signal, explicitly labeled as such in output and docs
- The one-line `harness_eval_pass_rate()` docstring correction (`history_reader.py:3036-3037`), since this issue is what first makes that number user-visible

**Out of scope**
- **Criterion-level attribution.** Populating `harness_events.semantic_prompt` (unwritten by every caller today) and adding a criterion-keyed query is a separate write-side issue — it changes the write path and needs its own migration/backfill discussion. v1 reports per target. See Summary.
- **Meta-loop gating.** Wiring `harness-optimize` / `evaluation-quality` / `rubric-refine` to consume the signal is a separate, later step — none of those loops reference `harness_events` at all today, and the threshold that makes a criterion a rewrite candidate should be measured against real data rather than guessed. v1 reports; it does not gate.
- Choosing that threshold
- Any change to the persistence half (`semantic_passed = NULL` on abstention, the pass-rate denominator) — it is already correct
- Backfilling or migrating existing `harness_events` rows

## Impact

Turns recorded-but-unread abstention data into an actionable, target-level signal: a target the judge repeatedly cannot evaluate becomes visible at the moment the user runs it, instead of accumulating unread in `.ll/history.db`. It points at the target whose criteria need rewriting; it does not name the offending criterion (see Summary). Additive — no existing key, field, or exit code changes, and no change to the persistence half.

## Related Key Documentation

- `docs/ARCHITECTURE.md` `## Directory Structure` history-schema table (v31
  `harness_events`, v33 `verdict_events`) — sibling live-write telemetry tables
  with the same recorded-but-unconsumed shape
- `docs/reference/API.md` `little_loops.fsm.executor` section — where
  `harness_eval_abstention_rate()`'s source data (`semantic_passed = NULL`
  on abstention) is produced

## Confidence Check Notes

> **The 2026-08-17T16:17 `/ll:confidence-check` verdict below is stale and retained only for history.** Every gap it lists has since been closed: `decision_needed` is `false` (Option A locked), `## Program Design` is populated (`ll-issues check-design ENH-3223` exits 0), `ll-issues format-check` reports structurally compliant, the Integration Map is no longer `TBD`, and both blockers now have concrete resolutions. Re-run `/ll:confidence-check` for a current score before implementing.

_Added by `/ll:confidence-check` on 2026-08-17 — SUPERSEDED, see note above_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 42/100 → LOW

### Gaps to Address
- ~~**Program Design section is missing entirely**~~ — closed; the section is populated and `check-design` exits 0.
- ~~Integration Map is entirely `TBD` and Implementation Steps is explicitly marked as a placeholder.~~ — closed; both are populated and Implementation Steps is now a route.
- ~~`decision_needed: true` is unresolved.~~ — closed by `/ll:decide-issue` (Option A).
- ~~Two internal blockers ... unresolved.~~ — closed in Program Design → Decision Rules; the read-before-write ordering is now pinned as AC2 with a required regression test.

### Outcome Risk Factors
_Superseded. Current residual risk after the 2026-08-17 review pass:_
- The change is contained to one best-effort read inside `_evaluate_and_report()` plus a docstring fix — narrower than the "normalizing `target` writes" scope this block assumed, since Decision Rules concluded no write-side normalization is needed.
- Remaining judgment calls are bounded and named in the ACs: the `since` window default (AC6) and the minimum-`scored` suppression threshold (AC7) are unpinned numbers. Both are display-only tuning knobs — a wrong value degrades signal quality but cannot change an exit code.

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-17T18:32:43 - `9b422899-526d-4898-abb7-ec412bd107e6.jsonl`
- `/ll:ready-issue` - 2026-08-17T18:08:18 - `e584aa15-2dbb-4ba0-9a8b-bf66ec82e3fd.jsonl`
- `/ll:confidence-check` - 2026-08-17T17:15:33 - `874f81b5-d638-4302-8b4b-3679eae19140.jsonl`
- `/ll:wire-issue` - 2026-08-17T17:12:42 - `874f81b5-d638-4302-8b4b-3679eae19140.jsonl`
- `/ll:decide-issue` - 2026-08-17T17:03:44 - `387b922e-f595-49bc-8769-737c1dde2c37.jsonl`
- `/ll:refine-issue` - 2026-08-17T16:58:18 - `d113a1c4-b361-4aaf-8a68-f645d463ffc1.jsonl`
- `/ll:confidence-check` - 2026-08-17T16:17:47 - `c786d9ca-0348-4ed5-812d-bc2de7a34350.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
