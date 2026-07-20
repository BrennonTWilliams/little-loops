---
id: ENH-2704
title: Enrich --plan with provenance + ambiguities; divergence warnings on re-init
type: ENH
priority: P3
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-20T06:05:03Z'
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
confidence_score: 98
outcome_confidence: 85
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 20
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

### Codebase Research Findings (2026-07-20 re-refine — supersedes some findings above)

_Added by `/ll:refine-issue` — FEAT-2703 landed since the last refine pass
(2026-07-19T22:49:02); the blocker is now cleared and the codebase state has
changed materially:_

- **`FEAT-2703` is `status: done`** (`ll-issues show FEAT-2703` reports
  "Completed"). `scripts/little_loops/init/introspect.py` now exists
  (400 lines) with `introspect(root, template) -> IntrospectResult`,
  `IntrospectedValue(value, provenance, evidence)`, and
  `Ambiguity(field, candidates, note)` dataclasses exactly matching this
  issue's proposed shape. The prior finding "`introspect.py` does not exist
  yet ... a real, currently-unmet blocker" is **stale** — the dependency is
  now satisfied.
- **`_run_plan` already emits `provenance` and `ambiguities`** — this is the
  single biggest change since the last refine pass. `init/cli.py:501-564`
  (line numbers shifted from the 455-488 cited above) now calls
  `introspect(project_root, template)` at line 516 and serializes both new
  top-level keys at lines 549-561:
  ```python
  "provenance": [
      {"field": dotted_key, "value": iv.value, "provenance": iv.provenance,
       "evidence": iv.evidence}
      for dotted_key, iv in introspection.values.items()
  ],
  "ambiguities": [
      {"field": a.field, "candidates": a.candidates, "note": a.note}
      for a in introspection.ambiguities
  ],
  ```
  This is a **list of flat dicts**, not the key-indexed map shown in this
  issue's Expected Behavior JSON example (`{"project.src_dir": {...}}`) —
  the example in this issue predates the actual implementation choice and
  should be read as illustrative, not authoritative; `field` is a dict key
  inside each list entry rather than the map key itself.
- **What is genuinely still missing** (the remaining scope of this issue):
  1. `_run_plan` still does **not** load `existing_config` (confirmed: no
     `load_existing_config()` call anywhere in `_run_plan`, `init/cli.py:501-564`)
     — so `--plan` on a re-init still can't show provenance-aware divergence,
     only fresh-detection provenance.
  2. `_warn_config_drift()` does **not** exist (confirmed via
     `grep -n "_warn_config_drift" scripts/little_loops/init/cli.py` — zero
     matches). The drift-warning behavior described in Expected Behavior is
     entirely unbuilt.
  3. `docs/reference/CLI.md` does not document the plan JSON schema at all —
     the `### ll-init` section (lines 35-88) is usage-example-only, no field
     table. The issue's original citation "line 48 documents the current
     `--plan` shape" is incorrect; there is no schema documentation to
     extend, only usage examples to add schema documentation *near*.
  4. `test_plan_emits_json` (`scripts/tests/test_init_core.py:1626-1637`)
     asserts only `detected`/`proposed_config`/`host_options`/`warnings` —
     it does **not** assert `provenance` or `ambiguities` even though both
     are already implemented. This is a live test-coverage gap independent
     of this issue's remaining work; extending this test is now a same-file,
     low-effort addition rather than new-feature test-writing.
- **Line-number drift in the existing Integration Map below**: `_run_yes`'s
  `existing_config = load_existing_config(...)` call, the `choices`
  pre-population block, and `merge_with_existing(...)` have all shifted
  since the prior refine pass — `merge_with_existing` is now at
  `init/cli.py:445` (not line 399), and `_run_yes` itself now spans
  `init/cli.py:229-498`. The `upgrade`/warn-only if/else split cited
  previously is now at `init/cli.py:477-484` (not 431-438); the mutual-
  exclusivity observation (that `_warn_config_drift` cannot simply piggyback
  on this branch) still holds structurally, only the line numbers moved.

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

### Codebase Research Findings — Integration Map corrections (2026-07-20)

_Added by `/ll:refine-issue`: the Integration Map below was written before
FEAT-2703 landed and cites stale line numbers / a since-completed
sub-task. Corrected scope:_

- **`_run_plan()` provenance/ambiguities serialization is DONE** (see the
  "supersedes some findings above" block earlier in this file) — no work
  needed there beyond wiring in `existing_config` for drift detection.
- **`build_config()` override path is DONE** — FEAT-2703 shipped it;
  `introspect()`'s output already flows into `choices` (in both `_run_yes`
  and `_run_plan`) ahead of `build_config(template, choices)`.
- **Remaining real work**: (1) load `existing_config` inside `_run_plan` so
  drift can be computed there too, not just in `_run_yes`/`--upgrade`; (2)
  write `_warn_config_drift()`; (3) call it from `_run_yes` unconditionally
  near its `merge_with_existing` call; (4) document the plan schema.

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_run_plan()` (confirmed at line 501,
  `proposed_config` serialized at line 541): DONE for provenance/ambiguities;
  still needs `existing_config = load_existing_config(project_root)` threaded
  in so `_warn_config_drift` (or an equivalent inline check) can
  annotate/flag declared-vs-existing divergence in the plan itself, not just
  at apply time. If `_run_plan`'s signature changes to accept
  `existing_config`, its sole call site — `main_init()` at **cli.py:827**
  (`return _run_plan(project_root, templates_dir, feature_choices=...)`) —
  must be updated in the same change. [`/ll:wire-issue` confirmation]
- `scripts/little_loops/init/cli.py` — `_run_yes()` (now lines 229-498):
  call `_warn_config_drift(existing_config, introspection)` near the
  `merge_with_existing` call, now at **line 445** (not 399), unconditionally
  (both the re-init and `--upgrade` paths, independent of the existing
  `upgrade`/warn-only if/else split now at **lines 477-484**, not 431-438).
- ~~`scripts/little_loops/init/core.py` — `build_config()` override path~~ —
  **already shipped by FEAT-2703**, no longer in scope for this issue.
- `docs/reference/CLI.md` — **correction (2, superseding the 2026-07-20
  refine-pass note above)**: `/ll:wire-issue` re-checked this file directly
  and found line 48's `### ll-init` flag table **already documents** the
  full 6-key shape (`{detected, proposed_config, host_options, warnings,
  provenance, ambiguities}`) including `provenance`'s
  `{field, value, provenance, evidence}` fields and the
  `declared`/`inferred`/`default` source values — this was evidently
  updated alongside FEAT-2703's landing, after the refine-pass note above
  was written. What CLI.md still lacks is documentation of the
  **drift-warning** behavior itself (`_warn_config_drift`), since that
  function doesn't exist yet — add a short note near the `--plan`/
  `--upgrade` flag rows once it's implemented, not a new schema subsection.
- `docs/guides/GETTING_STARTED.md` (line 96) — **new finding
  [`/ll:wire-issue`]**: the `--plan` flag-table row still shows the
  pre-FEAT-2703 4-key shape (`` `{detected, proposed_config, host_options,
  warnings}` ``), omitting `provenance`/`ambiguities` entirely. Confirmed via
  direct read — this file was not previously listed anywhere in this issue.
  Needs the same key-set update as CLI.md, plus a drift-warning mention if
  in scope.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:604` — `_run_apply()` (function starts
  line 567) reads only `plan.get("proposed_config") or plan` (line number
  corrected by `/ll:wire-issue`, was cited as 528); new top-level keys are
  inert here by construction, satisfying the round-trip acceptance criterion
  without changes to `_run_apply`.

_Wiring pass added by `/ll:wire-issue`:_
- No other importer/caller/registration/config-file coupling was found.
  Confirmed via targeted trace: `skills/init/SKILL.md` only forwards
  `--yes`-path flags (`--force`, `--dry-run`, `--hosts`, `--codex`,
  `--upgrade`) and never invokes `--plan`/`apply`, so it has zero coupling
  to the new keys. `ll-doctor` (`cli/doctor.py`) does not parse plan JSON.
  `config-schema.json` validates the `.ll/ll-config.json` *config file*
  shape, not the `--plan` *output* shape — no schema file exists for the
  plan-output payload anywhere in the repo, so the only schema
  documentation surface is the CLI.md/GETTING_STARTED.md prose flag tables
  above. `.claude/CLAUDE.md`'s `ll-init` bullet already mentions
  `--plan`/`apply` and FEAT-2703's provenance tagging generically; a short
  addition noting `_warn_config_drift` once built is optional polish, not
  required wiring.

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
- `scripts/tests/test_init_core.py` — `test_plan_emits_json` (**now lines
  1626-1637**, not 1537-1548) already runs `--plan` but its assertions only
  cover `detected`/`proposed_config`/`host_options`/`warnings` — extend
  with `assert "provenance" in plan` / `assert "ambiguities" in plan`
  (both keys already populated by `_run_plan`, so this is a same-file,
  low-effort coverage gap, not new-feature test-writing). `TestValidateDeps` version-mismatch tests
  (lines 1275-1291) and the `_warn_adapter_staleness` stderr triad
  (**now lines 2505-2543**, not 2416-2454 — line drift confirmed by
  `/ll:wire-issue`: `test_warn_adapter_staleness_prints_hint` /
  `_silent_when_current` / `_noop_without_codex`) are the test-shape
  template for `_warn_config_drift` — three-case convention: (a)
  warned-when-diverged asserts both old/new values + an actionable hint
  substring in `capsys.readouterr().err`; (b) silent-when-matched asserts a
  key warning substring is absent; (c) noop-when-not-applicable asserts
  `err == ""` entirely. `test_yes_warns_when_pypi_stale_without_upgrade_flag`
  (line 2016) and `test_yes_upgrades_when_pypi_stale_with_upgrade_flag`
  (line 2043) are a second precedent, reached through `main_init(["--yes",
  ...])` rather than calling the warn function directly — useful if
  `_warn_config_drift`'s test is driven end-to-end instead of as a unit
  test. [`/ll:wire-issue`]
- **IMPORTANT correction [`/ll:wire-issue`]**: `test_plan_emits_json`'s
  provenance/ambiguities gap noted above is **already partially covered
  elsewhere** —
  `scripts/tests/integration/test_init_e2e.py::test_plan_includes_provenance_and_ambiguities`
  (line 271) already exists and already asserts `"provenance" in plan` /
  `"ambiguities" in plan` plus a `project.lint_cmd` provenance field. Check
  for redundancy before adding the `test_init_core.py` assertion — it may
  only need extending for the specific `ambiguities` src_dir fixture this
  issue's AC calls for, not the bare-membership check.
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
- `scripts/tests/integration/test_init_e2e.py::TestInitHeadlessIntrospection.test_yes_preserves_existing_config_commands_on_reinit`
  (line 242) — **the exact fixture template to copy for the AC's "divergent
  declared test_cmd" scenario** [`/ll:wire-issue`]: it already writes a
  `pyproject.toml` with declared tool config, hand-writes a pre-existing
  `.ll/ll-config.json` with *different* `test_cmd`/`lint_cmd`/etc. values,
  re-runs `_run_init(["--yes", ...])`, and asserts the existing values win —
  it just doesn't yet assert a drift warning is printed. Copy this setup,
  add `capsys.readouterr().err` capture, and assert the new warning mentions
  both the introspected candidate and the existing stored value (mirroring
  `test_warn_adapter_staleness_prints_hint`'s `"0.0.1" in err and "9.9.9" in
  err` pattern above).
  `test_yes_leaves_existing_documents_section_untouched` (line 162) is a
  second precedent for the same pre-seeded-divergent-config fixture shape.
- **New test needed, no existing coverage** [`/ll:wire-issue`]: no current
  `--plan` test seeds a pre-existing `.ll/ll-config.json` before invoking
  `--plan` — every `TestInitHeadlessIntrospection` test and both
  `test_plan_includes_provenance_and_ambiguities` (e2e:271) /
  `test_plan_emits_json` (core:1626) run against a project with no existing
  config. Once `existing_config` is threaded into `_run_plan`, add a
  `--plan`-against-existing-config test asserting the plan JSON reflects
  the divergence (this is the one genuinely new test class this issue's
  scope requires, not just an extension of an existing test).

### Documentation
- `docs/reference/CLI.md` — **correction [`/ll:wire-issue`]**: the `ll-init`
  section already documents the full 6-key `--plan` shape (see Files to
  Modify correction above) — only the drift-warning behavior note remains
  to add, not a new schema section.
- `docs/guides/GETTING_STARTED.md` (line 96) — **new finding
  [`/ll:wire-issue`]**: stale 4-key `--plan` flag-table row, not previously
  listed in this issue anywhere. See Files to Modify above for detail.

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

> ⚠ **Status note (2026-07-20, `/ll:refine-issue`)**: the first criterion
> ("provenance entry per introspected key and ambiguities entry") is
> **already met by shipped code** — `_run_plan` (`init/cli.py:501-564`)
> emits both keys today. What remains unimplemented is the third criterion
> (re-init drift warning) and the documentation criterion implied by
> "Document the plan schema" in Proposed Solution; consider re-running
> `/ll:ready-issue ENH-2704` to reassess whether the remaining scope still
> justifies a standalone issue or should fold into a smaller follow-up.

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

## Resolution

Implemented the remaining scope identified by the 2026-07-20 refine pass
(provenance/ambiguities serialization was already shipped by FEAT-2703):

- Added `_warn_config_drift(existing_config, introspection)`
  (`init/cli.py`), modeled on `_warn_adapter_staleness` — warns to stderr
  only on `declared`-provenance divergence between a freshly introspected
  value and the stored config; the stored value is always kept (no merge
  semantics changed).
- Called it unconditionally from `_run_yes` (covers both plain re-init and
  `--upgrade`, since `--upgrade` routes through `_run_yes`) and from
  `_run_plan` (which now also loads `existing_config` via
  `load_existing_config`, so `--plan` surfaces the same drift warning
  before any writes happen).
- Extended `docs/reference/CLI.md` and `docs/guides/GETTING_STARTED.md`
  with the drift-warning behavior and the up-to-date 6-key `--plan` shape.
- Tests: unit coverage for `_warn_config_drift` (warned/silent-matched/
  silent-on-inferred, mirroring the `_warn_adapter_staleness` triad),
  `test_plan_emits_json` extended to assert `provenance`/`ambiguities`,
  and two new e2e tests (`--yes` reinit drift warning,
  `--plan` against an existing divergent config).

## Status

**Done** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:manage-issue improve` - 2026-07-20T00:00:00Z - `c705cd66-6afb-483c-b508-9582384f44e6.jsonl`
- `/ll:ready-issue` - 2026-07-20T05:56:19 - `e35b4aa8-5d70-4915-97a7-a2614d14fd7c.jsonl`
- `/ll:confidence-check` - 2026-07-20T05:54:30 - `dad9889b-834c-4880-ae5d-316cdb2f671a.jsonl`
- `/ll:wire-issue` - 2026-07-20T05:52:34 - `3399cef3-e476-4cac-9310-15be48698abe.jsonl`
- `/ll:refine-issue` - 2026-07-20T05:45:10 - `f678a120-06c7-4289-aa38-220dea5a9269.jsonl`
- `/ll:refine-issue` - 2026-07-19T22:49:02 - `51b0ed9e-d527-4b05-9340-b38244f69150.jsonl`
