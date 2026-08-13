# Spike Plan Template

The `/ll:spike` skill writes its plan into this shape (generalized from the
ENH-2565 readiness-gated-pop spike, the golden example). Every **mandatory
section** below must be present in a generated `spike-<ISSUE-ID>.md`; the
`test_spike_skill.py` fixture asserts their presence. Replace bracketed
placeholders; keep the headings verbatim.

The guiding principle: a spike proves **one unprecedented internal mechanism** in
isolation with a running test, so the outcome-confidence points that the unproven
mechanism cost can be recovered on re-scoring. It is not a partial implementation
of the issue — it is the smallest standalone artifact that retires the risk.

---

## Context

_Why outcome confidence was low._ Quote the issue's `### Outcome Risk Factors`
(or `## Spike Plan`) verbatim. State, per risk factor, the concrete failure the
spike must rule out. Name the two canonical low-confidence drivers when they
apply: **(a)** the mechanism has zero precedent in the codebase, **(b)** no
existing test exercises the risky core.

Example (ENH-2565): "(a) the flock-guarded readiness-gated pop has zero precedent
in any loop YAML; (b) no existing test exercises N-worker FSM fan-out with a real
barrier."

## Approach

_The smallest standalone artifact that proves the mechanism._ Describe the isolated
library + driver + test class you will build. State explicitly what is faked or
stubbed (real barrier, real flock, in-memory queue) and why that still proves the
risky core. One paragraph — resist scope creep.

## Critical files

_Read-only references that inform the spike, and the exact spike paths to create._
List the production files whose contract the spike must honor (read-only in this
skill) and the new spike package paths under `scripts/tests/spike/<slug>/`.

## Implementation

_Package layout + API sketch._ Show the file tree under
`scripts/tests/spike/<slug>/` (library module, optional driver, test module) and
sketch the public API (function/class signatures) the spike exercises. Spike code
lives **only** under `scripts/tests/spike/`; production files are read-only.

```
scripts/tests/spike/<slug>/
├── __init__.py
├── <mechanism>.py          # the isolated library proving the core
├── driver.py               # optional: exercises the library end-to-end
└── test_<mechanism>.py     # the AC test class
```

## Acceptance Criteria → Test Table

_One row per retired risk._ Map each test to the AC / risk factor it retires. Every
`### Outcome Risk Factor` that names an unproven mechanism becomes a row. Include
**at least one regression-guard test** — e.g. an AST sniff asserting the spike does
not import the forbidden production module, so the spike stays isolated.

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_readiness_gate_blocks_until_ready` | Risk (a): unprecedented gated pop | behavior |
| `test_n_worker_barrier_synchronizes` | Risk (b): untested N-worker fan-out | behavior |
| `test_spike_does_not_import_production_core` | isolation guard | regression |

## Verification

_Exact commands, all must exit 0._ List the precise `pytest` invocations — the
spike's own AC suite **plus** the named existing regression suites the mechanism
must not break.

```bash
python -m pytest scripts/tests/spike/<slug>/ -v
python -m pytest scripts/tests/<named-regression-suite>.py -v
```

## Out of Scope

_What this spike deliberately does not do._ The real integration point (the loop
YAML, the production wiring) is out of scope — the spike proves the core only.
External-API proving stays `/ll:explore-api` territory.

## Promotion

_Post-spike move, separate PR._ On acceptance, promote the proven code from
`scripts/tests/spike/<slug>/` to `scripts/little_loops/spike/<slug>/` in a
**separate PR**. This is a manual step documented here, not performed by
`/ll:spike`.
