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
blocks: [ENH-3338, BUG-3339, BUG-3340, BUG-3341, ENH-3342, ENH-3347]
---

# ENH-3337: Make :shell interpolation suffix compose with :default= and ?

## Summary

Normalize `interpolate()`'s suffix parsing so `:shell` composes with `:default=`
and `?` in every ordering, apply the fallback **before** `shlex.quote()`, and
update the two other places in the codebase that recognize `:shell` only as a
**trailing** token (`cli/loop/run.py:298-300` and `shell_safety.py:183`). This
is EPIC-3336's hard blocker: **130 `${context.*}` / `${captured.*}` sites carry a
`:default=` or `?` suffix**, and every one of them is unconvertible until this
lands.

Land as its own commit on `main`. Nothing else in the epic starts before it.

## Current Behavior

`interpolate()` (`scripts/little_loops/fsm/interpolation.py:209-287`) parses
`:default=`, `?`, and `:shell` as **mutually exclusive**
(docstring at `:214-216`, guard at `:243-249`). Four defects, all verified
against the code as it stands:

**1. Composition raises or silently misparses.**

| Written | Today's behavior |
|---|---|
| `${x:shell}` | Correct — `shlex.quote()` applied |
| `${x:shell:default=v}` | `InterpolationError("Ambiguous suffix: …")` — the documented blocker (`:243-249`) |
| `${x:default=v:shell}` | **Silent misparse.** Splits on `:default=` first, so `default_value` becomes the literal `"v:shell"` and **no quoting is applied** (`:244`) |
| `${x?:shell}` | `shell_quote=True`, then resolves the path `"x?"` → "not found" naming the wrong path (`:254-256`) |

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

## Expected Behavior

One defined, unit-tested meaning for every suffix ordering, with a single
evaluation pipeline:

> **resolve → apply fallback → `shlex.quote()`**

- All four orderings (`${x:shell}`, `${x:shell:default=v}`,
  `${x:default=v:shell}`, `${x?:shell}`) parse to the same intent. No ordering
  raises `Ambiguous suffix` and none silently misparses.
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

### Tests

- `scripts/tests/test_interpolation.py` (new) — one case per ordering
  (`:shell`, `:shell:default=`, `:default=…:shell`, `?:shell`), plus
  quoted-default, empty-value-emits-`''`, and the `}`-in-default decision.
- `scripts/tests/test_ll_loop_commands.py:7433-7501` — extend the two existing
  `:shell` pre-flight cases (`test_...:shell` ref not falsely flagged / genuinely
  missing still flagged) to cover composed suffixes.
- `scripts/tests/test_fsm_validation_shell_safety.py` — new: MR-11 does not fire
  on a composed `${context.goal:shell:default=}`.
- Regression sweep over the 17 existing `:shell` sites for behavior change (a).

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the suffix grammar is documented
  as part of ENH-3342's idiom section, not here. If a suffix reference exists
  elsewhere, update it.

### Configuration

- N/A

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

1. Strip a trailing/embedded `:shell` token wherever it appears in the suffix
   chain; set `shell_quote`.
2. Of what remains, `:default=` (first occurrence wins, everything after it is
   the literal default) and a trailing `?` are parsed as today.
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
7. Unit tests for all four orderings, quoted defaults, and empty-emits-`''`.
8. Audit the 17 existing `:shell` sites for behavior change (a); pay specific
   attention to `refine-to-ready-issue.yaml`'s `[ -n … ]` branch flip.
9. `python -m pytest scripts/tests/` exits 0; `ll-loop validate` clean across the
   corpus with no new MR-11 warnings.

## Acceptance Criteria

1. `${x:shell}`, `${x:shell:default=v}`, `${x:default=v:shell}`, and `${x?:shell}`
   each have one defined, unit-tested meaning. No ordering raises
   `Ambiguous suffix` and none silently misparses.
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
- `/ll:format-issue` - 2026-08-28T02:28:48 - `2ce7a90a-6aac-441b-a6ef-bdf7013fe147.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:44 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
