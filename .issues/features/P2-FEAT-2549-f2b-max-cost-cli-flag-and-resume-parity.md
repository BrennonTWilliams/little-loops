---
id: FEAT-2549
title: "F2b — --max-cost CLI flag + EXIT_CODES['cost_budget_exceeded'] + run_background re-exec forwarding + resume subparser + run.py override application"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-08T00:00:00Z"
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2476
parent: FEAT-2476
relates_to: [EPIC-2456, FEAT-2548, FEAT-2550, ENH-2475, ENH-2477, FEAT-2478, ENH-2461, FEAT-2123]
labels:
  - token-cost
  - budget
  - cli
  - tier-1
decision_needed: false
---

# FEAT-2549: F2b — `--max-cost` CLI flag + EXIT_CODES + run_background forwarding + resume parity

> **Split from FEAT-2476** (split 2026-07-08). F2b lands the *CLI surface* —
> argparse flag, exit-code table entry, detached-run forwarding, resume
> subparser, and `cmd_run` override application. **Depends on FEAT-2548**
> (the `BudgetAccumulatorConfig` type must exist to override). F2c
> (FEAT-2550) wires it into the executor end-to-end.

## Summary

Add the `--max-cost` argparse flag to `ll-loop run` and `ll-loop resume`,
register `cost_budget_exceeded: 1` in `EXIT_CODES`, forward the flag
through `run_background` re-exec so detached runs don't silently drop
it, and apply the CLI value to `fsm.budget_accumulator.max_cost_usd`
in `cmd_run` (mirror `host_guard_budget_mb:133-134`). Resume path
applies the `max_cost` override alongside the existing `no_host_guard`
mirror.

## Use Case

As an operator running `ll-loop run` or `ll-loop resume`, I want a
`--max-cost USD` argparse flag that accepts a USD ceiling and is
honored across `cmd_run` and the resume path, so the F2 cost
primitive (FEAT-2548) becomes reachable from the command line.
Detached (`--detach`) runs must forward the flag through the
re-exec, and the resume subparser must register the same flag for
parity. The flag defaults to `None` (unlimited) when absent so
existing runs are unaffected.

## Motivation

The CLI surface is the operator-facing entry point for the cost ceiling.
Without `--max-cost`, the primitive in F2a is unreachable from the
command line; without the resume subparser, an operator who sets a
ceiling on `run` can't reapply it on `resume`; without
`run_background` forwarding, detached runs silently drop the flag.
The four anchors (run_parser, resume_parser, run_background,
cmd_run) are independent enough to land in one focused PR.

## Current Behavior

- `cli/loop/__init__.py:156-165` — `run_parser` already has
  `--host-guard-budget-mb` (mirror for placement + argparse shape).
- `cli/loop/_helpers.py:65` — `EXIT_CODES` dict (the existing
  `host_budget_exceeded` is not in EXIT_CODES today; F2b adds
  `cost_budget_exceeded` proactively for consistency).
- `cli/loop/_helpers.py:1313-1379` — `run_background` re-exec
  forwarding (mirror `max_iter:1319` for placement).
- `cli/loop/__init__.py:280, 464` — resume subparser; mirrors
  `add_handoff_threshold_arg` / `add_context_limit_arg` at the
  same lines (per refine-pass correction, this lives in
  `__init__.py`, not `lifecycle.py`).
- `cli/loop/lifecycle.py:503-504` — `no_host_guard` runtime
  override mirror; F2b adds `max_cost` alongside.
- `cli/loop/run.py:133-134` — `host_guard_budget_mb` override
  application; F2b mirrors here.
- `cli_args.py:75-150` — `add_handoff_threshold_arg`,
  `add_context_limit_arg`, `add_max_workers_arg` helpers; if
  `--max-cost` is to be reused across `ll-auto` / `ll-sprint` /
  `ll-parallel`, F2b adds `add_max_cost_arg(parser)` here.

### Codebase Research Findings — Anchor Drift + Dependency State

_Added by `/ll:refine-issue` — drift between cited line anchors and current
codebase (verified 2026-07-08 via parallel codebase-locator / -analyzer /
-pattern-finder agents):_

| Cited anchor | Actual location | Drift | Notes |
|---|---|---|---|
| `__init__.py:156-165` (`run_parser` `--host-guard-budget-mb`) | `_init__.py:156-165` | none | exact match |
| `__init__.py:280` (resume subparser) | `_init__.py:404-495` (resume_parser block); helper calls at `494-495` | wrong line — `280` is inside the run_parser `--program-md` help text | both the resume subparser construction AND the helper-call placements (`add_handoff_threshold_arg(resume_parser)` at `494`, `add_context_limit_arg(resume_parser)` at `495`) drift from the cited anchor |
| `__init__.py:464` (resume subparser) | `_init__.py:494-495` (helpers) / `489-493` (raw `--no-prompt-size-guard`) | wrong line — `464` is inside the `--diagram-scope` resume flag help text | F2b `--max-cost` insertion point on resume subparser is after `add_context_limit_arg(resume_parser)` at `495` |
| `_helpers.py:65` (`EXIT_CODES`) | `_helpers.py:64-77` (dict); `1734` (translation site) | 1-line drift | keys today: `terminal/interrupted/handoff/max_steps/timeout/cycle_detected/stall_detected/user_stopped/system_signal`; **no budget-related keys present** — `host_budget_exceeded` is also absent (F2b adds both proactively per spec) |
| `_helpers.py:1313-1379` (`run_background`) | `_helpers.py:1323-1484` (function body) | starts ~10 lines later, ends much later | `run_background`'s `cmd` build spans `1383-1465`; the cited starting line `1313` is actually inside `print_execution_plan` |
| `_helpers.py:1319` (`max_iter` forward) | `_helpers.py:1400-1402` | off by ~81 lines | `max_iter` mirror block is intact, just shifted |
| `run.py:133-134` (`host_guard_budget_mb` cmd_run override) | `_run.py:132-135` | 1-line drift | override block identical in shape |
| `lifecycle.py:503-504` (`no_host_guard` resume override) | `_lifecycle.py:532-533` | off by ~29 lines | block identical in shape; resume subparser does NOT register `--host-guard-budget-mb` (existing asymmetry — out of scope for F2b) |
| `cli_args.py:75-150` (helpers) | `cli_args.py:75-150` (`add_max_workers_arg/add_timeout_arg/add_idle_timeout_arg/add_handoff_threshold_arg`); `181-192` for `add_context_limit_arg` | the cited range spans four helpers, not all in `75-150` | closest precedent for `add_max_cost_arg` is `add_handoff_threshold_arg:139-150` (single-purpose, no `default` parameter, hard-coded `default=None`) |
| `cli/loop/_helpers.py:1652-1714` (`_print_usage_summary`) | `_helpers.py:~1695-1734` (function body roughly to translation site) | minor drift | F2c extends the completion block; F2b does not modify this |

**FEAT-2548 dependency state**: FEAT-2548 has **not landed**.
- No `scripts/little_loops/fsm/budget.py` or `budget_accumulator.py` exists.
- Zero references to `BudgetAccumulatorConfig`, `max_cost_usd`, or `budget_accumulator` in `scripts/little_loops/` source.
- `fsm/schema.py:1115` declares `host_guard: HostGuardConfig = field(...)` but **no parallel `budget_accumulator` field** on `FSMLoop` (dataclass body `1090-1131`).
- The only on-disk occurrences of `budget_accumulator` are empty reserved envelopes in `scripts/tests/fixtures/tier0_traces/general-task-20260608T194041.json:688` and `general-task-20260619T225602.json:1104`, locked by `scripts/tests/test_tier0_traces.py:141, 157-158`.
- F2b's `run.py:135-136` and `lifecycle.py:537` lines (`fsm.budget_accumulator.max_cost_usd = args.max_cost`) will raise `AttributeError` until FEAT-2548 lands. This is consistent with the issue's stated `Depends on` relationship.

## Expected Behavior

- `ll-loop run --max-cost=1.00` accepts a USD ceiling; defaults to
  `None` (unlimited) when absent; rejects non-numeric or
  non-positive values with `argparse.error`.
- `ll-loop resume --max-cost=1.00` accepts the same flag
  (registration parity with `run`).
- `ll-loop run --max-cost=1.00 --detach` followed by `ll-loop
  resume` preserves the ceiling (no silent flag drop).
- On `--max-cost` abort, the run exits with code 1 and emits
  `terminated_by: "cost_budget_exceeded"` (exit-code wiring is
  the F2b contract; the actual emission happens in F2c executor
  wiring).
- `cmd_run` applies `args.max_cost` to
  `fsm.budget_accumulator.max_cost_usd` before the executor
  starts.

## Proposed Solution

1. **`scripts/little_loops/cli/loop/__init__.py:156-165`** — add
   `--max-cost` to `run_parser` immediately after
   `--host-guard-budget-mb`:
   ```python
   parser.add_argument(
       "--max-cost",
       type=float,
       default=None,
       metavar="USD",
       help="Cap on cumulative USD cost for the run. Exits 1 if reached.",
   )
   ```

2. **`scripts/little_loops/cli/loop/__init__.py:280, 464`** — register
   `--max-cost` on the resume subparser (mirror
   `add_handoff_threshold_arg` / `add_context_limit_arg` at the
   same lines).

3. **`scripts/little_loops/cli/loop/_helpers.py:65`** — add
   `"cost_budget_exceeded": 1` to `EXIT_CODES` dict (and proactively
   add `"host_budget_exceeded": 1` for parity — current code returns
   `EXIT_CODES.get(result.terminated_by, 1)` which already maps
   unknowns to 1, so the dict entry is for explicit documentation).

4. **`scripts/little_loops/cli/loop/_helpers.py:1313-1379`** — in
   `run_background`, append `--max-cost=$arg` to `cmd` if
   `args.max_cost is not None` (mirror `max_iter:1319` placement).

5. **`scripts/little_loops/cli/loop/run.py:133-134`** — in
   `cmd_run`, apply the override:
   ```python
   if getattr(args, "max_cost", None) is not None:
       fsm.budget_accumulator.max_cost_usd = args.max_cost
   ```
   (mirror `host_guard_budget_mb` at `:133-134`).

6. **`scripts/little_loops/cli/loop/lifecycle.py:503-504`** —
   resume path applies `max_cost` runtime override alongside
   `no_host_guard` mirror.

7. **`scripts/little_loops/cli_args.py:75-150`** — add
   `add_max_cost_arg(parser)` helper (mirror
   `add_handoff_threshold_arg`) if `--max-cost` is to be reused
   across `ll-auto` / `ll-sprint` / `ll-parallel`. Out of scope
   for the F2b core; add only if those surfaces request it.

### Codebase Research Findings — Verified Mirror Code Shapes

_Added by `/ll:refine-issue` — concrete code blocks that exactly mirror the
current `--host-guard-budget-mb` precedent (verified 2026-07-08 against the
working tree). Each block can be transcribed into the cited file with no
further exploration._

**`__init__.py:156-165` (run_parser)** — current `--host-guard-budget-mb`
block (verified verbatim):
```python
run_parser.add_argument(
    "--host-guard-budget-mb",
    type=int,
    default=None,
    metavar="N",
    help=(
        "Override host_guard.max_cumulative_subproc_mb: cap on summed peak "
        "subprocess RSS (MB) across the run (0 disables the budget)"
    ),
)
```

F2b `--max-cost` insertion (immediately after, at line 166):
```python
run_parser.add_argument(
    "--max-cost",
    type=float,
    default=None,
    metavar="USD",
    help="Cap on cumulative USD cost for the run. Exits 1 if reached.",
)
```

**`__init__.py:494-495` (resume subparser)** — current state (verified):
```python
add_handoff_threshold_arg(resume_parser)
add_context_limit_arg(resume_parser)
```

F2b `--max-cost` insertion (after `add_context_limit_arg(resume_parser)` at
line 495):
```python
run_parser.add_argument("--max-cost", type=float, default=None, metavar="USD", ...)
```
…or, if `add_max_cost_arg(resume_parser)` helper is added, called here in
mirror position. The current resume_parser construction runs lines 404-495;
insertion lands at line 495-or-later.

**`_helpers.py:64-77` (EXIT_CODES)** — current dict verified verbatim (9
keys, no budget-related keys). F2b adds two entries (proactively also
`host_budget_exceeded` per the issue's consistency note — verified absent
today):
```python
EXIT_CODES: dict[str, int] = {
    "terminal": 0,
    "interrupted": 0,
    "handoff": 0,
    "max_steps": 1,
    "timeout": 1,
    "cycle_detected": 1,
    "stall_detected": 1,
    "user_stopped": 1,
    "system_signal": 1,
    # F2b (FEAT-2549): cost-and-host budget terminations are non-zero so
    # callers can distinguish budget-exceeded from graceful paths. Both
    # entries are documentation-only today (the EXIT_CODES.get default is
    # already 1).
    "host_budget_exceeded": 1,
    "cost_budget_exceeded": 1,
}
```

**`_helpers.py:1444-1446` (run_background forwarding, after the `host_guard_budget_mb` block)** — exact mirror:
```python
max_cost = getattr(args, "max_cost", None)
if max_cost is not None:
    cmd.extend(["--max-cost", str(max_cost)])
```

Note: the `is not None` guard preserves `0.0` semantics if a user passes
`--max-cost=0.0` to mean "halt immediately".

**`run.py:132-135` (cmd_run override application)** — verified mirror block:
```python
if getattr(args, "host_guard_budget_mb", None) is not None:
    fsm.host_guard.max_cumulative_subproc_mb = args.host_guard_budget_mb
```

F2b insertion (after line 135, at `run.py:136`):
```python
if getattr(args, "max_cost", None) is not None:
    fsm.budget_accumulator.max_cost_usd = args.max_cost
```

**`lifecycle.py:532-533` (cmd_resume override)** — verified mirror block:
```python
if getattr(args, "no_host_guard", False):
    fsm.host_guard.enabled = False
```

F2b insertion (after `no_prompt_size_guard` at line 536, at `lifecycle.py:537`):
```python
if getattr(args, "max_cost", None) is not None:
    fsm.budget_accumulator.max_cost_usd = args.max_cost
```

**`cli_args.py:139-150` (`add_handoff_threshold_arg` template)** — verified
exact function body. If `add_max_cost_arg` is added (out of F2b core scope),
it would mirror this with `type=float, default=None, metavar="USD"`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — `run_parser` + resume subparser
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` + `run_background` forwarding
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` override application
- `scripts/little_loops/cli/loop/lifecycle.py` — resume runtime override
- `scripts/little_loops/cli_args.py` — `add_max_cost_arg` helper (optional)

### Tests

- `scripts/tests/test_cli_args.py:401-440` — `TestAddMaxCostArg`
  mirroring `TestAddHandoffThresholdArg` (default `None`, accepts
  `float`, rejects non-numeric with `SystemExit`).
- `scripts/tests/test_ll_loop_parsing.py:360-381` — resume subparser
  registration test mirroring
  `test_handoff_threshold_registered_on_real_resume_parser`.
- `scripts/tests/test_cli_max_cost.py` (new) — end-to-end CLI test:
  `ll-loop run --max-cost=0.05` halts at ceiling ±5%, never
  exceeds, propagates non-zero exit code 1, emits
  `terminated_by: "cost_budget_exceeded"`.

### Codebase Research Findings — Tests (template bodies verified)

_Added by `/ll:refine-issue` — verified 2026-07-08 from
`scripts/tests/test_cli_args.py` and `scripts/tests/test_ll_loop_parsing.py`:_

**`TestAddHandoffThresholdArg` template** (lines 401-440). The template uses
**local imports inside each test method** (not top-of-file) — pattern:
```python
class TestAddHandoffThresholdArg:
    """Tests for add_handoff_threshold_arg() function."""

    def test_default_is_none(self) -> None:
        from little_loops.cli_args import add_handoff_threshold_arg
        parser = argparse.ArgumentParser()
        add_handoff_threshold_arg(parser)
        assert parser.parse_args([]).handoff_threshold is None

    def test_accepts_integer(self) -> None:
        from little_loops.cli_args import add_handoff_threshold_arg
        parser = argparse.ArgumentParser()
        add_handoff_threshold_arg(parser)
        assert parser.parse_args(["--handoff-threshold", "60"]).handoff_threshold == 60

    def test_accepts_boundary_values(self) -> None: ...

    def test_rejects_non_integer(self) -> None:
        from little_loops.cli_args import add_handoff_threshold_arg
        parser = argparse.ArgumentParser()
        add_handoff_threshold_arg(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--handoff-threshold", "abc"])
```

`TestAddMaxCostArg` mirrors this with `type=float` and float boundary values;
the `test_rejects_non_integer` analogue would assert `SystemExit` on
`"--max-cost abc"`.

**`test_handoff_threshold_registered_on_real_resume_parser` template** (lines
360-381 in `test_ll_loop_parsing.py`):
```python
def test_handoff_threshold_registered_on_real_resume_parser(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--handoff-threshold is accepted by the actual ll-loop resume parser."""
    monkeypatch.chdir(tmp_path)
    with (
        patch.object(sys, "argv", ["ll-loop", "resume", "my-loop", "--handoff-threshold", "30"]),
        patch("little_loops.cli.loop.lifecycle.cmd_resume", return_value=0) as mock_resume,
    ):
        from little_loops.cli import main_loop
        result = main_loop()
    assert result == 0
    mock_resume.assert_called_once()
    resume_args = mock_resume.call_args[0][1]
    assert getattr(resume_args, "handoff_threshold", None) == 30
```

F2b's `test_max_cost_registered_on_real_resume_parser` follows the same
shape, with `"--max-cost"` + a float string like `"0.50"` and asserting
`getattr(resume_args, "max_cost", None) == 0.50`. A run_parser twin
(`test_max_cost_registered_on_real_run_parser` at `test_ll_loop_parsing.py:300-319`)
mirrors the existing dual coverage pattern.

**Sister test location** for `host_guard_budget_mb` flag coverage:
`scripts/tests/test_cli_loop_dispatch.py:652-666` is the existing
`ll-loop run --help` host-budget test pattern, and `test_cli_loop_dispatch.py:582`
covers `--max-iterations`. F2b can add a `test_max_cost_in_run_help_output`
analog at the same file.

**`test_cli_max_cost.py` realistic scope**: cannot fully pass until F2c wires
the executor (FEAT-2550 lands). The realistic F2b scope is the helper-class
test in `test_cli_args.py` and the real-parser tests in
`test_ll_loop_parsing.py`; the end-to-end behavioral test in
`test_cli_max_cost.py` is **deferred to F2c** unless F2b authors it as a
`pytest.skip(...)` placeholder gated on `BudgetAccumulatorConfig` importability.

**Closest structural twin for end-to-end**:
`scripts/tests/test_host_guard.py` (`make_prompt_fsm()` factory at lines 75-89
is the test template).

### Dependent Files (read-only consumers, no changes)

- `scripts/little_loops/cli/loop/_helpers.py:1652-1714` —
  `_print_usage_summary()` — unchanged (F2c extends the completion
  block, not the per-state table).
- `scripts/little_loops/cli/loop/info.py:522-523` — `info.py` reads
  `result.terminated_by` for `ll-loop history` rows (FEAT-2550/F2c
  will distinguish `cost_budget_exceeded` here, not F2b).
- `scripts/little_loops/cli/loop/testing.py:275` — testing output
  read of `result.terminated_by` (no F2b change).

### Codebase Research Findings — Cross-CLI Surfaces (out of scope)

_Added by `/ll:refine-issue` — verified call sites for the existing helper
precedents in case F2b adds `add_max_cost_arg` to `cli_args.py`:_

The cross-CLI consumers of `add_handoff_threshold_arg` (mirroring precedent
for an `add_max_cost_arg` helper):
- `scripts/little_loops/cli/loop/__init__.py:295` (run_parser), `:494` (resume_parser)
- `scripts/little_loops/cli_args.py:436` (registered inside `add_common_auto_args()`)
- `scripts/little_loops/cli/auto.py` — uses helper via `add_common_auto_args()`
- `scripts/little_loops/cli/sprint/__init__.py`
- `scripts/little_loops/cli/parallel.py`

Per the issue's `Out of scope` clause, F2b **does not** add
`add_max_cost_arg` to `cli_args.py` unless `ll-auto` / `ll-sprint` /
`ll-parallel` request it. If those CLIs later want `--max-cost`, the helper
takes only `(parser: argparse.ArgumentParser) -> None`, hard-codes
`type=float, default=None, metavar="USD"`, and emits one `parser.add_argument(...)`
call (mirror `add_handoff_threshold_arg` at `cli_args.py:139-150`). The
`__all__` list at `cli_args.py:473-501` would gain `"add_max_cost_arg"`.

**Important mirror-table note**: 4 of the 5 mirror flags
(`--host-guard-budget-mb`, `--max-iterations`, `--prompt-size-warn-chars`,
`--cost-output-json`) are **NOT** registered on the resume_parser. Only
`--no-host-guard`, `--no-prompt-size-guard`, `--delay`, `--handoff-threshold`,
`--context-limit` are. F2b's `--max-cost` resume subparser registration is a
**net-new parity surface**, not a mirror of `--host-guard-budget-mb`. The
relevant mirror for placement is `add_handoff_threshold_arg(resume_parser)`
at `cli/loop/__init__.py:494`.

## Acceptance Criteria

- `ll-loop run --help` shows `--max-cost USD` in the run-parser
  output.
- `ll-loop resume --help` shows `--max-cost USD` in the
  resume-parser output.
- `ll-loop run --max-cost=abc` exits with code 2 (argparse
  error).
- `ll-loop run --max-cost=1.00` followed by
  `ps -ef | grep ll-loop` shows the flag forwarded in the
  detached re-exec `cmd` (or equivalent inspection of
  `<run_dir>/run.json`).
- `argparse.Namespace(max_cost=0.5)` passed to `cmd_run` results
  in `fsm.budget_accumulator.max_cost_usd == 0.5` after override
  application.
- `EXIT_CODES["cost_budget_exceeded"] == 1`.
- `python -m pytest scripts/tests/` exits 0 (no regressions in
  test_cli_args, test_ll_loop_parsing, test_cli_loop_*).

## Scope Boundaries

- **In**: argparse flags (run + resume); `EXIT_CODES` entry;
  `run_background` re-exec forwarding; `cmd_run` override
  application; resume runtime override.
- **Out**: primitive library (F2a / FEAT-2548); executor
  wiring (F2c / FEAT-2550); OTel transport (F2c); docs (F2c).
- **Out of scope**: cross-CLI `--max-cost` flag (e.g., shared
  `add_max_cost_arg` for `ll-auto` / `ll-sprint` / `ll-parallel`)
  unless those surfaces request it.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/cli/loop/__init__.py:156-165` | `run_parser` `--host-guard-budget-mb` mirror for placement |
| `scripts/little_loops/cli/loop/__init__.py:280, 464` | Resume subparser registration anchor (refine-pass corrected) |
| `scripts/little_loops/cli/loop/_helpers.py:65` | `EXIT_CODES` dict — add entry |
| `scripts/little_loops/cli/loop/_helpers.py:1313-1379` | `run_background` re-exec forwarding |
| `scripts/little_loops/cli/loop/_helpers.py:1319` | `max_iter` forwarding — placement mirror |
| `scripts/little_loops/cli/loop/run.py:133-134` | `host_guard_budget_mb` override — placement mirror |
| `scripts/little_loops/cli/loop/lifecycle.py:503-504` | Resume runtime override — `no_host_guard` mirror |
| `scripts/little_loops/cli_args.py:75-150` | Argparse helper precedent (`add_handoff_threshold_arg` etc.) |
| `scripts/tests/test_cli_args.py:401-440` | `TestAddHandoffThresholdArg` — template |
| `scripts/tests/test_ll_loop_parsing.py:360-381` | `test_handoff_threshold_registered_on_real_resume_parser` — template |
| `FEAT-2548` | Depends-on: `BudgetAccumulatorConfig.max_cost_usd` field must exist |
| `FEAT-2476` | Parent umbrella |

## Impact

- **Priority**: P2 — first-clamp primitive for runaway cost.
- **Effort**: Small — ~80 LOC across 4 files + ~150 LOC tests.
- **Risk**: Low — additive; flag defaults to `None` (unlimited);
  existing runs unchanged.
- **Breaking Change**: No — opt-in flag.

## Status

**Open** | Created: 2026-07-08 | Priority: P2 | Split from FEAT-2476
**Depends on**: FEAT-2548 (primitive must exist for `fsm.budget_accumulator` field to override)

## Session Log
- `/ll:capture-issue` (split) - 2026-07-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
