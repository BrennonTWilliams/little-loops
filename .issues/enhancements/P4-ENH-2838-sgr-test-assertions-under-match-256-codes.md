---
id: ENH-2838
type: ENH
priority: P4
status: done
captured_at: '2026-07-27T00:08:18Z'
completed_at: '2026-07-27T05:00:35Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- testing
- cli
- color
- tech-debt
confidence_score: 98
outcome_confidence: 90
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 23
---

# ENH-2838: SGR test assertions silently under-match multi-segment 256 codes

## Summary

Test assertions that match ANSI SGR sequences with a single-segment pattern
(`\033\[\d+m`, `\033\[\d+;1m`) cannot match indexed-256 codes, which are
multi-segment (`38;5;240`, `38;5;245;1`). Such an assertion keeps passing as
long as *any* basic-16 code in the output happens to satisfy it, so it degrades
into a weaker check than its name and docstring claim without ever failing.
One confirmed instance was fixed; the pattern should be audited repo-wide.

## Current Behavior

Confirmed instance —
`scripts/tests/test_ll_loop_display.py::TestRenderFsmDiagram::test_non_highlighted_state_name_bold`:

```python
assert "\033[1m" in result or re.search(r"\033\[\d+;1m", result) is not None
```

Its own docstring states the intent explicitly:

> Accept any SGR that ends with ``;1m`` before the name text.

But `\d+;1m` admits only a single numeric segment. The diagram's actual output
for that fixture is:

```
0  32  38;5;240  38;5;240;1  38;5;245  38;5;245;1
```

Every bold-bearing code is multi-segment, so the regex matched **none** of them.
The assertion passed only because `_ACTION_TYPE_KIND_COLORS["shell"]` was basic
`90`, yielding `90;1m`. It had therefore **already** stopped covering the
pre-existing `_TERMINAL_KIND_COLOR` (`38;5;245;1`) — the loss was invisible
because one basic code was still carrying the assertion.

The failure only surfaced when `shell` was pinned to `38;5;240`, at which point
the test went red and could easily have been misread as a real regression in
bold rendering. (It was not: bold was verified still present as `38;5;240;1`
before the assertion was touched.)

## Expected Behavior

SGR assertions match the full code grammar: one or more `;`-separated numeric
segments. The fix applied to the confirmed instance:

```python
# ``[\d;]+`` not ``\d+``: kind colors may be multi-segment indexed-256
# codes, so the compounded form is e.g. ``\033[38;5;240;1m``.
assert "\033[1m" in result or re.search(r"\033\[[\d;]+;1m", result) is not None
```

## Motivation

This is a silent-coverage-loss class of bug, not a one-off typo. The palette is
actively migrating toward pinned indexed-256 codes wherever basic-16 cannot
express a distinction (see `docs/development/CLI_COLOR_PALETTE.md`), so every
remaining single-segment SGR pattern is a latent false-pass waiting for the code
it guards to move to 256. The cost of finding these now is a grep; the cost of
finding them later is a confusing red test that looks like a product regression.

## Proposed Solution

1. Audit `scripts/tests/` for SGR-matching regexes and substring checks that
   assume single-segment codes.
2. Widen each to `[\d;]+`, or better, replace ad-hoc regexes with a shared
   helper.
3. Add a small test utility — e.g. `sgr_codes(text) -> set[str]` returning the
   distinct SGR parameter strings — so assertions read
   `assert "38;5;240;1" in sgr_codes(result)` instead of hand-rolling a regex
   per test. This removes the failure mode at the source rather than patching
   each instance.

## Integration Map

| File | Change |
|---|---|
| `scripts/tests/` (SGR-asserting tests, notably `test_ll_loop_display.py`, `test_cli_loop_layout.py`, `test_cli_output.py`, `test_show.py`) | widen patterns / adopt the shared helper |
| a test-support module under `scripts/tests/` | add `sgr_codes()` helper |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Concrete home for the helper**: `scripts/tests/helpers.py` (136 lines) already
  hosts shared FSM test utilities (`make_test_state()`, `make_test_fsm()`) and
  has no existing SGR-related helper — this is the natural place to add
  `sgr_codes()`, not a new module.
- **Palette source, confirmed**: `scripts/little_loops/cli/loop/layout.py` —
  `_ACTION_TYPE_KIND_COLORS` (line 155), `_TERMINAL_KIND_COLOR` (line 170),
  `_EDGE_LABEL_COLORS` (line 42), `_bg_of()` (lines 173-194, branches on
  `fg.startswith("38;5;")`/`"38;2;"` vs. bare basic-16 ints — confirms the
  codebase already treats indexed-256 and basic-16 as structurally distinct
  forms a test helper must handle uniformly).
- **Existing sibling regex utilities** (candidates to model `sgr_codes()`
  after, or to consolidate with): `strip_ansi()` in
  `scripts/little_loops/cli/output.py:42-47` (`_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")`);
  a duplicate copy at `scripts/little_loops/cli/loop/layout.py:277-280`
  (`_ANSI_CSI_RE`, comment explicitly notes it duplicates rather than imports
  `cli.output.strip_ansi`'s regex); and a third independent copy in
  `scripts/little_loops/output_cleaner.py:27` (`_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")`,
  docstring cites `cli.output.strip_ansi` as the precedent it follows). None of
  these *extract* codes into a set — they only strip — so `sgr_codes()` is new
  work, not a rename of an existing function.
- **Repo-wide audit already run for this refinement pass** (satisfies
  Implementation Step 1's `grep -rn '033\\\[' scripts/tests/`): 13 test files
  reference SGR/CSI sequences (`test_ll_loop_commands.py`, `test_show.py`,
  `test_sprint.py`, `test_cli_output.py`, `test_issues_cli.py`,
  `test_ll_loop_display.py`, `test_loop_layout_alignment.py`,
  `test_cli_loop_background.py`, `test_cli_loop_layout.py`, `test_logger.py`,
  `test_refine_status.py`, `test_output_cleaner.py`, `test_cli.py`). Of these,
  **only `test_ll_loop_display.py:1352` uses a regex** (the already-fixed
  instance: `re.search(r"\033\[[\d;]+;1m", result)`). Every other SGR
  assertion in the suite is either an exact literal substring/equality check
  (e.g. `"\033[38;5;208" in result`, `Logger.RED == "\033[38;5;208m"`) — which
  inherently encodes the full compound form and cannot under-match — or a
  presence/absence check on the bare `"\033["` introducer, or an
  already-multi-segment-tolerant `[0-9;]*`/`[0-9;?]*` character class. **No
  additional single-segment-regex instances of this bug class exist beyond
  the one already fixed.** This materially narrows Implementation Step 1 from
  "find and fix N more instances" to "confirm zero more instances (done) and
  proceed straight to the `sgr_codes()` helper + adoption work."

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` (§ "Normalizing colored output", ~lines 562-570) — this is the existing doc anchor for `strip_ansi()`-based test conventions; extend it to introduce `sgr_codes()` as the assertion-side counterpart once added. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_helpers.py` — does not exist yet; `scripts/tests/helpers.py` currently has no dedicated test file (its existing helpers like `make_test_state`/`make_test_fsm` are only exercised indirectly through consumer tests). Implementation Step 2 ("Add the `sgr_codes()` helper with its own unit tests") needs a concrete home — create this file rather than appending to an existing one. `test_output_cleaner.py` (unit-tests `output_cleaner`'s own `_ANSI_RE`-based stripping) is the closest analogous small-utility test file to model its structure after. [Agent 1 + Agent 3 finding]

### Implementation notes

_Wiring pass added by `/ll:wire-issue`:_
- Model `sgr_codes()`'s regex on the production `_ANSI_RE` in `scripts/little_loops/cli/output.py:42` (`r"\x1b\[[0-9;]*[a-zA-Z]"`, backing `strip_ansi()`) rather than inventing a new grammar — it already spans the full `;`-delimited parameter list correctly; capture the parameter group instead of just matching-to-discard. [Agent 2 finding]
- `scripts/tests/helpers.py`'s module docstring currently reads "Shared test helpers for FSM loop tests" — `sgr_codes()` would be the first helper in this file unrelated to FSM/loop tests. Consider a one-line docstring wording update (drop the "FSM loop" scoping) when adding it, though this is stylistic, not required. [Agent 2 finding]

## Implementation Steps

1. `grep -rn '033\\\[' scripts/tests/` and triage matches into: exact literal
   comparisons (fine), single-segment regexes (fix), and multi-segment-aware
   (fine).
2. Add the `sgr_codes()` helper with its own unit tests.
3. Convert the regex-based assertions to use it, preserving each test's stated
   intent — check the docstring, since at least one docstring described broader
   coverage than the code delivered.
4. Confirm the suite stays green and that converted assertions still fail when
   the property they guard is genuinely removed (mutate-and-check one of them).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Create `scripts/tests/test_helpers.py` — no test file for `scripts/tests/helpers.py` currently exists; give `sgr_codes()` its own unit-test coverage there (Step 2's "own unit tests" target).
6. Update `docs/development/TESTING.md` § "Normalizing colored output" to mention `sgr_codes()` alongside the existing `strip_ansi()` guidance.

## Impact

- **Users**: none directly — test-only change.
- **Maintainers**: prevents future palette work from tripping false regressions
  and restores coverage that was already silently lost.
- **Risk**: Low. Widening an assertion can surface genuine pre-existing failures;
  that is the point.
- **Effort**: Small.

## Success Metrics

- No SGR assertion in `scripts/tests/` uses `\d+` where a multi-segment code can
  appear.
- Deliberately removing bold from state-name rendering fails
  `test_non_highlighted_state_name_bold`.

## Scope Boundaries

**In scope**: test assertions and test-support helpers for ANSI SGR matching.

**Out of scope**: changing any color value; the palette policy itself; non-SGR
terminal-output assertions.

## Backwards Compatibility

Test-only; no runtime or config surface affected.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/development/CLI_COLOR_PALETTE.md` | Why indexed-256 codes appear, and where |
| `.claude/CLAUDE.md` § Testing & CI Policy | The local suite is the only gate |

## Context

Found while pinning `_ACTION_TYPE_KIND_COLORS["shell"]` from `90` to
`38;5;240` to guarantee it stays distinct from the terminal-state gray. The
change turned the assertion red; investigation showed the regex — not the
product — was at fault, and that its coverage had already lapsed.

## Session Log
- `/ll:manage-issue` (improve) - 2026-07-27T05:00:10Z - `7e9f3f2d-7732-4c40-9872-f91f0866a503.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `c2ad2091-a3f8-486c-bc54-8a3163ce8935.jsonl`
- `/ll:wire-issue` - 2026-07-27T04:53:24 - `4ea1df21-c77c-4f5b-bf65-3854f9d5d192.jsonl`
- `/ll:refine-issue` - 2026-07-27T04:49:40 - `dd88fb8d-5409-47ad-97c8-b70e69d601fc.jsonl`
- `/ll:capture-issue` - 2026-07-27T00:08:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Status

open
