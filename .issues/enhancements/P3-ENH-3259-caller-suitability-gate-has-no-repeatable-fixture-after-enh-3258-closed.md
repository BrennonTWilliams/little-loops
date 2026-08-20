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
confidence_score: 90
outcome_confidence: 50
score_complexity: 14
score_test_coverage: 0
score_ambiguity: 18
score_change_surface: 18
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
any edit to § 8b or its companion. Concretely:

- A checked-in fixture issue body exists outside `.issues/` and is not visible to the
  backlog in steady state.
- A single command runs `/ll:wire-issue <fixture> --dry-run` against the current tree and
  captures its emitted Wiring Phase to a run-scoped artifact.
- The **record half** is asserted deterministically: the captured output contains a
  `### Dependent Files` entry citing `scripts/little_loops/git_operations.py:413`. This is
  the positive half of the gate's own "always emit both halves" rule
  (`caller-suitability-gate.md:40-50`) and doubles as the run's liveness precondition —
  see the vacuous-pass decision under Proposed Solution.
- The **suppression half** is asserted deterministically: the captured output contains no
  `Update` bullet for `scripts/little_loops/git_operations.py`.
- The **injection half** is asserted deterministically: the captured output contains an
  `Inject at` bullet naming `scripts/little_loops/cli/gitignore.py:55`.
- All three gates are evaluated on every run; none short-circuits the others, and the run
  reports which gate(s) failed.
- The fixture leaves no residue in `.issues/` after the run, including on failure — and any
  residue that a hard kill does leave is gitignored and cleared idempotently by the next
  run's staging state.

## Motivation

ENH-3258's own risk note says the failure mode is "an LLM under-applying a prose rule
inside a 493-line prompt." That risk does not end at merge — it recurs on every
subsequent edit to the file. The one-shot fixture proved the rule works once; it
provides nothing thereafter.

Both halves need coverage, and they fail differently:
- **Suppression** — no `Update <path>` bullet for the guarded call site.
- **Injection** — an `Inject at <path>` bullet naming the production caller that supplies
  the value (`cli/gitignore.py:55`), not the parameter itself. This half was
  added only after the clean fixture showed the rule was purely subtractive, so it is
  the newer and less-exercised of the two.

## Proposed Solution

Check the fixture body in (as `ENH-9999`) under `scripts/tests/fixtures/issues/` (it is not
real work and must not appear in the backlog), and drive it from a **hand-written FSM loop**
in the `loops/prompt-regression-test.yaml` shape: an execute state that runs
`/ll:wire-issue ENH-9999 --dry-run` and captures its output to `${context.run_dir}/`,
followed by three deterministic `output_contains` gates — record, suppression, injection —
and an aggregate state that names whichever gate(s) failed.

Because wire-issue resolves its argument through `ll-issues path` (see the resolver
constraint below), the loop **stages the fixture into `.issues/enhancements/` for the
duration of the run and removes it on every exit path**, rather than teaching any resolver
to accept a file path.

> **Selected (supersedes the 2026-08-20 `/ll:confidence-check` selection of
> `/ll:verify-issue-loop`):** a hand-written loop in the `prompt-regression-test.yaml`
> shape, with ephemeral `.issues/` staging. Rationale — three findings, each verified
> against the tree on 2026-08-19:
>
> 1. **`verify-issue-loop` has no execute phase.** `scaffold_verify.py:111-150` generates
>    states whose action is *"Verify acceptance criterion N for `<ISSUE>`: `<text>` …
>    Report what you observed"* and whose evaluator asks *"Does the implementation satisfy
>    criterion N?"* — a check that an issue's ACs are **already implemented in the tree**.
>    Nothing in the generated loop ever invokes `/ll:wire-issue --dry-run`. The
>    `<EXECUTE_PROMPT>` placeholder that `create-eval-from-issues` was rejected for is
>    precisely the step this fixture requires.
> 2. **The two roles collide in one file.** Pointing scaffold-verify at the fixture makes
>    the *fixture's own* ACs the criteria — but those ACs are "thread a config-sourced
>    `exclude_patterns` list into `get_untracked_files()`", i.e. the **stimulus** wire-issue
>    processes, not the two-halves assertion. One file cannot be both stimulus and
>    assertion spec; a hand-written loop keeps the assertion in the YAML where it belongs.
> 3. **The assertion does not need an LLM evaluator.** Both halves are literal-substring
>    checks over captured text, so `output_contains` gates them deterministically. This
>    strengthens the issue's "not pytest-assertable" framing to "not pytest-assertable,
>    but deterministically gated" — only the stimulus is non-deterministic.
>
> Consequence: the scaffold-local bypass flag, its `cli/loop/__init__.py` argparse row, and
> its `docs/reference/CLI.md` row are all **dropped** — see the superseded decision under
> Dependent Files. Decided 2026-08-19 (review round).

> **Prompt contamination — what this fixture can and cannot prove (decided 2026-08-19,
> second review round).** The fixture scenario and
> `caller-suitability-gate.md:52-90`'s **Worked example** are the *same scenario* — same
> symbol, same guard, same signature, same expected bullets. The worked-example correction
> (step 2) then rewrites it to name `scripts/little_loops/cli/gitignore.py:55`, which is
> precisely the substring the injection gate asserts — so after step 2 the answer is
> **verbatim in the prompt the model reads**. Same class of contamination as ENH-3000, but
> located in the companion doc rather than the fixture body, so Step 1's cleanliness rule
> does not catch it.
>
> Two resolutions were considered:
>
> - **(a) Re-scenario.** Build the fixture on a *different* real symbol with the same shape
>   (guard-branch call + parameter seam + single production caller), leaving the worked
>   example as independent doctrine. Yields a genuine generalization probe; costs a
>   discovery pass to find a second qualifying symbol.
> - **(b) Narrow the claim.** Keep the scenario and scope the fixture to what it actually
>   detects.
>
> **Selected: (b).** Rationale: this issue's own stated threat model is "a
> companion-extraction that drops the `Inject at <path>` clause to fit the 500-line cap"
> (Summary) — i.e. *deletion*, not subtle drift. A deletion detector covers that threat
> fully, and (b) costs nothing. Consequence: the fixture is a **§ 8b / companion deletion
> and gross-regression detector**, not a proof that the rule generalizes to unseen call
> shapes. Scope Boundaries states this explicitly and must not be softened. **(a) remains
> the upgrade path** — it is a fixture-body swap plus new gate substrings, no change to the
> loop shape — and should be taken if the gate is ever edited in a way that changes its
> reasoning rather than its presence.

> **Vacuous-pass hazard on the suppression gate (decided 2026-08-19, second review round).**
> `output_contains` with `negate: true` on "an `Update` bullet citing `git_operations.py`"
> returns `yes` for an empty capture, an errored wire-issue run, or a run that emitted no
> Wiring Phase at all — a broken run scores as a pass on that half. Fix: assert the gate's
> *positive* first half as a third deterministic gate (a `### Dependent Files` entry citing
> `git_operations.py:413`, mandated by `caller-suitability-gate.md:40-50`). That converts
> suppression from a bare negation into a positively-verified claim and supplies the run's
> liveness precondition at no extra cost.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **`/ll:create-eval-from-issues`** (`skills/create-eval-from-issues/SKILL.md:229-266`) synthesizes a single `llm_structured` evaluation-criteria prompt graded for *user-experience quality*, not implementation conformance — it explicitly states it never emits `check_stall`/`check_concrete`/`check_semantic`/`check_invariants`, and its evaluation prompt requires an agent to author free-text `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>` placeholders (via `ll-loop scaffold-eval --issues <IDS> --json`, output to `.loops/<name>.yaml`). A `--dsl` mode also exists, generating exact-match/graded fill-in-the-blank tasks under `evals/dsl/<source>/`, graded via `ll-harness dsl` against an `expected:` mapping — a different mechanism from the FSM harness path.
- **`/ll:verify-issue-loop`** (`skills/verify-issue-loop/SKILL.md:33-70`, `scripts/little_loops/cli/loop/scaffold_verify.py:111-156`) emits one `llm_structured` state **per Acceptance Criterion**, fully determined by the issue's own criterion text with no placeholder-authoring step (via `ll-loop scaffold-verify "$ISSUE_ID" [--adversarial] --json`, output to `.loops/<PREFIX>-<issue-id-lower>-<title-slug>.yaml`). This asserts against implementation conformance, which is the shape this issue's two-halves check needs. Its aggregate stage (`scaffold_verify.py:67-156`) routes every criterion's verdict forward without short-circuiting, then a final deterministic shell state inspects each captured verdict and reports every criterion that did not pass — established precedent in this codebase for asserting the suppression half and the injection half as two independent criteria routed into one aggregate gate, rather than either failing the run early.
- A third, structurally different precedent exists: `scripts/little_loops/loops/prompt-regression-test.yaml` (cataloged in `scripts/little_loops/loops/README.md:128-134`) has the LLM free-write prose and a downstream deterministic `output_contains` gate parse a fixed sentinel (e.g. `NO_REGRESSION`) out of it, rather than using the executor's structured-evaluator machinery to grade the prose directly. This is a viable third shape for the fixture's evaluator, distinct from either scaffold generator's `llm_structured` states.

## Integration Map

### Files to Modify
- A new fixture file holding the fixture issue body, under
  `scripts/tests/fixtures/issues/` (matching the existing convention — see "Existing
  fixture-issue storage convention" below). It must not live in `.issues/` in steady
  state, since it is not real work and would pollute the backlog.
  > **Selected: the fixture carries a reserved high ID, `ENH-9999`, not `ENH-3300`
  > (decided 2026-08-19, second review round).** `get_next_issue_number()`
  > (`issue_parser.py:2461`) allocates sequentially and will hand `3300` to a real issue
  > eventually; ephemeral staging would then collide with live backlog work — silently, at
  > whichever run happens to follow that allocation. `resolve_issue_path()`
  > (`issue_parser.py:92`) keys only on the `TYPE-NNN` shape, so a reserved high number
  > costs nothing and nothing else changes. `ENH-3300` remains the correct name for the
  > *historical* one-shot run recorded in ENH-3258's Session Log; it is not the fixture's ID
  > going forward
- A new hand-written FSM loop YAML (mechanism locked — see Proposed Solution decision):
  stage fixture → `/ll:wire-issue --dry-run` → three `output_contains` gates (record,
  suppression, injection) → aggregate → unstage
  > **Selected: the loop lives at `scripts/tests/fixtures/loops/`, not in the built-in
  > catalog (decided 2026-08-19, second review round).** `resolve_loop_path()`
  > (`fsm/loop_paths.py:21-23`) returns any path that exists *before* consulting any loops
  > dir, so `ll-loop run scripts/tests/fixtures/loops/<name>.yaml` works directly against a
  > path. Rationale: this is a fixture, not a shipped loop — a fixtures location keeps it
  > out of `test_builtin_loops.py`'s validation sweep over
  > `scripts/little_loops/loops/`, and drops the conditional README row entirely
- `.gitignore` — add an ignore entry for the staged fixture path
  (`.issues/enhancements/*ENH-9999-*`). Required, not optional: FSM `on_failure`/`on_error`
  routing cannot cover SIGINT, a timeout kill, or `max_steps` exhaustion, so in-loop
  cleanup alone cannot deliver the "no residue" criterion. See Implementation Steps step 3

_Superseded by the mechanism decision (2026-08-19) — no longer in scope:_
- ~~`scripts/little_loops/cli/loop/__init__.py` (~972-1019) — `scaffold-verify` argparse
  block; add the file-path bypass flag~~
- ~~`docs/reference/CLI.md` — `ll-loop scaffold-verify` (~1043-1049) flag table; add a row
  for the new flag~~

### Dependent Files (Callers/Importers)
- `skills/wire-issue/SKILL.md` § 8b and
  `skills/wire-issue/caller-suitability-gate.md` — the rule under test. Any edit to
  either is what the fixture exists to catch

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/SKILL.md:88` (Phase 2) — **the resolver gap that actually matters.**
  wire-issue locates its target via `FILE=$(ll-issues path "${ISSUE_ID}")`, which delegates
  to `_resolve_issue_id` (`cli/issues/show.py:39-60`) → `issue_parser.py:92`
  `resolve_issue_path()` — three ID-string formats only (`"518"`, `"FEAT-518"`,
  `"P3-FEAT-518"`), searching only the `.issues/` category dirs. A fixture living under
  `scripts/tests/fixtures/issues/` is therefore unreachable **by wire-issue**, which is the
  tool that must consume it.
  > **Selected:** ephemeral staging — the loop copies the fixture into
  > `.issues/enhancements/` before the wire-issue state and removes it in a cleanup state
  > wired onto every exit path (success, failure, error). Rationale: zero production
  > change, and it fixes the gap on the tool that has it. The previously-selected
  > scaffold-local bypass flag was on `_scaffold_core.resolve_issue()`, which only
  > `scaffold-eval`/`scaffold-verify` reach (`test_cli_loop_dispatch.py:53-54,147-174`) —
  > wire-issue never calls it, so that flag would have unblocked nothing. Cost of the
  > chosen path: a crashed run can leave a phantom untracked backlog entry, so cleanup must
  > be unconditional and the staged path should be gitignored. Decided 2026-08-19 (review
  > round), superseding the `/ll:confidence-check` decision of 2026-08-20.
- ~~`scripts/little_loops/cli/loop/_scaffold_core.py:46-57` / `scaffold_verify.py:279` /
  `scaffold_eval.py:246`~~ — out of scope under the mechanism decision; no scaffold code
  is touched
- `.gemini/skills/wire-issue/SKILL.md`, `.gemini/skills/wire-issue/caller-suitability-gate.md`,
  `.kimi-code/skills/wire-issue/SKILL.md`, `.kimi-code/skills/wire-issue/caller-suitability-gate.md`,
  `.qwen/skills/wire-issue/SKILL.md`, `.qwen/skills/wire-issue/caller-suitability-gate.md` —
  host mirrors of the gate under test; `scripts/tests/test_wiring_skills_and_commands.py:376-391`
  enforces content parity against the canonical files, so a § 8b regression could
  originate in a mirror edit, not only the canonical `skills/wire-issue/` copy.
  > **Selected:** `cli/gitignore.py:55` is the ground-truth seam, not
  > `suggest_gitignore_patterns()`'s own `untracked_files=` parameter. Rationale: this
  > issue's Codebase Research Findings confirm via `ll-code callers-of`/`callees-of`
  > (fresh) that `cli/gitignore.py:55` is the sole production caller of
  > `suggest_gitignore_patterns()`, one hop up from the parameter itself — that is the
  > actual injection point wire-issue would touch. `caller-suitability-gate.md:52-90`'s
  > worked example is stale and must be corrected to name `cli/gitignore.py:55` to match
  > the canonical `skills/wire-issue/` copy and its host mirrors. Decided
  > `/ll:confidence-check` — 2026-08-20.
  >
  > **Sharpened 2026-08-19 (review round):** this is a *format violation*, not an
  > ambiguity. `caller-suitability-gate.md:45-50` mandates the form `Inject at <path>`;
  > the worked example's bullet emits `Inject at suggest_gitignore_patterns()'s existing
  > untracked_files= parameter` — **naming no path at all**, in breach of its own rule.
  > The prose immediately below that bullet already reads "the production callers of *that*
  > function are where the filtered list must be supplied", so the doctrine is correct and
  > only the bullet is wrong. Step 2 fixes the bullet; the surrounding prose stands.

### Similar Patterns
- `scripts/little_loops/loops/prompt-regression-test.yaml` — **the shape to copy**: LLM
  free-writes, a downstream deterministic `output_contains` gate parses a fixed sentinel
  out of it. Cataloged in `scripts/little_loops/loops/README.md:128-134`
- The ENH-3258 § Session Log entry records the ground truth and both the pass and fail
  outputs — but **not** the fixture body (see the corrected finding under Codebase
  Research Findings). The body must be authored from that ground truth

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/scaffold_verify.py` `_criteria_states()` — not the
  mechanism (see Proposed Solution), but still the **routing precedent to copy by hand**:
  ENH-3200 no-short-circuit routing (every non-final verdict routes to the *next* check,
  not to a shared `failed` terminal), and a final deterministic aggregate
  `action_type: shell` state using `output_contains` that names every check that did not
  pass. Confirmed end-to-end in `scripts/tests/test_ll_loop_scaffold_verify.py`
  (`TestCriteriaModeNoShortCircuit`, `TestAggregateExecutionEndToEnd`, lines 227-397)
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
- `.issues/enhancements/P2-ENH-3258-wire-issue-maps-callers-of-hits-as-change-targets-without-checking-production-path-reachability-or-existing-injection-seams.md` § Session Log, "fixture validation (step 4)" (`:306-336`, issue is `status: done`) — the authoritative source for the fixture's **ground truth** and both recorded PASS/FAIL run outputs.
  > **Corrected 2026-08-19 (review round):** the earlier claim that this Session Log "records the full fixture body" is **false** — verified by reading `:306-336`. The only ENH-3300 mention in the whole 459-line file is `:317`, and it records the ground truth (sole caller `git_operations.py:413`, guard `:412`, enclosing signature), the two verdicts, and the `cli/gitignore.py:55` observation from the post-fix re-run. **No fixture body is stored anywhere.** Step 1 is therefore *authoring* a body faithful to that ground truth, not restoring one — which is what moves Effort off "Small".

### Existing fixture-issue storage convention
- `scripts/tests/fixtures/issues/` already holds several synthetic issue files used exactly this way — real issue frontmatter, but living outside `.issues/` and consumed via a direct file path from test code (e.g. `scripts/tests/test_issue_parser_unresolved.py:514-536`, `BUG-3025-*.md`; `FEAT-2339-mixed-resolved-unresolved.md`). There is no separate "deferred"/"test" subdirectory inside `.issues/` used for this purpose anywhere in the codebase — `scripts/tests/fixtures/issues/` is the only precedent.

### Constraint on the proposed mechanism
- **`/ll:wire-issue` itself is the binding constraint** (`skills/wire-issue/SKILL.md:88`): Phase 2 resolves via `ll-issues path "${ISSUE_ID}"`, and Phase 1 extracts `ISSUE_ID` as "the first non-flag token" — there is no path-accepting branch. `resolve_issue_path()` (`issue_parser.py:92`) accepts three ID formats and searches only the `.issues/` category dirs plus legacy `completed_dir`/`deferred_dir`. Whatever generates the assertion YAML, the fixture must be **resolvable as a `.issues/`-backed ID at the moment wire-issue runs**. Hence ephemeral staging (Dependent Files decision) rather than a resolver change.
- The two scaffold generators carry the same limitation one layer over — `create-eval-from-issues` via `ll-issues show <ID> --json` (`skills/create-eval-from-issues/SKILL.md:186-198`), `verify-issue-loop` via `resolve_issue(issue_id)` (`scaffold_verify.py:279`) — but that is now moot: neither is the selected mechanism.

## Implementation Steps

> **Step order matters (corrected 2026-08-19, second review round).** The worked-example
> correction now runs **before** the output-pinning step. In the prior ordering, pinning ran
> first and the correction then edited the very prompt text the model reads, changing the
> output the gate substrings had just been pinned against. Do not restore the old order; if
> `caller-suitability-gate.md` is touched for any reason after pinning, re-pin.

1. **Author** the fixture body as `ENH-9999` under `scripts/tests/fixtures/issues/`,
   faithful to the ground truth recorded in ENH-3258's Session Log (the body itself is not
   recorded there — see the corrected finding above). Ground truth: the fixture asks to
   thread a config-sourced `exclude_patterns` list into `get_untracked_files()`, whose sole
   production caller is `git_operations.py:413`, inside `if untracked_files is None:`
   (`:412`), enclosed by
   `suggest_gitignore_patterns(untracked_files: list[str] | None = None, ...)`. The body
   must say **nothing** about guards, fallbacks or seams — that contamination is exactly
   what invalidated the ENH-3000 run. (Contamination via the *companion doc* is a separate,
   accepted limitation — see the prompt-contamination decision under Proposed Solution.)
2. Correct `caller-suitability-gate.md`'s worked-example `Inject at` bullet to name
   `scripts/little_loops/cli/gitignore.py:55` — a format violation of its own
   `Inject at <path>` rule at `:45-50`, not merely a stale reference (see the sharpened
   decision above). Leave the surrounding prose alone. Then propagate to the
   `.gemini`/`.kimi-code`/`.qwen` mirrors per
   `test_wiring_skills_and_commands.py:376-391`'s parity check and re-run that test.
3. Add the staged-path ignore entry (`.issues/enhancements/*ENH-9999-*`) to `.gitignore`
   **before** the first staged run, so a crashed run cannot dirty the working tree.
4. Run `/ll:wire-issue ENH-9999 --dry-run` manually once — against the tree **as corrected
   by step 2** — and record the literal shape of its emitted Wiring Phase and Dependent
   Files bullets. No existing loop dry-runs wire-issue, so the gate substrings must be
   derived from observed output, not assumed.
5. Hand-write the FSM loop under `scripts/tests/fixtures/loops/`: `stage-fixture` (shell;
   `rm -f` the staged path first, then copy the fixture into `.issues/enhancements/` — the
   pre-clean is what makes staging idempotent after a hard kill) → `run-wire-issue`
   (capture dry-run output to `${context.run_dir}/wiring.txt`) → `gate-record`
   (`output_contains`, requires a `### Dependent Files` entry citing
   `git_operations.py:413`) → `gate-suppression` (`output_contains` with `negate: true`,
   fails if an `Update` bullet cites `git_operations.py`) → `gate-injection`
   (`output_contains`, requires an `Inject at` bullet citing `cli/gitignore.py:55`) →
   `aggregate` (names whichever gate(s) failed) → `unstage-fixture`. All three gates run on
   every path (ENH-3200 no-short-circuit routing); `unstage-fixture` is wired onto success,
   failure and error exits.
   > **Escape the gate patterns as regex.** `evaluate_output_contains()`
   > (`fsm/evaluators.py:470-473`) tries `re.search` **first** and falls back to substring
   > matching only when the pattern fails to *compile* — never on a no-match. So `.` in
   > `git_operations.py` is a wildcard, and any pattern containing `()` (e.g.
   > `suggest_gitignore_patterns()`) compiles as an empty group that matches everything,
   > yielding a permanently-true gate. Write every gate pattern as escaped regex and keep
   > bare parens out of them.
6. Run the loop once against the current tree and confirm it reproduces the recorded PASS,
   then confirm `git status` is clean — no staged fixture residue in `.issues/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Issue-resolution gap: implement via **ephemeral `.issues/` staging** (Dependent Files
  decision) — the gap is in `/ll:wire-issue` Phase 2, not in `_scaffold_core.resolve_issue()`
- Injection-seam target: implement via the `cli/gitignore.py:55` decision above — update
  the worked example, not the fixture
- ~~If the loop ships as a built-in under `scripts/little_loops/loops/`: add a row to
  `scripts/little_loops/loops/README.md`'s catalog table~~ — **moot**: the loop lives at
  `scripts/tests/fixtures/loops/` (decided under Files to Modify), so no catalog row exists
  to add
- Borrow `scaffold_verify.py`'s `_criteria_states()` **routing** shape by hand — ENH-3200
  no-short-circuit routing plus a final aggregate shell state with `output_contains` —
  rather than inventing a new aggregation shape or generating the YAML from a scaffold
- Since no existing loop invokes `/ll:wire-issue --dry-run`, verify the dry-run output
  format directly against a manual run before wiring the gates against it (step 4)
- `ll-loop validate` must pass on the new YAML.
  > **Corrected 2026-08-19 (second review round).** The prior claim — "this loop targets a
  > *skill* (wire-issue), so per-run artifact isolation is mandatory and the
  > `output_contains` gates satisfy the non-LLM-evaluator rule" — is **false on the
  > mechanism**. `_is_meta_loop()` (`fsm/validation/meta_rules.py:48-70`) classifies by
  > **action-string** regex (`skills/[\w-]+/SKILL\.md`, `loops/[\w-]+\.yaml`,
  > `agents/[\w-]+\.md`, `commands/[\w-]+\.md`, `\.claude/(CLAUDE\.md|settings)`) plus the
  > tokens `yaml_state_editor` / `replace_action`. This loop's actions — a `cp` of a fixture
  > and `/ll:wire-issue ENH-9999 --dry-run` — match none of them, so the loop is **not**
  > classified as a meta-loop and MR-1/MR-2 never fire. Separately, MR-3 is not meta-gated
  > at all: `_validate_artifact_isolation()` (`:191-222`) runs on every loop and fires only
  > on hardcoded `.loops/tmp/` paths (`_SHARED_TMP_PATH_RE`, `:36`). Writing artifacts under
  > `${context.run_dir}/` remains correct practice and is still required by this issue's
  > Expected Behavior — but it is a self-imposed constraint here, not a validator-enforced
  > one. Do not go looking for enforcement that does not exist

_Superseded by the mechanism decision (2026-08-19):_
- ~~Update `scripts/little_loops/cli/loop/__init__.py` argparse blocks (~972-1019) for the
  new `scaffold-verify` flag, and add the corresponding row to `docs/reference/CLI.md`~~

## Program Design

N/A — `program_design_not_applicable: true`. The deliverable is a fixture body plus a
hand-written loop YAML: no types, no signatures, no runtime call path (the mechanism
decision removed the last production-code touchpoint). The one design fact that matters is
the fixture's recorded ground truth, stated in Implementation Steps step 1.

## Impact

- **Priority**: P3 - the gate works today and the suite stays green; this protects
  against a future regression rather than fixing a present defect
- **Effort**: Medium - revised upward. The Session Log records the ground truth but **not**
  the fixture body, so the body is authored rather than restored; and the loop is
  hand-written rather than scaffold-generated. Offsetting that, no production code changes
  at all (the bypass flag, argparse row and CLI.md row are dropped)
- **Risk**: Low - the deliverable is a fixture plus a loop YAML and touches no production
  path. Two live hazards, both mitigated in Implementation Steps: (1) ephemeral `.issues/`
  staging leaving residue if a run is hard-killed before its cleanup state — mitigated by
  unconditional cleanup routing **plus** the `.gitignore` entry and the `rm -f` pre-clean in
  `stage-fixture`, since FSM error routing cannot cover SIGINT or a timeout kill; (2) a
  silently vacuous suppression gate — mitigated by the added positive `gate-record`. The
  residual, accepted limitation is evidential rather than operational: the fixture is a
  deletion detector, not a generalization probe (see Scope Boundaries). The real risk is
  doing nothing: the gate's only validation to date is one manual run
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: making the ENH-3258 gate re-runnable on demand, as a **§ 8b / companion
  deletion and gross-regression detector**.
- **Explicitly NOT claimed**: that the fixture proves the gate *generalizes*. The fixture
  reuses `caller-suitability-gate.md`'s own worked-example scenario, and step 2 puts the
  injection gate's expected substring verbatim into the prompt under test — so a passing run
  shows the rule is present and being applied to its documented example, not that it
  transfers to an unseen call shape. This wording is load-bearing; see the
  prompt-contamination decision under Proposed Solution before softening it. Option (a)
  there is the upgrade path if a generalization probe is later wanted.
- **Out of scope**: changing the gate itself, and asserting the fixture in the pytest
  suite — a prose-compliance check is not a unit test.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-08-19_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 50/100 → LOW

### Outcome Risk Factors (current run)
- Change surface is mixed rather than a clean isolated change or a pure mechanical
  sweep: ~9 distinct sites (fixture file, hand-written loop YAML, conditional README
  row, `caller-suitability-gate.md` correction, 6 host-mirror files) span new-artifact
  authoring plus a small enumerated fanout — Criterion D scored 18/25, not the 25/25 an
  isolated or fully-verified sweep would earn.
- No `scripts/tests/` coverage exists or is planned for this deliverable by design (the
  gate is prose-driven, not pytest-assertable) — Criterion B is 0/25. The loop's
  `output_contains` gates are deterministic but live outside the pytest suite.
- The dry-run output format of `/ll:wire-issue --dry-run` is unobserved by any existing
  loop; step 4 requires pinning the gate substrings against a real run before the loop
  can be trusted — residual execution-verification risk, not a design-decision gap
  (`unapplied_decision` check is clean).

_Prior note (2026-08-19, superseded above): Readiness 85/100 → PROCEED WITH CAUTION;
Outcome 49/100 → LOW._

### Concerns

_All three concerns below were **resolved** in the 2026-08-19 review round; retained for
provenance. Struck text is no longer live._

- ~~Implementation Step 1 defers the core architecture decision (which mechanism) to
  implementation time~~ → **Resolved**, but not as the 2026-08-20 check concluded. Both
  scaffold generators were rejected: `verify-issue-loop` has no execute phase and would
  never invoke wire-issue at all. Mechanism is now a hand-written loop in the
  `prompt-regression-test.yaml` shape — see Proposed Solution.
- ~~The `resolve_issue()` file-path gap has two candidate fixes~~ → **Resolved and
  relocated.** The gap was diagnosed on the wrong tool: wire-issue resolves via
  `ll-issues path` (`SKILL.md:88`), never via `_scaffold_core.resolve_issue()`. Fixed by
  ephemeral `.issues/` staging; no resolver is modified.
- ~~The injection-seam target is inconsistent~~ → **Resolved.** `cli/gitignore.py:55`
  confirmed as the sole production caller; the worked example's bullet is a format
  violation of the gate's own `Inject at <path>` rule and is corrected in step 2.

### Outcome Risk Factors

_Revised 2026-08-19:_

- ~~No automated test coverage by design~~ → **Reduced.** Both assertion halves are now
  literal-substring `output_contains` gates, so only the stimulus (an LLM running
  wire-issue) is non-deterministic; grading is deterministic. Still not a `scripts/tests/`
  addition, by design.
- ~~Multiple open design questions add judgment-call risk~~ → **Closed**; all three are
  decided above.
- ~~Depth escalates to cross-module if the shared resolver is extended~~ → **Eliminated**;
  no production module is touched under the selected mechanism.
- **New:** the fixture body must be authored from ground truth rather than restored (it is
  not recorded anywhere), and it must be *uncontaminated* — any mention of guards,
  fallbacks or seams in the body reproduces the ENH-3000 failure where the answer was in
  the input.
- **New:** the dry-run output format is unobserved by any existing loop, so the gate
  substrings are guesswork until step 4 pins them against a real run.
- **New (second review round):** the fixture reuses the gate companion's own worked-example
  scenario, so a PASS proves presence-and-application, not generalization. Accepted and
  scoped in Scope Boundaries; option (a) under Proposed Solution is the upgrade path.

## Session Log
- review round (second) - 2026-08-19 - **six corrections, all verified against the tree.**
  (1) *Prompt contamination*: the fixture scenario is `caller-suitability-gate.md:52-90`'s
  own worked example, and the (then-)step-4 correction puts the injection gate's expected
  substring verbatim into the prompt under test. Resolved by narrowing the claim — the
  fixture is a deletion/gross-regression detector, not a generalization probe; re-scenario
  recorded as the upgrade path. (2) *Vacuous suppression gate*: `negate: true` passes on an
  empty or errored capture; added a third positive `gate-record` asserting the Dependent
  Files entry mandated by `caller-suitability-gate.md:40-50`, which also supplies a liveness
  precondition. (3) *Regex-first evaluator*: `evaluate_output_contains()`
  (`fsm/evaluators.py:470-473`) falls back to substring only on compile error, so `()` in a
  pattern yields an always-true gate — gate patterns must be escaped regex. (4) *Meta-loop
  rationale was false*: `_is_meta_loop()` (`meta_rules.py:48-70`) is action-string based and
  will not classify this loop; MR-1/MR-2 never fire and MR-3 is not meta-gated. (5) *Step
  order*: the worked-example correction now precedes output-pinning, which it previously
  invalidated. (6) *Fixture ID*: `ENH-3300` → reserved `ENH-9999`, since
  `get_next_issue_number()` (`issue_parser.py:2461`) will allocate 3300 to real work.
  Also decided: loop location `scripts/tests/fixtures/loops/` (per `resolve_loop_path()`
  `fsm/loop_paths.py:21-23`), dropping the conditional README row; and `.gitignore` added to
  Files to Modify as a required mitigation, not an optional one.
- `/ll:confidence-check` - 2026-08-20T04:11:29 - `b253f9ca-7946-4d68-ac63-fe6e2061f212.jsonl`
- review round - 2026-08-19 - **mechanism reselected; three verified corrections.** (1)
  `/ll:verify-issue-loop` rejected: `scaffold_verify.py:111-150` generates
  "does the implementation satisfy criterion N" states with no execute phase, so the
  generated loop would never invoke `/ll:wire-issue --dry-run`; and pointing it at the
  fixture would take criteria from the fixture's own ACs, which are the stimulus, not the
  assertion. Replaced with a hand-written loop in the `prompt-regression-test.yaml` shape.
  (2) The resolver gap was on the wrong tool — wire-issue resolves via `ll-issues path`
  (`SKILL.md:88`), never via `_scaffold_core.resolve_issue()`; the scaffold bypass flag,
  its argparse row and its CLI.md row are dropped in favour of ephemeral `.issues/`
  staging. (3) "The fixture body already exists in ENH-3258's Session Log" is false —
  `:306-336` records ground truth and verdicts only; the body must be authored. Effort
  revised Small → Medium; scores updated (ambiguity 10→3, change surface 25→8, outcome
  confidence 49→70).
- `/ll:confidence-check` - 2026-08-20T03:52:52 - `519404c3-823a-450e-a451-9ef539f0b512.jsonl`
- `/ll:wire-issue` - 2026-08-20T03:48:45 - `289c2226-7e0b-4996-8d1c-0bc8cd8ed8f7.jsonl`
- `/ll:refine-issue` - 2026-08-20T03:40:49 - `0a4bff26-6c74-4fcb-929e-2b4abc66f29f.jsonl`
- `/ll:format-issue` - 2026-08-20T03:36:09 - `53335082-8487-448b-88b5-4205fec8f6a0.jsonl`
