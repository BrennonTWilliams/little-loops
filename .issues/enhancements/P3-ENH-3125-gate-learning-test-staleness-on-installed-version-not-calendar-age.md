---
id: ENH-3125
type: ENH
title: Gate learning-test staleness on installed-version drift, not calendar age
priority: P3
status: open
discovered_date: 2026-08-08
discovered_by: ENH-3073
labels:
- learning-tests
- release
- gates
testable: true
decision_needed: false
relates_to:
- ENH-3073
- FEAT-1813
- ENH-2214
confidence_score: 90
outcome_confidence: 64
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 10
---

# ENH-3125: Gate learning-test staleness on installed-version drift, not calendar age

## Summary

`is_record_stale()` (`scripts/little_loops/learning_tests/gate.py:45-63`) compares
`record.date` against `stale_after_days` (default 30) — a purely temporal check with no
reference to whether the target's API actually changed. ENH-3073 (Option A) fixed the
*symptom* — the release gate's output now names a remediation command for every row — but
the underlying proxy is still weak: a record proven against a dependency whose installed
version has not changed becomes a warning purely by the passage of time, and the same
seven-ish records will cross the 30-day threshold again ~30 days after ENH-3073 re-proves
them.

This is Option B from ENH-3073's Proposed Solution, filed as its own issue per that
issue's "Follow-up for Option B" section and Acceptance Criteria.

## Current Behavior

`is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool`
(`scripts/little_loops/learning_tests/gate.py:45`) computes `age_days = today -
record.date` and returns `age_days > threshold`. It has no parameter for, and never
consults, the dependency's installed version — a record proven against an unchanged
dependency is flagged stale purely because 30 days elapsed.

## Expected Behavior

**Staleness is `version_drift OR age > backstop`, not version-drift alone.** An earlier
draft of this section said a record with a captured version is stale *iff* the version
differs, dropping age entirely; the Wiring Phase notes assumed an OR. The OR is the
resolved design, for two reasons: proof decays when *our* usage of an API changes, not
only when the dependency's version moves; and a record proven against a hard-pinned
dependency would otherwise never be re-verified for the life of the pin.

Concretely, `is_record_stale()` returns True when **any** of:

- a version was captured for the record and it differs from the currently installed
  version of the same distribution (**version drift** — fires regardless of age, so a
  record can go stale the day after it was proven); or
- no comparable version is available — nothing was captured, the package no longer
  resolves, or the target is not a resolvable distribution — **and** `age_days >
  stale_after_days` (today's behavior, unchanged, and the path every pre-existing record
  takes until it is backfilled or re-proven); or
- a version *was* captured and matches, **and** `age_days > stale_after_days *
  version_match_backstop_multiplier` (the backstop: a matching version buys a longer
  leash, not an unlimited one).

A record proven against a dependency whose installed version hasn't changed should not be
flagged stale by the ordinary 30-day threshold — only by the (much longer) backstop.

## Motivation

Age is a proxy for "the API may have moved." The proxy is weak when the dependency's
installed version has not changed — which is directly observable and currently not
consulted at all.

## Proposed Solution

Record the resolved package name and version in the learning-test record at prove time;
treat a record as stale on version drift, with age as the fallback and as a backstop (see
Expected Behavior for the exact predicate).

**Superseded framing — do not start from `loops/migrate-sdk-version.yaml`.** An earlier
draft of this section said that loop (FEAT-1813) already contains a reusable version
resolver. It does not; see § Codebase Research Findings below, which found the loop
re-proves via an LLM skill invocation and classifies via an LLM prompt, with no
deterministic version lookup anywhere in it. The actual starting point is
`installed_package_version()` (`scripts/little_loops/init/install_check.py:23-34`),
generalized to take a package name (see Program Design). The correct path reference for
the loop, used inconsistently below, is
`scripts/little_loops/loops/migrate-sdk-version.yaml`.

### Capture path — the load-bearing half of this issue

The reader-side change (`is_record_stale()` + its 8 call sites) is inert without a writer
that populates the new field. **Learning-test records are not written by Python.**
`write_record()` has zero production callers (grep across `scripts/` returns only tests,
`CHANGELOG.md`, and `docs/`); records are emitted as hand-written YAML by the
`/ll:explore-api` skill via the `Write` tool (`skills/explore-api/SKILL.md:208-226`), and
`docs/ARCHITECTURE.md:1568` makes "record creation is owned by `/ll:explore-api`" an
explicit design contract.

**Chosen approach: stamp the version deterministically in Python at `cmd_prove`.**
`cmd_prove` (`scripts/little_loops/cli/learning_tests.py:59-98`) already re-reads the
record via `check_learning_test(args.target)` after `ll-loop run ready-to-implement-gate`
returns (line 86); resolve the package/version there and write the two fields back with
`update_frontmatter` before the `print_json(record.to_dict())` on line 91.

Rejected alternative: adding `proven_version:` to the skill's frontmatter template and
relying on the LLM to type a correct installed version. It is non-deterministic, must be
mirrored into every host adapter copy of the skill, and a hallucinated version silently
poisons the drift comparison in the direction of "not stale". The skill template is still
documented as *permitted* to emit the fields (harmless if correct, overwritten by
`cmd_prove` either way), but nothing may depend on it doing so.

### Known costs (from ENH-3073's decision scoring, Option B: 4/12)

- `is_record_stale(record, stale_after_days)`'s signature likely widens to take an
  installed-version input, which ripples through its production call sites:
  `fsm/executor.py:1113,1161`, `hooks/learning_tests_gate.py:28,129`,
  `hooks/install_learning_gate.py:31,122`, `cli/ctx_stats.py:31`,
  `cli/history_context.py`, plus a dedicated test class in
  `scripts/tests/test_learning_tests_discoverability.py` (`TestIsRecordStale`).
- A new schema field on `LearnTestRecord` (the proven-against version) and a migration
  path for existing `.ll/learning-tests/*.md` frontmatter that predates the field.
- `scripts/little_loops/config-schema.json` additions for any new config knobs, plus
  `docs/reference/CONFIGURATION.md:893-905` and `docs/ARCHITECTURE.md:690` updates
  (both identified as Option-B-only in ENH-3073's wiring pass).
- `test_config.py` (`TestLearningTestsConfig`) and `test_install_learning_gate.py` need
  updates for the new field/behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

**Claim-grounding**: `loops/migrate-sdk-version.yaml` (FEAT-1813) does **not** contain a
deterministic version resolver, contrary to this section's framing. Its 8 states
(`list_stale`, `reprove_next`, `classify_outcome`, `apply_update`, `advance_queue`,
`prepare_report_path`, `build_report`, `done`) re-prove a target by shelling out to
`ll-action invoke explore-api --args "$TARGET"` (`reprove_next`, lines 68-122 — an LLM
skill invocation) and classify old-vs-new records via an LLM prompt in `classify_outcome`
(`fragment: llm_gate`, lines 124-154, emitting `CLASSIFY_JSON:{"verdict":
"still-valid"|"needs-upgrade"|"refuted"}`). There is no `importlib.metadata`, `pip show`,
or comparable deterministic version lookup anywhere in the file, and grep across
`scripts/little_loops/loops/` found no such helper elsewhere. FEAT-1813's own issue body
states explicitly that `LearnTestRecord` has no `versions` field and that earlier drafts
referencing one were incorrect — consistent with this finding.

The one generic-ish precedent that does exist is `installed_package_version()`
(`scripts/little_loops/init/install_check.py:23-34`), which wraps
`importlib.metadata.version("little-loops")` — but it is hardcoded to the literal string
`"little-loops"` and takes no package-name argument, so it is not directly reusable for
arbitrary third-party targets either (matches this section's own characterization of
`_warn_adapter_staleness` as "narrower... not directly reusable" — the same limitation
extends one level deeper, to the function `_warn_adapter_staleness` itself wraps).

**Net effect on scope**: a deterministic per-package version resolver (e.g.
`importlib.metadata.version(pkg_name)` parameterized by target, with a fallback for
targets that are not installed Python packages) is absent from the codebase today and
would need to be built new for this issue — it cannot be extracted from
`migrate-sdk-version.yaml`, since that loop's re-proving and classification both run
through the LLM rather than through Python version-comparison code.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Version resolver is a drop-in generalization of an existing wrapper**: `installed_package_version()` (`scripts/little_loops/init/install_check.py:23-34`) is `importlib.metadata.version("little-loops")` wrapped in `try/except importlib.metadata.PackageNotFoundError: return None` — the `"little-loops"` literal is the *only* hardcoded part (no install-path or pyproject read). Generalizing to `installed_package_version(pkg_name: str)` and catching the same `PackageNotFoundError` is the entire resolver change; no new exception-handling shape needs to be invented.
- **`LearnTestRecord.target` has no type discriminator — it is free text, not guaranteed to be a pip package name.** Confirmed via `scripts/little_loops/learning_tests/__init__.py:44-71` (plain `str` field, no enum/literal) and `skills/explore-api/SKILL.md:12-14` ("Free-text description of the system or API to explore", examples like `"Anthropic SDK streaming"`, `"Python pathlib"` — multi-word prose, not installable identifiers). `normalize_target()` (`scripts/little_loops/learning_tests/import_scan.py:57-64`) already works around this by taking only `target.split()[0].lower()` to compare against import-scanned packages, which is itself only a heuristic reduction. A version resolver keyed on `importlib.metadata.version(target)` will `PackageNotFoundError` for any multi-word or non-pip target — this is not an edge case to special-case, it is the common case for existing registry entries, and must route through the Expected Behavior's existing "no version captured → age-based fallback" path rather than being treated as a resolver bug.

_Measured correction — 2026-08-09, review pass:_

- **"the common case" is directionally right but overstated — quantify it before scoping.**
  Running `importlib.metadata.version(target.split()[0].lower())` over this repo's 33 real
  records in `.ll/learning-tests/` yields: **14 resolve (42%)** — `anthropic`, `hypothesis`,
  `mcp`, `mypy`, `playwright`, `pre-commit`, `psutil`, `pytest`, `pytest-json-report`,
  `pytest-xdist`, `pyyaml`, `questionary`, `ruamel.yaml`, `asyncio` (see hazard below);
  **6 are stdlib** (`concurrent.futures`, `fcntl`, `selectors`, `sqlite3`, `subprocess`,
  `threading`); **13 do not resolve** (`bun-types`, `claude-code`, `claude-code-hooks`,
  `codegraph`, `git`, `jq`, `kimi`, `node`, `oh-my-pi`, `opentelemetry`, `phoenix`,
  `'@types/bun'`, `yaml`). So version-drift gating has real reach on ~40% of the registry,
  not the near-zero reach the paragraph above implies — the feature is worth building, and
  the age fallback carries the other ~60% indefinitely.
- **Silent-wrong-answer hazard: stdlib targets can resolve to unrelated PyPI shims.**
  `importlib.metadata.version("asyncio")` returns **`4.0.0`** in this environment — an
  abandoned PyPI backport distribution, not stdlib `asyncio`, whose version has nothing to
  do with the API the record was proven against. A resolver keyed blindly on the target
  string binds stdlib targets to whatever squatted distribution happens to share the name,
  producing a version that never drifts (so the record never re-proves) and that is
  semantically meaningless. **The resolver must test
  `name.split(".")[0] in sys.stdlib_module_names` FIRST and return "no comparable version"
  for stdlib targets**, before ever calling `importlib.metadata.version()`. Stdlib targets
  therefore stay on the age-based path.
- **Where version resolution should live**: at each of the 3 seeded call sites (`cli/learning_tests.py:53` `cmd_check`, `learning_tests/release_gate.py:58` `run_release_gate`, `fsm/executor.py:1164` `_fresh_record`), the target string is already in scope at the `is_record_stale()` call, but `run_release_gate` and `_fresh_record` both loop over multiple records/targets per invocation — resolving version per-call-site would repeat the same `importlib.metadata.version()` lookup logic at 3+ sites. A resolver embedded in or immediately adjacent to `is_record_stale()` (taking `record.target` and returning the comparison internally) avoids duplicating that loop-body resolution across callers, versus requiring each of the 8 call sites to resolve and pass `installed_version` themselves.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py:45-63` — `is_record_stale()` widens per Program Design; new `resolve_target_version()` lands here or adjacent
- `scripts/little_loops/learning_tests/__init__.py:44-71` — `LearnTestRecord` dataclass gains `proven_package` and `proven_version` fields; `to_dict()`/`from_dict()` (lines 54-71) already round-trip optional keys via `.get()`, so this addition needs no forced migration script for existing `.ll/learning-tests/*.md` frontmatter
- `scripts/little_loops/init/install_check.py:23-34` — `installed_package_version()` gains a `pkg_name` parameter **with a `"little-loops"` default**

### Capture path (write side) — added by review pass, 2026-08-09

Absent from every prior pass; without these the reader-side change is inert (see §
Proposed Solution → Capture path).

- `scripts/little_loops/cli/learning_tests.py:59-98` — `cmd_prove()` stamps
  `proven_package`/`proven_version` onto the record via `update_frontmatter` between the
  `check_learning_test()` re-read (line 86) and `print_json()` (line 91). **This is the
  only mechanism the design may depend on for populating the fields.**
- `scripts/little_loops/cli/learning_tests.py` — new `backfill-versions` subcommand (see
  Acceptance Criteria AC-7) plus its `argparse` wiring
- `skills/explore-api/SKILL.md:208-226` — the on-disk frontmatter template; document the
  two new optional keys so the skill's emitted shape stays a truthful description of the
  format. Nothing may *rely* on the skill emitting them.
- `skills/explore-api/SKILL.md:286` — the acceptance checklist for the skill
- `.kimi-code/skills/explore-api/SKILL.md:208`, `.gemini/skills/explore-api/SKILL.md:208`
  — adapter-generated mirrors, **not hand-synced**. Confirmed by code trace and by
  reproducing the emitters locally: `GeminiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/gemini.py:80-108`) and `KimiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/kimi.py:57-82`) each derive their output by running
  `skills/explore-api/SKILL.md`'s content through
  `_select_frontmatter_fields()`/`_prepare_skill_content()`
  (`scripts/little_loops/adapters/core.py:117-180`) and unconditionally overwriting the
  mirror whenever the result differs (no hand-edit marker check, unlike
  `_emit_degraded_agent`'s marker guard in the same module) — invoked via
  `ll-adapt --host gemini --apply` / `ll-adapt --host kimi-code --apply`
  (`scripts/little_loops/cli/adapt.py`, `process_skills()` in `adapters/core.py:282-336`).
  Running both transforms locally against the current source reproduces both mirror files
  byte-for-byte, confirming they are current, source-derived output. **Implementation must
  edit only `skills/explore-api/SKILL.md:208-226` for the two new optional frontmatter
  keys and then regenerate both mirrors with `ll-adapt --host gemini --apply` and
  `ll-adapt --host kimi-code --apply`** — never hand-edit the two mirror files directly, a
  hand-edit is silently clobbered on the next adapt run.
- `docs/ARCHITECTURE.md:1538,1568` — states "record creation is owned by `/ll:explore-api`
  … skills emit the on-disk YAML directly"; needs a note that `cmd_prove` now enriches the
  record after the skill writes it

### Dependent Files (Callers/Importers) — is_record_stale()
Full call-graph sweep found 7 non-loop call sites plus one loop-embedded call site — 4 more than the issue's Known Costs list names:
- `scripts/little_loops/cli/learning_tests.py:53` — `cmd_check()`, gated on `--stale-aware`
- `scripts/little_loops/learning_tests/release_gate.py:58` — `run_release_gate()`, filters `list_records()` for the release gate
- `scripts/little_loops/fsm/executor.py:1164` — `_execute_learning_state()`'s `_fresh_record()` closure (not lines 1113/1161 as Known Costs states — confirmed anchor is 1152-1167)
- `scripts/little_loops/hooks/learning_tests_gate.py:134` — `gate()` (PreToolUse discoverability hook), not line 28/129 as Known Costs states — confirmed call is inside `gate()` at 91-150
- `scripts/little_loops/hooks/install_learning_gate.py:122` — `gate()` (PostToolUse install-nudge hook), confirmed inside `gate()` at 88-129
- `scripts/little_loops/cli/ctx_stats.py:680` — records-summary stale-bucket counter (not line 31 as Known Costs states)
- `scripts/little_loops/cli/history_context.py:74` — `_render_learning_test_section()`, computes `effective_status` for the `## Learning Test Evidence` table row
- `scripts/little_loops/loops/migrate-sdk-version.yaml:28-38` — a Python-heredoc inside the `list_stale` state imports and calls `is_record_stale()` directly; not in Known Costs' list at all, and not updatable via a Python signature change alone since it's FSM YAML, not a Python caller. Its local `_is_stale(r)` already ORs `r.status == "stale"` with `is_record_stale(...)`, so a manually `mark-stale`d record stays queued here regardless of version match — the same OR must hold at every other call site (AC-6). **Expected behavior change**: this loop's queue shrinks to version-drifted + manually-staled records. That is the intended win, not a regression, and should be stated in the loop's docs rather than discovered at runtime.

All 8 sites currently call with exactly `(record, stale_after_days)` — none pass version info today, consistent with the proposed optional third parameter.

### Dependent Files (Callers/Importers) — installed_package_version()

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py:691,804` — two zero-arg call sites (`installed_package_version() or ""`, adapter-write helpers). Generalizing the signature to `installed_package_version(pkg_name: str = "little-loops")` **must keep a default** or both of these break. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/init/cli.py:208` (`_warn_adapter_staleness`) — third zero-arg call site, same default-value requirement. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/__init__.py:40,74-75` — re-exports `LearnTestRecord` and `check_learning_test` in `__all__`; no signature dependency but confirms these are public package symbols. [Agent 1 finding]

### Age-based message construction (duplicates staleness logic)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/learning_tests_gate.py:124,137-138,156` — `gate()` independently recomputes `age = (today - record.date).days` to render `f'"{pkg}" (stale: {age} days old)'`, duplicating logic that will live inside `is_record_stale()`. A record that goes stale via version drift with a small/zero day-age will render a misleading `"(stale: N days old)"` hint unless this is updated to reflect the actual stale reason. [Agent 2 finding]

### Tests
- `scripts/tests/test_learning_tests_discoverability.py:454-498` — `TestIsRecordStale`, 6 tests constructing `LearnTestRecord` via its current 5-field constructor with no `proven_version` — a new field must stay optional/keyword-defaulted or all 6 break
- `scripts/tests/test_learning_tests_gate.py` — additional gate.py coverage
- `scripts/tests/test_release_gate.py`, `scripts/tests/test_install_learning_gate.py`, `scripts/tests/test_cli_learning_tests.py`, `scripts/tests/test_cli_ctx_stats.py`, `scripts/tests/test_history_context_cli.py`, `scripts/tests/test_learning_state.py` — one per caller above
- `scripts/tests/test_config.py::TestLearningTestsConfig` — config schema test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_tests.py` — `TestLearnTestRecord` class + `sample_record` fixture (lines 28-114+) is the dataclass-level home for `LearnTestRecord` serialization tests (`test_to_dict_basic_fields`, `test_from_dict_round_trip`, `test_from_dict_missing_raw_output_path`); natural anchor for new `proven_version` tests (default-None round trip, `to_dict` inclusion, `from_dict` backward-compat when the key is absent from pre-existing frontmatter — mirroring `test_from_dict_missing_raw_output_path`). [Agent 3 finding]
- No test exists for `installed_package_version()` in isolation — grep across `scripts/tests/` returns zero direct hits; `test_init_core.py`'s `detect_installation()` tests inline their own `importlib.metadata.version()` call rather than delegating to it. This is a genuine gap to fill when generalizing the function's signature. Follow the mocking convention in `scripts/tests/test_init_install.py` (`TestDetectInstallation`, `TestCheckVersion`): patch the module-qualified `little_loops.init.install_check.importlib.metadata.version`, using `PackageNotFoundError` as the not-installed side effect and a bare version string as `return_value`. [Agent 3 finding]
- `scripts/tests/test_init_core.py` — 11 `mock.patch("little_loops.init.install_check.installed_package_version", ...)` sites (lines 1242, 1256, 1314, 1323, 1334, 1339, 1353, 1371, 1391, 3112, 3129) patch the callable directly and are unaffected by an added default-valued parameter, but confirm the coverage extent for the `init/writers.py` and `init/cli.py` call sites that must keep working after the signature change. [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json` — `learning_tests` block (~line 1046+), `stale_after_days` property (~line 1060+)
- `scripts/little_loops/config/features.py:495-515` — `LearningTestsConfig` dataclass (`stale_after_days: int = 30`)

### Documentation
- `docs/reference/CONFIGURATION.md:893-905`
- `docs/ARCHITECTURE.md:690`
- `docs/guides/LEARNING_TESTS_GUIDE.md` — staleness/record-status section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6628-6653` — `## little_loops.learning_tests` → `#### LearnTestRecord` documents the exact field list (`target`, `date`, `status`, `assertions`, `raw_output_path`) with no `proven_version`, and the section's `.ll/learning-tests/<slug>.md` YAML frontmatter example (6644-6653) also needs a `proven_version:` line for consistency. `is_record_stale` itself has no API.md entry at all — only `run_learning_gate_for_issue` is documented (line 6666) — so widening its signature has no existing prose to update unless doc coverage is added as part of this work. [Agent 2 finding]
- `skills/configure/areas.md:976-1032`, `skills/configure/show-output.md:207-210`, `skills/configure/SKILL.md:122,155,310,399` — interactive `/ll:configure` wizard copy presents `stale_after_days` as the sole staleness lever (e.g. "How many days before a learning test record is considered stale?" with "7 (aggressive)"/"90 (relaxed)" options). Once staleness is OR'd with version-drift, a record can go stale before this threshold elapses — wizard copy becomes incomplete unless updated to mention version drift. `.kimi-code/skills/configure/SKILL.md` and `.gemini/skills/configure/SKILL.md` carry mirrored mentions but are adapter-generated copies, not hand-maintained sources — flagged for awareness only. [Agent 2 finding]

## Program Design

### Types

- `LearnTestRecord.proven_package: str | None` (new field) — the **resolved distribution
  name** the version belongs to
- `LearnTestRecord.proven_version: str | None` (new field) — the installed version of
  `proven_package` at prove time

Both are new, alongside existing `target`, `date`, `status`, `assertions`,
`raw_output_path`. **Two fields, not one.** `target` is free text and the package name is
derived from it by a `normalize_target()`-style `split()[0].lower()` heuristic; storing
only a version forces every reader to re-derive the name with the same heuristic, so a
change to that heuristic — or an edit to the record's `target` text — silently compares
the versions of two different distributions. Storing the resolved name makes the
comparison self-describing: compare only when `proven_package` still resolves to an
installed distribution, otherwise fall back to age.

- `learning_tests.version_aware_staleness: bool = True` (new config field on
  `LearningTestsConfig`) — escape hatch to restore pure age-based staleness
- `learning_tests.version_match_backstop_multiplier: int = 12` (new config field) — the
  Expected Behavior backstop; a version-matching record ages out at `stale_after_days *
  multiplier` (default 30 × 12 ≈ one year) instead of never

Naming these closes an open hole in § Known Costs, which budgets "config-schema.json
additions for any new config knobs" and whose Wiring Phase adds `/ll:configure` wizard
copy for them, without either one ever specifying a knob.

### Signatures

- `installed_package_version(pkg_name: str = "little-loops") -> str | None`
  (`init/install_check.py:23-34`, generalized — the default is mandatory, see Wiring Phase)
- `resolve_target_version(target: str) -> tuple[str, str] | None` (new, in
  `learning_tests/gate.py` or an adjacent module) — normalizes `target`, returns
  `(distribution_name, version)` or `None`. Returns `None` for stdlib targets (checked via
  `sys.stdlib_module_names` **before** any `importlib.metadata` call) and for
  `PackageNotFoundError`. Never raises.
- `is_record_stale(record: LearnTestRecord, stale_after_days: int, *, installed_version: str | None = None, version_aware: bool = True, backstop_multiplier: int = 12) -> bool`
  — `installed_version` stays an optional escape hatch for callers that have already
  resolved it (and for tests), but the default path is for `is_record_stale()` to call
  `resolve_target_version()` itself. Per the Codebase Research Findings on call-site
  shapes, `run_release_gate` and `_fresh_record` both loop over many records per
  invocation; requiring each of the 8 call sites to resolve and pass a version duplicates
  that loop-body logic 8 times.

### Call Path

`hooks/learning_tests_gate.py`, `hooks/install_learning_gate.py`, `fsm/executor.py`,
`cli/ctx_stats.py`, `cli/history_context.py`, `cli/learning_tests.py`,
`learning_tests/release_gate.py`, `loops/migrate-sdk-version.yaml` -> `is_record_stale()`
-> `resolve_target_version()` -> `installed_package_version(pkg_name)`

Write path (new): `/ll:explore-api` writes the record -> `cmd_prove`
(`cli/learning_tests.py:86-91`) re-reads it -> `resolve_target_version()` ->
`update_frontmatter` stamps `proven_package` / `proven_version`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Call-site invocation shapes (analyzer trace)**: all 3 seeded callers already load `stale_after_days` from config immediately before calling `is_record_stale()`, and none pass version info today (matches Integration Map's "none pass version info" finding). `cmd_check` (`cli/learning_tests.py:53`) and `run_release_gate` (`release_gate.py:58`) both call with `record` already resolved; `_fresh_record` (`fsm/executor.py:1152-1167`) resolves `rec = check_learning_test(target)` inline in a per-target loop (`for target in targets:`, line 1169) and is guarded by a broad `except Exception: pass` around its config load (lines 1130-1142) that silently falls back to a hardcoded `_lt_stale_days = 30` — the same silent-fallback shape should be considered for the new `installed_version` resolution so a resolver failure degrades to the existing age-based path rather than raising.
- **`PackageNotFoundError` is the resolver's primary failure mode, not an edge case**: since `LearnTestRecord.target` is free text (see Proposed Solution → Codebase Research Findings), most existing registry entries will not resolve via `importlib.metadata.version(target)`. The resolver's `except PackageNotFoundError: return None` path (mirroring `installed_package_version()`, `init/install_check.py:23-34`) is what routes these into Expected Behavior's "no version captured → age-based fallback," not a rare failure branch.

### Confirmed current schema and behavior

- `LearnTestRecord` (`scripts/little_loops/learning_tests/__init__.py:44-71`) is exactly
  `target: str, date: str, status: Literal["proven","refuted","stale"], assertions:
  list[Assertion], raw_output_path: str | None`. `to_dict()`/`from_dict()` (54-71) use
  `.get()` with defaults for everything except `target`/`date` — a new `proven_version`
  field added as `data.get("proven_version")` round-trips cleanly through existing
  `.ll/learning-tests/*.md` frontmatter with no forced migration step.
- `is_record_stale()` (`gate.py:45-63`) is a pure leaf function (no callees, confirmed by
  code-graph query and by reading the body): `threshold = max(1, stale_after_days)`;
  unparseable/missing `record.date` → returns `False` (treated as fresh, not an error);
  `age_days > threshold` otherwise.
- Corrected call path — 8 sites, not the 5 named in Known Costs (line numbers there are
  also imprecise; confirmed anchors below):
  `cli/learning_tests.py:53` (`cmd_check`, `--stale-aware` only) · `release_gate.py:58`
  (`run_release_gate`) · `fsm/executor.py:1152-1167` (`_fresh_record` closure inside
  `_execute_learning_state`) · `hooks/learning_tests_gate.py:91-150` (`gate()`, call at
  134) · `hooks/install_learning_gate.py:88-129` (`gate()`, call at 122) ·
  `cli/ctx_stats.py:660-684` (records-summary stale bucket) ·
  `cli/history_context.py:59-90` (`_render_learning_test_section`) ·
  `loops/migrate-sdk-version.yaml:35` (Python-heredoc in the `list_stale` state — an FSM
  YAML caller, not updatable by a Python signature change alone).
- All 8 currently call with exactly `(record, stale_after_days)`; none pass version info
  today, consistent with an optional third parameter.
- Existing coverage: `test_learning_tests_discoverability.py:454-498`
  (`TestIsRecordStale`, 6 tests) constructs `LearnTestRecord` via its current 5-field
  constructor with no `proven_version` — the new field must stay optional/keyword-defaulted
  or all 6 break.
- See § Proposed Solution → Codebase Research Findings: no deterministic version resolver
  currently exists in the codebase (not in `migrate-sdk-version.yaml`, which re-proves via
  LLM) — a per-package resolver (e.g. `importlib.metadata.version(pkg)`-based) is new work,
  not an extraction from FEAT-1813.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Give the generalized `installed_package_version(pkg_name: str)` a default of `"little-loops"` so the 3 existing zero-arg call sites (`init/writers.py:691,804`, `init/cli.py:208`) keep working unmodified
- Update `hooks/learning_tests_gate.py`'s `"(stale: N days old)"` hint construction (lines 124, 137-138, 156) so a record staled by version drift doesn't render a misleading age-only message
- Add `proven_version` to `docs/reference/API.md`'s `LearnTestRecord` field table and YAML example (lines 6628-6653)
- Update `skills/configure/areas.md` and `skills/configure/SKILL.md`'s `stale_after_days` wizard copy to mention version-drift gating alongside the age threshold
- Add direct test coverage for `installed_package_version()` (currently untested in isolation) following the `importlib.metadata.version` mocking convention in `test_init_install.py`
- Add `proven_version` field tests to `test_learning_tests.py::TestLearnTestRecord` (default-None round trip, `to_dict` inclusion, `from_dict` backward-compat)

### Wiring Phase addenda (added by review pass, 2026-08-09)

- Implement the capture path in `cmd_prove` and the `backfill-versions` subcommand — the
  reader-side change is a no-op without them (§ Proposed Solution → Capture path)
- Store `proven_package` alongside `proven_version`; do not re-derive the package name at
  read time (§ Program Design → Types)
- Guard the resolver with `sys.stdlib_module_names` before any `importlib.metadata` call —
  `asyncio` otherwise resolves to an unrelated PyPI shim (§ Proposed Solution → Measured
  correction)
- Name the two new config fields in `config-schema.json` and `config/features.py`
  (`version_aware_staleness`, `version_match_backstop_multiplier`); the pre-existing
  wizard-copy and docs bullets above are only actionable once these exist
- Update `scripts/little_loops/loops/migrate-sdk-version.yaml`'s state docs to note the
  intended queue-shrink
- Wrap resolver failures in the same silent-degradation shape as `_fresh_record`'s config
  load (`fsm/executor.py:1130-1142`): any resolver exception falls back to the age-based
  path rather than propagating

## Acceptance Criteria

_Added by review pass, 2026-08-09 — the issue previously had no AC section._

- **AC-1 (capture)**: after `ll-learning-tests prove <target>` succeeds for a resolvable
  pip target, that target's `.ll/learning-tests/<slug>.md` frontmatter contains
  `proven_package` and `proven_version` matching
  `importlib.metadata.version(proven_package)`. Verified by a test that mocks the
  `ll-loop` subprocess and the metadata lookup.
- **AC-2 (drift → stale)**: a record whose `proven_version` differs from the installed
  version of `proven_package` is reported stale **on the same day it was proven**
  (`age_days == 0`), by `is_record_stale()` and by every one of the 8 call sites.
- **AC-3 (match → not stale by age)**: a record whose `proven_version` matches the
  installed version is **not** stale at `age_days = stale_after_days + 1`, and **is**
  stale at `age_days > stale_after_days * version_match_backstop_multiplier`.
- **AC-4 (fallback unchanged)**: a record with no `proven_version` — i.e. every one of the
  33 records existing before this change — behaves exactly as today. The 6 existing tests
  in `test_learning_tests_discoverability.py::TestIsRecordStale` pass **unmodified**.
- **AC-5 (stdlib safety)**: `resolve_target_version("asyncio")` returns `None` even though
  `importlib.metadata.version("asyncio")` resolves to a PyPI shim in this environment.
  Covered for at least `asyncio`, `subprocess`, and `concurrent.futures`.
- **AC-6 (manual mark-stale wins)**: a record with `status == "stale"` (set by
  `ll-learning-tests mark-stale`) is never treated as fresh by a matching version, at any
  call site.
- **AC-7 (backfill)**: `ll-learning-tests backfill-versions` stamps `proven_package` /
  `proven_version` onto every existing record whose target resolves to a non-stdlib
  installed distribution, leaves all others untouched, is idempotent, and supports
  `--dry-run`. Running it against this repo's registry stamps ~13 of 33 records
  (14 resolvers minus `asyncio`, which AC-5 excludes).
- **AC-8 (message accuracy)**: `hooks/learning_tests_gate.py`'s nudge text does not render
  `"(stale: N days old)"` for a record staled by version drift; it names the version
  transition instead.
- **AC-9 (escape hatch)**: with `learning_tests.version_aware_staleness: false`,
  `is_record_stale()` is byte-for-byte equivalent in behavior to today's implementation
  for all inputs.
- **AC-10 (resolver never raises)**: `resolve_target_version()` returns `None` rather than
  propagating for a missing package, a malformed target, and an `importlib.metadata`
  internal error.
- **AC-11**: `python -m pytest scripts/tests/` exits 0; `ruff check scripts/` and
  `python -m mypy scripts/little_loops/` clean on changed files.

## Scope Boundaries

**Out of scope**: anything already shipped by ENH-3073 (per-row remediation text,
`cmd_prove` hardening) — this issue is additive on top of that, not a replacement.

## Impact

- **Priority**: P3 - Closes a known weak point in an existing gate (staleness proxy),
  not a regression or user-facing bug; deferred Option B from ENH-3073.
- **Effort**: Large - Signature change ripples through 8 call sites plus their tests
  (`TestIsRecordStale`, `TestLearningTestsConfig`, `test_install_learning_gate.py`), two
  new `LearnTestRecord` schema fields (backward-compatible via `.get()`), a new write path
  in `cmd_prove`, a new `backfill-versions` subcommand, two new config fields, and
  config-schema/docs/skill updates (see Known Costs and the Wiring Phase addenda).
  The review pass grew this beyond the original Known Costs estimate: the capture path and
  backfill were entirely absent from it.
- **Risk**: Medium - Touches a shared gate consumed by multiple hooks and CLIs; the
  fallback-to-age-based-staleness path for records without a captured version keeps
  existing behavior for those records, limiting blast radius.
- **Breaking Change**: No - `is_record_stale`'s new parameter is optional
  (`installed_version: str | None = None`), and records without a captured version keep
  today's age-based behavior.

## Related Issues

- ENH-3073 — made re-proving reachable (Option A); this issue is its deferred Option B
- FEAT-1813 — `migrate-sdk-version` loop; source of the version resolver this issue
  should build on
- ENH-2214 — introduced the release gate and `stale_after_days`

## Status

Open. Filed per ENH-3073's Acceptance Criteria requiring a follow-up ENH for Option B
before that issue closes.

Researched and reviewed: two `/ll:refine-issue` passes, one `/ll:wire-issue` pass, and a
2026-08-09 review pass that resolved the replace-vs-OR ambiguity in Expected Behavior,
added the missing capture path and backfill, split `proven_version` into
`proven_package` + `proven_version`, named the two config fields, added the stdlib
resolver guard, and added the Acceptance Criteria section. Scores raised from the
placeholder 40s accordingly.

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-08-09._

READINESS SCORE: 90/100 → PROCEED
OUTCOME CONFIDENCE: 62/100 → LOW

### Outcome Risk Factors
- **Breadth is 16+ distinct change sites** (`gate.py`, `LearnTestRecord`, `install_check.py`,
  `cli/learning_tests.py` (two features: `cmd_prove` stamping + new `backfill-versions`
  subcommand), 3 skill-template mirrors, 4+ docs files, config-schema.json,
  `config/features.py`, 8 `is_record_stale()` call sites, ~10 test files) — expect the
  implementation to spill across several sessions/commits rather than landing as one
  contained change.
- **`is_record_stale()`'s signature change fans out to 6-10 callers**, several of which
  (`hooks/learning_tests_gate.py`'s age-only message text, `migrate-sdk-version.yaml`'s
  existing `_is_stale(r)` OR-with-manual-stale logic) have caller-specific behavior that
  must be preserved individually rather than mechanically — each caller needs its own
  verification, not a single sweep.
- **Resolved 2026-08-09**: the skill-mirror ownership question is settled — both
  `.kimi-code/skills/explore-api/SKILL.md` and `.gemini/skills/explore-api/SKILL.md` are
  adapter-generated (`ll-adapt --host <gemini|kimi-code> --apply`), never hand-edited. See
  the updated Integration Map note. Implementation touches only
  `skills/explore-api/SKILL.md`, then regenerates both mirrors via `ll-adapt`.
- Mitigation: the issue's own Program Design and Wiring Phase sections already enumerate
  every call site and test file, and AC-1 through AC-11 give a concrete per-site
  verification target, which substantially de-risks the fanout despite its size.

## Session Log
- `/ll:confidence-check` - 2026-08-09T23:16:29 - `f96a5ae5-3aa8-4182-9112-8fe8af4976c7.jsonl`
- `/ll:wire-issue` - 2026-08-09T21:21:29 - `1928eea5-898a-4b0e-9f83-1704fa8dc30a.jsonl`
- `/ll:refine-issue` - 2026-08-09T20:43:47 - `e57311a1-9572-4b11-8e58-6e191d80f1ea.jsonl`
- `/ll:refine-issue` - 2026-08-09T20:27:31 - `fc23bfa7-fcc2-41bf-90ea-da56edaa284f.jsonl`
- `/ll:format-issue` - 2026-08-09T20:20:28 - `4e8af1cf-955c-4874-8514-ddcca515bcdb.jsonl`
