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
confidence_score: 97
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

### YAML authoring hazard

Both `define_done` and `plan` use `action: >` (folded scalar), unlike the precedent at
`interactive-component-generator.yaml:69` which uses `|`. Under `>`, consecutive non-blank
lines collapse into one paragraph — a numbered list written without blank lines between
items will render as a single run-on sentence. Write the new block as blank-line-separated
paragraphs and keep the `>` scalar; do **not** convert to `|` as a convenience, since that
rewrites every line's whitespace in a body that three tests assert substrings against.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml:81` — the `define_done` prompt body.
- `scripts/little_loops/loops/general-task.yaml:153` — the `plan` prompt body, same
  conditional pre-step worded for step authoring.

These two prompt bodies are the entire change under option 1.

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
- No natural pytest assertion; the failure is prompt quality, not logic.
- Prefer `/ll:create-eval-from-issues` to build an eval harness: a task whose input names an
  exemplar in a non-default format, asserting no DoD criterion cites the wrong format.
- Regression guard for the conditional: a task naming **no** exemplar must not gain a
  file-reading step in `define_done`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — the loop's dedicated content-assertion test
  file (`raw_data` fixture loads `general-task.yaml` and asserts substrings of
  `states.define_done.action`, e.g. `TestChange1DefineDoneRuntimeCriteria` at line 81,
  `TestBUG1766ConvergenceEfficiency` at line 1017, `TestENH2858StandingCriteria` at
  line 2385). Add a new `TestEnh3272DefineDoneConditionalRead` class here asserting the
  conditional-detect-then-read instruction is present in `define_done.action` **and in
  `plan.action`**, following the same substring-assertion convention as the existing
  classes.
- **Existing tests to preserve (not edit), guard against accidental breakage**:
  `test_define_done_action_requires_runtime_criteria` (`test_general_task_loop.py:81`,
  requires `"runtime"`/`"static"`/`"insufficient"`),
  `test_define_done_forbids_tracking_file_criteria` (`test_general_task_loop.py:1017`,
  requires `"Do NOT write DoD criteria that target"` + `"plan.md"`/`"dod.md"`), and
  `test_define_done_has_standing_criteria_block` (`scripts/tests/test_builtin_loops.py:14994`,
  requires `"## Standing Criteria"` + `"not derived from the task description"`) all do
  substring containment on `define_done.action`. The prompt revision must add text without
  removing or rewording these phrases, or these three tests break.
- `scripts/tests/test_create_eval_from_issues.py` — home for a fixture test class
  (mirroring `TestEvalHarnessVariantAWithProofGates` at line 519) once the
  `/ll:create-eval-from-issues`-generated eval harness for this issue is checked into source
  control, asserting its `execute`→`check_skill` shape via `load_and_validate`/
  `validate_fsm`/`ll-loop validate` [Agent 3 finding]. **This is contingent on checking the
  harness in** (Implementation Steps 4 and 7) — it is a second deliverable, not a free
  add-on. If the eval is run ad hoc instead, drop both.

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

1. **Confirm the ordering claim** — `check_baseline_tests → define_done → plan`, and that
   both `define_done` and `plan` receive only `${context.input}` with no read instruction.
2. **Draft the prompt revision** for `define_done` per Proposed Solution: conditional
   detection, conditional read, derivation binding, and the explicit omit-don't-guess
   fallback. Place it first in the prompt, with the "reading is not work" carve-out, as
   blank-line-separated paragraphs under the `>` scalar.
3. **Apply the same pre-step to `plan`**, worded for step authoring: steps whose correctness
   depends on the artifact's concrete form must be derived from the exemplar actually read,
   not from the artifact-type name.
4. **Build the eval** with `/ll:create-eval-from-issues` — a task naming an exemplar in a
   non-default format for its artifact type. Check the generated harness into source control
   under `scripts/little_loops/loops/` (or the repo's eval-harness location) so step 7 has a
   fixture to assert against.
5. **Measure before/after** on that eval: does any DoD criterion, or any plan step, cite a
   format the exemplar does not use? Zero wrong-format citations is the acceptance signal.
6. **Check the no-exemplar path** — assert the prompt text makes the read *conditional*
   (an explicit "if a reference is named … otherwise …" branch rather than an unconditional
   preamble). This is a prompt-text assertion in the new test class, not a runtime
   observation: attributing tool calls to a single state's turn would require parsing the
   run's session transcript, which is out of proportion to the guarantee it buys.
7. **Add the eval-harness fixture test** in `scripts/tests/test_create_eval_from_issues.py`
   once step 4's harness is checked in — or drop both step 4's check-in and this step if the
   eval is run ad hoc. Do not leave the harness uncommitted with a test asserting against it.
8. **Verify.** `ll-loop validate general-task` clean; `python -m pytest scripts/tests/`
   exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_general_task_loop.py` — add a `TestEnh3272DefineDoneConditionalRead`
  class asserting the conditional-detect-then-read instruction is present in
  `define_done.action` and `plan.action`, plus a conditionality assertion (the branch is
  "if a reference is named … otherwise …", not an unconditional read).
- Preserve (do not reword away) the substrings required by
  `test_general_task_loop.py:81` (`test_define_done_action_requires_runtime_criteria`),
  `test_general_task_loop.py:1017` (`test_define_done_forbids_tracking_file_criteria`), and
  `scripts/tests/test_builtin_loops.py:14994` (`test_define_done_has_standing_criteria_block`)
  when rewriting the `define_done` prompt body.
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

**In scope**: the `define_done` and `plan` prompts in `general-task.yaml`. (Option 2, if it
were chosen, would instead add one new post-`plan` state — it is not chosen.)

**Out of scope**:
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
- `/ll:confidence-check` - 2026-08-21T15:54:46 - `da526826-2179-460f-b823-35695378ac55.jsonl`
- Pre-implementation review - 2026-08-21 - scope extended to `plan`; line anchors
  re-verified against current `general-task.yaml`; prompt placement, `>`-scalar hazard, and
  eval-harness deliverable made explicit; Step 5 no-exemplar check converted from an
  unspecified runtime observation to a prompt-text conditionality assertion.
- `/ll:wire-issue` - 2026-08-21T15:40:50 - `643c18b8-5d02-4711-bb71-5bf283d175a3.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
