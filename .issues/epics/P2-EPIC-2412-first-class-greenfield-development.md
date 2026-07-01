---
id: EPIC-2412
title: "Make end-to-end greenfield project development a first-class capability"
type: EPIC
priority: P2
status: open
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
relates_to:
- FEAT-2413
- FEAT-2414
- ENH-2415
- FEAT-2416
- BUG-2417
- ENH-2418
- ENH-2419
- EPIC-1811
labels:
- loops
- orchestration
- greenfield
- verification
- rn-build
---

# EPIC-2412: Make end-to-end greenfield project development a first-class capability

## Summary

The `rn-*` greenfield loop family (`rn-build` → `goal-cluster` → `rn-implement`
→ `rn-remediate`/`rn-decompose`, plus the `rn-plan`/`rn-refine` planning stack)
is **deep on orchestration but shallow on proof**. The FSM plumbing is mature and
battle-hardened — non-LLM routing, cycle detection, outcome-token parent/child
communication, near-universal `on_error` fail-open edges, resume, `run_dir`
isolation, and all 13 tracked `rn-build` robustness issues closed (see EPIC-1811).
But two structural gaps keep it from being a first-class greenfield builder:

1. **Verification of generated code is LLM-only.** Nothing in `rn-implement` or
   `rn-remediate` compiles, tests, lints, type-checks, or runs the code. "Implemented"
   is defined as `/ll:confidence-check` scoring the *issue text* as ready plus a
   git diff existing (`verify_issue_completed` in `issue_lifecycle.py:407` reads
   `status:` frontmatter; `verify_work_was_done` only checks a diff exists). The one
   real code-run gate — `rn-build`'s eval harness — is optional, LLM-installed, and
   silently degrades to "no verification / done" on every absence/error path.
2. **Project-type coverage is narrow.** True empty→working-project greenfield only
   exists for single-page static HTML (`html-website-generator`), interactive
   client-side widgets (`interactive-component-generator`), and CLI wrappers over
   existing software (`cli-anything-bootstrap`). There is **no** greenfield loop for
   a full-stack web app, REST/GraphQL API service, packaged library with CI, mobile
   app, or data pipeline. Anything with a server, database, or multi-service topology
   falls through to the generic `general-task` loop with no archetype scaffolding and
   no runtime gate.

This is notable because the repo's own CLAUDE.md rigorously enforces "pair every LLM
self-grade with a non-LLM evaluator" (MR-1, citing SHOR's 33–55% self-grade accuracy)
— for *meta*-loops. The product build path does not hold itself to the same bar.

## Motivation

Greenfield is the highest-leverage use of the loop engine (spec → shipped project),
but today a run can terminate `done` while the generated project does not build, its
tests do not pass, and its features have never been exercised together. Closing the
verification gap and adding project-type breadth converts an impressive scaffolder
into a builder whose "done" means the project actually builds, runs, and satisfies
its own acceptance criteria.

## Goal

When this epic is done:

- The implement path (`rn-implement`/`rn-remediate`) gates `IMPLEMENTED` on a **real
  code run-gate** (build + test + typecheck + lint, and service-start/health probe
  where applicable), not on LLM-scored issue text (FEAT-2413).
- `rn-build` runs an **end-to-end integration/acceptance phase** after
  `cluster_execute` that stands up the assembled project and executes the spec's
  `## Acceptance Criteria` as runnable checks (FEAT-2414).
- The eval harness is **mandatory and loud** — its absence routes to `build_failed`,
  never silently to `done` (ENH-2415).
- `rn-build` supports **project archetypes** (static-web, cli, api-service,
  full-stack, library, data-pipeline), each supplying type-specific scaffolding and
  its own real run-gate, selected at scope time (FEAT-2416).
- Residual correctness debt is cleared: `rn-plan-apo`'s broken optimizer spine
  (BUG-2417), `rn-refine`'s unguarded in-place source overwrite (ENH-2418), and the
  untested `run_dir`-across-`with:` framework fix (ENH-2419).

## Scope Boundaries

- In scope: the `rn-*` build/plan family, `goal-cluster` dispatch, the eval-harness
  templates, and a reusable code run-gate oracle (generalizing the proven patterns in
  `oracles/generator-evaluator.yaml` and `cli-anything-bootstrap.yaml`).
- Out of scope: the backlog-automation family (`autodev`, `auto-refine-and-implement`,
  sprint loops) except where they share the new run-gate; deployment/CD infrastructure
  beyond a local service-start/health probe.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (meta-loop MR rules, MR-1 rationale)
- `docs/guides/LOOPS_GUIDE.md` (Cluster vs Composer vs Router; rn-build orchestration)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (`ll-loop run --baseline` validation)
- Prior family EPIC-1811 (rn-build capstone, closed)
