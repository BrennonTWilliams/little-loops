---
id: BUG-3340
type: BUG
title: Convert class-A scalar interpolations to :shell env-var binding
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocked_by: [ENH-3337, ENH-3338, BUG-3339]
blocks: [BUG-3341]
---

# BUG-3340: Convert class-A scalar interpolations to :shell env-var binding

## Summary

Convert every **class-A** site — a user- or config-supplied scalar
(`${context.<key>}`, key outside the trusted runner set) interpolated into a
Python string literal inside a shell action — to the env-var idiom:

```bash
LL_ARG_GOAL=${context.goal:shell} python3 << 'PYEOF'
import os
goal = os.environ.get("LL_ARG_GOAL", "")
PYEOF
```

No surrounding double quotes — `:shell` shlex-quotes the value itself. The
authoritative site list is ENH-3338's baseline class-A entries; the survey's
provisional figure was 78 (55 heredoc + 23 `-c "`).

## Current Behavior

`InterpolationContext.resolve()` substitutes the value into the raw action text
before `bash -c <action>` runs (`scripts/little_loops/fsm/interpolation.py`,
`fsm/runners.py:297`), and the substituted text is then parsed **as Python
source**. A class-A value lands inside a Python string literal, so:

- an apostrophe closes the literal — a goal containing `don't` raises
  `SyntaxError` and the state dies. This is the live, non-adversarial defect: it
  needs no attacker, only ordinary English.
- a `'; import os; …` payload executes as Python with the run's privileges.

Representative sites: `loop-router.yaml:34, 53, 192, 252, 345`;
`loop-composer.yaml:231`; `goal-cluster.yaml:347, 389`;
`apply-research.yaml:216, 217`. (`loop-router.yaml:34` and `:53` are `-c "`
sites, converted to heredocs by BUG-3339 first.)

The safe idiom already exists in the corpus — `mechanize-skills.yaml:162, 283,
511, 528`; `autodev.yaml:405`; `flux-image-generator.yaml:275`;
`interactive-component-generator.yaml:529`;
`openscad-model-generator.yaml:330`; `html-website-generator.yaml:211` — it is
simply not applied uniformly. 17 `:shell` sites exist against 78 class-A sites
that need one.

## Expected Behavior

Every class-A value reaches the Python body through `os.environ`, never through
the parser. After conversion, an apostrophe, a quote, a `$(...)`, or a Python
injection payload in a user-supplied context value is inert: `shlex.quote()`
makes it one bash token, and `os.environ.get()` hands Python a `str` it never
parses.

ENH-3338's baseline holds **zero class-A entries** when this issue closes.

## Steps to Reproduce

1. `ll-loop run loop-router --context goal="don't overfit the router"`
2. `InterpolationContext.resolve()` substitutes the raw value into the action
   text before bash runs (`scripts/little_loops/fsm/interpolation.py`,
   `fsm/runners.py:297`).
3. The `parse_project_score` state's Python body receives
   `goal = 'don't overfit the router'` — the apostrophe closes the literal.
4. Observe: `SyntaxError`, the state dies, the loop routes to `on_error`. No
   attacker, no special characters beyond ordinary English.

For the injection variant, substitute
`--context goal="'; import os; os.system('touch \$TMPDIR/pwned') #"` and observe
the file is created.

## Motivation

This is the availability half of EPIC-3336 — the class users hit by accident.
Class B (BUG-3341) is the sharper security class, but class A is the one
breaking loops today on ordinary input.

## Conventions in force

Inherited from EPIC-3336's settled decisions; do not re-litigate:

- **Every binding is named `LL_ARG_<NAME>`.** `runners.py:305` spawns each shell
  action with `env=project_child_env()`, a full `os.environ.copy()`
  (`host_runner.py:1872`, which deliberately provides no way to clear an
  inherited key). A binding named `GOAL=`, `TASK=`, `INPUT=`, or `PROMPT=`
  silently shadows whatever the operator's environment already had under that
  name, and the corpus already reuses generic names (`RUN_DIR`, `SKILL_FILE`)
  across unrelated states. The prefix also makes the conversions greppable and
  keeps them from colliding with pre-existing unprefixed bindings this issue does
  not touch.
- **No surrounding double quotes.** `LL_ARG_GOAL="${context.goal:shell}"` is
  wrong — `:shell` already quotes, and the extra quotes re-expose the value to
  bash. Write `LL_ARG_GOAL=${context.goal:shell}`.
- **Read with `os.environ.get("LL_ARG_X", "")`**, not `os.environ["LL_ARG_X"]`,
  where the site tolerates absence. A bare `[]` on an unset binding raises
  `KeyError` at runtime.
- **Composed suffixes are available** — ENH-3337 lands first, so
  `${context.x:default=v:shell}` and `${context.x?:shell}` are legal and quoted.
  There is no `:default=`/`?` exemption: those ~130 sites convert like any other.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **The `LL_ARG_` naming prefix has zero shipped occurrences anywhere in the codebase.** A repo-wide search (including scoped to `scripts/little_loops/loops/`) finds it only in `.issues/*.md` prose (EPIC-3336, BUG-3331, BUG-3340, BUG-3341, ENH-3338, ENH-3342). This issue's own six cited "safe idiom already exists in the corpus" precedent sites (`mechanize-skills.yaml:162,283,511,528`, `autodev.yaml:405`, plus the four `export ABS_DIR`-style sites `flux-image-generator.yaml:271-275`, `interactive-component-generator.yaml:526-529`, `openscad-model-generator.yaml:327-330`, `html-website-generator.yaml:208-211`) all use unprefixed generic names (`RUN_DIR`, `SKILL_FILE`, `ISSUE_FILE`, `ABS_DIR`, `VISION_THRESHOLD`) — precisely the collision risk this section's text already warns about. `LL_ARG_` is a naming rule this issue introduces going forward; no existing site needs renaming to match it, since none currently does.
- A second, `LL_`-prefixed-but-not-`LL_ARG_` shape already exists in the corpus: `LL_EPIC_BRANCH`/`LL_RUN_DIR` (`auto-refine-and-implement.yaml:756,783`, `rn-refine.yaml:663,668,722,727`) and `LL_PROPOSAL_OUT`/`LL_REVIEW_OUT` (`loop-router.yaml:512-513`, shipped by BUG-3349/done, binding two `${captured.*}` class-B values — outside this issue's class-A scope). None of the three `LL_`-prefixed naming shapes found agree with each other.
- `loop-router.yaml:512-513` is the only site in the corpus using the composed `:shell:default=` suffix today (confirmed via repo-wide search — no hits for the reverse ordering `:default=...:shell` or for `?:shell` in any loop YAML). This issue will be the first to apply that suffix broadly once conversions begin.

## Integration Map

### Files to Modify

The authoritative list is ENH-3338's baseline, filtered to `class == "A"`. From
the provisional survey, ordered by class-A+B density:

- `scripts/little_loops/loops/sft-corpus.yaml`, `loop-router.yaml`,
  `recursive-refine.yaml`, `goal-cluster.yaml`, `autodev.yaml`,
  `loop-composer-adaptive.yaml`, `loop-composer.yaml`,
  `refine-to-ready-issue.yaml`, `rn-implement.yaml`, `harness-optimize.yaml`,
  `general-task.yaml`, `rn-plan-apo.yaml`, `apply-research.yaml`,
  `assumption-firewall.yaml`, `learning-tests-audit.yaml`,
  `migrate-sdk-version.yaml`, `auto-refine-and-implement.yaml`,
  `rn-build.yaml`, `workflow-generator.yaml`, `cli-anything-bootstrap.yaml`,
  `prompt-across-issues.yaml`
- Subdirectories: `lib/composer.yaml`, `lib/policy-router.yaml`,
  `lib/rubric-router.yaml`, `oracles/code-run-gate.yaml`,
  `oracles/enumerate-and-prove.yaml`, `oracles/generator-evaluator.yaml`,
  `oracles/oracle-capture-issue.yaml`, `oracles/verify-confidence-scores.yaml`
- `mechanize-skills.yaml` — **no class-A sites** (all 13 are class C). Its
  `SKILL_FILE` binding at `:283-286` is the shape to copy, and the raw
  `${captured.run_dir.output}` on the next line is why the sweep asserts per
  site.
- `scripts/tests/data/loop_interpolation_baseline.json` (new) — created by ENH-3338 — shrink the class-A entries in the same commit that converts them.

**File contention:** BUG-3339 and BUG-3341 edit many of these same files.
Run strictly after BUG-3339 and before BUG-3341; do not dispatch to a parallel
epic branch.

### Dependent Files (Callers/Importers)

- N/A — loops are invoked by ID via the FSM runner, not imported.

### Tests

- `scripts/tests/test_builtin_loops.py` — ENH-3338's baseline-equality test must
  stay green at every commit, with the baseline shrinking as sites convert. The
  behavioral apostrophe/injection cases are ENH-3347.
- `scripts/tests/test_loops_sft_corpus.py`, `scripts/tests/test_autodev_loop.py`
  — file-specific coverage for the two densest files that have it.
- `ll-loop validate` is the applicable check for files without a dedicated test
  module.

### Documentation

- N/A here — the idiom is documented by ENH-3342.

### Configuration

- N/A

## Program Design

### Signatures

No Python API change. This is a per-site edit inside loop YAML action strings.
Two functions determine whether a converted site reads as correct, and neither is
modified here:

- `interpolate(template, ctx)`
  (`scripts/little_loops/fsm/interpolation.py:209`) — supplies `:shell`'s
  `shlex.quote()`, composed per ENH-3337.
- `_find_unsafe_context_interpolations(fsm)`
  (`scripts/little_loops/fsm/validation/shell_safety.py:148`) — MR-11, whose
  `:shell` recognition (fixed by ENH-3337) is what keeps a converted site
  lint-clean.

### Call Path

Before: `resolve()` substitutes → `bash -c` → quoted heredoc → **`python3` parses
the substituted text as source**.

After: `resolve()` substitutes a `shlex.quote()`d token into a bash env-binding
position → `bash -c` sets the variable → the heredoc body is passed to `python3`
verbatim and contains no interpolation → Python reads the value from
`os.environ` as a `str` it never parses. The last arrow — the one this epic
exists to break — is gone.

### Decision Rules

Per class-A site:

1. Choose the binding name: `LL_ARG_` + the context key upper-cased
   (`context.goal` → `LL_ARG_GOAL`). Where two different keys in one state would
   collide after upper-casing, disambiguate by appending the state's role, and
   record it.
2. Hoist the binding to the `python3` invocation line. A binding must not land
   inside the heredoc body.
3. Replace the interpolation with a read of the binding, **typed to match the
   position it sits in** — see "Non-string Python positions" below. In a string
   literal that is `os.environ.get("LL_ARG_X", "")`; it is not that everywhere.
4. Preserve any `:default=` / `?` semantics on the interpolation itself — do not
   move the default into Python. Option S2 (push the default into Python) was
   considered and rejected at the epic level: it works for class A but leaves
   class B without an answer, and a split remedy defeats the single-rule sweep.

### Non-string Python positions — the transform is not uniform

**Not every class-A site sits inside a string literal.** `os.environ.get()`
returns `str`, so the standard transform silently converts a working numeric
comparison into a `TypeError`. Confirmed sites, all comparisons against a bare
interpolated number:

| Site | Today | Wrong | Right |
|---|---|---|---|
| `autodev.yaml:1821` | `readiness_ok = conf >= ${context.readiness_threshold}` | `conf >= os.environ.get("LL_ARG_READINESS_THRESHOLD", "")` → `TypeError` | `conf >= int(os.environ["LL_ARG_READINESS_THRESHOLD"])` |
| `autodev.yaml:1822`, `2053-2054` | same shape, `outcome_threshold` | | |
| `autodev.yaml:1633` | `and int(cur) < ${context.readiness_threshold} and not attempted` | | |
| `autodev.yaml:1742` | `sys.exit(0 if int(d.get('confidence') or 0) >= ${context.readiness_threshold} else 1)` | | |
| `oracles/code-run-gate.yaml:438` | `${context.min_pass_rate}` in an `if ! python3 -c` condition | | `float(...)` — it is a rate, not an int |

Rule: **classify each site by its Python position before transforming.**

- **string literal** → `os.environ.get("LL_ARG_X", "")`
- **numeric / boolean / expression position** → `int(...)` / `float(...)` around
  `os.environ["LL_ARG_X"]`. Use the bracket form here, not `.get(..., "")` —
  `int("")` raises anyway, so an explicit `KeyError` on an unset binding is the
  better failure. Where the site carries a `:default=`, keep the default on the
  interpolation (Decision Rule 4) so the binding is always set.
- **f-string / interpolated-into-a-larger-string position** → treat as a string
  literal, but verify the surrounding format still produces the same text.

Note `min_pass_rate` is a `float`, and the `autodev.yaml` thresholds are `int`.
Do not blanket-apply one coercion.

### `:shell` inside the heredoc is not the fix

The remedy is a binding on the `python3` invocation line. Writing
`goal = '${context.goal:shell}'` **inside** the Python body looks like a
conversion and is not one — bash does no processing inside a quoted heredoc, so
`shlex.quote()`'s output reaches the Python parser verbatim:

```
shlex.quote("don't")  ->  '\'don\'"\'"\'t\''
goal = ''don'"'"'t''  ->  SyntaxError: unterminated string literal
```

ENH-3338's sweep reports this shape with `misapplied_remedy: true` rather than
clearing it, so a conversion that makes this mistake fails the baseline test
instead of shipping green.

### Sites needing more than the standard transform

- **Multiple class-A sites in one heredoc** — one binding per distinct key,
  all hoisted to the same invocation line. Do not emit one binding and leave a
  sibling raw; that is the `mechanize-skills.yaml:283-286` failure shape.
- **A site inside an `if`/`for`** — the binding attaches to the `python3` line,
  which may itself be nested. That is fine for env bindings (unlike BUG-3341's
  heredocs, which need column-0 hoisting).
- **A site in a comment.** The FSM interpolates the **whole** action string,
  comments included (`reference_fsm_action_interpolated_before_bash`). A comment
  near a converted site that quotes `${context.goal}` interpolates too — convert
  or `$${`-escape it in the same edit.
- **`sft-corpus.yaml`** carries the highest density (38 sites total). Convert it
  as its own commit so the diff stays reviewable.

## Implementation Steps

1. Filter ENH-3338's baseline to `class == "A"`; that is the work list. Reconcile
   any divergence from the survey's 78 and note it in EPIC-3336.
2. Convert loop by loop, one commit per file (or per small group), running
   `ll-loop validate` on each.
3. Shrink the baseline's class-A entries in the **same commit** as each
   conversion — a stale entry is a test failure by design.
4. Treat any new MR-11 warning as a failed conversion. **Do not set
   `unsafe_context_interpolation_ok`** on any loop; no loop in the corpus sets it
   today and that property is a success metric.
5. Sweep each converted action for comments quoting a converted token; convert or
   `$${`-escape them in the same edit.
6. `python -m pytest scripts/tests/` exits 0 at every commit.

## Acceptance Criteria

1. ENH-3338's baseline has **zero** class-A entries.
2. Every binding introduced is named `LL_ARG_*`, written without surrounding
   double quotes, and read via `os.environ.get(..., "")` where absence is
   tolerable. `grep -rn "LL_ARG_" scripts/little_loops/loops/` enumerates the
   conversions.
3. `ll-loop validate` is clean on every touched file — **no** new MR-11
   warnings, and **no** loop sets `unsafe_context_interpolation_ok`.
4. `python -m pytest scripts/tests/` exits 0 at every commit of this issue, not
   only the last.
5. No class-A site is left partially converted (one binding hoisted, a sibling
   interpolation still raw in the same heredoc) — enforced by ENH-3338's per-site
   assertion.
6. Sites carrying `:default=` or `?` are converted like any other, using the
   composed suffix from ENH-3337 — none is exempted.
7. No behavior change to any Python body's logic; only how the value arrives
   changes.
8. Every site in a **non-string Python position** keeps its type: the six sites
   named in Program Design → Non-string Python positions
   (`autodev.yaml:1633, 1742, 1821, 1822, 2053, 2054`;
   `oracles/code-run-gate.yaml:438`) are converted with an explicit
   `int(...)`/`float(...)` coercion and their comparisons still evaluate
   identically. Verified by running the affected states, not by inspection —
   a `str`/`int` comparison raises at runtime and is invisible to
   `ll-loop validate`.
9. No conversion writes `:shell` inside a Python body; ENH-3338's baseline
   reports zero `misapplied_remedy` sites.

## Impact

- **Priority**: P2 — inherited from EPIC-3336. Live availability defect on
  ordinary input, plus a self-inflicted injection surface.
- **Effort**: Medium — ~78 mechanical per-site edits across ~28 files. Individually
  trivial; the volume and the discipline of shrinking the baseline in lockstep
  are the cost.
- **Risk**: Low–Medium — lower than BUG-3339 because nothing about the shell
  *structure* changes, only a token and a binding. Two realistic failures: a
  partial conversion (ENH-3338 catches it) and a **non-string position converted
  to a `str`** (`conf >= "85"` → `TypeError`), which neither the baseline nor
  `ll-loop validate` can see — only running the state does. AC 8 exists for that.
- **Breaking Change**: No — internal to loop action bodies.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-08-28T03:15:15 - `21c2bc4e-6e06-47c6-a164-ddb166a7cfff.jsonl`
- `/ll:format-issue` - 2026-08-28T03:03:20 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
