---
id: ENH-3337
type: ENH
title: Make :shell interpolation suffix compose with :default= and ?
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocks:
- ENH-3338
- BUG-3339
- BUG-3340
- BUG-3341
- ENH-3342
- ENH-3347
confidence_score: 100
outcome_confidence: 74
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 15
---

# ENH-3337: Make :shell interpolation suffix compose with :default= and ?

## Summary

Normalize `interpolate()`'s suffix parsing so `:shell` composes with `:default=`
and `?` in every ordering, apply the fallback **before** `shlex.quote()`, and
update the two other places in the codebase that recognize `:shell` only as a
**trailing** token (`cli/loop/run.py:298-300` and `shell_safety.py:183`). This
is EPIC-3336's hard blocker: **130 `${context.*}` / `${captured.*}` sites carry a
`:default=` or `?` suffix**. BUG-3349 (`d8d3476a1`) already made the
`:shell:default=` ordering work inside `interpolate()` itself, so
default-bearing sites are mechanically convertible today — but the `?`
orderings still misparse, and both out-of-module recognizers still reject or
mis-flag composed suffixes, so the conversions remain blocked until this
lands.

Land as its own commit on `main`. Nothing else in the epic starts before it.

## Current Behavior

`interpolate()` (`scripts/little_loops/fsm/interpolation.py:209-287`) parses
`:default=`, `?`, and `:shell` as only partially composable
(docstring at `:214-219`, `:default=` branch at `:246-256`). Five defects,
all verified against the code as it stands:

**1. Composition silently misparses in two orderings.**

| Written | Today's behavior |
|---|---|
| `${x:shell}` | Correct — `shlex.quote()` applied |
| `${x:shell:default=v}` | **Correct since BUG-3349** (`d8d3476a1`) — the `:default=` branch strips a leading `:shell` and quotes the fallback (`:253-255`, `:283`). Already covered by `TestShellSuffix` tests tagged BUG-3349; do not re-fix or duplicate those tests |
| `${x:default=v:shell}` | **Silent misparse.** Splits on `:default=` first, so `default_value` becomes the literal `"v:shell"` and **no quoting is applied** |
| `${x?:shell}` | `shell_quote=True` is never set and `nullable` is never set — the string ends in `"shell"` not `"?"`, so the path resolves as the literal `"x?"` → "not found" naming the wrong path |
| `${x:shell?}` | **Silent misparse.** Trailing `?` sets `nullable`, path becomes the literal `"x:shell"` → resolve fails → nullable swallows it → yields `""` with no quoting and no error |

**2. `None` short-circuits before the quote.** `:270-271` returns `""` for a
resolved `None` *before* the `shell_quote` branch at `:272-273`. In a bare token
position that emits nothing rather than a valid empty token — bash then sees one
fewer argument.

**3. `:default=` does not fire on a resolved `None`.** The fallback is applied
only in the `except InterpolationError` handler (`:275-279`), i.e. only when the
*path is missing*. A path that resolves to `None` takes the `:270-271` early
return and yields `""`, never the author's default. This is pre-existing and
invisible today; it becomes visible the moment the "resolve → fallback → quote"
pipeline is written, because that ordering implies routing `None` through the
fallback.

**4. Two out-of-module recognizers assume a trailing `:shell`.** Both were
written when the suffix could not compose, and both break under it:

- `scripts/little_loops/cli/loop/run.py:298-300` — the missing-context
  pre-flight. `raw.endswith(":shell")` strips only a trailing suffix. Verified:
  `${context.x?:shell}` yields `raw = "x?"`, which is not in `fsm.context`, so
  the CLI reports `Missing required context variable: 'x?'` and `return 1`
  before the loop starts.
- `scripts/little_loops/fsm/validation/shell_safety.py:183` — MR-11's
  safe-position check, `token.endswith(":shell}")`. Verified:
  `${context.goal:shell:default=}` ends in `default=}`, so MR-11 flags an
  already-quoted site as unsafe. Every BUG-3340 conversion at a default-bearing
  site would emit a **new MR-11 warning**, directly violating EPIC-3336's
  success metric 2.

**5. `VARIABLE_PATTERN` cannot hold a `}` inside a default.** `:28` is
`r"\$\{([^}]+)\}"`. Verified:

```
'${captured.final_counts.output:default={}}' -> ['captured.final_counts.output:default={']
```

The default becomes the literal `{` and a stray `}` is left in the output. This
is live today at `general-task.yaml:895-902`, and BUG-3339 flags it obliquely at
the same site.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Stale as of BUG-3349 (commit `d8d3476a1`, 2026-08-27T20:46:41, closed BUG-3349) — landed AFTER this issue was captured (17:51:35 same day).** Row 2 of the behavior table above (`${x:shell:default=v}` → `InterpolationError`) is no longer accurate. BUG-3349 already fixed the shell-before-default ordering: `interpolate()`'s `:default=` branch now also strips a leading `:shell` off `var_part` and sets `shell_quote=True` (`interpolation.py:253-255`), and the fallback is shlex-quoted too (`:283`). `${x:shell:default=v}` now composes correctly.
- **The other three defects are unchanged and still exactly as described**, verified against current `interpolation.py`: `${x:default=v:shell}` still silently misparses (default-before-shell — `:default=` split happens first and nothing strips a trailing `:shell` from the captured default string); `${x?:shell}` still resolves the wrong path `"x?"` (the `elif full_path.endswith("?")` branch is skipped because the string ends in `"shell"`, so `nullable` is never set); the `None` short-circuit (now at `:276-277`, `if value is None: return ""`) still fires before the `shell_quote` check at `:278-279` and before the `except` block's `default_value` handling; `VARIABLE_PATTERN` (`:28`, unchanged) still terminates on the first `}`, so `}` inside a `:default=` value is still unhandled. `shell_safety.py:183`'s `token.endswith(":shell}")` and `run.py`'s pre-flight (now at `:288-302`, regex compiled `:288`) are both unchanged and still exhibit the defects this issue describes for them.
- **Line numbers have shifted by BUG-3349's diff** (+5 net lines before the suffix-parse block): the suffix-chain cascade is now at `interpolation.py:246-262` (was cited as `:238-256`), and the resolve/quote/fallback block is now at `:274-286` (was `:268-280`). `run.py`'s `_ctx_var_re` pre-flight loop is now at `:276-309` (regex compile `:288`, loop body `:289-302`, `:default=`/`?` skip `:297`, `:shell` strip `:299-300`) — was cited as `:284-300`/`:288-305`.
- **Existing test coverage**: `scripts/tests/test_fsm_interpolation.py`'s `TestShellSuffix` class (`:844-921`) already has `test_shell_default_combined_missing_path_emits_quoted_fallback` (`:886`) and `test_shell_default_combined_present_path_emits_quoted_value` (`:898`), both tagged "BUG-3349" — these cover exactly the now-fixed shell-before-default ordering. Confirmed via repo-wide grep: no existing test covers `${x:default=v:shell}` (default-before-shell), `${x?:shell}`, `}` inside a `:default=` value, or the combined "resolved value is `None` AND `:default=` is present" interaction (the closest existing test, `test_shell_suffix_empty_value_resolves_to_empty` at `:874`, only exercises bare `:shell` on a resolved `None`, no `:default=`).

## Expected Behavior

One defined, unit-tested meaning for every suffix ordering, with a single
evaluation pipeline:

> **resolve → apply fallback → `shlex.quote()`**

- All five orderings (`${x:shell}`, `${x:shell:default=v}`,
  `${x:default=v:shell}`, `${x?:shell}`, `${x:shell?}`) parse to the same
  intent. No ordering raises `Ambiguous suffix` and none silently misparses.
  (`?` with `:default=` stays a hard error, as today.)
- The fallback value is itself quoted when `:shell` is present — a default
  containing a space or a quote must not break the token.
- An empty or absent value under `:shell` emits `''` (a valid empty token), not
  nothing.
- `run.py`'s pre-flight and MR-11's safe-position check recognize `:shell`
  wherever it appears in the suffix chain, not only at the end.

### Behavior changes to audit in this commit

These are observable and must be checked, not assumed benign.

**a. Empty value under `:shell` now emits `''`.** 17 `:shell` sites exist in the
corpus; the ones in a bare token position see the change:
- `outer-loop-eval.yaml` — `ll-loop show ${context.input:shell}` (two sites)
- `refine-to-ready-issue.yaml` — `[ -n ${context.input:shell} ]`. Today an empty
  input collapses to `[ -n ]`, which is **always true** in bash. `''` fixes that
  latent bug — but **verify the branch flip is intended**, because a loop may be
  depending on the always-true behavior.
- `|| echo ${context.goal:shell}` fallbacks — `loop-router.yaml` (×2),
  `loop-composer.yaml`, `loop-composer-adaptive.yaml`
- `prompt-across-issues.yaml`, `rn-implement.yaml`, `proof-first-task.yaml`
  (×2), `mechanize-skills.yaml` (×5), `cua-agent-desktop.yaml`

**b. Routing `None` through the fallback affects ~130 `:default=`/`?` sites**,
not only the 5 bare-token `:shell` ones. Decide explicitly: either (i) `None`
routes through the fallback (consistent pipeline, wider blast radius), or (ii)
`None` keeps its `""` short-circuit and only the quote moves after it (narrower,
but leaves `${x:default=v}`-on-`None` yielding `""`, which will surprise a future
reader). **Recommendation: (ii)** — this issue's mandate is composition, and (i)
is a separate semantic change that deserves its own issue and its own audit of
the 130 sites. Record whichever is chosen.

**c. `VARIABLE_PATTERN` and `}` in defaults.** Either widen the pattern to
balance braces, or reject a `}` in a default with a clear `InterpolationError`
and fix `general-task.yaml:895` to not need one. **Recommendation: reject
loudly** — brace-balancing a regex-based interpolator invites worse bugs than it
fixes, and exactly one corpus site needs it.

## Motivation

BUG-3331 §BLOCKER: *"Steps 5 and 6 as written are unimplementable at any site
that already carries a `:default=` or `?` suffix — the conversion produces a
runtime hard failure, not a lint warning."*

Real EPIC-3336 targets sit among the 130:
- Class B: `loop-router.yaml:522-523`
  (`"""${captured.new_loop_proposal.output:default=}"""`,
  `"""${captured.review_result.output:default=}"""`);
  `loop-composer-adaptive.yaml:744, 750`
- Class A: `rn-refine.yaml:151, 223, 500, 907, 1014-1015`;
  `recursive-refine.yaml:55, 82-83, 118, 304, 320`; `rn-build.yaml:728-729`

Option S1 (make `:shell` compose) was selected over S2 (push the default into
Python — class-A only, no answer for class B) and S3 (exempt these sites — carves
a permanent hole in the sharpest class). S1 is the only option that keeps the
per-site remedy uniform across all 145 sites, which is what lets ENH-3338's sweep
be a single rule instead of a rule plus an exemption list.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/interpolation.py`
  - `:28` — `VARIABLE_PATTERN`, per Expected Behavior (c)
  - `:214-216` — docstring: the three suffixes are no longer mutually exclusive
  - `:238-256` — the suffix-parse block
  - `:268-280` — resolve / quote / fallback ordering
- `scripts/little_loops/cli/loop/run.py:284-300` — the missing-context
  pre-flight's `_ctx_var_re` handling and the `endswith(":shell")` strip.
  **Note `:298` already `continue`s on any `":default=" in raw`**, so
  `${context.x:default=v:shell}` is skipped entirely rather than mis-stripped;
  the `?:shell` ordering is the one that hard-fails.
- `scripts/little_loops/fsm/validation/shell_safety.py:183` — MR-11's
  `token.endswith(":shell}")` safe-position check. **Recognition only** — make it
  see `:shell` anywhere in the chain. Whether recognizing it *clears* the site is
  ENH-3342's question, and the answer there is "not inside a Python body"; do not
  pre-empt it.
- `scripts/little_loops/loops/general-task.yaml:895-902` — the one YAML edit in
  scope, per Scope Boundaries. Rewrite `:default={}` so it needs no brace.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py:2115` — calls `interpolate()` on each
  action; no change, but it is the path every behavior change reaches production
  through.
- `scripts/little_loops/fsm/runners.py:297` — `bash -c <action>`; no change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/evaluators.py` — 9 direct `interpolate()` call sites
  (`:855,863,1758,1877,1913,1931,1947,1971,1984,2004`) on author-configured
  `EvaluateConfig` template fields (`target`, `previous`, `tolerance`,
  `history_file`, `prompt`) — structurally identical exposure to `action:`
  strings. No corpus site currently attaches a composed suffix to these
  fields, so this is a latent, not active, exposure — no code change
  required, but Implementation Step 8's regression sweep should confirm these
  fields are unaffected.
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test()` builds an
  `InterpolationContext` (`:115`) and calls `evaluate()` (`:119`), routing
  into the `evaluators.py` `interpolate()` sites above when `ll-loop test`
  exercises a loop's `evaluate:` config. No change; same latent-exposure note
  applies.
- `scripts/little_loops/fsm/__init__.py:120-125` — re-exports
  `InterpolationContext`, `InterpolationError`, `interpolate`,
  `interpolate_dict` as the FSM package's public API surface. No change, but
  this is the public contract this issue's semantics change reaches
  consumers through, outside the two already-known callers.
- `scripts/little_loops/fsm/validation/__init__.py:117-127,217` — re-exports
  `_find_unsafe_context_interpolations` and related MR-11 names from
  `shell_safety.py`. No change beyond `shell_safety.py:183` itself, already
  in scope.

### Tests

- `scripts/tests/test_fsm_interpolation.py` — one case per ordering
  (`:shell`, `:shell:default=`, `:default=…:shell`, `?:shell`, `:shell?`),
  plus mid-default literal `:shell`, quoted-default, empty-value-emits-`''`,
  and the `}`-in-default decision. (The refine findings below correct the
  originally proposed new-file location: `TestShellSuffix` in the existing
  module is where this coverage lives, and the `:shell:default=` cases
  already exist there from BUG-3349.)
- `scripts/tests/test_ll_loop_commands.py:7433-7501` — extend the two existing
  `:shell` pre-flight cases (`test_...:shell` ref not falsely flagged / genuinely
  missing still flagged) to cover composed suffixes.
- `scripts/tests/test_fsm_validation_shell_safety.py` — new: MR-11 does not fire
  on a composed `${context.goal:shell:default=}`.
- Regression sweep over the 17 existing `:shell` sites for behavior change (a).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_interpolation.py:874-878`
  (`TestShellSuffix.test_shell_suffix_empty_value_resolves_to_empty`) —
  **will break**. It currently asserts the old None-short-circuit-before-quote
  behavior (`"VAL="`); under this issue's "resolve → fallback → quote"
  pipeline the same input must become `"VAL=''"` (Acceptance Criterion 3).
  Update the expected value as part of this issue's own change.
- **Correction**: `scripts/tests/test_fsm_validation_shell_safety.py` already
  exists (`TestUnsafeContextInterpolation` class, `:202-334`, covering
  MR-7/MR-9/MR-11) — it is not a new file. Add a new test method to that
  existing class (sibling to `test_mr11_does_not_fire_for_shell_suffix` at
  `:275`), not a new test file.
- `scripts/little_loops/loops/general-task.yaml:895-902`'s `summarize_success`
  state has zero direct interpolation-level test coverage today (confirmed:
  existing `TestSafeInterpolation` general-task coverage only exercises
  `check_done` and `run_final_tests`). Add a case covering the `}`-in-default
  fix at this exact site.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the suffix grammar is documented
  as part of ENH-3342's idiom section, not here. If a suffix reference exists
  elsewhere, update it.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6222-6268` (`#### interpolate` section) — the worked
  examples document `:default=`, `?`, and `:shell` as separate, non-composed
  cases (`:6254`, `:6258`, `:6263`). No example shows a composed ordering;
  this goes stale the moment this issue lands and should gain at least one
  composed example. (MR-11's conceptual descriptions elsewhere — `API.md:6321`,
  `CLI.md:870`, `skills/review-loop/reference.md:50`,
  `HARNESS_OPTIMIZATION_GUIDE.md:104` — remain accurate and need no edit.)

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Conventions in Force** — the codebase's established precedent for a small parse routine shared across multiple consumer modules (which is what the proposed `parse_interpolation_suffixes()` helper would be) is `policy_rules.py`'s `grammar_spec()`/`parse_rules()` (`scripts/little_loops/fsm/policy_rules.py:98,262`), imported directly by `route_table.py`, `validation/reachability.py:175`, and `cli/artifact/policy_builder.py:63` — a real cross-module import, not a re-implementation. By contrast, the two out-of-module `:shell` recognizers this issue targets currently hand-mirror `interpolate()`'s parse with a synchronization comment citing the canonical line numbers rather than importing a shared function (`run.py:276-287`'s comment names `fsm/interpolation.py:236-250` as the source of truth) — this comment-only synchronization is the drift risk that produced defects 4a/4b, and is the gap the proposed helper extraction closes.
- `InterpolationError` is a bare `Exception` subclass carrying only an f-string message — no error codes or `.kind` attributes exist anywhere in the codebase's 10 raise sites in `interpolation.py`. Tests assert via `pytest.raises(InterpolationError, match="<substring>")`.
- `shlex.quote()` is called directly (no wrapper) at exactly two production sites, both inside `interpolate()` itself (`interpolation.py:279,283`) — no other production module under `scripts/little_loops/` calls `shlex.quote()`.
- Suffix/grammar test classes in `test_fsm_interpolation.py` follow a `class Test<Feature>` shape with `# ── section ──` comment dividers grouping sub-cases and a one-line docstring per test naming the originating issue ID — evidence: `TestSafeInterpolation` (`:554`, ENH-1958), `TestShellSuffix` (`:844`, BUG-2622/BUG-3349). New test cases for this issue should follow that shape rather than `scripts/tests/test_interpolation.py` (a new filename the issue proposes, but the actively maintained module for this area is `test_fsm_interpolation.py`).
- This codebase's convention for recording a semantic decision (as Acceptance Criterion 6 requires for the None-handling and `}`-in-default choices) is a dated `## Recorded decisions (DATE)` section with per-topic `### <topic>` subheadings, each opening with a bold `**Decision: ...**` line plus rationale — evidence: `.issues/features/P3-FEAT-3036-artifact-templates-design.md:229,328`. No such section exists yet in this issue.

## Scope Boundaries

**In scope:** the suffix grammar and its evaluation ordering in
`interpolate()`, plus the two out-of-module recognizers that must agree with it
(`cli/loop/run.py`, `shell_safety.py:183`). The two recorded semantic decisions
(`None` handling, `}` in defaults).

**Out of scope:** any loop YAML site conversion (BUG-3339/3340/3341); MR-11's
pattern width and namespace coverage (ENH-3342 — this issue touches `:183` only
to keep composed suffixes recognized); new suffixes beyond the existing three.

**One named exception to "no loop YAML edits":
`general-task.yaml:895-902`.** Step 4 makes a `}` inside a `:default=` a hard
`InterpolationError`, and that site
(`${captured.final_counts.output:default={}}`) is the corpus's only occurrence.
Landing the error without fixing the site turns a working state into a runtime
hard failure for however many commits separate this issue from BUG-3339. So the
fix ships **in this commit**, and this issue's scope boundary is "no *conversion*
of a site to a safe idiom" — not "no YAML edits at all".

Two consequences to carry forward:

- **BUG-3339 also targets `general-task.yaml:895-902`** (its `-c "` →
  heredoc conversion, and its Program Design flags this exact `:default={}`
  interaction). That conversion must **preserve** this issue's fix, not revert to
  a brace-bearing default. Cross-referenced in BUG-3339's Implementation Steps.
- **ENH-3338 seeds its baseline *after* this commit**, so the seed reflects the
  fixed form of that site. Seeding from a pre-3337 `main` would bake in a site
  that no longer exists.

## Program Design

### Signatures

- `interpolate(template: str, ctx: InterpolationContext) -> str`
  (`scripts/little_loops/fsm/interpolation.py:209`) — unchanged signature; the
  inner `replace_var(match)` closure (`:231`) is where the parse and the
  evaluation ordering change.
- `InterpolationContext.resolve(self, namespace: str, path: str) -> Any`
  (`:78`) — unchanged. Suffixes are parsed off before `resolve()` is called and
  are invisible to it.
- `_run(...)` context pre-flight in `scripts/little_loops/cli/loop/run.py`
  (`_ctx_var_re` block, `:288-305`) — no signature change; the suffix-stripping
  logic inside is replaced.
- `_find_unsafe_context_interpolations(fsm: FSMLoop) -> list[tuple[str, str]]`
  (`scripts/little_loops/fsm/validation/shell_safety.py:148`) — no signature
  change; the `:shell` recognition at `:183` is replaced.

### Decision Rules

Suffix chain parsing — one rule, order-independent:

1. Recognize `:shell` in **exactly two positions**: immediately before
   `:default=` (i.e. the chain contains `:shell:default=`), or at the very
   end of the whole chain (after the default value, or after `?`, or alone).
   Set `shell_quote` and remove it. **Not** "anywhere in the string": a
   `:shell` embedded mid-default (`:default=use :shell here`) is part of the
   literal default and must survive untouched — an unrestricted
   strip-anywhere pass would corrupt it.
2. Of what remains, `:default=` (first occurrence wins, everything after it is
   the literal default) and a trailing `?` are parsed as today. `?` and
   `:default=` **remain mutually exclusive** — the existing raise at
   `interpolation.py:248-252` is kept, not silently dropped in the rewrite.
3. Evaluate: `resolve()` → on `InterpolationError`, substitute the default (or
   `""` if nullable, else re-raise) → if `shell_quote`, `shlex.quote(str(result))`.

The one genuine ambiguity is `${x:default=v:shell}`: is `:shell` a suffix or part
of the literal default `"v:shell"`? **Resolve in favor of the suffix** — a
default value ending in the exact string `:shell` is not a real use in the corpus
(verify with a grep before implementing), and reading it as the suffix is the
only reading that makes the ordering irrelevant, which is the point of this
issue. Document the escape hatch for anyone who genuinely wants a literal
`:shell` default.

### Call Path

Unchanged in shape:
`executor.py:2115 interpolate()` → `replace_var` (suffix parse, resolve, quote)
→ `runners.py:297 bash -c <action>`.

Two side paths must agree with the new parse, and neither runs through
`interpolate()`:
- `cli/loop/run.py:288-305` — pre-flight, runs before the FSM starts
- `fsm/validation/shell_safety.py:181-187` — MR-11, runs at `ll-loop validate`

A parse that lives in three places is the root of defects 4a and 4b. **Consider
extracting a single `parse_interpolation_suffixes(raw: str) -> tuple[str, ...]`
helper in `interpolation.py` and importing it from both side paths**, so the next
suffix addition cannot desynchronize them again.

## Implementation Steps

1. Extract the suffix parse into one helper in `interpolation.py`; make it
   order-independent per Decision Rules.
2. Reorder evaluation to resolve → fallback → `shlex.quote()`, quoting the
   fallback value too.
3. Decide and record the `None` question (Expected Behavior b) — recommendation
   (ii), narrow.
4. Decide and record the `}`-in-default question (Expected Behavior c) —
   recommendation: reject loudly; fix `general-task.yaml:895` accordingly.
5. Update `cli/loop/run.py:288-305` to use the shared helper.
6. Update `shell_safety.py:183` to use the shared helper.
7. Unit tests for all five orderings (including `${x:shell?}`), the
   mid-default literal `:shell`, quoted defaults, and empty-emits-`''`.
8. Audit the 17 existing `:shell` sites for behavior change (a); pay specific
   attention to `refine-to-ready-issue.yaml`'s `[ -n … ]` branch flip.
9. `python -m pytest scripts/tests/` exits 0; `ll-loop validate` clean across the
   corpus with no new MR-11 warnings.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

- Update `scripts/tests/test_fsm_interpolation.py:874-878` — fix
  `test_shell_suffix_empty_value_resolves_to_empty`'s expected value from
  `"VAL="` to `"VAL=''"` per the new resolve → fallback → quote ordering.
- Add a test method to `scripts/tests/test_fsm_validation_shell_safety.py`'s
  existing `TestUnsafeContextInterpolation` class covering
  `${context.goal:shell:default=}` not firing MR-11.
- Add interpolation-level test coverage for `general-task.yaml:895-902`'s
  `summarize_success` state, exercising the `}`-in-default fix at this exact
  site.
- Update `docs/reference/API.md:6222-6268`'s `interpolate` worked examples to
  include at least one composed-suffix ordering.

## Acceptance Criteria

1. `${x:shell}`, `${x:shell:default=v}`, `${x:default=v:shell}`, `${x?:shell}`,
   and `${x:shell?}` each have one defined, unit-tested meaning. No ordering
   raises `Ambiguous suffix` and none silently misparses. A `:shell` embedded
   mid-default (`:default=use :shell here`) stays literal, with a unit test.
   `?` + `:default=` still raises, with the existing test kept passing.
2. A fallback value is `shlex.quote()`d when `:shell` is present; a default
   containing a space or a quote produces a single valid shell token.
3. An empty or absent value under `:shell` emits `''`. The 5 bare-token sites
   named in Expected Behavior (a) are individually audited, and
   `refine-to-ready-issue.yaml`'s `[ -n … ]` branch flip is confirmed intended
   and recorded.
4. `ll-loop run <loop> --context x=...` no longer reports a false
   `Missing required context variable: 'x?'` for `${context.x?:shell}`, with a
   test in `test_ll_loop_commands.py`.
5. MR-11 does not fire on a composed `${context.goal:shell:default=}`, with a
   test in `test_fsm_validation_shell_safety.py`.
6. The `None`-handling decision and the `}`-in-default decision are each recorded
   in this issue with their rationale.
6b. `general-task.yaml:895-902` is fixed in the **same commit** that makes a `}`
   in a default an error, so no commit on `main` leaves that state hard-failing.
   `ll-loop validate general-task` is clean at that commit.
7. `python -m pytest scripts/tests/` exits 0 and `ll-loop validate` is clean
   across the whole loop corpus — no new MR-11 warnings, no loop setting
   `unsafe_context_interpolation_ok`.

## Impact

- **Priority**: P2 — inherited from EPIC-3336, and it is the epic's hard gate:
  130 sites are unconvertible until it lands.
- **Effort**: Small–Medium — one function's parse plus two out-of-module
  recognizers, but the audit of 17 existing `:shell` sites and two recorded
  semantic decisions are the real cost. Not a one-line edit.
- **Risk**: Medium — `interpolate()` is on the execution path of every loop
  action in the corpus. Mitigated by being pure, synchronous, and fully
  unit-testable in isolation.
- **Breaking Change**: Yes, narrowly — behavior change (a) is observable at 5
  existing bare-token `:shell` sites, one of which (`[ -n … ]`) flips a branch.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-28T03:13:07 - `e52b5f8b-4479-4377-bf0a-15b1b4dcbd9a.jsonl`
- `/ll:confidence-check` - 2026-08-28T03:03:45 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:wire-issue` - 2026-08-28T02:57:39 - `13d6dd54-6fe5-483d-8ac7-01629c54d02f.jsonl`
- `/ll:refine-issue` - 2026-08-28T02:39:00 - `b0fc8e25-b423-43c9-a6e7-49a921fc64b8.jsonl`
- `/ll:format-issue` - 2026-08-28T02:28:48 - `2ce7a90a-6aac-441b-a6ef-bdf7013fe147.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:44 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
