---
id: ENH-3259
type: ENH
title: Caller suitability gate has no repeatable fixture after ENH-3258 closed
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T00:19:48Z'
testable: true
program_design_not_applicable: true
relates_to:
- ENH-3258
---

# ENH-3259: Caller suitability gate has no repeatable fixture after ENH-3258 closed

## Summary

The § 8b caller suitability gate (ENH-3258) has no regression protection. It is a
prose rule in a markdown prompt, so it is not pytest-assertable, and the fixture that
validated it was synthetic and deleted after use. A future edit to § 8b — or a
companion-extraction that drops the `Inject at <path>` clause to fit the 500-line cap —
can silently undo it with a green test suite.

## Current Behavior

`python -m pytest scripts/tests/` covers the 500-line cap, companion registration, and
mirror drift. It does not and cannot cover whether wire-issue actually applies the gate.
ENH-3258 Implementation Step 4 is explicitly labelled "post-merge validation, not a
pytest gate."

The validating fixture was ENH-3300, a synthetic issue over real code:
`get_untracked_files()` has exactly one production caller,
`scripts/little_loops/git_operations.py:413`, inside `if untracked_files is None:`
(`:412`), whose enclosing `suggest_gitignore_patterns()` already accepts
`untracked_files: list[str] | None = None`. Both skip conditions fire. It was deleted
after the run, so the fixture no longer exists.

## Expected Behavior

The fixture is preserved and runnable on demand, so the gate can be re-validated after
any edit to § 8b or its companion.

## Motivation

ENH-3258's own risk note says the failure mode is "an LLM under-applying a prose rule
inside a 493-line prompt." That risk does not end at merge — it recurs on every
subsequent edit to the file. The one-shot fixture proved the rule works once; it
provides nothing thereafter.

Both halves need coverage, and they fail differently:
- **Suppression** — no `Update <path>` bullet for the guarded call site.
- **Injection** — an `Inject at <path>` bullet naming the parameter seam. This half was
  added only after the clean fixture showed the rule was purely subtractive, so it is
  the newer and less-exercised of the two.

## Proposed Solution

Preserve the ENH-3300 fixture as an eval task via `/ll:create-eval-from-issues` or
`/ll:verify-issue-loop`, with the issue body checked in as a fixture file rather than
living in `.issues/` (it is not real work and must not appear in the backlog).

The assertion is textual over wire-issue's dry-run output, so it needs an LLM evaluator
or a targeted grep on the emitted Wiring Phase, not an exact-match diff.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **`/ll:create-eval-from-issues`** (`skills/create-eval-from-issues/SKILL.md:229-266`) synthesizes a single `llm_structured` evaluation-criteria prompt graded for *user-experience quality*, not implementation conformance — it explicitly states it never emits `check_stall`/`check_concrete`/`check_semantic`/`check_invariants`, and its evaluation prompt requires an agent to author free-text `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>` placeholders (via `ll-loop scaffold-eval --issues <IDS> --json`, output to `.loops/<name>.yaml`). A `--dsl` mode also exists, generating exact-match/graded fill-in-the-blank tasks under `evals/dsl/<source>/`, graded via `ll-harness dsl` against an `expected:` mapping — a different mechanism from the FSM harness path.
- **`/ll:verify-issue-loop`** (`skills/verify-issue-loop/SKILL.md:33-70`, `scripts/little_loops/cli/loop/scaffold_verify.py:111-156`) emits one `llm_structured` state **per Acceptance Criterion**, fully determined by the issue's own criterion text with no placeholder-authoring step (via `ll-loop scaffold-verify "$ISSUE_ID" [--adversarial] --json`, output to `.loops/<PREFIX>-<issue-id-lower>-<title-slug>.yaml`). This asserts against implementation conformance, which is the shape this issue's two-halves check needs. Its aggregate stage (`scaffold_verify.py:67-156`) routes every criterion's verdict forward without short-circuiting, then a final deterministic shell state inspects each captured verdict and reports every criterion that did not pass — established precedent in this codebase for asserting the suppression half and the injection half as two independent criteria routed into one aggregate gate, rather than either failing the run early.
- A third, structurally different precedent exists: `scripts/little_loops/loops/prompt-regression-test.yaml` (cataloged in `scripts/little_loops/loops/README.md:128-134`) has the LLM free-write prose and a downstream deterministic `output_contains` gate parse a fixed sentinel (e.g. `NO_REGRESSION`) out of it, rather than using the executor's structured-evaluator machinery to grade the prose directly. This is a viable third shape for the fixture's evaluator, distinct from either scaffold generator's `llm_structured` states.

## Integration Map

### Files to Modify
- A new fixture file holding the ENH-3300 issue body — location undecided. It must not
  live in `.issues/`, since it is not real work and would pollute the backlog
- A new eval/verification loop YAML, if `/ll:create-eval-from-issues` or
  `/ll:verify-issue-loop` is the chosen mechanism

_Wiring pass added by `/ll:wire-issue` — conditional on Step 1's mechanism decision:_
- `scripts/little_loops/cli/loop/__init__.py` (~972-1019) — `scaffold-eval`/`scaffold-verify`
  argparse blocks (`--issues`, positional `issue_id`); needs a new flag only if a
  scaffold-local file-path override is the chosen path around the resolver gap below
- `docs/reference/CLI.md` — `ll-loop scaffold-eval` (~1025-1031) and `ll-loop scaffold-verify`
  (~1043-1049) flag tables; needs a new row under the same condition
- `scripts/little_loops/loops/README.md` catalog table — needs an entry only if the new
  loop ships as a built-in under `scripts/little_loops/loops/` rather than a private
  fixture location

### Dependent Files (Callers/Importers)
- `skills/wire-issue/SKILL.md` § 8b and
  `skills/wire-issue/caller-suitability-gate.md` — the rule under test. Any edit to
  either is what the fixture exists to catch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_scaffold_core.py:46-57` — `resolve_issue(issue_id)`
  delegates through `_resolve_issue_id` (`cli/issues/show.py:39-60`) to
  `issue_parser.py:92` `resolve_issue_path()`, which only accepts the three ID-string
  formats (`"518"`, `"FEAT-518"`, `"P3-FEAT-518"`) — confirmed no branch treats
  `user_input` as an existing file path. This directly determines Implementation Step 1:
  as written, neither `/ll:create-eval-from-issues` nor `/ll:verify-issue-loop` can point
  at a fixture file outside `.issues/` without (a) extending the shared
  `resolve_issue_path()` (also used by `ll-issues show`/`path`/`set-status` and
  `sprint.py:_find_issue_path` — a shared-surface change), or (b) adding a scaffold-local
  bypass flag in `scaffold_verify.py`/`scaffold_eval.py`/`_scaffold_core.py` only
- `scripts/little_loops/cli/loop/scaffold_verify.py:279` — sole call site of
  `resolve_issue()` inside scaffold-verify
- `scripts/little_loops/cli/loop/scaffold_eval.py:246` — the only other call site of
  `resolve_issue()` in the repo
- `.gemini/skills/wire-issue/SKILL.md`, `.gemini/skills/wire-issue/caller-suitability-gate.md`,
  `.kimi-code/skills/wire-issue/SKILL.md`, `.kimi-code/skills/wire-issue/caller-suitability-gate.md`,
  `.qwen/skills/wire-issue/SKILL.md`, `.qwen/skills/wire-issue/caller-suitability-gate.md` —
  host mirrors of the gate under test; `scripts/tests/test_wiring_skills_and_commands.py:376-391`
  enforces content parity against the canonical files, so a § 8b regression could
  originate in a mirror edit, not only the canonical `skills/wire-issue/` copy. Note also:
  `caller-suitability-gate.md:52-90`'s "Worked example" phrases the injection bullet as
  naming `suggest_gitignore_patterns()`'s own `untracked_files=` parameter, while this
  issue's Codebase Research Findings and Implementation Steps target
  `cli/gitignore.py:55` (the caller one hop further up) — both are defensible readings of
  "the seam," but the fixture and the worked example should agree on which one before
  either is treated as ground truth

### Similar Patterns
- `/ll:create-eval-from-issues` and `/ll:verify-issue-loop` both already generate FSM
  YAML from issue content; check which handles a prose-compliance assertion better
- The ENH-3258 § Session Log entry records the full fixture body, ground truth, and both
  the pass and fail outputs — reuse it rather than reconstructing

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/scaffold_verify.py` `_criteria_states()`/
  `_adversarial_states()` — the concrete generated-loop shape to follow if the two halves
  (suppression, injection) become independent criteria: one `llm_structured` state per
  criterion, ENH-3200 no-short-circuit routing (every non-final verdict routes to the
  *next* criterion, not to a shared `failed` terminal), and a final deterministic
  `verify-aggregate` `action_type: shell` state using `output_contains` that names every
  criterion that did not pass. Confirmed end-to-end in
  `scripts/tests/test_ll_loop_scaffold_verify.py` (`TestCriteriaModeNoShortCircuit`,
  `TestAggregateExecutionEndToEnd`, lines 227-397)
- `scripts/little_loops/loops/rn-remediate.yaml:616`, `autodev.yaml:795,1753`,
  `recursive-refine.yaml:624`, `refine-to-ready-issue.yaml:268` — five existing loops
  invoke `/ll:wire-issue ... --auto` today; none invoke `--dry-run`. No prior art exists
  for a loop that dry-runs wire-issue and asserts on its output — this fixture would be
  the first

### Tests
- Not pytest-assertable by design. The completion gate is the fixture running and
  reproducing the recorded verdict, not a new test in `scripts/tests/`

_Wiring pass added by `/ll:wire-issue` — closest existing pattern to model the fixture's
harness after, not a required pytest change:_
- `scripts/tests/test_ll_loop_scaffold_verify.py` — exercises `scaffold_verify.py` via an
  inline `_write_issue(tmp_path, ...)` helper (lines 33-58) that writes a synthetic issue
  directly under a `tmp_path/.issues/` tree, not via `scripts/tests/fixtures/issues/` —
  shows the existing convention is generate-on-the-fly, not a checked-in fixture file
- `scripts/tests/test_ll_loop_scaffold_eval.py` — sibling pattern for `scaffold_eval.py`
- `scripts/tests/test_cli_loop_dispatch.py:53-54,147-174` — confirms `scaffold-eval`/
  `scaffold-verify` are the only two CLI entry points that reach `resolve_issue()`

### Documentation
- None expected unless a new loop is added to the built-in catalog

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `scripts/little_loops/git_operations.py:389` — `suggest_gitignore_patterns(untracked_files: list[str] | None = None, repo_root: Path | str = ".", logger: Logger | None = None) -> GitignoreSuggestion` (confirmed signature); guard at `:412` (`if untracked_files is None:`), call at `:413` (`get_untracked_files(repo_root)`) — matches the recorded ground truth exactly.
- `scripts/little_loops/cli/gitignore.py:55`, inside `main_gitignore()` — the confirmed `Inject at` seam: this is the sole production caller of `suggest_gitignore_patterns()` and it passes no `untracked_files=`, so it always falls through to the unfiltered call. `ll-code callers-of`/`callees-of` (codegraph provider, fresh) confirm no other production caller exists.
- `skills/wire-issue/SKILL.md:417-423` — the inline § 8b gate text (kept short to fit the 500-line cap), linking out to the companion at line 423.
- `skills/wire-issue/caller-suitability-gate.md:52-90` — a **second, currently-live copy** of this exact scenario (same symbol, same file:line citations, same expected Markdown bullets), embedded as the companion's "Worked example." This copy was never deleted — only the `.issues/`-resident ENH-3300 fixture file was. Any repeatable fixture must stay in sync with this worked example, since it is the doctrine the gate's own prompt cites as correct behavior.
- `.issues/enhancements/P2-ENH-3258-wire-issue-maps-callers-of-hits-as-change-targets-without-checking-production-path-reachability-or-existing-injection-seams.md` § Session Log, "fixture validation (step 4)" (`:306-336`, issue is `status: done`) — the authoritative source for the fixture body and both recorded PASS/FAIL run outputs; ENH-3259's own Implementation Step 2 already points here.

### Existing fixture-issue storage convention
- `scripts/tests/fixtures/issues/` already holds several synthetic issue files used exactly this way — real issue frontmatter, but living outside `.issues/` and consumed via a direct file path from test code (e.g. `scripts/tests/test_issue_parser_unresolved.py:514-536`, `BUG-3025-*.md`; `FEAT-2339-mixed-resolved-unresolved.md`). There is no separate "deferred"/"test" subdirectory inside `.issues/` used for this purpose anywhere in the codebase — `scripts/tests/fixtures/issues/` is the only precedent.

### Constraint on the proposed mechanism
- Both candidate mechanisms resolve issues through the normal backlog path — `create-eval-from-issues` via `ll-issues show <ID> --json` (`skills/create-eval-from-issues/SKILL.md:186-198`), `verify-issue-loop` via `resolve_issue(issue_id)` (`scripts/little_loops/cli/loop/scaffold_verify.py:279`). Neither has a documented flag to point at an arbitrary file path instead of a resolvable `.issues/`-backed ID. As written today, the Proposed Solution's "checked in as a fixture file rather than living in `.issues/`" is not directly compatible with either mechanism without either extending one of them to accept a file path, or registering the fixture as a real (non-`.issues/`-excluded) issue ID.

## Implementation Steps

1. Decide where the fixture body lives and whether `/ll:create-eval-from-issues` or
   `/ll:verify-issue-loop` is the right mechanism.
2. Restore the ENH-3300 fixture body from ENH-3258's Session Log, with its recorded
   ground truth: `get_untracked_files()`'s sole production caller is
   `git_operations.py:413`, inside `if untracked_files is None:` (`:412`), enclosed by
   `suggest_gitignore_patterns(untracked_files: list[str] | None = None, ...)`.
3. Assert both halves — no `Update ...git_operations.py` bullet for that call site, and
   an `Inject at ...cli/gitignore.py:55` bullet naming the seam.
4. Run it once against the current tree and confirm it reproduces the recorded PASS.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the `resolve_issue()` file-path gap before Step 1 is final: confirm whether the
  fixture will be reachable via a scaffold-local bypass flag in
  `scaffold_verify.py`/`scaffold_eval.py`/`_scaffold_core.py`, or via extending the shared
  `issue_parser.py:92` `resolve_issue_path()` — the latter also affects `ll-issues show`/
  `path`/`set-status` and `sprint.py:_find_issue_path`
- Reconcile the injection-seam target before writing the fixture: `caller-suitability-gate.md:52-90`'s
  worked example names `suggest_gitignore_patterns()`'s own `untracked_files=` parameter;
  this issue's Codebase Research Findings and Step 3 target `cli/gitignore.py:55`. Pick one
  and make the worked example and the fixture agree
- If a CLI flag is added: update `scripts/little_loops/cli/loop/__init__.py` argparse
  blocks (~972-1019) and add the corresponding row to `docs/reference/CLI.md`'s
  `ll-loop scaffold-eval`/`scaffold-verify` flag tables
- If the loop ships as a built-in under `scripts/little_loops/loops/`: add a row to
  `scripts/little_loops/loops/README.md`'s catalog table
- Follow `scaffold_verify.py`'s `_criteria_states()` shape for the two-halves assertion —
  one `llm_structured` criterion per half, ENH-3200 no-short-circuit routing, final
  `verify-aggregate` shell state with `output_contains` — rather than inventing a new
  aggregation shape
- Since no existing loop invokes `/ll:wire-issue --dry-run`, verify the dry-run output
  format directly against a manual run before wiring the FSM's evaluator against it

## Program Design

N/A — `program_design_not_applicable: true`. The deliverable is a fixture body plus an
eval/verification YAML: no types, no signatures, no runtime call path. The one design
fact that matters is the fixture's recorded ground truth, stated in Implementation
Steps step 2.

## Impact

- **Priority**: P3 - the gate works today and the suite stays green; this protects
  against a future regression rather than fixing a present defect
- **Effort**: Small - the fixture body already exists in ENH-3258's Session Log and the
  ground truth is recorded there; the work is choosing a home for it and wiring one eval
  task
- **Risk**: Low - a fixture is additive and touches no production path. The real risk is
  doing nothing: the gate's only validation to date is one manual run
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: making the ENH-3258 gate re-runnable on demand.
- **Out of scope**: changing the gate itself, and asserting the fixture in the pytest
  suite — a prose-compliance check is not a unit test.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-20T03:48:45 - `289c2226-7e0b-4996-8d1c-0bc8cd8ed8f7.jsonl`
- `/ll:refine-issue` - 2026-08-20T03:40:49 - `0a4bff26-6c74-4fcb-929e-2b4abc66f29f.jsonl`
- `/ll:format-issue` - 2026-08-20T03:36:09 - `53335082-8487-448b-88b5-4205fec8f6a0.jsonl`
