---
id: ENH-3069
title: refine-to-ready-issue's breakdown_issue state has no resolvable pruning_profile
  (MR-12 warning)
type: ENH
priority: P4
status: done
discovered_by: capture-issue
discovered_date: 2026-08-06
captured_at: '2026-08-06T00:13:28Z'
completed_at: '2026-08-06T00:13:28Z'
relates_to:
- ENH-2805
- ENH-2714
- BUG-2831
labels:
- loops
- fsm
- tokens
testable: true
blocked_by: []
---

# ENH-3069: refine-to-ready-issue's breakdown_issue state has no resolvable pruning_profile

## Summary

`ll-loop validate scripts/little_loops/loops/refine-to-ready-issue.yaml` emitted an MR-12
Check 3 WARNING against `states.breakdown_issue.pruning_profile`: the state invokes
`/ll:issue-size-review` with no resolvable `pruning_profile` (neither a state override nor a
loop-level default).

Investigated and confirmed **legitimate** — a plain inconsistency, not a false positive.
Four of the five skill-invoking states in this loop already carried a profile;
`breakdown_issue` was the lone omission. Fixed by adding the same profile block autodev.yaml
already uses on its identical `/ll:issue-size-review ... --auto` state.

## Current Behavior

MR-12 Check 3 (`scripts/little_loops/fsm/validation/evaluator_rules.py:340-364`) warns for any
state whose `action` invokes a `/ll:` skill and whose effective pruning profile
(`_effective_pruning_profile()` — state override, else loop default) resolves to `None`.

`refine-to-ready-issue.yaml` declares no loop-level `pruning_profile`, and only four of its five
skill-invoking states declared one:

| State | Action | Profile before this change |
|---|---|---|
| `refine_issue` | `/ll:refine-issue --auto` | `refine-issue-repair` |
| `refine_followup` | `/ll:refine-issue --auto --gap-analysis` | `refine-issue-repair` |
| `wire_issue` | `/ll:wire-issue --auto` | `wire-issue-auto` |
| `verify_issue` | `/ll:verify-issues --check --auto` | `verify-issues-auto` |
| `breakdown_issue` | `/ll:issue-size-review --auto` | **none → warning** |

The realized cost is the SessionStart digest, re-sent on every invocation of the unprofiled
state. Traced end to end:

1. `FSMExecutor` resolves `state.pruning_profile or self.fsm.pruning_profile` and, when enabled
   and the action is prompt-mode, passes `automation_profile=<name>` to the action runner
   (`scripts/little_loops/fsm/executor.py:1896-1902`).
2. `host_runner` turns that into `LL_AUTOMATION=1` + `LL_AUTOMATION_PROFILE=<name>` in the child
   environment (`scripts/little_loops/host_runner.py:351-353`, and the same block in the other
   four `build_*` paths).
3. The child session's SessionStart hook sees `LL_AUTOMATION` and early-returns with only the
   stay-in-turn instruction, dropping the config-JSON + `project_context` digest payload
   (`scripts/little_loops/hooks/session_start.py:110-124`).

Note the profile *name* and `suppress_claude_md` are inert today: `suppress_catalog` /
`suppress_claude_md` are declarative-only with no runtime consumer (schema.py:460, 479), so
`enabled: true` alone is what produces the saving.

## Expected Behavior

`breakdown_issue` resolves a pruning profile like every other skill-invoking state in the loop,
and `ll-loop validate` on this file reports no warnings.

## Proposed Solution

Add the state-level profile, matching autodev.yaml's `run_size_review`
(`scripts/little_loops/loops/autodev.yaml:1342-1345`) so both `/ll:issue-size-review --auto`
call sites are identical:

```yaml
    pruning_profile:
      enabled: true
      name: issue-size-review-auto
      suppress_claude_md: true
```

### Alternatives Rejected

- **`pruning_profile_ok: true` at the loop top-level.** One line, but it suppresses all three
  MR-12 checks loop-wide — including Check 1, an ERROR-severity guard against a state's own
  `tools:` allowlist blocking its own action. Blanket-disabling a real error class to silence
  one warning is the wrong trade.
- **A loop-level `pruning_profile` default.** Also one line, but it would silently reassign a
  profile name to any skill state added to this loop later, and the four existing per-state
  overrides make the intent explicit.

## Program Design

### Types
_No new types — the change is one `pruning_profile` mapping in a loop YAML, deserialized by the
existing `PruningProfile` dataclass (`scripts/little_loops/fsm/schema.py:460, 479`)._

### Signatures
- `_validate_pruning_profile(fsm: FSMLoop, orchestration_request_path: str | None = None)
  -> list[ValidationError]` — `scripts/little_loops/fsm/validation/evaluator_rules.py:251-365`.
  **Unchanged.** Named to record that this issue satisfies Check 3 by supplying the missing
  profile, not by relaxing the rule.
- `_effective_pruning_profile(fsm, state)` — resolves the state override then the loop default;
  returns `None` when neither is set, which is the sole trigger for the Check 3 warning.

### Decision Rules
_N/A — no new decision logic._ The change is declarative YAML; every predicate involved
(`_SKILL_INVOKE_RE`, the `profile is None` test) already exists and is untouched.

### Call Path
`ll-loop validate` → `validate_fsm()` → `_validate_pruning_profile()` → `_effective_pruning_profile()`
(now resolves a profile for `breakdown_issue` instead of `None`).

At runtime: `FSMExecutor._execute_action` (`fsm/executor.py:1896-1902`) → `automation_profile`
kwarg → `host_runner` `build_*` (`host_runner.py:351-353`) → `LL_AUTOMATION=1` in the child env →
`hooks/session_start.py:110-124` early-return, suppressing the config + digest payload.

## Impact

Small and bounded. `breakdown_issue` runs at most once per loop run (it routes straight to
`write_broke_down → done`), so this is consistency-with-autodev more than a meaningful token
win — roughly the SessionStart digest (~1K tokens) on the runs that reach size-review at all.
No behavioral change to the size-review invocation itself.

## Scope Boundaries

- Only `states.breakdown_issue` in `refine-to-ready-issue.yaml` was touched.
- No change to MR-12 itself, to the pruning machinery, or to `suppress_catalog` /
  `suppress_claude_md` remaining declarative-only.
- No sweep of other loops for the same warning class.

## Acceptance Criteria

- [x] `ll-loop validate scripts/little_loops/loops/refine-to-ready-issue.yaml` exits 0 with no
      MR-12 warning
- [x] `breakdown_issue`'s profile block matches `autodev.yaml`'s `run_size_review`

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules (MR-1..MR-14)
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — `_validate_pruning_profile()`

## Resolution

- **Action**: improve
- **Completed**: 2026-08-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: added a `pruning_profile`
  (`enabled: true`, `name: issue-size-review-auto`, `suppress_claude_md: true`) to the
  `breakdown_issue` state, with a comment recording why the name/shape mirrors autodev.yaml and
  what enabling it actually saves

### Verification Results
- `ll-loop validate scripts/little_loops/loops/refine-to-ready-issue.yaml`: PASS, no warnings
  (previously one MR-12 Check 3 WARNING)
- Test suite: not run — single-state YAML metadata change with no runtime behavior change beyond
  the `LL_AUTOMATION` env signal already exercised by the loop's other four profiled states

## Status

**Completed** | Created: 2026-08-06 | Priority: P4


## Session Log
- `hook:posttooluse-status-done` - 2026-08-06T00:14:06 - `22a2d710-b927-4674-8d5f-e2d567aaea06.jsonl`
