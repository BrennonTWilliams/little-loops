---
id: FEAT-2414
title: "rn-build end-to-end integration/acceptance phase"
type: FEAT
priority: P2
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Large
relates_to:
- EPIC-2412
- FEAT-2413
- ENH-2415
labels:
- loops
- verification
- greenfield
- rn-build
- e2e
---

# FEAT-2414: rn-build end-to-end integration/acceptance phase

## Summary

Add an **end-to-end integration/acceptance phase** to `rn-build` that runs after
`cluster_execute` (once all features are built): stand up the assembled project and
execute the spec's `## Acceptance Criteria` as runnable checks. Today every feature
is built and self-judged in isolation via `goal-cluster` → `rn-implement`, so the
features are **never exercised together** and the acceptance criteria in the spec
template are read by an LLM but never executed.

## Current Behavior

`rn-build` builds and self-judges every feature in isolation via `goal-cluster` →
`rn-implement`. Features are never exercised together, and the spec's
`## Acceptance Criteria` are read by an LLM but never executed. Cross-feature
integration bugs (shared state, interface drift) stay invisible until a human runs the
project.

## Expected Behavior

After `cluster_execute` completes, `rn-build` stands up the assembled project and
executes the spec's acceptance criteria as runnable checks, scored by a non-LLM
`output_numeric` gate. A spec whose criteria cannot all be satisfied terminates
non-`done` with a per-criterion breakdown.

## Use Case

**Who**: A developer running `rn-build` against a multi-feature spec.

**Context**: All features have been built independently and the loop is about to report
the build outcome.

**Goal**: Verify the whole project integrates and the spec's acceptance criteria
actually hold before the run is marked `done`.

**Outcome**: Integration failures are caught automatically with a per-criterion report
instead of surfacing only when a human runs the project.

## Motivation

`rn-build` already requires `## Acceptance Criteria` in the spec (`specs/SPEC_TEMPLATE.md`)
and normalizes for its presence via non-LLM grep gates. But nothing turns those
criteria into an executable contract. The existing `eval_gate` verifies *an* installed
harness runs `project.test_cmd`; it does not verify the whole project integrates or
that the spec's acceptance criteria actually hold. Cross-feature integration bugs
(shared state, interface drift between independently-built issues) are invisible until
a human runs the project.

## Proposed Solution

Insert an `integration_gate` phase between `cluster_execute`/`check_build_outcome` and
`synthesize_result`:

1. `derive_acceptance_checks` — LLM converts each spec acceptance criterion into a
   concrete runnable check (a test command, an HTTP request + expected response, a CLI
   invocation + expected output), written to `${run_dir}/acceptance/checks.json`.
2. `run_acceptance` — a shell state that executes each check against the built project
   (starting the service/build first via the FEAT-2413 run-gate where relevant),
   recording pass/fail per criterion to `${run_dir}/acceptance/results.json`.
3. `score_acceptance` — non-LLM: `output_numeric` on pass count / total; routes
   `on_no` to a bounded remediation re-entry (feed failures back as issues), else to
   `synthesize_result`.

Reuse FEAT-2413's run-gate for build/service startup rather than duplicating it.

## Implementation Steps

1. Add the three states to `rn-build.yaml`, artifact-versioned under `${run_dir}/acceptance/`.
2. Wire `check_build_outcome` `on_yes` → `derive_acceptance_checks` (before harness).
3. Route acceptance failures through the existing `capture_eval_failures` →
   `cluster_execute` re-entry, respecting `max_eval_retries`.
4. Distinguish a new terminal `acceptance_failed` (`success: false`) so partial
   integration is not reported `done`.
5. Update `synthesize_result` JSON to include per-criterion acceptance results.

## Acceptance Criteria

- A spec whose criteria cannot all be satisfied by the built project terminates
  non-`done` with a per-criterion breakdown.
- `results.json` is derived from actually executing checks against the running
  project, not from an LLM reading code.
- E2E test (gated on `PYTEST_INTEGRATION=1`) extends the existing `TestE2E`
  (ENH-2014) to assert acceptance results are produced and honored.

## Scope Boundaries

- Depends on FEAT-2413 for build/service startup primitives.
- Does not add archetype-specific check derivation (FEAT-2416 supplies that); a
  generic derivation is sufficient here.

## Integration Map

- Modified: `rn-build.yaml` (new integration phase + `acceptance_failed` terminal,
  `synthesize_result`).
- Reuses: `oracles/code-run-gate.yaml` (FEAT-2413), existing eval-retry loop.

## Impact

- **Priority**: P2 - Turns the spec's acceptance criteria into an executable contract,
  closing the cross-feature integration gap that currently escapes all automated gates.
- **Effort**: Large - Three new states plus a new terminal in `rn-build.yaml`, wired
  into the existing eval-retry loop; depends on FEAT-2413's run-gate primitives.
- **Risk**: Medium - Adds a new failure terminal to the core build path; generic
  (non-archetype) check derivation limits false negatives.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P2
