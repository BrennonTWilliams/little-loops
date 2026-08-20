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
behavior_parity_not_applicable: true
relates_to:
- ENH-3258
confidence_score: 100
outcome_confidence: 75
score_complexity: 19
score_test_coverage: 8
score_ambiguity: 25
score_change_surface: 23
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
- A single command runs `/ll:wire-issue <fixture> --auto` against the current tree, letting
  it write its findings into the ephemeral staged copy, and archives that written copy to a
  run-scoped artifact. The assertions are made against the **written fixture file**, not
  against wire-issue's stdout — see the dry-run decision under Proposed Solution.
- The **record half** is asserted deterministically: the written fixture contains a
  `### Dependent Files` entry citing `scripts/little_loops/git_operations.py:413`. This is
  the positive half of the gate's own "always emit both halves" rule
  (`caller-suitability-gate.md:40-50`) and doubles as the run's liveness precondition —
  see the vacuous-pass decision under Proposed Solution.
- The **suppression half** is asserted deterministically: the written fixture contains no
  `Update` bullet for `scripts/little_loops/git_operations.py`.
- The **injection half** is asserted deterministically: the written fixture contains an
  `Inject at` bullet naming `scripts/little_loops/cli/gitignore.py:55`.
- All three gates are evaluated on every run; none short-circuits the others, and the run
  reports which gate(s) failed. When `gate-record` fails the run reports `RUN_INVALID`
  rather than a per-gate tally — see the aggregate-semantics decision below.
- All three gates are shell greps over that written file, not `output_contains` matches over
  LLM-formatted prose. Each gate action exits 0 unconditionally, carrying its verdict in a
  `GATE_PASS`/`GATE_FAIL` sentinel rather than in its exit code.
- The loop YAML itself stays `ll-loop validate`-clean under `python -m pytest scripts/tests/`,
  not merely by convention — see the loop-validation test under Tests.
- The fixture leaves no residue in `.issues/` after the run, including on failure — and any
  residue that a hard kill does leave is cleared idempotently by the next run's staging
  state, and is detected by a pytest residue guard rather than by `git status` (the
  `.gitignore` entry hides it from `git status` by construction — see the residue-detection
  decision under Implementation Steps step 3).

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

Check the fixture body in (as `ENH-288`) under `scripts/tests/fixtures/issues/` (it is not
real work and must not appear in the backlog), and drive it from a **hand-written FSM loop**
in the `loops/prompt-regression-test.yaml` shape: an execute state that runs
`/ll:wire-issue ENH-288 --auto` against the staged copy, followed by three deterministic
gates — record, suppression, injection — each a shell `grep` over the file wire-issue just
wrote, and an aggregate state that names whichever gate(s) failed.

Because wire-issue resolves its argument through `ll-issues path` (see the resolver
constraint below), the loop **stages the fixture into `.issues/enhancements/` for the
duration of the run and removes it on every exit path**, rather than teaching any resolver
to accept a file path.

> **`--dry-run` is dropped; the loop wires the staged copy for real and greps the written
> file (decided 2026-08-20, fifth review round). This resolves a defect that made the
> injection gate unpassable by construction.** Three findings, all verified against the tree:
>
> 1. **`--dry-run` never prints the `Inject at` bullet.** `--dry-run` skips Phase 8
>    (`skills/wire-issue/SKILL.md:338`) and `--auto` skips Phase 7, so the only output an
>    auto+dry-run invocation emits is the Phase 10 report
>    (`skills/wire-issue/output-report.md`). That template prints Integration Map additions
>    as bullets (`### Added to Dependent Files`) but renders Implementation Steps changes as
>    a bare count — `- [N] wiring touchpoints added`. `Inject at` bullets are Wiring Phase
>    entries, i.e. Implementation Steps, so they are **never printed under `--dry-run`**.
>    `gate-injection` — the half this issue calls "the newer and less-exercised of the two"
>    — could therefore never match, permanently. The old step 4 would have discovered this
>    only after the loop was written.
> 2. **Bare `--dry-run` hangs a headless run.** Without `--auto`, Phase 7 reaches
>    `AskUserQuestion` (`SKILL.md:308-330`), which has no answer source under `ll-loop run`.
>    Any dry-run variant would have had to be `--auto --dry-run` — precisely the combination
>    that emits nothing but the summary report.
> 3. **Writing for real is free here.** The staged fixture is ephemeral and deleted on every
>    exit path, so there is nothing to protect from mutation — `--dry-run` was guarding a
>    file that gets `rm`'d seconds later. Letting Phase 8 write gives the gates the *actual
>    emitted markdown* instead of an LLM-formatted summary of it.
>
> **Selected:** run `/ll:wire-issue ENH-288 --auto` (no `--dry-run`) and gate with `grep`
> over the staged file. Consequences, all improvements:
> - All three gates become shell `grep` states over a file on disk — fully deterministic,
>   with no dependence on how the host formats stdout and no `output_contains`
>   regex-vs-substring hazard.
> - The old step 4 ("run it once manually and pin the substrings against observed dry-run
>   output") **collapses**: the assertion targets are the Integration Map and Wiring Phase
>   bullet formats, specified verbatim in `SKILL.md:344-403` and
>   `caller-suitability-gate.md:40-50`, not discovered empirically. Step 4 is retained in
>   reduced form as a single confirming run.
> - The fixture must set `testable: false` in its frontmatter so Phase 9's learning-target
>   extraction is skipped (`SKILL.md:471`) — that skip is conditioned on `testable: false`
>   **or** `--dry-run`, and only the former is still available.
> - Phase 9 runs `ll-issues append-log` and `git add "<staged path>"` **unguarded by
>   `DRY_RUN`** (`SKILL.md:456-470`) — the "skip all file modifications" rule at `:338` is
>   scoped to Phase 8's heading only. `git add` on an explicitly-named gitignored path fails
>   without `-f` and stages nothing, so this is noise rather than a leak; `unstage-fixture`
>   nonetheless runs `git reset -- <path>` before `rm -f` as a defensive measure.

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
>    checks over emitted Markdown, so they gate deterministically. This strengthens the
>    issue's "not pytest-assertable" framing to "not pytest-assertable, but deterministically
>    gated" — only the stimulus is non-deterministic. *(Refined in the fifth review round:
>    the checks are shell `grep`s over the file wire-issue writes, not `output_contains` over
>    its stdout — see the `--dry-run` decision below.)*
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

> **`gate-record` must invalidate the run, not merely count as one failure (decided
> 2026-08-20, fourth review round).** The vacuous-pass decision above adds `gate-record` as
> the run's liveness precondition, but the step-5 aggregate as previously specified only
> "names whichever gate(s) failed" under ENH-3200 no-short-circuit routing. Under that
> spec a wholly dead run — empty capture, errored wire-issue, no Wiring Phase emitted —
> reports **"1 of 3 gates failed" with `gate-suppression` showing PASS**, which is exactly
> the false signal `gate-record` exists to prevent. The mitigation is present but inert
> unless the aggregate distinguishes the two cases.
>
> **Selected:** the aggregate emits `RUN_INVALID` (not a per-gate tally) whenever
> `gate-record` fails, and reports the suppression and injection verdicts as *unevaluated*
> in that case. No-short-circuit routing still holds — all three gates run — but the
> aggregate's *reporting* is precedence-ordered, not flat.
>
> Why `gate-record` remains the only liveness signal, restated for the fifth round's gate
> shape: the gates now `grep` a file rather than negate an `output_contains` match, so the
> fourth round's specific reasoning — that `evaluate_output_contains()` skips
> `error_patterns` routing when negating (`fsm/evaluators.py:481`, `if verdict == "no" and
> not negate and error_patterns`), leaving the negated suppression gate structurally unable
> to reach `on_error` — no longer applies. The conclusion is unchanged and now simpler:
> `grep` finding nothing is indistinguishable from `grep` running against an empty or
> never-written file. `gate-suppression` passing means "the bad bullet is absent", which is
> trivially true of a file wire-issue never wrote. Only `gate-record` asserts that
> wire-issue produced output at all.
>
> The fifth round *strengthens* this: `archive-wiring` `cp`s the written staged file before
> any gate runs, so if wire-issue never wrote — or never ran — the copy is of the unmodified
> fixture body, which contains no `### Dependent Files` entry. `gate-record` fails and the
> aggregate emits `RUN_INVALID`, exactly as intended.

> **Fixture ID is a never-allocated *gap* number, `ENH-288` — not a reserved high number
> (decided 2026-08-20, fifth review round; supersedes both the `ENH-3300` and `ENH-9999`
> selections).** The fourth round correctly identified that staging a high ID perturbs
> global numbering — `get_next_issue_number()` (`issue_parser.py:2461-2510`) returns
> **max + 1** by filename regex across all category dirs, so a staged `ENH-9999` makes the
> next allocation `10000`, permanently if a crash leaves residue — but it accepted that as a
> bounded residual rather than eliminating it.
>
> It is eliminable at zero cost. Because the allocator takes **max + 1**, every number
> *below* the current max is permanently unallocatable: the allocator can never hand one
> out, no matter how many issues are created. That is the same collision-freedom guarantee
> the reserved-high-ID was chosen for, but with **no perturbation at all** — staging a
> below-max ID cannot move the maximum. The tree currently has 96 such gaps (max is 3260);
> `281`–`295` is a contiguous 15-wide block, and `git log --all --diff-filter=D` shows no
> issue file with any of those numbers ever existed, so the block is an allocation skip
> rather than a set of deletions that might be restored.
>
> **Selected: `ENH-288`.** Consequences:
> - The numbering hazard is **gone**, not bounded. The fourth round's residual accepted risk
>   ("a human creating an issue by hand, in the seconds a staged run is live, still gets
>   `10000`") no longer exists.
> - `scope: [".issues/enhancements/"]` on the loop (step 5) is **retained on its own merits**
>   — a correct narrow scope that avoids the repo-root-lock fallback — but it is no longer
>   justified as a numbering mitigation. Note that justification was weak regardless:
>   `LockManager` is taken only by `ll-loop run` (`cli/loop/run.py:372`,
>   `_helpers.py:1545`), and `ll-issues create` takes no lock, so an `ll-auto` session
>   running `/ll:capture-issue` was never blocked by it.
> - The pytest residue guard (step 3) is likewise retained on its own merits, as the only
>   thing that can see residue once the path is gitignored.
> - **New guard required:** the residue guard's file asserts `ENH-288` is still absent from
>   `.issues/` in steady state, which doubles as a reservation check — if a human ever
>   hand-allocates `288`, the suite goes red instead of the fixture silently colliding with
>   live backlog work.
>
> The one property the high ID had that this one lacks is self-evident sentinel-ness. Recover
> it in the slug, not the number: stage as `P3-ENH-288-fixture-caller-suitability-gate.md`.

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
  > **Selected: the fixture carries the never-allocated gap ID `ENH-288`** — see the
  > fixture-ID decision under Proposed Solution for the full rationale. Short form:
  > `get_next_issue_number()` (`issue_parser.py:2461`) takes **max + 1**, so any below-max
  > number is permanently unallocatable and staging it perturbs nothing.
  > `resolve_issue_path()` (`issue_parser.py:92`) keys only on the `TYPE-NNN` shape, so the
  > choice of number is otherwise free. `ENH-3300` remains the correct name for the
  > *historical* one-shot run recorded in ENH-3258's Session Log; it is not the fixture's ID
  > going forward. `ENH-9999` (fourth-round selection) is superseded — it avoided collision
  > but blew the allocator's maximum out to `10000` while staged
- A new hand-written FSM loop YAML (mechanism locked — see Proposed Solution decision):
  stage fixture → `/ll:wire-issue --auto` → three shell `grep` gates (record, suppression,
  injection) → aggregate → unstage
  > **Selected: the loop lives at `scripts/tests/fixtures/loops/`, not in the built-in
  > catalog (decided 2026-08-19, second review round).** `resolve_loop_path()`
  > (`fsm/loop_paths.py:21-23`) returns any path that exists *before* consulting any loops
  > dir, so `ll-loop run scripts/tests/fixtures/loops/<name>.yaml` works directly against a
  > path. Rationale: this is a fixture, not a shipped loop — a fixtures location keeps it
  > out of `test_builtin_loops.py`'s validation sweep over
  > `scripts/little_loops/loops/`, and drops the conditional README row entirely
  > > **Why not the existing `scripts/tests/fixtures/fsm/` (noted 2026-08-20, fifth review
  > > round).** That directory already holds ~20 loop YAMLs, so a reviewer will ask. It is
  > > the *validator*-fixture directory — many of its files (`incomplete-loop.yaml`,
  > > `loop-with-unreachable-state.yaml`, `broken-verify-loop.yaml`) are deliberately
  > > invalid and exist to be rejected. This loop is the opposite: a runnable artifact that
  > > must stay `ll-loop validate`-clean. Keeping them apart prevents a future
  > > "validate everything under `fixtures/fsm/`" sweep from being impossible to write.
  > > Create `scripts/tests/fixtures/loops/` new
> **Descoped 2026-08-19 (third review round):** `skills/wire-issue/caller-suitability-gate.md`
> and its six host mirrors are **no longer modified by this issue** — the worked-example
> correction shipped separately (Implementation Steps step 2). What remains is three sites:
> the fixture body, the loop YAML, and the `.gitignore` entry.

- `.gitignore` — add an ignore entry for the staged fixture path
  (`.issues/enhancements/*ENH-288-*`). Required, not optional: FSM `on_failure`/`on_error`
  routing cannot cover SIGINT, a timeout kill, or `max_steps` exhaustion, so in-loop
  cleanup alone cannot deliver the "no residue" criterion. See Implementation Steps step 3
- `scripts/tests/test_caller_suitability_gate.py` — add the **residue guard** (a ~5-line
  test asserting no `.issues/enhancements/*ENH-288-*` exists). Added 2026-08-20 (fourth
  review round) as the detection mechanism the `.gitignore` entry removes; see the
  residue-detection decision under Implementation Steps step 3. It doubles as the
  **ID-reservation guard** under the fifth round's gap-number decision: the same assertion
  proves nobody has hand-allocated `288`. Added 2026-08-20 (sixth review round): the same
  file also gains the **loop-validation test** (`ll-loop validate` on the fixture loop path,
  exit 0) — see Tests. Change surface is **4 sites**, not 3; the sixth round's addition is a
  second test in an already-counted file, so the count is unchanged

_Superseded by the mechanism decision (2026-08-19) — no longer in scope:_
- ~~`scripts/little_loops/cli/loop/__init__.py` (~972-1019) — `scaffold-verify` argparse
  block; add the file-path bypass flag~~
- ~~`docs/reference/CLI.md` — `ll-loop scaffold-verify` (~1043-1049) flag table; add a row
  for the new flag~~
  > **`behavior_parity_not_applicable: true` (set 2026-08-19, second review round).**
  > `ll-issues format-check` flagged `missing_behavior_parity: docs/reference/CLI.md`,
  > tripped by the Proposed Solution line "its `docs/reference/CLI.md` row are all
  > **dropped** — see the superseded decision". That is a false positive: "dropped" means
  > dropped *from this issue's scope*, not a file or documented behavior being removed.
  > `docs/reference/CLI.md` is untouched by this issue, so there is no old-vs-new behavior
  > to establish parity for. Flag set by human decision per `issue_parser.py:727-730`

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
  > **Corrected 2026-08-19 (third review round) — the parity claim above was false when
  > written, and is now true.** `SKILL_MIRRORS_MUST_MATCH_SOURCE` covered `SKILL.md` pairs
  > only; no companion file appeared in it, so these six mirrors had **no** drift check.
  > `test_enh494_skill_companions.py` covers only the canonical companion's existence,
  > non-emptiness and linkage — not mirror content. The three
  > `caller-suitability-gate.md` pairs were added to the list
  > (`test_wiring_skills_and_commands.py:386-396`) and the mirrors are in sync. These files
  > remain *dependent* on this issue's subject matter but are no longer *modified* by it.
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
  invoke `/ll:wire-issue ... --auto` today; none invoke `--dry-run`.
  > **Re-read 2026-08-20 (fifth review round): this finding now cuts the other way.** It was
  > recorded as a risk ("no prior art for dry-running wire-issue in a loop, so the output
  > format is unobserved"). Under the `--dry-run` decision the fixture joins the existing
  > `--auto` cohort instead of pioneering an unexercised invocation mode, so the five loops
  > above are **precedent**, not a gap. What remains novel is only that this loop *asserts*
  > on wire-issue's written output rather than consuming it

### Tests

> **Corrected 2026-08-19 (third review round) — "not pytest-assertable" was too broad,
> and it was pinning Outcome Confidence Criterion B at 0/25 permanently.** The second
> review round narrowed the threat model to *deletion / gross regression* (see the
> prompt-contamination decision). Deletion of a clause from a markdown file **is**
> pytest-assertable, and this repo does it routinely
> (`test_capture_issue_skill.py:22-39`, `test_enh494_skill_companions.py:44-70`).
> The claim splits in two:
>
> - **Presence is deterministically gated in pytest** — `scripts/tests/test_caller_suitability_gate.py`
>   (landed 2026-08-19) asserts the "Always emit both halves" mandate, the literal
>   `` `Inject at <path>` `` clause, its contrast against `Update <path>`, both skip
>   conditions, § 8b's inline copy in `SKILL.md`, the companion link, and that the worked
>   example cites a real path whose line still calls `suggest_gitignore_patterns()`.
>   Mutation-verified: deleting the clause from either the companion or `SKILL.md`
>   fails 3 tests. This covers the Summary's stated threat in full, with no LLM.
> - **Application is not** — whether an LLM running `/ll:wire-issue` *applies* a rule
>   that is demonstrably present is the residual, and that is what the fixture loop is
>   for. This is the honest scope of the remaining work.

- `scripts/tests/test_caller_suitability_gate.py` — **landed**; the deterministic
  presence half. The presence assertions are not part of this issue's remaining work, but
  the file gains one new test in this issue: the **residue guard** (see below)
- **New (2026-08-20, fourth review round): a residue guard IS in scope.**
  `assert not list((project_root / ".issues").glob("*/*-288-*.md"))`. This is
  not a prose-compliance check — it is a filesystem invariant, and it is the *only*
  mechanism that can see the staged fixture once step 3 gitignores the path. ~5 lines.
  > **Two amendments, fifth review round (2026-08-20).**
  > 1. **It must not race a live run.** The assertion fails spuriously if the suite runs
  >    while a staged loop run is in flight — the fixture is *supposed* to be there for
  >    those seconds. Skip the guard when `LL_AUTOMATION` is set, or when the loop's lock
  >    file is present under the loops dir. Without this it is a flake generator, and a
  >    flaky invariant guard gets deleted rather than fixed.
  > 2. **It also serves as the ID-reservation guard.** Under the gap-number decision the
  >    same glob proves nobody has hand-allocated `288` to real work — the one property a
  >    below-max ID does not get for free from the allocator. Assert the absence for the
  >    whole of `.issues/`, not just `enhancements/`, so a `BUG-288` or `FEAT-288` is caught
  >    too; `get_next_issue_number()` treats the numeric space as global across prefixes
  >    (`issue_parser.py:2488-2496`), and so must this guard.
  > **Amendment, sixth review round (2026-08-20): the glob as written could not do what
  > amendment 2 asks.** The specified pattern was `*ENH-288-*`, which matches no `BUG-288`
  > or `FEAT-288` — the type-widening was stated in prose but absent from the assertion.
  > Corrected above to `.issues/` + `*/*-288-*.md`, which matches the anchored
  > `P?-TYPE-NNN-` filename shape across every category dir. Note the hyphen boundary is
  > load-bearing and sufficient: it does **not** false-positive on the existing
  > `P2-ENH-1288-*` and `P3-ENH-2288-*` files, matching `resolve_issue_path()`'s own
  > anchored `_ANCHORED_FILENAME_RE` semantics (`issue_parser.py:117-125`).
- **New (2026-08-20, sixth review round): a loop-validation test IS in scope.** ~5 lines in
  the same file, shelling out to `ll-loop validate scripts/tests/fixtures/loops/<name>.yaml`
  and asserting exit 0.
  > **Nothing else will ever validate this loop.** The Files-to-Modify decision puts the
  > YAML under `scripts/tests/fixtures/loops/` specifically to escape
  > `test_builtin_loops.py`'s sweep, and the Wiring Phase states "`ll-loop validate` must
  > pass on the new YAML" — but specifies no mechanism. Verified: every test file that
  > validates loops defines `BUILTIN_LOOPS_DIR` as `little_loops/loops/`
  > (`test_builtin_loops.py:28`, `test_bug_2816_cli_invocations.py:14`,
  > `test_auto_refine_closure_accounting.py:26`), so the new path has **zero** schema
  > coverage and a break surfaces only when a human next runs the loop by hand — which,
  > this issue being a lapsed-fixture issue, may be never. This is the same failure mode
  > ENH-3259 exists to fix, reproduced in the fix itself.
  > **Selected:** wrap it as a pytest that shells out and asserts exit 0. That is this
  > repo's documented pattern for enforcing a non-pytest gate inside
  > `python -m pytest scripts/tests/` (`.claude/CLAUDE.md` § Testing & CI Policy; precedent
  > `test_policy_builder_node_gate.py`). It adds no change site — it lands in
  > `test_caller_suitability_gate.py` alongside the residue guard.
- Beyond those two guards, the fixture loop's completion gate remains the loop running and
  reproducing the recorded verdict, not a further addition to `scripts/tests/`

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

> **Steps 2 and 3 landed 2026-08-19 (third review round) and are struck below.** The
> worked-example correction was descoped from this issue and shipped directly — it is a
> live defect in doctrine the model reads on every run, independent of whether this
> fixture is ever built. Removing it drops ~7 of this issue's ~9 change sites (the
> correction plus 6 host mirrors), which is what was holding Criterion A at 14/25 and
> Criterion D at 18/25.
>
> The prior "step order matters" note is now **moot**: the correction no longer sits in
> this issue, so it cannot invalidate the output-pinning step. The underlying hazard
> stands as a standing rule — **if `caller-suitability-gate.md` is touched for any reason
> after pinning, re-pin the gate substrings.**

1. **Author** the fixture body as `ENH-288` under `scripts/tests/fixtures/issues/`,
   faithful to the ground truth recorded in ENH-3258's Session Log (the body itself is not
   recorded there — see the corrected finding above). Ground truth: the fixture asks to
   thread a config-sourced `exclude_patterns` list into `get_untracked_files()`, whose sole
   production caller is `git_operations.py:413`, inside `if untracked_files is None:`
   (`:412`), enclosed by
   `suggest_gitignore_patterns(untracked_files: list[str] | None = None, ...)`. The body
   must say **nothing** about guards, fallbacks or seams — that contamination is exactly
   what invalidated the ENH-3000 run. (Contamination via the *companion doc* is a separate,
   accepted limitation — see the prompt-contamination decision under Proposed Solution.)
   The frontmatter must set **`testable: false`**, which is what suppresses Phase 9's
   learning-target extraction now that `--dry-run` is gone (`skills/wire-issue/SKILL.md:471`
   skips on `testable: false` **or** `--dry-run`); and it must carry a
   `program_design_not_applicable: true` / `behavior_parity_not_applicable: true` pair so
   wire-issue's own gates do not fire on the stimulus. File name when staged:
   `P3-ENH-288-fixture-caller-suitability-gate.md`, placed in the `.issues/enhancements/`
   directory. (That staged path is deliberately transient and gitignored, so it will never
   be git-tracked — `ll-issues format-check` reports it as a `stale_file_ref`, which is a
   false positive by construction here.)
2. ~~Correct `caller-suitability-gate.md`'s worked-example `Inject at` bullet~~ —
   **DONE 2026-08-19, descoped from this issue.** The bullet now reads
   ``Inject at `scripts/little_loops/cli/gitignore.py:55` `` in the canonical file and all
   three host mirrors. Two follow-on findings, both landed with it:
   - `scripts/tests/test_caller_suitability_gate.py` — the deterministic presence gate
     (see the Tests correction above).
   - **The parity claim in this issue was wrong.**
     `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:386-396`)
     listed only `SKILL.md` pairs — **no companion file was covered**, so the six mirror
     copies of the gate had zero drift protection and step 2's propagation would have been
     unverified. The three `caller-suitability-gate.md` pairs are now in that list;
     mutation-verified against an appended-line drift.
3. Add the staged-path ignore entry (`.issues/enhancements/*ENH-288-*`) to `.gitignore`
   **before** the first staged run, so a crashed run cannot dirty the working tree. In the
   same step, add the residue guard to `scripts/tests/test_caller_suitability_gate.py`.
   > **Residue detection: the `.gitignore` entry destroys the obvious check (decided
   > 2026-08-20, fourth review round).** Once the staged path is gitignored, `git status`
   > reports clean **whether or not residue exists** — so the previously-written step 6
   > verification ("confirm `git status` is clean — no staged fixture residue") was vacuous
   > by construction, and Expected Behavior conflated *hiding* residue with *clearing* it.
   > The two goals are in direct tension: ignoring the path is required so a crash cannot
   > dirty the tree, and it is precisely what blinds the check.
   > **Selected:** keep the `.gitignore` entry and add a filesystem-level pytest residue
   > guard alongside it (Tests section). It runs on every `python -m pytest scripts/tests/`,
   > costs ~5 lines, converts invisible residue into a red suite, and gives step 6 a real
   > assertion. Both landing in the same step is deliberate — the ignore entry must never
   > exist without the guard.
4. **Confirm the emitted bullet formats with one manual run** of
   `/ll:wire-issue ENH-288 --auto` against a hand-staged copy, and read the written file.
   This step was formerly "derive the gate substrings from observed dry-run output, since
   they cannot be assumed"; under the `--dry-run` decision it is reduced to a confirmation.
   The formats are **specified**, not discovered: `### Dependent Files` and its bullet shape
   at `skills/wire-issue/SKILL.md:344-352`, the Wiring Phase `Update <path>` bullet shape at
   `:404-417`, and the `Inject at <path>` form mandated by
   `caller-suitability-gate.md:40-50`. Write the gate patterns from those citations; use the
   run to confirm them, and to confirm that Phase 8 wrote into the staged copy at all.
5. Hand-write the FSM loop under `scripts/tests/fixtures/loops/`. Top-level keys follow
   `prompt-regression-test.yaml`: `initial: stage-fixture`, `max_steps: 10`,
   `timeout: 3600`, plus the `scope:` declared below. States:
   - `stage-fixture` (shell) — `rm -f` the staged path first, then copy the fixture from
     `scripts/tests/fixtures/issues/` into the `.issues/enhancements/` directory as
     `P3-ENH-288-fixture-caller-suitability-gate.md`. The pre-clean is what makes staging
     idempotent after a hard kill.
   - `run-wire-issue` (`action_type: slash_command`) — `/ll:wire-issue ENH-288 --auto`. No
     `--dry-run`; Phase 8 writes its findings into the staged copy, which is what the gates
     read. `capture:` is declared for forensics, but **the gates do not read the capture**.
     > **`slash_command`, not `prompt` (decided 2026-08-20, sixth review round).** Both are
     > in `LLM_ACTION_TYPES` (`fsm/executor.py:125`) so either would likely execute, but all
     > five existing `/ll:wire-issue ... --auto` call sites use `action_type: slash_command`
     > (`rn-remediate.yaml:614-616`, and the four others listed under Similar Patterns).
     > Under the fifth round's decision this loop *joins* that cohort, so there is no reason
     > to diverge from it.
   - `archive-wiring` (shell) — `cp` the written staged file to
     `${context.run_dir}/wired-fixture.md` before any gate runs, so a failing run leaves the
     evidence behind after `unstage-fixture` deletes the original.
   - `gate-record`, `gate-suppression`, `gate-injection` — each `action_type: shell`,
     each a `grep` over `${context.run_dir}/wired-fixture.md`, each with `capture:` set and
     `evaluate: {type: output_contains, pattern: "GATE_PASS"}` over its own action output.
     Record: a `### Dependent Files` bullet citing `git_operations.py:413`. Suppression: no
     Wiring Phase `Update` bullet citing `git_operations.py`. Injection: an `Inject at`
     bullet citing `cli/gitignore.py:55`.
   - `aggregate` (shell) — names whichever gate(s) failed, or emits `RUN_INVALID` if
     `gate-record` failed (see the aggregate-semantics decision under Proposed Solution).
   - `unstage-fixture` — `git reset -- <staged path>` (defensive; see the Phase 9 note in
     the `--dry-run` decision), then `rm -f` the staged path.

   All three gates run on every path (ENH-3200 no-short-circuit routing: every gate's
   `on_yes`/`on_no`/`on_error` routes to the *next* gate, not to a shared failure terminal);
   `unstage-fixture` is wired onto success, failure and error exits.
   > **`grep -v` must not be used for the suppression gate (decided 2026-08-20, sixth
   > review round). The previously-offered form was a second permanent vacuous pass.** Step
   > 5 formerly offered "(`grep -v`/`! grep`, echoing `GATE_PASS` on absence)" as an
   > implementer's choice. `grep -v <pattern> <file>` prints the *non-matching lines* and
   > exits 0 whenever **at least one line** fails to match — trivially true of any multi-line
   > issue file, whatever it contains. A `grep -v`-based gate would therefore emit
   > `GATE_PASS` unconditionally, forever, including on a file that *does* carry the
   > forbidden `Update` bullet. That is the same class of defect as the fourth round's
   > vacuous-pass and the fifth round's permanent-FAIL, and `gate-record` does **not** catch
   > it — a live run passes `gate-record` and then lies on suppression.
   > **Selected:** `! grep -qF ...` only. Strike `grep -v` from the spec rather than leaving
   > the choice open.
   > **Scope the suppression grep to the Wiring Phase section (same round).** `gate-record`
   > requires a `### Dependent Files` bullet citing `git_operations.py:413` to be present in
   > the *same file* `gate-suppression` reads, so a whole-file search for an `Update` bullet
   > mentioning `git_operations.py` runs adjacent to a section that legitimately cites that
   > path. Slice first — e.g. `sed -n '/### Wiring Phase/,$p' <file>` — then `! grep -qF`
   > over the slice, so the two gates cannot interfere.
   > **Every gate action must exit 0 unconditionally (same round).** Routing is *not* at
   > risk — verified: a bare `grep` miss (exit 1) classifies as `FailureType.REAL`
   > (`issue_lifecycle.classify_failure`), which falls through to normal verdict routing at
   > `fsm/executor.py:2038-2041`; and the `on_error` early-return at `:1836` sits inside the
   > `if state.next:` branch, which these gates do not use. But a non-zero exit still feeds
   > the stall detector's `(state, exit_code, verdict)` triple (`:1935`) and lands in
   > `${captured.<gate>.exit_code}`, so a legitimately-failing gate reads as an infra fault
   > in forensics. Write each gate as
   > `if grep -qF ...; then echo GATE_PASS; else echo GATE_FAIL; fi` — verdict carried by
   > the sentinel, exit code always 0.
   > **Escape bash braces in the gate actions (same round).** These are this loop's first
   > shell states and they interpolate `${context.run_dir}`. FSM interpolates the whole
   > action string before bash sees it, so any *bash* variable in the same action must be
   > written `$${...}` or interpolation raises "expected namespace.path". Prefer literal
   > paths over bash variables in these actions and the hazard does not arise.
   > **Each gate must be an *action* state, not an evaluate-only state (decided 2026-08-20,
   > fifth review round). The previously-specified shape produced a permanent, silent
   > FAIL.** The fourth round specified the gates as evaluate-only states with an
   > `evaluate.source` override, and step 5 borrows `scaffold_verify.py`'s aggregate, which
   > reads each gate's verdict as `${captured.<key>.verdict:default=unknown}`
   > (`scaffold_verify.py:88-90`). Those two do not compose. The verdict write-back is
   > guarded by `if state.capture and state.capture in self.captured`
   > (`fsm/executor.py:1922`), and the capture dict is only *created* by the action-result
   > block (`:2370`), which lives inside the action-execution path — an evaluate-only state
   > never populates it. So the write-back is a no-op, all three gates read back `unknown`,
   > and the aggregate reports `NOT_PASSED` on **every** run, forever.
   >
   > `ll-loop validate` cannot catch this: `_validate_capture_reachability()`
   > (`fsm/validation/reachability.py:376-378`) builds its capture map from *declared*
   > `capture:` keys, so a declared-but-never-written capture lints clean. And the
   > aggregate's `:default=unknown` guard converts the missing value into a wrong answer
   > rather than a crash. This is the exact mirror of the vacuous-pass hazard the fourth
   > round fixed — a silent permanent-fail instead of a silent permanent-pass, and equally
   > invisible.
   >
   > **Selected:** every gate is `action_type: shell` with a real `grep` action and a
   > `capture:` key, evaluated by `output_contains` over its **own** action output. The
   > capture dict is then populated by the action, the ENH-3200 write-back lands, and the
   > aggregate reads real verdicts. This also removes the need for any `evaluate.source`
   > override at all.
   > **Consequently the fourth round's `source:` pinning note is moot**, and its underlying
   > hazard is retired rather than mitigated: `evaluate.source` (`fsm/schema.py:114`) is an
   > interpolated string, not a file reader, so `source: "${context.run_dir}/wiring.txt"`
   > would have gated on the literal *path text* and passed vacuously forever. No gate now
   > declares `source:`, so the trap is unreachable. `${context.run_dir}/wired-fixture.md`
   > is read by `grep` inside the action — where a path *is* a path.
   > **Regex-vs-substring escaping is likewise retired for the gates** — they are `grep`
   > invocations now, so use `grep -F` for literal patterns and the hazard is gone. The
   > underlying evaluator behavior still stands and still applies to the `GATE_PASS` /
   > `ALL_PASSED` sentinels: `evaluate_output_contains()` (`fsm/evaluators.py:470-473`)
   > tries `re.search` **first** and falls back to substring matching only when the pattern
   > fails to *compile* — never on a no-match. Keep bare `.` and `()` out of every sentinel.
   > **Declare `scope: [".issues/enhancements/"]` (added 2026-08-20, fourth review round;
   > rationale narrowed in the fifth).** `_validate_missing_scope()`
   > (`fsm/validation/structural_rules.py:1226-1245`) warns on any loop with no `scope:`,
   > and an empty scope falls back to a repo-root lock (`resolve_scope(fsm.scope or ["."],
   > ...)` in `cli/loop/run.py`) that false-conflicts with every concurrently running loop.
   > Declaring the staged directory is the correct narrow scope, and that alone is the
   > justification — the fourth round's secondary claim that the lock closes a
   > numbering-allocation hazard no longer applies (the hazard is gone under the gap-number
   > decision, and the lock never covered `ll-issues create` anyway). `${context.run_dir}/`
   > needs no scope entry — it is runner-managed.
6. Run the loop once against the current tree and confirm it reports `ALL_PASSED`, then
   confirm no staged fixture residue remains — by globbing `.issues/enhancements/*ENH-288-*`
   directly, **not** by `git status`, which is clean by construction once step 3's ignore
   entry exists (see the residue-detection decision under step 3). Running
   `python -m pytest scripts/tests/test_caller_suitability_gate.py` is the equivalent check
   and is what the suite enforces thereafter.

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
  rather than inventing a new aggregation shape or generating the YAML from a scaffold.
  **Borrow its state shape too, not just its routing:** every criterion state there is an
  *action* state with `capture:` declared, and that is load-bearing, not incidental — see
  the action-state decision under step 5
- ~~Since no existing loop invokes `/ll:wire-issue --dry-run`, verify the dry-run output
  format directly against a manual run before wiring the gates against it (step 4)~~ —
  **superseded 2026-08-20 (fifth review round).** `--dry-run` is dropped; the gates read the
  file wire-issue writes, whose bullet formats are specified at `SKILL.md:344-403` and
  `caller-suitability-gate.md:40-50`. Step 4 is now a confirmation, not a discovery
- `ll-loop validate` must pass on the new YAML — and, per the sixth review round, that
  requirement now has a **mechanism**: a subprocess-wrapping pytest in
  `test_caller_suitability_gate.py` (see Tests). Stating it here without one left the loop
  with no schema coverage at all, since every `BUILTIN_LOOPS_DIR` sweep points at
  `little_loops/loops/`.
  > **Corrected 2026-08-19 (second review round).** The prior claim — "this loop targets a
  > *skill* (wire-issue), so per-run artifact isolation is mandatory and the
  > `output_contains` gates satisfy the non-LLM-evaluator rule" — is **false on the
  > mechanism**. `_is_meta_loop()` (`fsm/validation/meta_rules.py:48-70`) classifies by
  > **action-string** regex (`skills/[\w-]+/SKILL\.md`, `loops/[\w-]+\.yaml`,
  > `agents/[\w-]+\.md`, `commands/[\w-]+\.md`, `\.claude/(CLAUDE\.md|settings)`) plus the
  > tokens `yaml_state_editor` / `replace_action`. This loop's actions — a `cp` of a fixture
  > and `/ll:wire-issue ENH-288 --auto` — match none of them, so the loop is **not**
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
  unconditional cleanup routing **plus** the `.gitignore` entry, the `rm -f` pre-clean in
  `stage-fixture`, and the pytest residue guard, since FSM error routing cannot cover SIGINT
  or a timeout kill and the ignore entry blinds `git status`; (2) a
  silently vacuous suppression gate — mitigated by the added positive `gate-record`, whose
  precedence in the aggregate is now specified (`RUN_INVALID`) rather than left as a flat
  tally; (3) ~~staged-fixture perturbation of `get_next_issue_number()`~~ — **eliminated**
  in the fifth review round by moving the fixture to a below-max gap ID, which the allocator
  can never hand out and which cannot move the maximum; (4) a silently permanent-failing
  aggregate, from gates that declare `capture:` but never populate it — **eliminated** in
  the fifth review round by making every gate an action state; (5) ~~a `grep -v`-based
  suppression gate emitting `GATE_PASS` unconditionally~~ — **eliminated** in the sixth
  review round by striking `grep -v` in favour of `! grep -qF` over a Wiring-Phase slice;
  (6) ~~the loop YAML carrying no schema coverage at all, since
  `scripts/tests/fixtures/loops/` sits outside every `BUILTIN_LOOPS_DIR` sweep~~ —
  **eliminated** in the sixth review round by the subprocess-wrapping `ll-loop validate`
  test. The
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

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 50/100 → LOW

### Outcome Risk Factors (current run)
- Change surface is mixed rather than a clean isolated change or a pure mechanical
  sweep: ~9 distinct sites (fixture file, hand-written loop YAML, `.gitignore` entry,
  `caller-suitability-gate.md` correction, 6 host-mirror files) span new-artifact
  authoring plus a small enumerated fanout — Criterion D scored 18/25, not the 25/25 an
  isolated or fully-verified sweep would earn.
- No `scripts/tests/` coverage exists or is planned for this deliverable by design (the
  gate is prose-driven, not pytest-assertable) — Criterion B is 0/25. The loop's
  `output_contains` gates are deterministic but live outside the pytest suite.
- ~~The dry-run output format of `/ll:wire-issue --dry-run` is unobserved by any existing
  loop; step 4 requires pinning the gate substrings against a real run before the loop
  can be trusted~~ — **materially reduced 2026-08-20 (fifth review round).** `--dry-run` is
  dropped, so the gates read the file wire-issue writes, whose bullet formats are specified
  verbatim in `SKILL.md:344-403` and `caller-suitability-gate.md:40-50`. Step 4 is a
  confirming run, not a discovery run. Some execution-verification residual remains (the
  loop has still never been run), but it is no longer a format unknown.

_Reassessment note (2026-08-19, this run): all findings above are unchanged from the
prior run — re-verified independently against the current tree (format-check clean,
Program Design gate clean, no unresolved `blocked_by`, git_operations.py:412-413 and
cli/gitignore.py:55 citations both confirmed by direct read). Readiness raised 90→96:
on independent scoring the only deduction found was Criterion 4 (2 points) for step 4's
observed-not-assumed gate substrings, which is an execution-order safeguard already
built into Implementation Steps rather than an open spec gap. Outcome Confidence
unchanged at 50 — the three risk factors above are structural to the chosen mechanism,
not resolvable by further issue refinement._

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
- ~~**New:** the dry-run output format is unobserved by any existing loop, so the gate
  substrings are guesswork until step 4 pins them against a real run.~~ → **Largely
  resolved** in the fifth review round by dropping `--dry-run`; the gate patterns now derive
  from specified bullet formats rather than observed stdout.
- **New (second review round):** the fixture reuses the gate companion's own worked-example
  scenario, so a PASS proves presence-and-application, not generalization. Accepted and
  scoped in Scope Boundaries; option (a) under Proposed Solution is the upgrade path.

## Session Log
- `/ll:confidence-check` - 2026-08-20T15:42:02 - `3a0f8a60-e129-4a2b-aaef-742b585ee623.jsonl`
- review round (sixth) - 2026-08-20 - **six findings, two of them defects that would have
  made a gate lie; all verified against the tree before writing.** First re-verified the
  fifth round's load-bearing claims and they hold: the ENH-3200 write-back does require
  `state.capture in self.captured` (`executor.py:1922`) against a dict only the action-result
  block creates (`:2370`); `resolve_issue_path()`'s anchored `P?-TYPE-NNN-` match means
  `ENH-288` cannot collide with the existing `P2-ENH-1288-*`/`P3-ENH-2288-*` files; and `288`
  is genuinely unallocated, with no file of that number in
  `git log --all --diff-filter=D`. Findings:
  (1) *`grep -v` was a second permanent vacuous pass.* Step 5 offered `grep -v` as an
  alternative to `! grep` for the suppression gate. `grep -v <pat> <file>` prints the
  non-matching lines and exits 0 whenever any line fails to match — always true of a
  multi-line issue file — so it would emit `GATE_PASS` even when the forbidden `Update`
  bullet was present, and `gate-record` does not catch this (a live run passes record, then
  lies on suppression). `grep -v` struck.
  (2) *Nothing would ever validate the loop.* The Wiring Phase requires "`ll-loop validate`
  must pass on the new YAML" but specifies no mechanism, and the fixtures location that
  escapes `test_builtin_loops.py` escapes every other sweep too — all of them define
  `BUILTIN_LOOPS_DIR` as `little_loops/loops/` (`test_builtin_loops.py:28`,
  `test_bug_2816_cli_invocations.py:14`, `test_auto_refine_closure_accounting.py:26`). A
  schema break would surface only on the next manual run, which for a lapsed-fixture issue
  may be never — this issue's own failure mode, reproduced in its fix. Added a
  subprocess-wrapping pytest per the repo's Testing & CI Policy (precedent
  `test_policy_builder_node_gate.py`); no new change site.
  (3) *The residue guard's glob contradicted its own amendment.* Specified as
  `*ENH-288-*` while the fifth round's amendment 2 asks it to catch `BUG-288`/`FEAT-288`,
  which that pattern cannot. Widened to `.issues/` + `*/*-288-*.md`.
  (4) *Suppression grep needed section scoping.* `gate-record` requires a `### Dependent
  Files` bullet citing `git_operations.py:413` in the same file `gate-suppression` reads, so
  a whole-file search runs adjacent to a section that legitimately cites that path. Slice to
  the Wiring Phase first.
  (5) *Gates should exit 0.* Routing is **not** at risk — verified that a `grep` miss
  classifies as `FailureType.REAL` (`issue_lifecycle.classify_failure`) and falls through to
  normal verdict routing (`executor.py:2038-2041`), and that the `on_error` early-return at
  `:1836` is inside the `if state.next:` branch these gates do not use. But exit 1 feeds the
  stall detector's triple and pollutes `${captured.<gate>.exit_code}`, so a failing gate
  reads as an infra fault. Gates now carry their verdict in the sentinel only.
  (6) *`action_type: prompt` → `slash_command`*, matching all five existing
  `/ll:wire-issue ... --auto` call sites; plus `initial`/`max_steps`/`timeout` specified
  from `prompt-regression-test.yaml`, and a note that bash braces in the new shell states
  need `$${...}`. Change surface unchanged at 4 sites.
  Also confirmed the current implementation state: steps 2 and the presence-test half landed
  in `15786dc4`; the fixture body, loop YAML, `.gitignore` entry and residue guard do not
  exist yet.
- `/ll:confidence-check` - 2026-08-20T15:11:30 - `d1a0a529-4a4a-4956-8bd6-268fc1152f27.jsonl`
- review round (fifth) - 2026-08-20 - **four findings, two of them defects that would have
  made the loop fail or lie on its first run; all verified against the tree before writing.**
  (1) *`gate-injection` was unpassable by construction*: `--dry-run` skips Phase 8
  (`SKILL.md:338`) and `--auto` skips Phase 7, so the only auto+dry-run output is the Phase
  10 report (`output-report.md`), which prints Integration Map additions as bullets but
  Implementation Steps changes as a bare count (`- [N] wiring touchpoints added`). `Inject
  at` bullets are Wiring Phase entries, so they are never printed under `--dry-run`.
  Separately, bare `--dry-run` reaches `AskUserQuestion` and hangs a headless run. Resolved
  by dropping `--dry-run` entirely: the staged copy is ephemeral, so wire-issue writes for
  real and the gates `grep` the written file. This also collapses the old step 4 from
  discovery to confirmation and retires the `evaluate.source` and regex-escaping hazards.
  (2) *The aggregate would have read `unknown` for all three gates, forever*: the gates were
  specified as evaluate-only states, but the ENH-3200 verdict write-back requires
  `state.capture in self.captured` (`executor.py:1922`) and that dict is only created by the
  action-result block (`:2370`) inside the action path. `_validate_capture_reachability()`
  (`reachability.py:376-378`) lints on *declared* captures, so `ll-loop validate` cannot
  catch it, and the aggregate's `:default=unknown` turns the miss into a wrong answer rather
  than a crash — a silent permanent-FAIL, the mirror of the fourth round's vacuous-pass.
  Resolved by making every gate an `action_type: shell` state with a real action and
  `capture:`. (3) *The numbering perturbation was eliminable, not merely boundable*: because
  `get_next_issue_number()` takes **max + 1**, every below-max number is permanently
  unallocatable, so a never-allocated gap ID has the high ID's collision-freedom with none
  of its blowout. Moved `ENH-9999` → `ENH-288` (in the never-used 281–295 block; no such
  file exists anywhere in `git log --all --diff-filter=D`). Also corrected the fourth
  round's claim that the `scope:` lock closed the concurrent-allocation half — `LockManager`
  is taken only by `ll-loop run` (`cli/loop/run.py:372`, `_helpers.py:1545`) and
  `ll-issues create` takes no lock, so an `ll-auto` session running `/ll:capture-issue` was
  never blocked by it. `scope:` is retained on its own merits. (4) *The residue guard would
  flake*: it fails spuriously while a staged run is live; now skipped under `LL_AUTOMATION`
  or a present lock file, and widened to all of `.issues/` so it doubles as the ID
  reservation guard. Also noted why the new loop goes in `scripts/tests/fixtures/loops/`
  rather than the existing `scripts/tests/fixtures/fsm/` (the latter is the validator-fixture
  dir, deliberately full of invalid YAML). Change surface unchanged at 4 sites.
  **`/ll:confidence-check` should be re-run** — two live correctness defects were removed
  from the spec and step 4's outstanding execution risk is materially reduced.
- `/ll:confidence-check` - 2026-08-20T14:36:58 - `b65e97ff-c048-4f0b-8912-71924070aaa4.jsonl`
- review round (fourth) - 2026-08-20 - **five findings, all verified against the tree
  before writing.** (1) *Numbering perturbation*: `get_next_issue_number()`
  (`issue_parser.py:2461-2510`) returns **max + 1** by filename regex, not a count — so a
  staged `ENH-288` makes the next allocation `10000`, permanently if a crash leaves
  residue. The reserved-high-ID decision avoided a collision but introduced this, unstated.
  Mitigated by the loop `scope:` lock plus the residue guard; residual accepted.
  (2) *Step 3 defeats step 6*: once the staged path is gitignored, `git status` is clean
  regardless of residue, so step 6's verification was vacuous by construction and Expected
  Behavior conflated hiding with clearing. Replaced with a direct glob plus a ~5-line pytest
  residue guard in `test_caller_suitability_gate.py`. (3) *`gate-record` was inert*: under
  flat no-short-circuit aggregation a wholly dead run reports "1 of 3 failed" with
  suppression PASSing — the exact false signal `gate-record` was added to prevent. Aggregate
  now emits `RUN_INVALID` on a `gate-record` failure. Reinforced by
  `evaluate_output_contains()` skipping `error_patterns` when negating
  (`fsm/evaluators.py:481`), which means the suppression gate structurally cannot route an
  errored run to `on_error` — `gate-record` is the only liveness path there is.
  (4) *Gate `source` was underspecified*: `evaluate.source` (`fsm/schema.py:114`) is an
  interpolated string, not a file reader, so gating on `${context.run_dir}/wiring.txt` would
  match the literal path text and pass vacuously forever. Gates now pinned to
  `${captured.<state>.output}`; `wiring.txt` is archival only. (5) *No `scope:`*:
  `_validate_missing_scope()` (`structural_rules.py:1226-1245`) warns, and the empty-scope
  fallback is a repo-root lock. Declared `scope: [".issues/enhancements/"]`.
  Re-verified and unchanged: `_is_meta_loop()` (`meta_rules.py:48-70`) will not classify
  this loop; `BUILTIN_LOOPS_DIR` sweeps only `scripts/little_loops/loops/`, so
  `scripts/tests/fixtures/loops/` stays out of `test_builtin_loops.py`; the regex-first
  evaluator and `negate` semantics are as previously recorded. Change surface 3 → 4 sites.
  **`/ll:confidence-check` should be re-run** — Criterion B moves again with the residue
  guard, and three of these five were live correctness defects in the spec.
- `/ll:confidence-check` - 2026-08-20T04:59:12 - `8a861a8f-cdf6-4be8-84e8-9d4a036b13d9.jsonl`
- review round (third) - 2026-08-19 - **root-cause pass on persistent LOW outcome
  confidence (50/100 across four runs while readiness climbed 85→96).** Diagnosis: every
  remaining deduction was an *action*, not a specification gap, so further refinement could
  not move any of them. Three causes, two now resolved:
  (1) *Criterion B pinned at 0/25 by a false axiom.* "Not pytest-assertable by design" was
  asserted as given and re-affirmed every run. But the second round had already narrowed the
  threat to deletion/gross-regression, which is exactly what a content-assertion test covers.
  Landed `scripts/tests/test_caller_suitability_gate.py` (11 tests, mutation-verified: 3 fail
  when the `Inject at <path>` clause is deleted from either the companion or `SKILL.md`).
  (2) *Criteria A/D depressed by scope bundling.* The worked-example correction plus its six
  mirror propagations were ~7 of ~9 change sites. Descoped and shipped separately — it is a
  live doctrine defect regardless of this fixture. Residual surface is 3 sites. This also
  dissolved the step-order hazard.
  (3) *Criterion C's residual is an unperformed observation* — step 4's dry-run output
  pinning. Not resolvable by refinement (correctly noted in the prior run), but resolvable by
  one execution. Still outstanding; it is now the only thing standing between this issue and
  a HIGH score.
  Also found and fixed a **live gap this issue had mis-stated**: the mirror parity test
  covered `SKILL.md` only, so the six host-mirror copies of the gate had no drift protection
  at all. Three companion pairs added to `SKILL_MIRRORS_MUST_MATCH_SOURCE`. Full suite green
  (19273 passed). **`/ll:confidence-check` should be re-run** — scores in frontmatter are
  stale and understate the issue.
- `/ll:confidence-check` - 2026-08-20T04:29:30 - `d25c66c3-4afe-428a-ae85-77939fc798a9.jsonl`
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
  invalidated. (6) *Fixture ID*: `ENH-3300` → reserved `ENH-288`, since
  `get_next_issue_number()` (`issue_parser.py:2461`) will allocate 3300 to real work.
  Also decided: loop location `scripts/tests/fixtures/loops/` (per `resolve_loop_path()`
  `fsm/loop_paths.py:21-23`), dropping the conditional README row; and `.gitignore` added to
  Files to Modify as a required mitigation, not an optional one. Separately,
  `behavior_parity_not_applicable: true` was set (human decision) to clear a
  `missing_behavior_parity: docs/reference/CLI.md` false positive — rationale recorded
  inline under Files to Modify — and a pre-existing `stale_file_ref` was fixed by spelling
  out the elided ENH-3258 filename. `ll-issues format-check` is now clean.
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
