---
id: BUG-2840
type: BUG
title: claude_md_suppression reported "full" on a host that cannot do it; both pruning suppression flags are inert
priority: P2
status: done
captured_at: '2026-07-27T00:22:46Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2714
- ENH-2805
- ENH-2839
- ENH-2841
- EPIC-2456
labels:
- fsm
- orchestration
- host-abstraction
- doctor
- token-cost
completed_at: '2026-07-27T00:22:46Z'
---

# BUG-2840: claude_md_suppression reported "full" on a host that cannot do it; both pruning suppression flags are inert

## Summary

`ClaudeCodeRunner.describe_capabilities()` registered `claude_md_suppression`
with status `"full"` — on the one host that provably cannot suppress CLAUDE.md.
The other three hosts (codex, gemini, omp) all honestly reported
`"unsupported"`.

Investigating that entry surfaced a larger defect: **both suppression fields on
`PruningProfileConfig` are inert.** Neither `suppress_claude_md` nor
`suppress_catalog` is read by any code path that reaches a host invocation, so
setting either changes nothing about what the host loads.

## Current Behavior

The entry's own inline comment stated the contradiction plainly
(`host_runner.py:412-415`, pre-fix):

> ENH-2714: automation-profile invocations **rely on CLAUDE.md still loading
> normally** (suppression is via env-gated hook output, **not a host flag that
> skips CLAUDE.md itself**)

`"full"` here meant *the LL_AUTOMATION env signal is honored*, not *CLAUDE.md is
suppressed*. Those are different things, and the smaller one (~1K tokens of our
own hook output) was standing in for the larger one (~7.7K tokens of CLAUDE.md).

Field-level inertness, confirmed by grep across `scripts/little_loops`:

- **`suppress_claude_md`** — read by **no** runtime code. Referenced only in
  docstrings and JSON-schema descriptions.
- **`suppress_catalog`** — read only by `fsm/validation.py:2222` to emit an
  MR-12 WARN. Never reaches a host invocation.
- `fsm/executor.py:1674-1680` passes only `automation_profile=<name>` to the
  runner; the suppression booleans are never consulted.

The documented contract — "narrowing flags consulted only on hosts whose
capability is confirmed via `ll-doctor`" (`fsm/schema.py`), repeated in
`fsm-loop-schema.json`, `docs/ARCHITECTURE.md:769`, and
`docs/guides/LOOPS_GUIDE.md:629` — described a runtime gate that does not exist.

## Impact

1. **`ll-doctor` claimed a capability the host lacks.** Anyone running preflight
   saw `claude_md_suppression: full` and would reasonably budget for CLAUDE.md
   savings that never materialize.
2. **17 states across 3 loops looked optimized when they were not** —
   `autodev.yaml` (13 states), `refine-to-ready-issue.yaml` (3),
   `oracles/verify-confidence-scores.yaml` (2) all declare
   `suppress_claude_md: true` and get only the ~1K hook pruning.
3. **The MR-12 validator warning propagated the same false promise**, telling
   authors a state "pays the full automation-context static prefix (catalog +
   SessionStart digest + CLAUDE.md)" and implying a `pruning_profile:` would
   prune all three.
4. Measured cost of the illusion: expected ~7,704-token saving, actual ~1,632
   (ENH-2839, arm A vs. arm B).

## Root Cause

The `claude_md_suppression` capability was registered on the strength of the
LL_AUTOMATION env signal being honored, conflating "the host respects our
automation signal" with "the host can skip CLAUDE.md." The claude CLI exposes no
flag for the latter.

The inertness of both fields is a separate gap: ENH-2714 shipped the schema
surface and the env-signal path, but the wiring items that would have made
`suppress_catalog`/`suppress_claude_md` reach `build_streaming()` were never
completed, while the docstrings were written as though they had been.

## Steps to Reproduce

1. `python -c "from little_loops.host_runner import ClaudeCodeRunner; print([(c.name, c.status) for c in ClaudeCodeRunner().describe_capabilities().capabilities])"`
   → pre-fix showed `('claude_md_suppression', 'full')`.
2. `grep -rn "suppress_claude_md" scripts/little_loops --include="*.py"` →
   matches only in `fsm/schema.py` docstrings; no runtime consumer.
3. Run any loop state declaring `suppress_claude_md: true` and compare
   first-turn `cache_creation_input_tokens` against a no-profile baseline →
   delta ~1.6K, not ~7.7K.

## Expected Behavior

A capability's status reflects whether the host can actually do the thing.
Schema fields that are not wired are documented as forward-declarations rather
than as working features, so nobody budgets savings against them.

## Fix Applied

| File | Change |
|---|---|
| `scripts/little_loops/host_runner.py:412` | `claude_md_suppression` → `"unsupported"`, note stating the CLI has no flag and the env signal prunes only hook output |
| `scripts/little_loops/cli/doctor.py:64` | New `_ADVISORY_CAPABILITIES` frozenset; advisory capabilities fold in at `informational` rather than `error` severity |
| `scripts/little_loops/fsm/schema.py:422` | `PruningProfileConfig` docstring gains a warning block marking both fields declarative-only, with real token figures |
| `scripts/little_loops/fsm/fsm-loop-schema.json:388` | Both field descriptions prefixed `DECLARATIVE-ONLY (not yet implemented)` |
| `scripts/little_loops/fsm/validation.py:2170,2251` | MR-12 warning no longer implies a profile prunes catalog + CLAUDE.md; states the ~1K realized saving |
| `docs/ARCHITECTURE.md:769` | Same correction |
| `docs/guides/LOOPS_GUIDE.md:629` | Same correction, plus a "What pruning actually saves today" callout |
| `scripts/tests/test_cli_doctor.py` | Two regression tests |

### Design note: the advisory-severity carve-out

Marking the capability honestly initially **broke `ll-doctor`**.
`_exit_code_for()` (`cli/doctor.py:82`) fails on *any* `unsupported` capability,
and `_capability_check_results()` folded every host capability in at `error`
severity — so an honest `unsupported` made the primary host fail its own health
check over a missing optimization.

Rejected alternatives: leaving the status `"full"` (dishonest, the original
bug), and using `"partial"` (dodges the exit code but is equally dishonest).

Chosen: an explicit `_ADVISORY_CAPABILITIES` set folded at `informational`
severity. `claude_md_suppression` is an optimization, not a correctness
requirement — automation is fully functional without it, just more
token-expensive.

**Side effect:** codex/gemini/omp no longer fail `ll-doctor` *solely* on
`claude_md_suppression`. They may still fail on genuinely critical
capabilities; that was not audited as part of this fix.

## Acceptance Criteria

- [x] `claude_md_suppression` reports a status that matches host reality.
- [x] `ll-doctor` still exits 0 for a healthy claude-code host.
- [x] Schema, JSON-schema, validator, and docs no longer describe
      `suppress_catalog`/`suppress_claude_md` as implemented.
- [x] MR-12 warning text states the realized saving rather than implying
      catalog + CLAUDE.md are pruned.
- [x] Regression tests pin both the capability status and the advisory-severity
      behavior.
- [x] Full suite green (`python -m pytest scripts/tests/`).

## Status

Completed. Capability status corrected, advisory-severity carve-out added, and
all downstream documentation surfaces fixed; committed as `8b6ff8d5`. The two
regression tests in `scripts/tests/test_cli_doctor.py` were excluded from that
commit and remain uncommitted — until they land, the corrected status is
unpinned. Both listed follow-ups (implementing or removing `suppress_catalog` /
`suppress_claude_md`) are open and unscheduled.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-27T00:24:26 - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`
- interactive session - 2026-07-27T00:22:46Z - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-07-27
- **Status**: Completed
- **Implementation**: Corrected the capability status, added an advisory-severity
  carve-out so an honest `unsupported` optimization does not fail `ll-doctor`,
  and corrected every surface that described the two suppression fields as
  implemented.

### Verification

- Full suite: **16,436 passed, 42 skipped**, exit 0.
- `ruff check scripts/` clean; `ruff format --check` clean; `mypy` clean on
  `cli/doctor.py`.

### Files Changed

Committed as `8b6ff8d5` ("fix(doctor): report claude_md_suppression as
unsupported, not fatal") — 7 files, 82 insertions, 35 deletions.

**Note:** that commit was created by a concurrent session and did **not**
include `scripts/tests/test_cli_doctor.py`, so the two regression tests were
still uncommitted at the time of writing. Without them the capability status is
unpinned and can silently revert to `"full"` — which is how this bug arose.

### Follow-ups

- Implement `suppress_catalog` for real (largest remaining lever, ~6,429 tokens
  post-ENH-2841), or remove the field rather than shipping a permanent
  forward-declaration.
- `suppress_claude_md` has no viable host implementation today; consider
  removing it outright.
