---
id: ENH-2977
title: Add a --timeout CLI flag to ll-auto, matching the existing --idle-timeout
type: ENH
priority: P4
status: done
parent: EPIC-3213
epic: EPIC-3213
discovered_date: 2026-08-01
discovered_by: human
completed_at: '2026-08-30T04:51:00Z'
relates_to:
- BUG-2976
- FEAT-488
- BUG-3034
- ENH-3129
labels:
- cli
- ll-auto
- ergonomics
testable: true
verify_verdict: NON_VALID
confidence_score: 100
outcome_confidence: 98
score_complexity: 25
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2977: Add a --timeout CLI flag to ll-auto, matching the existing --idle-timeout

## Summary

`ll-auto` is the only one of the three issue-processing entry points without a
`--timeout` flag. `ll-parallel` (`cli/parallel.py:172`) and `ll-sprint run`
both call the shared `add_timeout_arg` helper; `ll-auto` does not, so
`automation.timeout_seconds` is reachable only by editing `.ll/ll-config.json`
— a per-project, frequently gitignored file — and then remembering to revert.

**This adds no timeout mechanism.** The knob already exists and already fires;
this issue only makes it settable from the command line, exactly as
`--idle-timeout` already is (FEAT-488). The flag *declaration* also already
exists — `add_timeout_arg` (`cli_args.py:100-122`) is written and exported; it
is simply never called from `add_common_auto_args`.

## Current Behavior

`add_common_auto_args` (`cli_args.py:522-540`) wires ten flags including
`add_idle_timeout_arg(parser)` at line 538, but never calls `add_timeout_arg`.
`cli/auto.py` correspondingly wires exactly one of the two:

```python
if args.idle_timeout is not None:
    config.automation.idle_timeout_seconds = args.idle_timeout
```

`AutomationConfig` (`config/automation.py:21-22`) defines both
`timeout_seconds: int = 7200` and `idle_timeout_seconds: int = 0`, and
`from_dict()` reads both from `.ll/ll-config.json`. Only the idle one has a CLI
override. Raising the budget for one unusually large issue is therefore a
config edit plus a manual revert, with no record in the invocation of what was
actually run.

## Scope Boundaries

Trimmed 2026-08-29 after review. Three lines of source plus one test
assertion. Everything that widened the blast radius has been cut.

**In scope:**

1. `add_timeout_arg(parser)` added to `add_common_auto_args`
   (`cli_args.py:522-540`), alongside the existing `add_idle_timeout_arg(parser)`
   call at line 538, plus the docstring flag list at line 525-526.
2. `if args.timeout is not None: config.automation.timeout_seconds = args.timeout`
   in `cli/auto.py`, immediately after the existing `--idle-timeout` block
   (`auto.py:80-81`).
3. A negative-value `parser.error()` guard, mirroring the `--handoff-threshold`
   and `--context-limit` guards directly below (`auto.py:83-92`).
4. One added assertion in the existing
   `TestAddCommonAutoArgs.test_adds_all_expected_arguments`
   (`test_cli_args.py:781-819`).

**Out of scope (cut from the earlier revision):**

- **Changing the `help=` string in `add_timeout_arg`.** The earlier revision
  proposed `"Per-issue timeout in seconds"` as new shared text. That is
  **factually wrong for `ll-auto`**: `config.automation.timeout_seconds` is
  threaded independently into five separate `run_claude_command` sites in
  `issue_manager.py` (lines 897, 973, 1178, 1325, 1548), so it is a
  per-invocation budget there, not a per-issue one — the finding established by
  ENH-3129. Adopting that wording would ship a false statement in `--help` for
  `ll-auto` and rewrite `ll-parallel --help` for no reason. The helper's current
  `"Timeout in seconds"` is vague but not wrong; leave it.
- The `docs/reference/CLI.md` / `CONFIGURATION.md` / `CHANGELOG.md` expansion
  the earlier revision specified. One `--timeout` row in the `ll-auto` flag
  table (`CLI.md:430`, next to the `--idle-timeout` row) is sufficient.
- The `config/core.py:576` truthiness fix — already shipped as BUG-3034; that
  file now uses the `is not None` form.
- Changing the `7200` default, per-phase budgets, and the timeout *handling*
  defect (BUG-2976 — a breach aborts the run and deletes resume state). This
  issue does not change what happens when the budget is breached.
- `ll-sprint` and `ll-parallel` source changes — both already declare the flag.

## Expected Behavior

`ll-auto --timeout N` sets `config.automation.timeout_seconds` for that
invocation, with the same precedence and shape as `--idle-timeout`:

- Absent (`None`) → the config value, else the `7200` default. Unchanged for
  every existing invocation.
- `--timeout 0` → no wall-clock timeout, consistent with `0` disabling
  `idle_timeout_seconds` and with `run_claude_command`'s documented
  `timeout: Timeout in seconds (0 for no timeout)`. Honored at the bottom of
  the stack: `subprocess_utils.py:465` guards with
  `if timeout and (now - start_time) > timeout`, so a falsy `0` never fires.
  This is why the assignment must use `is not None`, not truthiness.
- `--timeout -N` → `parser.error()`. Without the guard, `if timeout and ... >
  timeout` is immediately true and every issue instant-fails.
- `-t` is registered as a short alias — not a design goal, just what
  `add_timeout_arg` (`cli_args.py:110,118`) declares. Verified free on
  `ll-auto`, whose short flags are `-r -n -m -q -o -s -T -p -C`.

## Backwards Compatibility

Fully backwards compatible. The flag defaults to `None`, leaving the existing
config→default resolution untouched.

## Program Design

### Types

- `timeout: int | None` — the new `argparse.Namespace` attribute; `None` when
  omitted.
- `timeout_seconds: int` — the existing `AutomationConfig` field
  (`config/automation.py:21`, default `7200`) it assigns to.

### Signatures

- `add_timeout_arg(parser: argparse.ArgumentParser, default: int | None = None) -> None`
  — unchanged. Called with no `default`, so the `default=None` branch applies.
- `add_common_auto_args(parser: argparse.ArgumentParser) -> None` — unchanged
  signature; gains one call and a docstring line.

No signature changes anywhere below the CLI layer — every consumer already
reads the value off `config.automation`.

### Call Path

`ll-auto` → `cli/auto.py` parsing → `config.automation.timeout_seconds =
args.timeout` (guarded by `is not None`, at `auto.py:82`) → `AutoManager` →
`process_issue_inplace()` → `run_claude_command(timeout=...)` →
`subprocess_utils.py:465`.

**Blast radius**: `add_common_auto_args` has exactly one caller in the tree
(`cli/auto.py:55`), so adding a flag to it cannot affect any other entry point.
Because the `help=` string is now out of scope, `ll-parallel` and `ll-sprint`
are untouched.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli_args.py` — add `add_timeout_arg(parser)` to
  `add_common_auto_args` (after line 538); update the docstring flag list
  (lines 525-526).
- `scripts/little_loops/cli/auto.py` — the `is not None` assignment and
  negative guard, after line 81.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py` — reads
  `config.automation.timeout_seconds` at five `run_claude_command()` sites
  (897, 973, 1178, 1325, 1548); no change.
- `scripts/little_loops/cli/sprint/run.py` — also consumes
  `automation.timeout_seconds`; no change.
- `scripts/little_loops/loops/autodev.yaml` and other callers shelling out to
  `ll-auto` — unaffected; the flag is additive and optional.

### Similar Patterns

- `cli/auto.py:80-81` (`--idle-timeout`) is the template for the assignment;
  `auto.py:83-92` (`--handoff-threshold`, `--context-limit`) is the template
  for the `parser.error()` guard.

### Tests

`scripts/tests/test_cli_args.py` is the coverage location (no `test_cli_auto.py`
exists in this tree). Extend the existing
`TestAddCommonAutoArgs.test_adds_all_expected_arguments`
(`test_cli_args.py:781-819`) — add `"--timeout", "1800"` to the argv list and
`assert args.timeout == 1800`, mirroring `TestAddCommonParallelArgs` which
already makes the identical assertion for the parallel side. Update that test's
docstring (line 782), which enumerates the flags it covers.

Add narrow cases for the two behaviors the trim depends on:

- `--timeout 0` parses to `0` (not `None`, not coerced) — pins that the
  `cli/auto.py` assignment uses `is not None` rather than truthiness.
- `--timeout -1` exits with the argparse usage error (status 2), same shape as
  the existing `--handoff-threshold` / `--context-limit` range tests.

### Documentation

- **`docs/reference/CLI.md`** — one `--timeout` / `-t` row in the `ll-auto`
  flag table, adjacent to the existing `--idle-timeout` row at line 430.
  Nothing else.

### Configuration

- No schema change; `automation.timeout_seconds` already exists
  (`config-schema.json:241`).

## Impact

- **Priority**: P4 — downgraded from P3 on 2026-08-29. Pure CLI-surface
  consistency with an existing workaround, and at the `7200` default the budget
  is rarely binding. Nothing depends on it.
- **Effort**: Trivial — three lines of source and three test assertions, all
  mirroring code a few lines away.
- **Risk**: Low. The single trap is a `if args.timeout:` truthiness check
  silently discarding `--timeout 0`; the `is not None` idiom avoids it and a
  test pins it.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-01 | Priority: P4 | Trimmed: 2026-08-29

Filed alongside BUG-2976 after reviewing a recovery plan for a timed-out
`ll-auto --only FEAT-108` run in a downstream project. The plan's remedy for
the timeout was a `.ll/ll-config.json` edit precisely because no CLI override
exists.

### Relationship to ENH-3129

ENH-3129 (a distinct `automation.max_issue_wall_clock_time` ceiling) was
**cancelled** on 2026-08-29 for timeout-mechanism proliferation: it proposed a
fourth kill path with its own interaction rules and failure reason. That
rationale does not carry over here. This issue introduces no new config key, no
new kill path, and no new semantics — it exposes the second of the two existing
`ll-auto` timeouts on the command line, matching how the first one
(`--idle-timeout`) is already exposed.

The one thing ENH-3129 *does* contribute is the finding that
`automation.timeout_seconds` is per-invocation rather than per-issue for
`ll-auto` — which is why the shared help-text rewrite is now out of scope.

## Verification Notes

**2026-08-12** (`/ll:verify-issues`): The folded-in `ll-parallel --timeout 0`
truthiness sub-scope (`config/core.py:576`) was already fixed by a separate
commit that closed BUG-3034 — `config/core.py` now uses the `is not None`
form — so that item is struck. The cited `AutomationConfig.timeout_seconds`
default was also stale (`3600` → `7200`, per commit `1405c21b`) and has been
corrected. The core ask — adding a `--timeout` CLI flag to `ll-auto` — remains
valid and open.

**2026-08-29** (review): Re-verified against the tree. `add_timeout_arg` exists
at `cli_args.py:100-122` and is absent from `add_common_auto_args`
(`cli_args.py:522-540`) — the gap is real. `-t` confirmed free on `ll-auto` by
parsing a live parser (short flags in use: `-r -n -m -q -o -s -T -p -C`).
Issue trimmed: the shared `help=` rewrite was cut as factually wrong for
`ll-auto`, and the docs expansion was cut to a single table row. Priority
lowered P3 → P4.

## Related Key Documentation

- `docs/reference/CLI.md` — the `ll-auto` flag table this change lands in
  (line 430 region). `.claude/CLAUDE.md` names it authoritative, with
  `<cmd> --help` winning over any prose.

## Session Log
- `/ll:manage-issue` - 2026-08-30T04:50:35 - `2bacf986-2318-4058-944b-2e7185d8ee77.jsonl`
- `/ll:confidence-check` - 2026-08-30T04:40:55 - `0d08a078-6a53-4f72-959b-ecc948902882.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:18:53 - `52bc5a67-0032-4383-ae03-a6de98447a01.jsonl`
