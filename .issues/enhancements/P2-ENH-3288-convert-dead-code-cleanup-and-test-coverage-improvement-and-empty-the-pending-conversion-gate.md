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
`.ll/ll.local.md`. Neither can reach `commit` without a real test signal. A no-signal skip is
routed and reported distinctly from a test failure. `_PENDING_CONVERSION` is empty and the
constant is deleted, leaving exactly three permanent exemptions.

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
| `test-coverage-improvement.yaml:148-158` (`verify_tests`) | `commit` | **explicit skip required** — target pinned under *Pinning the two explicit-skip gate edges* below; its `on_no`/`on_error: fix_tests` is reachable but wrong |
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
   Move it to `verify_tests` (`:148-158`), per decision (a) below, now pinned.
3. **`test-coverage-improvement`'s `context.test_cmd` parameter is currently inert** — a latent
   bug this issue surfaces. It is declared at `:23` with the comment *"override test command;
   empty = read from ll-config.json"* and documented as a supported knob in
   `docs/guides/LOOPS_REFERENCE.md:1347` (*"Test command to run (e.g. `python -m pytest --cov`)"*),
   but its **only consumer is the dead block**. `verify_tests:148-158` — the state that actually
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
(`dead-code-cleanup.yaml:87`) and `fix_tests` reads `ll-coverage-tests.txt`. Combining
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
  that reverts the current removal (`git checkout -- <file>`) and writes the reason — *no test
  command resolved; nothing was verifiable* — to `${context.run_dir}/ll-dead-code-unverifiable.txt`,
  with **`next: unverifiable`**. Model its body on `revert_and_scan` (`:83-97`) but with the
  no-signal framing rather than "tests failed", and **`next: unverifiable`, never `next: scan`** —
  a `next: scan` re-scans, re-deletes, and re-reaches an ungated `verify_tests` for the remainder
  of `max_steps: 15`, deleting code on every lap with no verification at any of them.
  `unverifiable` itself is a **bare** `terminal: true` + `failure: true` marker with no action and
  no `next:`, matching `failed`'s existing shape.
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

#### DECIDED (2026-08-21) — `dead-code-cleanup` gets a `check_preconditions` entry gate, config-first bare

**Pinned in scope.** This was the last item in this issue left as a "Recommendation," which meant
an implementer could reasonably ship either shape — and the two differ in scope, state count,
tests, and step budget. It is now **in scope and required**, alongside the mid-run
`harness_exit` skip edge (both, not either — same rationale
`incremental-refactor.yaml:100-108` gives for keeping both). Three constraints, each verified:

1. **Config-first bare — do NOT paste `incremental-refactor.yaml:20-86` verbatim.** That
   template resolves context-first via `${context.test_cmd}`, but `dead-code-cleanup`'s
   `context:` block (`:13-14`) declares **only** `commit_message`. An undeclared
   `${context.test_cmd}` raises `InterpolationError: Path 'test_cmd' not found in context` at
   interpolation time *and* fails the gate's assertion (ii),
   `test_context_references_are_declared`. Use `CMD=$(ll-config get project.test_cmd)` — the
   general warning under *Proposed Solution* > *Precedence* applies here too, and this is the site
   most likely to be
   written by copying.
2. **Budget.** `dead-code-cleanup` is `max_steps: 15`; the entry gate consumes one and runs the
   suite once at loop start, adding roughly one test-suite duration to every run. See
   *Step budget* below — this issue raises `max_steps` to `18`.
3. **Routing.** `exit 1` → `on_no: unverifiable`, the bare terminal-failure state (not `failed`,
   per *State names* above, and **not** `revert_unverifiable` — nothing has been deleted yet at
   loop start, and the gate's own shell action already wrote `precondition-failure.txt` before
   exiting 1), per the `incremental-refactor` precedent. `exit 0` → **`on_yes: scan`**, the
   loop's previous `initial:` — the success edge must re-enter the original pipeline, and no
   existing assertion pins it. It needs its own assertion —
   `test_required_states_exist` (L11688) is a subset check and will pass without it.
4. **`initial:` must move — easily missed, and the gate is dead YAML without it.**
   `dead-code-cleanup.yaml:7` is `initial: scan` today. Change it to
   `initial: check_preconditions`, matching `incremental-refactor.yaml:4`. An entry state that is
   not the FSM's `initial` is never entered — `scan` still runs first and the gate never fires,
   while every structural assertion (state-set membership, edge shape) passes. Assert
   `fsm.initial == "check_preconditions"` explicitly.

#### Step budget — `dead-code-cleanup` goes to `max_steps: 18`

`dead-code-cleanup` is `max_steps: 15` against a five-state lap (`scan` → `count_findings` →
`remove_code` → `verify_tests` → `commit` → `scan`), i.e. three full laps today.
This issue adds two steps to the *success* path budget — the `check_preconditions` entry gate
(one, once at loop start) — and one more on the *skip* path (`revert_unverifiable`). Left at 15,
the loop drops to two full laps plus a partial, a silent reduction in cleanup throughput that has
nothing to do with the resolution refactor.

Raise `max_steps` to **18** in the same edit. The comparable sibling, `incremental-refactor`,
carries its entry gate out of `max_steps: 30` (`:7`). Assert the new value so it is not
absent-mindedly reverted along with the gate.

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
template violates. Text kept here as rationale._

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
needs its own assertion — `TestDeadCodeCleanupLoop.test_required_states_exist` (L11688) is a
subset check and will pass without it (see *Tests*). Also see *Consider an entry precondition*
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
carries the same
subset-check caveat: `TestTestCoverageImprovementLoop.test_required_states_exist` (L11722) will
pass without validating it.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/dead-code-cleanup.yaml` — the inline read at `:76`, plus four edits
  outside it: **`:7` `initial: scan` → `initial: check_preconditions`** (without it the new entry
  gate is never entered), **`:108` `max_steps: 15` → `18`** (*Step budget*), the new
  `check_preconditions` entry gate, and the two new states `revert_unverifiable` /
  `unverifiable` (*Terminality*)
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — `:37-48` (the dead `CMD` block in
  `measure`) **deleted, not converted**; `:148-158` (`verify_tests`) converted context-first and
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
- `scripts/little_loops/fsm/runners.py:297` — `cmd = ["bash", "-c", action]`; the reason
  `set -o pipefail` is valid in these bodies and must stay `bash`
- `scripts/little_loops/loops/lib/common.yaml:15-22` (`shell_exit`) and `:23-37`
  (`harness_exit`, which supplies `abstain_on_exit_3: true`)

### Tests

_No existing test in `scripts/tests/` executes the shell body of either site at the
value-resolution level — every current test is structural only (state-set membership, `fragment:`
field, routing-edge shape). None will break from the conversion; none gives coverage either._

- **Subprocess resolution tests for both `verify_tests` states**, driven through **`bash -c`**,
  asserting all three config cases (set / present-null / absent). Model on
  `TestRlCodingAgentObserveTestCmdResolution` (`test_builtin_loops.py:10747-10799`). Add a fourth
  case at `test-coverage-improvement.verify_tests` only — context wins over `ll-config get`, per
  `TestIncrementalRefactorLoop.test_verify_tests_resolves_context_first_then_ll_config` (L11983).
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
  `TestIncrementalRefactorLoop.test_revert_has_exactly_one_inbound_edge` shape, `:11999-12006`).
  `TestDeadCodeCleanupLoop.test_required_states_exist` (L11688) and
  `TestTestCoverageImprovementLoop.test_required_states_exist` (L11722) are **subset** checks and
  will silently pass without any of this.
- **Assert neither `unverifiable` state carries an action**, and that `revert_unverifiable` is
  non-terminal with `next: unverifiable`. This is the executable form of the *TERMINAL-ACTION
  CORRECTION*: an `action` on a terminal state is silently dead, so nothing else in the suite
  would catch someone "simplifying" the two states back into one.
- **Assert `dead-code-cleanup`'s `initial == "check_preconditions"` and `max_steps == 18`.** Both
  are one-line scalars a future edit can revert without breaking any state-set or edge-shape
  assertion, and either reversion silently disables the entry gate or silently cuts a cleanup
  lap. Also assert `check_preconditions.on_yes == "scan"` — the success edge is equally a
  one-line scalar with nothing else holding it in place.
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
- [ ] `verify_tests` (`:148-158`) uses the context-first shape, so the `:23` `test_cmd`
      declaration becomes live
- [ ] `verify_tests` is `fragment: harness_exit` with a declared `on_cannot_judge: unverifiable`
- [ ] `unverifiable` exists as a **bare** `terminal: true` + `failure: true` state — no `action`,
      no `next:`

**`dead-code-cleanup.yaml`**

- [ ] `:76` converted, **config-first bare** (not context-first — `InterpolationError`)
- [ ] `verify_tests` is `fragment: harness_exit` with `on_cannot_judge: revert_unverifiable`
- [ ] `revert_unverifiable` exists as `action_type: prompt` with `next: unverifiable`, and is
      `verify_tests.on_cannot_judge`'s only target
- [ ] `unverifiable` exists as a bare `terminal: true` + `failure: true` state
- [ ] `check_preconditions` entry gate exists (config-first bare), routing `on_yes: scan` and
      `on_no: unverifiable`
- [ ] `:7` is `initial: check_preconditions`
- [ ] `:108` is `max_steps: 18`

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

**Tests** (each is new; none exists today)

- [ ] Subprocess resolution tests for both states, driven through `bash -c`, all three config
      cases (plus the context-first fourth case at `test-coverage-improvement`)
- [ ] Exit-3 collision case at both states: `sh -c 'exit 3'` → state exits **1**; empty `CMD` →
      exits **3**
- [ ] Dedicated assertions for all four new/changed states, plus `initial`, `max_steps`, and
      `abstain_on_exit_3`/`harness_exit` at both states
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
   `fragment: harness_exit` with `on_cannot_judge: revert_unverifiable`; add
   `revert_unverifiable` (prompt, `next: unverifiable`) and the bare `unverifiable` terminal; add
   the `check_preconditions` entry gate (**config-first bare**, `on_no: unverifiable`); move
   `initial` to `check_preconditions`; raise `max_steps` to `18`. Land its regression tests in the
   same change.
4. **Verify each loop before moving on:** `ll-loop validate`, the scoped grep, and the gate with
   that file's entry removed from `_PENDING_CONVERSION`.
5. **Execute ENH-3277's Option A decision.** Move `rn-refine.yaml` and
   `auto-refine-and-implement.yaml` from `_PENDING_CONVERSION` into `_PERMANENT_EXEMPTIONS`
   (`:49`), growing it from one entry to three, and extend that constant's comment to carry the
   §1d rationale (absent ≡ null ≡ skip, never guess) for all three. Both YAMLs stay byte-for-byte
   unchanged. Do **not** build `ll-config get --raw`.
6. **Empty `_PENDING_CONVERSION` and delete the constant.** Four coupled edits in
   `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`, not one — deleting the constant alone
   is a `NameError`:
   - grow `_PERMANENT_EXEMPTIONS` (`:49`) to three per step 5 — **this must land before the set
     below is deleted**, or the gate fails on those two files;
   - delete the `_PENDING_CONVERSION` set (`:55-65`);
   - delete `test_pending_conversion_sites_still_exist` (`:148-156`), which dereferences it;
   - collapse `_EXEMPT = _PERMANENT_EXEMPTIONS | _PENDING_CONVERSION` (`:67`) to
     `_EXEMPT = _PERMANENT_EXEMPTIONS`.

   Plus the doc edit: **`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569`**'s "temporary exemption
   pending **ENH-3288's** conversion pass" sentence must be rewritten to name the three permanent
   exemptions. Deleting the constant without it leaves the guide advertising closed issues as
   pending work forever. (The line named *ENH-3277* until that issue's step 5c retargeted it —
   see *Documentation*. Grep for `ENH-3288`, not `ENH-3277`.)

   Leave `test_no_inline_project_command_config_read`, `test_context_references_are_declared`, and
   `test_general_task_and_rl_coding_agent_are_not_exempt` in place. The inline-read assertion then
   holds with exactly three permanent exemptions. **This is the definition of done for the whole
   ENH-3277 family.**

7. **Widen `_INLINE_ACCESS_RE` (`:71-84`) — a verified blind spot.** The regex matches only a
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
`check_preconditions`), `dead-code-cleanup`'s `initial:` and `max_steps:` edits — plus the full
gate teardown (moving two entries to `_PERMANENT_EXEMPTIONS`, deleting `_PENDING_CONVERSION`,
widening `_INLINE_ACCESS_RE`) and the exemption-list doc edits.

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
  existing users of this loop.
- **`dead-code-cleanup`'s `max_steps` rises 15 → 18 and its `initial` moves to
  `check_preconditions`.** The step bump is not a behavior change users asked for; it keeps the
  loop at three cleanup laps after the entry gate and `revert_unverifiable` each claim a step. A
  run that previously exhausted its budget mid-lap will now get slightly further.
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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- Blocked by ENH-3277 (status: open) — this issue's own Prerequisite step already says ENH-3277
  must land first; the Dependencies Hard Override forces STOP regardless of aggregate score until
  it resolves.
- Criterion 4 capped at 10/20 by `format-check`'s `stale_cli_flag` gap:
  `"ll-config get --raw (no such flag)"` — likely a false-positive read of this issue's own
  explicitly-rejected Option C ("Do **not** build `ll-config get --raw`"), but recorded per
  protocol since the CLI is the single source of truth for this signal.

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-21T23:00:39 - `02e1c33a-8ca1-415d-9b72-205f956514ca.jsonl`
