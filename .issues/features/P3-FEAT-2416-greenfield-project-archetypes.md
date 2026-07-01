---
id: FEAT-2416
title: "Greenfield project archetypes with type-specific run-gates and routing"
type: FEAT
priority: P3
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: XLarge
relates_to:
- EPIC-2412
- FEAT-2413
- FEAT-2414
labels:
- loops
- greenfield
- archetypes
- rn-build
- coverage
---

# FEAT-2416: Greenfield project archetypes with type-specific run-gates and routing

## Summary

Introduce **project archetypes** so `rn-build` can build real software beyond the
current narrow surface. True empty→working-project greenfield today only covers
single-page static HTML, interactive client-side widgets, and CLI wrappers over
existing software. Add archetypes for `api-service`, `full-stack`, `library`, and
`data-pipeline` (formalizing `static-web` and `cli` too), each supplying its own
scaffolding, type-specific research/design prompts, and — critically — its own **real
run-gate** (server-start + endpoint probe, DB migration, `pip install` + import,
CI dry-run). Route `rn-build` to the right archetype at scope time.

## Current Behavior

True empty→working-project greenfield only covers single-page static HTML, interactive
client-side widgets, and CLI wrappers over existing software. Anything with a server,
database, or multi-service topology falls through to the generic `general-task` loop
with no domain scaffolding and no runtime gate.

## Expected Behavior

`rn-build` detects a project archetype (`static-web`, `cli`, `api-service`,
`full-stack`, `library`, `data-pipeline`) at scope time and applies archetype-specific
scaffolding, research/design prompts, and a real run-gate (server start + endpoint
probe, DB migration, install + import, CI dry-run). Unknown specs fall back to
`generic` without crashing.

## Motivation

Anything with a server, database, or multi-service topology currently falls through
to the generic `general-task` loop with no domain scaffolding and no runtime gate.
The difference between "handles static artifacts" and "handles real software" is
archetype-specific scaffolding plus an archetype-specific execution gate. The proven
gate patterns already exist (`cli-anything-bootstrap`: venv install + pytest;
`generator-evaluator`: Playwright render + optional vision) and should be extended,
not reinvented per project.

## Use Case

A user writes a spec for a REST API with a database and runs `rn-build`. The loop
detects the `api-service` archetype, scaffolds the framework + migrations + routes,
builds features, then the run-gate starts the server, runs migrations, and probes
endpoints — failing loudly if the service does not come up or a route regresses.

## Proposed Solution

1. Add archetype definitions under `scripts/little_loops/templates/archetypes/`
   (one dir per archetype): scaffold files, `research`/`design` prompt fragments,
   and a `run_gate` command matrix consumed by the FEAT-2413 oracle.
2. Add a `detect_archetype` state early in `rn-build` (after `load_normalized`):
   non-LLM signals from the spec (keywords, requested stack) + an LLM classifier,
   with the resolved archetype written to `${run_dir}/archetype.txt` and defaulting to
   `generic` when unsure.
3. Parameterize `tech_research`/`design_artifacts`/scaffolding by archetype fragment.
4. Each archetype provides its `code-run-gate` matrix (FEAT-2413) and acceptance-check
   derivation hints (FEAT-2414).
5. Document archetypes and selection in `docs/guides/LOOPS_GUIDE.md`.

Archetypes to ship: `static-web`, `cli`, `api-service`, `full-stack`, `library`,
`data-pipeline`. (Mobile deferred — see Scope Boundaries.)

## Acceptance Criteria

- `rn-build` on an API spec selects `api-service`, scaffolds a runnable service, and
  its run-gate starts the server + probes an endpoint (non-LLM pass/fail).
- Archetype selection is recorded and overridable via `--context archetype=<name>`.
- Each shipped archetype has an E2E smoke (gated on `PYTEST_INTEGRATION=1`) that
  reaches a passing run-gate from a sample spec.
- Unknown/ambiguous specs fall back to `generic` without crashing.

## Scope Boundaries

- Mobile (iOS/Android/React Native) and full CD/deployment are explicitly out of
  scope for the first cut; the run-gate is a local build/start/probe.
- Depends on FEAT-2413 (run-gate oracle) and pairs with FEAT-2414 (acceptance phase).

## Integration Map

- New: `templates/archetypes/*`, `detect_archetype` state.
- Modified: `rn-build.yaml` (archetype-parameterized research/design/scaffold + gate),
  `LOOPS_GUIDE.md`.

## Impact

- **Priority**: P3 - High-value expansion of what greenfield can build, but gated behind
  FEAT-2413/FEAT-2414 and larger than the immediate robustness fixes.
- **Effort**: XLarge - Six archetype definitions, a new `detect_archetype` state,
  parameterized research/design/scaffolding, per-archetype run-gates and E2E smokes.
- **Risk**: Medium - Broad surface area across `rn-build`; mitigated by a `generic`
  fallback and per-archetype smoke tests.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P3
