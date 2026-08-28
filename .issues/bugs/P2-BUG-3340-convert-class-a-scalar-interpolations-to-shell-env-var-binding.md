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
blocked_by:
- ENH-3337
- ENH-3338
- BUG-3339
blocks:
- BUG-3341
confidence_score: 100
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Correction to the prior pass's "LL_ARG_ has zero shipped occurrences" claim — it is now stale.** BUG-3339's structural carve-out shipped exactly this convention at four `autodev.yaml` states (`check_reconcile_needed` at `:1624-1638`, `check_readiness_for_atomic_remediation` at `:1748-1752`, and the outcome-threshold sites at `:1828-1838`/`:2066-2075`) and `oracles/code-run-gate.yaml`'s `aggregate_gate` state (`:438-439`). Confirmed against the current baseline: `oracles/code-run-gate.yaml` has **zero** remaining class-A entries and `autodev.yaml` has only 4, all class B/C — both files are effectively complete for this issue already; per Implementation Step 1, verify rather than re-convert them.
- These four confirmed sites use a **two-step hoist**, not the single-line inline form shown in this issue's own Summary example: `VAR=${context.x:shell}` on its own line, then `LL_ARG_VAR="$VAR"` (quoting the already-`shlex.quote()`d shell variable, not the raw interpolation token) on the `python3` invocation line, alongside other `LL_*`-prefixed bindings for class-B/captured values on the same line. Both the single-line inline form and this two-step hoist form clear MR-11 — `_find_unsafe_context_interpolations()` recognizes `:shell` anywhere in the suffix chain (confirmed at `shell_safety.py:149`). Pick per site based on whether other bindings already share the invocation line.
- Numeric positions at these confirmed sites read via `int(os.environ['LL_ARG_X'])` / `float(os.environ['LL_ARG_X'])`, bracket form — matching this issue's own Program Design → Non-string Python positions rule exactly.
- The six sites this issue's Current Behavior section cites as "the safe idiom already exists in the corpus" (`mechanize-skills.yaml`, `autodev.yaml:405`, `flux-image-generator.yaml`, `interactive-component-generator.yaml`, `openscad-model-generator.yaml`, `html-website-generator.yaml`) are unprefixed env-var bindings for class-B/C (trusted/captured) values with **no `:shell` suffix** — none binds a `:shell`-quoted class-A scalar. The closest, `flux-image-generator.yaml:272`'s `export VISION_THRESHOLD="${context.pass_threshold}"`, touches a class-A-shaped key but is unquoted and sits on an `export` line outside `interp_sweep`'s scanned scope (not inside a heredoc/`-c` body), so it is not a baseline entry either way. The only real `:shell`+class-A precedent in the corpus today is the `autodev.yaml`/`code-run-gate.yaml` sites above, which post-date these six.
- ENH-3338's baseline currently holds **67** `class: A` entries (`grep -c '"class": "A"' scripts/tests/data/loop_interpolation_baseline.json`), not the survey's provisional 78 — this reconciles Implementation Step 1's instruction to "reconcile any divergence from the survey's 78 and note it in EPIC-3336" (EPIC-3336 itself is outside this single-issue refine's edit scope).

## Integration Map

### Files to Modify

The authoritative list is ENH-3338's baseline, filtered to `class == "A"`.
Current baseline state (verified 2026-08-28, 67 class-A entries across 21
files, entry count in parentheses):

- `scripts/little_loops/loops/sft-corpus.yaml` (18), `loop-router.yaml` (7),
  `recursive-refine.yaml` (6), `auto-refine-and-implement.yaml` (5),
  `refine-to-ready-issue.yaml` (5), `goal-cluster.yaml` (3),
  `apply-research.yaml` (2), `rlhf-svg-evaluate.yaml` (2),
  `rn-implement.yaml` (2), `brainstorm.yaml` (1), `loop-composer.yaml` (1),
  `loop-composer-adaptive.yaml` (1), `migrate-sdk-version.yaml` (1),
  `rn-plan-apo.yaml` (1), `rn-remediate.yaml` (1)
- Subdirectories: `lib/composer.yaml` (3), `lib/rubric-router.yaml` (2),
  `oracles/enumerate-and-prove.yaml` (2),
  `oracles/verify-confidence-scores.yaml` (2), `lib/policy-router.yaml` (1),
  `oracles/oracle-capture-issue.yaml` (1)
- **Zero class-A entries remain** in files the provisional survey listed:
  `autodev.yaml`, `harness-optimize.yaml`, `general-task.yaml`,
  `assumption-firewall.yaml`, `learning-tests-audit.yaml`, `rn-build.yaml`,
  `workflow-generator.yaml`, `cli-anything-bootstrap.yaml`,
  `prompt-across-issues.yaml`, `oracles/code-run-gate.yaml`,
  `oracles/generator-evaluator.yaml`. Do not do per-file passes on these; the
  `autodev.yaml`/`code-run-gate.yaml` conversions landed via BUG-3339 and are
  verify-only per Implementation Step 1.
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- `test_autodev_loop.py`'s `_extract_python_script()`/`_run_reconcile_predicate()` (`scripts/tests/test_autodev_loop.py:39-91`) is the established pattern for behaviorally verifying a converted state per AC 8: load the real YAML, pull the `python3 << 'PYEOF'` heredoc body out textually, run it as a `subprocess` seeding `env=` with the `LL_ARG_*` values the FSM's `:shell` binding would produce at runtime (e.g. `"LL_ARG_READINESS_THRESHOLD": "85"`), then assert the exit code/behavior. This is the pattern to extend per-site for AC 8's non-string-position sites, since `ll-loop validate` cannot catch a `str`/`int` comparison `TypeError` — only running the state can.
- `scripts/tests/test_interp_sweep.py::TestScanActionHeredoc` already carries a fixture exercising the exact target shape as "correctly converted, not a site": `LL_ARG_X=${context.x:shell} python3 << 'PYEOF'` — a scan-correctness reference distinct from the baseline-equality test in `test_builtin_loops.py`.

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
comparison into a `TypeError`. The reference example of the failure shape and
its fix (these specific sites were converted by BUG-3339 and are verify-only
now — see below):

| Site | Today | Wrong | Right |
|---|---|---|---|
| `autodev.yaml:1821` | `readiness_ok = conf >= ${context.readiness_threshold}` | `conf >= os.environ.get("LL_ARG_READINESS_THRESHOLD", "")` → `TypeError` | `conf >= int(os.environ["LL_ARG_READINESS_THRESHOLD"])` |
| `autodev.yaml:1822`, `2053-2054` | same shape, `outcome_threshold` | | |
| `autodev.yaml:1633` | `and int(cur) < ${context.readiness_threshold} and not attempted` | | |
| `autodev.yaml:1742` | `sys.exit(0 if int(d.get('confidence') or 0) >= ${context.readiness_threshold} else 1)` | | |
| `oracles/code-run-gate.yaml:438` | `${context.min_pass_rate}` in an `if ! python3 -c` condition | | `float(...)` — it is a rate, not an int |

**Type-classification is not a 6-site concern — roughly half the remaining 67
sites carry numeric- or boolean-shaped keys** (verified against the baseline
2026-08-28). Files with numeric-comparison positions to classify:
`recursive-refine.yaml` (`readiness_threshold`/`outcome_threshold` ×4,
`max_depth`, `max_refine_count`), `refine-to-ready-issue.yaml` (×5),
`lib/rubric-router.yaml` (`threshold_high`/`threshold_medium`),
`lib/composer.yaml` (`max_plan_nodes`), `sft-corpus.yaml`
(`min_tokens`/`max_tokens`, `test_ratio`/`val_ratio` — floats,
`dedup_threshold`), `apply-research.yaml` (`relevance_threshold`,
`max_issues_per_file`), `brainstorm.yaml` (`novelty_threshold`),
`loop-router.yaml` (`confidence_threshold`), `rlhf-svg-evaluate.yaml`
(`exploit_cutoff`).

Boolean-shaped keys (`auto`, `exclude_user_corrections`,
`require_file_modifications`, `require_issue_outcome`, `propagate_context`,
`auto_prove_learning_gate`) are **string positions** in the corpus idiom —
`'${context.x}'.lower() == 'true'` (confirmed at `loop-router.yaml:318`,
`sft-corpus.yaml:156`) — so they take the standard string transform. Verify
the idiom per site rather than assuming it.

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
- **`sft-corpus.yaml`** carries the highest density (18 class-A entries in the
  current baseline; the survey's 38 counted all classes). Convert it as its own
  commit so the diff stays reviewable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Current anchors (confirmed 2026-08-28 via codebase-analyzer — re-verify before citing at implementation time, since these drift): `parse_interpolation_suffixes()` — the ENH-3337 suffix-stripping helper shared by `interpolate()`, MR-11, and the ENH-3338 sweep — is at `scripts/little_loops/fsm/interpolation.py:209` (the line this issue previously cited for `interpolate()` itself). `interpolate()` is now at `interpolation.py:274`. `InterpolationContext.resolve()` is at `interpolation.py:78`. `_find_unsafe_context_interpolations()` is at `scripts/little_loops/fsm/validation/shell_safety.py:149` (one line later than previously cited). All three interpolation-side functions still call the shared `parse_interpolation_suffixes()`, so `interpolate()`'s quoting behavior and MR-11's `:shell` recognition stay in sync by construction — confirmed by direct inspection, not just by docstring claim.

## Implementation Steps

1. Filter ENH-3338's baseline to `class == "A"`; that is the work list. Reconcile
   any divergence from the survey's 78 and note it in EPIC-3336. Sites already
   landed in final form by BUG-3339's structural carve-out (its Implementation
   Step 8: the pipe-fed `autodev.yaml` threshold sites and
   `code-run-gate.yaml:438`) will already be absent from the baseline — verify
   they used this issue's conventions (`LL_ARG_` naming, no surrounding
   quotes, typed coercion) rather than re-converting them.
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
8. Every site in a **non-string Python position** keeps its type:
   - Every numeric-position site in the *current* baseline (the files
     enumerated in Program Design → Non-string Python positions:
     `recursive-refine.yaml`, `refine-to-ready-issue.yaml`,
     `lib/rubric-router.yaml`, `lib/composer.yaml`, `sft-corpus.yaml`,
     `apply-research.yaml`, `brainstorm.yaml`, `loop-router.yaml`,
     `rlhf-svg-evaluate.yaml`) is converted with an explicit
     `int(...)`/`float(...)` coercion matching the value's type, and its
     comparison still evaluates identically. Verified by running the affected
     states (the `test_autodev_loop.py` `_extract_python_script` pattern), not
     by inspection — a `str`/`int` comparison raises at runtime and is
     invisible to `ll-loop validate`.
   - The sites already converted by BUG-3339
     (`autodev.yaml:1633, 1742, 1821, 1822, 2053, 2054`;
     `oracles/code-run-gate.yaml:438`) are **verified**, not re-converted:
     confirm they use `LL_ARG_` naming, no surrounding quotes, and typed
     coercion.
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
- `/ll:confidence-check` - 2026-08-28T18:37:17 - `0ddc564b-dddb-422a-9108-e946e9a7ae88.jsonl`
- `/ll:refine-issue` - 2026-08-28T18:12:42 - `917f03bf-c58d-4c5b-9275-d06596c522eb.jsonl`
- `/ll:refine-issue` - 2026-08-28T03:15:15 - `21c2bc4e-6e06-47c6-a164-ddb166a7cfff.jsonl`
- `/ll:format-issue` - 2026-08-28T03:03:20 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
