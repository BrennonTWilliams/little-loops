---
id: BUG-3704
type: BUG
title: Native 1M models use stale 200k context limits
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-03T01:25:23Z'
---

# BUG-3704: Native 1M models use stale 200k context limits

## Summary

Native 1M Claude models currently fall back to 200 000 tokens in Python and the shell context monitor. This prematurely triggers handoff and compression. Correcting the table also needs to preserve lower effective host limits; raising the denominator without that handling could delay a handoff past the actual limit. Split from BUG-3701 during its pre-implementation review with `/ll:advise` (Opus, 2026-10-02).

## Current Behavior

- `scripts/little_loops/context_window.py:19` has no Claude 5.x entries; all existing entries equal the 200 000 floor, including a fictitious `claude-opus-3-7` entry.
- `hooks/scripts/context-monitor.sh:179` handles `[1m]` but otherwise returns 200 000. Its caller at line 335 supplies the environment override.
- Live [Sonnet 5.5 specifications](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) and [Claude Code model configuration](https://code.claude.com/docs/en/model-config) confirm native 1M for Sonnet 5/5.5. The latter also documents `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`, gateway limits, and other host-specific caps. API maximum and effective host window are different contracts.
- The table also understates some 4.x native windows according to the current Claude Code docs (Opus 4.7/4.8); verify exact IDs individually before changing them.

## Expected Behavior

Resolve the effective window used by each consumer, with explicit LL overrides taking precedence and verified model defaults used only when no lower host constraint applies. Python and shell must agree for equivalent inputs. Preserve the conservative 200k floor for unknown IDs and retain real legacy model entries regardless of whether they have pricing coverage.

## Motivation

The stale denominator triggers avoidable continuation and compression on native-1M sessions. A safe correction must preserve lower deployment limits while sizing unconstrained sessions accurately; changing only the constants could suppress a required handoff.

## Proposed Solution

1. Audit consumers before choosing a shared model-capacity helper versus a host-aware effective-window resolver. Known consumers include `issue_manager.py`, `subprocess_utils.py`, `parallel/worker_pool.py`, `compression/heuristic.py`, `compaction/instant.py`, and the shell context monitor. Record which consumes an observed model, an API request model, or no model.
2. Verify exact native windows from official model specifications. At minimum cover Sonnet 5/5.5, Opus 5.5, and Fable 5.1; audit legacy 5.x and Opus 4.7/4.8 separately. Remove fictitious `claude-opus-3-7`; retain real `claude-sonnet-4-5`. Do not require context-window keys to be a subset of `MODEL_PRICING`.
3. For Claude Code consumers, account for documented native-1M caps such as `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`. Define precedence relative to explicit LL overrides and `[1m]` before implementation. Do not inject CLI-only caps into SDK compression. For unobservable provider/gateway limits, document the existing explicit override instead of guessing the deployment capacity.
4. Mirror model defaults in the shell layer and require automated, environment-isolated parity tests. Exercise explicit/config and positive environment overrides, `[1m]`, verified native windows, a lower host cap, and unknown-model fallback. Test source-extracted functions or a supported test seam without executing the hook's main routine.
5. Check the affected models' official long-context pricing before release. [Current pricing](https://platform.claude.com/docs/en/about-claude/pricing) and Claude Code docs state standard pricing for current native-1M models; preserve that evidence and keep unrelated TTL/geography pricing out of scope.

## Integration Map

### Files to Modify

- `scripts/little_loops/context_window.py` — model capacities and documented effective-window contract, after consumer audit
- `hooks/scripts/context-monitor.sh` — shell resolution and matching precedence
- `scripts/tests/test_context_window.py` — native-window, override, cap, and Python/shell parity cases
- `docs/reference/API.md` — context-window contract and examples
- Consumer files listed below only where the audited host/API boundary requires an explicit effective-window argument

### Dependent Files

- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/subprocess_utils.py`, `scripts/little_loops/parallel/worker_pool.py`
- `scripts/little_loops/compression/heuristic.py`, `scripts/little_loops/compaction/instant.py`
- `scripts/tests/test_issue_manager.py`, `scripts/tests/test_worker_pool.py`, and compression/compaction tests for changed consumers

## Implementation Steps

1. Document consumer contracts, exact vendor sizes, and cap/override precedence.
2. Implement the smallest host-aware correction; update Python and shell together.
3. Add automated parity and consumer threshold regression tests; update affected documentation.
4. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — current behavior is conservative but triggers early continuation and compression; an incorrect 1M correction could delay required handoffs
- **Effort**: Medium — effective-window contract and consumer audit, beyond a constants-only change
- **Risk**: Medium — a larger window changes handoff and compression thresholds

## Steps to Reproduce

1. Clear `LL_CONTEXT_LIMIT` and call `context_window_for('claude-sonnet-5-5')`.
2. Observe 200 000 despite the published native 1M window.
3. Compare `get_context_limit` with the same model and no config override; it also returns 200 000.

## Root Cause

`MODEL_CONTEXT_WINDOW` and the shell `get_context_limit()` mapping predate native 1M models. The generic Python helper is also used by API compression and compaction, so blindly applying Claude Code environment flags there could incorrectly change SDK behavior.

## Acceptance Criteria

- [ ] Exact changed model IDs cite official window sizes; fictitious `claude-opus-3-7` is removed and real legacy entries are retained independently of pricing coverage
- [ ] Consumer audit separates model capacity from effective CLI/API limits and records override/cap precedence
- [ ] Verified Sonnet 5/5.5 native windows resolve to 1M when unconstrained; a documented Claude Code 200k cap remains 200k on relevant host consumers
- [ ] Explicit LL overrides, `[1m]`, and unknown-model fallback retain their documented behavior; CLI-only environment flags do not change SDK compression
- [ ] An automated Python/shell parity test runs within pytest with environment isolation and equivalent inputs
- [ ] Changed consumer handoff/compression thresholds have regression coverage and docs match the effective-window contract
- [ ] Current long-context pricing assumptions are source-cited
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3701 — alias/rank correction; independent of this context-window change
- BUG-3696 — exact Sonnet 5.5 pricing; independent of context-window coverage
- ENH-2282 — original shared context-window mapping, already done
- BUG-3541 — earlier alias correction explicitly left context windows out of scope, already done

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Existing context-window precedence and consumers |
| `docs/ARCHITECTURE.md` | Continuation and compression boundaries |

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-03T01:30:45 - `7cd57e8e-71e0-4299-a1a4-ccd6bda98ee6.jsonl`
