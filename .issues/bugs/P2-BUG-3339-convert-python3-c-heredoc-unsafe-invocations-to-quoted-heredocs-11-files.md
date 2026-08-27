---
id: BUG-3339
type: BUG
title: Convert python3 -c heredoc-unsafe invocations to quoted heredocs (11 files)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# BUG-3339: Convert python3 -c heredoc-unsafe invocations to quoted heredocs (11 files)

## Summary

Convert the 53 python3 -c "..." interpolation sites (11 files under the narrow scope) to quoted python3 << PYEOF heredocs so they stop being shell-injectable, validating each converted file with ll-loop validate.

## Current Behavior

A handful of loop YAML `action_type: shell` states pipe or invoke
`python3 -c "..."` where the Python source is a **bash double-quoted string**
literal embedded directly in the action body. `InterpolationContext.resolve()`
(`scripts/little_loops/fsm/interpolation.py`) performs pure text substitution
into the raw action string before `bash -c <action>` ever runs
(`scripts/little_loops/fsm/runners.py:297`), so any `${context.*}`/`${captured.*}`
value landing inside the `-c "…"` string is exposed to bash expansion (`"`,
`$(...)`, backticks, `!`) *and*, after bash finishes, to Python string-literal
parsing — a shell injection stacked on top of a code-literal injection. This is
"Host shape 2" from the parent survey (BUG-3331 § Current Behavior), the
strictly worse of the two host shapes: a quoted heredoc (`python3 << 'PYEOF'`)
is not shell-expanded by bash at all, but `-c "..."` is.

MR-11 (`_find_unsafe_context_interpolations`,
`scripts/little_loops/fsm/validation/shell_safety.py:148-188`) treats a
site as safe once it sits inside a properly `<<'MARKER'`/`<<"MARKER"` quoted
heredoc (tracked via `_QUOTED_HEREDOC_START_RE`, line 41, closed on
`line.strip() == marker`). A bare `python3 -c "…"` body is never in that safe
position, so every `${context.<sevenkey>}` interpolation inside one is
flagged today (subject to MR-11's fixed seven-key allowlist and its
`${captured.*}` blind spot — both out of this issue's scope, see
EPIC-3336/ENH-3342).

## Expected Behavior

Each `python3 -c "..."` invocation confirmed to carry a `${context.*}` or
`${captured.*}` interpolation inside its Python-literal body is rewritten to
the quoted-heredoc shape already used ~90+ times elsewhere in the loop corpus:
`python3 << 'PYEOF' ... PYEOF` (marker word varies by file — `PYEOF` is the
majority convention, `PY` the minority; always single-quoted, always closed on
a bare marker line). This removes the bash-double-quote layer so bash performs
zero expansion on the body; it is **behavior-neutral and does not address the
remaining Python-string-literal injection** (that is BUG-3340/BUG-3341's
scope — the class-A `:shell`-env-var and class-B heredoc-to-file remedies).
`ll-loop validate` must stay clean (no new MR-11 warnings) on every converted
file.

## Steps to Reproduce

1. Run `loop-router`'s `discover_loops` state (or any of the 9 confirmed
   sites in Integration Map) with an `${context.include}`/`${context.exclude}`
   (or the site's equivalent interpolated key) containing a `"` or a
   `$(...)` command-substitution token — e.g.
   `ll-loop run loop-router --context include='"; touch /tmp/pwned; #'`.
2. `InterpolationContext.resolve()` substitutes the raw value into the
   `python3 -c "..."` string before bash ever sees it
   (`scripts/little_loops/loops/loop-router.yaml:34`).
3. Observe: bash tokenizes the substituted `"` as the end of the `-c`
   argument, so the remainder of the interpolated value executes as a
   separate shell command with the run's full privileges — not merely a
   Python `SyntaxError`, but a live shell injection. A quoted heredoc
   (`python3 << 'PYEOF'`) at this site would prevent bash from interpreting
   the `"` at all.

## Root Cause

- **Files**: see confirmed site list in Integration Map below.
- **Anchor**: representative — `discover_loops` state,
  `scripts/little_loops/loops/loop-router.yaml:31-79`.
- **Cause**: the action body opens Python via `python3 -c "..."` (a bash
  double-quoted string) instead of a quoted heredoc. Bash *does* expand the
  contents of a double-quoted string — unlike a `<<'MARKER'` heredoc, which
  bash passes through verbatim — so an interpolated value containing `"`,
  `$(...)`, or backticks breaks bash tokenizing or command-substitutes before
  Python is ever invoked. The same file already contains five other states
  using the converted `python3 << 'PYEOF'` shape
  (`route_branch_project:130-142`, `route_branch_builtin:144-156`,
  `parse_project_score:196-224`, `select_loop:304-321`,
  `apply_user_choice:365-388`, `finalize_present_result:509-557`) — this issue
  brings `discover_loops` and the equivalent sites in the other 10 files up to
  that same shape.

## Integration Map

### Files to Modify

Confirmed `python3 -c "..."` sites with a `${context.*}`/`${captured.*}`
interpolation inside the Python-literal body (locator + analyzer, cross-checked):

- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` (31-79):
  `${context.include}` (34), `${context.exclude}` (53), `${context.run_dir}` (76)
- `scripts/little_loops/loops/sft-corpus.yaml` — 9 sites, each `${context.output_dir}`
  plus a state-specific key: lines 114, 136, 139, 156, 178, 198, 220, 240, 262, 319
- `scripts/little_loops/loops/autodev.yaml` — 4 confirmed groups:
  1619-1653 (`${context.run_dir}` at 1633/1640, `${context.readiness_threshold}`),
  1739-1746 (`${context.readiness_threshold}`),
  1815-1824 (`${context.readiness_threshold}`, `${context.outcome_threshold}`),
  2047-2054 (same pair repeated)
- `scripts/little_loops/loops/lib/composer.yaml` — `discover_loops` fragment
  (18-79), near-identical to loop-router's: `${context.include:default=}` (32),
  `${context.exclude}` (51)
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` —
  `check_mechanical` (28-54): `${context.output}` (34, triple-single-quoted literal)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:438` —
  `${context.min_pass_rate}`, inside an `if ! python3 -c "..."; then` condition
- `scripts/little_loops/loops/rn-plan-apo.yaml:48` — `${context.tasks_file}`,
  single-line `-c` body redirected with `>`
- `scripts/little_loops/loops/general-task.yaml:895-902` —
  `${captured.final_counts.output:default={}}`, wrapped in `$(...) || echo 0`

**Not in scope — verify before treating as a target:**
- `scripts/little_loops/loops/harness-optimize.yaml:160-165` — textually
  matches `python3 -c "..."` and was named in the parent survey's confirmed-site
  list, but its enclosing state (`apply`) has `action_type: prompt`
  (harness-optimize.yaml:145), not `shell`. `runners.py` only shells out for
  `action_type: shell`/`None`, and MR-11 itself skips non-shell states
  (`shell_safety.py:165`). This text is prose describing a shell command to
  the LLM, not a live invocation — including it in the 11-file/53-site count
  is a false positive from a naive `grep 'python3 -c "'` sweep.
- `scripts/little_loops/loops/rn-build.yaml` — has 10 `python3 -c "` occurrences
  (lines 559, 798, 826, 953, 974, 979, 984, 1216, 1329, 1363) but none was
  individually confirmed to carry a `${context.*}`/`${captured.*}` interpolation
  inside the literal body in this pass. The parent survey's "11 files" list
  does not name it either. Flagging as unconfirmed, not asserting inclusion or
  exclusion.

The confirmed list above is 9 files. The parent survey states "53 sites, 11
files"; this pass could not independently reconstruct 11 files with
interpolation-bearing `-c "` sites from the corpus (harness-optimize.yaml
appears not to qualify, and no second unconfirmed file beyond rn-build.yaml
was identified). Resolving the exact file/site count against the parent
survey's original count is unstarted work for whoever begins the conversion,
not a blocker to starting on the 9 confirmed files.

### Conventions in Force

- The target heredoc shape is `python3 << 'PYEOF' ... PYEOF` (single-quoted
  marker, bare marker line closes it) — used ~90+ times across the loop
  corpus. Marker word varies by file: `PYEOF` is the majority convention
  (e.g. `rn-build.yaml`, `loop-composer.yaml`, `mechanize-skills.yaml`,
  `goal-cluster.yaml`, `recursive-refine.yaml`); `PY` is used by a minority
  (e.g. `openscad-model-generator.yaml:328`, `rlhf-svg-evaluate.yaml`,
  `svg-image-generator.yaml`, `flux-image-generator.yaml`,
  `html-website-generator.yaml`, `interactive-component-generator.yaml`) —
  evidence: pattern-finder survey. Marker spacing (`<< 'PYEOF'` vs
  `<<'PYEOF'`) varies independently of marker word choice.
- `loop-router.yaml` already contains both the unconverted shape
  (`discover_loops`) and the converted shape side by side
  (`route_branch_project:130-142` etc.) — the exact before/after transformation
  target is visible in the same file being edited.
- `scripts/little_loops/loops/lib/composer.yaml`'s `discover_loops` fragment is
  near-identical to `loop-router.yaml`'s unconverted `discover_loops` — the same
  converted shape applies to both.
- MR-11's heredoc-safety check (`_QUOTED_HEREDOC_START_RE`,
  `shell_safety.py:41`) is marker-agnostic — it accepts any single- or
  double-quoted word, confirmed by its own test fixture using yet a third
  marker (`LL_EOF`,
  `scripts/tests/test_fsm_validation_shell_safety.py:267-273`,
  `test_mr11_does_not_fire_inside_quoted_heredoc`). Converting a site does not
  require using `PYEOF`/`PY` specifically, only a quoted marker.
- No checked-in baseline/allowlist data file (JSON/YAML/txt enumerating sites)
  exists yet anywhere in the repo for this class of ratchet migration — the
  parent EPIC's proposed sibling static-sweep issue (ENH-3338) would introduce
  one. The one precedent for a similar "discovered sites == checked-in
  classification" ratchet in this codebase is a Python module-level
  set/dict, not a data file: `FENCED_BRIEF_SITES` /
  `KNOWN_UNFENCED_PROMPT_SITES` (`scripts/little_loops/fsm/fence.py:156-164`),
  enforced by `test_completeness_guard`
  (`scripts/tests/test_builtin_loops.py:18666-18688`, asserts
  `discovered == set(FENCED_BRIEF_SITES) | KNOWN_UNFENCED_PROMPT_SITES`).

### Tests

- `scripts/tests/test_fsm_validation_shell_safety.py` — MR-11 unit tests;
  covers the quoted-heredoc safe-position fixture referenced above.
- `scripts/tests/test_builtin_loops.py` — behavioral loop tests; per BUG-3331's
  Tests section, this is where the four planned behavioral cases (apostrophe
  goal, `"""` capture, Python injection, shell-injection-at-a-converted-`-c "`-site)
  are meant to live.
- File-specific coverage for the 9 confirmed target files:
  `scripts/tests/test_loops_sft_corpus.py` (sft-corpus.yaml),
  `scripts/tests/test_autodev_loop.py` (autodev.yaml). No file-specific test
  module was found for `loop-router.yaml`, `lib/composer.yaml`,
  `oracles/oracle-capture-issue.yaml`, `oracles/code-run-gate.yaml`,
  `rn-plan-apo.yaml`, or `general-task.yaml` in this pass — `ll-loop validate`
  is the applicable check for those.

### Documentation

- N/A — no documentation currently describes the `-c "` vs. heredoc host
  shapes; `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` is where the parent EPIC
  plans to document the resulting idiom (its Implementation Step 10, not this
  issue's).

### Configuration

- N/A

## Program Design

### Signatures

No Python API changes — this is a shell-syntax-only conversion inside loop
YAML action strings. The two functions that determine whether a converted
site reads as "safe" stay as-is and are not modified by this issue:

- `_find_unsafe_context_interpolations(fsm: LoopFSM) -> list[ValidationError]`
  (`scripts/little_loops/fsm/validation/shell_safety.py:148`) — the MR-11
  scanner whose `_QUOTED_HEREDOC_START_RE` heredoc-tracking
  (`shell_safety.py:41`) is what makes a converted `<<'PYEOF'` site clean.
- `InterpolationContext.resolve(self, template: str) -> str`
  (`scripts/little_loops/fsm/interpolation.py`) — the pure-text substitution
  pass that runs before `bash -c <action>`
  (`scripts/little_loops/fsm/runners.py:297`); unchanged by this issue, since
  the conversion changes only the shell wrapper around the already-substituted
  text, not the substitution itself.

### Call Path

Before: `InterpolationContext.resolve()` substitutes into the raw action
string (`scripts/little_loops/fsm/interpolation.py`) -> `bash -c <action>`
(`scripts/little_loops/fsm/runners.py:297`) -> bash expands the double-quoted
`-c "..."` string (command substitution, quote-breaking) -> `python3 -c`
parses whatever bash left as source.

After: `InterpolationContext.resolve()` substitutes into the raw action string
-> `bash -c <action>` -> bash passes the `<<'PYEOF'` heredoc body through
**verbatim, no expansion** -> `python3` parses the body as source. This
removes the bash-expansion arrow; the Python-literal-parsing arrow at the end
is unchanged and stays out of this issue's scope.

### Decision Rules

N/A — no new gap kind, gate, or threshold. This is a mechanical shell-syntax
conversion (`-c "..."` → `<<'PYEOF'`) with no new decision logic; the
per-site classification of which sites qualify (a `${context.*}`/`${captured.*}`
interpolation inside the Python-literal body of a *live shell* invocation) is
inherited from the parent EPIC-3336's sweep classification rule, not
introduced here.

### Sites requiring more than a 1:1 token swap

Per the analyzer's findings, a plain "replace `python3 -c \"` with
`python3 << 'PYEOF'` and the closing `\"` with `PYEOF`" transform is
insufficient at several confirmed sites — each needs structural handling
beyond the token swap, listed here as constraints the implementer must satisfy
rather than a prescribed rewrite:

- `oracles/code-run-gate.yaml:438` — the `-c "..."` call is the condition
  expression of `if ! python3 -c "..."; then`. A heredoc cannot itself serve
  as an `if !` condition; the converted form must still produce a test-able
  exit status for that `if`.
- `autodev.yaml:1815-1824` and `autodev.yaml:1619-1653`,
  `general-task.yaml:895-902` — the `-c "..."` body is piped from another
  command and/or wrapped in `$(...)` command substitution with a
  `2>/dev/null || echo ...` fallback appended after the closing quote. The
  converted heredoc's terminator must still resolve at column 0 while nested
  inside the substitution, and the fallback semantics after the block must be
  preserved.
- `autodev.yaml:1619-1653` additionally closes its `-c "..."` string on the
  same physical line as the final statement (no line break before the closing
  `"`), unlike `loop-router.yaml`'s pattern where the closing quote sits alone
  on its own line.
- `rn-plan-apo.yaml:48` and the repeated one-line `autodev.yaml`
  `| python3 -c "import json,sys; print(...)" \` invocations are single-line,
  semicolon-separated `-c` bodies with no existing multi-line structure;
  converting to a heredoc changes them from an inline pipeline expression to a
  multi-line block, which affects the surrounding pipe/line-continuation
  structure and must be accounted for.
- `general-task.yaml:895-902` — the interpolated value carries a
  `:default={}` suffix whose literal contains a `{`/`}` pair, which sits
  inside both the FSM's own `${...}` interpolation syntax and a Python
  single-quoted string. This interacts with `interpolation.py`'s suffix
  parsing, not just bash quoting — verify the substituted text still parses
  correctly after conversion.

`loop-router.yaml:31-79` (`discover_loops`) and `lib/composer.yaml:18-79`
(the equivalent fragment) have no nested `"`, no `$(...)`, and no backticks in
their bodies — a literal token swap is sufficient there, matching the
already-converted precedent states in the same files.

## Implementation Steps

1. The 9 confirmed sites (Integration Map → Files to Modify) resolve to a
   quoted heredoc (`python3 << 'MARKER' ... MARKER`) with bash performing no
   expansion on the body, and their `${context.*}`/`${captured.*}`
   interpolations land unchanged inside the Python source — the conversion is
   behavior-neutral for the Python body itself.
2. Each of the structural complications listed under Program Design → Sites
   requiring more than a 1:1 token swap is resolved without changing the
   surrounding control flow's observable behavior (the `if !` condition at
   `code-run-gate.yaml:438` still gates on the same pass/fail outcome; the
   `$(...) || echo ...` fallbacks in `autodev.yaml`/`general-task.yaml` still
   fall back the same way on error).
3. `harness-optimize.yaml:160-165` is excluded from this conversion (or its
   `action_type: prompt` status is re-verified if that turns out to be wrong)
   — it is not a live shell invocation.
4. `rn-build.yaml`'s 10 `python3 -c "` occurrences are checked individually
   for a `${context.*}`/`${captured.*}` interpolation inside the literal body
   before being included in or excluded from this issue's scope — this pass
   could not confirm either way.
5. `ll-loop validate` reports no new MR-11 warnings on every converted file,
   and no loop sets `unsafe_context_interpolation_ok` to suppress one.
6. The FSM interpolates the whole action string, comments included
   (`reference_fsm_action_interpolated_before_bash`) — any comment near a
   converted site that quotes a `${context.*}`/`${captured.*}` token is
   converted or `$${`-escaped in the same edit, not left to interpolate
   independently.

## Acceptance Criteria

1. Every site listed under Integration Map → Files to Modify is converted
   from `python3 -c "..."` to a quoted heredoc; `ll-loop validate` passes
   clean (no new MR-11 warnings) on `loop-router.yaml`, `sft-corpus.yaml`,
   `autodev.yaml`, `lib/composer.yaml`, `oracles/oracle-capture-issue.yaml`,
   `oracles/code-run-gate.yaml`, `rn-plan-apo.yaml`, and `general-task.yaml`.
2. `harness-optimize.yaml`'s `action_type: prompt` status is confirmed (or the
   site is converted, if that status turns out to be wrong), and the decision
   is recorded.
3. `rn-build.yaml`'s scope status (in or out of this issue) is resolved and
   recorded, based on an individual check of its 10 `python3 -c "` sites.
4. The structural sites (`code-run-gate.yaml:438`, `autodev.yaml:1619-1653`,
   `autodev.yaml:1815-1824`, `general-task.yaml:895-902`,
   `rn-plan-apo.yaml:48`) preserve their existing control-flow/fallback
   behavior after conversion — verified by running the affected loop states
   (or their existing test coverage) before and after.
5. No behavior change to the Python body's logic in any converted site —
   only the shell-invocation shape changes.

## Impact

- **Priority**: P2 — inherited from parent EPIC-3336/BUG-3331. Each affected
  site is both an availability bug (an interpolated value containing `"` or
  `$` breaks the shell tokenizing, not just the Python parse) and a shell
  injection (operator/LLM-controlled text reaching `bash -c` unquoted).
- **Effort**: Small–Medium — a mechanical per-site rewrite across 9 confirmed
  files (see Integration Map), but several sites are not a pure 1:1 token swap
  (see Program Design → Call Path and the flagged complications below);
  `ll-loop validate` must be run and stay clean on each converted file.
- **Risk**: Medium — per the parent EPIC's Impact analysis, this is "the only
  step that changes shell structure rather than a token, so it is the one that
  can break a working loop." A missed or malformed conversion is invisible
  until the affected state runs.
- **Breaking Change**: No — internal to loop action bodies; the Python
  behavior in each converted body is unchanged.

## Status

**Open** | Created: 2026-08-27 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-27T19:51:04 - `121602fa-f1cf-4559-9d22-a1a9e5682b74.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
