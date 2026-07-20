---
id: ENH-2702
title: Score template detection by match count instead of first-alphabetical
type: ENH
priority: P4
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
labels:
- init
- cli
- detection
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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/core.py:77` (`build_config()`) — consumes the
  winning `TemplateMatch`; unaffected by scoring changes as long as the
  `TemplateMatch` shape stays compatible.
- `scripts/little_loops/init/tui.py:254-255` — reads `template.data` /
  `template.meta.get("command_options", {})` from the returned match.

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
  without going through full glob matching.

### Documentation
- No dedicated docs page for template-detection internals was found; no
  doc update appears required beyond the issue itself.

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


## Session Log
- `/ll:refine-issue` - 2026-07-19T23:04:20 - `c0ad722f-fe1d-4ab6-8062-9c79877dc3cc.jsonl`
