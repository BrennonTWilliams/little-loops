---
id: BUG-3331
type: BUG
title: Loop YAMLs interpolate untrusted text into Python string literals inside shell
  actions
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-26'
captured_at: '2026-08-26T21:00:00Z'
supersedes: []
decision_needed: false
---

# BUG-3331: Loop YAMLs interpolate untrusted text into Python string literals inside shell actions

## Summary

Loop `action_type: shell` states embed Python via a heredoc
(`python3 << 'PYEOF'`) and build that Python by **textually substituting**
`${context.*}` and `${captured.*.output}` directly into string literals. The
FSM's interpolation engine is pure text substitution
(`scripts/little_loops/fsm/interpolation.py`) with no quoting or escaping, so
the substituted value is not data — it is *source code*.

Two consequences, both live today:

- **A quote character in the value is a `SyntaxError`.** A goal containing
  `don't` terminates the single-quoted literal it lands in; an LLM response
  containing `"""` terminates the triple-quoted literal it lands in. The state
  dies with an opaque Python traceback that names neither the loop nor the
  offending input.
- **The value can inject arbitrary Python.** Anything that closes the literal
  and continues with a new statement executes inside the loop's shell action,
  with the run's full privileges.

Split out of BUG-3327 (its "class (2) — code literal" sites). BUG-3327 covers
prompt fencing; this issue covers code-literal quoting. The two share no code,
no test shape, and no rationale.

**BUG-3327 named four sites. The survey below found 145 (plus 131 lower-priority
class-C sites) across 33 loop files.**

## Current Behavior

Two *value shapes* (scalar vs. multi-line LLM output) crossed with two *host
shapes* (quoted heredoc vs. `python3 -c "…"`). The host shape determines how many
layers are broken, and the issue's remedy differs per shape.

### Host shape 1 — quoted heredoc (`python3 << 'PYEOF'`)

Scalar user input into a single-quoted literal
(`scripts/little_loops/loops/loop-router.yaml:192`):

```python
inp = (input_m.group(1).strip() if input_m else '') or '${context.goal}'
```

LLM output into a triple-quoted literal (`loop-router.yaml:185`):

```python
output = """${captured.project_score.output}"""
```

The heredoc *is* quoted, so bash performs no expansion — these are not shell
injections. The substitution happens one layer earlier, in the FSM interpolation
pass over the raw action string, before bash ever sees the text. Quoting the
heredoc does not help.

### Host shape 2 — `python3 -c "…"` (53 sites, 11 files)

`loop-router.yaml:31-34` — the very site this issue lists first as a class-A
representative:

```bash
ll-loop list --json --visibility public 2>/dev/null | python3 -c "
import json, sys, os
loops = json.load(sys.stdin)
include_raw = '${context.include}'
```

The Python body here lives inside a **bash double-quoted string**. Bash *does*
expand it, so this shape is strictly worse than the heredoc: a value containing
`"` breaks bash tokenizing, `$(...)`/backticks command-substitute *before* Python
is ever invoked, and the surviving text still has to parse as a Python literal.
Both a shell injection and a code-literal injection, stacked.

Confirmed `-c "` class-A/B sites: `loop-router.yaml:34, 53`; `sft-corpus.yaml:114,
118, 136, 139, 156, 160, 178, 181, 198, 202, 220, 223, 240, 244, 262, 265, 319,
322`; `autodev.yaml:1633, 1742, 1821, 1822, 2053, 2054`; `lib/composer.yaml:32,
51`; `oracles/code-run-gate.yaml:438`; `oracles/oracle-capture-issue.yaml:34`;
`rn-plan-apo.yaml:48`; `harness-optimize.yaml:164`; `general-task.yaml:898`.

**These must be converted to a quoted heredoc first**, then treated as shape 1.
That is a third mechanical step the original plan did not budget for.

#### Scope ambiguity in the shape-2 conversion (resolve before Step 4)

"53 sites, 11 files" counts **interpolation sites**, but the unit of work in Step 4
is the **invocation**: there are **114 `python3 -c "` invocations across 29 files**
(`autodev.yaml` 26, `rn-build.yaml` 10, `oracles/code-run-gate.yaml` 10,
`sft-corpus.yaml` 9, `workflow-generator.yaml` 7, `cli-anything-bootstrap.yaml` 6,
…). Two readings, roughly 2× apart in effort on the riskiest step:

- **Narrow — SELECTED (2026-08-27).** Convert only the invocations that *contain* a
  class-A/B site (the 11 files). Consequence: 18 files keep the `-c "` shape, so the
  Step-2 sweep **must not flag a `-c "` block whose interpolations are all class C**.
  This is not a special case in the sweep: it falls out of the per-site
  classification rule below for free, since a class-C site is clean in either host
  shape.
- ~~**Broad**~~ — convert all 114 invocations. Rejected: it triples the volume of the
  one step that changes shell structure rather than a token (the step Impact names as
  hazard 1), and buys only a simpler sweep rule the classifier already gives us.

### Sweep classification rule (settles class C vs. class A/B)

The sweep must decide, per interpolation site, whether it is untrusted. Do **not**
reproduce MR-11's fixed key allowlist — that is the exact narrowness this issue
faults it for. Invert it:

- `${captured.*}` — **always untrusted** (class B). No exceptions; a capture is
  either LLM output or command output, never operator-fixed.
- `${context.<key>}` — **untrusted by default** (class A), except the *trusted*
  set of runner-constructed keys. **That set is enumerated (2026-08-27), not
  open-ended**: the only non-underscore keys the runner itself writes are
  `run_dir` (`executor.py:903, 979`) and `promoted_artifact`
  (`persistence.py:1229`); underscore-prefixed bookkeeping keys
  (`_tamper_guard`, `_prepatch_check`) are runner-internal and also trusted.
  Every other `context.*` key originates from the loop YAML's `context:` block
  or a CLI override and is untrusted. `${loop.*}` (run_id, iteration, …) is
  runner-constructed and trusted.
- Consequence: a newly-introduced `${context.*}` key is untrusted until someone
  adds it to the trusted list, which is the safe default direction.

The same rule serves Step 9's MR-11 widening — implement it once, share it.

## Steps to Reproduce

1. Run `loop-router` with a goal containing an apostrophe:
   `ll-loop run loop-router --input "don't break the build"`.
2. `parse_project_score` interpolates it into
   `... or '${context.goal}'`, producing
   `... or 'don't break the build'`.
3. Observe: `SyntaxError: invalid syntax` from the heredoc'd Python. The state
   fails, and the error names neither `loop-router` nor the goal.

For the LLM-output variant, no adversary is needed — any model response
containing `"""` reproduces it non-deterministically.

## Expected Behavior

Untrusted text reaches Python as **data**, never as source. Two established
in-repo idioms, one per value shape:

1. **Scalars → environment, bound with `:shell`.** Bind the value to an env var
   on the `python3` invocation and read it with `os.environ`:

   ```bash
   LL_ARG_GOAL=${context.goal:shell} python3 << 'PYEOF'
   import os
   goal = os.environ.get("LL_ARG_GOAL", "")
   PYEOF
   ```

   **The `LL_ARG_` prefix is mandatory** — see *Env-var naming* under Proposed
   Solution; shell actions inherit the full parent environment, so an unprefixed
   `GOAL=` shadows an inherited value.

   **The `:shell` suffix is required and the surrounding double quotes must be
   omitted.** `interpolation.py` supports a `:shell` suffix that `shlex.quote()`s
   the resolved value at substitution time (`interpolation.py:255, 271`); it
   supplies its own quoting. Writing `GOAL="${context.goal}"` instead re-creates
   the identical defect one layer down — a `"` in the value closes the bash
   string and a `$(...)` command-substitutes — which is exactly the argument used
   below to reject env-binding for class B. It is equally fatal for class A. It
   also trips the existing MR-11 lint (see *Interaction with MR-11*).

   Existing precedent for the env-var half:
   `mechanize-skills.yaml:162` (`RUN_DIR="$RUN_DIR" python3 << 'PYEOF'` +
   `os.environ`), `:283`, `:511`, `:528`; `autodev.yaml:405`
   (`ISSUE_FILE="$ISSUE_FILE" python3 << 'PYEOF'`); `flux-image-generator.yaml:275`
   (`abs_dir = os.environ["ABS_DIR"]`). Note those bind an already-safe *shell*
   variable, not a raw interpolation — for a raw `${context.*}` the `:shell`
   suffix is what makes the binding safe. 17 sites across the loop corpus already
   use `:shell` (recounted 2026-08-27; 12 assignment-prefix, 5 bare-token — the
   bare-token five are audited under S1, see the BLOCKER section).

   **Only sound in the assignment-prefix position.** `interpolate()` returns `""`
   for a `None`-resolving value *before* it reaches the `shlex.quote` branch
   (`interpolation.py:270-273`), so `:shell` on an absent value emits nothing —
   not `''`. `VAR=${context.x:shell} python3 …` degrades harmlessly to
   `VAR= python3 …` (empty assignment), but the same token in a bare argument
   position (`[ -z ${context.x:shell} ]`) collapses the token and changes the
   command's arity. Use the `VAR=…` prefix form only; do not generalize `:shell`
   to bare token positions as part of this work.
2. **Multi-line LLM output → a file.** Write the captured output to a run-dir
   file via its own quoted heredoc, then `open()` that file from the Python
   heredoc (Option B — see Decision Rationale under Proposed Solution).
   Precedent: `brainstorm.yaml:160-169` (BUG-2468, shipped/tested),
   `cua-agent-desktop.yaml:417-423` (shell-only sibling).

## Motivation

This is the sharper half of what BUG-3327 surfaced, and it is not latent — the
apostrophe break fires on ordinary English input, and the LLM-output variant
fires on ordinary model output with no adversary at all. Unlike the fencing
work, it has an unambiguous, already-used-in-repo remedy; what it lacks is
coverage.

## Site survey

Recounted 2026-08-27 across `scripts/little_loops/loops/**/*.yaml` — **recursive,
including the `lib/` and `oracles/` subdirectories**, which the original
2026-08-26 survey's non-recursive glob missed. Counted by walking each action
string's real block boundaries (quoted-heredoc marker matching; `-c "` closed at
the next unescaped `"`), skipping sites already carrying a `:shell` suffix.

| Class | Heredoc | `-c "` | Total |
|---|---|---|---|
| A — user/config scalar into a Python literal | 55 | 23 | **78** |
| B — LLM output into a Python literal | 56 | 11 | **67** |
| C — `run_dir` / loop-controlled paths | 112 | 19 | **131** |
| **Total** | 223 | 53 | **276** |

**33 loop files affected; 11 of them contain `-c "` sites.**

The original survey's "~23 class A / 27 class B / ~10 class C, ~60 total" was low
by roughly 2.5× on A and B and 13× on C. Densest files: `sft-corpus.yaml` (38),
`loop-router.yaml` (35), `recursive-refine.yaml` (29), `goal-cluster.yaml` (19),
`autodev.yaml` (13), `loop-composer-adaptive.yaml` (13), `mechanize-skills.yaml`
(13, all class C).

### Class A — user/config input into a Python literal (78 sites)

Apostrophe-breakable and injectable. The value originates from operator CLI
input, so the security severity is self-inflicted; the **availability** impact
is not — an ordinary goal breaks the loop.

Representative: `loop-router.yaml:34, 53, 192, 252, 345`;
`loop-composer.yaml:231`; `goal-cluster.yaml:347, 389`;
`apply-research.yaml:216, 217`. Note `loop-router.yaml:34` and `:53` are `-c "`
sites, not heredoc sites — see *Host shape 2* above.

### Class B — LLM output into a Python literal (67 sites)

**The sharper class.** The value is model-generated, so nothing constrains it:
a `"""` anywhere in the response breaks the state, and prompt-injected content
in the model's own output becomes executed Python.

Representative: `loop-router.yaml:127, 141, 185, 245, 338, 472`;
`apply-research.yaml:168, 306`; `assumption-firewall.yaml:66, 128, 158`;
`goal-cluster.yaml:207, 436, 566, 639`; `learning-tests-audit.yaml:114-116, 225`;
`migrate-sdk-version.yaml:171, 183`. The 11 `-c "` class-B sites
(`sft-corpus.yaml:118, 139, 160, 181, 202, 223, 244, 265, 322`;
`harness-optimize.yaml:164`; `general-task.yaml:898`) need the heredoc conversion
before the class-B remedy applies.

### Class C — `run_dir` and similar loop-controlled paths (131 sites)

Same textual shape (`run_dir = '${context.run_dir}'`), but the value is
constructed by the runner, not by a user or a model. **Lowest priority** — fix
opportunistically while touching a file, do not sweep for it. The count is far
larger than first estimated, which is another reason not to sweep it: the sweep
would dominate the diff without closing a live defect.

### Subdirectory coverage (28 sites, 8 files) — missed by the original survey

`lib/composer.yaml`, `lib/policy-router.yaml`, `lib/rubric-router.yaml`,
`oracles/code-run-gate.yaml`, `oracles/enumerate-and-prove.yaml`,
`oracles/generator-evaluator.yaml`, `oracles/oracle-capture-issue.yaml`,
`oracles/verify-confidence-scores.yaml`. `oracles/` loops are runnable and
`lib/` holds fragments composed into runnable loops; both are in scope. **The
static regression sweep must glob recursively** or it will certify a false clean.

### Explicitly out of scope

`${context.*}` interpolated into **prompt** text (e.g.
`incremental-refactor.yaml:88, 93, 136, 165`) is not a code literal — no
interpreter parses it. That is BUG-3327's territory.

## Proposed Solution

0. Convert the **53 `python3 -c "…"` sites** (11 files) to quoted heredocs
   (`python3 << 'PYEOF'`) first. Until that lands, those sites are shell
   injections as well as literal injections, and neither the class-A nor the
   class-B remedy is sound in place.
1. Convert **class A** sites to the `:shell`-bound env-var idiom:
   `LL_ARG_GOAL=${context.goal:shell} python3 << 'PYEOF'` +
   `os.environ.get("LL_ARG_GOAL", "")`. No surrounding double quotes — `:shell`
   shlex-quotes the value itself. Prefix every binding `LL_ARG_` (see *Env-var
   naming* below).
2. Convert **class B** sites per the decision below.
3. Leave **class C** alone except where already editing the surrounding state.
4. Add a lint (see Follow-up) so new sites cannot be introduced.

### BLOCKER — `:shell` does not compose with `:default=` or `?`

`interpolate()` parses the three suffixes as **mutually exclusive** and raises
`InterpolationError("Ambiguous suffix: … (:default=..., ?, and :shell are mutually
exclusive)")` on any combination (`scripts/little_loops/fsm/interpolation.py:242-248`,
`:250-256`). Steps 5 and 6 as written are therefore **unimplementable at any site
that already carries a `:default=` or `?` suffix** — the conversion produces a
runtime hard failure, not a lint warning.

This is not hypothetical. **130 `${context.*}` / `${captured.*}` sites repo-wide
carry `:default=` or `?`**, and real class-A/B targets are among them:

- Class B: `loop-router.yaml:522-523`
  (`"""${captured.new_loop_proposal.output:default=}"""`,
  `"""${captured.review_result.output:default=}"""`);
  `loop-composer-adaptive.yaml:744, 750`
  (`'${captured.user_plan_decision.output:default=}'`,
  `'${captured.chain_review.output:default=}'`)
- Class A: `rn-refine.yaml:151, 223, 500, 907, 1014-1015`;
  `recursive-refine.yaml:55, 82-83, 118, 304, 320`; `rn-build.yaml:728-729`

**Additionally, the suffix parse has a silent-misparse branch — S1 must fix it too.**
The mutual-exclusion guard fires for only *one* of the two orderings
(`interpolation.py:243-248` tests `var_part.endswith(":shell")`, i.e.
`${x:shell:default=v}`). The other orderings fail quietly or confusingly:

| Written | Today's behavior |
|---|---|
| `${x:shell:default=v}` | `InterpolationError` (the documented blocker) |
| `${x:default=v:shell}` | **Silent misparse** — splits on `:default=` first, so the default becomes the literal string `"v:shell"` and no quoting is applied |
| `${x?:shell}` | `shell_quote=True`, then resolves the path `"x?"` → "not found" error naming the wrong path |

So S1 is not "relax the mutual-exclusion check": it must **normalize suffix order**
and give all orderings one defined meaning, with unit tests covering all four
(`:shell` alone, both `:default=` orders, `?:shell`). Budget for that, not a
one-line edit.

**S1 must also spec what an empty/absent value emits under `:shell` — it is an
observable behavior change at existing sites.** Post-S1 rule: resolve, apply the
fallback, then `shlex.quote()` whatever string results — so an empty result emits
`''` (a valid empty token), where today the `None` branch emits nothing
(`interpolation.py:270-273`). Five of the 17 existing `:shell` sites use bare
token positions and will see the change: `outer-loop-eval.yaml:51`
(`ll-loop show ${context.input:shell}`), `refine-to-ready-issue.yaml:123`
(`[ -n ${context.input:shell} ]` — today an empty input collapses to `[ -n ]`,
which is **always true** in bash; `''` fixes that latent bug, but verify the
branch flip is intended), and the `|| echo ${context.goal:shell}` fallbacks at
`loop-router.yaml:299, 393`, `loop-composer.yaml:286`,
`loop-composer-adaptive.yaml:295`. Audit these five in the S1 commit.

**Decision — SELECTED (2026-08-27): Option S1.**
S2 does not answer class B at all (it says so itself), and S3 carves the permanent
hole in exactly the class this issue calls sharpest. S1 is the only option that
keeps the per-site remedy uniform across all 145 sites, which is what lets the
Step-2 sweep be a single rule instead of a rule plus an exemption list. It is one
function, unit-testable in isolation, no schema change.

**Options considered:**

- **Option S1 — SELECTED: make `:shell` compose.** Change `interpolate()` so
  `:shell` may be combined with `:default=` and `?` — apply the fallback first,
  then `shlex.quote()` the result — instead of raising. Small, local, directly
  unit-testable, and it is the only change that leaves the per-site remedy uniform
  across all 145 sites. It is a runner-side edit, but a far smaller one than
  Option A's `${captured.x.path}` accessor, and it does not touch the schema.
  Also fixes the `None` → bare-empty asymmetry noted in *Expected Behavior* if the
  quote is applied after the `None` branch.
- ~~**Option S2: push the default into Python.**~~ Rejected. Drop the suffix and write
  `os.environ.get("VAR") or "queue"`. Works for **class A only**. For class B,
  `:default=` guards a *missing capture* — dropping it makes the interpolation
  raise on a state that never ran, converting a graceful default into a loop
  failure. So S2 still needs a separate answer for the class-B `:default=` sites.
- ~~**Option S3: exempt these sites.**~~ Rejected. Leave `:default=`/`?` sites
  unconverted and teach the Step-2 sweep to accept them as known-unfixable.
  Cheapest, but it carves a permanent hole in exactly the class-B sites the issue
  calls sharpest.

The **Step-2 sweep's definition of "clean" depends on this** — under S1 there is no
`:default=`/`?` exemption: every class-A/B site converts, and a surviving raw one is
a failure.

### Interaction with MR-11 (existing lint)

`_find_unsafe_context_interpolations` (`scripts/little_loops/fsm/validation/shell_safety.py:163-188`)
already flags a `${context.<input|goal|description|task|prompt|query|topic>}`
that is not single-quoted, not inside a quoted heredoc, and not `:shell`-suffixed.
Consequences for this work:

- The originally-proposed `VAR="${context.goal}"` form **would have introduced
  ~23 new MR-11 WARNINGs**. No loop currently sets
  `unsafe_context_interpolation_ok`, so the corpus is clean today and must stay
  clean. The `:shell` form above is lint-clean by construction.
- Run `ll-loop validate` on each file after conversion and treat any new MR-11
  warning as a failed conversion, not as noise to suppress.
- MR-11 currently treats "inside a quoted heredoc" as unconditionally safe —
  true for bash, false once the body is re-parsed as Python. That is precisely
  the gap the Follow-up lint closes.
- **MR-11's heredoc terminator match is looser than bash's.** `shell_safety.py:180`
  closes a heredoc on `stripped == heredoc_marker`, so an *indented* line equal to
  the marker ends the tracked block — where bash requires column 0 for `<<` (only
  `<<-` relaxes it, and only for **tabs**). Any block after such a line is scoped
  wrong. Since Step 2's sweep is expected to share this heredoc tracking and Step 9
  extends it, tighten the check to column-0 (or `<<-` + leading tabs) as part of
  this work — otherwise the sweep mis-scopes blocks the same way the original
  survey's scanner did.

### Heredoc sentinel collision

Option B writes untrusted text through `cat > FILE << 'RAWEOF'`. If the LLM
output contains a line that is exactly `RAWEOF`, the heredoc terminates early and
the remainder of the payload is executed as shell. No in-repo instance
(`brainstorm.yaml`, `cua-agent-desktop.yaml`) guards against this, and Option B
multiplies the surface by ~67.

Randomizing the sentinel is not free: bash matches the closing line literally, so
the opener and closer must both carry the same token, and interpolating one
(`<< "RAW_${loop.run_id}"`) makes the heredoc *double-quoted* — which re-enables
expansion and defeats the entire mechanism. Two workable options; **pick one
during implementation and record it here**:

- **Fixed, improbable sentinel** — **SELECTED (2026-08-27).** A long fixed marker
  unlikely to appear in prose (e.g. `LL_RAW_9F3C1A7E_EOF`). Zero mechanism, keeps
  the quoted heredoc, residual risk is non-zero but negligible: a line reading
  exactly `LL_RAW_9F3C1A7E_EOF` in LLM prose is not a realistic failure. Cheapest,
  and consistent with the existing precedents.
- ~~**Sentinel plus post-read length check.**~~ Rejected: costs ~4 lines per site
  × 67 and only converts a silent truncation into a loud one — it does not prevent
  the collision, and the collision it guards is already negligible.

A randomized-per-run sentinel would require quoting the marker as
`<< 'RAW'"$SENTINEL"''` or similar contortions; it is not recommended.

### Option B canonical block (and its column-0 constraint)

Bash matches a `<<` heredoc terminator **only at column 0** (`<<-` relaxes it for
**tabs** only, which this repo's space-indented YAML block scalars cannot supply).
The `brainstorm.yaml:161-164` precedent works because its `cat >` sits at the
action body's top level. Several conversion targets do **not** — their Python is
nested inside an `if` (`recursive-refine.yaml:82-83`, `rn-build.yaml:728-729`,
`loop-composer-adaptive.yaml:744`). Writing the Option B block in place there
produces an unterminated heredoc that swallows the rest of the action.

**Rule: hoist the `cat >` heredoc to the top of the action, above any `if`/`for`,
even when the Python that reads it is nested.** The file write is unconditional
and harmless; only the read is conditional. Canonical block:

```bash
cat > "${context.run_dir}/<state>-<capture>.txt" << 'LL_RAW_9F3C1A7E_EOF'
${captured.<name>.output}
LL_RAW_9F3C1A7E_EOF
# ... any if/for wrapping goes here ...
LL_ARG_RUN_DIR=${context.run_dir:shell} python3 << 'PYEOF'
import os
run_dir = os.environ["LL_ARG_RUN_DIR"]
with open(os.path.join(run_dir, "<state>-<capture>.txt")) as f:
    value = f.read()
PYEOF
```

**The `LL_ARG_RUN_DIR=` binding is load-bearing and was missing from the first draft
of this block** — an earlier revision read `os.environ["RUN_DIR"]` without ever
setting it, which raises `KeyError` at every one of the ~67 copy-paste sites. If you
prefer to match the `brainstorm.yaml:163` precedent instead, raw-interpolate the path
(`open("${context.run_dir}/<state>-<capture>.txt")`) — that is an accepted class-C
site — but then drop the `os.environ` line. Do not ship the half-and-half form.

Three notes on the block: the heredoc appends a trailing newline the captured value
did not have (`.strip()` or `.rstrip("\n")` at the read site if the consumer is
newline-sensitive — `brainstorm.yaml` gets away with it because it strips
per-line); the filename must be unique **per capture per state**, since `>`
truncates and a re-entered state legitimately overwrites its own file — the
`<state>-<capture>.txt` naming is the enforced rule, not a suggestion, and the
Step-2 sweep should assert it; and grepping `LL_RAW_9F3C1A7E_EOF` is the canonical
way to enumerate every completed class-B conversion.

### Env-var naming: reserve an `LL_ARG_` prefix

`runners.py:305` spawns each shell action with `env=project_child_env()`, which is a
full `os.environ.copy()` (`host_runner.py:1872` — the helper deliberately provides no
way to clear an inherited key). So a binding named `GOAL=`, `TASK=`, `INPUT=`, or
`PROMPT=` silently shadows whatever the operator's environment already had under that
name, and the corpus already reuses generic names (`RUN_DIR`, `SKILL_FILE`) across
unrelated states.

**Rule: every binding introduced by this work is named `LL_ARG_<NAME>`** — e.g.
`LL_ARG_GOAL=${context.goal:shell}` read as `os.environ.get("LL_ARG_GOAL", "")`. The
Step-2 sweep asserts the prefix, which also makes the 78 class-A conversions greppable
and keeps them from colliding with the pre-existing unprefixed bindings this issue
does not touch.

### Open decision — how class B passes multi-line LLM output

Env-var binding is **not sufficient on its own** for class B. The binding
itself is a bash double-quoted string (`VAR="${captured.x.output}"`), so a `"`
in the value closes it and a `$(...)` inside it command-substitutes — the same
defect relocated from Python to bash. Multi-line values make it worse.

> **Correction (2026-08-27):** the *safety* half of this argument no longer
> holds. `${captured.x.output:shell}` shlex-quotes the value, newlines included,
> so a `:shell`-bound env var is not injectable for class B either.
>
> **Second correction (2026-08-27, eighth pass):** the ARG_MAX ground offered in
> the first correction is also wrong. The interpolated value rides inside the
> single `bash -c <action>` argv element (`runners.py:297`) under **both**
> shapes — Option B's heredoc body and a `:shell` env assignment are both text
> within that one argument — so both hit the same `ARG_MAX` ceiling at the same
> exec boundary; Option B removes only the second (bash→python3) boundary, which
> has essentially the same budget. The Option B decision stands, but on the
> Decision Rationale's grounds — shipped precedent (`brainstorm.yaml`, BUG-2468),
> uniformity across the 67 sites, no new mechanism — not on ARG_MAX. Do not
> reuse the ARG_MAX argument elsewhere.

Three options; pick one and record it:

**Option A**: Runner-side capture-to-file. Have the FSM persist each `capture:`
variable to a file under the run dir and expose its path (e.g.
`${captured.x.path}`), so shell actions read it with `open(...)`. Cleanest and
fixes the class permanently, but it is a runner change plus a schema addition,
not a per-site edit. Note captured values are already carried in the
checkpoint state (`fsm/persistence.py:332, 379`) but are not exposed as a
per-variable file a shell action can open.

**Option B**: Per-site heredoc for the value. Write the captured output to a
run-dir file in the same action via its own quoted heredoc, then read that
file from the Python heredoc. No runner change; ~27 hand-edits with a
repeated boilerplate block.

> **Selected:** Option B — Per-site heredoc for the value. Already a shipped,
> tested in-repo precedent for this exact failure mode
> (`brainstorm.yaml`'s `dedup_novelty` state, BUG-2468, done), plus a
> shell-only sibling in `cua-agent-desktop.yaml`. No runner or schema change,
> lower risk than Option A's untested runner change, and unlike Option C it
> closes the live, non-adversarial defect now instead of deferring it.

**Option C**: Scope this issue to class A and file class B separately.
Defensible given that (a) is a different kind of change, but leaves the
sharper class open.

~~**Recommended**: (a) Runner-side capture-to-file, with (b) as the fallback if
the schema addition proves contentious.~~ **Superseded by the Decision Rationale
below**, which overturned this note on fresh evidence. Retained only for
provenance. The "do not ship env-binding for class B" caution still holds, but
for the ARG_MAX/reviewability reasons in the correction above, not the injection
reason originally given.

### Decision Rationale

**Selected: Option B — Per-site heredoc for the value.**

`/ll:decide-issue` re-evaluated the issue's own "Recommend (a)" note against
fresh codebase evidence and overturned it: the issue's Codebase Research
Findings claimed "no existing in-repo pattern writes untrusted multi-line
capture output to a run-dir file for later `open()`" — that claim is false.
`brainstorm.yaml`'s `dedup_novelty` state (`scripts/little_loops/loops/brainstorm.yaml:160-169`)
already implements exactly this shape — write untrusted LLM output to a file
via a quoted shell heredoc, then `open()` it from the Python heredoc — as the
shipped, tested fix for BUG-2468 (`status: done`,
`scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting`), which is the
identical `"""`-breaks-triple-quoted-literal failure mode this issue
describes. `cua-agent-desktop.yaml:417-423` has a shell-only sibling of the
same pattern. Option B therefore generalizes an already-proven idiom rather
than inventing new mechanism, needs no FSM runner or schema change (unlike
Option A), and — unlike Option C — resolves the live, non-adversarial class-B
defect now instead of deferring it to a new issue (a defer-risk borne out by
this same split lineage's sibling, FEAT-3332, still sitting open).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — runner-side `.path` accessor | 2 | 1 | 2 | 1 | 6/12 |
| **B — per-site heredoc-to-file** | **3** | **2** | **3** | **2** | **10/12** |
| C — defer class B to a new issue | 2 | 3 | 3 | 1 | 9/12 |

Key evidence:
- `brainstorm.yaml:156-169` — shipped BUG-2468 fix, identical failure mode, identical mechanism
- `cua-agent-desktop.yaml:417-423` — shell-only sibling instance, explicit "~25% failure rate" comment on the raw-interpolation defect it replaced
- `scripts/little_loops/fsm/validation/shell_safety.py:37-41,154,178-180` (MR-11) — the regression-guard lint already tracks quoted-heredoc boundaries structurally; it needs to stop treating "safe from bash" as "safe from the re-parsed Python literal," not be built from scratch
- Known residual risk to address during implementation: static heredoc sentinels (`RAWEOF`, `PLANEOF`, etc.) are not collision-proof against LLM output that happens to contain the sentinel line verbatim — no in-repo instance uses a randomized/per-run sentinel yet. Now specified as an explicit pre-implementation choice in *Heredoc sentinel collision* above (a randomized sentinel turns out not to be workable without un-quoting the heredoc); applies across all **67** class-B sites, not the ~27 originally counted

## Integration Map

### Files to Modify

33 files hold class-A/B/C sites. Ordered by class-A+B density (the sites that
must change):

- `scripts/little_loops/loops/sft-corpus.yaml` — densest overall (38 sites), and
  9 of its 18 `-c "` sites are class B; needs the shape-0 heredoc conversion
- `scripts/little_loops/loops/loop-router.yaml` — 35 sites, both classes, both
  host shapes
- `scripts/little_loops/loops/recursive-refine.yaml` (29),
  `goal-cluster.yaml` (19), `autodev.yaml` (13),
  `loop-composer-adaptive.yaml` (13), `loop-composer.yaml` (10),
  `refine-to-ready-issue.yaml` (9), `rn-implement.yaml` (9),
  `harness-optimize.yaml`, `general-task.yaml`, `rn-plan-apo.yaml`,
  `apply-research.yaml`, `assumption-firewall.yaml`,
  `learning-tests-audit.yaml`, `migrate-sdk-version.yaml`,
  `auto-refine-and-implement.yaml`, `rn-build.yaml`, `workflow-generator.yaml`,
  `cli-anything-bootstrap.yaml`, `prompt-across-issues.yaml`
- `mechanize-skills.yaml` (13 sites, **all class C**) — no required change; the
  existing `SKILL_FILE` env-binding at `:283-286` is the shape to copy
- **Subdirectories (missed by the original survey):**
  `lib/composer.yaml`, `lib/policy-router.yaml`, `lib/rubric-router.yaml`,
  `oracles/code-run-gate.yaml`, `oracles/enumerate-and-prove.yaml`,
  `oracles/generator-evaluator.yaml`, `oracles/oracle-capture-issue.yaml`,
  `oracles/verify-confidence-scores.yaml`
- `scripts/little_loops/fsm/validation/shell_safety.py` — the MR-11 extension
  (Follow-up); this is now in-scope-adjacent rather than purely optional, since
  the sweep is what makes ~145 hand-edits verifiable. Also carries the column-0
  heredoc-terminator fix (`:180`).
- `scripts/little_loops/fsm/interpolation.py` — **required (Option S1 selected)**:
  `:242-256`, the suffix parse (mutual exclusion *and* the `${x:default=v:shell}`
  silent misparse — the guard at `:243-248` only catches the reverse order);
  `:270-273`, the `None`-before-`shlex.quote` ordering.
- ~~Under option (a): `interpolation.py` / `executor.py` / `fsm-loop-schema.json`
  for the `.path` accessor~~ — not needed; Option B was selected

### Dependent Files (Callers/Importers)

- N/A — loops are invoked by ID via the FSM runner, not imported

### Similar Patterns

- Safe idiom already in-repo: `mechanize-skills.yaml:162, 283, 511, 528`;
  `autodev.yaml:405`; `flux-image-generator.yaml:275`;
  `interactive-component-generator.yaml:529`; `openscad-model-generator.yaml:330`;
  `html-website-generator.yaml:211`
- The interpolation engine itself: `scripts/little_loops/fsm/interpolation.py`
  (`VARIABLE_PATTERN` / `InterpolationContext.resolve()`) — pure text
  substitution, no escaping hook to extend

### Tests

- `scripts/tests/test_builtin_loops.py` — behavioral cases in the established
  extract-action / `subprocess.run(["bash", "-c", action])` shape:
  - a goal containing `don't` runs `loop-router`'s `parse_project_score`
    action to exit 0 (today: `SyntaxError`);
  - a captured output containing `"""` and a newline runs the class-B action to
    exit 0;
  - a goal containing `'; import os; os.system("touch <tmp_path>/pwned") #` does
    not create the file (use pytest `tmp_path`, not a fixed `/tmp` path — fixed
    paths collide across parallel/xdist runs and leak between tests);
  - a goal containing `"; touch <tmp_path>/pwned; #` run against a converted **`-c "`**
    site (e.g. `loop-router`'s `list_loops`) does not create the file — this is
    the shell-injection half that only the `-c "` shape exhibits, and it needs
    its own case.
- A static sweep asserting no built-in loop interpolates `${context.*}` or
  `${captured.*}` inside a Python string literal — this is the regression guard,
  and the survey above is its expected-clean baseline. Requirements:
  - **glob recursively** (`loops/**/*.yaml`) so `lib/` and `oracles/` are covered;
  - handle **both host shapes** — a heredoc body delimited by its marker, and a
    `python3 -c "` body delimited by the next unescaped `"`. A line-oriented
    scanner that only tracks heredoc markers silently mis-scopes every `-c "`
    block (this is how the original ~60 count was produced);
  - treat a `:shell`-suffixed site as clean;
  - **track heredoc terminators at column 0**, not `line.strip() == marker` — see
    the MR-11 note above; an indented marker line is not a bash terminator;
  - classify per site via the *Sweep classification rule* above (`captured.*` always
    untrusted; `context.*` untrusted minus a trusted runner-key list), **not** via a
    fixed untrusted-key allowlist;
  - encode the settled decisions: under **S1** there is no `:default=`/`?`
    exemption — every class-A/B site converts; under **narrow**, a `-c "` block whose
    sites are all class C is clean (which the classifier gives for free);
  - assert the `LL_ARG_` prefix on bindings this work introduces, and the
    `<state>-<capture>.txt` filename rule on Option B writes;
  - assert **per interpolation site**, not per file — `mechanize-skills.yaml:283-286`
    is the counterexample: one converted binding on one line, a raw
    interpolation on the next, inside the same heredoc.

#### The sweep must be green on every commit — use a ratcheting baseline

"Pin the survey table as the sweep's expected-fail baseline" cannot mean a failing
test. `python -m pytest scripts/tests/` must exit 0 on `main` (see CLAUDE.md
*Testing & CI Policy*, and the self-hosted runner gates every push), while steps 4/5/6
are explicitly meant to land as separate commits — so a test red for the duration is
not landable.

Mechanism: check in a **baseline allowlist file** enumerating the known-unconverted
sites (file, line-anchor, class). The test asserts the current scan equals the
baseline — a site **not** in the baseline is a failure (no new sites), and a baseline
entry that no longer scans is also a failure (stale entry: delete it in the same
commit that converts it). Each conversion commit shrinks the baseline; the work is
done when the class-A and class-B entries are empty. This makes every phase both
green and independently verifiable, which is what step 2 is actually for.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the env-var (and
  file-passing) idiom as the required way to get external text into a
  heredoc'd Python body, alongside the MR rule table

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Existing lint precedent for the Notes "Follow-up": MR-11 (`_validate_unsafe_context_interpolation`, `scripts/little_loops/fsm/validation/shell_safety.py:191-227`) already walks `state.action` tracking heredoc state via `_QUOTED_HEREDOC_START_RE` (`shell_safety.py:41`) and flags matches of `_UNSAFE_CONTEXT_INTERP_RE` (`shell_safety.py:33-35`). It currently treats being inside a quoted heredoc (`<< 'EOF'`) as an unconditionally safe position — safe from bash's perspective — and does not distinguish that from being unsafe once the heredoc body is re-parsed as a Python string literal. The Follow-up should extend MR-11's existing heredoc-tracking rather than add a new rule from scratch.
- **But MR-11's matcher is narrower than this issue needs, in two ways.** (1) `_UNSAFE_CONTEXT_INTERP_RE` (`shell_safety.py:33-35`) matches a *fixed key allowlist* — `input|goal|description|task|prompt|query|topic` — so class-A keys outside that set are invisible to it. (2) It matches `${context.*}` **only**; there is no `${captured.*}` alternation at all, so **class B — the sharper class — is entirely outside MR-11's reach today.** Extending MR-11 therefore means widening the pattern (drop the key allowlist for the Python-literal position, add the `captured` namespace), not merely adding a heredoc-position branch. Budget for the widening to surface pre-existing findings in files this issue does not otherwise touch.
- MR-11 emits `ValidationSeverity.WARNING` (`shell_safety.py:220-226`) and is suppressible per-loop via `unsafe_context_interpolation_ok` (`:212`). **No loop in the corpus currently sets that flag** — the corpus is MR-11-clean, so any new warning introduced by this work is a regression, not ambient noise.
- The env-var idiom is not applied uniformly even within one file: `mechanize-skills.yaml:283-286` binds `SKILL_FILE` via the env-var idiom (`SKILL_FILE="${captured.current_skill.output}" python3 << 'PYEOF'` / `os.environ["SKILL_FILE"]`) but still raw-interpolates `${captured.run_dir.output}` into a Python string literal (`open("${captured.run_dir.output}/diagnosis.json")`) on the very next line inside the same heredoc. Any regression sweep must check every interpolation site per-heredoc, not treat a file as clean once one site is converted.
- ~~No existing in-repo pattern writes untrusted multi-line capture output to a run-dir file for later `open()` (relevant to Open Decision option (b)/(a)). The two existing file-handoff shapes found are: (1) an LLM self-managing its own artifact file per prose instructions in `generate_prompt`/`rubric` (e.g. `html-website-generator.yaml:67-95`), and (2) a Python heredoc opening a JSON file at a `${captured.run_dir.output}`-derived path that a prior state wrote (e.g. `mechanize-skills.yaml:286,337,370,581`) — there only the harness-controlled *path* is interpolated raw, not the untrusted file *contents*. Neither is a precedent for passing arbitrary untrusted captured text via file.~~ **FALSE — retracted 2026-08-27.** `brainstorm.yaml:160-169` does exactly this (`cat > "$RUN_DIR/round_ideas.txt" << 'RAWEOF'` / `${captured.round_ideas.output}` / `open(...)`), as the shipped BUG-2468 fix; `cua-agent-desktop.yaml:415-423` is a shell-only sibling. This bullet is what the Decision Rationale below overturned; do not plan against it.
- The `:shell` interpolation suffix (`scripts/little_loops/fsm/interpolation.py:255, 271`) `shlex.quote()`s a resolved value at substitution time and is the sanctioned fix for a bash token position — MR-11's own docstring names it (`shell_safety.py:157-160`). 17 sites in the loop corpus already use it. It is the missing half of the class-A remedy.

## Program Design

### Signatures

- No Python API change under options (b)/(c).
- Under option (a): a `${captured.<name>.path}` accessor resolving to a run-dir
  file holding that capture's raw output verbatim.
- `_run_action(self, action_template: str, state: StateConfig, ctx: InterpolationContext, on_usage: UsageCallback | None = None) -> ActionResult` (`scripts/little_loops/fsm/executor.py:2097`) — the single write site (`:2370-2391`) where a `path` key would be added to `self.captured[state.capture]` under option (a).
- `_build_context(self) -> InterpolationContext` (`scripts/little_loops/fsm/executor.py:3284`) — constructs each interpolation context with `captured=self.captured` by reference, so a `path` key added at the write site above is visible with no further plumbing.

### Call Path

`InterpolationContext.resolve()` substitutes into the raw action string ->
`bash -c` (`scripts/little_loops/fsm/runners.py:297`) -> quoted heredoc ->
`python3` parses the substituted text **as source**. The fix breaks the last
arrow: the value must arrive through `os.environ` or `open()`, never through
the parser.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- `InterpolationContext.resolve()` (`scripts/little_loops/fsm/interpolation.py:78`) and `_get_nested()` (`:119`) already generically resolve any dot-path under the `captured` namespace via plain dict traversal (`path.split(".")`, `:133`) — a `${captured.X.path}` accessor requires no change to `VARIABLE_PATTERN` (`:28`) or the `:default=`/`?`/`:shell` suffix-parsing block in `interpolate()` (`:209-274`). It resolves automatically once `self.captured["X"]["path"]` exists as a key — this is a data-population problem, not an interpolation-syntax problem.
- Capture write site: `_run_action()` (`scripts/little_loops/fsm/executor.py`, signature at line 2097) populates `self.captured[state.capture] = {"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ..., "failure_type": ..., "timeout_kind": ...}` at lines 2370-2391. A `path` key (plus the corresponding file write of `result.output`/`result.stderr` under `${context.run_dir}`) would be added at this single site.
- `_build_context()` (`executor.py:3284-3303`) constructs each `InterpolationContext` with `captured=self.captured` passed by reference. A `path` key added at the write site above is therefore visible to every subsequent state's interpolation with no additional plumbing — `_build_context` is called from multiple sites (`executor.py:3294, 3755, 3802`), all referencing the same instance dict.
- `run_dir` is available inside the executor via `self.fsm.context.get("run_dir", "")` (`executor.py:1692`, `:3031`) — the same dict backing `${context.run_dir}` — not as a dedicated attribute on the executor.
- `LoopState.captured` (`scripts/little_loops/fsm/persistence.py:332`, dataclass field) and `to_dict()` (`:379`) serialize the captured dict opaquely with no per-key shape enforcement — a new `path` key round-trips through checkpointing with no persistence-layer code change.
- `fsm-loop-schema.json:489-492` — `capture` is currently a bare `{"type": "string", "description": "Variable name to store action output"}` with no destination-path sibling key. Any new schema key for this accessor is purely additive; nothing existing to reconcile with.
- `bash -c` invocation (`scripts/little_loops/fsm/runners.py:297`, `cmd = ["bash", "-c", action]`) confirms interpolation is fully resolved into `action` (via `interpolate()` at `executor.py:2115`) before bash — and therefore python3 — ever sees the text, confirming the issue's stated Call Path.

## Implementation Steps

1. ~~Settle the class-B decision (a/b/c) above.~~ Decided: Option B — see
   Decision Rationale under Proposed Solution.
1a. ~~Settle the `:shell` / `:default=` blocker.~~ Decided: **S1 — make `:shell`
   compose**. Land the `interpolate()` change as its own first commit: normalize
   suffix order so all four orderings have one defined meaning (including the
   currently silent `${x:default=v:shell}` misparse), apply the fallback before
   `shlex.quote()`, and fix the `None`-before-quote ordering. Unit tests for every
   ordering ship in the same commit. Nothing else starts until this is on `main`.
1b. ~~Settle the `-c "` conversion scope.~~ Decided: **narrow** — the 11 files that
   contain a class-A/B site. See *Scope ambiguity in the shape-2 conversion*.
2. **Write the static sweep first**, with the ratcheting baseline file described in
   Tests (the sweep is green from commit one; the baseline shrinks per phase).
   Building the detector before the edits is what turns ~145 hand-edits from hopeful
   into verifiable, and it is the only way to know the conversion is complete. It
   must handle both host shapes, glob recursively, and classify per site (see Tests).
3. ~~Pick the sentinel strategy.~~ Decided: fixed-improbable
   (`LL_RAW_9F3C1A7E_EOF`) — see *Heredoc sentinel collision*.
4. Convert the `python3 -c "…"` sites to quoted heredocs — **11 files under the
   narrow reading, 29 files / 114 invocations under the broad one (step 1b)** —
   running `ll-loop validate` on each. Behavior-neutral by itself; do it as its own
   commit so the diff is reviewable.
5. Convert the 78 class-A sites to `LL_ARG_X=${context.x:shell}` + `os.environ`, loop
   by loop, `ll-loop validate` each. Any new MR-11 warning means the conversion
   is wrong — do not set `unsafe_context_interpolation_ok`. Note the FSM interpolates
   the **whole** action string, comments included
   (`reference_fsm_action_interpolated_before_bash`): a comment near the site that
   quotes `${context.goal}` interpolates too, so convert or escape (`$${`) it in the
   same edit.
6. Convert the 67 class-B sites via Option B (per-site heredoc-to-file), using the
   canonical block above — hoisting each `cat >` heredoc above any enclosing
   `if`/`for` so its terminator lands at column 0.
7. Leave the 131 class-C sites alone except where already editing the state.
8. Add the behavioral tests; confirm the sweep from step 2 now passes clean.
9. Extend MR-11 (widen the pattern to drop the key allowlist and add the
   `captured` namespace; distinguish "inside a quoted heredoc" from "inside a
   Python literal within one") so new sites cannot be introduced.
10. Document the idiom in `HARNESS_OPTIMIZATION_GUIDE.md`.

## Acceptance Criteria

1. `${x:default=v:shell}`, `${x:shell:default=v}`, `${x?:shell}`, and `${x:shell}`
   each have one defined, unit-tested meaning; no ordering silently misparses. An
   empty/absent value under `:shell` emits `''` (quoted empty token), and the five
   existing bare-token `:shell` sites are audited for the resulting behavior
   change (see the S1 BLOCKER section).
2. The static sweep exists, globs `loops/**/*.yaml` recursively, handles both host
   shapes, classifies per site, and asserts equality against a checked-in baseline
   file. It is green on `main` at every commit of this work.
3. The baseline's class-A and class-B entries are **empty** at completion; class-C
   entries may remain.
4. `ll-loop validate` is clean on all 33 touched files, with **no** new MR-11
   warnings and **no** loop setting `unsafe_context_interpolation_ok`.
5. Every binding this work introduces is named `LL_ARG_*`; every Option B write uses
   the `LL_RAW_9F3C1A7E_EOF` sentinel and a `<state>-<capture>.txt` filename.
6. The four behavioral tests in *Tests* pass (apostrophe goal, `"""` capture, Python
   injection, shell injection at a converted `-c "` site).
7. MR-11 is widened (no key allowlist, `captured` namespace included, column-0
   heredoc terminator) and the guide documents the two idioms.

## Impact

- **Sizing / split**: this is EPIC-shaped, not a single issue — 145 site edits plus a
  runner change, a new lint, a widened lint, and docs. The phases are already
  independently landable and independently gated by the step-2 baseline; the natural
  children are **1a** (`interpolation.py` suffix composition + tests), **2** (sweep +
  baseline), **4** (`-c "` → heredoc, 11 files), **5** (78 class-A), **6** (67
  class-B), **9+10** (MR-11 widening + guide). Run `/ll:scope-epic` before starting if
  this will not be finished in one session; the ordering constraint is 1a → 2 → 4 →
  {5, 6} → 9.
- **Priority**: P2 — an ordinary apostrophe in a goal breaks `loop-router` and
  `loop-composer` today, and class B fails non-deterministically on ordinary
  model output. The injection path is real but mostly self-inflicted (operator
  input), which is what keeps this off P1.
- **Effort**: Large (revised up from Medium on the 2026-08-27 recount) — **145
  required site edits across 33 loop files** (78 class A + 67 class B), of which
  53 need a prior `python3 -c "…"` → heredoc conversion, plus the class-B
  boilerplate block ×67, plus the static sweep, the behavioral tests, and the
  MR-11 widening. The original "~50 edits across 10 files" understated this by
  roughly 3×. Splitting by phase (steps 4 / 5 / 6 above) is advisable — each is
  independently landable and independently verifiable by the step-2 sweep.
- **Risk**: Medium — each edit is local and `ll-loop validate`-checkable, but the
  sites are numerous and a missed one is invisible until it fires. Four specific
  hazards: (1) the `-c "` → heredoc conversion is the only step that changes
  shell structure rather than a token, so it is the one that can break a working
  loop — and its volume is 11 files or 29 depending on step 1b; (2) the MR-11
  widening will surface pre-existing findings in files this issue does not
  otherwise touch, which must be triaged rather than suppressed; (3) the
  `:shell`/`:default=` blocker turns a mechanical suffix edit into a runtime
  `InterpolationError` at 130 candidate sites unless step 1a lands first; (4) an
  Option B block left inside an `if` yields an unterminated heredoc that silently
  swallows the rest of the action.
  The static regression sweep, written first, is what makes the sweep verifiable
  rather than hopeful.
- **Breaking Change**: No — all edits are internal to loop action bodies.

## Notes

Split from BUG-3327's "Site classification" section, class (2), per the
decision recorded there on 2026-08-26. BUG-3327 is now class-(1)-only
(prompt fencing) and links here.

Sequencing: independent of BUG-3326 and FEAT-3328. Can land in parallel;
nothing in the `workflow-generator` chain touches these files.

**Follow-up (promoted to Implementation Step 9):** a `fsm/validation` rule
flagging any `${context.*}` / `${captured.*}` interpolation that lands inside a
quote character in a `python3` heredoc **or `-c "…"`** body. Same
import-don't-restate spirit as FEAT-3328's gate-completeness rule, same
regex-over-raw-action-string shape — but extend MR-11 rather than adding a rule,
and widen its matcher (see Codebase Research Findings): today it matches a fixed
seven-key `${context.*}` allowlist and has no `captured` alternation at all.

**Eighth review pass — 2026-08-27** (pre-implementation; verified against the code):
- **Re-verified the seventh pass's load-bearing claims directly**: the
  `${x:default=v:shell}` silent misparse and `${x?:shell}` bogus-path resolution
  (`interpolation.py:242-256`), the `None`-before-`shlex.quote` ordering
  (`:270-273`), MR-11's indented-terminator looseness (`shell_safety.py:173`),
  the 114-invocation / 29-file `-c "` count, and the `brainstorm.yaml:160-169`
  precedent. All hold.
- **Enumerated the trusted `context.*` key list** the sweep classification rule
  referenced but never specified — a blocker input to Steps 2 and 9. The runner
  writes only `run_dir`, `promoted_artifact`, and underscore-internal keys;
  `${loop.*}` is trusted. Recorded in the rule.
- **Spec'd S1's empty-value emission** (`''` after fallback, quote applied last)
  and identified the five existing bare-token `:shell` sites whose behavior it
  changes — including `refine-to-ready-issue.yaml:123`, where today's collapse
  to `[ -n ]` is always-true (a latent bug S1 incidentally fixes). Added to
  AC-1.
- **Retracted the first correction's ARG_MAX ground for Option B** — the value
  rides inside the single `bash -c` argv element under both shapes
  (`runners.py:297`), so the ceiling is identical. Option B stands on the
  Decision Rationale's precedent/uniformity grounds.
- Corrected the `:shell` site count (17, not 18) and pointed the behavioral
  injection tests at pytest `tmp_path` instead of fixed `/tmp` paths.

**Seventh review pass — 2026-08-27** (verified against the code):
- **Both open decisions settled; `decision_needed` → false.** S1 (make `:shell`
  compose) and narrow (`-c "` scope). Rationale recorded inline at each.
- **S1 is bigger than "relax the mutual-exclusion check".** The guard at
  `interpolation.py:243-248` only catches `${x:shell:default=v}`; the reverse order
  `${x:default=v:shell}` **silently misparses** into the literal default `"v:shell"`
  with no quoting, and `${x?:shell}` resolves the bogus path `"x?"`. S1 must
  normalize suffix order and test all four forms.
- **The Option B canonical block was broken** — it read `os.environ["RUN_DIR"]`
  without ever binding it, i.e. a `KeyError` at all ~67 copy-paste sites. Fixed;
  the alternative raw-path form (matching `brainstorm.yaml:163`) is spelled out.
- **Env-var names need the `LL_ARG_` prefix.** `runners.py:305` passes
  `project_child_env()` = full `os.environ.copy()` (`host_runner.py:1872`), so an
  unprefixed `GOAL=`/`TASK=` shadows an inherited value, and the corpus already
  reuses generic names across states.
- **The sweep needs a stated classification rule**, or it reproduces the very
  allowlist this issue faults MR-11 for. Added: `captured.*` always untrusted,
  `context.*` untrusted minus a trusted runner-key list (new keys untrusted by
  default).
- **"Expected-fail baseline" conflicted with the CI policy** (`pytest` must exit 0
  on `main`, phases land as separate commits). Replaced with a ratcheting
  baseline-file equality assertion that is green at every commit.
- Added an **Acceptance Criteria** section and an **EPIC split recommendation**.
- Noted that the FSM interpolates comments too, so comments quoting a converted
  placeholder must be converted or `$${`-escaped in the same edit.

**Sixth review pass — 2026-08-27** (verified against the code; see the sections
above for detail):
- **BLOCKER added:** `:shell` is mutually exclusive with `:default=` and `?`
  (`interpolation.py:242-256`), so the class-A/B remedy is unimplementable at the
  130 sites carrying those suffixes — including class-B targets
  `loop-router.yaml:522-523` and `loop-composer-adaptive.yaml:744, 750`. New
  open decision S1/S2/S3; `decision_needed` flipped to `true`.
- `:shell` returns a bare `""` (not `''`) for a `None` value, so the remedy is
  sound only in the `VAR=…` assignment-prefix position.
- The `-c "` figure "53 sites, 11 files" counts sites; the *invocations* are 114
  across 29 files. Narrow-vs-broad scope is now an explicit step-1b decision.
- Option B needs a column-0 heredoc terminator; several targets nest their Python
  inside an `if`. Canonical block + hoisting rule added.
- MR-11 closes heredocs on `line.strip() == marker` (`shell_safety.py:180`),
  looser than bash; fix while extending it, since the sweep shares the tracking.
- Sentinel strategy decided: fixed-improbable `LL_RAW_9F3C1A7E_EOF`.

**Also corrected on 2026-08-27** (see the sections above for detail):
- The class-A remedy is `VAR=${context.x:shell}`, not `VAR="${context.x}"`. The
  latter relocates the defect into bash and trips MR-11.
- `python3 -c "…"` is a second host shape (53 sites) the original survey did not
  distinguish; there the defect is a shell injection too.
- The survey's glob was non-recursive and missed `lib/` + `oracles/` (28 sites).
- Site counts recounted: 78 / 67 / 131 (A / B / C) across 33 files, vs. the
  original ~23 / 27 / ~10.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:decide-issue` - 2026-08-27T03:02:59 - `4a4c9942-5c58-4b71-851d-896694066b21.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:45:46 - `091f85a6-5523-4888-8bc0-8e7acb268aae.jsonl`
