---
id: ENH-2838
type: ENH
priority: P4
status: open
captured_at: "2026-07-27T00:08:18Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [testing, cli, color, tech-debt]
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
- `/ll:capture-issue` - 2026-07-27T00:08:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Status

open
