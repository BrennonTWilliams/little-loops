---
id: BUG-3196
type: BUG
title: "ll-harness dsl never compares against a task's expected: values — a flagless\
  \ run reports a 100% pass rate unconditionally"
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T18:44:20Z'
---

# BUG-3196: ll-harness dsl never compares against a task's expected: values — a flagless run reports a 100% pass rate unconditionally

## Summary

`ll-harness dsl` loads each task YAML into `DslTask`, which parses an `expected:` mapping
(`harness.py:167,178`), but `cmd_dsl` never reads it. The runner builds `task.prompt`,
appends the `blanks` list, and delegates to `cmd_prompt` (`harness.py:689-703`); pass/fail is
then decided entirely by `_evaluate_and_report`, which checks only `--exit-code` and
`--semantic` (`harness.py:406-433`).

Three consequences:

1. **A DSL set run without `--semantic` reports a 100% pass rate unconditionally.** `passed`
   initializes to `True` at `harness.py:419` and no requested check can flip it, so every
   task returns rc 0 and `cmd_dsl` prints `N/N [1.00, 1.00] (95% CI)` regardless of what the
   model answered. The Wilson interval makes the null result look rigorous.

2. **Even with `--semantic`, grading is uniform across the set.** One criterion string
   applies to every task, so per-task `expected` values — the whole point of a
   fill-in-the-blank/correction task — are never checked.
   `/ll:create-eval-from-issues --dsl` generates `expected:` blocks for the tasks it emits
   and `skills/create-eval-from-issues/SKILL.md:129-141` documents `expected` as part of the
   Option B schema, so the generator and the runner disagree about the contract.

3. **The per-task telemetry row is wrong in the same loop.** `_record_harness_event(runner=
   "dsl-task", ...)` at `harness.py:706-717` hardcodes `semantic_verdict=None` — discarding
   the verdict `cmd_prompt` just computed — and writes `exit_code=rc`, the *evaluation*
   result (0/1/2), where every other runner writes the host process exit code. Historical
   queries that compare `dsl-task` rows against `prompt` rows are comparing different
   quantities. The aggregate `runner="dsl"` row (`harness.py:669`) is written before the
   loop and never updated, so it carries no outcome at all.

Fix direction: give tasks a machine-checkable answer contract, grade each task against its
own `expected` mapping, exclude tasks that no check can grade from the denominator instead of
counting them as passes, and repair the telemetry writes in the same pass.

Documented as a gotcha in `docs/guides/EVALUATION_GUIDE.md` § Gotchas — that gotcha is
removed by this fix.

## Steps to Reproduce

1. Generate a DSL task set: `/ll:create-eval-from-issues --dsl loops/<some-loop>.yaml`.
   Each emitted `evals/dsl/<name>/task-NN.yaml` carries an `expected:` mapping.
2. Run the set with no evaluator flags: `ll-harness dsl evals/dsl/<name>/`.
3. Observe `DSL pass-rate: N/N  [1.00, 1.00] (95% CI)` and exit code 0.
4. Edit any task's `expected:` values to something the model cannot possibly produce
   (e.g. `on_yes: zzz_not_a_state`) and re-run. The reported pass rate is still `N/N`.

Reproduces on any task set; there are no `evals/dsl/` fixtures checked into this repo, so
no existing green run regresses when this is fixed.

## Current Behavior

`DslTask.expected` is populated from the task YAML (`harness.py:178`) and then never
referenced again anywhere in `scripts/little_loops/cli/harness.py`. Each task is run as a
bare prompt and graded only by the flags passed to the `dsl` subcommand, which apply
identically to every task in the set. With no `--semantic` and no `--exit-code`,
`_evaluate_and_report` leaves `passed` at its `True` initializer and the run reports
`N/N  [1.00, 1.00] (95% CI)`.

Two smaller defects sit in the same code path:

- The blanks hint is built as `prompt_text += f"\n\nBlanks to fill: {task.blanks}"`
  (`harness.py:691`), which interpolates a Python list repr (`['on_yes', 'on_no']`) into the
  prompt.
- `wilson_ci` raises `ValueError("n must be positive")` on `n=0` (`stats.py:30`), so any
  code path that reaches the report with an empty denominator crashes rather than reporting.

## Expected Behavior

Each task is graded against its own `expected:` mapping. Tasks that declare `expected` ask
the model for a structured answer and are compared key-by-key, deterministically and with no
extra LLM call. `--semantic` remains available as a fallback for tasks that declare no
`expected`, and as an additional gate layered on top of the expected-match when both are
present.

A run that cannot produce a meaningful verdict says so rather than reporting a perfect
score: tasks that no check can grade are excluded from the pass-rate denominator, counted on
their own line, and make the run exit nonzero. A set in which nothing is gradable exits 2
with an explanatory message instead of crashing inside `wilson_ci`.

Per-task telemetry records the host process exit code and the real semantic verdict, and the
aggregate row carries the run's outcome.

## Root Cause

`cmd_dsl` (`harness.py:641`) was written as a thin fan-out over `cmd_prompt`, and
`cmd_prompt` (`harness.py:610`) returns only `int` — `result.stdout` never escapes its frame.
With no access to the response text, `cmd_dsl` had nothing to compare `expected` against, so
the field was parsed and dropped. Grading was left entirely to `_evaluate_and_report`, whose
`passed = True` initializer (`harness.py:419`) is a deliberate "no requested check failed"
default that is correct for a single hand-run `ll-harness cmd` invocation and wrong for a
batch runner that is supposed to derive its own per-task verdict.

## Non-Goals

- Changing `_evaluate_and_report`'s `passed = True` default for the other runners. The
  general "`ll-harness` with no flags always passes" gotcha is a separate, deliberate
  behavior and stays documented; this issue only stops `dsl` from relying on it.
- Adding fuzzy / semantic matching of `expected` values. The comparison is exact after
  normalization (below); a task that needs judgment declares no `expected` and uses
  `--semantic`.
- Retrofitting a schema validator onto task YAML files. Malformed `expected` blocks surface
  as grading failures, not as a separate lint.

## Proposed Solution

### Decision: how the model's answer is compared to `expected`

The model's response is free-form host CLI stdout; `expected` is a `{blank: value}` mapping.
Substring-searching stdout for each expected value is a false-positive machine — a `status:`
blank with `expected: open` matches almost any prose response containing the word "open".
Two options were considered:

- **(A) Structured answer contract — chosen.** When a task declares `expected`, `cmd_dsl`
  appends an instruction requiring the model to end its response with a single fenced
  ```` ```json ```` block mapping each blank name to its value. `cmd_dsl` recovers that
  object and compares it key-by-key. Deterministic, costs no extra LLM call, and produces a
  number that is actually comparable across `--model` runs — which is the stated reason the
  `dsl` runner exists.
- **(B) Per-task semantic grading — rejected.** Synthesize a `--semantic` criterion from
  `expected` and call `evaluate_llm_structured` once per task. It needs no prompt contract,
  but it costs an LLM call per task and reintroduces nondeterminism into the exact number the
  runner is trying to make trustworthy. It also cannot distinguish "the model got it wrong"
  from "the judge got it wrong", which is the failure mode the Wilson CI is supposed to
  bound.

Under (A), a response that declares `expected` but yields no parseable answer object grades
**FAIL**, not "ungradable" — the answer contract is part of the task, and treating a
malformed answer as unmeasurable would hand the model an escape hatch that inflates the rate.
It is reported in its own sub-count so a systematically unparseable set is visible as a task
authoring problem rather than a model quality problem.

### Decision: what "ungradable" means, and what it does to the exit code

A task is **ungraded** when it declares no `expected` *and* `--semantic` was not passed.

`--exit-code` deliberately does **not** make a task graded. For the `PROMPT` runner the exit
code is the host CLI's, so `--exit-code 0` asserts "the CLI did not crash", not "the model
answered correctly". Counting it as a grader would let `ll-harness dsl <dir> --exit-code 0`
restore exactly the false-100% behavior this issue removes.

Ungraded tasks are excluded from the pass-rate numerator and denominator — counting them as
passes is today's bug, and counting them as failures is equally untrue. They are reported on
a dedicated line and make the run exit `1`, because a set that silently measures only part of
itself is the same class of false confidence this issue is about. If *every* task is
ungraded, the run exits `2` (configuration error) and never calls `wilson_ci`.

### Normalization

Comparison is exact after normalizing both sides: strip surrounding whitespace, then strip
one layer of matching outer quotes or backticks. Case is significant — DSL targets are
identifiers (state names, canonical `status:` values), and the entire point of a
`status: completed → done` correction task is exactness.

Keys are taken from `expected`, not from `blanks`; `expected` is authoritative. An answer
object containing extra keys is not penalized, a missing key is a mismatch with actual
`None`.

## Program Design

### Signatures

In `scripts/little_loops/cli/harness.py`:

- `class GradeStatus(Enum)` — per-task grading outcome, placed in a banner section next to
  `DslTask`. Plain `Enum` with string values, matching `DeferReason` / `FailureType` in
  `issue_lifecycle.py`; the repo has no `StrEnum` usages.

```python
class GradeStatus(Enum):
    PASS = "pass"                # every expected key matched
    FAIL = "fail"                # answer parsed, >=1 key mismatched
    UNPARSEABLE = "unparseable"  # expected declared, no answer object recovered -> counts FAIL
    UNGRADED = "ungraded"        # no expected and no --semantic -> excluded from denominator
```

- `@dataclass(frozen=True) class ExpectedGrade` — the result of comparing one response
  against one `expected` mapping.

```python
@dataclass(frozen=True)
class ExpectedGrade:
    status: GradeStatus
    matched: dict[str, str]                          # blank -> value, keys that matched
    mismatched: dict[str, tuple[str, str | None]]    # blank -> (expected, actual or None)
    raw_answer: str | None                           # recovered JSON text, None if unparseable

    @property
    def passed(self) -> bool:
        return self.status is GradeStatus.PASS
```

- `_answer_contract_suffix(blanks: list[str], expected: dict[str, str]) -> str` — builds the
  text appended to `task.prompt`. Replaces the list-repr hint at `harness.py:691`. With
  `expected` non-empty it names the exact keys and demands a single fenced `json` object;
  with `expected` empty it emits a comma-joined blanks hint only.

- `_extract_answer_object(stdout: str) -> dict[str, str] | None` — recovers the answer.
  Tries the **last** ```` ```json ```` fenced block first, then falls back to the last
  balanced `{...}` span in the response. Returns `None` when nothing parses, when the parsed
  value is not an object, or when any value is not a scalar. Last-wins because models
  routinely restate the block after reasoning aloud.

- `_normalize_answer(value: object) -> str` — `str(value).strip()`, then strip one layer of
  matching `"` / `'` / `` ` ``.

- `_grade_expected(stdout: str, expected: dict[str, str]) -> ExpectedGrade` — pure function
  over the two inputs; no I/O, directly unit-testable.

- `_run_prompt_action(target: str, args: argparse.Namespace) -> tuple[RunnerResult, int]` —
  extracted from `cmd_prompt`'s body (`harness.py:614-623`): builds the `ActionSpec`, calls
  `run_action`, returns the result and `duration_ms`. This is the refactor that makes the
  response available to `cmd_dsl`; the issue's original claim that "the response is already
  in hand from `cmd_prompt`" was wrong — `cmd_prompt` returns `int` and discards
  `result.stdout`.

- `_evaluate_and_report(...)` (`harness.py:406`) gains one keyword-only parameter:

```python
def _evaluate_and_report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    *,
    expected_grade: ExpectedGrade | None = None,
) -> tuple[int, HarnessEvalOutcome]:
```

  When `expected_grade` is not `None` it folds `expected_grade.passed` into `passed`
  alongside the existing `--exit-code` / `--semantic` checks, adds an `Expected` row to the
  text status block, and an `"expected"` key to the JSON payload. Defaulted, so the four
  existing call sites (`cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`) are unchanged.

### Call Path

```
cmd_dsl(args)
  ├─ load task files (unchanged)
  ├─ write aggregate harness_events row -> aggregate_id  (unchanged, harness.py:665-681)
  └─ for each task_file:
       task = DslTask.from_dict(...)
       prompt_text = task.prompt + _answer_contract_suffix(task.blanks, task.expected)
       result, duration_ms = _run_prompt_action(prompt_text, task_args)
       grade = (_grade_expected(result.stdout, task.expected) if task.expected
                else ExpectedGrade(UNGRADED|None-sentinel per args.semantic))
       rc, outcome = _evaluate_and_report(label, result, task_args, expected_grade=grade)
       tally into graded_pass / graded_total / ungraded / unparseable
       _record_harness_event(runner="dsl-task",
                             exit_code=result.exit_code,      # host rc, not evaluation rc
                             semantic_verdict=outcome.verdict, # no longer hardcoded None
                             semantic_passed=outcome.passed,
                             timed_out=result.timed_out, ...)
  ├─ if graded_total == 0: print explanation, return 2   (never reaches wilson_ci)
  ├─ lo, hi = wilson_ci(graded_pass, graded_total)
  ├─ UPDATE harness_events SET exit_code=?, semantic_passed=? WHERE id=aggregate_id
  └─ return 0 if (graded_pass == graded_total and ungraded == 0) else 1
```

The aggregate-row update is a direct `UPDATE` inside the existing
`contextlib.suppress(Exception)` block, matching how `aggregate_id` is already fetched with
raw SQL at `harness.py:676-681`. Telemetry stays best-effort and never affects the exit code.

`_grade_expected` is only called when `task.expected` is non-empty; the ungraded branch
constructs an `ExpectedGrade(status=UNGRADED, ...)` only when `args.semantic is None`,
otherwise it passes `expected_grade=None` so `--semantic` alone grades the task exactly as it
does today.

### Output

```
DSL pass-rate: 12/14  [0.57, 0.94] (95% CI)
  graded 14 of 16 tasks — 2 ungradable (no `expected:` and no --semantic)
  failed: task-03.yaml (on_yes: expected 'done', got 'finish')
          task-09.yaml (unparseable answer — no JSON object in response)
```

The `graded N of M` line prints only when `ungraded > 0`; the `failed:` block prints only
when there are failures. A clean, fully graded run keeps today's single-line output.

## Acceptance Criteria

`Acceptance Criteria` is not a required BUG section in this repo (the schema scopes it to
FEAT), but this fix turns on a grading path with several independently-wrong-able edges, and
the prose Expected Behavior does not give those individual pass/fail boundaries.

1. A task whose `expected` values the model answers correctly counts as a pass; a task whose
   answer mismatches any expected key counts as a fail and the run exits `1`.
2. A task declaring `expected` whose response contains no recoverable JSON object grades
   `UNPARSEABLE`, counts toward the denominator as a **failure**, and is reported
   distinguishably from a value mismatch.
3. A task declaring no `expected`, run without `--semantic`, is excluded from both numerator
   and denominator, is reported on the `ungradable` line, and makes the run exit `1`.
4. `ll-harness dsl <dir> --exit-code 0` over a set with no `expected` does **not** mark tasks
   graded — the run still reports them ungradable and exits nonzero.
5. A set in which every task is ungradable exits `2` with an explanatory message and never
   calls `wilson_ci` (no `ValueError` escapes).
6. When a task declares `expected` **and** `--semantic` is passed, both must hold for the
   task to pass.
7. `expected` values are matched exactly after normalization: surrounding whitespace and one
   layer of matching quotes/backticks are stripped; case differences are a mismatch.
8. Keys are taken from `expected`. A missing key in the answer object is a mismatch with
   actual `None`; extra keys in the answer object do not fail the task.
9. The prompt sent for a task with blanks contains no Python list repr — `['on_yes']` does
   not appear in any generated prompt.
10. Each `dsl-task` `harness_events` row records the **host process** exit code
    (`result.exit_code`), not the evaluation rc, and records the real `semantic_verdict` when
    `--semantic` was passed.
11. The aggregate `runner="dsl"` row carries the run's outcome after the loop completes.
12. Telemetry remains best-effort: a `harness_events` write failure does not change the
    reported pass rate or the exit code.
13. `_evaluate_and_report`'s four existing call sites are behaviorally unchanged — the
    `ll-harness skill|cmd|mcp|prompt` surfaces produce identical output and exit codes.

## Integration Map

- `scripts/little_loops/cli/harness.py` — all code changes: `DslTask` neighborhood
  (`:162-181`), `_evaluate_and_report` (`:406`), `cmd_prompt` (`:610`), `cmd_dsl` (`:641`).
- `scripts/little_loops/stats.py:30` — `wilson_ci` n=0 guard is the caller's responsibility;
  no change to `stats.py`.
- `scripts/tests/test_cli_harness.py` — `TestCmdDsl` (`:963`) and `TestDslSubcommandParser`
  (`:921`) extend here.
- `skills/create-eval-from-issues/SKILL.md:129-141` — the Option B schema block. The
  generator already emits `expected`; add a note that `expected` is what grades the task and
  that a task omitting it needs `--semantic` at run time.
- `docs/guides/EVALUATION_GUIDE.md` — `:104-108` (the "read the DSL gotcha" pointer) and the
  DSL gotcha at `:409-414` must be rewritten; the sample output at `:97` gains the new lines.
- `docs/reference/CLI.md:190,209,220-221` — the `dsl` row, the dsl-specific flag block, and
  the examples need the grading semantics and the new exit-code meanings.
- `.ll/history.db` `harness_events` — row *shape* is unchanged; only the values written for
  `dsl-task` / `dsl` rows change. Pre-fix rows keep their old semantics, so any analysis
  spanning the fix boundary is mixing two definitions of `exit_code`.

## Implementation Steps

1. Add `GradeStatus`, `ExpectedGrade`, `_normalize_answer`, `_extract_answer_object`,
   `_grade_expected`, `_answer_contract_suffix` — pure functions, unit-tested first (TDD is
   on for this repo).
2. Extract `_run_prompt_action` from `cmd_prompt`; assert `cmd_prompt` behavior is unchanged.
3. Add the keyword-only `expected_grade` parameter to `_evaluate_and_report` and thread it
   into `passed`, the status block, and the JSON payload.
4. Rewrite `cmd_dsl`'s per-task loop per the call path above, including the corrected
   `_record_harness_event` arguments and the graded/ungraded tallies.
5. Add the `graded_total == 0` guard and the aggregate-row `UPDATE`.
6. Extend `TestCmdDsl` to cover acceptance criteria 1-13.
7. Update `EVALUATION_GUIDE.md` (remove the gotcha, refresh the sample output), `CLI.md`, and
   the `create-eval-from-issues` SKILL schema note.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy
   scripts/little_loops/`.

## Impact

- **Priority**: P2 - Silently produces a confidently-wrong measurement. Any decision made on
  a DSL pass rate (model comparison via `--model`, regression tracking) is unfounded, and the
  Wilson CI lends it false credibility. Not P1 only because the DSL runner is a narrow,
  opt-in surface with no `evals/dsl/` fixtures in this repo.
- **Effort**: Medium - The grading functions are small and pure, but the fix requires
  extracting the runner call out of `cmd_prompt`, threading a new parameter through
  `_evaluate_and_report` without disturbing four existing call sites, rewriting `cmd_dsl`'s
  loop, and updating three docs. Originally estimated Small on the incorrect premise that the
  response was already available to `cmd_dsl`.
- **Risk**: Low - The grading path is additive and gated on `task.expected`; `--semantic`-only
  behavior is preserved verbatim. The one behavioral change for existing users is that
  flagless runs now exit nonzero instead of reporting a false 100%, which is the point.
- **Breaking Change**: No - though previously-green DSL runs will start reporting real
  (lower) pass rates, and flagless runs over `expected`-less sets will start exiting `1`.

## Related Key Documentation

- [docs/guides/EVALUATION_GUIDE.md](../../docs/guides/EVALUATION_GUIDE.md) — § `ll-harness dsl`, § Gotchas
- [docs/reference/CLI.md](../../docs/reference/CLI.md) — `ll-harness` reference
- [skills/create-eval-from-issues/SKILL.md](../../skills/create-eval-from-issues/SKILL.md) — Option B task schema

## Status

**Open** | Created: 2026-08-15 | Priority: P2
