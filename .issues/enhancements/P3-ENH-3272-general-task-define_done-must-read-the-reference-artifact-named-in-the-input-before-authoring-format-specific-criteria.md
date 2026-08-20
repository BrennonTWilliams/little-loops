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

`define_done` (`general-task.yaml:43`) is the second state in the loop, entered directly
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
form.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml:43` — the `define_done` prompt body. This is
  the entire change under option 1.

### Dependent Files (Callers/Importers)
- No code callers. The downstream consumers of `dod.md` are states within the same loop:
  - `count_done` — gates on unchecked `[hard]` criteria
  - `final_verify` (`:552`) — re-verifies every criterion
  - `count_final` (`:632`) — tallies FAILEDs
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

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the general rule: a state that authors
  gating criteria must not run before the evidence those criteria depend on has been read.

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
- `define_done` → `plan` — the successor that would have supplied the missing context; it
  runs too late to inform the criteria.
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

No new states, no schema change under option 1 — the whole change is the `define_done`
prompt body at `general-task.yaml:43`.

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
  - `define_done` state: `:45-115` (prompt body `:46-112`, `action_type: prompt` `:113`, `next: plan` `:114`, `on_error: diagnose` `:115`). Confirmed the prompt references only `${context.input}` (`:47`), `${context.min_pass_rate}` (`:63`), and `${context.run_dir}` (`:50,69,82`) — no instruction anywhere to locate or read a referenced exemplar before authoring criteria.
  - Entry edge: `check_baseline_tests` (`:35`) → `next: define_done` (`:42`) **and** `on_error: define_done` (`:43`) — both the success and shell-error paths land on `define_done`, so it always runs second regardless of baseline outcome.
  - `plan` state: `:117-135`. Confirmed it is **not** a richer state than `define_done` in this respect — its prompt (`:118-132`) also receives only `${context.input}` with no read-first instruction. The claim that `plan` "would have supplied the missing context" (issue's Call Path) is not backed by `plan`'s current prompt text; both states are equally silent on reading a named exemplar.
  - Step-abandonment machinery: `context.max_step_attempts: 3` (`:24`); `select_step:189-268` counts attempts against `${context.run_dir}/step-attempts.txt`, abandons via the awk-tmp-mv rewrite at `:242-244`, emits `STEP_BLOCKER_HALT`/`STEP_ABANDONED`. `check_step_halt:276-286` routes blocker-halts to `summarize_partial` and plain abandonment to `spin_gate:296-307` (cap `target: 3`, `on_yes: check_done`). Abandonment does **not** halt the run directly — it falls through to the normal `check_done`/`count_done` DoD-gating machinery.
  - `count_done:470-551` gate: `evaluate.path: ".total"`, `operator: eq`, `target: 0` (`:544-548`); `on_no: continue_work` (`:550`). Confirmed: an unchecked `[hard]` criterion keeps `HARD_UNCHECKED_DOD > 0` forever (no mechanism auto-satisfies or drops a `[hard]` criterion), so `TOTAL` never reaches 0 and `count_done` routes to `continue_work` on every pass — the same non-terminating-pressure shape as BUG-3270, bounded only by `continue_work`'s own `max_retries: 3`/`on_retry_exhausted: diagnose` (unrelated general retry cap, not an unsatisfiable-criterion detector).
- **Pattern precedent for the "detect a reference, read only if found" prompt shape** (pattern_finder axis): this exact shape already exists in the codebase at `scripts/little_loops/loops/interactive-component-generator.yaml:69-71` (`profile_input` state, `action_type: prompt`): "Step 1 — Resolve the source. If the input names or path-references a file (e.g. a .csv, .json, .md, .txt, .tsv), read that file. Otherwise treat the text itself as the subject/data description." This confirms option 1's shape — conditional detect-then-read inside a single prompt-type state's action text, no new FSM state or schema addition — is an established convention, not a novel mechanism being introduced for the first time.

## Implementation Steps

1. **Confirm the ordering claim** — `check_baseline_tests → define_done → plan`, and that
   `define_done`'s prompt receives only `${context.input}` with no read instruction.
2. **Draft the prompt revision** per Proposed Solution: conditional detection, conditional
   read, derivation binding, and the explicit omit-don't-guess fallback.
3. **Build the eval** with `/ll:create-eval-from-issues` — a task naming an exemplar in a
   non-default format for its artifact type.
4. **Measure before/after** on that eval: does any DoD criterion cite a format the exemplar
   does not use? This is the acceptance signal.
5. **Check the no-exemplar path** — a task naming no reference must show no added file reads
   in `define_done`.
6. **Verify.** `ll-loop validate general-task` clean; `python -m pytest scripts/tests/`
   exits 0.

## Impact

- **Severity**: P3. Real and measurable, but bounded — the abandonment machinery recovers,
  at a cost in steps and tokens rather than a hung run.
- **Scope**: prompt-quality change, contained to one state.
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

The root cause is ordering: `define_done` runs before `plan` (`general-task.yaml:43`,
`next: define_done` from `check_baseline_tests`), so at authoring time the loop has read
nothing about the domain. It has only the raw input string, and it fills the gap with the
most statistically common form of the artifact type — flowchart, for "mermaid diagram".

**Credit where due:** the step-abandonment machinery worked exactly as designed. Step 21
hit `max_step_attempts`, was abandoned cleanly, and was re-planned as a narrower Step 23
that succeeded — the FSM recovering from a bad step without human intervention. This issue
is about not generating the bad step in the first place, not about the recovery path.

## Scope Boundaries

**In scope**: the `define_done` prompt and, if option 2 is chosen, one new post-`plan`
state in `general-task.yaml`.

**Out of scope**:
- Generalizing exemplar-reading to other loops' DoD-authoring states. Do that only once
  this shape is proven in `general-task`.
- Any change to the step-abandonment machinery, which behaved correctly.
- Mermaid-specific knowledge baked into the prompt. The failure was "did not read the
  reference", not "did not know mermaid" — a mermaid-specific patch would fix this run and
  no other.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §6
- `general-task.yaml:43` — `define_done`, and the `check_baseline_tests → define_done → plan` ordering
- ENH-2857 — step-blocker detection in the abandonment path that recovered this run

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
