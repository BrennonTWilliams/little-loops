---
id: BUG-3339
type: BUG
title: Convert python3 -c heredoc-unsafe invocations to quoted heredocs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocked_by:
- ENH-3337
- ENH-3338
blocks:
- BUG-3340
- BUG-3341
- ENH-3347
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 62
score_complexity: 9
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3339: Convert python3 -c heredoc-unsafe invocations to quoted heredocs

## Summary

Convert every `python3 -c "..."` interpolation site carrying a
`${context.*}`/`${captured.*}` value in its Python-literal body to a quoted
`python3 << 'PYEOF'` heredoc, so they stop being shell-injectable, validating
each converted file with `ll-loop validate`.

**Site count is provisional.** The parent survey said "53 sites, 11 files"; this
issue's own research could confirm only **9 files** and ruled out
`harness-optimize.yaml` as a false positive (its enclosing state is
`action_type: prompt`), with `rn-build.yaml` unresolved. **ENH-3338's baseline is
the authoritative list** — reconcile against it rather than against the survey's
numbers, and record the reconciliation in EPIC-3336.

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

1. Run `loop-router`'s `discover_loops` state (or any of the confirmed
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
- `scripts/little_loops/loops/sft-corpus.yaml` — 9 states / 18 baseline var
  entries (lines 114, 136, 139, 156, 178, 198, 220, 240, 262, 319): the 4
  `check_*` states each carry `${captured.enrich_output.output}` (captured
  LLM output, class B) plus a `${context.*}` threshold key; the 5 `reject_*`
  states each carry `${captured.enrich_output.output}` plus
  `${context.output_dir}`. The heredoc conversion is interim at these class-B
  sites — BUG-3341 still owns the remaining Python-literal remedy for the
  captured LLM value.
- `scripts/little_loops/loops/autodev.yaml` — 4 confirmed groups:
  1619-1653 (`${context.run_dir}` at 1633/1640, `${context.readiness_threshold}`),
  1739-1746 (`${context.readiness_threshold}`),
  1815-1824 (`${context.readiness_threshold}`, `${context.outcome_threshold}`),
  2047-2054 (same pair repeated)
- `scripts/little_loops/loops/lib/composer.yaml` — `discover_loops` fragment
  (18-79), near-identical to loop-router's: `${context.include:default=}` (32),
  `${context.exclude}` (51), `${context.run_dir}` (baseline class C — the
  analog of loop-router's line-76 occurrence)
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` —
  `check_mechanical` (28-54): `${context.output}` (34, triple-single-quoted literal)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:438` —
  `${context.min_pass_rate}`, inside an `if ! python3 -c "..."; then` condition
- `scripts/little_loops/loops/rn-plan-apo.yaml:48` — `${context.tasks_file}`,
  single-line `-c` body redirected with `>`
- `scripts/little_loops/loops/general-task.yaml` — 2 sites:
  `summarize_success` (895-902, `${captured.final_counts.output:default={}}`,
  wrapped in `$(...) || echo 0`) and `check_abandoned_route` (934-943,
  `${context.run_dir}`, class C, `action_type: shell`) — the latter is a
  plain token-swap conversion, but its `evaluate: type: output_numeric`
  means the converted heredoc must preserve stdout exactly (the printed
  count is the routing signal)
- `scripts/little_loops/loops/harness-optimize.yaml` — `load_directive`
  (39-45, `action_type: shell`): `${context.run_dir}` (45), closed on the same
  physical line with a trailing `2>/dev/null || true`. Distinct from the
  already-excluded `apply` state (160-165, `action_type: prompt`) — see
  "Not in scope" below, which covers `apply` only.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml` —
  `validate-classification` (143-159, `action_type: shell`,
  `evaluate: type: exit_code` directly on the state, no `if !` wrapper):
  `${captured.run_dir.output}` (149). No existing heredoc conversion anywhere
  in this file — this would be the file's first.
- `scripts/little_loops/loops/workflow-generator.yaml` — 5 sites, all
  `${captured.run_dir.output}`, all state-level `evaluate: type: exit_code`
  with no `if !` wrapper: `validate_intent` (212, output piped to `tee` with
  an explicit `RC=$?`/`exit "$RC"` after), `validate_sketch` (391),
  `validate_evaluators` (474), `validate_routing` (525),
  `shrink_select_candidate` (683, 3 occurrences merged into one baseline
  entry). This file already has 3 in-file heredoc conversions
  (`shrink_baseline`, `shrink_try_remove`, `shrink_probe_candidate`) as
  before/after precedent — see Conventions in Force.

**Not in scope — verified:**
- `scripts/little_loops/loops/harness-optimize.yaml:160-165` (the `apply`
  state) — textually matches `python3 -c "..."` but its enclosing state has
  `action_type: prompt` (line 145), not `shell`. `runners.py` only shells out
  for `action_type: shell`/`None`, and MR-11 itself skips non-shell states
  (`shell_safety.py:165`). This exclusion covers only `apply` — the same
  file's `load_directive` state (above) is a separate, in-scope site.
- `scripts/little_loops/loops/rn-build.yaml` — all 10 `python3 -c "`
  occurrences (lines 559, 798, 826, 953, 974, 979, 984, 1216, 1329, 1363)
  individually checked; none carries a `${context.*}`/`${captured.*}`
  interpolation inside the Python-literal body (each threads the value in via
  `sys.argv[...]`/`os.environ[...]` instead). Corroborated by ENH-3338's
  baseline: all 6 of this file's entries are `host_shape="heredoc"`, none
  `"c-string"`. Confirmed out of scope.

The confirmed list is **11 files** (matching the baseline exactly): the 8
from the original pass, plus `harness-optimize.yaml`,
`cli-anything-bootstrap.yaml`, and `workflow-generator.yaml`, added by
reconciling against ENH-3338's now-landed baseline
(`scripts/tests/data/loop_interpolation_baseline.json`, filtered to
`host_shape == "c-string"` → 45 sites, 11 files) — the authoritative source
per this issue's Summary. An earlier revision of this issue said "12 files"
— an arithmetic error that double-counted `harness-optimize.yaml`. The
parent survey's original "53 sites, 11 files" figure is also superseded by
the baseline; do not reconcile against the survey.

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
- File-specific coverage for the 11 confirmed target files:
  `scripts/tests/test_loops_sft_corpus.py` (sft-corpus.yaml),
  `scripts/tests/test_autodev_loop.py` (autodev.yaml). No file-specific test
  module was found for `loop-router.yaml`, `lib/composer.yaml`,
  `oracles/oracle-capture-issue.yaml`, `oracles/code-run-gate.yaml`,
  `rn-plan-apo.yaml`, `general-task.yaml`, `harness-optimize.yaml`,
  `cli-anything-bootstrap.yaml`, or `workflow-generator.yaml` in this pass —
  `ll-loop validate` is the applicable check for those.

### Documentation

- N/A — no documentation currently describes the `-c "` vs. heredoc host
  shapes; `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` is where the parent EPIC
  plans to document the resulting idiom (its Implementation Step 10, not this
  issue's).

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **`rn-build.yaml` scope resolved**: all 10 `python3 -c "` occurrences (lines 559, 798, 826, 953, 974, 979, 984, 1216, 1329, 1363) individually checked — none carries a `${context.*}`/`${captured.*}` interpolation inside the Python-literal body; each instead threads the value in via `sys.argv[...]` or `os.environ[...]` set by a preceding shell assignment. `rn-build.yaml` is out of scope for this issue's conversion.
- **`harness-optimize.yaml:160-165` scope confirmed**: the enclosing `apply` state (header at line 144) has `action_type: prompt` (line 145), not `shell` — confirmed excluded, matching the issue's own citation exactly.
- **No line-number drift on any of the 9 confirmed sites** despite commit d8d3476a1 (BUG-3349, done) touching both `loop-router.yaml` and `fsm/interpolation.py` after this issue's last refine — every cited file/line still matches, still unconverted.
- `loop-router.yaml`'s `finalize_present_result` heredoc precedent now spans lines 509-560 (was cited 509-557) — a small line-count drift from BUG-3349's own fix (which changed the state's Python body, not its heredoc wrapper), not a shape change; it remains valid as the "already-converted heredoc shape" precedent.

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **ENH-3338 has landed since this issue's last refine** (status: done, commit `ba3c2c3bf`) — the sibling static-sweep issue this issue's Summary calls the not-yet-existing "authoritative list" now exists: `scripts/little_loops/fsm/interp_sweep.py` + checked-in ratcheting baseline `scripts/tests/data/loop_interpolation_baseline.json` (225 total sites). Filtering that baseline to `host_shape == "c-string"` yields **45 sites across 11 files** — a strict superset of this issue's hand-researched 9-file list, adding three files/sites this issue's prior passes did not catch.
- **`harness-optimize.yaml` has a second, in-scope site distinct from the already-excluded `apply` state.** The `load_directive` state (`harness-optimize.yaml:39-45`, `action_type: shell` — a real shell state, unlike `apply`'s `action_type: prompt`) contains a live, unconverted `python3 -c "import yaml,json; ... open('${context.run_dir}/harness-optimize-state-queue.txt','w')..."` (baseline: `var=context.run_dir`, `class=C`, line 45). The existing "Not in scope" exclusion of `harness-optimize.yaml:160-165` (the `apply` state) remains correct on its own terms — it just does not cover the whole file. `load_directive`'s `-c` body is single-quoted-literal-only (no f-string double-quote escaping) but is terminated on the same physical line with a trailing `2>/dev/null || true`, structurally similar in kind (single-line closure + fallback) to `rn-plan-apo.yaml:48`'s already-flagged complication.
- **`cli-anything-bootstrap.yaml` — one new confirmed site.** `validate-classification` state (`cli-anything-bootstrap.yaml:143-159`, `action_type: shell`, `evaluate: type: exit_code` directly on the state, no `if !` wrapper) — `python3 -c "..."` interpolates `${captured.run_dir.output}` (baseline: `var=captured.run_dir.output`, `class=B`, line 149). The file's other 5 `python3 -c` occurrences (lines 215, 299, 328, 329, 330) reference only bash-local variables inside the Python literal, not a direct `${context.*}`/`${captured.*}` token, and are not baseline-flagged. No existing heredoc conversion exists anywhere in this file (no `PYEOF`/`PY` delimiter present) — this would be the file's first.
- **`workflow-generator.yaml` — five new confirmed sites**, all `var=captured.run_dir.output`, `class=B`: `validate_intent` (line 212, output piped to `tee`, explicit `RC=$?`/`exit "$RC"` after — needs the same testable-exit-status handling as the `$(...) || echo` fallback sites already flagged under Program Design), `validate_sketch` (line 391), `validate_evaluators` (line 474), `validate_routing` (line 525), `shrink_select_candidate` (line 683, 3 occurrences of the same var merged into one baseline entry). This file already contains 3 in-file heredoc conversions (`shrink_baseline`, `shrink_try_remove`, `shrink_probe_candidate`) as before/after precedent for its own remaining unconverted sites — see Conventions in Force.
- **`rn-build.yaml`'s absence from the baseline's c-string file list independently corroborates this issue's manual finding.** The baseline contains 6 `rn-build.yaml` entries, all `host_shape="heredoc"`, none `"c-string"` — none of the file's 10 `python3 -c "` occurrences carries a scannable `${context.*}`/`${captured.*}` token inside the Python-literal body, matching the per-site check already recorded here.
- **Corrected count for AC #6 reconciliation**: the confirmed-site file count is **11**, matching the baseline's `host_shape == "c-string"` file set exactly (45 sites / 11 files). An earlier revision said 12 — an arithmetic error double-counting `harness-optimize.yaml` (it was both in the prior confirmed list and counted again among the reconciliation additions).

_Added by pre-implementation review — 2026-08-28 — verified against baseline + live YAML:_

- **Missed site caught: `general-task.yaml:check_abandoned_route` (934-943).** A second c-string site in `general-task.yaml` — `action_type: shell`, `python3 -c "..."` with `${context.run_dir}` in the Python body, present in the baseline (`class=C`) but absent from every prior revision of this issue's site list. Plain token-swap conversion; its `evaluate: type: output_numeric` requires the converted heredoc to preserve stdout exactly. Now listed in Files to Modify.
- **`lib/composer.yaml` carries a third baseline var**: `context.run_dir` (class C), the analog of loop-router's line-76 occurrence — added to its Files to Modify entry.
- **`sft-corpus.yaml` var description corrected**: prior text said "each `${context.output_dir}` plus a state-specific key"; the baseline shows the 4 `check_*` states carry `${captured.enrich_output.output}` (class B) + a `context.*` threshold key, and the 5 `reject_*` states carry `${captured.enrich_output.output}` + `${context.output_dir}` — 9 states, 18 var entries.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **No corpus precedent for wrapping a heredoc directly as an `if !` condition.** Every site in the loop corpus that branches on a heredoc's outcome instead runs the heredoc first (bare or `$(...)`-captured) and tests `$?` on the following line — e.g. `mechanize-skills.yaml:436-444`, and four sibling instances in `code-run-gate.yaml`'s own state family (`:214-215`, `:254-255`, `:304-305`, `:331-332`, `:387-388`). `code-run-gate.yaml:438`'s conversion needs to produce a testable `$?`/exit status for its enclosing `if !`, since no heredoc-as-condition shape exists to model it on.
- **No corpus precedent for piping command output directly into a heredoc's stdin** (`cmd | python3 << 'PYEOF'`) — a heredoc already occupies stdin, so this cannot be a literal conversion. The pipe-fed `-c "..."` sites this issue must convert (`autodev.yaml:1619,1739,1815`) have no existing heredoc analogue; the piped value must reach the heredoc some other way — e.g. the env-var-prefixed-invocation shape already used at `mechanize-skills.yaml:162` / `autodev.yaml:405` (`VAR="$VAR" python3 << 'PYEOF'`, read via `os.environ` inside the body) is an established pattern for getting a value into a heredoc without stdin.
- An FSM-level alternative exists for exit-code-based branching without any bash-level `if`: `fragment: shell_exit` / `evaluate: type: exit_code` (`lib/common.yaml:14-21`, used at `autodev.yaml:1731-1746`) routes on a whole state's exit code directly — a different granularity than `code-run-gate.yaml:438`'s single embedded statement inside a larger `aggregate` state.
- The corpus's existing idiom for embedding a `${context.*}` value as a Python literal directly inside a `<<'PYEOF'` heredoc (triple-quoted, e.g. `arg = """${context.scope}""".strip()` at `auto-refine-and-implement.yaml:144,215-216,352`) confirms a literal token swap is already a normal, used shape in this corpus — consistent with the plain conversion needed at `loop-router.yaml:discover_loops` and `lib/composer.yaml`.
- **ENH-3337 (blocked_by) is fully resolved (status: done).** An earlier draft of this finding claimed `cli/loop/run.py` and `fsm/validation/shell_safety.py` still recognized only a *trailing* `:shell`; both now call the shared `parse_interpolation_suffixes()` and accept any supported suffix ordering (verified against source 2026-08-28). No residual ENH-3337 scope blocks this issue.

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **New structural complication not in the existing "more than a 1:1 token swap" list: f-string double-quote escaping.** Three of the newly-confirmed sites contain Python f-strings that use double quotes, backslash-escaped to survive the outer bash double-quoted `-c "..."` string: `cli-anything-bootstrap.yaml:153` (`f\"unknown classification: {d.get('classification')}\"`), `workflow-generator.yaml:487` (`f\"state {s.get('name')!r} has disallowed evaluator {etype!r}\"`), `workflow-generator.yaml:536` (`f\"state {s.get('name')!r} has no routing\"`). A quoted heredoc is not shell-expanded, so a literal `\"` left inside it is invalid Python (a bare backslash before a quote outside a string literal) — the backslash-escaping must be removed as part of the conversion at these three sites specifically. `harness-optimize.yaml:load_directive` and `workflow-generator.yaml`'s other four new sites (`validate_intent`, `validate_sketch`, `shrink_select_candidate`) use only single-quoted Python literals and need no such de-escaping.
- **Precedent found for a bare heredoc paired directly with state-level `evaluate: type: exit_code` (no `if !` wrapper) — a plain heredoc conversion is sufficient for most of the newly-confirmed sites.** Confirmed independently at 4+ existing sites: `migrate-sdk-version.yaml:28-75` (`list_stale`), `proof-first-task.yaml:53-68` (`check_gate_blocked`), `loop-router.yaml:131-139` and `:145-153`, and `workflow-generator.yaml:734-777` (`shrink_probe_candidate`, already converted) — each is a bare `python3 << 'PYEOF' ... PYEOF` as the state's sole action content, terminating with `sys.exit(...)`/`raise SystemExit(...)`, with `evaluate: type: exit_code` attached directly beneath, no bash `if` in between. This is the exact shape of `cli-anything-bootstrap.yaml:validate-classification` and of `workflow-generator.yaml`'s `validate_sketch`, `validate_evaluators`, `validate_routing`, and `shrink_select_candidate` (all state-level `evaluate: type: exit_code`, no `if !`) — these 5 sites do not need `code-run-gate.yaml:438`-style structural rework, only the plain token-swap plus (where applicable) the f-string de-escaping noted above.
- **`workflow-generator.yaml:validate_intent` (line 212) needs its post-processing preserved**: output is piped to `tee`, followed by an explicit `RC=$?` capture and conditional `exit "$RC"`. The heredoc conversion must still leave the same testable `$?` available to the following lines — the same category of requirement as the existing `$(...) || echo ...` fallback sites (`autodev.yaml`/`general-task.yaml`), though structurally simpler (no `if !` wrapper, sequential commands only).
- **Reconfirmed: no corpus precedent exists anywhere for the `if !`-wrapped shape at `code-run-gate.yaml:438`.** Searched the full `scripts/little_loops/loops/` tree — this remains the only `if ! python3 ...` invocation in the corpus, unconverted; no other file offers a before/after example for that narrower structural class.
- **`workflow-generator.yaml`'s 3 existing in-file heredoc conversions** (`shrink_baseline:634-676`, `shrink_try_remove:699-732`, `shrink_probe_candidate:734-777`) use the file-local delimiter spelling `<<'PYEOF'` (no space before the quote) and interpolate `${captured.run_dir.output}` directly inside the heredoc body — in-file before/after precedent for this file's own 5 remaining unconverted sites, the same way `loop-router.yaml` already contains both shapes side by side. This file-local spelling diverges from the corpus-dominant `<< 'PYEOF'` (with space, 100+ occurrences) documented under Conventions in Force above — both are accepted by MR-11's marker-agnostic heredoc check.
- **`cli-anything-bootstrap.yaml` has no in-file heredoc precedent** — no `PYEOF`/`PY` delimiter exists anywhere in the file; its conversion at `validate-classification` would be the file's first, modeled on the cross-file bare-heredoc-plus-exit_code precedent above rather than an in-file example.

## Implementation Steps

1. Every confirmed site (Integration Map → Files to Modify; 45 baseline
   sites across 11 files) resolves to a
   quoted heredoc (`python3 << 'MARKER' ... MARKER`) with bash performing no
   expansion on the body, and their `${context.*}`/`${captured.*}`
   interpolations land unchanged inside the Python source — the conversion is
   behavior-neutral for the Python body itself. This includes the 3 files
   added by reconciling against ENH-3338's baseline: `harness-optimize.yaml`
   (`load_directive`), `cli-anything-bootstrap.yaml`
   (`validate-classification`), and `workflow-generator.yaml` (5 states).
2. Each of the structural complications listed under Program Design → Sites
   requiring more than a 1:1 token swap is resolved without changing the
   surrounding control flow's observable behavior (the `if !` condition at
   `code-run-gate.yaml:438` still gates on the same pass/fail outcome; the
   `$(...) || echo ...` fallbacks in `autodev.yaml`/`general-task.yaml` still
   fall back the same way on error).
3. `harness-optimize.yaml`'s `apply` state (160-165) is excluded from this
   conversion — it has `action_type: prompt`, not a live shell invocation.
   Its `load_directive` state (39-45, `action_type: shell`) is a separate,
   in-scope site and is converted along with the file's other confirmed
   sites.
4. `rn-build.yaml` is confirmed out of scope: all 10 of its `python3 -c "`
   occurrences were checked individually and none carries a
   `${context.*}`/`${captured.*}` interpolation inside the Python-literal
   body (each threads the value in via `sys.argv[...]`/`os.environ[...]`
   instead), corroborated by ENH-3338's baseline (all 6 of its entries are
   `host_shape="heredoc"`, none `"c-string"`).
5. `ll-loop validate` reports no new MR-11 warnings on every converted file,
   and no loop sets `unsafe_context_interpolation_ok` to suppress one.
6. `general-task.yaml:895-902`'s `:default={}` was already rewritten by
   ENH-3337 (its one in-scope YAML edit — a `}` inside a `:default=` is a hard
   `InterpolationError` after that issue lands). The heredoc conversion here
   **preserves** that rewrite; do not restore a brace-bearing default.
7. The FSM interpolates the whole action string, comments included
   (`reference_fsm_action_interpolated_before_bash`) — any comment near a
   converted site that quotes a `${context.*}`/`${captured.*}` token is
   converted or `$${`-escaped in the same edit, not left to interpolate
   independently.
8. **Final-form carve-out for structurally entangled sites** (review
   decision, 2026-08-28). The pipe-fed sites (`autodev.yaml:1619-1653`,
   `:1739-1746`, `:1815-1824`) cannot become pipe-fed heredocs — a heredoc
   occupies stdin, and this issue's own research found no corpus precedent
   for `cmd | python3 << 'PYEOF'` — and `code-run-gate.yaml:438` /
   `general-task.yaml:895-902` need structural rework either way. An
   intermediate heredoc form at these sites is throwaway work redone by
   BUG-3340/BUG-3341. At these sites, land the final remedy directly in this
   issue's edit — class-A values via the `LL_ARG_*=${...:shell}` env binding
   per BUG-3340's conventions (typed coercion included: `int(...)` for the
   `autodev.yaml` thresholds, `float(...)` for `min_pass_rate`); the class-B
   value at `general-task.yaml:895-902` via BUG-3341's canonical Option B
   block — shrinking the corresponding baseline entry in the same commit and
   noting the pre-conversion in the downstream issue. All blockers permit
   this: ENH-3337 is done.

## Acceptance Criteria

1. Every site listed under Integration Map → Files to Modify is converted
   from `python3 -c "..."` to a quoted heredoc; `ll-loop validate` passes
   clean (no new MR-11 warnings) on all 11 confirmed files, reconciled
   against ENH-3338's baseline: `loop-router.yaml`, `sft-corpus.yaml`,
   `autodev.yaml`, `lib/composer.yaml`, `oracles/oracle-capture-issue.yaml`,
   `oracles/code-run-gate.yaml`, `rn-plan-apo.yaml`, `general-task.yaml`,
   `harness-optimize.yaml`, `cli-anything-bootstrap.yaml`, and
   `workflow-generator.yaml`.
2. `harness-optimize.yaml`'s `apply` state (160-165) is confirmed
   `action_type: prompt` and stays excluded; its separate `load_directive`
   state (39-45, `action_type: shell`) is confirmed in-scope and converted
   along with the file's other confirmed sites.
3. `rn-build.yaml` stays out of scope, per the recorded individual check of
   its 10 `python3 -c "` sites (already resolved in Codebase Research
   Findings; re-verify only if the file changed since 2026-08-28).
4. The structural sites (`code-run-gate.yaml:438`, `autodev.yaml:1619-1653`,
   `autodev.yaml:1815-1824`, `general-task.yaml:895-902`,
   `rn-plan-apo.yaml:48`) preserve their existing control-flow/fallback
   behavior after conversion — verified by running the affected loop states
   (or their existing test coverage) before and after.
5. No behavior change to the Python body's logic in any converted site —
   only the shell-invocation shape changes.
6. The confirmed site list is reconciled against ENH-3338's baseline (filtered to
   `host_shape == "c-string"`), any divergence from the survey's "53 sites, 11
   files" is explained, and the reconciled count is recorded in EPIC-3336. The
   baseline — not the survey table — is what "every site" means.
7. `python -m pytest scripts/tests/` exits 0 at every commit of this issue.
   ENH-3338's baseline does **not** shrink for a plain heredoc conversion —
   its comparison key `(file, state, var, class)` deliberately excludes
   `host_shape`, so the site reads as unchanged; instead, update each
   converted entry's informational `host_shape` field from `c-string` to
   `heredoc` in the same commit. Only sites landed in final form under
   Implementation Step 8's carve-out shrink the baseline here.
8. Each structurally entangled site (Implementation Step 8) either received a
   behavior-preserving heredoc conversion or was landed directly in its final
   BUG-3340/BUG-3341 form, with the per-site choice recorded and the baseline
   updated accordingly; the downstream issue is annotated so it does not
   re-convert.

## Impact

- **Priority**: P2 — inherited from parent EPIC-3336/BUG-3331. Each affected
  site is both an availability bug (an interpolated value containing `"` or
  `$` breaks the shell tokenizing, not just the Python parse) and a shell
  injection (operator/LLM-controlled text reaching `bash -c` unquoted).
- **Effort**: Small–Medium — a mechanical per-site rewrite across 11 confirmed
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-28_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~28 change sites in 11 files (Breadth 0/12) — a high site count raises the odds one site is missed or malformed during the sweep, even though most sites are mechanical token swaps. (Pre-implementation review already caught one such miss — `general-task.yaml:check_abandoned_route` — now in the site list.)
- Only 2 of 11 target files (`sft-corpus.yaml`, `autodev.yaml`) have dedicated test modules; the other 9 rely solely on `ll-loop validate`, a structural/static linter that won't catch a behaviorally-broken Python body until the affected state actually runs — mitigate by exercising the structurally-entangled sites (`code-run-gate.yaml:438`, the `autodev.yaml` pipe-fed groups, `general-task.yaml:895-902`) directly per Acceptance Criterion #4.

## Session Log
- `/ll:confidence-check` - 2026-08-28T16:59:31 - `5e4f9ac6-d048-48b7-a0cd-6e184370a286.jsonl`
- `/ll:reconcile-issue` - 2026-08-28T16:54:12 - `1f800b67-df1c-4ef2-913d-0f4cba863bf8.jsonl`
- `/ll:refine-issue` - 2026-08-28T16:27:59 - `b3de8990-2254-46d0-8e9a-792563a8e929.jsonl`
- `/ll:refine-issue` - 2026-08-28T03:15:15 - `21c2bc4e-6e06-47c6-a164-ddb166a7cfff.jsonl`
- `/ll:format-issue` - 2026-08-28T03:03:20 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:refine-issue` - 2026-08-27T19:51:04 - `121602fa-f1cf-4559-9d22-a1a9e5682b74.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
