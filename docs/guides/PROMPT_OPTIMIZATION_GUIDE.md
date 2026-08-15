# Prompt Optimization Guide (APO)

> **When to use this**: You have a prompt, skill, or agent instruction file that mostly works
> but fails in ways you can describe — and you would rather have a loop improve it than tweak
> it by hand. This guide covers choosing an APO technique, building the labeled corpus
> `apo-textgrad` needs, running an optimization end to end, and defending the result with
> `prompt-regression-test`. For per-loop context variables and FSM state tables, see the
> [Built-in Loops Reference](LOOPS_REFERENCE.md#prompt-optimization-loops-apo). For FSM
> fundamentals (states, evaluators, routing), start with the [Loops Guide](LOOPS_GUIDE.md).

## Contents

- [What APO Actually Does](#what-apo-actually-does)
- [Choose a Technique](#choose-a-technique)
- [Build Your First `examples.json`](#build-your-first-examplesjson)
- [Worked Example: Optimizing a Commit-Message Prompt](#worked-example-optimizing-a-commit-message-prompt)
- [Reading the Signal](#reading-the-signal)
- [Locking Gains In with `prompt-regression-test`](#locking-gains-in-with-prompt-regression-test)
- [Gotchas](#gotchas)
- [When APO Stops Helping](#when-apo-stops-helping)
- [See Also](#see-also)

---

## What APO Actually Does

Every APO loop runs the same shape: read a prompt file, propose a change, score the result,
keep or discard, repeat until a score clears a threshold or the step budget runs out.

Two properties of that shape matter more than any individual loop's mechanics, and both are
easy to miss:

**Scoring is asserted by a model, not computed.** All five APO loops decide convergence with
the same evaluator — `output_contains` matching the literal string `CONVERGED`
(`apo-textgrad.yaml:43-49` and its equivalents). There is no numeric comparator anywhere in
the family. The loop asks a model to score its own work, compare that score to your threshold,
and print `CONVERGED` if it clears. The executor only checks whether that word appeared. A
score of `92/100` in a transcript is a model's opinion, not a measurement.

**Most of these loops never run your prompt against anything.** This is the distinction that
should drive your choice, and it is the one the per-loop reference pages cannot show you
because it only becomes visible when you compare them:

| | What it scores |
|---|---|
| `apo-textgrad` | Executes the prompt against labeled `input`/`expected` pairs and counts how many pass |
| `apo-beam`, `apo-contrastive`, `apo-opro`, `apo-feedback-refinement` | Reads the prompt as a document and grades the text against an `eval_criteria` string |

The second row is a categorically weaker signal. It rewards prompts that *read* well —
well-organized, explicit, confident — which correlates with prompts that *work*, but only
loosely. A prompt can score 95 on "clarity, specificity, and effectiveness" and still get the
answer wrong on every real input, and nothing in those four loops would notice.

That does not make them useless. Rubric-graded optimization is genuinely useful when you have
no ground truth to measure against — for tone, structure, coverage of edge cases you can name
but not label. Just know which one you are running.

## Choose a Technique

The root question is whether you can produce labeled examples. Everything else is secondary.

```
Can you write down inputs and their correct outputs?
│
├─ Yes, 10+ pairs ──────────────────────────────→ apo-textgrad
│     The only loop that measures outcomes. Use it.
│
├─ Yes, but only a handful ─────────────────────→ apo-textgrad anyway
│     A 5-pair corpus beats a rubric. Grow it as failures surface.
│
└─ No — quality is real but not enumerable
   │
   ├─ Criteria are precise, want a fast pass ───→ apo-feedback-refinement
   │     Single candidate, tightest convergence.
   │
   ├─ Want breadth / stuck on a plateau ────────→ apo-beam
   │     Widest exploration, most expensive.
   │
   ├─ Long run, keeps re-proposing bad ideas ───→ apo-opro
   │     Only loop with cross-round memory. Advisory only — writes nothing.
   │
   └─ Want a few angles, cheaply ───────────────→ apo-contrastive
         Smallest budget of the five.
```

The properties behind that tree:

| | `apo-textgrad` | `apo-feedback-refinement` | `apo-contrastive` | `apo-beam` | `apo-opro` |
|---|---|---|---|---|---|
| **Signal source** | Measured pass rate on labeled data | Rubric score on prompt text | Rubric score on prompt text | Rubric score on prompt text | Rubric score on prompt text |
| **Writes your prompt file?** | Yes, only on non-converged rounds | Yes, every round + on accept | Yes, every round | Yes, every round | **No — advisory only** |
| **Cross-round memory** | Implicit (via the file) | None | None | None | Explicit score history |
| **Candidates per round** | 1 targeted refinement | 1 | 3 (`num_variants`) | 4 (`beam_width`) | 1 |
| **Effective rounds at default** | ~5 | ~5 | 5 | ~5 | ~6 |
| **Threshold comparison** | strictly `exceeds` | `>=` | `>=` | strictly `exceeds` | `>=` |
| **Safe to run unattended** | Yes — full `on_blocked` + `on_error` routes | Partial | Partial | Partial | Partial |
| **Threshold variable** | `target_pass_rate` (90) | `quality_threshold` (85) | `quality_threshold` (90) | `target_score` (90) | `target_score` (90) |

Notes on the columns that bite:

- **"Writes your prompt file"** — four of the five overwrite the file *before* the convergence
  check, on every round including ones that end `CONTINUE`. Commit before you run. See
  [Gotchas](#gotchas).
- **"Effective rounds"** — `max_steps` caps *state executions*, not rounds. Divide by
  states-per-cycle to get the real budget.
- **"Threshold comparison"** — `apo-textgrad` and `apo-beam` require the score to strictly
  exceed the target, so `target_score=100` can never converge.

`apo-contrastive` and `apo-beam` are near-duplicates; pick contrastive when you want a cheaper
run and beam when you want structurally diverse candidates (its prompt explicitly instructs
"vary structure, phrasing, examples, and persona — not just minor wording",
`apo-beam.yaml:24`).

## Build Your First `examples.json`

`apo-textgrad` is the technique worth reaching for, and it is the one with a prerequisite:
a corpus. Nothing in little-loops ships a starter file or scaffolds one, so the first one is
handwritten.

The contract is a JSON array of objects:

```json
[
  {
    "input": "the input the prompt will receive",
    "expected": "what a correct response looks like"
  }
]
```

That is the whole schema. Two things to know about it:

- **Only `input` and `expected` are read.** `examples-miner` writes a much richer record
  (`difficulty_score`, `failure_cluster`, `freshness_weight`, and more), and `apo-textgrad`
  ignores all of it. Extra keys are harmless.
- **Nothing validates this file.** No Python code in little-loops reads or schema-checks it —
  it is a prose contract between the loop's action text (`apo-textgrad.yaml:22-23`) and you.
  A typo in a key name will not raise an error; it will silently produce a corpus the model
  interprets however it likes. If a run reports a suspiciously round pass rate on the first
  iteration, check the file.

**Sizing**: 10–20 pairs is the usual working range. Fewer than 5 and the pass rate quantizes
so coarsely that the gradient signal is noise — one example flipping moves the rate 20 points.
More than about 30 and each `test_on_examples` round gets slow and risks the state's 300-second
timeout (`apo-textgrad.yaml:19`), since every example is executed inside a single state.

**What makes a pair informative**: the corpus is a measuring instrument, so it should
discriminate. Pairs the current prompt already passes teach the optimizer nothing; pairs it
fails for reasons you cannot articulate teach it the wrong thing. Aim for a mix where the
current prompt passes roughly half — those are the cases where a change to the prompt actually
moves the number. If everything passes, the loop converges on iteration one and you learn
nothing. If nothing passes, every gradient points in a different direction at once.

`expected` does not need to be a verbatim string match. The comparison is semantic — the
action says "compare output to expected" (`apo-textgrad.yaml:23`) and a model does the
comparing. Describing the shape of a correct answer ("a conventional-commit subject line under
72 characters, type `fix`, no body") works as well as a literal example, and is often more
robust.

## Worked Example: Optimizing a Commit-Message Prompt

Say you have a prompt that writes commit messages and it keeps producing subject lines that
are too long and occasionally picks the wrong conventional-commit type.

**1. Commit first.** Four of the five loops rewrite the file in place, mid-run. Without a clean
tree you cannot tell what the loop changed, and you cannot get back.

```bash
git status --porcelain   # confirm clean
```

**2. Write the corpus.** Ten pairs, spanning the failure you can describe and the cases that
already work:

```json
[
  {
    "input": "diff: added retry with backoff to the S3 upload path after intermittent 503s",
    "expected": "fix(upload): retry S3 uploads with exponential backoff — subject under 72 chars, type is fix not feat"
  },
  {
    "input": "diff: new --json flag on the export command, plus docs and tests",
    "expected": "feat(export): add --json output flag — type is feat, scope names the command"
  },
  {
    "input": "diff: renamed internal variable tmp2 to retry_count, no behavior change",
    "expected": "refactor: rename tmp2 to retry_count — type is refactor, no scope needed for a cross-cutting rename"
  }
]
```

**3. Dry-run to check the wiring** before spending tokens:

```bash
ll-loop run apo-textgrad --dry-run \
  --context prompt_file=prompts/commit-message.md \
  --context examples_file=prompts/commit-examples.json
```

**4. Run it.** Start the threshold below where you expect to land — a target you cannot reach
burns the whole budget without converging:

```bash
ll-loop run apo-textgrad \
  --context prompt_file=prompts/commit-message.md \
  --context examples_file=prompts/commit-examples.json \
  --context target_pass_rate=80
```

The transcript alternates between testing and gradient computation:

```
[test_on_examples]
Example 1: PASS
Example 2: FAIL — subject line 81 chars, exceeds 72
Example 3: PASS
...
PASS_RATE=60

[compute_gradient]
FAILURE_PATTERN: subject lines exceed the length limit when the change touches
  multiple files
ROOT_CAUSE: the prompt states "keep the subject concise" without a hard limit,
  so the model treats it as a preference
GRADIENT: replace "concise" with an explicit "72 characters maximum, count them
  before responding" and add a self-check step

[apply_gradient]  → prompts/commit-message.md rewritten

[test_on_examples]
PASS_RATE=90

[compute_gradient]
CONVERGED
```

**5. Read the diff, not the score.** The loop's own report is a model grading itself; the diff
is ground truth:

```bash
git diff prompts/commit-message.md
```

Look for changes that generalize. A gradient that added "72 characters maximum" is a real fix.
A gradient that hardcoded your test inputs into the prompt is the loop gaming its own metric —
revert and add more varied examples.

**6. Lock it in** — see the next section.

## Reading the Signal

`apo-textgrad` emits four named tokens. What they mean, and what they mean when they go wrong:

| Token | What it is | Trouble sign |
|---|---|---|
| `PASS_RATE=<0-100>` | Share of corpus examples the model judged passing | Jumps to 100 in one round — usually a corpus that was too easy, or the model grading generously |
| `FAILURE_PATTERN` | The common theme across failures | Reworded but unchanged across rounds — the prompt is not absorbing the fix |
| `ROOT_CAUSE` | What in the prompt causes that pattern | Points at the input rather than the prompt — the corpus is wrong, not the prompt |
| `GRADIENT` | The specific instruction for the next revision | Vague ("make it clearer") — the loop has run out of signal |

The failure mode to watch for: **pass rate climbing while `FAILURE_PATTERN` stays the same.**
Because both the score and the convergence decision come from the same model reading the same
transcript, a run can drift into scoring itself more generously rather than actually improving.
The corpus is the only anchor. If the number moves and the described failure does not, trust
the description.

The mirror-image failure: the pass rate stalls but each round's `GRADIENT` is sensible and
specific. That is the loop working correctly against a corpus that is too hard — the prompt
genuinely cannot satisfy those examples. Either the examples encode contradictory expectations,
or the task needs more than prompt engineering.

## Locking Gains In with `prompt-regression-test`

An optimized prompt decays. The next person to edit it has no idea which line the loop
fought for. `prompt-regression-test` is the defensive counterpart: instead of chasing a
target, it defends a baseline.

```bash
ll-loop run prompt-regression-test \
  --context prompt_suite=prompts/ \
  --context pass_threshold=90
```

It runs your prompt suite, scores it, and compares against `.loops/tmp/prompt-baseline.json`.
On the first run the baseline does not exist, so it is created from the current scores
(`prompt-regression-test.yaml:54-56`) — the first run always passes and establishes the floor.

The useful part is what happens on a regression: `route_regression` routes to `trigger_apo`,
which runs `apo-textgrad` as a **sub-loop** to attempt an automatic repair, then re-scores and
updates the baseline only if the fix clears `pass_threshold`
(`prompt-regression-test.yaml:92-112`). A regression triggers a repair attempt rather than just
a red mark.

> **Caveat**: `trigger_apo` passes context through to the child (`context_passthrough: true`)
> but `prompt-regression-test` declares no `examples_file` of its own. The child therefore
> falls back to `examples.json` in the working directory. If your corpus lives anywhere else,
> pass `--context examples_file=<path>` on the parent run, or the repair sub-loop optimizes
> against the wrong file — or none.

Note the scope difference: `prompt-regression-test` takes a *directory* of prompts
(`prompt_suite`), not a single file. It is the only loop in this guide built for a suite.

## Gotchas

> **`apo-opro` does not write your prompt file.** It reads `prompt_file`
> (`apo-opro.yaml:29`) and never writes it — no state in the loop modifies the file. The
> winning candidate exists only in the run transcript. Copy it out yourself, or you will
> finish a run, check `git diff`, see nothing, and conclude the loop failed. Every other APO
> loop writes; this one advises.

> **The other four write before deciding.** `apo-beam` (`:48`), `apo-contrastive` (`:49-50`),
> and `apo-feedback-refinement` (`:74`) overwrite the prompt file inside the same state that
> scores it — *before* the convergence check. A run that ends at the step cap without
> converging still leaves the file modified, mid-optimization. Always start from a clean tree.

> **`apo-beam`'s `eval_criteria` defaults to an empty string** (`apo-beam.yaml:14`). Unlike
> `apo-contrastive` and `apo-feedback-refinement`, beam does not inherit the populated default
> from `lib/apo-shape-a`. Run it bare and it scores every variant against `""` — which
> produces scores, and convergence, and means nothing. Always pass `--context eval_criteria=...`
> to `apo-beam`.

> **`target_score=100` never converges on `apo-textgrad` or `apo-beam`.** Both require the
> score to *strictly exceed* the target (`apo-textgrad.yaml:39`, `apo-beam.yaml:46`), so a
> perfect score fails its own test. (`apo-textgrad` special-cases `PASS_RATE=100`; `apo-beam`
> does not.) The other three use `>=`. Set 90, not 100.

> **`max_steps` counts state executions, not rounds.** The executor increments its counter on
> every state entry (`fsm/executor.py:486`), including the pure evaluator states that only
> route. Divide by states-per-cycle for your real budget: `apo-textgrad` 20/4 ≈ 5 rounds,
> `apo-contrastive` 15/3 = 5, `apo-opro` 25/4 ≈ 6. Raise it with `-n`/`--max-steps`.
> `--max-iterations` does **not** help here — it counts maintain-mode restarts
> (`fsm/executor.py:597-599`), and no APO loop runs in maintain mode.

> **`target_pass_rate` means different things in different loops.** `apo-textgrad` reads it as
> an integer percent (`90`); `examples-miner` declares the same name as a fraction (`0.6`).
> Because the miner runs textgrad as a sub-loop with `context_passthrough: true`, overriding
> `target_pass_rate` on an `examples-miner` invocation passes your value straight into the
> child. Pass `0.6` and the child sees a target of 0.6 percent — it converges immediately.

One more, subtler: **`apo-feedback-refinement` evaluates a candidate it has not written.**
`generate_candidate` produces a candidate in memory, `evaluate_candidate` scores that text, and
on a non-converged round `refine` edits the *file* to address the weaknesses
(`apo-feedback-refinement.yaml:67-77`). The next round then re-reads the file. So the text that
was scored and the text on disk can drift apart across rounds. It converges anyway, but do not
read an intermediate score as describing the file's current contents.

## When APO Stops Helping

APO plateaus. The signature is a pass rate that sits flat for two or three rounds while the
gradients get progressively vaguer — the optimizer has extracted everything your corpus can
tell it.

At that point the bottleneck is the corpus, not the prompt. A corpus written when the prompt
was weak is all easy cases now: everything passes, the gradient signal disappears, and further
optimization is just noise. The fix is harder examples, targeted at the failures the current
prompt still has.

That is what [`examples-miner`](EXAMPLES_MINING_GUIDE.md) automates — harvesting real
invocations from your own session history, quality-gating them, and calibrating difficulty to
a band where the signal is informative again. Reach for it once `apo-textgrad` has plateaued
around 90% and the prompt still fails on real inputs.

If you are optimizing the `rn-plan` planning prompt specifically, there is a purpose-built
variant: [`rn-plan-apo`](LOOPS_REFERENCE.md#rn-plan-apo--plan-quality-gradient-optimization)
scores plans on subtask success rate, depth, redundancy, and coverage gaps rather than a text
rubric.

## See Also

- [Built-in Loops Reference → Prompt Optimization Loops (APO)](LOOPS_REFERENCE.md#prompt-optimization-loops-apo) — per-loop context variables, FSM state tables, and invocation examples
- [Examples Mining Guide](EXAMPLES_MINING_GUIDE.md) — co-evolutionary corpus mining for when `apo-textgrad` plateaus
- [Loops Guide](LOOPS_GUIDE.md) — FSM fundamentals: states, evaluators, routing, and the `/ll:create-loop` wizard
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — hill-climbing a skill, command, or agent definition against a benchmark, rather than a prompt file against examples
- [Loops Guide → Composable Sub-Loops](LOOPS_GUIDE.md#composable-sub-loops) — how `context_passthrough` works, relevant to both the miner and regression-test handoffs
- [`apo-textgrad.yaml`](../../scripts/little_loops/loops/apo-textgrad.yaml) — the loop definition itself; the action text is the real specification for `examples.json`
