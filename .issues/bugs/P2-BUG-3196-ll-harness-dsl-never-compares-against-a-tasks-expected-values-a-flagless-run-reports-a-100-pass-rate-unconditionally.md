---
id: BUG-3196
type: BUG
title: "ll-harness dsl never compares against a task's expected: values \u2014 a flagless\
  \ run reports a 100% pass rate unconditionally"
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T18:44:20Z'
decision_needed: false
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
reconcile_attempted: true
---

# BUG-3196: ll-harness dsl never compares against a task's expected: values — a flagless run reports a 100% pass rate unconditionally

## Baseline — REBASE REQUIRED (blocked_by ENH-3185)

**This issue was written against a pre-ENH-3185 `harness.py`. Do not implement it against
those line numbers or those assumptions.** ENH-3185 (abstention verdicts) committed as
`dea24aac` and rewrote both functions this issue touches. All line references below are
given against the **post-ENH-3185** file (verified against `dea24aac`).

What ENH-3185 already changed, and what it means here:

- `_evaluate_and_report` is at `:409` (was `:406`); the `passed = True` initializer is at
  `:422` (was `:419`); `cmd_dsl` is at `:665` (was `:641`); the per-task loop is at
  `:709-750` (was `:689-703`); `_record_harness_event(runner="dsl-task", ...)` is at
  `:739-750` (was `:706-717`).
- `_evaluate_and_report` now returns `tuple[int, HarnessEvalOutcome]` where
  `HarnessEvalOutcome` carries an **`abstained: bool`** field (`:392`), and it returns a
  fourth exit code: `0` pass, `1` fail, `2` harness/infra error, **`3` inconclusive** (no
  failure, ≥1 abstention). Precedence is **fail > abstain > pass** (`:444-503`).
- `cmd_dsl` already tracks `abstain_count`, already excludes abstained tasks from the Wilson
  denominator (`ci_total = total - abstain_count`, `:753`), and **already guards `n=0`**:
  `if ci_total > 0:` … `else: print("DSL pass-rate: n/a (all N task(s) abstained)"); return 3`
  (`:755-761`).
- `semantic_passed` in the `dsl-task` telemetry row is already abstain-aware
  (`None if rc == 3 else rc == 0`, `:744`).

The `blocked_by: [ENH-3185]` frontmatter edge was **removed 2026-08-16** — ENH-3185 is
`done`, but the unresolved edge still rendered as "Blocked by: ENH-3185" in
`ll-issues show` and risked scheduling tools skipping the issue.

Consequences for this issue's scope, resolved below rather than left to the implementer:
the `wilson_ci` n=0 crash is **already fixed** (Current Behavior corrected), the "ungraded"
concept must be reconciled against ENH-3185's abstention bucket (see **Decision: exit codes**),
and grading must state its precedence against abstention (AC6).

## Summary

`ll-harness dsl` loads each task YAML into `DslTask`, which parses an `expected:` mapping
(`harness.py:163-181`), but `cmd_dsl` never reads it. The runner builds `task.prompt`,
appends the `blanks` list, and delegates to `cmd_prompt` (`harness.py:712-728`); pass/fail is
then decided entirely by `_evaluate_and_report`, which checks only `--exit-code` and
`--semantic` (`harness.py:409-441`).

Three consequences:

1. **A DSL set run without `--semantic` reports a 100% pass rate unconditionally.** `passed`
   initializes to `True` at `harness.py:422` and no requested check can flip it, so every
   task returns rc 0 and `cmd_dsl` prints `N/N [1.00, 1.00] (95% CI)` regardless of what the
   model answered. The Wilson interval makes the null result look rigorous. (ENH-3185's
   abstention path cannot fire here either: with no `--semantic` there is no verdict to
   abstain, so `abstain_count` stays 0 and every task lands in `pass_count`.)

2. **Even with `--semantic`, grading is uniform across the set.** One criterion string
   applies to every task, so per-task `expected` values — the whole point of a
   fill-in-the-blank/correction task — are never checked.
   `/ll:create-eval-from-issues --dsl` generates `expected:` blocks for the tasks it emits
   and `skills/create-eval-from-issues/SKILL.md:129-141` documents `expected` as part of the
   Option B schema, so the generator and the runner disagree about the contract.

3. **The per-task telemetry row is wrong in the same loop.** `_record_harness_event(runner=
   "dsl-task", ...)` at `harness.py:739-750` hardcodes `semantic_verdict=None` (`:743`) —
   discarding the verdict `cmd_prompt` just computed — and writes `exit_code=rc` (`:742`),
   the *evaluation* result (now 0/1/2/3 post-ENH-3185), where every other runner writes the
   host process exit code. Historical queries that compare `dsl-task` rows against `prompt`
   rows are comparing different quantities. The aggregate `runner="dsl"` row
   (`harness.py:691`) is written before the loop and never updated, so it carries no outcome
   at all.

   Scope note: `semantic_passed` on this row is **not** part of the defect — ENH-3185 already
   made it abstain-aware (`None if rc == 3 else rc == 0`, `:744`). Only `semantic_verdict` and
   `exit_code` are wrong, and the fix must preserve the abstain-aware `semantic_passed`
   semantics rather than reverting them to a plain `outcome.passed`.

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

One smaller defect sits in the same code path:

- The blanks hint is built as `prompt_text += f"\n\nBlanks to fill: {task.blanks}"`
  (`harness.py:716`), which interpolates a Python list repr (`['on_yes', 'on_no']`) into the
  prompt.

**Corrected 2026-08-16 (post-ENH-3185).** An earlier draft listed a second smaller defect:
that `wilson_ci` raises `ValueError("n must be positive")` on `n=0` (`stats.py:30`) and so
any path reaching the report with an empty denominator crashes. **That is no longer true.**
ENH-3185 added the `if ci_total > 0:` guard at `harness.py:755`, with an `else` branch that
prints `DSL pass-rate: n/a (all N task(s) abstained)` and returns `3`. `stats.py` is
unchanged and still raises on `n=0` — the guard is the caller's, exactly as this issue's
Integration Map says — but the crash is already unreachable from `cmd_dsl`. The remaining
work is to extend that existing guard to cover the *ungraded* denominator-emptying case, not
to add a guard that already exists.

## Expected Behavior

Each task is graded against its own `expected:` mapping. Tasks that declare `expected` ask
the model for a structured answer and are compared key-by-key, deterministically and with no
extra LLM call. `--semantic` remains available as a fallback for tasks that declare no
`expected`, and as an additional gate layered on top of the expected-match when both are
present.

A run that cannot produce a meaningful verdict says so rather than reporting a perfect
score: tasks that no check can grade are excluded from the pass-rate denominator, counted on
their own line, and make the run exit nonzero. A set in which nothing is gradable exits 2
with an explanatory message, reusing the existing empty-denominator guard rather than
reaching `wilson_ci`.

Ungraded and abstained are **distinct** buckets that happen to share the "excluded from the
denominator" treatment — see **Decision: exit codes** for why they get different exit codes
and how they interact.

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

  **Qualified 2026-08-16.** That statement only holds once the task file *parses*, which it
  is not guaranteed to do today — see **Decision: a malformed task file must not kill the
  run**. Making a malformed task grade FAIL-and-continue is in scope; a standalone schema
  lint is not.

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

### Decision: exit codes — how "ungraded" relates to ENH-3185's "abstained"

ENH-3185 introduced exit `3` ("inconclusive": no failure, ≥1 abstention) and an
`abstain_count` bucket that is already excluded from the Wilson denominator. "Ungraded"
shares that exclusion, which raises the obvious question: is it just a second name for the
same thing, and should it exit `3` too?

**No — they stay distinct, and ungraded keeps the exit `1` / all-ungraded exit `2` behavior
specified above.** The discriminator is *who can fix it*:

- **Abstained** is a legitimate runtime outcome. A grader ran and honestly reported that it
  could not decide. Re-running may produce a verdict; nothing about the invocation is wrong.
  Exit `3`, "inconclusive".
- **Ungraded** is an operator configuration defect. No grader ran at all, because the task
  declares no `expected` and no `--semantic` was passed. Re-running changes nothing; the
  invocation itself is under-specified. That is the same class as exit `2`'s existing
  meaning, and it is precisely the false-confidence failure this issue exists to remove — so
  it must not be reportable as a soft "inconclusive".

Concretely, `cmd_dsl` maintains **four** exclusion-worthy counters — `ungraded_count`,
`abstain_count`, `errored_count` (see the next Decision), `unparseable_count` (the last
counts as a failure and stays *in* the denominator) — and resolves the run's exit code by
this precedence, highest first:

| Condition | Exit | Notes |
|---|---|---|
| every task ungraded | `2` | configuration error; never calls `wilson_ci` |
| ≥1 infra-errored task (per-task rc `2`) | `2` | next Decision; never a model-quality signal |
| ≥1 graded failure (mismatch or unparseable) | `1` | |
| ≥1 ungraded task | `1` | partial measurement is not a pass |
| ≥1 abstention, no failure, no ungraded | `3` | **behavior change — see below** |
| all graded, all passed | `0` | |

### Decision: a per-task infra error (rc `2`) is excluded from the denominator

**Gap found 2026-08-16, pre-implementation review.** Earlier drafts enumerated
`pass / fail / ungraded / abstain / unparseable` and never said where a task whose *host
CLI* failed goes. There is a fifth outcome and it is reachable today:
`_evaluate_and_report` returns `2` from two guards that fire **before** any grading runs
(`harness.py:415-419`):

```python
if result.timed_out:  ... return 2, HarnessEvalOutcome(passed=False, ...)
if result.error is not None: ... return 2, HarnessEvalOutcome(passed=False, ...)
```

Today `cmd_dsl` handles only `rc == 0` and `rc == 3` (`harness.py:733-738`), so an rc `2`
task increments neither `pass_count` nor `abstain_count` while still incrementing `total`
— it lands in the Wilson denominator as a **failure**. A host CLI timeout is therefore
scored as a wrong model answer. That is the same class of confidently-wrong measurement
this issue exists to remove, so it is fixed here rather than left as a separate issue.

**Rule.** A per-task rc `2` increments `errored_count`, is excluded from **both** the
numerator and the denominator (like `ungraded` and `abstained`), is reported on its own
line, and makes the run exit `2`. Rationale for the exit code: an infra error is neither
a model failure (`1`) nor an honest non-verdict (`3`); it is the same "this run did not
measure what you asked" class as the all-ungraded case, and `_evaluate_and_report`
already spends `2` on exactly this meaning at the per-task level. Propagating it keeps
one definition of `2` across both levels.

**`2` is already overloaded at the run level and that stays true.** `cmd_dsl` returns `2`
today for a missing path (`harness.py:675`) and for an empty task directory (`:679`).
Adding all-ungraded and any-errored to that set is consistent — every `2` means "the run
could not produce a measurement" — but the meanings must be enumerated together in
`CLI.md` rather than accreting silently. See Integration Map.

**Correction 2026-08-16: the partial-abstention row is a behavior CHANGE, not a
preservation.** An earlier draft annotated it "ENH-3185 behavior, preserved verbatim." That
is wrong, and the wrong version would have shipped an unannounced exit-code flip. Verified
against `dea24aac`: `cmd_dsl`'s final statement is

```python
return 0 if pass_count == ci_total else 1          # harness.py:763
```

so **today a run with ≥1 abstention and no failure returns `0`**, not `3`. ENH-3185's `3`
fires only from the *all*-abstained early return at `:762` (`ci_total == 0`). The
partial-abstention case has never returned `3`.

Adopting the table above is still the right call — an aggregate run that could not grade
some of its tasks should not report a clean `0`, which is the same false-confidence class
this whole issue exists to remove. But it must be stated and tested as a deliberate `0 → 3`
flip, not smuggled in as preservation. See AC5c.

Only the *all*-abstained case is genuinely preserved verbatim (`ci_total == 0` → message
containing "abstained" → `3`). The new all-ungraded case is a separate branch returning `2`.
A set that is entirely a mix of abstained and ungraded tasks hits the all-ungraded branch
only if `ungraded_count == total`; otherwise it falls through to the `≥1 ungraded → 1` row.

### Decision: a malformed task file must not kill the run

**Gap found 2026-08-16, pre-implementation review.** `cmd_dsl`'s per-task loop opens and
parses each file with no guard (`harness.py:709-712`), and `DslTask.from_dict` indexes
`data["prompt"]` unconditionally (`harness.py:175`). So any of these raises out of the
loop and aborts the **whole set** with a traceback, before the aggregate `harness_events`
row is ever updated:

- unparseable YAML → `yaml.YAMLError`
- a task file with no `prompt:` key → `KeyError`
- a top-level scalar/list instead of a mapping → `TypeError`

There is a second, quieter case that reaches the new grading path rather than the loader:
`expected` is typed `dict[str, str]` but populated by a bare `data.get("expected") or {}`
(`harness.py:178`), so `expected: [a, b]` or `expected: somestring` yields a list/str that
`_grade_expected` will iterate wrongly or raise on.

**Rule.** Wrap per-task load in a `_load_task(path) -> DslTask | None` helper. On any
load/shape error it returns `None`; the task grades **FAIL**, is counted in the
denominator, is reported distinguishably (`malformed task file`), and the loop
**continues** to the next file. `_grade_expected` additionally treats a non-mapping
`expected` as a malformed task rather than raising. This is the same reasoning as the
`UNPARSEABLE` answer decision: a task the runner cannot grade because of how it was
authored must be visible as a task-authoring failure, never as a crash and never as a
silent skip.

### Normalization

Comparison is exact after normalizing both sides: strip surrounding whitespace, then strip
one layer of matching outer quotes or backticks. Case is significant — DSL targets are
identifiers (state names, canonical `status:` values), and the entire point of a
`status: completed → done` correction task is exactness.

**"Both sides" means both sides literally — `_normalize_answer` is applied to the `expected`
value as well as to the model's answer.** `DslTask.expected` is *annotated* `dict[str, str]`
but nothing coerces it: `from_dict` does a bare `data.get("expected") or {}` (`harness.py:178`)
over whatever `yaml.safe_load` produced. So the declared type lies for any non-string scalar:

- `expected: {retries: 3}` → Python `int` `3`, which `== "3"` is `False`
- `expected: {enabled: true}` → Python `True` → `str(True)` is `"True"`, which under the
  case-significance rule above mismatches a model that correctly answers `true`
- `expected: {value: null}` → Python `None` → `"None"`, colliding with the sentinel used for
  a missing key

Normalizing the expected side through the same `_normalize_answer(value: object)` resolves
the first and third; the boolean case needs one explicit carve-out, because YAML's `true` and
JSON's `true` are the same value with different Python reprs. `_normalize_answer` therefore
lower-cases `bool` inputs specifically (`True → "true"`), before the generic
`str(value).strip()` path. This is the one documented exception to case significance and it
is a *representation* fix, not a fuzzy match — it does not soften the exactness rule for
identifier-valued blanks.

A task author who wants a literal `"True"` string compared case-sensitively quotes it in the
YAML (`expected: {value: "True"}`), which `safe_load` yields as `str` and the bool carve-out
never sees.

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
    MALFORMED = "malformed"      # task file unloadable / expected not a mapping -> counts FAIL
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
  text appended to `task.prompt`. Replaces the list-repr hint at `harness.py:716`. With
  `expected` non-empty it names the exact keys and demands a single fenced `json` object;
  with `expected` empty it emits a comma-joined blanks hint only.

- `_extract_answer_object(stdout: str) -> dict[str, str] | None` — recovers the answer.
  Tries the **last** ```` ```json ```` fenced block first, then falls back to the last
  balanced `{...}` span in the response. Returns `None` when nothing parses, when the parsed
  value is not an object, or when any value is not a scalar. Last-wins because models
  routinely restate the block after reasoning aloud.

- `_normalize_answer(value: object) -> str` — `"true"`/`"false"` for `bool` inputs (the
  carve-out under Normalization), otherwise `str(value).strip()`, then strip one layer of
  matching `"` / `'` / `` ` ``. Applied to **both** the expected value and the model's
  answer.

- `_grade_expected(stdout: str, expected: dict[str, str]) -> ExpectedGrade` — pure function
  over the two inputs; no I/O, directly unit-testable. A non-mapping `expected` returns
  `GradeStatus.MALFORMED` rather than raising (see § Decision: a malformed task file).

- `_load_task(path: Path) -> DslTask | None` — parses one task YAML, returning `None` on
  `yaml.YAMLError`, a missing `prompt:` key, or a non-mapping document. Exists so a single
  bad file grades FAIL instead of aborting the set with a traceback.

- `_run_prompt_action(target: str, args: argparse.Namespace) -> tuple[RunnerResult, int]` —
  extracted from `cmd_prompt`'s body (`harness.py:638-647`): builds the `ActionSpec`, calls
  `run_action`, returns the result and `duration_ms`. This is the refactor that makes the
  response available to `cmd_dsl`; the issue's original claim that "the response is already
  in hand from `cmd_prompt`" was wrong — `cmd_prompt` returns `int` and discards
  `result.stdout`.

- `_evaluate_and_report(...)` (`harness.py:409`) gains one keyword-only parameter:

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

  **Interaction with ENH-3185's abstention (`:444-503`).** `_evaluate_and_report` computes
  `passed`, `abstained`, an `overall` label, and an exit code under the precedence
  `fail > abstain > pass`. An `expected` mismatch is a **hard failure** and enters at the
  `passed = False` level, so it outranks abstention exactly the way an `--exit-code`
  mismatch already does. Threading is therefore a single line next to the existing
  `args.exit_code` check — `if expected_grade is not None and not expected_grade.passed:
  passed = False` — placed **before** the `args.semantic` block so a mismatch is recorded
  regardless of what the judge later says. No change to the `abstained` computation, the
  `overall` ladder, or the returned exit-code ladder.

  The resulting per-task truth table (`expected` declared **and** `--semantic` passed):

  | expected | semantic | task `overall` | task rc | pass-rate bucket |
  |---|---|---|---|---|
  | match | `yes` | PASS | `0` | numerator + denominator |
  | match | abstain | ABSTAIN | `3` | excluded (abstained) |
  | match | not-`yes` | FAIL | `1` | denominator only |
  | mismatch / unparseable | `yes` | FAIL | `1` | denominator only |
  | mismatch / unparseable | abstain | FAIL | `1` | denominator only |
  | mismatch / unparseable | not-`yes` | FAIL | `1` | denominator only |

  Note row 5: a task whose answer is objectively wrong is a failure even when the judge
  abstains. Abstention means "the judge could not decide", not "the deterministic check is
  void" — letting it mask a known mismatch would reopen a narrower version of this bug.

### Call Path

```
cmd_dsl(args)
  ├─ load task files (unchanged)
  ├─ write aggregate harness_events row -> aggregate_id  (unchanged, harness.py:687-707)
  └─ for each task_file:
       task = _load_task(task_file)          # returns None on malformed YAML -> FAIL, continue
       prompt_text = task.prompt + _answer_contract_suffix(task.blanks, task.expected)
       result, duration_ms = _run_prompt_action(prompt_text, task_args)
       grade = (_grade_expected(result.stdout, task.expected) if task.expected
                else ExpectedGrade(UNGRADED|None-sentinel per args.semantic))
       rc, outcome = _evaluate_and_report(label, result, task_args, expected_grade=grade)
       tally into graded_pass / graded_total / ungraded_count
                 / abstain_count (ENH-3185, rc == 3) / errored_count (rc == 2)
                 / unparseable_count
       _record_harness_event(runner="dsl-task",
                             exit_code=result.exit_code,      # host rc, not evaluation rc
                             semantic_verdict=outcome.verdict, # no longer hardcoded None
                             semantic_passed=None if outcome.abstained else outcome.passed,
                             timed_out=result.timed_out, ...)
  ├─ if ungraded_count == total: print explanation, return 2   (never reaches wilson_ci)
  ├─ if graded_total == 0:      # nothing left to put in a denominator
  │    if errored_count > 0: print "n/a (N task(s) errored)"; return 2
  │    print "DSL pass-rate: n/a (all N task(s) abstained)"; return 3  # ENH-3185's branch
  ├─ lo, hi = wilson_ci(graded_pass, graded_total)
  ├─ UPDATE harness_events SET exit_code=?, semantic_passed=? WHERE id=aggregate_id
  └─ resolve exit code per the Decision: exit codes table
     (errored_count > 0 -> 2, failure -> 1, ungraded_count > 0 -> 1,
      abstain_count > 0 -> 3, else 0)
```

`graded_total` counts tasks that a check actually adjudicated: it excludes
`ungraded_count`, `abstain_count`, and `errored_count`, and includes `unparseable_count`
(which grades FAIL).
The empty-denominator branches are ordered ungraded-first, then errored, then abstained,
so that a wholly mis-configured or wholly-broken run reports the actionable `2` rather
than the softer `3`. Keep the word "abstained" in the abstain branch's message —
`test_cmd_dsl_all_abstain_excludes_from_ci_and_exits_3` (`test_cli_harness.py:1085-1103`)
asserts `"abstained" in out` (substring, not the full string); the errored branch must
therefore **not** reuse that word, or a set that wholly errored would satisfy the
abstention test's assertion.

### Hazard: `_extract_answer_object`'s bare-brace fallback can capture a non-answer object

The fallback "last balanced `{...}` span" will happily match **any** JSON object in stdout,
including one that has nothing to do with the answer contract. This is not hypothetical: when
`--semantic` is passed, `evaluate_llm_structured` output and judge payloads are themselves
JSON objects, and the existing test at `test_cli_harness.py:1085` drives `cmd_dsl` with
stdout that is exactly an LLM verdict object (`_llm_verdict("cannot_judge")`). A naive
last-brace fallback parses that verdict payload as the answer, finds no `on_yes` key, and
reports a confident *mismatch* — swapping this bug's false pass for a false fail.

Constrain the fallback: a bare-brace candidate is accepted **only if its key set intersects
`expected`'s key set**; otherwise it is discarded and the task grades `UNPARSEABLE`. The
fenced ```` ```json ```` block is accepted unconditionally (an explicit answer block is the
contract being honoured). Add this as an acceptance criterion — see AC2b.

The aggregate-row update is a direct `UPDATE` inside the existing
`contextlib.suppress(Exception)` block, matching how `aggregate_id` is already fetched with
raw SQL at `harness.py:700-706`. Telemetry stays best-effort and never affects the exit code.

**Citation corrected 2026-08-16.** An earlier draft cited `:676-681` for that raw-SQL fetch;
those lines are the two exit-`2` error returns, not the `aggregate_id` lookup. Verified against
the current file: the error returns are at `:675` (path not found) and `:679` (empty directory),
and the `SELECT id FROM harness_events ORDER BY id DESC LIMIT 1` fetch is at `:700-706`, inside
the existing `contextlib.suppress(Exception)` block.

### Consequence: the per-task `runner="prompt"` telemetry rows disappear

Today `cmd_dsl` delegates to `cmd_prompt`, and `cmd_prompt` writes its own
`_record_harness_event(runner="prompt", ...)` row (`harness.py:650-661`) before returning.
So **every DSL task currently writes two `harness_events` rows** — one `prompt`, one
`dsl-task` — and the `prompt` row is the one that already carries the correct host
`exit_code` and real `semantic_verdict` (which is why the `dsl-task` row's hardcoded
`semantic_verdict=None` went unnoticed).

Replacing `cmd_prompt(task_args)` with `_run_prompt_action(...)` + `_evaluate_and_report(...)`
in the call path above **removes those `prompt` rows**, because `_run_prompt_action` is
extracted from `:638-647` only and does not include the `_record_harness_event` call at
`:650-661`.

That is the intended outcome — one row per task, correctly populated, instead of two rows
with overlapping and partly-wrong fields — but it is a deliberate telemetry change and is
recorded here rather than discovered at review. Consequences:

- Any historical query counting `runner = 'prompt'` rows changes meaning at the fix
  boundary: pre-fix it includes one row per DSL task, post-fix it does not.
- The `dsl-task` row becomes the *sole* per-task record, which raises the stakes on AC10 —
  if `exit_code`/`semantic_verdict` are not corrected there, the fix loses information
  rather than de-duplicating it. AC10 and this change must land together.

Do **not** preserve the `prompt` rows by having `_run_prompt_action` write them; that would
keep the duplication and reintroduce the ambiguity.

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

2b. A response whose only JSON object shares **no keys** with `expected` (e.g. an LLM judge
   verdict payload) grades `UNPARSEABLE`, not a mismatch — the bare-brace fallback requires a
   key-set intersection, while a fenced ```` ```json ```` block is accepted unconditionally.
3. A task declaring no `expected`, run without `--semantic`, is excluded from both numerator
   and denominator, is reported on the `ungradable` line, and makes the run exit `1`.
4. `ll-harness dsl <dir> --exit-code 0` over a set with no `expected` does **not** mark tasks
   graded — the run still reports them ungradable and exits nonzero.
5. A set in which every task is ungradable exits `2` with an explanatory message and never
   calls `wilson_ci` (no `ValueError` escapes).
5b. ENH-3185's all-abstained behavior is preserved unchanged: a set in which every task
   abstains still exits `3` with a message containing "abstained", and the ungraded branch is
   evaluated **before** the abstain branch so an all-ungraded set reports `2`, not `3`.

5c. **Partial abstention flips `0` → `3`, deliberately.** A set with ≥1 abstention, ≥1
   graded pass, no failure and no ungraded task exits `3`. This is a *change*: `harness.py:763`
   returns `0` for that case today (`return 0 if pass_count == ci_total else 1`). It needs its
   own test — the existing `test_cmd_dsl_all_abstain_excludes_from_ci_and_exits_3` covers only
   the `ci_total == 0` path and would pass either way. The new test must have a non-empty
   denominator (≥1 passing task alongside the abstaining one) to exercise the flip, and the
   CHANGELOG/`CLI.md` exit-code documentation must record it.
5d. **A per-task infra error (rc `2`) is excluded from numerator and denominator, reported
   on its own line, and makes the run exit `2`.** Drive a task whose `RunnerResult` has
   `timed_out=True` (or a non-`None` `error`) and assert it does **not** appear in the
   Wilson denominator — today it silently counts as a failure. A set in which every task
   errors exits `2` with a message that does **not** contain the word "abstained".
5e. **A malformed task file grades FAIL and the run continues.** Three cases, each its own
   test: unparseable YAML, a file with no `prompt:` key, and `expected:` that is not a
   mapping. In all three the run completes, reports the task distinguishably as a malformed
   task, counts it in the denominator, and exits `1` — no traceback escapes `cmd_dsl`, and
   the remaining tasks in the set still run.
6. When a task declares `expected` **and** `--semantic` is passed, the per-task outcome
   follows the truth table under Program Design § Interaction with abstention. Specifically:
   an `expected` mismatch is a **hard FAIL that outranks abstention** (mismatch + abstain →
   FAIL/rc 1, counted in the denominator), while a match + abstain is ABSTAIN/rc 3 and is
   excluded from the denominator. A task passes only on match + `yes`.
7. `expected` values are matched exactly after normalization applied to **both sides**:
   surrounding whitespace and one layer of matching quotes/backticks are stripped; case
   differences are a mismatch. Non-string YAML scalars normalize through `str()` (so
   `expected: {retries: 3}` matches an answer of `"3"`), with `bool` as the single documented
   exception — `True`/`False` normalize to `"true"`/`"false"` so a JSON `true` matches.
8. Keys are taken from `expected`. A missing key in the answer object is a mismatch with
   actual `None`; extra keys in the answer object do not fail the task.
9. The prompt sent for a task with blanks contains no Python list repr — `['on_yes']` does
   not appear in any generated prompt.
10. Each `dsl-task` `harness_events` row records the **host process** exit code
    (`result.exit_code`), not the evaluation rc, and records the real `semantic_verdict` when
    `--semantic` was passed.
10a. The same row records the real `timed_out` value (`result.timed_out`). It is hardcoded
    `timed_out=False` today (`harness.py:741`), so a timed-out DSL task is currently
    indistinguishable from a completed one in telemetry. Pinned by its own assertion —
    the Call Path change alone is not enough to guarantee it lands.
10b. A DSL task writes **exactly one** per-task `harness_events` row (`runner="dsl-task"`).
    The `runner="prompt"` row that `cmd_prompt` writes per task today is gone, because
    `cmd_dsl` no longer calls `cmd_prompt` — see Program Design § Consequence. A test asserts
    the post-fix row count per task, so the change is pinned rather than incidental.
11. The aggregate `runner="dsl"` row carries the run's outcome after the loop completes.
12. Telemetry remains best-effort: a `harness_events` write failure does not change the
    reported pass rate or the exit code.
13. `_evaluate_and_report`'s four existing call sites are behaviorally unchanged — the
    `ll-harness skill|cmd|mcp|prompt` surfaces produce identical output and exit codes.

## Integration Map

- `scripts/little_loops/cli/harness.py` — all code changes: `DslTask` neighborhood
  (`:163-183`), `_evaluate_and_report` (`:409`), `cmd_prompt` (`:634`), `cmd_dsl` (`:665`).
  Line numbers are post-ENH-3185; see § Baseline.
- `scripts/little_loops/stats.py:30` — `wilson_ci` n=0 guard is the caller's responsibility
  and ENH-3185 already installed it at `harness.py:755`; no change to `stats.py`.
- `scripts/tests/test_cli_harness.py` — `TestCmdDsl` (`:1019`) and `TestDslSubcommandParser`
  (`:977`) extend here.

  **Every existing `TestCmdDsl` test regresses on landing and must be updated in the same
  commit.** They all share the `_make_task_yaml` fixture (`:1022-1033`), which declares
  `expected:\n  on_yes: done` — so turning on grading changes their outcomes:

  - `test_cmd_dsl_single_file_pass` (`:1035`) drives stdout `"done"`, which is not a JSON
    object → `UNPARSEABLE` → rc `1`, breaking `assert result == 0`. Either give the fixture's
    stdout a fenced answer block, or add a no-`expected` fixture variant for the tests that
    are not about grading.
  - `test_cmd_dsl_all_abstain_excludes_from_ci_and_exits_3` (`:1085`) drives stdout that *is*
    a JSON object (`_llm_verdict("cannot_judge")`) — this is the exact case AC2b exists to
    handle, and it must still exit `3`.
  - `test_cmd_dsl_single_file_fail` (`:1051`) drives empty stdout with `--exit-code 0`; it
    still exits `1`, but now for two reasons rather than one.

  Prefer adding a `expected`-less fixture variant over weakening the shared one, so the
  ENH-3185 abstention tests keep testing abstention rather than grading.

  **Fixture cleanup while in there.** `_make_task_yaml` (`:1025-1027`) emits a duplicated
  YAML key: `"blanks:\n  - on_yes\nblanks:\n  - on_yes\n"`. `yaml.safe_load` silently takes
  the last, so it is harmless today, but the fixture is being rewritten anyway and a
  duplicate-key fixture is a bad base for the new grading tests. Collapse it to one `blanks:`
  block in the same pass.
- `skills/create-eval-from-issues/SKILL.md:129-141` — the Option B schema block. The
  generator already emits `expected`; add a note that `expected` is what grades the task and
  that a task omitting it needs `--semantic` at run time.
- `docs/guides/EVALUATION_GUIDE.md` — `:104-108` (the "read the DSL gotcha" pointer) and the
  DSL gotcha at `:409-414` must be rewritten; the sample output at `:97` gains the new lines.
- `docs/reference/CLI.md:190,209,220-221` — the `dsl` row, the dsl-specific flag block, and
  the examples need the grading semantics and the new exit-code meanings. **Enumerate all
  meanings of exit `2` in one place** rather than letting them accrete: path not found
  (`harness.py:675`), empty task directory (`:679`), every task ungradable (new), and ≥1
  per-task infra error (new). The unifying statement is "the run could not produce a
  measurement" — write that, then list the four triggers.
- `.ll/history.db` `harness_events` — row *shape* is unchanged, but both the values and the
  row *count* change:
  - the values written for `dsl-task` / `dsl` rows change (AC10, AC11);
  - **the per-task `runner="prompt"` rows stop being written** (AC10b) — `cmd_dsl` no longer
    routes through `cmd_prompt`, which is where that row is emitted (`harness.py:650-661`).

  Pre-fix rows keep their old semantics, so any analysis spanning the fix boundary is mixing
  two definitions of `exit_code` *and* two row counts per DSL task.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Conventions in Force (codebase-pattern-finder, ll:refine-issue --auto)

- **JSON recovery from LLM stdout is not a solved primitive in this codebase** — two existing extractors handle adjacent but different shapes, neither is "fenced ```json block OR balanced-brace span, recovering an arbitrary object." `extract_tagged_json(raw, tag)` (`scripts/little_loops/output_parsing.py:27`) expects a `TAG:`-prefixed line and does bounded bracket/brace repair; `_extract_tagged_structured_output(text)` (`scripts/little_loops/fsm/evaluators.py:118`) strips a fenced ```` ```json ```` block then mines `<verdict>`/`<confidence>`/`<reason>`/`<evidence>` XML-style tags. `_extract_answer_object` is a genuinely new third shape — there is no existing helper to consolidate onto.
- **Small outcome-classification enums are plain `Enum` with string values** — precedented directly in `scripts/little_loops/issue_lifecycle.py`: `DeferBy` (`:58`), `DeferReason` (`:65`), `ClosureReason` (`:96`), `CompletionResult` (`:121`), `FailureType` (`:141`). `CompletionResult`'s docstring (`:124`) states the house rule explicitly: plain `Enum`, not `StrEnum` — a repo-wide grep found zero `StrEnum` usages in `scripts/little_loops/`. `GradeStatus` as specified already matches this.
- **Contested**: whether the paired result dataclass should be `frozen=True`. The closest local precedents are both mutable: `issue_lifecycle.py`'s `_PreflightResult` (`:477`, paired with the enums above) and `harness.py`'s own `DslTask` (`:162`) are plain `@dataclass`, not frozen. There is no existing frozen-dataclass-paired-with-outcome-enum example in this codebase to point to either way — `ExpectedGrade`'s `frozen=True` is a deviation from, not a continuation of, the two closest local precedents.
- **Optional/None-returning safe YAML loading on parse failure is a strong, repeated house convention** — `try: yaml.safe_load(...) except yaml.YAMLError: <None/{}/fallback>` then an `isinstance(..., dict)` type-gate recurs at `frontmatter.py:394-397` and `:150-157`, `doc_counts.py:312-315`, `cli/logs.py:929-932,957-960`, `cli/verify_triggers.py:270-273,339-342`, `adapters/core.py:96-100` (closest shape match: `except yaml.YAMLError: return None` then `return fm if isinstance(fm, dict) else None`), `adapters/codex.py:51-54,134-137,213-215`, `config/core.py:83-87`, `goals_parser.py:133-136`, `cli/history_context.py:117-120`. `cmd_dsl`'s current task-loading (`harness.py:711`, `data = yaml.safe_load(f)`) is unguarded and does not follow this convention — that gap is exactly what `_load_task` closes.
- **Testing convention**: pure helper functions get direct unit tests in a `TestXxx` class per function/feature area with hand-built input strings, no CLI/subprocess mocking — see `class TestExtractTaggedJson` (`test_output_parsing.py:1027`), including edge-case tests like `test_repairs_missing_closing_bracket`/`test_repairs_missing_closing_brace` (`:1042`, `:1052`). CLI-level plumbing (`cmd_dsl` calling `_evaluate_and_report` with `expected_grade`) is tested by mocking `subprocess.run`/`resolve_host` and asserting on return code + `capsys` output, per the existing `TestCmdDsl` class (`test_cli_harness.py:1019`) this issue's tests extend. Both layers apply here: new pure functions get `TestXxx`-per-function unit tests; the `cmd_dsl` rewrite extends the existing mocked-subprocess integration tests.

## Implementation Steps

0. **DONE** — ENH-3185 committed as `dea24aac` (issue status `done`), so the
   `blocked_by: [ENH-3185]` edge is resolved and this issue is implementable. Line numbers
   in § Baseline were verified against that commit; re-verify if other work lands in
   `harness.py` first.
1. Add `GradeStatus`, `ExpectedGrade`, `_normalize_answer`, `_extract_answer_object`,
   `_grade_expected`, `_answer_contract_suffix`, `_load_task` — pure functions, unit-tested
   first (TDD is on for this repo). `_extract_answer_object` implements the
   key-set-intersection constraint on its bare-brace fallback (AC2b); `_load_task` and
   `_grade_expected` implement the malformed-task rule (AC5e).
2. Extract `_run_prompt_action` from `cmd_prompt`; assert `cmd_prompt` behavior is unchanged.
3. Add the keyword-only `expected_grade` parameter to `_evaluate_and_report` and thread it
   into `passed`, the status block, and the JSON payload.
4. Rewrite `cmd_dsl`'s per-task loop per the call path above, including the corrected
   `_record_harness_event` arguments (keeping ENH-3185's abstain-aware `semantic_passed`,
   and passing the real `result.timed_out` per AC10a) and the graded / ungraded /
   abstained / errored / unparseable / malformed tallies.
5. Add the `ungraded_count == total` guard **ahead of** ENH-3185's existing
   `ci_total == 0` abstain branch, split that branch so `errored_count > 0` reports `2`
   before the abstain message is reached (and without using the word "abstained", which
   `test_cmd_dsl_all_abstain_excludes_from_ci_and_exits_3` asserts on), wire the exit-code
   precedence table, and add the aggregate-row `UPDATE`.
6. Update the existing `TestCmdDsl` tests for the shared-fixture regression noted in the
   Integration Map, then extend the class to cover acceptance criteria 1-13 (including 2b,
   5b, 5c, 5d, 5e, and 10a).
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
  response was already available to `cmd_dsl`. Revised upward again post-ENH-3185: the fix
  must now interleave with an abstention model it was not written against, and every existing
  `TestCmdDsl` test changes outcome because they share an `expected`-declaring fixture.
- **Risk**: Low - The grading path is additive and gated on `task.expected`; `--semantic`-only
  behavior is preserved verbatim. The one behavioral change for existing users is that
  flagless runs now exit nonzero instead of reporting a false 100%, which is the point.
- **Breaking Change**: No - though previously-green DSL runs will start reporting real
  (lower) pass rates, and flagless runs over `expected`-less sets will start exiting `1`.
- **Measurement discontinuity (noted 2026-08-16)**: pre-fix and post-fix pass rates are not
  comparable *even for the same model on the same task set*, and not only because grading
  turns on. `_answer_contract_suffix` changes the **prompt text itself** for every task
  declaring `expected` — the model is being asked a different question (produce a fenced
  `json` answer object) than it was before. This is distinct from, and additional to, the
  telemetry-boundary discontinuity recorded under Integration Map. Any longitudinal DSL
  tracking must treat the fix as a hard baseline reset rather than a continuation.

## Related Key Documentation

- [docs/guides/EVALUATION_GUIDE.md](../../docs/guides/EVALUATION_GUIDE.md) — § `ll-harness dsl`, § Gotchas
- [docs/reference/CLI.md](../../docs/reference/CLI.md) — `ll-harness` reference
- [skills/create-eval-from-issues/SKILL.md](../../skills/create-eval-from-issues/SKILL.md) — Option B task schema

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-16T06:12:55 - `6fdede19-5616-4773-8866-a77790066587.jsonl`
- `/ll:confidence-check` - 2026-08-16T05:31:33 - `bb755dcf-6087-41b3-80d2-a79a3aba782e.jsonl`
- `/ll:reconcile-issue` - 2026-08-16T05:25:32 - `4feb49e0-b3c6-41d3-bd75-18b2a42c9652.jsonl`
- `/ll:confidence-check` - 2026-08-16T04:59:10 - `8af101e8-440c-4dfd-9d90-99c46a875466.jsonl`
- `/ll:decide-issue` - 2026-08-16T04:51:40 - `cc7f1236-7d7a-4f5c-962b-052b11db8a39.jsonl`
- `/ll:refine-issue` - 2026-08-16T04:48:41 - `cc7f1236-7d7a-4f5c-962b-052b11db8a39.jsonl`
