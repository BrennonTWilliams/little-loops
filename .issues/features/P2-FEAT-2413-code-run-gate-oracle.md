---
id: FEAT-2413
title: "Real code run-gate oracle wired into rn-implement/rn-remediate"
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
- FEAT-2414
- ENH-2415
labels:
- loops
- verification
- greenfield
- rn-implement
- rn-remediate
---

# FEAT-2413: Real code run-gate oracle wired into rn-implement/rn-remediate

## Summary

Add a reusable **code run-gate oracle** that actually runs the generated project —
build, test, typecheck, lint, and (for services) start-the-process + health probe —
scored by non-LLM evaluators (`exit_code`, `output_numeric`), and make
`rn-remediate`'s `IMPLEMENTED` verdict **require** it to pass. Today the entire
implement path judges completion from LLM-scored issue prose plus "a git diff exists,"
so plausible-but-broken code earns `IMPLEMENTED`.

## Current Behavior

The implement path judges completion from LLM-scored issue prose plus a "git diff
exists" check; `rn-implement`/`rn-remediate` never build, test, typecheck, lint, or run
the generated project. `implement`'s `on_yes → emit_implemented` fires on `ll-auto`
exit 0, and `ll-auto`'s verify phase only reads `status:` frontmatter and confirms a
diff exists.

## Expected Behavior

A reusable code run-gate oracle actually executes the generated project (build, test,
typecheck, lint, and optional service start + health probe), scored by non-LLM
evaluators. `rn-remediate`'s `IMPLEMENTED` verdict requires the gate to pass; broken
code routes to `IMPLEMENT_FAILED`.

## Use Case

**Who**: A developer running `rn-remediate` (directly or via `ll-auto`) on a
greenfield issue.

**Context**: The loop has produced a code change and is about to emit a completion
verdict.

**Goal**: Trust that an `IMPLEMENTED` verdict means the code actually builds and passes
tests, not merely that a diff exists.

**Outcome**: Implementations that fail to compile or fail tests terminate as
`IMPLEMENT_FAILED`, closing the biggest robustness hole in the greenfield family.

## Motivation

`rn-implement`/`rn-remediate` never compile, test, or run anything. `implement`'s
`on_yes → emit_implemented` fires on `ll-auto` exit 0, and `ll-auto`'s own "verify"
phase only reads `status:` frontmatter (`verify_issue_completed`,
`issue_lifecycle.py:407`) and checks a diff exists (`work_verification.py`). This is
the single biggest robustness hole in the greenfield family and directly violates the
MR-1 doctrine the repo enforces on meta-loops (LLM self-grades are 33–55% accurate).

The proven pattern already exists twice and should be generalized, not reinvented:
`oracles/generator-evaluator.yaml` (renders the artifact, snapshots per-iteration,
pairs an LLM rubric with a non-LLM `diff_stall` gate) and `cli-anything-bootstrap.yaml`
(fresh venv `pip install -e`, `--help` coverage walk, `pytest --json-report`
pass-rate — an LLM state explicitly forbidden from reading source, judging only the
measured numbers).

## Proposed Solution

Create `scripts/little_loops/loops/oracles/code-run-gate.yaml` (a `from:`-inheritable
oracle) that runs a caller-supplied command matrix and emits non-LLM verdicts:

- `build` → resolve from `.ll/ll-config.json` `project.build_cmd` (archetype default);
  gate on `exit_code`.
- `test` → `project.test_cmd` (fallback `pytest --json-report`); gate on exit code and
  a real `test_pass_rate` (`output_numeric`), captured to `${run_dir}/`.
- `typecheck`/`lint` → `project.typecheck_cmd` / `lint_cmd` (e.g. `mypy`, `ruff`);
  gate on `exit_code`.
- `service_health` (optional, archetype-driven) → start the process, poll a health
  endpoint with a bounded timeout, assert 2xx; tear down on exit.
- All quality/LLM scoring reads ONLY the measured `.txt`/`.json` files (never source),
  per the `cli-anything-bootstrap` pattern.

## Implementation Steps

1. Author `oracles/code-run-gate.yaml` with `build`/`test`/`typecheck`/`lint`/
   `service_health` states, per-iteration artifact snapshots under `${run_dir}/`, and
   `on_error` routes on every state.
2. Extend `.ll/ll-config.json` / `config-schema.json` with optional
   `project.{build_cmd,typecheck_cmd,lint_cmd,health_url,start_cmd}` (test_cmd exists).
3. Wire `rn-remediate`: after `implement`, invoke `code-run-gate` as a sub-loop before
   `emit_implemented`; a failing gate routes to a remediation pass (respecting
   `max_remediation_passes`) or `IMPLEMENT_FAILED`, not `IMPLEMENTED`.
4. Thread the gate's outcome token through `rn-implement`'s `classify_remediation`
   routing so counters/summary reflect real build status.
5. Ensure the gate is a no-op-pass for issues that legitimately produce no runnable
   code (docs-only), guarded by config/archetype, not by an LLM.

## Acceptance Criteria

- A deliberately broken implementation (compile error or failing test) yields
  `IMPLEMENT_FAILED`, never `IMPLEMENTED`.
- `test_pass_rate` and build/typecheck/lint exit codes are captured to `${run_dir}/`
  and are the routing signal (non-LLM), satisfying MR-1.
- `ll-loop validate rn-remediate` passes; the new oracle passes MR-1/MR-3.
- Integration test: `rn-remediate` on a seeded failing issue does not terminate as
  implemented.

## Scope Boundaries

- Reuses existing evaluator types; no new FSM primitive.
- Deployment/CD is out of scope — `service_health` is a local start + probe only.

## Integration Map

- New: `oracles/code-run-gate.yaml`; config schema additions.
- Modified: `rn-remediate.yaml` (implement → gate → emit_*), `rn-implement.yaml`
  (token routing).
- Pattern sources: `oracles/generator-evaluator.yaml`, `cli-anything-bootstrap.yaml`.

## Impact

- **Priority**: P2 - Single biggest robustness hole in the greenfield family; directly
  enforces the MR-1 doctrine (LLM self-grades are 33–55% accurate) on the implement path.
- **Effort**: Large - New reusable oracle plus config-schema additions and rewiring of
  two loops (`rn-remediate`, `rn-implement`); reuses existing evaluator types and two
  proven gate patterns.
- **Risk**: Medium - Changes the completion verdict of the core implement path; a
  docs-only no-op-pass guard is required to avoid false failures.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P2
