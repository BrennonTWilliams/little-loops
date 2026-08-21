---
id: ENH-3272
type: ENH
title: 'general-task: define_done must read the reference artifact named in the input
  before authoring format-specific criteria'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T22:49:09Z'
labels:
- enhancement
- loops
- general-task
- prompt-quality
- postmortem
relates_to:
- BUG-3269
- BUG-3270
- BUG-3271
confidence_score: 99
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 25
---

# ENH-3272: general-task: define_done must read the reference artifact named in the input before authoring format-specific criteria

## Summary

`general-task.yaml`'s `define_done` state authors the Definition of Done **before** `plan`
runs, and therefore before anything in the run has read the artifacts the task refers to.
In run `2026-08-20T121448` it wrote three DoD criteria in the wrong diagram vocabulary,
making them unsatisfiable as written and costing 3 of 23 plan steps — **13% of the run** —
to detect and repair its own text.

Postmortem: `postmortems/general-task-final-verify-spin-2026-08-20.md` (§6).

## Current Behavior

`define_done` (`general-task.yaml:81`) is the second state in the loop, entered directly
from `check_baseline_tests` via `next: define_done`, and it runs **before** `plan`.

Its prompt supplies only `${context.input}` — the raw task string — and asks for concrete,
`[hard]`-tagged verification criteria written to `${context.run_dir}/dod.md`. At that
moment the run has read no project files, resolved no references, and inspected no exemplar
artifact. The prompt contains no instruction to go read anything first.

So when the task names an artifact type ("a mermaid diagram"), the state has nothing to
ground format-specific criteria in except the type name, and fills the gap with the most
statistically common form of that type. Any criterion whose satisfiability depends on the
artifact's concrete shape is therefore authored blind.

The resulting criteria are then load-bearing for the rest of the run: `count_done` gates on
them, and an unsatisfiable `[hard]` criterion can never be checked off by any correct
implementation.

## Expected Behavior

When the input names or implies an existing exemplar artifact ("already completed for X",
"like the one in Y", "matching the existing Z"), `define_done` must read that artifact
before authoring any criterion whose satisfiability depends on the artifact's concrete
form — and `plan` must do the same before authoring steps whose correctness depends on it
(see Scope note below).

Two viable shapes:

1. **Read-first**: extend the `define_done` prompt to require locating and reading any
   referenced exemplar before writing criteria, and to derive format-specific criteria from
   what it actually found rather than from the artifact-type name.
2. **Defer-and-revise**: let `define_done` author only format-agnostic criteria up front,
   and add a post-`plan` state that revises the DoD once the plan has established the
   concrete format.

Option 1 is cheaper and stays within one state. Option 2 is more robust when no exemplar is
named but the format is still discoverable during planning. Option 1 is the recommended
starting point; the issue should decide explicitly rather than implementing both.

## Motivation

A DoD criterion that no correct implementation can satisfy is worse than a missing one: it
guarantees `count_done` never reaches zero, which routes to `continue_work`, which is the
same class of non-terminating pressure as BUG-3270 — just resolved here by the abandonment
machinery instead of a spin guard.

The 13%-of-run cost is the visible part. The invisible part is that unsatisfiable criteria
push the loop toward `partial` terminals on runs that actually succeeded.

## Proposed Solution

Adopt **option 1 (read-first)** from Expected Behavior, with the read made *conditional* so
it costs nothing on tasks that name no exemplar.

Extend the `define_done` prompt with a bounded pre-step:

1. Scan `${context.input}` for a reference to an existing artifact — a path, a filename, or
   a phrase of the "already completed for X" / "like the one in Y" / "matching the existing
   Z" family.
2. If and only if one is found, locate and read it before authoring any criterion.
3. Derive every format-specific criterion from what was actually read — the concrete
   dialect, structure, and vocabulary of the exemplar — never from the artifact-type name.
4. If a reference is named but cannot be located, say so in `dod.md` and author only
   format-agnostic criteria, rather than guessing.

Rejecting option 2 (defer-and-revise) for now: it adds a state to a loop this postmortem is
already trying to simplify, and the observed failure had a named exemplar that step 1 would
have caught. Revisit if a later run fails with no exemplar named.

### Apply the same pre-step to `plan`

`plan` (`general-task.yaml:153`) has the identical defect: its prompt receives only
`${context.input}` and contains no instruction to read a named exemplar. This was
established by the refine pass and supersedes this issue's earlier Call Path claim that
`plan` "would have supplied the missing context" — it would not have.

Fixing only `define_done` leaves the fix half-done: correct criteria, blind plan steps.
`do_work` executes plan steps, so in the observed run the diagrams themselves could still
have been drafted as flowcharts; the (now-correct) DoD would fail them and the loop would
still burn steps on repair. Add the same conditional-detect-then-read pre-step to `plan`'s
prompt, worded for step authoring rather than criterion authoring.

### `plan` must carry the observed format forward into the step text

_Added by the 2026-08-21 pre-implementation review._

`do_work` (`general-task.yaml:430`) is blind in exactly the same way, and it is the state
that actually authors the artifact. Its full prompt is `${context.input}`, an instruction to
read `${context.run_dir}/current-step.txt`, a prohibition on editing `plan.md`/`dod.md`, and
the `LAST_FILES:` reporting line. There is no exemplar instruction and no path by which the
exemplar reaches it.

So with the pre-step added to `define_done` and `plan` alone, the exemplar is read twice —
once per state — and neither read reaches the state that writes the diagram. The fix would
stop one state short, which is the same half-done shape this section argues against for
`define_done`-only.

The resolution is **not** a third copy of the pre-step in `do_work`. It is to make `plan`'s
pre-step responsible for propagation: when `plan` reads an exemplar, it must state the
observed concrete format **inside the step text it writes to `plan.md`** (e.g. "…as a
`sequenceDiagram`, matching `<exemplar path>`"), not merely use it to shape its own
step decomposition. The step text is the only channel from `plan` to `do_work`, since
`do_work` reads `current-step.txt` and nothing else from the planning phase.

This is a wording requirement on `plan`'s new block, not an additional state or context key,
and it keeps `do_work`'s prompt untouched.

### Placement inside the prompt

The new block must be the **first** instruction after the `Your task is: ${context.input}`
line in each state, before `define_done`'s "Before planning or executing anything, write a
concrete Definition of Done" and before `plan`'s "Before starting, decompose this task".
A read-first instruction placed lower in the prompt is subordinate to instructions that
already told the model to start writing.

Both prompts also end with a do-not-act line — `define_done`: "Do NOT start any work. Only
write the DoD file."; `plan`: "Do NOT start executing any steps yet." The new block must
explicitly carve these out, stating that reading an existing file to ground the criteria (or
steps) is not "work" and is required before writing. Without the carve-out the two
instructions read as contradictory and the trailing one wins.

### YAML authoring hazard — convert both scalars to `|`

Both `define_done` and `plan` use `action: >` (folded scalar), unlike the precedent at
`interactive-component-generator.yaml:69` which uses `|`. Under `>`, consecutive non-blank
lines at the same indentation collapse into one paragraph.

**This hazard is already live, not merely a risk for the new block.** Loading
`general-task.yaml` and printing the resolved `define_done.action` shows the fenced DoD
template rendering as a single line:

```
...write a concrete Definition of Done to ${context.run_dir}/dod.md in this format:
``` # Definition of Done ## Verification Criteria - [ ] <Hard criterion — must be
satisfied for done> [hard] - [ ] <Another hard criterion ...> [hard] - [ ] <Soft
criterion ...> ```
```

The fence, the heading, and all three sample criteria fold together. The Standing Criteria
block — which the prompt instructs the model to reproduce **verbatim** — folds the same way:
the fence, `## Standing Criteria`, criterion 1, and the opening of criterion 2 become one
line. Criteria 2 onward survive only incidentally, because their continuation lines are
more-indented and break the fold. `plan.action`'s `# Task Plan` template is folded
identically.

This is not cosmetic. `count_done` tallies criteria with an awk pass anchored on `^- [ ]`
(`general-task.yaml:596-620`, see Codebase Research Findings). A model that copies the
verbatim block as delivered emits criteria that do not start a line and are therefore not
counted.

**Therefore: convert both `action: >` to `action: |` as part of this change**, and write the
new pre-step block as ordinary literal lines. This repairs an existing defect in the same
edit rather than authoring a new block around it. See the test-preservation notes below for
the one assertion that requires a source rewrap under `|`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml:81` — the `define_done` prompt body, plus
  its `action: >` → `action: |` scalar conversion.
- `scripts/little_loops/loops/general-task.yaml:153` — the `plan` prompt body, same
  conditional pre-step worded for step authoring and carrying the observed format into the
  step text; same scalar conversion.
- `scripts/little_loops/loops/general-task.yaml:139-140` — whitespace-only rewrap so
  `no new errors` sits on one source line, required by the scalar conversion.

These two prompt bodies (plus the scalar conversion and the one rewrap) are the entire
change under option 1. `do_work` (`:430`) is deliberately **not** modified — see "`plan`
must carry the observed format forward into the step text".

### Dependent Files (Callers/Importers)
- No code callers. The downstream consumers of `dod.md` are states within the same loop:
  - `count_done` — gates on unchecked `[hard]` criteria
  - `final_verify` (`:662`) — re-verifies every criterion
  - `count_final` (`:784`) — tallies FAILEDs
- None need changing; they consume better-grounded criteria, not differently-shaped ones.

### Similar Patterns
- Other loops with a DoD- or criteria-authoring prompt run before any project read —
  survey `harness-single-shot.yaml`, `harness-multi-item.yaml`, and
  `harness-plan-research-implement-report.yaml` for the same ordering, but do **not** change
  them here (see Scope Boundaries).

### Tests
- No natural pytest assertion for the behavior itself; the failure is prompt quality, not
  logic. The committed automated gate is a prompt-text assertion (see Implementation Step 6).
- An ad-hoc eval run — a task whose input names an exemplar in a non-default format,
  checking no DoD criterion or plan step cites the wrong format — is the honest behavioral
  check. Not checked in; see "Decision: no checked-in eval harness".
- Regression guard for the conditional: assert the prompt makes the read an explicit
  branch, so a task naming **no** exemplar gains no file-reading step in `define_done`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — the loop's dedicated content-assertion test
  file (`raw_data` fixture loads `general-task.yaml` and asserts substrings of
  `states.define_done.action`, e.g. `TestChange1DefineDoneRuntimeCriteria` at line 81,
  `TestBUG1766ConvergenceEfficiency` at line 1017, `TestENH2858StandingCriteria` at
  line 2385). Add a new `TestEnh3272DefineDoneConditionalRead` class here asserting the
  conditional-detect-then-read instruction is present in `define_done.action` **and in
  `plan.action`**, following the same substring-assertion convention as the existing
  classes.
- **Existing tests to preserve (not edit), guard against accidental breakage.** _Corrected
  by the 2026-08-21 pre-implementation review: the originally-listed three tests are all
  safe under the `|` conversion, and the one assertion that actually breaks was missing._

  All of these do substring containment on `define_done.action`. The prompt revision must
  add text without removing or rewording these phrases:

  - `test_define_done_action_requires_runtime_criteria` (`test_general_task_loop.py:81`) —
    `"runtime"`/`"static"`/`"insufficient"`. **Intra-line; `|`-safe.**
  - `test_define_done_forbids_tracking_file_criteria` (`test_general_task_loop.py:1017`) —
    `"Do NOT write DoD criteria that target"` + `"plan.md"`/`"dod.md"`. **Intra-line;
    `|`-safe.**
  - `test_define_done_has_standing_criteria_block`
    (`scripts/tests/test_builtin_loops.py:14994`) — `"## Standing Criteria"` + `"not derived
    from the task description"`. **Intra-line; `|`-safe.**
  - `TestENH2858StandingCriteria` (`test_general_task_loop.py:2385`) — five further
    `define_done.action` assertions the issue previously cited only as a line anchor and
    never listed as protected: `test_define_done_contains_standing_criteria_heading` (`:2388`),
    `test_define_done_standing_criteria_cover_all_five` (`:2393`, requires `"read on every
    code path"`, `"Contract-over-mechanism"`, `"validated before use"`, `"reachable from a
    built artifact"`, `"PROVISIONAL"`/`"TODO"`/`"GUESS"`),
    `test_define_done_wheel_criterion_is_conditional` (`:2401`), and
    `test_define_done_marker_criterion_notes_mechanical_grep` (`:2406`). All intra-line;
    `|`-safe.

- **The one assertion that breaks under `|` — requires a source rewrap.**
  `test_define_done_requires_exits_0_phrasing` (`test_general_task_loop.py:2411`) asserts:

  ```python
  assert 'never as a delta claim like "no new errors"' in action
  ```

  The phrase spans a source line break in the YAML (`general-task.yaml:139-140`:
  `... never as a delta claim like "no new` / `errors" or "no new lint failures
  introduced."`). Folding under `>` stitches it back into one line; `|` will not. Rewrap
  those two source lines so `no new errors` sits on a single line. This is a whitespace-only
  fix, but it is **required** — without it the `|` conversion turns this test red.
- ~~`scripts/tests/test_create_eval_from_issues.py` — fixture test class for a checked-in
  eval harness [Agent 3 finding].~~ **Dropped by the 2026-08-21 pre-implementation review**
  along with the harness check-in itself; see "Decision: no checked-in eval harness".

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the general rule: a state that authors
  gating criteria must not run before the evidence those criteria depend on has been read.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:106` — the "1. **Define Done**" step description
  ("writes verifiable acceptance criteria to `${context.run_dir}/dod.md`... static file/import
  checks alone are insufficient") does not mention the conditional exemplar-read step and will
  go stale once `define_done`'s prompt changes; update alongside the prompt edit [Agent 2
  finding]. Update the adjacent "2. **Plan**" line (`:107`) the same way, since `plan` gains
  the same pre-step.

### Configuration
- N/A

## Program Design

### Signatures

- `define_done(input: str) -> None` — writes `dod.md`; unchanged signature, the prompt body
  gains a conditional read step. No new state, no new context key under option 1.
- `exemplar_ref(input: str) -> str | None` — the conditional detection step added to the
  prompt: returns a referenced artifact path when the input names one, else nothing.

### Call Path

- `check_baseline_tests` → `define_done` — the entry edge. This ordering is the defect:
  `define_done` runs second, before any project file has been read.
- `define_done` → `plan` — the successor. It does **not** supply the missing context: its
  own prompt (`:153`) also receives only `${context.input}` with no read instruction, so
  plan steps are authored just as blind as the criteria. Both states need the pre-step.
- `define_done` → writes `${context.run_dir}/dod.md` — the artifact whose criteria are
  authored blind.
- `count_done` → reads `dod.md` — the gate that an unsatisfiable `[hard]` criterion
  permanently blocks.
- `count_done` → `continue_work` — the edge taken forever when a criterion cannot be
  satisfied; the same non-terminating pressure as BUG-3270.
- `select_step` → `do_work` → `verify_step` → abandonment at `max_step_attempts` — the
  recovery path that absorbed the cost in the observed run (steps 20, 21, 23).
- `FSMExecutor` (`scripts/little_loops/fsm/executor.py:171`) — the class that runs every
  `action_type: prompt` state, `define_done` included. Confirms the change is purely
  prompt-text: no executor behavior needs to change for a conditional read-first
  instruction to take effect, since `FSMExecutor` already just passes the prompt body
  through to the host CLI.

### Design constraints

No new states, no schema change under option 1 — the whole change is the `define_done` and
`plan` prompt bodies at `general-task.yaml:81` and `:153`.

The design constraint that matters is **conditionality**. A prompt that unconditionally
requires a file read adds latency and tool calls to every run of the most-used built-in
loop, including the majority that name no exemplar. The prompt must therefore make the read
an explicit branch, not a preamble: *detect a reference first; read only if one exists.*

The second constraint is **derivation direction**. It is not enough to instruct "read the
reference" — the observed failure would still occur if the model read the exemplar and then
authored criteria from the artifact-type name anyway. The prompt must bind the criteria to
the read: format-specific criteria are to be *derived from the exemplar's observed form*,
and where no exemplar was read, format-specific criteria are to be *omitted* rather than
guessed.

The third constraint is **propagation**. `do_work`, not `plan`, writes the artifact, and it
never sees the exemplar. A read that stops at `plan`'s own reasoning is wasted; `plan` must
serialize what it learned into the step text, which is the only channel forward.

The failure mode to guard against in review is a mermaid-specific patch. The defect was "did
not read the reference", not "did not know mermaid"; format-name allowlists would fix the
observed run and nothing else.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Confirmed current anchors** (`scripts/little_loops/loops/general-task.yaml`, line numbers as of this pass):
  - _Line numbers below re-verified 2026-08-21; the earlier `:43`/`:45-115` anchors were stale
    after `check_baseline_tests` grew with the BUG-3269 test-cmd resolution._
  - `define_done` state: `:81-151` (prompt body `:82-148`, `action_type: prompt` `:149`, `next: plan` `:150`, `on_error: diagnose` `:151`). Confirmed the prompt references only `${context.input}` (`:83`), `${context.min_pass_rate}` (`:99`), and `${context.run_dir}` (`:86,105,118`) — no instruction anywhere to locate or read a referenced exemplar before authoring criteria.
  - Entry edge: `check_baseline_tests` (`:41`) → `next: define_done` (`:78`) **and** `on_error: define_done` (`:79`) — both the success and shell-error paths land on `define_done`, so it always runs second regardless of baseline outcome.
  - `plan` state: `:153`. Confirmed it is **not** a richer state than `define_done` in this respect — its prompt also receives only `${context.input}` with no read-first instruction. The claim that `plan` "would have supplied the missing context" (issue's original Call Path) is not backed by `plan`'s current prompt text; both states are equally silent on reading a named exemplar. **This is why the Proposed Solution now covers `plan` as well as `define_done`.**
  - Step-abandonment machinery: `context.max_step_attempts: 3` (`:25`); `select_step` (`:225`) counts attempts against `${context.run_dir}/step-attempts.txt`, abandons via an awk-tmp-mv rewrite, emits `STEP_BLOCKER_HALT`/`STEP_ABANDONED`. `check_step_halt` (`:312`) routes blocker-halts to `summarize_partial` and plain abandonment to `spin_gate` (`:332`, cap `target: 3`, `on_yes: check_done`). Abandonment does **not** halt the run directly — it falls through to the normal `check_done`/`count_done` DoD-gating machinery.
  - `count_done` (`:578`) gate: `evaluate.path: ".total"`, `operator: eq`, `target: 0`; `on_no: continue_work`. Confirmed: an unchecked `[hard]` criterion keeps `HARD_UNCHECKED_DOD > 0` forever (no mechanism auto-satisfies or drops a `[hard]` criterion), so `TOTAL` never reaches 0 and `count_done` routes to `continue_work` on every pass — the same non-terminating-pressure shape as BUG-3270, bounded only by `continue_work`'s own `max_retries: 3`/`on_retry_exhausted: diagnose` (unrelated general retry cap, not an unsatisfiable-criterion detector).
- **The "reference named but not locatable" fallback is safe to write as prose.** `count_done`
  tallies unchecked hard criteria with an awk pass over `^- [ ]`-prefixed lines carrying
  `${context.hard_criteria_tags}` (`general-task.yaml:596-620`); a prose note in `dod.md`
  about an unlocatable reference matches no criterion line and therefore cannot perturb the
  gate. No escaping or placement constraint applies to the fallback text.
- **Pattern precedent for the "detect a reference, read only if found" prompt shape** (pattern_finder axis): this exact shape already exists in the codebase at `scripts/little_loops/loops/interactive-component-generator.yaml:69-71` (`profile_input` state, `action_type: prompt`): "Step 1 — Resolve the source. If the input names or path-references a file (e.g. a .csv, .json, .md, .txt, .tsv), read that file. Otherwise treat the text itself as the subject/data description." This confirms option 1's shape — conditional detect-then-read inside a single prompt-type state's action text, no new FSM state or schema addition — is an established convention, not a novel mechanism being introduced for the first time.

## Implementation Steps

_Revised by the 2026-08-21 pre-implementation review: the `|` conversion and its required
rewrap are now explicit steps, `plan`'s carry-forward requirement is called out, and the
eval-harness deliverable is decided rather than left as a branch at implementation time._

1. **Confirm the ordering claim** — `check_baseline_tests → define_done → plan`, and that
   `define_done`, `plan`, and `do_work` all receive only `${context.input}` with no read
   instruction.
2. **Convert `define_done.action` and `plan.action` from `>` to `|`** (see YAML authoring
   hazard). Do this first, as a mechanical scalar change, so the prompt-text edits in steps
   3–4 are made against the body as it will actually render.
3. **Rewrap `general-task.yaml:139-140`** so `no new errors` sits on a single source line,
   preserving `test_define_done_requires_exits_0_phrasing`. Run
   `pytest scripts/tests/test_general_task_loop.py scripts/tests/test_builtin_loops.py`
   after steps 2–3 and before any prompt-text edit — a green run here proves the scalar
   conversion is behavior-preserving, and isolates any later failure to the new text.
4. **Draft the prompt revision** for `define_done` per Proposed Solution: conditional
   detection, conditional read, derivation binding, and the explicit omit-don't-guess
   fallback. Place it first in the prompt, with the "reading is not work" carve-out.
5. **Apply the same pre-step to `plan`**, worded for step authoring: steps whose correctness
   depends on the artifact's concrete form must be derived from the exemplar actually read,
   not from the artifact-type name. **Include the carry-forward requirement** — when an
   exemplar is read, the observed concrete format must appear in the step text written to
   `plan.md`, since that is the only channel to `do_work`.
6. **Check the no-exemplar path** — assert the prompt text makes the read *conditional*
   (an explicit "if a reference is named … otherwise …" branch rather than an unconditional
   preamble). This is a prompt-text assertion in the new test class, not a runtime
   observation: attributing tool calls to a single state's turn would require parsing the
   run's session transcript, which is out of proportion to the guarantee it buys. **This is
   the committed automated gate for the issue.**
7. **Measure before/after ad hoc** on a task naming an exemplar in a non-default format for
   its artifact type: does any DoD criterion, or any plan step, cite a format the exemplar
   does not use? Zero wrong-format citations is the acceptance signal. Record the result in
   the issue; **do not** check an eval harness into source control for this issue (decided
   below).
8. **Verify.** `ll-loop validate general-task` clean; `python -m pytest scripts/tests/`
   exits 0.

### Decision: no checked-in eval harness

_2026-08-21 pre-implementation review._ The earlier steps 4 and 7 offered "check the harness
in, or drop both" as a branch to be resolved during implementation. That is the difference
between a two-prompt-body edit and a new checked-in FSM harness plus a fixture test in
`scripts/tests/test_create_eval_from_issues.py` — too large a scope swing to leave to the
implementer, and an open invitation to silently take the cheap branch.

Decided: **run the eval ad hoc (step 7), commit no harness.** The prompt-text conditionality
assertion (step 6) is the committed gate. §Impact already concedes there is no natural
pytest assertion for prompt quality, so a checked-in harness would buy a fixture-shape test
(`load_and_validate`/`validate_fsm`) rather than a test of the behavior this issue is about.
The `test_create_eval_from_issues.py` fixture-test entry under Wiring is therefore dropped.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_general_task_loop.py` — add a `TestEnh3272DefineDoneConditionalRead`
  class asserting the conditional-detect-then-read instruction is present in
  `define_done.action` and `plan.action`, plus a conditionality assertion (the branch is
  "if a reference is named … otherwise …", not an unconditional read) and an assertion that
  `plan.action` requires the observed format to be written into the step text.
- Preserve (do not reword away) the substrings required by the tests enumerated under
  **Existing tests to preserve** above. Note that list was corrected on 2026-08-21: the
  originally-named three are all `|`-safe, `TestENH2858StandingCriteria`
  (`test_general_task_loop.py:2385`) was missing from it, and
  `test_define_done_requires_exits_0_phrasing` (`:2411`) requires the
  `general-task.yaml:139-140` rewrap or it turns red under the scalar conversion.
- Update `docs/guides/LOOPS_REFERENCE.md:106` — extend the "Define Done" step description to
  note the conditional exemplar-read requirement.

## Impact

- **Severity**: P3. Real and measurable, but bounded — the abandonment machinery recovers,
  at a cost in steps and tokens rather than a hung run.
- **Scope**: prompt-quality change, contained to two prompt bodies (`define_done`, `plan`).
- **Risk**: a read-first requirement adds latency to `define_done` on every run, including
  the ones with no exemplar to read. The prompt must make the read conditional on a
  reference actually being named.
- **Measurability**: hard to unit-test directly. The honest verification is a
  before/after comparison on a task whose input names an exemplar in a non-default format,
  checking that no DoD criterion cites the wrong format. Consider `/ll:create-eval-from-issues`
  rather than a pytest assertion.

## Current Pain Point

The task was "make a mermaid diagram for each sub-folder in `<workflows-dir>/`", and the
input explicitly pointed at an already-completed reference diagram as the exemplar.

`define_done` authored criteria 5, 7, and 8 in **flowchart** vocabulary — `{}` for
decision, `([])` for stadium, `[]` for rectangle, `flowchart TD` / `flowchart LR` for
direction, "link directives" for edges.

Every one of the 13 diagrams is a `sequenceDiagram`, including the pre-existing reference
diagram the task named. `sequenceDiagram` has no flowchart node shapes and no `TD`/`LR`
direction. The criteria were not merely wrong — they were unsatisfiable by any correct
implementation.

Recovery cost, visible in the plan:

- **Step 20** — draft a revision proposal (`dod-criteria-5-7-8-revision-proposal.md`, 5.9 KB)
- **Step 21** — apply it; **abandoned after 3 attempts** (`max_step_attempts: 3`)
- **Step 23** — narrower direct-verify path; succeeded

The root cause is ordering: `define_done` runs before `plan` (`general-task.yaml:81`,
`next: define_done` from `check_baseline_tests`), so at authoring time the loop has read
nothing about the domain. It has only the raw input string, and it fills the gap with the
most statistically common form of the artifact type — flowchart, for "mermaid diagram".

**Credit where due:** the step-abandonment machinery worked exactly as designed. Step 21
hit `max_step_attempts`, was abandoned cleanly, and was re-planned as a narrower Step 23
that succeeded — the FSM recovering from a bad step without human intervention. This issue
is about not generating the bad step in the first place, not about the recovery path.

## Scope Boundaries

**In scope**: the `define_done` and `plan` prompts in `general-task.yaml`, their `>` → `|`
scalar conversion, and the `:139-140` rewrap that conversion requires. (Option 2, if it were
chosen, would instead add one new post-`plan` state — it is not chosen.)

**Out of scope**:
- Any edit to `do_work`'s prompt (`:430`). It is blind to the exemplar by design here; the
  observed format reaches it through the step text `plan` writes, not through a third copy
  of the pre-step.
- Converting other states' `action: >` scalars in `general-task.yaml`, or other loops'.
  The same folding hazard very likely affects them, but that is a separate sweep — file it
  as its own issue if the conversion here proves out.
- Generalizing exemplar-reading to other loops' DoD-authoring states. Do that only once
  this shape is proven in `general-task`.
- Any change to the step-abandonment machinery, which behaved correctly.
- Mermaid-specific knowledge baked into the prompt. The failure was "did not read the
  reference", not "did not know mermaid" — a mermaid-specific patch would fix this run and
  no other.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §6
- `general-task.yaml:81` — `define_done`, and the `check_baseline_tests → define_done → plan` ordering (`plan` at `:153`)
- ENH-2857 — step-blocker detection in the abandonment path that recovered this run

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-21T16:05:43 - `e51da567-cdae-4205-bfd5-023682a758f8.jsonl`
- `/ll:confidence-check` - 2026-08-21T15:54:46 - `da526826-2179-460f-b823-35695378ac55.jsonl`
- Pre-implementation review (2) - 2026-08-21 - four corrections verified against the tree:
  (1) `>` → `|` guidance **reversed** — the folding hazard is already live and mangles both
  fenced templates and the Standing Criteria block, so the conversion is now required work,
  not a forbidden convenience; (2) protected-test list corrected — the three named tests are
  all `|`-safe, `TestENH2858StandingCriteria` was missing, and
  `test_define_done_requires_exits_0_phrasing` (`:2411`) is the sole breakage, needing a
  `general-task.yaml:139-140` rewrap; (3) `do_work` identified as equally blind, resolved by
  requiring `plan` to carry the observed format into the step text rather than by editing
  `do_work`; (4) eval-harness branch decided — ad-hoc run, no check-in, dropping former
  Implementation Steps 4 and 7 and the `test_create_eval_from_issues.py` wiring entry.
- Pre-implementation review - 2026-08-21 - scope extended to `plan`; line anchors
  re-verified against current `general-task.yaml`; prompt placement, `>`-scalar hazard, and
  eval-harness deliverable made explicit; Step 5 no-exemplar check converted from an
  unspecified runtime observation to a prompt-text conditionality assertion.
- `/ll:wire-issue` - 2026-08-21T15:40:50 - `643c18b8-5d02-4711-bb71-5bf283d175a3.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
