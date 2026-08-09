---
id: ENH-3129
status: open
priority: P3
captured_at: "2026-08-09T05:58:12Z"
discovered_date: 2026-08-09
discovered_by: capture-issue
---

# ENH-3129: Add a per-issue wall-clock ceiling to ll-auto and raise the timeout default

## Summary

`automation.timeout_seconds` (default 3600) is a **per-subprocess-invocation**
budget, not a per-issue one. `ll-auto` passes it separately to every
`run_claude_command` call in an issue's lifecycle, so the real per-issue worst
case is a multiple of the configured value with no ceiling anywhere. Raise the
default to 5400 to fit observed run lengths, and add an
`automation.max_issue_wall_clock_time` ceiling mirroring the one `sprints`
already has.

## Current Behavior

`config.automation.timeout_seconds` is threaded independently into each phase:

| Site | Phase |
|------|-------|
| `issue_manager.py:838` | ready-issue |
| `issue_manager.py:911` | ready-issue retry (UNKNOWN verdict) |
| `issue_manager.py:1111` | implement |
| `issue_manager.py:1241` | continuation |
| `issue_manager.py:1445` | finalize retry (BUG-3058) |

plus the wrappers at `issue_manager.py:212`, `:350`, `:531` inside
`run_with_continuation`. With `automation.max_continuations` defaulting to 3,
a single issue can legitimately consume 6+ full timeout budgets — roughly 6
hours at the current default — and nothing tracks or caps the aggregate.

`sprints` already solves this: `sprints.max_issue_wall_clock_time` (default
2700, `config-schema.json:965-969`) is a hard per-issue ceiling enforced by the
sequential dispatch loop at `cli/sprint/run.py:91`, which records
`WALL_CLOCK_TIMEOUT` and moves to the next issue. `automation` has no
equivalent.

Separately, the 3600 default is tight in practice: the FEAT-3078 run's
implement phase finished at 59.98 minutes and was killed 15 seconds after it
committed.

## Expected Behavior

1. `automation.timeout_seconds` defaults to **5400** — headroom over observed
   ~60-minute implement phases without doubling a value that multiplies across
   five call sites.
2. A new `automation.max_issue_wall_clock_time` caps the **total** elapsed time
   across all phases for one issue. When breached, `ll-auto` stops that issue,
   records a distinct failure reason, and proceeds to the next one.
3. The two interact predictably: the per-invocation timeout bounds a single
   hung call; the ceiling bounds the issue as a whole.

## Motivation

Unattended overnight `ll-auto` runs are the primary use case. Today a single
pathological issue can absorb the entire window while the operator believes a
1-hour cap is in force. Naively raising `timeout_seconds` to 7200 — the first
instinct after the FEAT-3078 timeout — would make that worse, pushing the
uncapped worst case past 12 hours. The ceiling is what makes raising the
per-call default safe.

## Proposed Solution

**Schema** (`scripts/little_loops/config-schema.json`, `automation` block at
`:241`):

```json
"timeout_seconds": {
  "type": "integer",
  "description": "Timeout per Claude CLI invocation in seconds. Note this is per-phase, not per-issue — see max_issue_wall_clock_time.",
  "default": 5400,
  "minimum": 60
},
"max_issue_wall_clock_time": {
  "type": "integer",
  "description": "Hard per-issue wall-clock ceiling in seconds across all phases (ready, implement, continuations, finalize retry). 0 disables.",
  "default": 10800,
  "minimum": 0
}
```

**Dataclass** (`config/automation.py:17,37`): add the field with a matching
default and `data.get(...)` read.

**Enforcement**: `process_issue_inplace` already tracks `issue_start_time`
(used for `issue_timing["total"]`). Check the elapsed budget before each
`run_claude_command` and raise/return a distinct terminal reason rather than
starting a phase that cannot finish. Model the failure reason on the sprint
path's `WALL_CLOCK_TIMEOUT` so log-scraping stays consistent across drivers.

Deciding whether the ceiling should also *interrupt* an in-flight phase (vs.
only gating the next one) is the main open design question — gating the next
phase is simpler and avoids a second kill path, at the cost of overshooting by
up to one `timeout_seconds`.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json` — `automation` block
- `scripts/little_loops/config/automation.py` — dataclass + `from_dict`
- `scripts/little_loops/config/core.py:730` — `to_dict` serializer
- `scripts/little_loops/issue_manager.py` — budget check in `process_issue_inplace`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — the 8 `timeout=` sites listed above
- `scripts/little_loops/config/automation.py:114` — `ParallelConfig` reuses
  `timeout_seconds` via `timeout_per_issue` fallback; confirm the default
  change does not silently shift `ll-parallel` behavior

### Similar Patterns
- `scripts/little_loops/cli/sprint/run.py:91` — the existing ceiling
  enforcement and `WALL_CLOCK_TIMEOUT` reason to mirror

### Tests
- `scripts/tests/test_issue_manager.py` — `TestAutoManagerRun` timeout group
- `scripts/tests/test_config*.py` — default + override + schema round-trip
- `scripts/tests/test_cli_sprint.py` — guard that the sprint ceiling is unchanged

### Documentation
- `docs/reference/CONFIGURATION.md` — document both keys and the
  per-invocation vs. per-issue distinction explicitly

### Configuration
- `scripts/little_loops/config-schema.json`

## Implementation Steps

1. Add `max_issue_wall_clock_time` to schema + dataclass + serializer.
2. Change `timeout_seconds` default 3600 → 5400 in schema and dataclass (both
   places — the literal is duplicated at `automation.py:17` and `:37`).
3. Verify the `ParallelConfig` fallback at `automation.py:114` still resolves
   the intended value for `ll-parallel`.
4. Enforce the ceiling in `process_issue_inplace` against `issue_start_time`.
5. Emit a distinct failure reason; make sure it flows into the run summary and
   the state manager as a non-retryable outcome.
6. Tests + CONFIGURATION.md.

## Impact

- **Risk**: Low-to-medium. The default change affects every unattended run;
  the shared `timeout_per_issue` fallback means `ll-parallel` must be checked.
- **Benefit**: Bounded overnight runs and fewer spurious kills of
  nearly-finished phases.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CONFIGURATION.md` | Documents the `automation.*` keys being changed |
| `docs/ARCHITECTURE.md` | Automation driver design and phase sequencing |
| `docs/reference/API.md` | `little_loops.config` and `issue_manager` module reference |

## Status

- **Current**: open
- **Blockers**: None

## Session Log
- `/ll:capture-issue` - 2026-08-09T05:59:56 - `ce451e9a-4952-45a2-828c-106f17467622.jsonl`
