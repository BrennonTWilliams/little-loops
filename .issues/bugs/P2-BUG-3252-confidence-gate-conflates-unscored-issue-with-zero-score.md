---
id: BUG-3252
type: BUG
title: ll-auto confidence gate conflates an unscored issue with a zero-scored one,
  emits no remediation, and records the skip as a failure
priority: P2
status: open
testable: true
discovered_by: analyze_log
discovered_date: '2026-08-17'
discovered_commit: 6ba249d0
discovered_source: ll-auto run 2026-08-17T17:51-18:20 (--only ENH-3237,ENH-3240)
relates_to:
- FEAT-3117
---

# BUG-3252: ll-auto confidence gate conflates an unscored issue with a zero-scored one, emits no remediation, and records the skip as a failure

## Summary

`readiness_status()` coerces a missing `confidence_score` frontmatter key to the
integer `0`. The `ll-auto` pre-Phase-1 confidence gate then reports that `0` as
though it were a measured score, halts, and files the issue under
`failed_issues` — so an issue that has simply never been through
`/ll:confidence-check` is indistinguishable in the log, the summary, and the
state file from one that was assessed and found genuinely unready.

The gate itself is correct to halt. Three things around it are wrong: the
message misrepresents absence as a score, the remediation the skill spec
mandates is never emitted, and the outcome is classified as a failure rather
than a skip.

## Steps to Reproduce

1. Take an issue with no `confidence_score` in frontmatter — e.g. one freshly
   produced by `/ll:capture-issue` + `/ll:format-issue` + `/ll:wire-issue`, none
   of which write a score.
2. Ensure `commands.confidence_gate.enabled` is `true` in `.ll/ll-config.json`
   (it is, with `readiness_threshold: 85`).
3. Run `ll-auto --only <ID>`.

Observed, from the 2026-08-17 run against ENH-3240:

```
[18:20:58] ENH-3240: below readiness threshold (confidence 0 < 85)
CONFIDENCE_GATE_BLOCKED ENH-3240
PHASE1_NOT_STARTED ENH-3240 confidence_gate
...
[18:20:58] Failed issues: 1
[18:20:58]   - ENH-3240: below_readiness_threshold (0 < 85)...
```

ENH-3240's frontmatter at that moment contained no `confidence_score` key at
all — the `0` is entirely synthesized by the reader.

## Current Behavior

`scripts/little_loops/cli/issues/check_readiness.py:87`:

```python
confidence = int(fm.get("confidence_score") or 0)
```

`ReadinessStatus` therefore has no way to express "unscored". Its
`meets_readiness` property (`check_readiness.py:33-35`) compares the synthesized
`0` against the threshold, which is the right *decision* but for a reason the
type can no longer carry.

`scripts/little_loops/issue_manager.py:813-833` consumes it:

```python
logger.warning(
    f"{info.issue_id}: below readiness threshold "
    f"(confidence {status.confidence} < {status.readiness_threshold})"
)
print(f"CONFIDENCE_GATE_BLOCKED {info.issue_id}", flush=True)
print(f"PHASE1_NOT_STARTED {info.issue_id} confidence_gate", flush=True)
return _stamped_result(
    success=False,
    ...
    failure_reason=(
        f"below_readiness_threshold "
        f"({status.confidence} < {status.readiness_threshold})"
    ),
)
```

`success=False` routes the issue into `state.failed_issues`, which the run
summary renders under the "Failed issues:" heading
(`issue_manager.py:1965-1968`).

## Expected Behavior

1. **Absence is representable.** `ReadinessStatus` distinguishes "no
   `confidence_score` key" from "`confidence_score: 0`". The gate decision is
   unchanged — both halt — but the reported reason differs.
2. **The message states which case it is.** Unscored issues get "has no
   confidence score (never assessed)", not "confidence 0 < 85".
3. **The remediation is emitted.** `skills/manage-issue/SKILL.md:183` specifies
   the gate should "HALT and direct the user to run `/ll:confidence-check
   [ID]`". `ll-auto` mirrors the gate's decision but not its remediation, so the
   operator gets a number with no next command. Emit the suggested command.
4. **A gate skip is not a failure.** The issue was never attempted; counting it
   as failed misrepresents the run's outcome and pollutes downstream metrics
   (see BUG-3253 for one concrete instance).

The `CONFIDENCE_GATE_BLOCKED` / `PHASE1_NOT_STARTED` stdout markers must keep
their exact current spelling — `autodev.yaml`'s `check_impl_reached`
discriminator greps for them (per the comments at `issue_manager.py:819-826`).

## Impact

- **Severity**: P2 — no data loss, but the run summary actively misinforms.
  "Failed issues: 1 — below_readiness_threshold (0 < 85)" reads as "this issue
  was evaluated and scored badly", prompting an operator to go re-refine an
  issue whose only real problem is that nobody has run `/ll:confidence-check`
  on it yet.
- **Frequency**: every unscored issue passed to `ll-auto` while the gate is
  enabled. In the observed run that was 1 of 2 issues (50%).
- **Data Risk**: None.

## Root Cause

`or 0` in `check_readiness.py:87` is a lossy coercion at the type boundary. The
`ReadinessStatus` dataclass docstring is explicit that it deliberately avoids a
combined `passed` verdict so that two callers with different needs each get a
correct answer — the same reasoning applies here: collapsing absent and zero
serves the comparison but destroys the diagnostic.

The classification half is separate: `_stamped_result(success=False, ...)` is
the only outcome shape the gate branch has available, and `IssueProcessingResult`
has no "skipped" state distinct from "failed".

## Proposed Solution

**Part 1 — represent absence.**

Add a nullable raw field to `ReadinessStatus` alongside the coerced one, so no
existing consumer changes behavior:

- `confidence_present: bool` (or `raw_confidence: int | None`) populated from
  whether the frontmatter key existed, not from its value.
- `confidence` keeps its current `int` semantics and `meets_readiness` keeps its
  current comparison, so `cmd_check_readiness` and the `autodev.yaml`
  `--readiness`/`--outcome` CLI fallbacks are untouched.

**Part 2 — message and remediation.**

In `issue_manager.py`'s gate branch, branch the log line on
`confidence_present` and append the remediation command in both cases:

```
ENH-3240: no confidence score recorded (never assessed) — run
  /ll:confidence-check ENH-3240
ENH-3240: below readiness threshold (confidence 40 < 85) — run
  /ll:confidence-check ENH-3240
```

Leave the two `print(...)` marker lines byte-identical.

**Part 3 — classification.**

Distinguish gate skips from failures in the run state. Minimum viable form:
keep `success=False` (so `--only` callers still see a non-success) but record
the outcome under a `skipped_issues` mapping rather than `failed_issues`, and
render it in the summary under its own heading. This is the piece with the
widest blast radius — `state.py`, the summary renderer, and any FSM predicate
reading the state file all need checking before committing to a shape.

## Program Design

### Types
- `ReadinessStatus` (`scripts/little_loops/cli/issues/check_readiness.py:16`) gains one
  field: `confidence_present: bool`. It records whether the `confidence_score`
  frontmatter key existed, independent of its value. The existing `confidence: int`
  field and the `meets_readiness`/`meets_outcome` properties keep their current
  semantics unchanged, so every existing consumer is unaffected. Defaulting the new
  field to `True` keeps any positional construction in tests valid.

### Signatures
- `readiness_status(config: BRConfig, issue_id: str, *, default_readiness: int = 85, default_outcome: int = 65) -> ReadinessStatus | None` — `scripts/little_loops/cli/issues/check_readiness.py:41` — resolves the issue, reads frontmatter, and builds the status. This is where `fm.get("confidence_score") or 0` lives and where `confidence_present` must be populated from `"confidence_score" in fm` before the coercion discards the distinction.
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/check_readiness.py:95` — the `ll-issues check-readiness` entry point. Requires both thresholds and ignores `enabled`. Must not change: `autodev.yaml` invokes it at three sites with `--readiness`/`--outcome`.
- `_stamped_result(**kwargs: Any) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:768` — the local closure stamping base-state onto every outcome. The gate branch's `success=False` return flows through here, which is where a distinct skip classification would have to be expressed.

### Call Path
The gate path this bug reports:
`ll-auto --only <ID>` -> `AutoManager._process_issue()` -> the pre-Phase-1 gate at `scripts/little_loops/issue_manager.py:806-833` -> `readiness_status()` (`check_readiness.py:41`) -> `parse_frontmatter()` -> `int(fm.get("confidence_score") or 0)` at `check_readiness.py:87` -> `ReadinessStatus.meets_readiness` -> `logger.warning(...)` + two `print(...)` markers -> `_stamped_result(success=False, failure_reason="below_readiness_threshold ...")` -> `state.failed_issues` -> `_log_timing_summary()` at `issue_manager.py:1949`.

The spec this path is meant to mirror:
`skills/manage-issue/SKILL.md:183` — "If absent or below `readiness_threshold` and `--force-implement` is not set, HALT and direct the user to run `/ll:confidence-check [ID]`."

### Decision Rules
- **Add a field, do not change `confidence`'s type.** Making `confidence` an `int | None` would force every consumer to handle the None case. The `ReadinessStatus` docstring already establishes the pattern of carrying multiple narrow signals rather than one collapsed verdict, precisely so different callers stay correct; `confidence_present` follows it.
- **The gate decision does not change.** Absent and zero both halt today and must both halt after this fix. Only the reported reason and the classification differ. This keeps the fix free of any behavior change for the pass/fail path.
- **Marker strings are frozen.** `CONFIDENCE_GATE_BLOCKED <ID>` and `PHASE1_NOT_STARTED <ID> confidence_gate` are consumed by `autodev.yaml`'s `check_impl_reached` discriminator (see the comments at `issue_manager.py:819-826`). Remediation text goes on the `logger.warning` line, never into the marker lines.
- **Threshold resolution stays the raw-JSON read.** `readiness_status`'s docstring is explicit that it must remain absence-sensitive rather than sourcing from `ConfidenceGateConfig`, because the config dataclass cannot express "key absent" and would break `autodev.yaml`'s `--readiness`/`--outcome` fallback. Do not refactor it while in this file.
- **Parts 1-2 and Part 3 are separable.** Parts 1-2 touch two files and carry no state-shape change. Part 3 touches `AutoManagerState`, the summary renderer, and `parallel/orchestrator.py`'s mirror — see Open Questions.

## Open Questions

- Should Part 3 land here or split into its own issue? It touches
  `AutoManagerState` and the parallel orchestrator's mirror of the same summary
  block (`parallel/orchestrator.py:1620,1653`), whereas Parts 1-2 are contained
  to two files.
- Does any FSM loop currently key off `failed_issues` containing gate-blocked
  IDs? If so, moving them is a behavior change for those loops and needs a
  compatibility window.

## Related Issues

- FEAT-3117 — wires an Advisor `confidence_gate` consult trigger into this exact
  call site (`issue_manager.py`'s pre-Phase-1 gate). Adjacent, not overlapping:
  it adds an escalation path, this fixes what the gate reports. FEAT-3117 is
  blocked on FEAT-3116/FEAT-3120; this issue is not.
- BUG-3253 — the auto-correction rate metric distorted by this issue's
  failure-classification half.

## Related Key Documentation

- `skills/manage-issue/SKILL.md:179-183` — Phase 2.5 confidence gate spec, the
  behavior `ll-auto`'s gate is meant to mirror.

## Status

**Open** | Created: 2026-08-17 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-08-18T01:35:12 - `f0f6a7d7-4813-4604-95ee-0469a847224f.jsonl`
- `/analyze_log` - 2026-08-17 - ll-auto run audit (ENH-3237, ENH-3240)
