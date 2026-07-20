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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/init/introspect.py` does not exist yet (confirmed via
  glob, zero matches). FEAT-2703 is `status: open`, unimplemented — this
  issue's `depends_on: FEAT-2703` is a real, currently-unmet blocker, not
  just a suggested ordering.
- `_run_plan` (`init/cli.py:455-488`) **never loads `existing_config`** —
  unlike `_run_yes`, it builds `config` purely from `template` + `choices`
  with no `load_existing_config()`/`merge_with_existing()` call at all. It
  has exactly one output statement, `print(json.dumps(plan, indent=2))` at
  line 487 — no other stdout/stderr writes in this function today, so the
  "stdout stays pure JSON" acceptance criterion already holds structurally
  and only needs preserving, not establishing.
- `_run_yes` (`init/cli.py:214-452`): `existing_config = load_existing_config(project_root)`
  at line 260; `choices` pre-population from `existing_config` at lines
  362-392 (`src_dir`, feature flags); `config = merge_with_existing(config,
  existing_config, force)` at **line 399** — the exact call the Proposed
  Solution below targets; `upgrade` branch (calls `_dispatch_host_upgrade`)
  vs. warn-only branch (calls `_warn_adapter_staleness`) split at lines
  431-438 — these two are **mutually exclusive** today (if/else), whereas
  `_warn_config_drift` must fire on both re-init *and* `--upgrade`, so it
  cannot simply piggyback on that existing if/else split.
- `build_config()` (`init/core.py:77-200`): `project` block (lines 114-120)
  is `dict(data.get("project", {}))` — a straight template copy. Only
  `project["name"]` and `project["src_dir"]` have any override path via
  `choices` today; `test_cmd`/`lint_cmd`/`format_cmd`/`type_cmd` and all of
  `scan.*` (lines 122-126) have **zero** override mechanism in
  `build_config` currently — every one of those is a pure template literal,
  confirming FEAT-2703 must land first since `provenance` is meaningless
  without an override contract for these keys.
- `_run_apply` (`init/cli.py:491-571`): line 528,
  `config = plan.get("proposed_config") or plan`, is the **only** plan key
  ever read — confirms the round-trip acceptance criterion holds today by
  construction; new `provenance`/`ambiguities` top-level keys are silently
  ignored.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_warn_config_drift(existing_config, introspected)` should model
  `_warn_adapter_staleness()` (`init/cli.py:165-184`) — the existing
  divergence-warning pattern in this same file: compare two named sources of
  a fact, warn only on inequality, `print(..., file=sys.stderr)`. The
  `_run_yes` loop at lines 440-447 shows the established stderr-warning
  convention for reuse (`f"Warning: {w.message}"` + optional
  `install_hint` line, `file=sys.stderr`).
- Unlike `_warn_adapter_staleness` (called only from the non-upgrade
  `else` branch, line 438), `_warn_config_drift` must be called
  unconditionally near the `merge_with_existing` call (line 399) — config
  drift is orthogonal to whether host adapters are being regenerated, so it
  cannot reuse the existing `if upgrade: ... else: ...` branch structure at
  lines 431-438.
- A ready-made `value + source + evidence` dataclass shape already exists
  in this codebase to model `IntrospectedValue` after:
  `CapabilityEntry`/`HookEntry` (`host_runner.py:123-145`,
  `frozen=True`, `Literal` status field + `note: str` evidence field) and
  `ProviderStatus` (`codequery/core.py:47-66`).
- The `ambiguities` list's `{"key", "candidates", "note"}` shape mirrors the
  existing `DependencyProposal` dataclass
  (`dependency_mapper/models.py:11-31`, fields `reason`/`rationale`/
  `confidence`) and its JSON serialization in `cli/deps.py:379-420` — a
  precedent for flattening a list of proposal-like dataclasses into a
  `--format json`/`--plan` payload.
- `DepWarning` (`init/validate.py:14-19`, fields `message`/`install_hint`)
  is the dataclass `_run_plan`'s existing `warnings` key already serializes
  as flat dicts (`cli.py:485`) — the `provenance`/`ambiguities` dict shapes
  in this issue's example JSON should follow that same flat-dict-per-entry
  convention for consistency.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_run_plan()` (lines 455-488): thread
  FEAT-2703's `introspect(project_root, template)` output into `choices`
  before `build_config()`, then serialize `provenance`/`ambiguities` onto
  the `plan` dict before the single `print(json.dumps(plan, indent=2))`
  call at line 487.
- `scripts/little_loops/init/cli.py` — `_run_yes()`: call
  `_warn_config_drift(existing_config, introspected)` near the
  `merge_with_existing` call at line 399, unconditionally (both the
  re-init and `--upgrade` paths, independent of the existing
  `upgrade`/warn-only if/else split at lines 431-438).
- `scripts/little_loops/init/core.py` — `build_config()` (lines 77-200):
  needs an override path for `project.test_cmd`/`lint_cmd`/`format_cmd`/
  `type_cmd` and `scan.focus_dirs`, which currently have none (this is
  FEAT-2703's responsibility, but ENH-2704's provenance serialization
  depends on it existing).
- `docs/reference/CLI.md` (line 48 documents the current `--plan` shape) —
  extend with the new `provenance`/`ambiguities` keys.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:528` — `_run_apply()` reads only
  `plan.get("proposed_config") or plan`; new top-level keys are inert here
  by construction, satisfying the round-trip acceptance criterion without
  changes to `_run_apply`.

### Similar Patterns
- `scripts/little_loops/init/cli.py:165-184` — `_warn_adapter_staleness()`,
  the stderr divergence-warning pattern to model `_warn_config_drift` after.
- `scripts/little_loops/host_runner.py:123-145` — `CapabilityEntry`/
  `HookEntry`, a `frozen=True` dataclass pairing a value with a `Literal`
  status and a `note: str` evidence field, structurally close to
  `IntrospectedValue`.
- `scripts/little_loops/dependency_mapper/models.py:11-31` +
  `scripts/little_loops/cli/deps.py:379-420` — `DependencyProposal` list
  serialized to JSON, the closest existing precedent for the `ambiguities`
  list shape.

### Tests
- `scripts/tests/test_init_core.py` — `test_plan_emits_json`
  (lines 1537-1548) asserts the current plan keys; extend for
  `provenance`/`ambiguities`. `TestValidateDeps` version-mismatch tests
  (lines 1275-1291) and the `_warn_adapter_staleness` stderr triad
  (lines 2416-2454: warned-when-diverged / silent-when-matched /
  noop-when-not-applicable) are the test-shape template for
  `_warn_config_drift`.
- `scripts/tests/test_init_core.py` — `TestDetectProjectType` /
  `test_real_template_detection` (lines 310-399) shows the fixture pattern
  for manifest-driven detection tests (write real TOML/JSON content, not
  just `.touch()`, when table content like `[tool.pytest.ini_options]`
  matters — relevant for the multi-candidate `src_dir` ambiguity fixture).
- `scripts/tests/integration/test_init_e2e.py` —
  `test_plan_output_has_no_logo_and_stays_valid_json` (lines 179-193) is the
  existing model for asserting `--plan` stdout purity;
  `test_plan_apply_produces_same_artifacts_as_yes` (lines 97-142) is the
  existing plan→apply round-trip test to extend.

### Documentation
- `docs/reference/CLI.md` — `ll-init` section (lines 35-95) documents the
  current `--plan` output shape; needs the new keys added per the issue's
  own "Document the plan schema" note.

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


## Session Log
- `/ll:refine-issue` - 2026-07-19T22:49:02 - `51b0ed9e-d527-4b05-9340-b38244f69150.jsonl`
