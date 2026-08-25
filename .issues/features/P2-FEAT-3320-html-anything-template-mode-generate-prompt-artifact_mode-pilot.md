---
id: FEAT-3320
type: FEAT
title: html-anything template-mode generate prompt (artifact_mode pilot)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:25:58Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- fsm
- templates
- prompt
depends_on:
- FEAT-3318
relates_to:
- FEAT-3036
learning_tests_required:
- playwright
- jinja2
confidence_score: 96
outcome_confidence: 78
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-3320: html-anything template-mode generate prompt (artifact_mode pilot)

## Summary

Split out of FEAT-3318 at the 2026-08-25 pre-implementation review. FEAT-3318 lands
the `artifact_mode: template` plumbing — the schema field, the static and runtime
gates, atomic directory promotion, and a round-trip test against a hand-written
`.llat/` fixture. None of that requires an LLM to produce a template.

This issue is the other half: teach `html-anything` to actually *generate* a
`manifest.yaml` + `template.*.j2` + `data.json` triple instead of a fused
`index.html`, selected per-run via `--context artifact_mode=template`. It is the
pilot that proves the epic's design principle 1 ("loops emit template + data
natively") works in practice, and the precondition for rolling the variant out to
the remaining eight HTML-family loops.

## Current Behavior

- `html-anything.yaml:117-186` delegates to `oracles/generator-evaluator` via a
  `loop:` thin wrapper, passing a `generate_prompt` that instructs the model to
  "Write a single self-contained HTML file to `${captured.run_dir.output}/index.html`"
  (`:133`). There is one prompt and one output shape.
- The oracle's evaluate cycle is built around that single file: a Playwright
  screenshot of `file://.../${context.artifact_path}` (`generator-evaluator.yaml:82`,
  `artifact_path` defaulting to `index.html` at `:52`), then an LLM rubric score
  over `screenshot.png` (`html-anything.yaml:151-155`).
- With FEAT-3318 landed, a loop *can* declare `artifact_mode: template` and have a
  `.llat/` directory promoted and validated — but no built-in loop produces one.
  Every route from a loop to a template still runs through `ll-artifact templatize`
  (FEAT-3308), the lossy LLM-extraction path.

## Expected Behavior

`ll-loop run html-anything --context artifact_mode=template` produces a validated
`.llat/` directory that `ll-artifact render` consumes by name, with the same
iterate-until-`ALL_PASS` quality cycle the `file` mode gets today. The default
(`file`) path is byte-for-byte unchanged.

## Motivation

FEAT-3318's plumbing is inert without a producer. It is also unproven: the whole
reason this was split out is that "an LLM reliably emits a schema-valid
manifest + Jinja2 body + conforming data.json, repeatedly, under critique
iteration" is an empirical claim, not a mechanical one. Proving it on one loop
before rewriting nine prompts is the cheap ordering.

## Proposed Solution

### The evaluate cycle is the hard part, not the generate prompt

The generate prompt rewrite is mostly mechanical. The problem is that a `.llat/`
directory has nothing to screenshot, and the oracle's entire quality loop —
screenshot, rubric score, critique, iterate — is downstream of a renderable HTML
file at a fixed path.

Proposed: **render the template to HTML on each iteration, then screenshot the
render.** The oracle already parameterizes the screenshot target
(`artifact_path`, `generator-evaluator.yaml:43,52`), so the wrapper passes a
rendered path rather than the template directory. This keeps the entire
evaluate/score/critique cycle unchanged and untouched — the template becomes an
extra upstream step, not a fork of the oracle.

**Decided (2026-08-25 pre-implementation review) — the render is a
`pre_evaluate_cmd` oracle parameter, prepended to `evaluate`'s existing shell
action.** This closes what was previously left as an open question, and it
resolves a contradiction the issue carried: Acceptance Criterion 3 forbids
forking or branching `oracles/generator-evaluator.yaml`, while § Program Design's
research below proposed **a new `render` state inside that oracle**, between
`generate` and `evaluate`. A new state is an edit to the shared oracle: all nine
consumers inherit it, and at `max_steps: 40` over a ~9-state cycle it silently
costs every consumer roughly half an iteration of budget.

The three options considered:

- **(a) Prepend to `evaluate`'s action — chosen.** Add an optional
  `pre_evaluate_cmd` parameter to the oracle (`parameters:` +
  `context: {pre_evaluate_cmd: ""}`), interpolated at the top of `evaluate`'s
  existing shell action (`generator-evaluator.yaml:78-82`). Zero new states, zero
  `max_steps` impact, and the parameter is generic — it is not a branch on
  artifact mode, so AC 3 holds in letter and spirit. All eight other consumers
  leave it unset and their behavior is byte-identical.

  **Caveat on `evaluate`'s routing — the prepended command's stdout must be
  quieted.** `evaluate` inherits `fragment: playwright_screenshot`, whose
  `evaluate:` block is `type: output_contains, pattern: "CAPTURED"`
  (`lib/harness.yaml:12-14`) — routing is **text-matched on stdout, not on exit
  code**. An earlier revision of this bullet said the render's stdout "lands in
  `evaluate`'s own output, which the failure-message work uses"; that is true but
  incomplete, and the phrasing understated the risk. Today the mismatch is
  harmless (all three of `on_yes`/`on_no`/`on_error` route to `snapshot`,
  `:83-85`), but any future routing change on this state would silently depend on
  render chatter. Redirect the render's stdout (`>/dev/null`) so it can never
  perturb the `CAPTURED` match; keep stderr, which is what the render-failure
  message (step 6) needs.
- **(b) A new optional-no-op `render` state.** Honest, but pays the `max_steps`
  tax for every consumer; would require bumping `max_steps` and re-checking
  ENH-2903's cap arithmetic against the longer cycle.
- **(c) The generate prompt instructs the model to run `ll-artifact render`
  itself.** Rejected: a deterministic step is cheaper and cannot be skipped by a
  model that decides it is done early.

Consequence worth checking against ENH-2903: a render failure produces no HTML,
which produces no screenshot, which the oracle already models as a
screenshot-miss with a consecutive-miss abandon gate
(`generator-evaluator.yaml:89-143`). A malformed template may therefore surface
as a screenshot-miss rather than as a template error — the abandon path should
report the render failure, not a generic missing-screenshot message.

### Mode selection

Per FEAT-3318's § Mode selection: `artifact_mode` is a `context:` var on
`html-anything` (alongside `pass_threshold` / `design_tokens_context`), read by
`promote_run_artifact` with the top-level field as the default. Selection uses
the existing `ll-loop run --context artifact_mode=template`
(`cli/loop/__init__.py:294`) — no new CLI flag.

The generate prompt branches by interpolating that var. FSM prompts are static
text, so this is a conditional block in the prompt body, not two prompts.

**`html-anything.yaml` has no `artifact_output` block today** — `hitl-md.yaml` is
the only loop that declares one. FEAT-3318's static gate requires one whenever
the effective mode is `template`, so this issue must add it.

**Resolved: declare `from: artifact.llat`, and the file-mode path stays quiet by
itself.** The earlier concern here — that a mode-independent `artifact_output`
block would make *every* run, including default `file`-mode runs, start promoting
`index.html` into `promotion_dir` — does not materialize.
`promote_run_artifact` returns `None` when `run_dir / spec.from` does not exist
(`fsm/persistence.py:757-763`, before any mode dispatch). `artifact.llat` is only
written in template mode, so a `file`-mode run finds no source and skips
promotion silently. No `on:` allowlist is needed and no sign-off on a
default-path behavior change is needed — the default path genuinely does not
change. AC 2's second clause should be read as satisfied by this mechanism, and
the file-mode regression test should pin it (a `file`-mode run promotes nothing).

Note the corollary: `spec.from` is a single static path, so it cannot name both
`index.html` (file mode) and a `.llat/` directory (template mode). Naming the
directory is what makes the mode-independence harmless; naming `index.html`
instead would both promote on every file-mode run *and* fail template-mode
promotion, since `_promote_template_artifact` requires `from` to resolve to a
directory (`persistence.py:828-836`).

### The generate prompt must mandate `output: index.html`

_Added at the 2026-08-25 pre-implementation review._

§ Program Design's research notes the problem twice without resolving it: the
rendered filename is manifest-controlled (`render_to_disk` writes to
`output_dir / manifest["output"]`, `render.py:36-69`), while the oracle's
`artifact_path` is bound once at invocation time and never re-read from a
captured value. A model-authored manifest therefore picks a filename the wrapper
cannot know in advance.

Fixing the filename in the prompt resolves this completely. The template-mode
branch mandates `output: index.html` in `manifest.yaml`; the render runs with
`-o <run_dir>`; `artifact_path` then keeps the oracle's own default
(`"index.html"`, `generator-evaluator.yaml:52`).

Three consequences that shrink this issue's scope:

- **No `artifact_path` key is added to the `with:` block.** The § Signatures
  claim that this issue "adds `artifact_path` as a new key in that binding", and
  the § Files to Modify mention of it, are both withdrawn — `with:` is unchanged
  except for `pre_evaluate_cmd`.
- The `rubric` prompt's existing *fallback* — "Otherwise read
  `${captured.run_dir.output}/index.html` directly" (`html-anything.yaml:157-158`)
  — keeps working in template mode without a branch, because the mandated
  `output: index.html` puts the rendered file exactly where the fallback looks.
  **This does not mean the `rubric` prompt needs no branch at all** — see
  § The `rubric` prompt needs its own template-mode branch below. The fallback is
  fine; the criterion set is not.
- `snapshot`'s per-iteration `cp "$RUN_DIR/${context.artifact_path}"`
  (`generator-evaluator.yaml:106`) still copies a single file. `iter-N/` therefore
  archives the *rendered* HTML, not the `.llat/` source. That is the right signal
  for the score-plateau and diff-stall guards, which reason about what was scored
  — but it is **not** harmless the way an earlier revision of this bullet
  ("accept knowingly") claimed. See § `iter-N/` loses the template, which breaks
  best-iteration recovery.

### `iter-N/` loses the template, which breaks best-iteration recovery

_Added at the second pre-implementation review — corrects the "accept knowingly"
disposition above._

In `file` mode, "the artifact that gets promoted" and "the artifact the operator
is told was best" can diverge in *score* but never in *identity*: `index.html` is
both the live artifact and the thing archived under `iter-N/`, so an operator told
"iter-3 scored highest" can simply copy `iter-3/index.html` and have the real
thing. Template mode breaks that equivalence.

Two facts combine:

1. `max_steps_summary` (`generator-evaluator.yaml:315-335`) explicitly instructs
   the model to "identify the highest-scoring iteration from the score history and
   name it explicitly, along with its score" — pointing the operator at `iter-N/`.
2. `iter-N/` in template mode contains only the rendered HTML for iteration N. The
   `.llat/` that produced it was overwritten in place by iteration N+1's
   `generate`.

So a run that plateaus or exhausts `max_steps` promotes the **last** template,
tells the operator the **best** iteration was some earlier N, and leaves no way to
recover the template behind N. The operator's only recourse would be
`ll-artifact templatize` on the archived HTML — the exact lossy path this issue
exists to avoid.

**Decide one of two, and do it explicitly:**

- **(a) Archive the source too — preferred.** `pre_evaluate_cmd` reads
  `.iter_counter` the same way `snapshot` does and copies the template alongside:
  `cp -R <abs run_dir>/artifact.llat <abs run_dir>/iter-$N/` . Note the ordering
  hazard: `snapshot` *increments* `.iter_counter` and creates `iter-$COUNTER/`
  itself (`generator-evaluator.yaml:97-101`), and `pre_evaluate_cmd` runs
  **before** `snapshot` in the same cycle, so the counter it reads is
  `N-1`. Either `mkdir -p` the `N+1` directory from `pre_evaluate_cmd` (fragile —
  it duplicates the oracle's counter arithmetic) or, more robustly, copy the
  `.llat/` into a flat `<run_dir>/llat-history/<timestamp-or-hash>/` and have
  `finalize_done` explain the mapping. Do not add a state or a second parameter to
  the oracle to solve this — AC 3 permits exactly two oracle edits.
- **(b) Document the limitation.** `finalize_done`'s template-mode branch states
  that only the final `.llat/` survives and that `iter-N/` archives renders only,
  so best-iteration recovery is unavailable in template mode.

(a) is preferred because the pilot's whole purpose is comparing template outputs
across iterations; (b) is acceptable if (a)'s counter coupling proves ugly in
practice. What is *not* acceptable is shipping the current silent divergence.

### The prompt must also state four contract details that are currently omitted

_Added at the 2026-08-25 pre-implementation review. Retitled from "three" at the
second pre-implementation review — the `assets/` bullet is new._

§ Program Design's `.llat/` contract summary is otherwise accurate, but each of
these omissions produces a hard render failure:

- **`ll.theme_css` exists only when `manifest.yaml` declares `theme:
  design-tokens`** (`build_ll_namespace`, `artifact_templates.py:311-318`).
  `theme` is not one of the required manifest keys, so it is absent from the
  contract summary below. Under `StrictUndefined`, a body referencing
  `[[= ll.theme_css =]]` without it raises at render time. The template-mode
  branch must therefore instruct the model to declare `theme: design-tokens` and
  reference `ll.theme_css`, **not** to inline the resolved token values. Inlining
  them freezes today's theme into the promoted template and destroys the
  render-it-again-next-month benefit that is this issue's own § Use Case.

  **Declare `theme: design-tokens` unconditionally — do not gate it on
  `design_tokens_context`.** _(Corrected at the second pre-implementation review;
  supersedes the earlier "when `design_tokens_context` is non-empty" phrasing
  here, in Implementation Step 3, and in the Acceptance Criteria.)_
  `themed_css_vars(config)` (`artifact_template_kit.py:18-42`) already degrades
  gracefully: when no tokens are configured for the project it returns neutral
  empty scoped blocks (`":root {\n}\n[data-theme=dark] {\n}"`) rather than raising
  or emitting garbage. Gating the declaration on a runner-injected context var
  therefore buys nothing and costs a nested conditional inside the single most
  conditional prompt string in the file. Always declare it; instruct the model to
  supply concrete CSS fallbacks alongside every `var(--…)` reference so the
  no-tokens render still looks right.
- **`assets/` is read as UTF-8 text, so a binary file there is a hard failure**
  (`load_assets`, `artifact_templates.py:296-308` — `path.read_text(encoding="utf-8")`
  over `assets_dir.rglob("*")`, every file, unconditionally). _(Added at the second
  pre-implementation review.)_ This is the second-most-likely first-try failure
  after the delimiters, and it is specific to *this* loop: a model asked for a
  poster, social card, or résumé will very plausibly write `assets/logo.png`. The
  resulting `UnicodeDecodeError` fires inside `build_ll_namespace`, which means it
  breaks **both** `pre_evaluate_cmd`'s per-iteration render *and* FEAT-3318's
  promotion runtime gate — and it is not a `ManifestError`/`DataValidationError`,
  so in the promotion path it lands in `_promote_template_artifact`'s generic
  `except Exception` degrade-to-warning branch (`persistence.py:802-897`) and the
  promotion silently does not happen. The prompt must state: images are inline
  `<svg>` or `data:` URIs embedded in the template body; if an `assets/` directory
  is created at all it holds UTF-8 text only (`.css`, `.svg`, `.js`, `.txt`).
  Note that `ll.assets` is a plain dict keyed by relative POSIX path and is `{}`
  when no `assets/` dir exists, so under `StrictUndefined` any
  `[[= ll.assets['x'] =]]` for a file the model did not write also fails — the
  simplest correct instruction is to not use `assets/` at all for this loop.
- **`ll-artifact render` resolves a relative `--data` and `-o` against
  `config.project_root`, not the process cwd** (`render.py:96-97`,
  `render_to_disk` `:58-60`). `run_dir` is captured absolute at `init`
  (`html-anything.yaml:31-44`), so the render invocation must pass absolute
  paths.
- The generate prompt must state the non-default Jinja delimiters
  (`[[= =]]` / `[[% %]]` / `[[# #]]`) explicitly — already captured in the
  contract notes below, repeated here because it is the single most likely way a
  first-try template fails.

### Nothing currently forces a *meaningful* template/data split

_Added at the 2026-08-25 pre-implementation review — scope gap._

Every acceptance criterion as originally written is satisfiable by a template
with all content hardcoded in `template.html.j2` and a `data.json` of `{}`. That
shape is schema-valid, renders, screenshots, and scores 10/10 against the current
rubric — while delivering none of the epic's value. There is no criterion
anywhere, in the rubric or in the runtime gate, for parameterization.

This is the pilot's real failure mode, and measuring "schema-valid emission
rate" (step 7) without it would report a success number that means nothing.

Fix, in two layers:

- **Rubric layer.** The `plan` state's rubric-writing prompt
  (`html-anything.yaml:46-114`) needs a template-mode branch that adds a
  `data_parameterization` criterion: every piece of run-specific content
  (headings, copy, figures, table rows, links) reaches the template through
  `data.json`, and `data_schema` describes it. This makes a hardcoded template
  score badly and get critiqued and regenerated — the existing iterate cycle then
  does the work. **`plan` was not in § Files to Modify; it now is.**
- **Deterministic backstop, at the terminal — *not* inside `pre_evaluate_cmd`.**
  A shell assertion that `data.json` has at least a few top-level keys and that
  the template body references them, so a degenerate `{}` never reaches
  promotion regardless of what the rubric scored. **Placement corrected below** —
  the earlier "after render (or inside `pre_evaluate_cmd`)" phrasing is
  withdrawn; see § The backstop must not live inside the iterate cycle.

### The backstop must not live inside the iterate cycle

_Added at the 2026-08-25 pre-implementation review — corrects the placement
suggested in the bullet above._

If the degenerate-`data.json` assertion runs inside `pre_evaluate_cmd` and exits
nonzero, the render is skipped (or its output is stale), so `evaluate` captures
no fresh screenshot, `snapshot` records a miss (`generator-evaluator.yaml:97-130`),
and three consecutive misses hit `check_screenshot_abandon`'s hardcoded cap
(`:156-179`) and terminate the run at `screenshot_abandoned`. That is *abandoning*
the run, which directly contradicts this issue's own acceptance criterion that "a
low-scoring template is critiqued and regenerated, not abandoned." It also wastes
the critique loop: a shell exit code produces no `critique.md` entry, so the model
is never told what was wrong.

The two layers therefore live in two different places, and the split is the point:

- **Iterating layer = the rubric.** The `data_parameterization` criterion is the
  only mechanism that can turn "this template is hardcoded" into a `critique.md`
  line the next `generate` pass reads and fixes. All in-cycle enforcement goes
  here.
- **Gating layer = the terminal.** The deterministic assertion runs once, in
  `finalize_done` (or a shell state immediately before it), as a hard gate on
  promotion — after the iterate cycle has already had every chance to fix the
  problem. A failure here routes to `failed`/`diagnose` with an explicit message,
  rather than being laundered as a screenshot miss.

`pre_evaluate_cmd` stays a pure render step. Its only non-render responsibilities
are the `.miss_reason` side-channel of step 6 and the stale-render deletion of
§ A failed render is invisible after iteration 1.

**The gate is a new shell state, not `finalize_done`.** `finalize_done` is
`action_type: prompt` (`html-anything.yaml:189`) — a prompt state cannot host a
deterministic shell assertion, and asking the model to perform the check
reintroduces exactly the skippability that option (c) was rejected for. Add a new
`gate_template` shell state between `run_gen_eval`'s `on_yes` and `finalize_done`
(`html-anything`'s `max_steps: 20` has room for one more state on the non-looping
tail). Wording elsewhere in this issue that puts the gate "in `finalize_done`" is
superseded by this paragraph.

**Why `on_yes` is the right edge to intercept — a `max_steps` exhaustion arrives
there too.** _(Added at the second pre-implementation review — this is the
load-bearing reason for the placement, and it was unstated.)_ The intuitive
reading is that `run_gen_eval`'s `on_yes` means "ALL_PASS" and that a run which
burns its budget goes to `on_no: diagnose`. It does not. The oracle declares
`on_max_steps: max_steps_summary` (`generator-evaluator.yaml:19-20`), and
`max_steps_summary` is `terminal: true` **without** `failure: true`
(`:315-335`). Sub-loop dispatch (`fsm/executor.py:1087-1092`) routes on
`terminated_by == "terminal"` plus the child's explicit `failure_terminal` flag —
so a budget-exhausted oracle run is a **non-failure terminal** and takes the
parent's `on_yes`. The same is true of both plateau exits (`check_stall` `on_no:
done`, `check_diff_stall` `on_no: done`, `:246-279`). Only `failed` and
`screenshot_abandoned` (which does declare `failure: true`) take `on_no`/`on_error`
into `diagnose`.

Consequences, both of which the design depends on:

- Every route that can promote a `.llat/` passes through `on_yes`, so a gate on
  that edge is exhaustive. A gate placed anywhere else would let plateau and
  max_steps runs promote unchecked.
- Conversely, § A failed render is invisible after iteration 1's claim that a
  broken run "burns to `max_steps` and promotes whatever `.llat/` last survived"
  is **correct**, not pessimistic — max_steps is a success route, not a failure
  one. Pin this with a test rather than re-deriving it; it is counter-intuitive
  enough that a future reader will assume the opposite.

**The gate's state shape, explicitly.** The issue previously said only "routes
failure to `diagnose`", leaving the rest to implementation time:

```yaml
gate_template:
  action_type: shell
  action: |
    ...predicate, exit 0 = pass, exit 1 = fail...
  on_yes: finalize_done
  on_no: diagnose
  on_error: diagnose
```

`on_error: diagnose` matters as much as `on_no`: a malformed `data.json` makes the
JSON parse in the predicate itself fail, and that must be a gate rejection, not an
unrouted state error.

**Why routing the gate's failure to `diagnose` suppresses promotion.**
`promote_run_artifact` returns `None` whenever `result.failure_terminal`
(`fsm/persistence.py:753`), evaluated before any mode dispatch. `failed` is in
`FAILURE_TERMINAL_NAMES` (`fsm/schema.py:26-32`), so `html-anything`'s bare
`failed:` terminal is failure-flagged without declaring `failure: true`. A gate
failure routed `gate_template -> diagnose -> failed` therefore blocks promotion
with no new plumbing at all. This mechanism was unstated and is what makes the
terminal-gate placement work; pin it with a test rather than assuming it.

**The gate's predicate must be concrete, not "a few keys."** The earlier phrasing
("at least a few top-level keys and the template references them") is not
implementable and would be invented at implementation time — unacceptable for the
one check that decides whether this pilot's success rate means anything. The rule:

0. `<run_dir>/artifact.llat` exists and is a **directory**, and contains exactly
   one `template.*.j2` plus a readable `data.json`. _(Added at the second
   pre-implementation review.)_ Without this, a template-mode run in which the
   model wrote nothing at all satisfies rules 1–3 vacuously or fails them by
   accident depending on how the shell happens to be written — and the failure
   message would describe degenerate parameterization rather than a missing
   artifact. Rule 0 is also what makes the gate's `file`-mode no-op unambiguous:
   in `file` mode the directory does not exist, so the mode guard must be checked
   *before* rule 0 rather than relying on it.
1. `<run_dir>/artifact.llat/data.json` parses as a JSON **object** with **>= 3**
   top-level keys (excluding none — a top-level `ll` key is already a validation
   error upstream, `artifact_templates.py:190-197`).
2. **Every** top-level key of `data.json` appears somewhere in the
   `template.*.j2` body.
3. The body contains **>= 5** `[[=` substitution openers.

Rule 2 catches dead data; rules 1 and 3 together catch the hardcoded-body
degenerate case. Tune the two numbers if the pilot shows them mis-calibrated, but
they must be numbers in this issue before implementation starts, and the values
used must be recorded in § Pilot Results alongside the success rate.

### A failed render is invisible after iteration 1

_Added at the 2026-08-25 pre-implementation review — corrects a load-bearing
assumption behind steps 5 and 6._

Step 6 and § Promotion... both assume a render failure produces no HTML, hence no
screenshot, hence a miss that the ENH-2903 abandon gate can report. **That is only
true on the first iteration.**

`evaluate`'s action carries no `set -e`, so a nonzero `pre_evaluate_cmd` falls
through to the Playwright invocation, which finds the *previous* iteration's
`index.html` still on disk — `render_to_disk` overwrites its output rather than
creating it fresh (`render.py:67-68`), and nothing else removes it. Playwright
captures that stale render successfully, so `snapshot` computes
`SHOT_MTIME > ART_MTIME` and records `MISS=0` (`generator-evaluator.yaml:111-127`).
Consequences, all silent:

- `.screenshot_misses` never increments, `check_screenshot_abandon` never fires,
  and the `.miss_reason` side-channel of step 6 is never read.
- The scorer critiques the stale render, so `critique.md` describes output the
  model's current (broken) template did not produce. The next `generate` pass
  "fixes" phantom issues.
- The run burns to `max_steps` and promotes whatever `.llat/` last survived the
  terminal gate — or, if the template happens to be schema-valid but semantically
  broken, promotes it outright.

**Fix: `pre_evaluate_cmd` deletes the render target before rendering.** Shape:

```
rm -f <abs run_dir>/index.html
ll-artifact render <abs run_dir>/artifact.llat -o <abs run_dir> >/dev/null || <write .miss_reason>
```

With the target removed first, a failed render genuinely leaves no artifact,
`snapshot`'s `cp` fails, `MISS=1`, and the abandon path engages exactly as step 6
assumes. This is not an optimization — without it, step 6's entire mechanism is
dead code from iteration 2 onward.

Note the ordering constraint this creates: the `rm -f` must precede the render and
must not be conditional on the render's exit code, and the `.miss_reason` write
must not resurrect a stale `index.html`.

### `ll-artifact` on PATH becomes a hard dependency of a general-purpose harness

_Added at the second pre-implementation review._

`pre_evaluate_cmd` shells out to `ll-artifact`, a console script from the pip
package. There is precedent for a built-in loop invoking an `ll-*` CLI —
`rn-remediate.yaml:113-116,467-495` calls `ll-issues` and `ll-auto` — but those
are automation loops for maintainers. `html-anything` is a general-purpose harness
that a consumer whose `install_source` is `project-claude-code` or
`global-claude-code` (plugin only, no pip package) can run today with no `ll-*`
binary anywhere on PATH.

In that environment a template-mode run fails at *every* iteration with
`ll-artifact: command not found`. Post-`rm -f` that is indistinguishable from any
other render failure: no `index.html`, `snapshot` records `MISS=1`, and after
three iterations the run abandons — having spent three full `generate` passes to
report a generic screenshot problem.

Fix, one line inside `pre_evaluate_cmd`: probe `command -v ll-artifact` before
rendering and write a distinct `.miss_reason` naming the missing binary and the
`pip install little-loops` remedy when it is absent. This costs nothing, reuses
the step-6 side-channel already being built, and is what makes the pilot's failure
data honest — a run abandoned for a missing binary must not be counted as an
LLM template-emission failure in § Pilot Results.

Scope note: this is a *reporting* fix, not a packaging one. Making template mode
work without the pip package (vendoring the renderer, or a plugin-side shim) is
out of scope here and belongs with the follow-up that rolls the variant out to the
other eight loops — flag it there.

### The `rubric` prompt needs its own template-mode branch

_Added at the 2026-08-25 pre-implementation review — a fifth `html-anything.yaml`
edit that § Files to Modify was missing._

Adding a `data_parameterization` criterion to `rubric.md` (via `plan`) is only
half the mechanism. The **scoring** prompt — `run_gen_eval`'s `rubric` binding
(`html-anything.yaml:149-159`) — tells the scorer to read exactly three things:
`rubric.md`, then `screenshot.png` *or* `index.html`, then `brief.md`. It never
reads `manifest.yaml`, `template.*.j2`, or `data.json`. In template mode all
three of those are the *only* evidence that could support a parameterization
score, and the scorer would be looking solely at the rendered HTML — where a
hardcoded template and a fully parameterized one are indistinguishable by
construction.

Left unbranched, the scorer either invents a `data_parameterization` score with
no evidence or omits the criterion and breaks `critique.md`'s mandated format,
which the `ALL_PASS`/`ITERATE` decision is parsed from.

Fix: the `rubric` binding gets a template-mode branch instructing the scorer to
additionally read `<run_dir>/artifact.llat/manifest.yaml`,
`<run_dir>/artifact.llat/template.*.j2`, and `<run_dir>/artifact.llat/data.json`,
and to score `data_parameterization` from those sources — while continuing to
score every visual criterion from the screenshot as today. Same inline-conditional
prose convention as the `generate_prompt` branch.

### Promotion destination is overwritten on every run

_Added at the 2026-08-25 pre-implementation review — decide explicitly._

Post-correction (see § Program Design), the default template-mode destination is
`<templates_dir>/html-anything.llat`, keyed by **loop name only**
(`_promote_template_artifact`, `persistence.py:843-846`). `artifact_output.to` is
static YAML with no interpolation, so a run-scoped destination is not available
without new plumbing. Every template-mode run therefore clobbers the previous
one; because `produced_by` matches, it does so without even a warning
(`persistence.py:869-881`).

For a pilot whose whole point is comparing outputs across runs, that is worth
deciding rather than discovering. Land the overwrite behavior, document it in
LOOPS_REFERENCE.md, and note run-scoped naming as a follow-up if the pilot
proceeds to the other eight loops.

### Scope bound

`html-anything` only. The remaining eight HTML-family loops are a follow-up,
scoped once this pilot reports an actual success rate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **Mode-branch prose convention confirmed unchanged post-FEAT-3318**: `oracles/research-coverage.yaml`'s `academic_mode` remains the sole live example of "inline conditional prose, no template-conditional syntax" — declared in `context:` (`:29-39`) and interpolated raw into natural-language branches at `:57-64`, `:110-122`, `:150-179`, `:248-251`, `:280-330`, `:411-412` (e.g. "Query phrasing (academic_mode = ${context.academic_mode}): If academic_mode is true: ... If false: ..."). No newer instance of this convention landed elsewhere in the repo.
- **`artifact_path` override via `with:` confirmed unchanged**: `svg-image-generator.yaml:67-71` and `flux-image-generator.yaml:102-114` still pass `artifact_path` as a sibling key alongside `run_dir` in their `oracles/generator-evaluator` `with:` block. `html-anything.yaml`'s own `with:` block (`:122-182`) still passes only `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` — no `artifact_path` today.
- **`ll-artifact render` CLI contract** (`docs/reference/CLI.md:4512-4535`): resolves `<template>` path-first as a `.llat/` dir, falling back to `config.artifacts.templates_dir/<name>.llat`; render context is `data.json`'s top-level keys plus reserved `ll.theme_css`/`ll.assets`; a top-level `ll` key in `data.json` or `data_schema` is a validation error; `--output` names a directory, the actual filename comes from `manifest.yaml`'s `output:` key.
- **No FSM prompt anywhere instructs a model to emit the manifest+template+data triple** — confirmed again post-landing (grep for `manifest\.yaml|data_schema|\[\[=|renderer: jinja2` across the repo returns only FEAT-3318's own test fixtures, `artifact_templates.py`, the `ll-artifact` CLI modules, and one unrelated false positive in `cli-anything-bootstrap.yaml`). This issue's template-mode `generate_prompt` has zero prior art to model wording after.

## Integration Map

### Files to Modify

_Revised at the 2026-08-25 pre-implementation review — `artifact_path` removed
(§ The generate prompt must mandate `output: index.html`), `plan` and the oracle
parameter added._

- `scripts/little_loops/loops/html-anything.yaml:24-28` — the `artifact_mode`
  context var and the new top-level `artifact_output:` block
  (`from: artifact.llat`)
- `scripts/little_loops/loops/html-anything.yaml:46-114` — `plan`'s
  rubric-writing prompt: a template-mode branch adding the
  `data_parameterization` criterion (§ Nothing currently forces a meaningful
  template/data split). **Not in the original map.**
- `scripts/little_loops/loops/html-anything.yaml:117-186` — the `generate_prompt`
  template-mode branch and the new `pre_evaluate_cmd` value passed through
  `with:`. Note `artifact_path` is **not** added to `with:` — the mandated
  `output: index.html` means the oracle's own default already points at the
  rendered file.
- `scripts/little_loops/loops/html-anything.yaml:149-159` — `run_gen_eval`'s
  `rubric` binding: a template-mode branch pointing the scorer at the `.llat/`
  sources so `data_parameterization` is scoreable (§ The `rubric` prompt needs its
  own template-mode branch). **Not in the original map.**
- `scripts/little_loops/loops/html-anything.yaml:187-201` — `finalize_done` reports
  `index.html`; template mode reports the `.llat/` contents and the promotion
  destination instead. It is `action_type: prompt`, so it does **not** host the
  deterministic gate (correction below).
- `scripts/little_loops/loops/html-anything.yaml` — a **new `gate_template` shell
  state** between `run_gen_eval`'s `on_yes` and `finalize_done`, hosting the
  deterministic degenerate-`data.json` gate, with
  `on_yes: finalize_done` / `on_no: diagnose` / `on_error: diagnose`
  (§ The backstop must not live inside the iterate cycle). **Not in the original
  map**, and it supersedes the earlier plan to put the gate in `finalize_done` —
  a prompt state cannot run a deterministic shell assertion.
- `scripts/little_loops/loops/html-anything.yaml:207-218` — `diagnose`'s prompt is
  file-mode only: it names `index.html` as the artifact and reads
  `critique.md`/`rubric.md`, and its "most likely failure cause" hint names the
  score state. In template mode the likely causes are a render failure or a
  degenerate-data gate rejection, and the operator needs pointing at
  `artifact.llat/` (plus `.miss_reason` when present). **Not in the original map**
  — this is the sixth `html-anything.yaml` edit.
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:30-52,74-85` — the
  new optional `pre_evaluate_cmd` parameter (`parameters:` entry + `context:`
  default `""`) interpolated at the top of `evaluate`'s shell action. This is the
  *only* oracle edit; it is a generic parameter, not an artifact-mode branch, and
  the other eight consumers leave it unset. **Do not fork the oracle** and do not
  add a state to it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:43,52,82,106` —
  `artifact_path` stays at its `index.html` default in both modes; the screenshot
  target is not repointed. Eight other loops delegate to this oracle.
- `scripts/little_loops/cli/artifact/render.py:72` — `cmd_render`, invoked per
  iteration via `pre_evaluate_cmd` with absolute `--data`/`-o` paths

### Tests
- `scripts/tests/test_builtin_loops.py` — conformance for the modified
  `html-anything.yaml` (both modes parse, validate, and route)
- A `file`-mode regression asserting the default path is unchanged — but see
  § The file-mode regression cannot be byte-for-byte on the prompt for what that
  test can and cannot assert.

#### The file-mode regression cannot be byte-for-byte on the prompt

_Added at the 2026-08-25 pre-implementation review — resolves a contradiction
between Acceptance Criterion 2, § Mode selection, and the wiring pass's test
suggestion._

AC 2 says the file-mode path is unchanged, "same prompt". The chosen mode-branch
convention (§ Codebase Research: inline conditional prose, `research-coverage.yaml`'s
`academic_mode`) puts both branches in **one static prompt string**. The
file-mode `generate_prompt` value therefore *does* change by construction — the
template-mode branch text is inside it — and the same is true of `plan`'s
rubric-writing prompt and `run_gen_eval`'s `rubric` binding. This is inherent to
the convention, not a defect in it.

Consequences:

- The wiring pass's pointer at `test_enh3035_artifact_template_kit.py:62-68`
  (golden fixture + exact `.read_bytes()` equality) **does not transfer to the
  prompt**. It remains a fine model for byte-equality on a *rendered artifact*,
  which is a different assertion.
- The earlier research finding that "no existing conformance test asserts
  byte-for-byte-unchanged prompt text" was read as a gap to fill. It is not — it
  is the correct state, and this issue should not introduce one.

What the file-mode regression asserts instead:

1. Every file-mode instruction present in today's `generate_prompt` is still
   present verbatim as a fragment (fragment-presence style, per
   `TestResearchCoverageOracle`), and no template-mode-only instruction is
   reachable when `artifact_mode` is unset or `file`.
2. A `file`-mode run still writes `index.html` and reports the same five output
   paths from `finalize_done`.
3. A `file`-mode terminal promotes **nothing** (the `from: artifact.llat`
   missing-source skip, `persistence.py:757-763`).
4. `gate_template` is a no-op / not reached in `file` mode.

AC 2's "same prompt" clause should be read as behavioral equivalence in this
sense. Byte-for-byte equality applies to the produced artifact, not the loop YAML.

_Added at the 2026-08-25 pre-implementation review:_
- A test that a `file`-mode terminal promotes **nothing** given
  `artifact_output.from: artifact.llat` (the missing-source skip,
  `persistence.py:757-763`) — this is what makes the mode-independent
  `artifact_output` block safe, so it needs pinning rather than assuming.
- A test that `oracles/generator-evaluator.yaml`'s `pre_evaluate_cmd` defaults to
  `""` and that `evaluate`'s action is a no-op prefix when unset, so the eight
  non-template consumers are provably unchanged.
- Conformance on `plan`'s template-mode rubric branch (the
  `data_parameterization` criterion appears in template mode and is absent in
  `file` mode) — fragment-presence style, per `TestResearchCoverageOracle`.
- Conformance on `run_gen_eval`'s `rubric` binding: the template-mode branch
  names the `.llat/` sources (`manifest.yaml`, `template`, `data.json`) and the
  `file`-mode text does not — otherwise `data_parameterization` is scored with no
  evidence (§ The `rubric` prompt needs its own template-mode branch).
- Conformance that the template-mode `generate_prompt` states `index.html` is a
  render output that must not be edited directly (fragment-presence).
- A check that **every** value in `run_gen_eval`'s `with:` mapping survives both
  interpolation passes — no `${` other than a resolvable `${captured.*}` /
  `${context.*}` reference, and no `$${` anywhere (§ `pre_evaluate_cmd` is
  interpolated TWICE). _(Widened at the second pre-implementation review from
  `pre_evaluate_cmd` alone: the double pass is a property of the `with:`
  mechanism, and the new `generate_prompt` / `rubric` branches are prose *about*
  templating — the likeliest place a stray `${` lands.)_ A static string assertion
  over the whole mapping is enough, and the existing bindings already satisfy it,
  so it needs no new-keys-only carve-out. It catches the failure at test time
  rather than at run time, where it surfaces as an opaque
  `expected namespace.path`.
- Conformance that the template-mode `generate_prompt` forbids an `assets/`
  directory and mandates inline `<svg>` / `data:` URIs for images
  (fragment-presence), plus a unit test that a `.llat/` containing a binary file
  under `assets/` fails `build_ll_namespace` — pinning *why* the instruction
  exists, since the failure is a bare `UnicodeDecodeError` that
  `_promote_template_artifact`'s generic `except Exception` degrades to a silent
  warning.
- Conformance that the template-mode `generate_prompt` mandates
  `theme: design-tokens` **unconditionally** — i.e. the mandate is not phrased as
  conditional on `design_tokens_context` (fragment-presence, asserting the
  conditional phrasing is absent).
- A test pinning that the oracle's `max_steps_summary` is a terminal **without**
  `failure: true`, and therefore that a budget-exhausted `run_gen_eval` routes to
  `on_yes` (`executor.py:1087-1092`) — the counter-intuitive fact the
  `gate_template` placement depends on (§ Why `on_yes` is the right edge to
  intercept). Same for `check_stall` / `check_diff_stall`'s `on_no: done` exits.
- A test of whichever § `iter-N/` loses the template option is chosen: under (a),
  that a template-mode iteration archives the `.llat/` source somewhere
  recoverable; under (b), fragment-presence that `finalize_done`'s template-mode
  branch states the limitation.
- Conformance that `pre_evaluate_cmd` probes for `ll-artifact` and writes a
  binary-specific `.miss_reason` when it is missing (fragment-presence), so a
  plugin-only install does not silently contaminate § Pilot Results.
- A test that the `.miss_reason` side-channel is cleared on a successful render,
  not only written on failure (step 6) — otherwise the abandon message reports a
  stale cause.
- A static assertion that the bound `pre_evaluate_cmd` deletes the render target
  before invoking `ll-artifact render`, and unconditionally (§ A failed render is
  invisible after iteration 1). Pair it with a behavioral test that drives
  `evaluate` + `snapshot` with a stale `index.html` present and a failing render,
  asserting `.screenshot_misses` increments — the regression this guards is
  silent, so a fragment-presence check alone is not enough.
- Conformance that `gate_template` exists as an `action_type: shell` state
  between `run_gen_eval` and `finalize_done`, routes failure to `diagnose`, and
  that `finalize_done` remains `action_type: prompt` (i.e. nobody moved the gate
  back into it).
- A unit test of the gate predicate itself against four fixtures: a fully
  parameterized `.llat/` (passes), a missing/empty `artifact.llat/` (fails rule
  0), a `data.json` of `{}` (fails rule 1), and a hardcoded body with
  populated-but-unreferenced data (fails rules 2 and 3). Plus a routing
  conformance check that `gate_template` declares `on_error: diagnose`, not only
  `on_no`.
- Conformance that `diagnose`'s prompt names the `.llat/` sources in template mode
  and `index.html` in `file` mode (fragment-presence).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py:62-68`
  (`test_policy_builder_renders_byte_identically_to_golden_fixture`) — the
  byte-for-byte-unchanged pattern to model the file-mode regression test after
  (golden fixture + exact `.read_bytes()` equality). Corrects the earlier
  refine-issue research note claiming no such shape exists in this codebase —
  it exists for CLI-command output, not loop YAML, so still needs adapting.
  [Agent 3 finding] **Superseded in part at the 2026-08-25 pre-implementation
  review:** this shape does not transfer to prompt text at all — see
  § The file-mode regression cannot be byte-for-byte on the prompt.
- `scripts/tests/test_builtin_loops.py:~13230-13269`
  (`test_snapshot_routes_to_score_gate`, `test_snapshot_writes_screenshot_misses_counter`,
  `test_score_gate_routes_fresh_screenshot_to_score`,
  `test_check_screenshot_abandon_routes_to_summary_on_cap`,
  `test_record_screenshot_skip_falls_through_to_stall_chain`,
  `test_screenshot_abandoned_summary_emits_abandoned_key`) — existing
  ENH-2903 abandon-gate coverage on `oracles/generator-evaluator.yaml`; must
  keep passing unmodified since the oracle is not forked. None currently
  assert on the literal abandon message text
  (`generator-evaluator.yaml:301`), so a render-failure-specific message can
  be added alongside it without touching these assertions. [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the
  template-mode invocation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (`html-anything` section, ~lines 1510-1582)
  — the `run_dir` context-var row lists file-mode-only outputs (`index.html`,
  `brief.md`, `rubric.md`, `critique.md`, `screenshot.png`), the context-variables
  table has no `artifact_mode` row, and the usage examples/override block show
  only the `file`-mode invocation. Needs an `artifact_mode` row plus a
  template-mode example. [Agent 2 finding]
- `docs/reference/loops.md` (`oracles/generator-evaluator` section, ~line 474)
  — the `artifact_path` parameter description and its `run_gen_eval`
  invocation example are file-mode only; add a note or example for the
  template-mode `with:` override (mechanism itself is unchanged — the oracle
  is not forked). [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **No existing loop invokes `ll-artifact render` as a state**: a grep for `ll-artifact render` across `scripts/little_loops/loops/**/*.yaml` returns zero hits. This issue's per-iteration render step has no direct precedent to model after — it is a genuinely new wiring shape, not an established convention.
- **Mode-branch conventions this codebase already holds** (two live, non-superseding shapes — pick one knowingly rather than defaulting):
  - *Inline conditional prose*: `oracles/research-coverage.yaml:29-39,57-65,110,150,248,280` interpolates the raw context value directly into prompt text (`${context.academic_mode}`) and phrases the branch as natural-language instructions ("If academic_mode is true: ... If false: ..."). There is no `{% if %}`/Jinja conditional syntax anywhere in the FSM prompt-rendering path (confirmed against `fsm/interpolation.py`) — this matches the issue's own Proposed Solution statement that "FSM prompts are static text, so this is a conditional block in the prompt body, not two prompts."
  - *Dedicated dispatch state*: `rn-implement.yaml:183-194` (`dequeue_next`) uses a `shell`/`exit_code`-evaluated state (`test "${context.schedule_mode}" = "value_ranked" && exit 0 || exit 1`) to route to one of two full downstream states (`fifo_pop` vs `select_next`), with both `on_no` and `on_error` falling back to the pre-existing legacy path.
  - Default-preservation guard convention (BUG-1947): a runner-injected context default that is an empty string (like `design_tokens_context: ""` in this same file) must be checked for **truthiness**, not key-existence, since the key is always declared — the same shape applies if `artifact_mode` is given an empty-string/`"file"` default rather than being absent when unset.
- **`artifact_path` override precedent**: two sibling wrapper loops already override the oracle's `artifact_path` parameter via their `with:` block — `svg-image-generator.yaml:71` (`artifact_path: "image.svg"`) and `flux-image-generator.yaml:111` (`artifact_path: "image.png"`) — confirming the mechanism this issue proposes reusing (repoint `artifact_path` at a rendered file) is the established way consumers customize the oracle's screenshot target without forking it.
- **ENH-2903's abandon gate has no cause-distinction mechanism today**: `evaluate`'s `on_yes`/`on_no`/`on_error` all route to the same `snapshot` state (`generator-evaluator.yaml:83-85`); a miss is tracked only as a consecutive-count (`.screenshot_misses`), with no signal anywhere for *why* a screenshot was missed. ENH-2903's own resolution explicitly rejected a harder `on_error: failed` split as "too blunt." A render-failure-specific message (this issue's Acceptance Criteria) has no existing mechanism to build on within the oracle's current routing shape, and the oracle is out of bounds to fork.
- **No existing conformance test asserts byte-for-byte-unchanged prompt text**: `test_builtin_loops.py`'s current `html-anything` coverage (and the closest analog, `academic_mode` coverage for `research-coverage.yaml`) asserts structural facts and text-fragment presence/absence, never full-string/hash equality on a `generate_prompt` value. This issue's "file-mode regression must stay byte-for-byte unchanged" acceptance criterion has no existing test shape to copy — the regression test will need a new assertion style (e.g. exact-string or hash comparison), not an extension of the existing fragment-presence style. **Corrected at the 2026-08-25 pre-implementation review:** the absence is correct, not a gap. Byte-equality on a prompt is unachievable under the inline-conditional-prose convention this issue chose, and no such assertion should be written — see § The file-mode regression cannot be byte-for-byte on the prompt. Fragment-presence *is* the right style here.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **No prompt anywhere in this codebase currently instructs a model to emit a `manifest.yaml` + `template.*.j2` + `data.json` triple** — that shape is produced today only by deterministic code, `cli/artifact/templatize.py:899-903` (`Path.write_bytes`/`write_text`), never by an LLM-facing prompt. This issue's template-mode `generate_prompt` branch has zero prior art to model wording after, beyond the schema contract itself (see Program Design).
- **`test_builtin_loops.py`'s established multi-mode conformance pattern** is `TestResearchCoverageOracle` (`:14025-14107`): a `parameters` block check (`"academic_mode" in params`, not-required) plus per-mode text-fragment presence checks on the raw `action` string (e.g. `"## BibTeX" in action`), never structural branch parsing or full-string equality. `TestHtmlAnythingLoop` (`:10303-10402`) already follows the same fixture/class shape but has no mode-branching tests yet — the new template-mode conformance test should extend it with fragment-presence assertions in this style, and the file-mode regression should use the *same* fragment-presence style rather than an exact-string/hash assertion — **corrected at the 2026-08-25 pre-implementation review**, see § The file-mode regression cannot be byte-for-byte on the prompt.

## Program Design

### Types

N/A — no new data shape is introduced; `artifact_mode` is a plain string context
var, not a new dataclass/schema.

### Signatures

- `cmd_render(args: argparse.Namespace, logger: Logger) -> int`
  (`scripts/little_loops/cli/artifact/render.py:72`) — exit `0` on success, exit
  `1` uniformly for every failure category (unresolvable template, invalid
  manifest, missing/malformed/schema-invalid data, an `-o` that names an existing
  *file*, bad `--source`, lockfile-write failure).
- `run_gen_eval`'s existing `with:` binding (`html-anything.yaml:122,148,182`)
  passes `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` into
  `oracles/generator-evaluator`; this issue adds **`pre_evaluate_cmd`** as the one
  new key in that binding.

_Correction (2026-08-25 pre-implementation review):_ an earlier revision of this
section said the issue adds `artifact_path` to that binding. It does not — see
§ The generate prompt must mandate `output: index.html`.

### Call Path

`ll-loop run html-anything --context artifact_mode=template` ->
`run_gen_eval` (`html-anything.yaml:117`) -> `oracles/generator-evaluator` with a
template-shaped `generate_prompt` + `pre_evaluate_cmd` ->
`generate` (model writes `<run_dir>/artifact.llat/`) -> `evaluate`, whose action
now begins with `rm -f <run_dir>/index.html; ll-artifact render
<run_dir>/artifact.llat -o <run_dir>` (rendering `index.html`, per the mandated
`manifest.output`) -> Playwright screenshot of the unchanged `artifact_path`
default -> `snapshot` / `score_gate` / `score` -> `gate_template` (deterministic
degenerate-`data.json` check; failure -> `diagnose` -> `failed`, which suppresses
promotion) -> `finalize_done` -> `promote_run_artifact` (FEAT-3318) ->
`<templates_dir>/html-anything.llat/`

_Correction (2026-08-25 pre-implementation review): the earlier
`{run_id}-html-anything.llat/` destination in this path was wrong — see the
research finding below on `_promote_template_artifact` keying by loop name only,
and § Promotion destination is overwritten on every run._

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **Current `context:` block** (`html-anything.yaml:24-28`) declares exactly `description`, `pass_threshold: 7`, `design_tokens_context: ""` — no `artifact_mode` key exists yet. FEAT-3318 (this issue's dependency) is itself still `status: open` with zero code hits for `artifact_mode` anywhere in the tree.
- **Current `run_gen_eval` `with:` block** (`html-anything.yaml:122,148,182`) passes exactly `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` into `oracles/generator-evaluator` — it does **not** currently pass `artifact_path`, so the oracle's own default (`"index.html"`, `generator-evaluator.yaml:52`) applies implicitly today. Adding template mode means adding an `artifact_path` binding here for the first time.
- `cmd_render(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/artifact/render.py:72`) — exit `0` on success, exit `1` (uniformly, no distinct codes) for every failure category: unresolvable template, invalid manifest, missing/malformed/schema-invalid data, an existing-file collision at the output path, a bad `--source`, or a lockfile-write failure. **Corrected 2026-08-25 (pre-implementation review):** "existing-file collision at the output path" overstates the guard. `OutputPathError` fires only when `-o` *itself* names an existing file (`render_to_disk`, `render.py:59-61`); the rendered artifact is written with `out_path.write_text` (`:67-68`), which overwrites. Re-rendering into the same directory every iteration is fine — no fresh-output-dir-per-iteration workaround is needed.
- **Rendered filename is manifest-controlled, not caller-controlled**: `render_to_disk` (`render.py:36-69`) writes to `output_dir / template.manifest["output"]` — only the containing directory is settable via `-o`, the filename itself comes from `manifest.yaml`'s `output` key. Consequence for this issue: the per-iteration `artifact_path` value passed to the oracle must be `<rendered-output-dir>/<manifest.output>`, not an arbitrary fixed name the wrapper chooses.
- **`promote_run_artifact` is currently a no-op for this loop**: it returns `None` whenever `fsm.artifact_output is None` (`fsm/persistence.py:753`), and `html-anything.yaml` declares no top-level `artifact_output:` key today. FEAT-3318 must land the `artifact_output`/`artifact_mode`-aware promotion logic before this issue's generate-prompt work has anything to promote into a `.llat/` directory — confirms the existing `depends_on: FEAT-3318` frontmatter edge is load-bearing, not incidental.
- `--context KEY=VALUE` (`cli/loop/__init__.py:294`, applied in `cli/loop/run.py:184-188`) is a fully generic mechanism — it does a plain `fsm.context[key] = value` string assignment with no artifact-specific dispatch. Setting `artifact_mode=template` today would only add an undeclared context key; nothing currently reads it.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **The render step has one available mechanism, and it is already exercised three times elsewhere**: FSM states have exactly four `action_type` values (`prompt`, `slash_command`, `shell`, `mcp_tool` — `fsm/schema.py:629-631,694`); there is no dedicated `type: shell`/`type: cmd` primitive. A shell state's `action:` is interpolated then run as `bash -c "<action>"` (`fsm/runners.py:117,284-306`), reached via `_action_mode()` (`fsm/executor.py:2843-2858`). Precedent for capturing an `ll-*` CLI invocation's output for a later state: `rn-remediate.yaml:467-495` (`capture: ll_auto_output`, running `ll-auto ... | tee ...; exit $?`) and the smaller `rn-remediate.yaml:113-116` (`ll-issues format-check "$ID"`). A `capture:` on a shell state writes `{output, stderr, exit_code, duration_ms, failure_type}` into `${captured.<name>.*}` (`fsm/executor.py:2369-2389`).
- **`oracles/generator-evaluator.yaml`'s full 11-state cycle** (`initial: generate`, `max_steps: 40`): `generate` (`:55-72`, routes `on_yes`/`on_no`/`on_partial` all to `evaluate`, `on_error: failed`) -> `evaluate` (`:74-85`, playwright screenshot of `${context.artifact_path}`, `on_yes`/`on_no`/`on_error` all to `snapshot`) -> `snapshot` (`:87-131`, ENH-2903, sole writer of `.screenshot_misses`) -> `score_gate` (`:133-154`) -> `check_screenshot_abandon` (`:156-179`, hardcoded cap 3) / `record_screenshot_skip` (`:181-191`) -> `score` (`:193-224`) / `record_score` (`:226-244`) -> `check_stall` (`:246-264`) -> `check_diff_stall` (`:266-279`, loops back to `generate` or `done`) -> terminals `done`/`failed`/`screenshot_abandoned_summary`->`screenshot_abandoned`/`max_steps_summary`.
- **Render-state insertion point**: between `generate` and `evaluate` — a new `render` state, routed to unconditionally from `generate` (mirroring `generate`'s existing "route everything downstream, let evaluate/snapshot/score_gate own the real gate" convention, `:55-72`'s ENH-1907 comment), itself routing unconditionally to `evaluate`. `evaluate`'s `${context.artifact_path}` is bound once at oracle-invocation time via the parent's `with:` block (`svg-image-generator.yaml:71`, `flux-image-generator.yaml:111` precedent) — it is not re-read per iteration from a captured value, so the wrapper must compute the rendered file's expected path itself (manifest-controlled filename, `render_to_disk`, `render.py:36-69`) rather than deriving it from the render state's `capture:`.
- **ENH-2903 abandon-gate mechanics, concretely**: `.screenshot_misses` is written solely by `snapshot` (`:97-130`); the abandon threshold check lives in a *separate* state, `check_screenshot_abandon` (`:156-179`, hardcoded `screenshot_max_step_attempts=3`). No file or context key anywhere records *why* a miss occurred. A render-failure-specific message (this issue's AC) needs a new side-channel — e.g. a `.miss_reason` file written by `snapshot` (or a new pre-`snapshot` state) and read only by `screenshot_abandoned_summary` (`:287-303`) when composing its final message — without touching `evaluate`'s undifferentiated routing (`:83-85`) or `check_screenshot_abandon`'s cap logic. `cmd_render` (`render.py:72`) itself has no distinct exit codes to key this off of (exit 1 uniformly for every failure category) — the differentiator would have to come from parsing `${captured.render_step.output}`/`.stderr` text.
- **The `.llat/` contract the template-mode generate prompt must describe precisely** (`artifact_templates.py`): `manifest.yaml` requires exactly `name, version, renderer, output, data_schema` (`renderer` must be `"jinja2"`); `data_schema` is a restricted JSON-Schema-like subset (`type ∈ {object,array,string,number,integer,boolean,null}`, keys limited to `type,required,properties,items,enum,description`, `:29-30,85-140`) that rejects a top-level `ll` key (`:190-197,245-248`, reserved for render context); exactly one `template.*.j2` file is required — zero or multiple both fail (`find_template_body`, `:275-285`); the Jinja environment uses **non-default delimiters** `[[= =]]` (variables), `[[% %]]` (blocks), `[[# #]]` (comments), `StrictUndefined`, `autoescape=False` (`build_environment`, `:252-272`) — a model instructed with plain `{{ }}`/`{% %}` Jinja syntax will produce an invalid template.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **FEAT-3318 has landed (status: done, commit a63c5d939)** — the findings below supersede this issue's earlier claims that FEAT-3318 was still open with zero `artifact_mode` code hits. `html-anything.yaml` itself remains untouched by FEAT-3318 (confirmed: no `artifact_output`/`artifact_mode` in the file today) — the wiring is still entirely FEAT-3320's own scope.

- **Correction to the Call Path claim above**: default template-mode promotion is keyed by **loop name only**, not run id — `_promote_template_artifact` (`scripts/little_loops/fsm/persistence.py:802-897`) computes `dest = <config.artifacts.templates_dir>/<fsm.name>.llat` (line 843-846) when no `to:` override is set. The Call Path's `{run_id}-html-anything.llat/` naming does not match the landed code; the correct default destination is `<templates_dir>/html-anything.llat`. An explicit `to:` override (ending in `.llat` per the static gate's WARN check) is the only way to get a run-id-scoped or otherwise customized destination.
- **Effective-mode resolution, concretely**: `_effective_artifact_mode(fsm)` (`fsm/validation/structural_rules.py:857-863`) = `fsm.context.get("artifact_mode", fsm.artifact_mode)` — a `context:` key named `artifact_mode` takes precedence over the top-level `FSMLoop.artifact_mode` field (default `"file"`, schema.py:1451). This single function is shared by both the static gate and `promote_run_artifact`, "so the two can never disagree about which mode a run is in" (code comment). `_is_template_capable(fsm)` (`:866-879`) is deliberately broader — it fires when the effective mode is already `"template"` **or** `"artifact_mode"` is present as a `context:` key at *any* value (covers `context: {artifact_mode: file}` flipped per-run via `--context artifact_mode=template`).
- **Static gate, concretely**: `_validate_artifact_mode_deliverable(fsm)` (`fsm/validation/structural_rules.py:882-925`, wired at `:1027`) is an unconditional ERROR (no `_ok` suppression flag) when a template-capable loop has no `artifact_output` block; WARN if `artifact_output.to` is set but doesn't end in `.llat`. `ArtifactOutput` (`schema.py:1308-1356`): fields `from` (required), `to` (not required), `on` (terminal allowlist, default empty = all non-failure terminals) — note the PyYAML bareword-boolean landmine where an unquoted `on:` key parses as Python `True` (handled at `schema.py:1351`).
- **`_promote_template_artifact` mechanics** (`persistence.py:802-897`): requires `artifact_output.from` to resolve to a *directory* (not a file); stages into a sibling temp dir, stamps `manifest.yaml`'s `produced_by: <fsm.name>`, runs the full runtime gate (`load_manifest`, `find_template_body`, `load_data`, `validate_top_level_data`, a discarded `render_template`) on the staged copy before ever touching `dest`, then atomically swaps via `_templatize_promote(..., force=True)`. Failures (`ManifestError`, `DataValidationError`, generic exceptions) degrade to a logged warning + `None` return — never raises — matching the file-mode best-effort contract.
- **No other loop in the repo declares `artifact_mode: template`** — confirmed by both research passes (grep across `scripts/little_loops/loops/**/*.yaml` for `artifact_mode` returns zero hits). `hitl-md.yaml` remains the only loop with an `artifact_output:` block, and it is `file`-mode only (`hitl-md.yaml:48-51`). FEAT-3320 will be the first loop in the repo to actually exercise template mode — there is no landed example loop to model the wiring after, only FEAT-3318's own synthetic test fixtures.
- **Canonical minimal `.llat/` fixture** (ground truth for the generate-prompt's wording target): `test_fsm_persistence.py:1620-1636`, `_write_llat_fixture()` — writes `manifest.yaml` (`name: t`, `version: 1`, `renderer: jinja2`, `output: out.txt`, a one-field `data_schema`), exactly one `template.txt.j2` (`Hello [[= title =]]`), and `data.json` (`{"title": "World"}`). Agrees with the pre-existing `scripts/tests/fixtures/artifact_templates/{simple,theme,delimiters}.llat/` fixtures (FEAT-3036/ENH-3035) on required manifest keys and `renderer: jinja2`.

_Added by the 2026-08-25 pre-implementation review — verified directly against
the landed code:_

- **`ll.theme_css` is conditional on a manifest key that is not required**:
  `build_ll_namespace` (`artifact_templates.py:311-318`) always populates
  `ll.assets`, but populates `ll.theme_css` **only** when
  `manifest.get("theme") == "design-tokens"`. `theme` is absent from the required
  manifest key list (`name, version, renderer, output, data_schema`), so a model
  following the contract summary alone will omit it; a body referencing
  `[[= ll.theme_css =]]` then hits `StrictUndefined` and the render fails with a
  `DataValidationError`.
- **`ll-artifact render`'s relative-path anchor is `config.project_root`, not
  cwd**: `data_path` (`render.py:105-107`) and the `-o` output dir
  (`render_to_disk`, `:58-60`) both resolve a relative value against
  `config.project_root`. `html-anything`'s `init` state already captures
  `run_dir` as an absolute path (`html-anything.yaml:31-44`), so passing
  `${captured.run_dir.output}` satisfies this — but only because it is absolute.
- **`render_to_disk` overwrites, it does not collide**: `out_path.write_text`
  (`render.py:67-68`). The only path-collision guard is `OutputPathError` when
  `-o` itself names an existing file (`:59-61`).
- **`snapshot` copies a single file, so `iter-N/` archives the render, not the
  source**: `cp "$RUN_DIR/${context.artifact_path}"`
  (`generator-evaluator.yaml:106`) is a plain file copy — a `.llat/` directory
  would not be archived by it even if `artifact_path` pointed at one. With the
  mandated `output: index.html` this is a non-issue: the rendered HTML is what
  gets versioned per iteration, which is also what `check_stall` /
  `check_diff_stall` (`:246-279`) reason about. The live `.llat/` under `run_dir`
  is what `promote_run_artifact` reads at terminal.
- **`html-anything`'s `rubric` prompt already falls back to reading
  `index.html`** when no screenshot exists (`html-anything.yaml:157-158`). The
  mandated `output: index.html` keeps that fallback correct in template mode with
  no branch — though note the fallback then scores the *rendered* output, so a
  template-specific critique still depends on the `data_parameterization`
  criterion, which reads the `.llat/` sources directly.
- **`evaluate` carries `timeout: 120`** (`generator-evaluator.yaml:75`), shared by
  the prepended `pre_evaluate_cmd`. A deterministic Jinja render is
  sub-second, so the existing budget is ample; no timeout change needed.

### `pre_evaluate_cmd` is interpolated TWICE — the escaping rule is different here

_Added at the 2026-08-25 pre-implementation review. This is the single most
likely way steps 5 and 6 fail on the first attempt, and nothing else in this
issue flags it._

A value bound through a `with:` block is interpolated **twice**, not once:

1. At sub-loop invocation, `interpolate_dict(state.with_, ctx)`
   (`fsm/executor.py:873-877`) resolves the whole `with:` mapping against the
   *parent's* context — this is what turns `${captured.run_dir.output}` into the
   absolute run directory.
2. The resolved string lands in the child's `context` (`executor.py:893`), and the
   oracle's `evaluate` action then interpolates `${context.pre_evaluate_cmd}` on
   its own — a second full pass over the already-substituted text.

The consequence is that the usual escaping rule from the repo's shell states is
**wrong for this value**. `$${VAR}` un-escapes to a literal `${VAR}` on pass 1
(`fsm/interpolation.py:213,228,284`), and pass 2 then reads that as a namespace
path and raises `expected namespace.path`. A bare `${VAR}` fails on pass 1 for
the same reason. Correct forms inside a `with:`-bound shell snippet:

- **`${VAR}` → `$$$${VAR}`** (double-escaped: survives pass 1 as `$${VAR}`, pass 2
  as `${VAR}`).
- **Preferred: avoid brace syntax entirely.** Interpolation only scans `${`, so
  `$VAR`, `$?`, and `$(...)` pass through both passes untouched. Write
  `pre_evaluate_cmd` brace-free and the problem disappears rather than being
  managed.

This applies to step 6's `.miss_reason` logic specifically, which is the only
part of `pre_evaluate_cmd` that needs shell variables at all. The render
invocation itself uses only interpolated absolute paths and is unaffected.

**The rule is not specific to `pre_evaluate_cmd` — it governs every new
`with:`-bound value.** _(Added at the second pre-implementation review; the
section title and the test in § Tests both scoped this too narrowly.)_ The two
passes are a property of the `with:` mechanism, not of shell text. The
template-mode `generate_prompt` branch and the `rubric` branch are bound the same
way and get the same double pass, and both are *prose about templating* — exactly
the kind of text that attracts a stray `${`:

- a sample template body or CSS snippet in the prompt,
- any mention of an environment variable or shell form,
- a `data.json` example whose values look like placeholders.

`[[= =]]` / `[[% %]]` / `[[# #]]` are safe by construction — interpolation only
scans `${` — which is a quiet argument for the non-default delimiters, but it does
not protect the surrounding prose. Widen the static test accordingly: **no new
`with:`-bound value may contain a `${` sequence other than a resolvable
`${captured.*}` / `${context.*}` reference, and none may contain `$${`.** Note the
existing bindings already satisfy this (`generate_prompt` and `rubric` contain
only `${captured.run_dir.output}` and `${context.design_tokens_context}`), so the
assertion can be written over the whole `with:` mapping rather than a
new-keys-only subset.

## Implementation Steps

_Revised at the 2026-08-25 pre-implementation review._

1. Add the `artifact_mode` context var and the `artifact_output:` block
   (`from: artifact.llat`) to `html-anything.yaml`. Verify the static gate is
   satisfied and that a `file`-mode run promotes nothing (missing source).
2. Add the optional `pre_evaluate_cmd` parameter to
   `oracles/generator-evaluator.yaml` (default `""`, prepended to `evaluate`'s
   shell action). Confirm the eight other consumers are behaviorally unchanged.
3. Branch the `generate_prompt` on the mode: template mode instructs the model to
   write `manifest.yaml` + exactly one `template.*.j2` + `data.json` under
   `<run_dir>/artifact.llat/`, per the contract `artifact_templates.py` enforces
   — including `output: index.html`, the `[[= =]]` / `[[% %]]` / `[[# #]]`
   delimiters, no top-level `ll` key, `theme: design-tokens` +
   `[[= ll.theme_css =]]` (declared **unconditionally**, not gated on
   `design_tokens_context` — `themed_css_vars` degrades to neutral empty blocks;
   pair it with concrete CSS fallbacks) rather than inlined token values, and **no
   `assets/` directory** — images are inline `<svg>` or `data:` URIs, since
   `load_assets` reads every file under `assets/` as UTF-8 and a binary file there
   fails both the render and the promotion gate (§ The prompt must also state four
   contract details). **The prompt must also state that `index.html` is a build
   output**: it is (re)generated by `ll-artifact render` before every screenshot,
   so any direct edit to it is silently clobbered on the next iteration. The
   model reads `critique.md`, which scores the *rendered* HTML, and will otherwise
   be strongly tempted to "fix" `index.html` directly — producing a critique that
   never resolves and an iterate cycle that runs to `max_steps`. Instruct
   explicitly: fix `template.*.j2` or `data.json`, never `index.html`.
4. Branch `plan`'s rubric-writing prompt to add the `data_parameterization`
   criterion in template mode (§ Nothing currently forces a meaningful
   template/data split), **and** branch `run_gen_eval`'s `rubric` scoring prompt
   so the scorer actually reads the `.llat/` sources that criterion is about
   (§ The `rubric` prompt needs its own template-mode branch). Both halves are
   required — the criterion is unscoreable without the second.
5. Pass `pre_evaluate_cmd` from `html-anything`'s `with:` block:
   `rm -f <abs run_dir>/index.html; ll-artifact render <abs run_dir>/artifact.llat
   -o <abs run_dir> >/dev/null` — absolute paths, since relative ones resolve
   against `config.project_root`, not cwd; stdout quieted so it cannot perturb
   `evaluate`'s `output_contains: "CAPTURED"` match (§ Caveat on `evaluate`'s
   routing). No `--data` flag is needed: `cmd_render` defaults `data_path` to
   `<template root>/data.json` (`render.py:105`). Note also that `cmd_render`
   constructs `BRConfig(Path.cwd())` (`render.py:80`), so its notion of
   `project_root` follows the loop shell's cwd — which `init`'s `$(pwd)` already
   assumes is the project root; the absolute paths make this moot for the two
   arguments that matter.

   **The leading `rm -f` is load-bearing, not hygiene** — without it a failed
   render is undetectable from iteration 2 onward. See § A failed render is
   invisible after iteration 1. It must precede the render unconditionally.

   Also probe `command -v ll-artifact` first and write a distinct `.miss_reason`
   when it is absent, so a plugin-only install reports the missing binary instead
   of burning three iterations into a generic screenshot abandon
   (§ `ll-artifact` on PATH becomes a hard dependency).

   Decide § `iter-N/` loses the template here: either `pre_evaluate_cmd` also
   archives the `.llat/` source per iteration (option a) or `finalize_done`
   documents that best-iteration recovery is unavailable in template mode
   (option b). Do not leave the divergence undocumented.

   Mind the double-interpolation escaping rule — it applies to **every** value
   bound through `with:`, not just this one, so the `generate_prompt` and `rubric`
   branches written in steps 3 and 4 are subject to it too. See
   § `pre_evaluate_cmd` is interpolated TWICE.
6. Make a render failure surface as a render error through the ENH-2903 abandon
   path rather than a bare screenshot-miss. This depends on step 5's `rm -f`:
   with the stale `index.html` removed, a failed render leaves no artifact,
   `snapshot`'s `cp` fails, and `MISS=1` is recorded — which is what puts the run
   on the abandon path at all. Then: `pre_evaluate_cmd` writes
   `.miss_reason` under `run_dir` on nonzero exit **and removes it on exit 0**,
   and `screenshot_abandoned_summary` (`generator-evaluator.yaml:287-303`)
   includes it in its message when present. The removal-on-success half is not
   optional: `.miss_reason` is otherwise never cleared, so a render failure at
   iteration 1 followed by successful renders would leave a stale file that gets
   reported verbatim if the run later abandons for an unrelated screenshot
   reason — a message that is actively wrong, which is worse than the generic one
   this step replaces. No routing change; `evaluate`'s undifferentiated
   `on_yes`/`on_no`/`on_error` → `snapshot` (`:83-85`) is untouched, so the
   existing ENH-2903 tests keep passing (none assert the literal message text).
7. Update `finalize_done`'s reported output paths for template mode, including the
   promotion destination, and update `diagnose`'s prompt so a template-mode
   failure points the operator at `artifact.llat/` and `.miss_reason` rather than
   at `index.html` and the score state.

   Add the deterministic degenerate-`data.json` gate as a **new `gate_template`
   shell state** between `run_gen_eval`'s `on_yes` and `finalize_done`, using the
   four-part predicate in § The backstop must not live inside the iterate cycle
   (rule 0: `artifact.llat/` is a directory holding one `template.*.j2` and a
   readable `data.json`; then >= 3 top-level `data.json` keys; every key
   referenced in the body; >= 5 `[[=` openers). `finalize_done` is
   `action_type: prompt` and cannot host it. Wire it as
   `on_yes: finalize_done` / `on_no: diagnose` / `on_error: diagnose` — the
   `on_error` edge matters, since a malformed `data.json` fails the predicate's own
   JSON parse and that must read as a gate rejection, not an unrouted state error.
   `diagnose -> failed` suppresses promotion via `promote_run_artifact`'s
   `result.failure_terminal` short-circuit (`persistence.py:753`). In `file` mode
   the gate is a no-op — check the mode guard *before* rule 0, since
   `artifact.llat/` legitimately does not exist there.

   Note this edge is exhaustive precisely because a `max_steps` exhaustion and
   both plateau exits are **non-failure** terminals in the oracle and therefore
   arrive at `on_yes` too (§ Why `on_yes` is the right edge to intercept).
8. Conformance + `file`-mode regression tests; docs (LOOPS_REFERENCE.md's
   `artifact_mode` row and template-mode example, the overwrite-per-run note,
   CLI.md, HARNESS_OPTIMIZATION_GUIDE.md).
9. **Report the observed reliability** — see § Measuring the reliability number
   below for what to run and where to record it. This number is the input to the
   follow-up decision about the other eight loops.

### Measuring the reliability number

_Added at the 2026-08-25 pre-implementation review — the last acceptance
criterion previously had no method, and cannot be satisfied by the test suite._

It needs live host-CLI runs, which are manual, billable, and slow. Concretely:

- **N = 5** template-mode runs across at least three different artifact types
  (e.g. one dashboard, one résumé, one social card), so the number is not a
  single-prompt artifact.
- **First-try success** = the `.llat/` written by the first `generate` pass
  survives the runtime gate (`load_manifest` / `find_template_body` / `load_data`
  / `validate_top_level_data` / a discarded `render_template`) **and** clears the
  `data_parameterization` criterion. A template that is schema-valid but
  hardcoded counts as a failure, not a success — that distinction is the whole
  point of the measurement.
- **Post-critique success** = the same, at the run's terminal state.
- **Recorded in this issue** (a `## Pilot Results` section), not only in
  `postmortems/` — the follow-up scoping decision reads the issue.
- **Early-abort clause.** If the first **three** runs produce zero first-try
  successes, stop there. Record `0/3` and the observed failure modes as the
  result and close the measurement — the follow-up decision about the other eight
  loops is already answered, and the remaining two runs would only re-confirm it
  at cost. The abort is a valid outcome for this criterion, not a skipped one.
- Close-out is blocked on this section existing. It is the deliverable, not a
  nice-to-have.

## Impact

- **Priority**: P2 — without a producer, FEAT-3318's plumbing is inert and every
  loop→template route stays on the lossy `templatize` path.
- **Effort**: Medium — revised upward twice at the 2026-08-25 review. Not "one loop
  file": **seven** separate edits to `html-anything.yaml`
  (context/`artifact_output`, `plan`'s rubric-writing branch, `generate_prompt`,
  the `rubric` scoring branch, `finalize_done`'s reported paths, `diagnose`'s
  template-mode branch, and a new `gate_template` shell state), one generic
  parameter added to the shared oracle (plus one message-only edit to
  `screenshot_abandoned_summary`), and N=5 live runs for the reliability
  number, which is wall-clock and billable rather than code.
- **Risk**: Medium — the reliability of LLM-emitted schema-valid templates is
  unproven; that is what this issue measures. Contained: the default mode is
  untouched and the shared oracle is not forked.
- **Breaking Change**: No — new behavior is opt-in behind a context var.

## Use Case

A user runs `html-anything` in template mode over an architecture document. The
run produces a `.llat/` the user renders against an updated `data.json` next
month — no LLM call, no `templatize` round trip, no fidelity loss.

## Acceptance Criteria

- [ ] `ll-loop run html-anything --context artifact_mode=template` produces a
      `.llat/` directory that passes FEAT-3318's runtime gate and is rendered by
      `ll-artifact render` with no `templatize` step.
- [ ] The default (`file`) path is **behaviorally** unchanged — every file-mode
      instruction still present verbatim as a fragment, same `index.html`, same
      reported outputs, `gate_template` a no-op; a regression test pins this.
      Includes the promotion side effect of the newly-required `artifact_output`
      block: a `file`-mode run promotes **nothing**, because `from: artifact.llat`
      does not exist in that mode (`persistence.py:757-763`). The regression test
      asserts this explicitly.
      _(Revised at the 2026-08-25 pre-implementation review: the earlier "same
      prompt" wording implied byte-equality on the prompt string, which the
      inline-conditional-prose convention makes impossible by construction — the
      branch text lives in the same static string. Byte-equality applies to the
      produced artifact, not the loop YAML. See § The file-mode regression cannot
      be byte-for-byte on the prompt.)_
- [ ] `oracles/generator-evaluator.yaml` is **not** forked, branched on artifact
      mode, or given a new state. Exactly two changes are permitted: (a) one
      generic optional parameter, `pre_evaluate_cmd`, default `""`, prepended to
      `evaluate`'s existing action; and (b) a message-only edit to
      `screenshot_abandoned_summary` that appends `.miss_reason`'s contents when
      that file exists. Both are inert when unused: with `pre_evaluate_cmd` unset
      and no `.miss_reason` on disk, the eight other consumers are behaviorally
      unchanged and their existing conformance tests pass unmodified.
      _(Revised at the 2026-08-25 pre-implementation review: the earlier "the only
      oracle change is one generic optional parameter" wording contradicted
      Implementation Step 6, which requires (b).)_
- [ ] `artifact_path` keeps its `index.html` default in both modes — the template's
      `manifest.output` is mandated to `index.html` rather than the wrapper
      overriding the screenshot target.
- [ ] The emitted template is genuinely parameterized: run-specific content lives
      in `data.json` and is referenced from the body, not hardcoded. Enforced in
      two places: a `data_parameterization` rubric criterion in template mode
      (written by `plan`, **and** scoreable because the `rubric` prompt's
      template-mode branch reads the `.llat/` sources), plus a deterministic
      terminal gate that rejects a degenerate `data.json` before promotion. The
      deterministic gate runs in a new `gate_template` **shell** state immediately
      before `finalize_done` (which is `action_type: prompt` and cannot host it),
      **not** inside `pre_evaluate_cmd` — an in-cycle failure would surface as a
      screenshot miss and abandon the run, contradicting the criterion below. Its
      predicate is the concrete three-part rule in § The backstop must not live
      inside the iterate cycle, and a gate failure routes to `diagnose` ->
      `failed`, which suppresses promotion via `result.failure_terminal`
      (`persistence.py:753`). The gate sits on `run_gen_eval`'s `on_yes` edge and
      that placement is exhaustive: a `max_steps` exhaustion and both plateau
      exits are non-failure terminals in the oracle and arrive at `on_yes` too
      (§ Why `on_yes` is the right edge to intercept). Rule 0 (`artifact.llat/`
      is a directory with one `template.*.j2` and a readable `data.json`) precedes
      the three parameterization rules, and the state declares
      `on_error: diagnose` as well as `on_no: diagnose`.
- [ ] Best-iteration recovery in template mode is either supported or documented,
      not silently broken. `snapshot` archives only the rendered HTML, while
      `max_steps_summary` points the operator at `iter-N/` as "the highest-scoring
      iteration" — in template mode the template behind iteration N no longer
      exists (§ `iter-N/` loses the template). Either `pre_evaluate_cmd` archives
      the `.llat/` source per iteration, or `finalize_done`'s template-mode branch
      states the limitation explicitly. A test pins whichever was chosen.
- [ ] A template-mode run in an environment without `ll-artifact` on PATH reports
      the missing binary rather than abandoning after three iterations with a
      generic screenshot message (§ `ll-artifact` on PATH becomes a hard
      dependency). Runs abandoned for this reason are excluded from § Pilot
      Results rather than counted as template-emission failures.
- [ ] The emitted `manifest.yaml` declares `theme: design-tokens` and the body
      references `[[= ll.theme_css =]]` rather than inlining resolved token values
      — so the promoted template is re-renderable under a different theme.
      _(Revised at the second pre-implementation review: previously gated on
      `design_tokens_context` being non-empty. `themed_css_vars`
      (`artifact_template_kit.py:18-42`) already degrades to neutral empty scoped
      blocks when a project has no tokens configured, so the gate bought nothing
      and cost a nested conditional in the most conditional prompt string in the
      file. Declare it always; require concrete CSS fallbacks beside each
      `var(--…)` so the no-tokens render still looks right.)_
- [ ] The emitted template creates **no `assets/` directory**; images are inline
      `<svg>` or `data:` URIs. `load_assets` (`artifact_templates.py:296-308`)
      reads every file under `assets/` as UTF-8, so a model-written `logo.png`
      raises `UnicodeDecodeError` in `build_ll_namespace` — breaking the
      per-iteration render *and* silently aborting promotion, since that is not a
      `ManifestError`/`DataValidationError` and lands in
      `_promote_template_artifact`'s generic degrade-to-warning branch. The
      template-mode `generate_prompt` states this; a conformance test pins the
      instruction and a unit test pins the underlying failure.
- [ ] The screenshot/rubric/critique iterate cycle works in template mode — a
      low-scoring template is critiqued and regenerated, not abandoned.
- [ ] A template that fails to render surfaces the render error, not a generic
      missing-screenshot message — **and does so on every iteration, not only the
      first.** `pre_evaluate_cmd` removes the render target before rendering, so a
      failed render leaves no `index.html` for Playwright to capture; without that
      removal the previous iteration's render is screenshotted successfully,
      `snapshot` records `MISS=0`, and the abandon path plus the entire
      `.miss_reason` mechanism become unreachable (§ A failed render is invisible
      after iteration 1). A test simulates a mid-run render failure and asserts
      the miss is recorded.
- [ ] `test_builtin_loops.py` conformance passes for both modes.
- [ ] A `## Pilot Results` section in this issue records the observed first-try
      and post-critique success rates over N=5 live runs across ≥3 artifact types,
      per § Measuring the reliability number. A schema-valid but hardcoded
      template counts as a failure. An early abort at 0/3 first-try successes,
      recorded with its failure modes, satisfies this criterion.

## Related Key Documentation

- `.issues/features/P2-FEAT-3318-artifact-mode-template-loops-emit-template-data-natively.md`
  — the plumbing this consumes; see its § Generate-prompt variant and § Mode selection
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md`
  — the lossy fallback this exists to avoid (**done**)

## Status

**Open** | Created: 2026-08-25 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-25T19:38:24 - `57ef804f-0971-4904-a357-1b87749b6c61.jsonl`
- `/ll:refine-issue` - 2026-08-25T18:05:42 - `15c28d79-5759-4915-8931-cf98fd12b048.jsonl`
- `/ll:wire-issue` - 2026-08-25T17:31:29 - `f8fad891-fb12-4a0c-8abb-8d32e08edbbf.jsonl`
- `/ll:refine-issue` - 2026-08-25T17:24:56 - `93455bb6-59d7-4ea1-9471-0a612ecdba4d.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:33:23 - `057ec3b7-ff77-4991-8763-e77045d2afc1.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:33:14 - `057ec3b7-ff77-4991-8763-e77045d2afc1.jsonl`
