---
id: ENH-3288
type: ENH
title: Convert dead-code-cleanup and test-coverage-improvement to ll-config get, and
  empty the _PENDING_CONVERSION gate
priority: P2
status: open
discovered_by: split-from-ENH-3277
discovered_date: '2026-08-21'
captured_at: '2026-08-21T18:40:00Z'
labels:
- loops
- config
- test-cmd
- refactor
- follow-up
- fsm-control-flow
blocked_by:
- ENH-3277
relates_to:
- BUG-3269
- BUG-3276
- ENH-3277
- ENH-3281
decision_needed: false
confidence_score: 70
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3288: Convert `dead-code-cleanup` and `test-coverage-improvement` to `ll-config get`, and empty the `_PENDING_CONVERSION` gate

_Split out of **ENH-3277** on 2026-08-21 at the risk boundary. ENH-3277 keeps the six mechanical
conversions (`fix-quality-and-tests`, the three `harness-*`, and `evaluation-quality`'s two
branches) and shrinks `_PENDING_CONVERSION` from nine entries to four. **This issue owns
everything that changes FSM control flow, plus the final teardown.**_

## Summary

Two of ENH-3277's target loops cannot be converted mechanically. Both gate an **irreversible or
lossy** `on_yes` edge on a test suite, and under `fragment: shell_exit` a converted empty `CMD`
makes `eval ""` exit 0 — silently **passing** the gate against a suite that never ran:

- **`dead-code-cleanup.verify_tests`** → `on_yes: commit`. A naive conversion **commits dead-code
  deletions with zero verification**. This is the sharpest change in the whole ENH-3277 family.
- **`test-coverage-improvement.verify_tests`** → `on_yes: commit`, and its `measure` state holds a
  **dead** inline read whose deletion forces a decision about the loop's documented-but-inert
  `context.test_cmd` knob.

Handling them correctly is not a shell substitution. It requires a `fragment: shell_exit` →
`fragment: harness_exit` switch at both states, an exit-code normalization, four new states, and
two one-line scalar edits on `dead-code-cleanup`. That is why they were split out.

This issue also carries the **teardown**: moving `rn-refine.yaml` and
`auto-refine-and-implement.yaml` into `_PERMANENT_EXEMPTIONS` (ENH-3277's Option A decision),
emptying and deleting `_PENDING_CONVERSION`, widening `_INLINE_ACCESS_RE`, and the doc edits that
describe the exemption list.

## Current Behavior

Both loops resolve `project.test_cmd` with a hand-rolled inline `.ll/ll-config.json` parse that
guesses `pytest` via `raw if raw else 'pytest'` — overriding an explicit `test_cmd: null` and
bypassing `.ll/ll.local.md` entirely. Both `verify_tests` states are `fragment: shell_exit`, so a
resolution failure lands on the same edge as a real test failure.

`test-coverage-improvement.measure` additionally resolves a `CMD` at `:37-48` that it never uses
(only `$COV_CMD` is ever `eval`'d, at `:62`), leaving the loop's declared and documented
`context.test_cmd` parameter wired to nothing.

`_PENDING_CONVERSION` red-lists both files, plus `rn-refine.yaml` and
`auto-refine-and-implement.yaml`, so they are blocked from growing but not yet fixed.

## Expected Behavior

Both loops resolve through `ll-config get project.<key>`, honoring the three-way contract
(absent → `ProjectConfig` field default; present-and-null → opt out; value → value) and
`.ll/ll.local.md`. Neither can reach `commit` **via `verify_tests`** without a real test signal.
A no-signal skip is routed and reported distinctly from a test failure. `_PENDING_CONVERSION` is
empty and the constant is deleted, leaving exactly three permanent exemptions.

**Scope caveat on that guarantee (added by the seventh review, 2026-08-22).** The qualifier "via
`verify_tests`" is load-bearing and the unqualified claim would be false:
`test-coverage-improvement.extract_percentage` routes `target: commit` (`:85-86`), so a repo
already at `context.coverage_target` goes `measure → extract_percentage → commit` on its first lap
and never enters `verify_tests` at all. That bypass is **pre-existing and out of scope** — it is a
convergence-routing question, not a command-resolution one — but it is recorded here so a reviewer
does not read this issue as having closed a hole it never touched.

## Motivation

**This is where the ENH-3277 family's risk actually lives.** The other six conversions are
find-and-replace; these two redesign control flow on an edge that commits code deletions. Carried
inside a seven-file diff, that redesign gets reviewed as part of a refactor. On its own it gets
reviewed as what it is.

**Every one of these loops is live in every `local-editable` consuming project on this machine
with no reinstall step** — a defect here shows up as another project's tooling breaking silently.

**The teardown is the payoff for the whole family.** `_PENDING_CONVERSION` is technical debt with
a name; ENH-3277 shrinks it, this issue deletes it.

## Proposed Solution

All design work from BUG-3269 applies and is not repeated here — read it there: its §1
(`ll-config get`'s verified three-way contract), §1b (the `ll.local.md` bypass), §1d
(`oracles/code-run-gate.yaml`'s permanent exemption), §1f (why a non-zero exit is unroutable at
`evaluate: exit_code` states), §2 (per-site precedence), and §2b (the per-site empty-`CMD` table).

**Precedence: config-first bare at `dead-code-cleanup`, context-first at
`test-coverage-improvement`.** Only `test-coverage-improvement` declares a `context.test_cmd` key
(`:23`), so it is the one site in the family that may legitimately use the context-first shape —
and only at `verify_tests`, per the pinned *Dead site* decision (a) below. `dead-code-cleanup`'s
`context:` block (`:13-14`) declares only `commit_message`, so an undeclared
`${context.test_cmd}` there raises `InterpolationError: Path 'test_cmd' not found in context` at
interpolation time and fails BUG-3269's gate assertion (ii),
`test_context_references_are_declared`. Use:

```bash
CMD=$(ll-config get project.test_cmd)
```

**Do NOT add a `|| { ...; exit N; }` guard** — BUG-3269 §1f: at `evaluate: exit_code` states a
non-zero exit routes to `on_no`, which is `revert_and_scan` for `dead-code-cleanup`.

### The §2b rows for these two sites

| Site | `on_yes` | Decision |
|---|---|---|
| `test-coverage-improvement.yaml:45` (`measure`) | **none — `next: extract_percentage`** | **DEAD — delete, do not convert.** `measure` resolves `CMD` at `:37-48` and never uses it; the state's only `eval` is `eval "$COV_CMD"` (`:62`). See *Dead site* below — deleting it forces a decision about `context.test_cmd` |
| `test-coverage-improvement.yaml:143-159` (`verify_tests`, inline read at `:152`) | `commit` | **explicit skip required** — target pinned under *Pinning the two explicit-skip gate edges* below; its `on_no`/`on_error: fix_tests` is reachable but wrong |
| `dead-code-cleanup.yaml:71-81` | `commit` / `on_no: revert_and_scan` | **explicit skip required.** `[ -z "$CMD" ]` must route to a non-committing edge. Today `pytest` fails in exactly the project shape BUG-3269 was found in → `revert_and_scan`; after a naive conversion → **commits dead-code deletions with zero verification.** Sharpest change in the whole family. Target pinned under *Pinning the two explicit-skip gate edges* below; `revert_and_scan` is available but wrong |

**Rule (BUG-3269 §2b):** a site whose `on_yes` edge performs an irreversible action (`commit`) or
feeds a score must handle `[ -z "$CMD" ]` explicitly. A site whose `on_yes` leads to another gate
may pass on empty. Both sites here are the former.

### Permanently exempt — `rn-refine` and `auto-refine-and-implement`

**Decided in ENH-3277 (Option A, 2026-08-21, via `/ll:decide-issue`); the full scoring and
rationale live there and are not duplicated.** Both files use a falsy-*skip* shape rather than
`raw if raw else 'pytest'`, so for them conversion would **introduce** a guess rather than remove
one: an absent key today means *skip*, but `ll-config get` collapses absent and defaulted into one
output and would start running `pytest` / `ruff check .` in unconfigured projects. Same rationale
as `oracles/code-run-gate.yaml` (BUG-3269 §1d): *absent ≡ null ≡ skip, never guess.*

**This issue executes that decision** (step 5 below): both YAMLs stay byte-for-byte unchanged and
both filenames move from `_PENDING_CONVERSION` into `_PERMANENT_EXEMPTIONS`. Do **not** build
`ll-config get --raw` — that was Option C, rejected.

### Dead site — `test-coverage-improvement.yaml:45` is deleted, not converted

Verified 2026-08-21. The `measure` state (`:31-66`) resolves `CMD` context-first at `:37-48`
— `if [ -n "${context.test_cmd}" ]; then CMD="${context.test_cmd}"; else CMD=$(python3 -c ...)`
— and then **never references `$CMD` again**. The state's only `eval` is `eval "$COV_CMD"`
(`:62`), whose resolution is a wholly separate block at `:50-59`. The inline read is dead code.

Three consequences, each contradicting text that appeared elsewhere in this issue before this
correction:

1. **The conversion instruction for `:45` was wrong.** It is not a context-first conversion; the
   whole `CMD` block at `:37-48` is deleted. Converting it would preserve dead code in a new shape.
2. **The wiring pass's "fourth case" test at `:45` would pin dead code.** The
   `TestIncrementalRefactorLoop.test_verify_tests_resolves_context_first_then_ll_config`-style
   "context wins over `ll-config get`" assertion has no live behavior to assert at `measure`.
   Move it to `verify_tests` (`:143-159`), per decision (a) below, now pinned.
3. **`test-coverage-improvement`'s `context.test_cmd` parameter is currently inert** — a latent
   bug this issue surfaces. It is declared at `:23` with the comment *"override test command;
   empty = read from ll-config.json"* and documented as a supported knob in
   `docs/guides/LOOPS_REFERENCE.md:1347` (*"Test command to run (e.g. `python -m pytest --cov`)"*),
   but its **only consumer is the dead block**. `verify_tests:143-159` — the state that actually
   runs the test suite and gates `commit` — ignores it entirely and reads config inline.

**DECIDED — (a), make the documented override real.** Pinned 2026-08-21. Delete `:37-48`, and give
`verify_tests` the context-first shape (`general-task.yaml:54-63` /
`incremental-refactor.yaml:78-86`). This is the only target site that may legitimately use
context-first — it is the one loop in this issue that declares the key (`:23`), so BUG-3269's gate
assertion (ii) passes. Honors the doc as written, costs one already-precedented shape, and the
`test_cmd` row at `LOOPS_REFERENCE.md:1347` stays and becomes true.

*Rejected: (b) drop the knob* — delete `:37-48` *and* the `:23` declaration, config-first bare at
`verify_tests`, delete the `LOOPS_REFERENCE.md:1347` row. Fewer moving parts, but it removes
user-facing surface inside a refactor issue, which is the wrong place to shrink a documented API.

Note that **deleting `:37-48` without choosing** would have left a documented-but-inert parameter —
the current state of the world, silently preserved. That is the outcome (a) exists to prevent.

**Knowingly left behind (2026-08-21).** Deleting `:37-48` leaves `measure`'s only executed
command as the hardcoded `COV_CMD="python -m pytest --cov --cov-report=term-missing"` fallback
at `:50-59` — so after this issue, `measure` runs a pytest-shaped command in a project that may
have opted out of pytest entirely. That is the *hardcode* defect class, not the *inline-read*
class: it belongs to **ENH-3281** and is deliberately out of scope here. Flagged explicitly so a
reviewer does not read the surviving hardcode as an oversight of this conversion pass. The
`context.coverage_cmd` knob (`:24`) already overrides it and, unlike `context.test_cmd`, is live.

### Pinning the two explicit-skip gate edges

§2b says the empty-`CMD` branch "must route to a non-committing edge" without naming one, for both
`dead-code-cleanup.verify_tests` and `test-coverage-improvement.verify_tests`. Both are pinned
here. They share one shape and one hazard: the existing failure edge is reachable but frames a
*no-signal skip* as a *test failure*, handing a prompt state an empty log to explain.

#### MECHANISM CORRECTION (2026-08-21) — `on_cannot_judge` requires `fragment: harness_exit`

**Verified against the tree; this correction is load-bearing and supersedes the two "add
`on_cannot_judge:`" instructions below wherever they conflict.**

Both `verify_tests` states are `fragment: shell_exit` today
(`dead-code-cleanup.yaml:68-83`, `test-coverage-improvement.yaml:143-159`). Under
`shell_exit`, `exit 3` does **not** produce a `cannot_judge` verdict: `evaluate_exit_code`
maps `3 → cannot_judge` **only when `abstain_on_exit_3=True`**
(`scripts/little_loops/fsm/evaluators.py:243-263`), which defaults to `False` and is opt-in
per state (ENH-3224, `fsm/schema.py:65-71`). `shell_exit` (`lib/common.yaml:15-22`) sets only
`evaluate: {type: exit_code}` and never sets it.

So *adding an `on_cannot_judge:` edge to a `shell_exit` state accomplishes nothing*: `exit 3`
falls to `else → verdict "error"` and routes to `on_error` — `revert_and_scan` /
`fix_tests` — which is **exactly the mis-framing this section exists to prevent**, taken
silently. The run looks correctly routed in the transcript.

**Required change at both sites:** switch `fragment: shell_exit` → **`fragment: harness_exit`**
(`lib/common.yaml:23-37`), which supplies `abstain_on_exit_3: true` and documents
`on_cannot_judge` as REQUIRED, then declare `on_cannot_judge:`. The existing `on_yes`/`on_no`/
`on_error` edges carry over unchanged.

**Anchor correction for the cited precedent.** `incremental-refactor.yaml`'s `verify_tests` is
**`fragment: harness_exit`**, not `shell_exit`-plus-an-edge, and it now sits at `:99-128`
(the `[ -z "$CMD" ] && exit 3` line is `:120`, `on_cannot_judge: failed` is `:127`) — every
`verify_tests:87` citation in this issue is stale post-BUG-3276. Read the shape there before
writing either state; it is the exact template, fragment line included.

#### EXIT-CODE COLLISION (2026-08-21) — the exit normalization is mandatory, not stylistic

**This is the sharpest hazard introduced by the fragment switch above, and neither the
MECHANISM CORRECTION nor the cited precedent states it.**

`abstain_on_exit_3: true` claims exit code 3 for "unresolvable". **pytest also exits 3** — its
documented *internal error* code (and `5` = no tests collected, `2` = interrupted). Under
`fragment: shell_exit` those all land identically on `on_no`. Under `harness_exit`, a pytest
internal error becomes a `cannot_judge` verdict:

| Loop | pytest exits 3 today (`shell_exit`) | pytest exits 3 after a naive fragment switch |
|---|---|---|
| `dead-code-cleanup` | `on_no: revert_and_scan` — deletions reverted | `on_cannot_judge` → new terminal-failure state — **deletions may not be reverted** |
| `test-coverage-improvement` | `on_no: fix_tests` — the loop repairs | `on_cannot_judge` → terminal failure — `fix_tests` never runs |

That is the same "no-signal vs. real-failure" mis-framing this section exists to prevent,
inverted: a *real* failure gets reported as *no signal*.

`incremental-refactor.yaml:118-123` is immune only because it **normalizes the exit space** —
`sh -c "$CMD"; rc=$?; [ "$rc" = 0 ] && exit 0; exit 1` collapses every non-zero to `1`, so the
state's own `exit 3` at `:120` is the only path to `cannot_judge`. Its in-file comment
(`:98-107`) calls this "own the exit-code space." Copying the `[ -z "$CMD" ] && exit 3` line
without the collapse is the defect.

**Second trap:** `incremental-refactor`'s template runs `sh -c "$CMD"` with **no `tee`**, but
both target states must keep their log — `revert_and_scan` reads `ll-dead-code-tests.txt`
(`dead-code-cleanup.yaml:88`) and `fix_tests` reads `ll-coverage-tests.txt`. Combining
`pipefail` + `tee` + the collapse is exactly where this slips, because `$?` after a pipeline is
the pipeline's status. Pinned body for both states (substitute each site's log path):

```bash
CMD=$(ll-config get project.test_cmd)      # or the context-first shape at
                                           # test-coverage-improvement.verify_tests
[ -z "$CMD" ] && exit 3                    # the ONLY sanctioned exit 3
set -o pipefail
eval "$CMD" 2>&1 | tee ${context.run_dir}/<log>.txt
rc=$?
[ "$rc" = 0 ] && exit 0
exit 1                                     # collapse ALL non-zero — pytest's own
                                           # exit 3 must never reach on_cannot_judge
```

**The omitted `RC=$?` normalization is deliberate — do not paste it back (added by the seventh
review, 2026-08-22).** Both cited precedents wrap the call in an exit-code check —
`CMD=$(ll-config get project.test_cmd); RC=$?; if [ "$RC" != "0" ]; then CMD=""; fi`
(`incremental-refactor.yaml:52-57`, and the same shape at `general-task.yaml`) — and this issue
elsewhere says to "model resolution on these shapes, not new ones," so an implementer copying the
template will re-add it and no reviewer will know which form is canonical. It is omitted here
because it is unreachable defensive code: **`main_config` returns 0 unconditionally**
(`cli/config.py:53`, whose docstring states *"Returns: 0 always — mirrors
BRConfig.resolve_variable()'s never-raise, config-or-default contract"*); it catches its own
`BRConfig` construction failure and its own `resolve_variable` failure internally and still
returns 0, printing nothing on stdout. The only non-zero exit reachable is `127` from an absent
`ll-config` binary, which leaves `$CMD` empty and is already caught by the very next line's
`[ -z "$CMD" ]`. Adding `RC` would therefore change no behavior at either site while adding four
lines to a body whose whole point is that its exit space is auditable at a glance. (This is a
divergence from the template only in the *resolution* prelude — the `[ -z "$CMD" ] && exit 3`
line and the collapse below it are copied exactly.)

**Required test.** Each site's regression test must include a case where `test_cmd` resolves to
a command that exits 3 (e.g. `test_cmd: "sh -c 'exit 3'"`), asserting the state exits **1**, not
3. Without it the collapse can be dropped later and every existing structural assertion still
passes.

**The body is `bash`, and must stay `bash` — verified 2026-08-21.** FSM shell actions run as
`cmd = ["bash", "-c", action]` (`scripts/little_loops/fsm/runners.py:297`), so `set -o pipefail`
is valid and `rc=$?` after the pipeline is the pipeline's status, which is what makes the collapse
work. Both target states already rely on this today. **Do not "harmonize" the body toward `sh`**
— the cited precedent (`incremental-refactor.yaml:120`) uses `sh -c "$CMD"` for the *inner*
command, which is unrelated to the outer interpreter; rewriting the outer body for POSIX `sh`
would silently drop `pipefail` under `dash`, making `rc` the exit status of `tee` (always 0) and
turning every test failure into a pass. The regression tests must therefore drive the body via
`subprocess.run(["bash", "-c", ...])`, not `sh`, or they will not reproduce the runtime shell.

#### Terminality of the two new states — pinned (2026-08-21)

The sections below say "a new non-committing state" without pinning where it goes or whether it
terminates. Both are pinned here, because the wrong answer at `dead-code-cleanup` is a live
hazard rather than a style question:

**State names — pinned (2026-08-21).** Both states are named here so the state and its required
dedicated assertion (see *Tests*) cannot drift apart, and so the assertion can be written before
the YAML:

| Loop | New state name(s) |
|---|---|
| `dead-code-cleanup.yaml` | `revert_unverifiable` (prompt) → `unverifiable` (bare terminal) |
| `test-coverage-improvement.yaml` | `unverifiable` (bare terminal) |

Do **not** reuse `failed` at either site: both loops already have a `failed` state with a
distinct ENH-2825 meaning (a failed *findings count* / a failed *retry budget*), and collapsing
"could not verify" into it destroys the distinction this whole section exists to create — the
run transcript would again show a no-signal skip as an ordinary failure.

##### TERMINAL-ACTION CORRECTION (2026-08-21) — a terminal state's action never runs

**Verified against the tree; load-bearing, and it supersedes every "the state reverts /
reports and terminates" phrasing elsewhere in this issue.**

`FSMExecutor.run` checks terminality **before** dispatching the action
(`scripts/little_loops/fsm/executor.py:601-636`):

```python
# Check terminal
if state_config.terminal:
    ...
    else:
        return self._finish("terminal")
```

The only fall-through is the BUG-158 / ENH-1631 carve-out for a state that *is* the FSM's
`on_max_steps` / `on_max_iterations` handler. That is why every terminal-state-with-an-action in
the tree is a cap handler (`evaluation-quality.summarize_max_steps`,
`generator-evaluator.max_steps_summary`, `vega-viz.max_steps_summary`,
`generator-evaluator-flux.max_steps_summary`, `cua-agent-desktop.max_steps_summary`) and why both
loops' existing `failed` states are bare.

**Consequence:** a `terminal: true` + `failure: true` state with **no `next:`** executes nothing.
Specifying one that "reverts the deletion" or "states the actual reason" produces neither — at
`dead-code-cleanup` the run would end with the deletions sitting unreverted and uncommitted in the
working tree and no artifact explaining why.

**Pinned resolution — the two loops differ, deliberately:**

- **`dead-code-cleanup` needs work done, so it needs an intermediate state.**
  `verify_tests.on_cannot_judge:` → **`revert_unverifiable`**, an `action_type: prompt` state
  that reverts the current lap's removals (see *The removed-files manifest* immediately below —
  **which files** is not self-evident here, unlike at `revert_and_scan`) and writes the reason —
  *no test command resolved; nothing was verifiable* — to
  `${context.run_dir}/ll-dead-code-unverifiable.txt`, with **`next: unverifiable`**. Model its
  body on `revert_and_scan` (`:84-97`) but with the no-signal framing rather than "tests failed",
  and **`next: unverifiable`, never `next: scan`** — a `next: scan` re-scans, re-deletes, and
  re-reaches an ungated `verify_tests` for the remainder of `max_steps`, deleting code on every
  lap with no verification at any of them. `unverifiable` itself is a **bare** `terminal: true` +
  `failure: true` marker with no action and no `next:`, matching `failed`'s existing shape.
- **`test-coverage-improvement` needs nothing done, so a bare terminal is correct.**
  `verify_tests.on_cannot_judge:` → **`unverifiable`**, bare `terminal: true` + `failure: true`.
  The loop added tests rather than deleting code, so there is nothing to revert, and a
  `terminal: true` *success* would report a green run that verified nothing. The distinction from
  `failed` is carried by the state name in the run transcript and the `terminated_by` record — it
  does **not** require an action, and must not be given one.
- **`dead-code-cleanup`'s `check_preconditions` entry gate routes `on_no:` straight to
  `unverifiable`**, not to `revert_unverifiable`: at loop start nothing has been deleted yet, and
  the gate's own shell action already wrote `precondition-failure.txt` before exiting 1.

**Step-budget consequence.** `revert_unverifiable` consumes one more of `dead-code-cleanup`'s
`max_steps: 15` on the skip path — see *Step budget* below.

##### The removed-files manifest — `remove_code` must record what it deleted (2026-08-22)

**Added by the seventh review. This is the sharpest gap the review found, and without it
`revert_unverifiable` cannot be written correctly.**

`revert_and_scan` works today because it has a file to name: its prompt says *"Read
`ll-dead-code-tests.txt` to see the failures … revert the most recent dead code removal **that
caused the failure**"* (`:87-92`), and the failing test output identifies it. **`revert_unverifiable`
has neither.** In the `cannot_judge` case no test ran, the log is empty, and there is no "failure"
to attribute — *every* removal from the current lap is unverified, not one of them. Meanwhile
`remove_code` (`:51-67`) deletes the **top 3 highest-confidence items**, potentially across three
different files, and declares **no `capture:`** — so nothing in the run state records what it
touched. The pinned instruction "revert … `git checkout -- <file>`" has no `<file>` to bind.

**The obvious fallback is unsafe here, specifically because of constraint 0.** A blanket
`git checkout -- .` is provably correct in `incremental-refactor` *only because* its
`check_preconditions` gates on a clean working tree, making every uncommitted change the failed
step's own work (`incremental-refactor.yaml:21-35` states exactly this rationale). Constraint 0
below deliberately declines to port that check for `dead-code-cleanup` — correctly, since users run
a cleanup loop mid-branch — which means a blanket revert here would discard the user's own
uncommitted edits alongside the loop's deletions. The two decisions are coupled: **declining the
clean-tree gate is what makes an explicit manifest mandatory.**

**Pinned resolution.** `remove_code`'s prompt gains a final instruction to append every file path
it modified, one per line, to `${context.run_dir}/ll-dead-code-removed-files.txt` (truncating the
file first, so it always describes only the current lap). `revert_unverifiable` then reverts
exactly that list — `while read -r f; do git checkout -- "$f"; done` framing in its prompt body —
and states plainly in `ll-dead-code-unverifiable.txt` which files it restored. If the manifest is
absent or empty, `revert_unverifiable` must say so and revert **nothing** rather than guess.

This is the one place this issue adds surface to a state it was not otherwise touching
(`remove_code`); it is listed in *Files to Modify* and carries its own AC and assertion.

*Not retrofitted to `revert_and_scan`.* That state's existing per-file, failure-log-driven revert
keeps working unchanged, and widening it to consume the manifest would change behavior on the
loop's normal failure path — out of scope for a resolution refactor. The manifest is additive; the
only new consumer is `revert_unverifiable`.

#### DECIDED (2026-08-21) — `dead-code-cleanup` gets a `check_preconditions` entry gate, config-first bare

**Pinned in scope.** This was the last item in this issue left as a "Recommendation," which meant
an implementer could reasonably ship either shape — and the two differ in scope, state count,
tests, and step budget. It is now **in scope and required**, alongside the mid-run
`harness_exit` skip edge (both, not either — same rationale
`incremental-refactor.yaml:100-108` gives for keeping both). Five constraints, each verified:

0. **Which checks the gate performs — copy three of the template's four, NOT the clean-tree
   one (added by the sixth review, 2026-08-22).** "Modelled on `incremental-refactor.yaml:20-86`"
   under-specifies the most consequential thing about the state. That template gates on **four**
   conditions: `test_cmd` resolves, the command is runnable (exit 127), the suite is green at
   baseline, **and the working tree is clean** (`git status --porcelain`, untracked included,
   `.loops` excluded). The fourth is load-bearing *there* and nowhere else: its stated rationale
   (`:22-30`) is that `incremental-refactor`'s `revert` does a **blanket**
   `git checkout -- . && git clean -fd`, which is only provably correct if every uncommitted
   change is the failed step's own work.

   **`dead-code-cleanup` does not have that revert.** `revert_and_scan` reverts **per file** —
   *"Revert the most recent dead code removal that caused the failure using `git checkout --
   <file>`"* (`:84-97`) — so a dirty tree is not a correctness hazard for it. Copying `:20-86`
   wholesale would make the loop **refuse to start on any dirty working tree**, a far larger
   behavior change than the one *Impact* describes ("unresolvable, unrunnable, or already-red")
   and one nobody asked for: users routinely run a cleanup loop mid-branch.

   **Pinned: gate on resolvable / runnable / green-baseline only. Do not port the clean-tree
   check.** If a later issue wants it, that is a separate decision with its own Impact entry.

0b. **Fragment: `shell_exit`.** The template declares `fragment: shell_exit` at
   `incremental-refactor.yaml:47`, with a bare `exit 0` / `exit 1` body and `on_yes`/`on_no`/
   `on_error`. Stated explicitly because every other fragment choice in this issue is pinned and an
   unpinned one invites a `harness_exit` paste — which would then need an `on_cannot_judge` edge
   and re-open the exit-3 collision at a state that has no reason to abstain.

1. **Config-first bare — do NOT paste `incremental-refactor.yaml:20-86` verbatim.** That
   template resolves context-first via `${context.test_cmd}`, but `dead-code-cleanup`'s
   `context:` block (`:13-14`) declares **only** `commit_message`. An undeclared
   `${context.test_cmd}` raises `InterpolationError: Path 'test_cmd' not found in context` at
   interpolation time *and* fails the gate's assertion (ii),
   `test_context_references_are_declared`. Use `CMD=$(ll-config get project.test_cmd)` — the
   general warning under *Proposed Solution* > *Precedence* applies here too, and this is the site
   most likely to be
   written by copying.
2. **Budget — two knobs, not one.** `dead-code-cleanup` is `max_steps: 15` (`:108`) **and**
   `timeout: 5400` (`:109`); the entry gate consumes one step *and* runs the suite once at loop
   start, adding roughly one test-suite duration to every run. Both budgets absorb it and both
   move: see *Step budget* below — this issue raises `max_steps` to `18` and `timeout` to `7200`.
3. **Routing — all three edges, including `on_error` (pinned by the seventh review,
   2026-08-22).** `exit 1` → `on_no: unverifiable`, the bare terminal-failure state (not `failed`,
   per *State names* above, and **not** `revert_unverifiable` — nothing has been deleted yet at
   loop start, and the gate's own shell action already wrote `precondition-failure.txt` before
   exiting 1), per the `incremental-refactor` precedent. `exit 0` → **`on_yes: scan`**, the
   loop's previous `initial:` — the success edge must re-enter the original pipeline, and no
   existing assertion pins it. `on_error:` → **`unverifiable`** as well: a `shell_exit` state
   whose body times out or dies on a signal produces the `error` verdict, and the gate's whole
   purpose is that an entry-time problem never reaches `scan`. It was the one edge in this issue
   left unpinned while every other fragment and edge was pinned; the template's own
   `on_error: failed` (`incremental-refactor.yaml:85`) is the precedent, retargeted to
   `unverifiable` per *State names*. All three edges need their own assertions —
   `test_required_states_exist` (`test_builtin_loops.py:12057`) is a subset check and will pass
   without any of them.
4. **`initial:` must move — and an existing assertion pins the old value (corrected by the
   seventh review, 2026-08-22).** `dead-code-cleanup.yaml:7` is `initial: scan` today. Change it
   to `initial: check_preconditions`, matching `incremental-refactor.yaml:4`. An entry state that
   is not the FSM's `initial` is never entered — `scan` still runs first and the gate never fires,
   while every structural *state-set membership* assertion passes.

   **This is an edit to an existing test, not a new assertion.**
   `TestDeadCodeCleanupLoop.test_required_top_level_fields`
   (`scripts/tests/test_builtin_loops.py:12054`) already asserts
   `data.get("initial") == "scan"` and **will fail** the moment `initial:` moves. Update that
   line to `"check_preconditions"`. Adding a second, separately-placed
   `assert fsm.initial == "check_preconditions"` while leaving `:12054` alone produces two
   assertions that contradict each other and a red suite. (Note this also falsifies the *Tests*
   preamble's blanket "none will break from the conversion" — see the correction there.)
5. **The two back-edges stay pointed at `scan` — do not retarget them to the gate
   (pinned by the seventh review, 2026-08-22).** `revert_and_scan.next` (`:97`) and `commit.next`
   (`:100`) are both `next: scan` and must remain so. Once `check_preconditions` becomes
   `initial:`, "every lap re-enters at the top" is the natural instinct and is wrong twice over:
   it would re-run the **full baseline test suite** on every lap (the gate's whole cost, paid 3×
   instead of once, against a wall clock — see *Step budget*), and it would consume a second step
   per lap on a budget this issue is already raising. The gate is an entry precondition, not a lap
   invariant; the mid-run `harness_exit` skip edge is what covers config changing under a running
   loop. Assert both `next:` values so a later edit cannot quietly "unify" them.

#### Step budget — `dead-code-cleanup` goes to `max_steps: 18` **and `timeout: 7200`**

`dead-code-cleanup` is `max_steps: 15` against a five-state lap (`scan` → `count_findings` →
`remove_code` → `verify_tests` → `commit` → `scan`), i.e. three full laps today.
This issue adds one step to the *success* path — the `check_preconditions` entry gate, once at
loop start — and one more on the *skip* path (`revert_unverifiable`). Left at 15, the loop drops
to two full laps plus a partial, a silent reduction in cleanup throughput that has nothing to do
with the resolution refactor.

Raise `max_steps` to **18** in the same edit. The comparable sibling, `incremental-refactor`,
carries its entry gate out of `max_steps: 30` (`:7`). Assert the new value so it is not
absent-mindedly reverted along with the gate.

**The wall clock binds too, and raising `max_steps` alone does not achieve this section's stated
goal (added by the seventh review, 2026-08-22).** `dead-code-cleanup.yaml:109` also carries
`timeout: 5400` — a **loop-level wall clock**, enforced as elapsed-time-since-start at
`fsm/executor.py:559-561` (`if elapsed > self.fsm.timeout * 1000: ...`), entirely independent of
`max_steps`. The entry gate does not merely consume a step: it **runs the whole test suite once**
before `scan` ever fires, and each of the three laps runs it again at `verify_tests`. Against a
fixed 90 minutes, adding a fourth full suite run plus three more steps means the wall clock, not
`max_steps`, becomes the binding constraint on any suite of real length — so the loop would still
land at "two laps plus a partial," and the `15 → 18` bump would buy nothing while *appearing* to
have fixed the problem.

Raise `timeout` to **7200** (2 h) in the same edit. That is the value the sibling
`test-coverage-improvement` already carries (`:18`) for a comparably suite-heavy loop, it covers
the added baseline run with margin (`verify_tests` alone is budgeted `timeout: 600`), and it keeps
the two knobs consistent with each other rather than leaving one of them silently dominant. Assert
it alongside `max_steps` — both are one-line scalars with nothing else holding them in place, and
reverting either one silently re-imposes the throughput cut this section exists to prevent.

*Rejected: mid-run skip only.* Cheaper, but leaves the loop deleting code before discovering it
cannot verify, at the one site this issue itself calls "the sharpest change in the whole family."
*Rejected: entry gate only.* Loses the defense against `.ll/ll-config.json` being edited out from
under a running loop.

The original recommendation text is retained below as the rationale.

#### Consider an entry precondition at `dead-code-cleanup` instead of a mid-run skip

**A better precedent landed after this issue was written.** BUG-3276 gave
`incremental-refactor` a `check_preconditions` **entry gate** (`:20-86`) that resolves
`test_cmd` and *refuses to start* — `exit 1` → `on_no: failed`, with a written
`precondition-failure.txt` naming the reason — when it is unresolvable, unrunnable
(exit 127), or already red.

The plan below has `dead-code-cleanup` delete code first, discover at `verify_tests` that it
cannot verify, and then rely on an LLM prompt state to revert correctly. For the one site this
issue itself calls *"the sharpest change in the whole family"*, refusing to start is strictly
safer and is now the sibling loop's shipped shape. **Add a `check_preconditions`-style entry
state to `dead-code-cleanup` modelled on `incremental-refactor.yaml:20-86`, in addition to the
mid-run `harness_exit` skip edge** (the mid-run branch stays as the defense against
`.ll/ll-config.json` being edited out from under a running loop — the same rationale
`incremental-refactor.yaml:100-108` gives for keeping both).
A new entry state needs its own assertion for the same subset-check reason noted below.

_This was written as a recommendation; it is now **decided and in scope** — see the DECIDED
block immediately above, which also pins the config-first-bare constraint that the cited
template violates **and the three-of-four check subset** (the template's fourth check, clean
working tree, must not be ported — constraint 0). Text kept here as rationale; read "modelled on
`incremental-refactor.yaml:20-86`" above as subject to those constraints, not as a verbatim copy
instruction._

#### `dead-code-cleanup.verify_tests`

The loop's states are `scan`, `count_findings`, `remove_code`, `verify_tests`,
`revert_and_scan`, `commit`, `done`, `failed` (`dead-code-cleanup.yaml:16-105`).

`on_error: revert_and_scan` already exists on `verify_tests`, so an `exit 1` skip would route
somewhere safe with zero structural change — but `revert_and_scan`'s prompt opens *"Tests failed
after dead code removal. Read ... to see the failures"* (`:84-90`) against a log that, in the skip
case, is **empty because no test ever ran**. That mis-frames a no-signal skip as a test failure
and hands an LLM an empty artifact to explain.

**Recommended shape — reserved exit code plus a dedicated edge**, matching
`incremental-refactor.yaml verify_tests:99-128`'s `[ -z "$CMD" ] && exit 3` / `on_cannot_judge`
precedent (`incremental-refactor.yaml:99-128`, see *Dependent Files*): switch `verify_tests` to
**`fragment: harness_exit`** (see *MECHANISM CORRECTION* above — an `on_cannot_judge:` edge on
the current `shell_exit` fragment is inert) and point its `on_cannot_judge:` at a new
non-committing **`action_type: prompt`** state, `revert_unverifiable`, that reverts the deletions
and states the actual reason (no test command configured, nothing verifiable), with
`next: unverifiable` — a **bare** `terminal: true` + `failure: true` marker. The revert/report
work **cannot** live on the terminal state itself: a terminal state's action never executes
(*TERMINAL-ACTION CORRECTION* above). Keeps a real test failure's
`on_no: revert_and_scan` path distinct from "there was no signal," which matters because the two
warrant different prompts and different `excluded.txt` bookkeeping. If a new state is added, it
needs its own assertion — `TestDeadCodeCleanupLoop.test_required_states_exist`
(`test_builtin_loops.py:12057`) is a subset check and will pass without it (see *Tests*). Also see
*Consider an entry precondition*
above: the recommended shape for this loop is this skip edge **plus** an
`incremental-refactor`-style `check_preconditions` entry gate.

#### `test-coverage-improvement.verify_tests`

Same treatment, same reasoning. Verified 2026-08-21: this state's edges are `on_yes: commit`,
`on_no: fix_tests`, `on_error: fix_tests` (`:157-159`). `fix_tests` is a `action_type: prompt`
state whose body instructs *"Fix failing tests — diagnose before changing anything"* against
`ll-coverage-tests.txt` — which, in the skip case, is **empty because no test ever ran**. Routing
an empty `CMD` there is the exact `revert_and_scan` mistake in a different loop: an LLM asked to
diagnose failures that do not exist.

Switch `verify_tests` to **`fragment: harness_exit`** and add `on_cannot_judge: unverifiable` —
the fragment switch is required, not optional (see *MECHANISM CORRECTION* above). Unlike
`dead-code-cleanup` there is nothing to revert here — the loop added tests rather than deleting
code — so `unverifiable` is a **bare** `terminal: true` + `failure: true` state with no action and
no `next:`, and needs no intermediate prompt state. Do **not** give it a "report" action: a
terminal state's action never runs (*TERMINAL-ACTION CORRECTION* above), so the distinction from
`failed` is carried by the state name in the transcript, not by anything the state does. It
carries the same subset-check caveat:
`TestTestCoverageImprovementLoop.test_required_states_exist`
(`test_builtin_loops.py:12091`) will pass without validating it.

##### DECIDED (2026-08-22) — `test-coverage-improvement` gets **no** entry gate

**Added by the seventh review.** The issue argues at length for giving `dead-code-cleanup` a
`check_preconditions` gate and is simply *silent* about its sibling — which reads as an oversight
rather than a decision, and is the first thing a reviewer will ask. It is a decision. Recorded
with its cost so nobody re-opens it or, worse, adds one mid-implementation for symmetry.

**Decided: no gate. Mid-run `on_cannot_judge: unverifiable` only.** The rationale for
`dead-code-cleanup`'s gate does not transfer: there, `verify_tests`'s `on_yes` **commits
deletions**, and discovering at `verify_tests` that nothing is verifiable means code has already
been destructively removed. Here the loop *adds* test files. Nothing irreversible has happened by
the time `verify_tests` abstains, so refusing to start buys no safety — only earlier feedback.

**The accepted cost, stated plainly.** Under `test_cmd: null` this loop still runs
`measure` (a full coverage run — `measure` resolves `COV_CMD` independently and does not consult
`test_cmd` at all, so a gate would not spare it), `extract_percentage`, `identify_gaps`, and
`write_tests` (an LLM state budgeted `timeout: 900`) before `verify_tests` finally abstains and
routes to `unverifiable`. The run therefore terminates having spent one coverage run and two LLM
states, and **leaves the newly-written test files uncommitted in the working tree** with no revert
and no note — `unverifiable` is a bare terminal, so it cannot write one (*TERMINAL-ACTION
CORRECTION*).

That is judged acceptable: the leftovers are **additive** (new test files, not deletions), they
are plainly visible in `git status`, and the existing `revert` state (`:188-197`) is not a
suitable target because its `next: measure` would send the loop back around rather than
terminating. Adding a gate here would mean a second new state, a second baseline suite run, a
second set of edge assertions, and another `max_steps`/`timeout` argument — real cost for a
loop whose failure mode is untidy rather than destructive. Revisit only if the leftover-artifact
complaint shows up in practice; it is not a resolution-refactor concern.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/dead-code-cleanup.yaml` — the inline read at `:76`, plus six edits
  outside it: **`:7` `initial: scan` → `initial: check_preconditions`** (without it the new entry
  gate is never entered), **`:108` `max_steps: 15` → `18`** and **`:109` `timeout: 5400` → `7200`**
  (*Step budget* — the wall clock binds independently of `max_steps`), the new
  `check_preconditions` entry gate, the two new states `revert_unverifiable` / `unverifiable`
  (*Terminality*), and a final instruction appended to **`remove_code`'s prompt (`:54-66`)**
  writing the removed-files manifest (*The removed-files manifest* — `revert_unverifiable` cannot
  be written without it). `revert_and_scan.next` (`:97`) and `commit.next` (`:100`) stay
  `scan` — unchanged, but assert them (DECIDED constraint 5)
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — `:37-48` (the dead `CMD` block in
  `measure`) **deleted, not converted**; `:143-159` (`verify_tests`, inline read at `:152`)
  converted context-first and
  switched to `fragment: harness_exit`; the `:23` `test_cmd` declaration **stays** and becomes
  functional per the pinned decision (a); new `unverifiable` terminal state
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — the teardown (step 6): grow
  `_PERMANENT_EXEMPTIONS` to three, delete `_PENDING_CONVERSION`, delete
  `test_pending_conversion_sites_still_exist`, collapse `_EXEMPT`, widen `_INLINE_ACCESS_RE`

Out of scope: the six mechanical conversions (ENH-3277); `oracles/code-run-gate.yaml` (permanent
exemption, BUG-3269 §1d); `incremental-refactor.yaml` (BUG-3276).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/incremental-refactor.yaml` — the **primary template** for this
  issue, post-BUG-3276. Its `check_preconditions` entry gate is at `:20-86`, its
  `verify_tests` is `fragment: harness_exit` at `:99-128` (`[ -z "$CMD" ] && exit 3` at `:120`,
  `on_cannot_judge: failed` at `:127`), its `initial: check_preconditions` at `:4`, and its
  `max_steps: 30` at `:7`. Read the shape there before writing either state — fragment line
  included. **Any `verify_tests:87` citation inherited from ENH-3277 is stale.**
- `scripts/little_loops/loops/general-task.yaml:57` and
  `scripts/little_loops/loops/rl-coding-agent.yaml:62-63` — the other two already-converted
  precedent sites (BUG-3269). Model resolution on these shapes, not new ones.
- `scripts/little_loops/fsm/executor.py:601-636` — the terminal-state short-circuit that makes a
  terminal state's `action` dead code (*TERMINAL-ACTION CORRECTION*)
- `scripts/little_loops/fsm/executor.py:559-561` — the loop-level wall-clock check
  (`elapsed > self.fsm.timeout * 1000`), enforced independently of `max_steps`; the reason
  `timeout: 5400` must rise alongside `max_steps` (*Step budget*)
- `scripts/little_loops/cli/config.py:53` — `main_config`'s "Returns 0 always" contract, the
  reason the template's `RC=$?` normalization is deliberately omitted from the pinned body
- `scripts/little_loops/fsm/runners.py:297` — `cmd = ["bash", "-c", action]`; the reason
  `set -o pipefail` is valid in these bodies and must stay `bash`
- `scripts/little_loops/loops/lib/common.yaml:15-22` (`shell_exit`) and `:23-37`
  (`harness_exit`, which supplies `abstain_on_exit_3: true`)

### Tests

_No existing test in `scripts/tests/` executes the shell body of either site at the
value-resolution level — every current test is structural only (state-set membership, `fragment:`
field, routing-edge shape), so none gives coverage of the conversion._

**ONE existing test breaks, and it is not optional (corrected by the seventh review,
2026-08-22).** The earlier blanket claim that "none will break from the conversion" was wrong:
`TestDeadCodeCleanupLoop.test_required_top_level_fields`
(`scripts/tests/test_builtin_loops.py:12054`) asserts `data.get("initial") == "scan"` and fails
the moment `initial:` moves to `check_preconditions`. **Edit that line rather than adding a
parallel assertion** — see DECIDED constraint 4. Everything else below is genuinely new.

**All test-file line anchors below were re-verified against the tree on 2026-08-22 and every one
of them had drifted** — `test_builtin_loops.py` moved by roughly 350–650 lines when ENH-3277
landed, so anchors inherited from the split are stale by a full screen or more. The current
values are: `TestRlCodingAgentObserveTestCmdResolution` **:10820** (was cited 10747-10799),
`TestDeadCodeCleanupLoop.test_required_states_exist` **:12057** (was L11688),
`TestTestCoverageImprovementLoop.test_required_states_exist` **:12091** (was L11722),
`TestIncrementalRefactorLoop` **:12284**, its
`test_verify_tests_resolves_context_first_then_ll_config` **:12337** (was L11983), and its
`test_revert_has_exactly_one_inbound_edge` **:12358** (was :11999-12006). Prefer grepping the test
*name* over trusting any line number in this issue.

- **Subprocess resolution tests for both `verify_tests` states**, driven through **`bash -c`**,
  asserting all three config cases (set / present-null / absent). Model on
  `TestRlCodingAgentObserveTestCmdResolution` (`test_builtin_loops.py:10820`). Add a fourth
  case at `test-coverage-improvement.verify_tests` only — context wins over `ll-config get`, per
  `TestIncrementalRefactorLoop.test_verify_tests_resolves_context_first_then_ll_config` (`:12337`).
  **Drive through `bash`, not `sh`**: under `dash`, `set -o pipefail` is unavailable and `rc=$?`
  becomes `tee`'s status (always 0), so an `sh`-driven test reports a passing gate for a failing
  suite.
- **Exit-3 collision case at both states.** With `test_cmd` set to a command that exits 3 (e.g.
  `test_cmd: "sh -c 'exit 3'"`), the state must exit **1**, not 3 — proving the non-zero collapse
  is present and that pytest's own internal-error code cannot reach `on_cannot_judge`. Also assert
  `[ -z "$CMD" ]` still exits **3**.
- **Dedicated assertions for all four new/changed states** — `unverifiable` in both loops,
  `dead-code-cleanup`'s `check_preconditions` and `revert_unverifiable`. Assert each state's
  `terminal`/`failure` flags, its absence of a `next:`, and its inbound edge (the
  `TestIncrementalRefactorLoop.test_revert_has_exactly_one_inbound_edge` shape, `:12358`).
  `TestDeadCodeCleanupLoop.test_required_states_exist` (`:12057`) and
  `TestTestCoverageImprovementLoop.test_required_states_exist` (`:12091`) are **subset** checks and
  will silently pass without any of this.
- **Assert neither `unverifiable` state carries an action**, and that `revert_unverifiable` is
  non-terminal with `next: unverifiable`. This is the executable form of the *TERMINAL-ACTION
  CORRECTION*: an `action` on a terminal state is silently dead, so nothing else in the suite
  would catch someone "simplifying" the two states back into one.
- **Assert `dead-code-cleanup`'s `initial == "check_preconditions"`, `max_steps == 18`, and
  `timeout == 7200`.** All three are one-line scalars a future edit can revert without breaking
  any state-set or edge-shape assertion, and each reversion silently disables the entry gate,
  cuts a cleanup lap, or re-imposes the wall-clock ceiling the added baseline run now exceeds
  (*Step budget*). The `initial` assertion is the **edit** at `:12054`, not an addition.
- **Assert all three of `check_preconditions`' edges** — `on_yes == "scan"`,
  `on_no == "unverifiable"`, `on_error == "unverifiable"` (DECIDED constraint 3). Each is a
  one-line scalar with nothing else holding it in place, and `on_error` in particular has no
  natural reader: a wrong or missing value there routes an entry-time crash into the pipeline the
  gate exists to protect.
- **Assert the two back-edges still point at `scan`** — `revert_and_scan.next == "scan"` and
  `commit.next == "scan"` (DECIDED constraint 5). Once `check_preconditions` is `initial:`,
  retargeting either to the gate is a plausible "cleanup" that would re-run the baseline suite
  every lap; no other assertion would catch it.
- **Assert the removed-files manifest contract** (*The removed-files manifest*): `remove_code`'s
  action text references `ll-dead-code-removed-files.txt`, and `revert_unverifiable`'s does too.
  Without both halves the revert has no file list to act on and silently reverts nothing — a
  failure that leaves unverified deletions in the tree while the transcript reads as a clean
  abstention.
- **Pin `evaluate.abstain_on_exit_3` / the `harness_exit` fragment at both states**, so a future
  edit that reverts the fragment to `shell_exit` while leaving the `exit 3` body in place fails
  loudly rather than silently re-routing to `on_error`.
- **Guard asserting no state in `test-coverage-improvement.yaml` resolves a `CMD` it never
  evaluates** — the defect that made `:45` dead would otherwise be reintroducible.
- **The gate itself**, with `_PENDING_CONVERSION` shrinking to zero and finally removed.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569` — **required at step 6.** The sentence (inside
  the "Resolving a Project Command Inside a Loop" section, `:516-569`) becomes false the moment
  `_PENDING_CONVERSION` is deleted. Rewrite it to name the three **permanent** exemptions
  (`oracles/code-run-gate.yaml`, `rn-refine.yaml`, `auto-refine-and-implement.yaml`) and their
  shared §1d rationale — absent ≡ null ≡ skip, never guess. Leaving it stale points the guide at
  closed issues as pending work.

  **Expect to find ENH-3288, not ENH-3277 (anchor corrected 2026-08-22).** ENH-3277's step 5c
  retargets the identifier in place — the line reads *"A handful of other loops are a temporary
  exemption pending **ENH-3288's** conversion pass"* by the time this issue starts, and ENH-3277's
  own Docs AC requires `grep -n 'ENH-3277' docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` to return
  nothing. Do not grep for `ENH-3277` here and conclude the anchor is stale or the work already
  done; the sentence still needs this issue's rewrite, because after the teardown the exemptions
  are permanent rather than pending anyone's pass. _(That interim retarget was itself deferred to
  this issue until ENH-3277's fifth review pulled it forward: between the two issues the guide
  would otherwise have named a closed issue as owner of a pending pass — the same defect ENH-3277
  fixes at three anchors inside the gate file.)_
- `docs/guides/LOOPS_REFERENCE.md:1347` — `test-coverage-improvement`'s `test_cmd`
  context-variable row, currently documenting an inert knob (*Dead site*). Per the pinned decision
  (a) it **stays** and becomes true — no edit needed, but re-verify the wording matches
  `verify_tests`'s new context-first behavior.
- `scripts/little_loops/loops/README.md:33` — `auto-refine-and-implement`'s `test_cmd`/`lint_cmd`
  row. **No edit expected under Option A** (the file is not converted), but re-verify it does not
  describe a conversion that never happened.
- `skills/audit-loop-run/SKILL.md:~277` — documents `verify_verdict: "skipped"` for
  `auto-refine-and-implement`'s verify step. **No edit needed under Option A** — the file is not
  converted, so those semantics are preserved byte-for-byte. Sanity check only.

## Acceptance Criteria

**`test-coverage-improvement.yaml`**

- [ ] `:37-48` (the dead `CMD` block in `measure`) is **deleted**, not converted
- [ ] `verify_tests` (`:143-159`, inline read at `:152`) uses the context-first shape, so the
      `:23` `test_cmd` declaration becomes live
- [ ] `verify_tests` is `fragment: harness_exit` with a declared `on_cannot_judge: unverifiable`
- [ ] `unverifiable` exists as a **bare** `terminal: true` + `failure: true` state — no `action`,
      no `next:`

**`dead-code-cleanup.yaml`**

- [ ] `:76` converted, **config-first bare** (not context-first — `InterpolationError`)
- [ ] `verify_tests` is `fragment: harness_exit` with `on_cannot_judge: revert_unverifiable`
- [ ] `revert_unverifiable` exists as `action_type: prompt` with `next: unverifiable`, and is
      `verify_tests.on_cannot_judge`'s only target
- [ ] `remove_code`'s prompt writes every modified file path to
      `${context.run_dir}/ll-dead-code-removed-files.txt` (truncating first), and
      `revert_unverifiable` reverts **exactly that list** — never a blanket `git checkout -- .`,
      which is unsafe precisely because the gate does not check for a clean tree. With the
      manifest absent or empty, `revert_unverifiable` reverts nothing and says so
- [ ] `unverifiable` exists as a bare `terminal: true` + `failure: true` state
- [ ] `check_preconditions` entry gate exists (`fragment: shell_exit`, **config-first bare**),
      routing `on_yes: scan`, `on_no: unverifiable`, **and `on_error: unverifiable`**
- [ ] `revert_and_scan.next` and `commit.next` are both still `scan` — the gate is an entry
      precondition, not a per-lap one
- [ ] The gate checks **resolvable / runnable / green-baseline only** — it does **not** carry
      `incremental-refactor`'s clean-working-tree check, whose rationale is that loop's blanket
      `git checkout -- . && git clean -fd` revert and does not transfer to `dead-code-cleanup`'s
      per-file `git checkout -- <file>`. Added by the sixth review; assert no `git status
      --porcelain` in the gate's action
- [ ] `:7` is `initial: check_preconditions`
- [ ] `:108` is `max_steps: 18` **and `:109` is `timeout: 7200`** — the loop-level wall clock is
      enforced independently of `max_steps` (`fsm/executor.py:559-561`), so raising only the step
      budget leaves the added baseline suite run to be absorbed by an unchanged 90 minutes and the
      step bump buys nothing

**Both converted bodies**

- [ ] Collapse every non-zero exit to `1` (`rc=$?; [ "$rc" = 0 ] && exit 0; exit 1`) after the
      `pipefail`/`tee` pipeline
- [ ] `[ -z "$CMD" ] && exit 3` is the **only** path to exit 3
- [ ] The `tee` log is kept (`revert_and_scan` reads `ll-dead-code-tests.txt`; `fix_tests` reads
      `ll-coverage-tests.txt`)

**Gate teardown**

- [ ] `_PERMANENT_EXEMPTIONS` holds exactly three entries (`oracles/code-run-gate.yaml`,
      `rn-refine.yaml`, `auto-refine-and-implement.yaml`) with the §1d rationale in its comment
- [ ] `_PENDING_CONVERSION` and `test_pending_conversion_sites_still_exist` are deleted;
      `_EXEMPT = _PERMANENT_EXEMPTIONS`
- [ ] `_INLINE_ACCESS_RE` matches the two-step `project = cfg.get('project', {})` /
      `project.get('test_cmd')` binding shape, and the only hits across
      `scripts/little_loops/loops/**` are the three permanent exemptions
- [ ] `rn-refine.yaml` and `auto-refine-and-implement.yaml` are **byte-for-byte unchanged**
- [ ] `test_no_inline_project_command_config_read`, `test_context_references_are_declared`, and
      `test_general_task_and_rl_coding_agent_are_not_exempt` all remain and pass

**Tests** (all new except the first, which is an edit)

- [ ] `TestDeadCodeCleanupLoop.test_required_top_level_fields`
      (`test_builtin_loops.py:12054`) updated from `initial == "scan"` to
      `"check_preconditions"` — this existing assertion **fails** otherwise; do not add a second,
      contradicting one elsewhere
- [ ] Subprocess resolution tests for both states, driven through `bash -c`, all three config
      cases (plus the context-first fourth case at `test-coverage-improvement`)
- [ ] Exit-3 collision case at both states: `sh -c 'exit 3'` → state exits **1**; empty `CMD` →
      exits **3**
- [ ] Dedicated assertions for all four new/changed states, plus `initial`, `max_steps`,
      `timeout`, and `abstain_on_exit_3`/`harness_exit` at both states
- [ ] All three `check_preconditions` edges asserted (`on_yes: scan`, `on_no: unverifiable`,
      `on_error: unverifiable`), and both back-edges asserted still `scan`
      (`revert_and_scan.next`, `commit.next`)
- [ ] Assertion that both halves of the removed-files manifest contract are present —
      `remove_code` writes `ll-dead-code-removed-files.txt` and `revert_unverifiable` consumes it
- [ ] Assertion that neither `unverifiable` carries an action
- [ ] Guard against a state resolving a `CMD` it never evaluates

**Docs**

- [ ] `HARNESS_OPTIMIZATION_GUIDE.md:569` names the three permanent exemptions and no longer calls
      them temporary or pending. Verified by `grep -nE 'ENH-3277|ENH-3288|temporary exemption'
      docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` returning **no lines** — the incoming text names
      ENH-3288 (retargeted by ENH-3277 step 5c), so a grep for `ENH-3277` alone proves nothing
- [ ] `LOOPS_REFERENCE.md:1347`, `loops/README.md:33`, `skills/audit-loop-run/SKILL.md:~277`
      re-verified against final behavior

**Exit gates**

- [ ] `ll-loop validate` passes for both touched loops
- [ ] The scoped grep (below) returns empty
- [ ] `python -m pytest scripts/tests/` exits 0
- [ ] Manual smoke: `dead-code-cleanup` in a scratch project with `test_cmd: null` does **not**
      reach `commit`

## Implementation Steps

**Prerequisite: ENH-3277 must land first.** It converts the six mechanical sites and shrinks
`_PENDING_CONVERSION` from nine entries to four (`dead-code-cleanup.yaml`,
`test-coverage-improvement.yaml`, `rn-refine.yaml`, `auto-refine-and-implement.yaml`). Starting
this issue earlier means racing it on the same set literal.

1. **Read the pinned analysis before writing any shell.** *MECHANISM CORRECTION* (the fragment
   switch is required; an `on_cannot_judge:` edge on `shell_exit` is inert), *EXIT-CODE
   COLLISION* (the non-zero collapse is mandatory; pytest itself exits 3), *TERMINAL-ACTION
   CORRECTION* (a terminal state's action never runs), *Terminality*, *State names*, *Step
   budget*. Then read `incremental-refactor.yaml:20-86` and `:99-128` as the live template.
2. **`test-coverage-improvement.yaml` first** — it has no entry gate and nothing to revert, so it
   is the smaller of the two. Delete the dead `CMD` block at `:37-48`; apply *Dead site* decision
   **(a)** — `verify_tests` gets the context-first shape, the `:23` declaration stays,
   `LOOPS_REFERENCE.md:1347` stays. Switch `verify_tests` to `fragment: harness_exit`, add
   `on_cannot_judge: unverifiable`, add the bare `unverifiable` terminal state, and apply the
   pinned body **including the non-zero collapse**. Land its regression tests in the same change.
3. **`dead-code-cleanup.yaml` second**, since its `on_yes` commits deletions and it carries the
   most added surface. Convert `:76` config-first bare; switch `verify_tests` to
   `fragment: harness_exit` with `on_cannot_judge: revert_unverifiable`; **append the
   removed-files manifest instruction to `remove_code`'s prompt** (*The removed-files manifest* —
   do this **before** writing `revert_unverifiable`, which has no file list to act on without
   it); add `revert_unverifiable` (prompt, reverts exactly the manifest, `next: unverifiable`)
   and the bare `unverifiable` terminal; add the `check_preconditions` entry gate
   (`fragment: shell_exit`, **config-first bare**, **resolvable/runnable/green-baseline checks
   only — no clean-tree check**, `on_yes: scan`, `on_no: unverifiable`, `on_error: unverifiable`);
   move `initial` to `check_preconditions`; raise `max_steps` to `18` **and `timeout` to `7200`**;
   leave `revert_and_scan.next` and `commit.next` at `scan`. Land its regression tests in the same
   change — including the **edit** to `test_required_top_level_fields`
   (`test_builtin_loops.py:12054`), which fails as soon as `initial:` moves.
4. **Verify each loop before moving on:** `ll-loop validate`, the scoped grep, and the gate with
   that file's entry removed from `_PENDING_CONVERSION`.
5. **Execute ENH-3277's Option A decision.** Move `rn-refine.yaml` and
   `auto-refine-and-implement.yaml` from `_PENDING_CONVERSION` into `_PERMANENT_EXEMPTIONS`
   (`:51`), growing it from one entry to three, and extend that constant's comment to carry the
   §1d rationale (absent ≡ null ≡ skip, never guess) for all three. Both YAMLs stay byte-for-byte
   unchanged. Do **not** build `ll-config get --raw`.
6. **Empty `_PENDING_CONVERSION` and delete the constant.** Four coupled edits in
   `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`, not one — deleting the constant alone
   is a `NameError`:
   - grow `_PERMANENT_EXEMPTIONS` (`:51`) to three per step 5 — **this must land before the set
     below is deleted**, or the gate fails on those two files;
   - delete the `_PENDING_CONVERSION` set (`:56-63`);
   - delete `test_pending_conversion_sites_still_exist` (`:146-156`), which dereferences it;
   - collapse `_EXEMPT = _PERMANENT_EXEMPTIONS | _PENDING_CONVERSION` (`:65`) to
     `_EXEMPT = _PERMANENT_EXEMPTIONS`.

   _(All four anchors re-verified 2026-08-22; the values inherited from the split — `:49`,
   `:55-65`, `:148-156`, `:67` — were each off by one to six lines after ENH-3277 rewrote the
   module docstring and the set's comments. The module docstring at `:24-30` also still describes
   a "shrinking exemption list of four remaining sites" and names ENH-3288's definition of done;
   rewrite it in the same edit or it outlives the constant it documents.)_

   Plus the doc edit: **`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569`**'s "temporary exemption
   pending **ENH-3288's** conversion pass" sentence must be rewritten to name the three permanent
   exemptions. Deleting the constant without it leaves the guide advertising closed issues as
   pending work forever. (The line named *ENH-3277* until that issue's step 5c retargeted it —
   see *Documentation*. Grep for `ENH-3288`, not `ENH-3277`.)

   Leave `test_no_inline_project_command_config_read`, `test_context_references_are_declared`, and
   `test_general_task_and_rl_coding_agent_are_not_exempt` in place. The inline-read assertion then
   holds with exactly three permanent exemptions. **This is the definition of done for the whole
   ENH-3277 family.**

7. **Widen `_INLINE_ACCESS_RE` (`:74-84`) — a verified blind spot.** The regex matches only a
   *chained* access (`get('project', {}).get('test_cmd')` or `['project']['test_cmd']`). It does
   **not** match the two-step binding shape:

   ```python
   project = cfg.get('project', {})
   test_cmd = project.get('test_cmd')
   ```

   That is precisely `auto-refine-and-implement.yaml:432-434` — **both** keys, `test_cmd` at
   `:433` and `lint_cmd` at `:434`. So its `_PENDING_CONVERSION` entry has been vacuous all
   along; the gate never detected it.

   **Why widen it at all, precisely.** Widening changes *nothing* for the exempted files — they
   sit in `_PERMANENT_EXEMPTIONS` and are skipped before the regex runs either way. The value is
   entirely forward-looking: Option A leaves `auto-refine-and-implement.yaml` in the tree
   permanently as a **copyable precedent for a shape the gate cannot see**, so the next loop that
   clones it lands an undetected inline read. Treat this as hardening the gate, not as part of
   this issue's correctness.

   Add an alternation for a `project`-bound local followed by `.get('<key>')`, then confirm the
   exempted files are the only hits.

   **Pre-verified (2026-08-21) — the confirmation step will pass.** Enumerated every loop YAML
   under `scripts/little_loops/loops/**` containing `get('project'`: `auto-refine-and-implement`,
   `dead-code-cleanup`, `evaluation-quality`, `fix-quality-and-tests`, the three `harness-*`,
   `rn-refine`, `test-coverage-improvement` (all converted or exempt by then),
   `oracles/code-run-gate.yaml` (permanently exempt), and **`lib/composer.yaml:133`** — the only
   non-exempt survivor. That one is `catalog.get('project', []) + catalog.get('builtin', [])` over
   a *loop catalog*, with no command key following, so the widened alternation does not match it.
   No new exemption is needed. Recorded here so this is not re-derived at implementation time.

8. **Final verification.**

   ```bash
   grep -rn "\.get('test_cmd'\|\.get('lint_cmd'" scripts/little_loops/loops/ \
     --include='*.yaml' \
     | grep -v -e 'rn-refine.yaml' -e 'auto-refine-and-implement.yaml' -e 'oracles/code-run-gate.yaml'
   ```

   Expected output: empty. The exclusions are permanent — under Option A those three keep their
   inline parse forever, so an unscoped grep reads as a failed conversion at every checkpoint.

   Then `python -m pytest scripts/tests/` exits 0, and a manual smoke of `dead-code-cleanup` in a
   scratch project with `test_cmd: null` confirms it does **not** reach `commit`.

**Rollback seam:** independent per-file edits. If one conversion misbehaves in a consuming
project, revert that file and re-add its exemption — as a `_PENDING_CONVERSION` entry if step 6
has not yet run, or as a `_PERMANENT_EXEMPTIONS` entry (with a rationale comment) if it has, since
step 6 deletes the former.

## Scope Boundaries

**In scope:** `dead-code-cleanup.yaml` and `test-coverage-improvement.yaml` in full — two inline
reads (one converted, one deleted as dead), two `fragment: shell_exit` → `harness_exit` switches,
the non-zero exit collapse at both, four new states (`unverifiable` ×2, `revert_unverifiable`,
`check_preconditions`), the removed-files manifest instruction appended to
`dead-code-cleanup.remove_code`, and `dead-code-cleanup`'s `initial:`, `max_steps:` and
`timeout:` edits — plus the full gate teardown (moving two entries to `_PERMANENT_EXEMPTIONS`,
deleting `_PENDING_CONVERSION`, widening `_INLINE_ACCESS_RE`) and the exemption-list doc edits.

**Out of scope — pre-existing, surfaced by the seventh review:**
`test-coverage-improvement.extract_percentage`'s `route: {target: commit}` (`:85-86`) lets a repo
already at `context.coverage_target` reach `commit` without ever entering `verify_tests`. That is
a convergence-routing question, not a command-resolution one, and this issue's guarantee is
scoped accordingly (*Expected Behavior*). Also out of scope: giving `test-coverage-improvement` a
`check_preconditions` entry gate — considered and declined with its cost recorded, see *DECIDED —
`test-coverage-improvement` gets no entry gate*.

**Out of scope — belongs to ENH-3277:** `fix-quality-and-tests.yaml`, the three `harness-*.yaml`
(and their `# EXAMPLE:` scaffold comments), and `evaluation-quality.yaml`'s `:58` read and `:63`
hardcode — six mechanical conversions with no control-flow change. Also its *CAPTURE CORRECTION*
(`capture:` reads stdout, not the `tee` target), which applies only to `evaluation-quality`.

**Out of scope — belongs to BUG-3269:** the three defective sites (`general-task.yaml:37`,
`rl-coding-agent.yaml:60,68`); `general-task`'s `SKIP` sentinel, §3b reader-side normalization,
and §3c resolve-once handoff; the `cli/config.py` stderr warning; the mirror-drift gate's
creation; the `HARNESS_OPTIMIZATION_GUIDE.md` convention write-up.

**Out of scope — permanently:** `oracles/code-run-gate.yaml` (BUG-3269 §1d — alias-pair
resolution `typecheck_cmd|type_cmd` that `ll-config get` cannot express), plus `rn-refine.yaml`
and `auto-refine-and-implement.yaml:433-436` per ENH-3277's Option A. All three keep their inline
parse and their `.ll/ll.local.md` bypass indefinitely; this issue only moves the latter two
between constants.

**Out of scope — split separately:** generalizing BUG-3276's this-repo-hardcode gate over all
built-in loops → **ENH-3281**. Note that deleting `test-coverage-improvement.yaml:37-48` leaves
`measure`'s only executed command as the hardcoded
`COV_CMD="python -m pytest --cov --cov-report=term-missing"` fallback at `:50-59` — so after this
issue, `measure` runs a pytest-shaped command in a project that may have opted out of pytest
entirely. That is the *hardcode* defect class, not the *inline-read* class; it belongs to
ENH-3281 and is deliberately left behind here. Flagged so a reviewer does not read the surviving
hardcode as an oversight. The `context.coverage_cmd` knob (`:24`) already overrides it and,
unlike `context.test_cmd`, is live.

**Out of scope — split separately:** `incremental-refactor.yaml` → BUG-3276 (landed). It is this
issue's template, not its target.

**Explicitly not a call site:** `auto-refine-and-implement.yaml:679-680` reads
`cfg.project.test_cmd` / `cfg.project.lint_cmd` off a real `BRConfig` instance inside an embedded
Python block. It already resolves through `ProjectConfig` **and** already honors
`.ll/ll.local.md`. Do not "convert" it.

**No new production code.** This issue touches loop YAMLs, tests, and docs only. `ll-config get`'s
resolution is unchanged and no CLI surface is added — `cli/config.py` is **not** modified;
`--raw` belonged to ENH-3277's rejected Option C.

## Program Design

### Signatures

- `main_config() -> int` — **existing**, unchanged (`cli/config.py:54`); invoked from shell as
  `ll-config get project.test_cmd`. The single resolution path both converted sites delegate to.
  Takes no parameters — the key arrives as `args.key` from `parser.parse_args()`.
- `resolve_variable(var_path: str) -> str` — **existing**, unchanged (`config/core.py:1044`);
  returns `None` for a present-and-null key, which is the load-bearing opt-out signal each site's
  `[ -z "$CMD" ]` branch tests for.
- `ProjectConfig.from_dict(data: dict) -> ProjectConfig` — **existing**, unchanged
  (`config/core.py:208`); its field defaults (`:188-195`) are the only authority for the
  absent-key fallback. Its `data.get("test_cmd", "pytest")` (`:214`) is precisely where absent and
  defaulted collapse — the lossiness that makes `rn-refine` and `auto-refine` exempt rather than
  converted.

**No new signatures.**

### Call Path

- each converted state → `ll-config get project.<key>` → `main_config` → `BRConfig(Path.cwd())` →
  `_load_config` (deep-merges `.ll/ll.local.md`, `:265-280`) → `ProjectConfig.from_dict` →
  `resolve_variable` → `print` only when non-`None`.
- `[ -z "$CMD" ]` → `exit 3` → `abstain_on_exit_3` (via `fragment: harness_exit`) →
  `evaluate_exit_code` maps `3 → cannot_judge` (`fsm/evaluators.py:243-263`) → `on_cannot_judge`
  → `revert_unverifiable` → `unverifiable` (`dead-code-cleanup`) or `unverifiable` directly
  (`test-coverage-improvement`).
- non-empty `CMD` → `eval "$CMD" 2>&1 | tee <log>` under `set -o pipefail` → `rc=$?` → `exit 0`
  or the collapsed `exit 1` → `on_yes: commit` / `on_no: revert_and_scan` | `fix_tests`.
- **A declared `on_cannot_judge` routes immediately** — verified at `fsm/executor.py:2084`; the
  hold-cap path in `common.yaml`'s `harness_exit` description applies only to an *undeclared*
  `cannot_judge`, so `exit 3` will not re-run either state.

**Precondition — cwd must be the project root.** `main_config` constructs `BRConfig(Path.cwd())`
with no upward walk, so a state invoked from a subdirectory loses the opt-out. Safe for both
converted sites today: FSM shell actions run at `FSMExecutor.working_dir`
(`fsm/executor.py:2482`), the project or worktree root. Not a regression — the inline snippets
open the same relative path — but not fixed here either.

## Impact

- **Behavior change under `test_cmd: null`**: both loops stop gating on a guessed `pytest`, and
  neither can reach `commit` without a real signal. Without the §2b rows applied, the same change
  would commit unverified work — which is the entire reason this issue exists separately.
- **`test-coverage-improvement`'s `context.test_cmd` becomes functional** (pinned decision (a)) —
  today it is declared, documented, and wired to nothing. A user-visible change to a documented
  knob: a loop invocation passing `test_cmd` starts having an effect at `verify_tests` where it
  previously had none.
- **`.ll/ll.local.md` overrides of `test_cmd` start taking effect** inside both loops (they never
  did).
- **`dead-code-cleanup` gains a startup cost and refuses to run in more cases** (entry gate): it
  now runs the test suite once before scanning, and a project with an unresolvable, unrunnable, or
  already-red suite gets a terminal `unverifiable` instead of a scan. The **already-red** case is
  a broader condition than "no `test_cmd` configured" and is the main source of surprise for
  existing users of this loop. Those three conditions are the **whole** widening — the gate
  deliberately does not adopt the template's clean-working-tree check (constraint 0 under
  *DECIDED*), which would additionally refuse every mid-branch run.
- **`dead-code-cleanup`'s `max_steps` rises 15 → 18, its `timeout` rises 5400 → 7200, and its
  `initial` moves to `check_preconditions`.** Neither budget bump is a behavior change users asked
  for; together they keep the loop at three cleanup laps after the entry gate and
  `revert_unverifiable` each claim a step *and* after the gate's baseline suite run is added to
  the wall clock. Raising only `max_steps` would not have achieved that — the wall clock is
  enforced separately (`fsm/executor.py:559-561`) and would have become the binding constraint. A
  run that previously exhausted either budget mid-lap will now get further, and a long-running
  suite that previously fit inside 90 minutes now has 120.
- **`dead-code-cleanup`'s `remove_code` starts writing a removed-files manifest**
  (`${context.run_dir}/ll-dead-code-removed-files.txt`). A new per-run artifact, invisible outside
  the run dir, consumed only by `revert_unverifiable`. It exists because the entry gate
  deliberately does **not** require a clean working tree, which rules out the blanket revert
  `incremental-refactor` relies on: without an explicit list, an unverifiable lap could only be
  undone by discarding the user's own uncommitted work alongside the loop's.
- **`test-coverage-improvement` can now terminate leaving uncommitted new test files.** Under
  `test_cmd: null` the loop reaches `verify_tests`, abstains, and ends at the bare `unverifiable`
  terminal — having already run `measure` and written tests. Nothing reverts them and nothing
  writes an explanation (a terminal state's action never runs). Accepted rather than gated: the
  leftovers are additive and plainly visible in `git status`, and this loop's `on_yes` commits
  added tests rather than deletions, so the "refuse to start" rationale that justifies
  `dead-code-cleanup`'s gate does not transfer. See *DECIDED — `test-coverage-improvement` gets
  no entry gate*.
- **Both `verify_tests` states stop distinguishing a command's exit code beyond pass/fail.** The
  mandated collapse to `exit 1` means a runner exiting 2/3/5 now routes identically to a plain
  test failure. Deliberate — it is what keeps pytest's internal-error code out of
  `on_cannot_judge` — but any future need to route on a specific runner exit code must claim a
  code the state normalizes *before* the collapse.
- **Risk accepted**: both gates join the rest of the family in depending on a single fail-open
  binary (BUG-3269 §1e). At `dead-code-cleanup` the failure mode is safe — a missing `ll-config`
  yields an empty `CMD`, which routes to `unverifiable` rather than to `commit`.
- **Rollback seam**: independent per-file edits; the structural additions are confined to
  `dead-code-cleanup.yaml` and `test-coverage-improvement.yaml` respectively.

## Related Key Documentation

- **ENH-3277** — the parent this splits from; owns the six mechanical conversions, the Option A
  decision and its scoring, and the *CAPTURE CORRECTION*
- **BUG-3269** — the P0 the family splits from; all baseline design analysis (§1, §1b, §1d, §1f,
  §2, §2b)
- **BUG-3276** — `incremental-refactor.yaml`, this issue's live template for both the entry gate
  and the `harness_exit` `verify_tests` shape
- ENH-3281 — the sibling hardcode defect class (`measure`'s surviving `COV_CMD` fallback)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the `ll-config get` convention, written up by
  BUG-3269; its `:569` exemption sentence is this issue's to rewrite (ENH-3277 step 5c retargets
  the issue ID in it first — expect to find `ENH-3288` there, not `ENH-3277`)

## Design Review History

### Pre-implementation review — 2026-08-22 (seventh review; first since ENH-3277 landed)

_Independent design review against the tree, run after ENH-3277 reached `status: done`. **Every
loop-YAML anchor in this issue re-verified and holding** — `dead-code-cleanup`'s `initial: scan`
(`:7`), inline read (`:76`) inside `verify_tests` (`:68-83`) with `fragment: shell_exit` and
`on_yes: commit` / `on_no`+`on_error: revert_and_scan`, `revert_and_scan` (`:84-97`),
`max_steps: 15` (`:108`), `timeout: 5400` (`:109`); `test-coverage-improvement`'s `test_cmd`
declaration (`:23`), dead `CMD` block (`:37-48`), `verify_tests` (`:143-159`) with its inline read
at `:152` and `:157-159` edges; `incremental-refactor`'s gate (`:20-86`, `fragment: shell_exit` at
`:47`) and `verify_tests` (`:99-128`, `harness_exit` at `:109`, `exit 3` at `:120`). The three
mechanism corrections all confirmed against source: `evaluate_exit_code`'s
`abstain_on_exit_3` gate (`fsm/evaluators.py:238-263`), the `harness_exit` fragment
(`lib/common.yaml:23-37`), and the terminal-state short-circuit (`fsm/executor.py:601-636`).
Nine changes applied — the loop YAMLs' anchors were the only thing that had **not** drifted:_

1. **`revert_unverifiable` had no way to know which files to revert** — the sharpest gap found.
   `revert_and_scan` works because the failure log names the file; the no-signal case has neither
   a log nor a single culprit, `remove_code` deletes **three** items across possibly three files
   and declares no `capture:`, and the blanket-revert fallback is ruled out by this issue's own
   (correct) decision to skip the clean-tree check. Added *The removed-files manifest* under
   *Terminality*, an edit to `remove_code`, an AC, an assertion, and a step-3 ordering note.
2. **An existing test pins the old `initial` and will fail.**
   `TestDeadCodeCleanupLoop.test_required_top_level_fields` (`test_builtin_loops.py:12054`)
   asserts `initial == "scan"`; the issue framed the new value as an addition and the *Tests*
   preamble claimed nothing would break. Corrected in the preamble, DECIDED constraint 4, the
   Tests bullet, the AC, and step 3.
3. **Every test-file anchor was stale by 350–650 lines** — ENH-3277 shifted
   `test_builtin_loops.py`. All six corrected inline, with a standing note to grep test *names*
   over trusting line numbers. Five gate-file anchors (`:49`→`:51`, `:55-65`→`:56-63`,
   `:67`→`:65`, `:148-156`→`:146-156`, `:71-84`→`:74-84`) and `revert_and_scan`'s log read
   (`:87`→`:88`) likewise.
4. **The step budget ignored the wall clock.** `dead-code-cleanup` also carries `timeout: 5400`,
   enforced independently of `max_steps` at `fsm/executor.py:559-561`. Since the entry gate adds a
   whole baseline suite run, `max_steps: 18` alone would not have delivered the three laps the
   section promises. Added `timeout: 5400 → 7200` to *Step budget*, *Files to Modify*, the AC,
   Impact, and step 3.
5. **`check_preconditions.on_error` was the one unpinned edge** in an issue that pins every other
   fragment and edge. Pinned to `unverifiable` (DECIDED constraint 3) with an assertion.
6. **Nothing pinned the two back-edges.** Once the gate is `initial:`, retargeting
   `revert_and_scan.next` / `commit.next` from `scan` to the gate is a plausible "cleanup" that
   would re-run the baseline suite every lap. Added DECIDED constraint 5 and assertions.
7. **The pinned body's omission of the template's `RC=$?` normalization was unexplained**, so an
   implementer following "model on these shapes" would paste it back. Documented why it is
   unreachable — `main_config` returns 0 unconditionally (`cli/config.py:53`).
8. **`test-coverage-improvement`'s lack of an entry gate was silent, not decided.** Recorded as a
   decision with its accepted cost (a wasted `measure` + `write_tests`, and new test files left
   uncommitted at termination), plus an Impact bullet.
9. **The "cannot reach `commit` without a real test signal" claim was literally false** for
   `test-coverage-improvement`: `extract_percentage` routes `target: commit` (`:85-86`). Narrowed
   to "via `verify_tests`" and the pre-existing bypass recorded in *Scope Boundaries*.

_No change to the two conversions themselves, the fragment switches, the exit-collapse
requirement, the four new states, or the teardown steps. Net additions: one prompt edit
(`remove_code`), one scalar (`timeout`), two pinned edges, and six assertions._

### Pre-implementation review — 2026-08-22 (sixth review of the ENH-3277 family)

_Independent design review against the tree, run jointly with ENH-3277. Re-verified and holding:
`dead-code-cleanup`'s `initial: scan` (`:7`), `max_steps: 15` (`:108`), the inline read at `:76`
and its `:71-81` block, `verify_tests`'s `shell_exit` fragment and `on_yes: commit` /
`on_no`+`on_error: revert_and_scan` edges; `test-coverage-improvement`'s dead `CMD` block at
`:37-48` (with `${context.test_cmd}` referenced **nowhere else** in the file, so deleting it leaves
the `:23` declaration inert until `verify_tests` picks it up) and `verify_tests`'s
`:157-159` edges; `incremental-refactor`'s template at `:20-86` / `:99-128` with
`fragment: shell_exit` at `:47` and `harness_exit` at `:109`; the `harness_exit` fragment's
`abstain_on_exit_3: true` (`lib/common.yaml:23-37`); and step 7's pre-verification — the widened
`project`-bound access shape was re-run directly against `loops/**` and matches
`auto-refine-and-implement.yaml` (`:433`, `:434`) and nothing else, so no new exemption is needed.
Two corrections applied:_

1. **The `check_preconditions` entry gate was scoped only by what it must *not* paste
   (context-first), not by what it must *check*.** "Modelled on `incremental-refactor.yaml:20-86`"
   silently imports that template's **clean-working-tree** gate, whose rationale is that loop's
   blanket `git checkout -- . && git clean -fd` revert. `dead-code-cleanup` reverts per file
   (`:83-97`), so the rationale does not transfer, and a wholesale copy would make the loop refuse
   to start on any dirty tree — much broader than the widening *Impact* describes. Added
   constraints 0 (three-of-four checks, no clean-tree) and 0b (`fragment: shell_exit`, pinned like
   every other fragment in this issue), with matching AC, Impact, and step-3 updates.
2. **Stale `verify_tests` anchor for `test-coverage-improvement`, in four places.** The state is
   `:143-159` with the inline read at `:152`; `:148-158` was carried across the split even though
   ENH-3277's *Anchors spot-checked in the first addendum* had already corrected it. Fixed in the
   §2b row, *Dead site* consequence 2, *Files to Modify*, and the AC.

_No change to scope, state count, the pinned bodies, the exit-collapse requirement, or the
teardown steps._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~Blocked by ENH-3277 (status: open)~~ — **RESOLVED 2026-08-22.** ENH-3277 is `status: done`
  and its shrink is live: `test_bug3269_test_cmd_resolution_gate.py:56-63` now holds exactly the
  four entries this issue expects (`dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`,
  `rn-refine.yaml`, `auto-refine-and-implement.yaml`), and
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569` already reads "pending ENH-3288's conversion
  pass" per its step 5c retarget. The Dependencies Hard Override no longer applies; the readiness
  score should be re-run.
- Nine further gaps were found and closed by the seventh review (2026-08-22) — see *Design Review
  History*. The readiness score above predates all of them.
- Criterion 4 capped at 10/20 by `format-check`'s `stale_cli_flag` gap:
  `"ll-config get --raw (no such flag)"` — likely a false-positive read of this issue's own
  explicitly-rejected Option C ("Do **not** build `ll-config get --raw`"), but recorded per
  protocol since the CLI is the single source of truth for this signal.

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-21T23:00:39 - `02e1c33a-8ca1-415d-9b72-205f956514ca.jsonl`
