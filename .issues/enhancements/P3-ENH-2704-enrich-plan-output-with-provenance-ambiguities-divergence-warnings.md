---
id: ENH-2704
title: 'Enrich --plan with provenance + ambiguities; divergence warnings on re-init'
type: ENH
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
depends_on:
- FEAT-2703
labels:
- init
- cli
- provenance
- plan-apply
---

# ENH-2704: Enrich `--plan` output with provenance + ambiguities; divergence warnings on re-init

## Summary

Surface FEAT-2703's introspection results through the machine-readable
surface: `ll-init --plan` gains a `provenance` map and an `ambiguities` list,
and re-init/`--upgrade` warns when freshly-detected values diverge from the
existing config instead of silently keeping one side. This is the contract
FEAT-2705's agentic skill consumes — the plan must tell a reader *which*
proposed values are verified facts and *which* need judgment.

## Current Behavior

- `_run_plan` (init/cli.py:455-488) emits
  `{detected, proposed_config, host_options, warnings}` — every value in
  `proposed_config` looks equally authoritative, whether it came from a
  manifest declaration or a template literal.
- Re-init keeps existing config values (correct) but says nothing when
  detection now disagrees with them; `--upgrade` is silent too (only adapter
  staleness is warned, cli.py:165-184).

## Expected Behavior

`ll-init --plan` output shape (additive keys):

```json
{
  "detected": { ... },
  "proposed_config": { ... },
  "provenance": {
    "project.src_dir": {"source": "inferred", "evidence": "sole package marker scripts/little_loops/__init__.py"},
    "project.test_cmd": {"source": "declared", "evidence": "[tool.pytest.ini_options] in pyproject.toml"},
    "project.type_cmd": {"source": "default", "evidence": "template python-generic.json"}
  },
  "ambiguities": [
    {"key": "project.src_dir", "candidates": ["scripts/", "src/"], "note": "multiple package markers"}
  ],
  "host_options": { ... },
  "warnings": [ ... ]
}
```

On re-init (`--yes` without `--force`) and on `--upgrade`, when introspection
produces a `declared` value that differs from the existing config, print a
warning naming both values and which one was kept:

```
Warning: config has test_cmd 'pytest' but pyproject.toml declares
'python -m pytest scripts/tests/' — keeping existing config value.
  Review: ll-init --plan
```

Existing values are still kept (no behavior change to the merge); the change
is purely informational.

## Proposed Solution

- Extend `_run_plan` to run introspection (FEAT-2703) and serialize
  `provenance` + `ambiguities` alongside `proposed_config`. Keys absent from
  the provenance map are implicitly template/schema defaults.
- Add a `_warn_config_drift(existing_config, introspected)` helper called
  from `_run_yes` on the merge path (near cli.py:399) and from the
  `--upgrade` path; only `declared`-provenance divergences warn (inferred
  ones would be too noisy).
- Document the plan schema in the CLI epilog / docs so external tooling can
  rely on it.

## Acceptance Criteria

- `ll-init --plan` on a fixture with mixed declared/default values emits a
  provenance entry per introspected key and an entry in `ambiguities` for the
  multi-candidate src_dir fixture.
- Plan output remains valid input to `ll-init apply --config` (round-trip
  test) — new keys are ignored by apply.
- Re-init fixture with a divergent declared test_cmd prints the drift warning
  to stderr and leaves the config value unchanged.
- `--plan` stdout stays pure JSON (warnings to stderr only).
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: plan payload extension, drift warnings, schema documentation.
- **Out**: any change to merge/keep semantics; interactive resolution
  (FEAT-2705); provenance for feature toggles (schema defaults are already
  self-describing).

## Impact

- **Priority**: P3 — the contract layer between introspection and the skill.
- **Effort**: Small-Medium.
- **Risk**: Low — additive JSON keys; apply already tolerates unknown keys by
  reading only `proposed_config`.

## Status

**Open** | Created: 2026-07-19 | Priority: P3
