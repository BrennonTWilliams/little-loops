---
id: ENH-2702
title: Score template detection by match count instead of first-alphabetical
type: ENH
priority: P4
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-20T05:41:21Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
labels:
- init
- cli
- detection
confidence_score: 97
outcome_confidence: 70
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 18
---

# ENH-2702: Score template detection by match count instead of first-alphabetical

## Summary

`detect_project_type()` (scripts/little_loops/init/detect.py:124-211) treats
detection as boolean: a template matches if *any one* of its `_meta.detect`
globs hits, and on multi-match the winner is simply the first alphabetically
(`matches[0]`, detect.py:202-204). There is no scoring or specificity
weighting; `detect_exclude` is the only disambiguation mechanism and must be
hand-maintained pairwise (today it only covers typescript-vs-javascript).

## Current Behavior

- A polyglot repo with both `Cargo.toml` and `pyproject.toml` resolves to
  whichever template sorts first alphabetically, regardless of which stack
  dominates.
- Adding any new template with an overlapping detect set requires remembering
  to add `detect_exclude` entries or accepting alphabetical accidents.

## Expected Behavior

Among matching templates, the winner is the one with the strongest evidence:
score = number of `detect` globs that matched, with an optional
`_meta.priority` weight as tie-breaker. `detect_exclude` keeps working as a
hard veto. Ties after scoring fall back to the current alphabetical order so
existing behavior is preserved where evidence is equal.

## Proposed Solution

- In the match loop, count matched globs per template instead of
  short-circuiting on `any()`.
- Sort matches by `(-match_count, -meta.get("priority", 0), filename)` and
  return the head.
- Print the runner-up on multi-match (`Detected: Python (Generic) —
  3/3 indicators; also matched: Rust (1/2)`), so the choice is visible and
  overridable rather than silent.
- Consider a `--type <template>` CLI override flag for explicit selection
  (useful for polyglot repos regardless of scoring quality).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Match loop today** (`scripts/little_loops/init/detect.py:124-211`,
  `detect_project_type()`): iterates `_load_templates()`'s output, which is
  already alphabetically sorted (`sorted(templates_dir.glob("*.json"))`,
  `detect.py:56`) — this sort order is *why* `matches[0]` behaves as
  "first alphabetical" today (`detect.py:202-204`). The per-template check is
  `any(_glob_match(f, root) for f in detect_files)` (line ~185) — a boolean
  short-circuit with no count. The count-based rewrite is a small delta:
  replace that `any()` with `sum(_glob_match(f, root) for f in detect_files)`
  and only treat a template as a candidate when the sum is `> 0`. The
  `detect_exclude` veto check (line ~189) runs unconditionally on any
  surviving candidate — it should stay a hard veto independent of match
  strength, matching the ENH's expected behavior.
- **`_glob_match(pattern, root) -> bool`** (`detect.py:48-50`) is the only glob
  primitive in use; it already returns a bool per (pattern, root) call, so
  counting is `sum(...)` over the existing calls — no new glob utility
  needed.
- **`_meta.priority` already exists in the data**, but only on one template:
  `scripts/little_loops/templates/generic.json:7` (`"priority": -1`), used
  purely as a fallback marker today — `detect_project_type()` never reads
  `meta.get("priority", ...)` anywhere. No other shipped template
  (`python-generic.json`, `go.json`, `rust.json`, `dotnet.json`,
  `java-gradle.json`, `java-maven.json`, `typescript.json`, `javascript.json`)
  has a `priority` key. The proposed `meta.get("priority", 0)` tie-breaker is
  additive — it won't change behavior for any template until one explicitly
  sets a non-zero priority.
- **Established sort-key convention for this exact shape** — `(-primary,
  -secondary, tiebreaker)` tuple sort with a stable string tail to keep ties
  deterministic — already exists in `scripts/little_loops/fsm/route_table.py:389`
  (`sorted(_ALL_OPS, key=lambda op: (-len(op), op))`, with a comment
  explaining the alphabetical tail exists because `frozenset` iteration order
  is `PYTHONHASHSEED`-randomized) and in
  `scripts/little_loops/issue_history/hotspots.py` (`sort(key=lambda h:
  (-h.bug_ratio, -h.issue_count))`) and
  `scripts/little_loops/issue_history/coupling.py:75`
  (`sort(key=lambda p: (-p.coupling_strength, -p.co_occurrence_count))`).
  `(-match_count, -meta.get("priority", 0), filename)` follows this same
  established pattern.
- **Call sites that need the runner-up messaging threaded through** (all call
  `detect_project_type()` with no override param today):
  - `scripts/little_loops/init/cli.py:359-360` (`_run_yes()`) — prints
    `f"Detected project type: {template.name}"` with no alternatives shown.
  - `scripts/little_loops/init/cli.py:465,472-477` (`_run_plan()`) — packs
    `template.filename`/`template.name` into a `"detected"` JSON block with no
    candidates array; a runner-up field would need a new key here.
  - `scripts/little_loops/init/tui.py:253-259` (`run_tui()`) — Rich console
    banner, name-only.
  - `_run_apply()` (`cli.py:491+`) does **not** call `detect_project_type()`
    — it consumes an already-produced plan, so it's out of scope for this
    change.
- **`--type` flag naming collision to be aware of**: `scripts/little_loops/cli_args.py:387-395`
  already defines `add_type_arg()` registering `--type/-T` for *issue-type*
  filtering (`BUG`/`FEAT`/`ENH`/`EPIC`), used across `ll-issues`/`ll-history`
  subcommands. That's a different CLI (`ll-issues`, not `ll-init`) so there's
  no literal argparse conflict, but the flag name is already an established
  convention with different semantics in this codebase — worth a docstring
  note if `--type <template>` is added to `ll-init` to avoid user confusion.
  `ll-init`'s own flags (`--yes`, `--force`, `--dry-run`, `--plan`, `--hosts`,
  `--enable`/`--disable`, `--upgrade`, `--root`) are all registered inline in
  `main_init()` (`scripts/little_loops/init/cli.py:609-687`), not via
  `cli_args.py` — a new `--type` flag should follow that same inline-registration
  convention rather than adding a shared helper.

> ⚠ **Anchor refresh** (`/ll:refine-issue`, 2026-07-20): `detect.py` line
> references above are still exact (`any()` check at line 185, `detect_exclude`
> veto at line 189, `matches[0]` at line 204 — file is unchanged at 211 lines).
> The `cli.py`/`tui.py` line numbers have drifted from unrelated edits since the
> last refine pass and should be re-verified at implementation time:
> `_run_yes()`'s `print(f"Detected project type: ...")` is now at
> `cli.py:376` (was 359-360); `_run_plan()`'s `"detected"` block is now at
> `cli.py:522-527` (was 465, 472-477); `main_init()` now starts at `cli.py:637`
> and runs to end-of-file (836 lines total; was 609-687). `tui.py`'s banner
> line (`f"... detected [cyan]{template.name}..."`) is at `tui.py:258` (was
> 253-259) — this one is still accurate.

## Acceptance Criteria

- Fixture: repo with `pyproject.toml` + `setup.py` + `requirements.txt` and a
  lone `go.mod` resolves to python-generic (3 matches beat 1), not
  alphabetical `go.json`.
- typescript/javascript exclusion behavior is unchanged (existing tests pass).
- Multi-match prints the alternatives considered.
- `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/detect.py` — `detect_project_type()`
  (lines 124-211): replace the `any()` match check with a per-template match
  count, veto via `detect_exclude` unconditionally as today, sort surviving
  candidates by `(-match_count, -meta.get("priority", 0), filename)`. The
  `TemplateMatch` dataclass (lines 22-30) likely needs a `match_count` field
  (or the caller computes runner-up display separately) to support the
  "also matched" print.
- `scripts/little_loops/init/cli.py` — `_run_yes()` (line 359-360) and
  `_run_plan()` (line 465, 472-477): surface runner-up info in the printed
  message / plan JSON `"detected"` block.
- `scripts/little_loops/init/tui.py` — `run_tui()` (line 253-259): surface
  runner-up info in the Rich console banner.
- `scripts/little_loops/init/cli.py` — `main_init()` (lines 609-687): add the
  optional `--type <template>` override flag, inline per existing convention
  (not via `cli_args.py`).

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` — **conditional on the `--type` override flag being
  implemented**: the frontmatter `description` (line 10) enumerates
  passthrough flags (`--yes, --force, --dry-run, --hosts, --codex`) and the
  body's bash flag-extraction logic (~line 35, assembled ~line 48) has no
  conditional for `--type`. Without this update, `/ll:init --type <x>` would
  silently drop the flag instead of forwarding it to `ll-init` [Agent 2
  finding].

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/core.py:77` (`build_config()`) — consumes the
  winning `TemplateMatch`; unaffected by scoring changes as long as the
  `TemplateMatch` shape stays compatible.
- `scripts/little_loops/init/tui.py:254-255` — reads `template.data` /
  `template.meta.get("command_options", {})` from the returned match.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/introspect.py:22` (`introspect(root, template)`)
  — imports and takes `TemplateMatch` as a parameter, wrapping it in
  `IntrospectResult`; only reads existing fields, so additive-safe, but this
  is a real caller missing from the map above [Agent 1/2 finding].
- `scripts/little_loops/init/__init__.py` (lines 4, 34, 40, 46) — re-exports
  `TemplateMatch` and `detect_project_type` as public API; a new
  `match_count` field on the frozen `TemplateMatch` dataclass flows through
  automatically but has no default value, so **every direct
  `TemplateMatch(...)` construction site must add the new field** —
  confirmed construction sites besides `detect_project_type()` itself are
  test fixtures (`_make_match()` in `test_init_core.py`) [Agent 2 finding].
- `scripts/little_loops/cli/__init__.py:96` — re-exports `main_init` from
  `little_loops.init.cli`; no change needed unless `main_init()`'s signature
  changes (it won't — `--type` is an internal argparse addition) [Agent 1
  finding, FYI only].

### Similar Patterns
- `scripts/little_loops/fsm/route_table.py:389` — `(-len(op), op)` tuple sort
  with deterministic alphabetical tail.
- `scripts/little_loops/issue_history/hotspots.py` and
  `scripts/little_loops/issue_history/coupling.py:75` — `(-primary,
  -secondary)` descending sort-key convention already used elsewhere in this
  codebase.

### Tests
- `scripts/tests/test_init_core.py` — `TestDetectProjectType` (lines
  310-367): existing single-glob and `detect_exclude` tests
  (`test_js_excluded_by_tsconfig`, `test_js_matched_without_tsconfig`,
  `test_fallback_to_generic_on_no_match`) must keep passing unchanged.
- `scripts/tests/test_init_core.py:380-406` — `test_real_template_detection`
  (parametrized over all 9 real templates + `[]` → generic fallback): the
  natural place to add a polyglot multi-match case (per the Acceptance
  Criteria fixture) since it already exercises the real bundled
  `templates/` dir via the `templates_dir` fixture (line 56-59).
- `scripts/tests/test_init_core.py:56-239` — `fake_templates`/`tmp_project`
  fixtures and `_make_match()` helper (lines 242-253) for constructing a
  `TemplateMatch` by hand if a test needs to assert on runner-up display
  without going through full glob matching. **Note**: this helper is a
  second direct-construction site for `TemplateMatch` — if a `match_count`
  field is added without a default, `_make_match()` must be updated in
  lockstep or every test using it breaks [Agent 2 finding].

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py:1537` — `test_plan_emits_json`: asserts
  only `"detected" in plan` (key presence), not sub-key values — safe
  against the scoring change, but should be extended to assert
  `plan["detected"]` contains runner-up info once that's added [Agent 3
  finding].
- `scripts/tests/test_init_core.py:1594` — `test_unknown_feature_flag_exits_2`
  is the established pattern for an invalid-value CLI flag (exit 2, message
  in stderr, no config written) — follow this shape for a `--type
  <template>` validation test (unknown template name) [Agent 3 finding].
- `scripts/tests/test_init_core.py:1615` — `test_plan_reflects_feature_flags`
  is the established pattern for asserting a flag's effect surfaces in
  `plan["proposed_config"]` under `--plan` — directly applicable to
  verifying `--type` overrides `plan["detected"]["template_name"]` [Agent 3
  finding].
- `scripts/tests/test_init_tui.py` — no test currently greps/asserts the
  Rich console banner text (`tui.py:257-259`); the two fixtures that call
  `detect_project_type()` directly (`TestBuildFinalConfig.generic_template`
  line ~550-555, `TestBuildFinalConfigParity.generic_template` line
  ~1088-1093) always resolve to the generic fallback against an empty
  `tmp_path`, so they're unaffected by match-count scoring — flagged as
  covered-but-shallow, not a gap requiring new assertions [Agent 1/3
  finding].
- `scripts/tests/test_init_introspect.py` — imports `detect_project_type`
  for manifest-derived-command integration tests; should be re-run (not
  necessarily edited) since `introspect()` consumes `TemplateMatch` [Agent 1
  finding].
- `scripts/tests/integration/test_init_e2e.py` — real end-to-end tests via
  `_run_init()` against real bundled templates. All current fixtures use
  empty `tmp_path` project dirs that resolve to the generic fallback
  regardless of scoring algorithm (low risk), but this is the
  highest-risk test file for a live behavior shift if any two real
  templates in `scripts/little_loops/templates/*.json` share overlapping
  `detect` globs where match-count changes the winner vs. today's
  alphabetical order — worth a manual check against the real template set
  at implementation time. No test in this file asserts stdout content, so
  print-message changes won't break it [Agent 2/3 finding].
- Sort-key testing convention: `scripts/tests/test_ll_loop_edit_routes.py`
  (`test_cond_pattern_ops_match_all_ops` line 893,
  `test_parse_cond_cell_longest_match_gte` line 904) is the closer
  precedent for this issue's `(-match_count, -priority, filename)` sort —
  combines a regression guard against the old naive behavior, an
  exhaustive-domain gate, and a specific tie-break-winner test. Mirror this
  shape: N-glob-match beats 1-glob-match regardless of alphabetical order,
  equal match-count falls through to priority, equal match-count+priority
  falls through to filename [Agent 3 finding].

### Documentation
- No dedicated docs page for template-detection internals was found; no
  doc update appears required beyond the issue itself.

_Wiring pass added by `/ll:wire-issue`: this claim covers detection
**internals** only — the following user-facing surfaces DO need updates,
found by tracing beyond the internals-only search above:_
- `docs/reference/CLI.md`, `### ll-init` section — has no `--type` row
  today; if the `--type <template>` override flag is implemented, add one
  here worded distinctly from the *other* `--type`/`-T` rows this same doc
  already documents for `ll-issues`/`ll-auto`/`ll-parallel`/`ll-sprint`
  (issue-type filtering, different semantics) — otherwise a reader could
  conflate the two [Agent 2 finding].
- `docs/guides/GETTING_STARTED.md` — has its own ll-init flag table
  (~lines 95-100, missing `--type`) and a "Detected project types" prose
  block (~line 73) that describes detection at a high level but not the
  alphabetical-tiebreak-vs-scoring behavior; update both if the override
  flag or scoring behavior should be user-facing documented [Agent 2
  finding].
- `skills/init/SKILL.md`, frontmatter `description` (line 10) — explicitly
  enumerates the flags this skill wrapper passes through: `"Optional
  flags: --yes, --force, --dry-run, --hosts, --codex"`. **This list omits
  `--type` today, and the skill body's bash flag-extraction logic (~line
  35, assembled at ~line 48) has no conditional for it** — if `--type` is
  implemented on `ll-init` but not wired through this skill, invoking
  `/ll:init --type <template>` would silently drop the flag rather than
  forward it to `ll-init` [Agent 2 finding — moved to Files to Modify
  below since this is a functional gap, not just a docs gap].

## Scope Boundaries

- **In**: scoring within the existing single-winner model; visibility of the
  decision.
- **Out**: multi-template / polyglot merged configs (a repo still gets exactly
  one template); template content changes.

## Impact

- **Priority**: P4 — least urgent in the epic; `detect_exclude` already covers
  the one real collision shipped today. Value grows with template count.
- **Effort**: Small.
- **Risk**: Low — tie behavior preserves current ordering.

## Status

**Open** | Created: 2026-07-19 | Priority: P4

## Resolution

Replaced the `any()` boolean match check with a per-template glob match
count. `detect_project_type()` is now a thin wrapper around the new
`detect_project_type_all()`, which returns the full candidate list sorted by
`(-match_count, -meta.priority, filename)` — index 0 is the winner, the rest
are runners-up. `detect_exclude` remains an unconditional hard veto. A new
`format_detection_summary()` helper renders "Detected: X — n/m indicators;
also matched: Y (k/j)" and replaces the old name-only print in `_run_yes()`
(cli.py) and the Rich banner in `run_tui()` (tui.py); `_run_plan()`'s
`"detected"` JSON block gained `match_count` and `runner_up` keys.
`TemplateMatch` gained a defaulted `match_count: int = 0` field so existing
direct-construction sites (fallback path, `_make_match()` test helper) keep
working unchanged.

`--type <template>` CLI override was left out of scope — it was "Consider" in
the Proposed Solution, not in the Acceptance Criteria.

## Session Log
- `/ll:manage-issue` - 2026-07-20T05:40:50Z - `972ed3f7-7dc0-45b6-84f2-87e44802d703.jsonl`
- `/ll:ready-issue` - 2026-07-20T05:33:05 - `69ba6a83-d807-4e01-ad6a-f8465c6ceae4.jsonl`
- `/ll:wire-issue` - 2026-07-20T05:29:27 - `85578b13-5934-4dd2-9984-2a5c178628a6.jsonl`
- `/ll:refine-issue` - 2026-07-20T05:22:50 - `0e52c174-61b1-4c97-a898-72a5570ae694.jsonl`
- `/ll:refine-issue` - 2026-07-19T23:04:20 - `c0ad722f-fe1d-4ab6-8062-9c79877dc3cc.jsonl`
