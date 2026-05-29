---
id: FEAT-1743
type: FEAT
priority: P3
status: done
captured_at: '2026-05-27T18:24:59Z'
completed_at: '2026-05-29T05:42:15Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
decision_needed: false
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1742
- FEAT-1738
- FEAT-1287
- FEAT-1286
- FEAT-749
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1743: Wire learning-tests as opt-in feature flag in `/ll:init` and `config-schema.json`

## Summary

Add a `learning_tests.enabled` master flag to `config-schema.json` and wire `/ll:init` to ask whether the project wants proof-first development at setup time. When enabled, init scaffolds `.ll/learning-tests/`, writes the config block to `.ll/ll-config.json`, and registers `ll-learning-tests` and `/ll:explore-api` in allowed-tools. This becomes the front-door opt-in that gates every other EPIC-1694 surface (FEAT-1742 discoverability nudge, `proof-first-task` wrapper, gate loops) so they stay silent for projects that don't want them.

## Current Behavior

- `config-schema.json:847-858` declares `learning_tests` with a single field (`stale_after_days`, default 30). No `enabled` master flag exists.
- `.ll/ll-config.json` in this project has no `learning_tests` block at all.
- `/ll:init` (`skills/init/SKILL.md`) does not mention the Learning Test Registry — no question, no scaffold, no allowed-tools wiring.
- A developer running `/ll:init` against a fresh project ends up with all the LT-registry primitives installed (CLI, skill, FSM state, loops) but no signal that the feature exists or how to turn it on.

Result: the EPIC-1694 surfaces are effectively dark by default. The discoverability hook (FEAT-1742) has no master switch to read; the gate loops have no way to know whether the project has opted in; and a new user has no onboarding moment to make a deliberate choice.

## Expected Behavior

### Init flow addition

```
$ /ll:init
...
? Enable learning-test registry for proof-first development?
  Learning tests let you prove third-party API behavior before writing
  integration code. A gate primitive can block implementation loops
  when assumptions are unproven.
  > Yes — I want proof-first development on this project
    No — skip (you can enable later with /ll:configure)
```

On **Yes**:

1. Adds `learning_tests: { enabled: true, stale_after_days: 30, discoverability: { mode: "warn" } }` to `.ll/ll-config.json`.
2. Creates `.ll/learning-tests/` directory with a `.gitkeep`.
3. Registers `ll-learning-tests` and `Skill(ll:explore-api)` in `.claude/settings.json` allowed-tools (same pattern as FEAT-749).
4. Prints a "next steps" hint: *"Run `/ll:explore-api <api-name>` to record your first proof, or run `proof-first-task` instead of `general-task` for any issue that touches a third-party API."*

On **No**: writes `learning_tests: { enabled: false }` to `.ll/ll-config.json` (explicit opt-out so future re-runs of init don't re-ask).

### Master-switch semantics

Every EPIC-1694 surface checks `learning_tests.enabled` before activating:

- FEAT-1742's discoverability hook: no-op when `enabled: false`.
- `proof-first-task`, `assumption-firewall`, `ready-to-implement-gate`, `integrate-sdk`, `adopt-third-party-api`: continue to run (don't break direct invocations) but log a one-line hint if `enabled: false` — *"learning-tests feature is disabled; run `/ll:configure` to enable."*
- `learning-tests-audit` (FEAT-1739): exits with `done_no_op` if `enabled: false`.

### Schema addition

```json
"learning_tests": {
  "type": "object",
  "description": "Learning test registry settings",
  "properties": {
    "enabled": {
      "type": "boolean",
      "description": "Master switch for the Learning Test Registry. When false, all LT-related surfaces (discoverability hook, gate-loop hints) are silenced. Set via /ll:init or /ll:configure.",
      "default": false
    },
    "stale_after_days": {
      "type": "integer",
      "default": 30,
      "minimum": 1
    },
    "discoverability": {
      "type": "object",
      "description": "Controls how learning-test gaps are surfaced during implementation. See FEAT-1742.",
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["off", "warn", "block"],
          "default": "warn"
        },
        "skip_packages": {
          "type": "array",
          "items": {"type": "string"},
          "default": ["std", "typing", "os", "sys"]
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

`enabled: false` as the default preserves backwards compatibility — existing projects that don't have the block opt-out implicitly.

## Motivation

- **Closes the onboarding gap.** Without an init prompt, the registry remains invisible infrastructure. A one-question moment at setup makes the feature a deliberate, informed choice.
- **Gives FEAT-1742 a master switch.** The discoverability hook needs a "is this project participating?" check. Without it, the hook either nags every project unconditionally (bad) or never fires (bad). `learning_tests.enabled` is that check.
- **Explicit opt-out is durable.** Writing `enabled: false` to config means a re-run of init won't re-prompt, and downstream surfaces have a deterministic answer rather than "unset means ambiguous."
- **Composes with `/ll:configure`.** Projects that skip at init time can flip the switch later via the existing configure flow — no new entry point needed beyond the schema.

## Use Case

Two developers run `/ll:init` on the same day:

- **Developer A** (greenfield SaaS app, lots of third-party API integration): says Yes. Their project gets `.ll/learning-tests/`, the discoverability hook will nudge them when they edit unfamiliar API code, and `proof-first-task` is wired into their allowed-tools so they can run it without a confirmation prompt.
- **Developer B** (internal data pipeline, no external APIs): says No. Their `.ll/ll-config.json` records the opt-out; the EPIC-1694 surfaces stay silent; their `/ll:init` re-runs don't re-prompt.

Six weeks later, Developer B starts integrating with Snowflake and changes their mind. They run `/ll:configure` and flip `learning_tests.enabled: true`; from that point forward, the gate surfaces activate.

## Proposed Solution

### Phase 1: Schema + config plumbing

1. Extend `config-schema.json:847-858` with the `enabled` and `discoverability` properties shown above.
2. Update `scripts/little_loops/config.py` (or wherever config defaults are loaded) so `learning_tests.enabled` defaults to `false` when the block is absent.
3. Add a helper `is_learning_tests_enabled(config) -> bool` in `scripts/little_loops/learning_tests/` for downstream callers.

### Phase 2: `/ll:init` flow

1. Add a question to `skills/init/SKILL.md` (the init skill) after the existing "configure documents" / "configure project type" steps.
2. Use `AskUserQuestion` with two options: Yes / No (default highlighted to "Yes" only if the project shows external-API signals — e.g., a `requirements.txt` referencing `stripe`, `anthropic`, `openai`, or `boto3`).
3. On Yes: write the config block, create `.ll/learning-tests/.gitkeep`, append `ll-learning-tests` and `Skill(ll:explore-api)` to `.claude/settings.json` allowed-tools.
4. On No: write `learning_tests: { enabled: false }` only.

### Phase 3: Wire the master switch into EPIC-1694 surfaces

1. Update FEAT-1742's discoverability handler to read `learning_tests.enabled` and short-circuit when `false`.
2. Update `learning-tests-audit` (FEAT-1739) loop YAML to add a first state that checks `learning_tests.enabled` and routes to `done_no_op` if false.
3. Update `proof-first-task`, `assumption-firewall`, and `ready-to-implement-gate` to log a one-line hint when invoked while the master switch is `false` (don't block — direct invocation should still work for users who know what they're doing).

### Phase 4: Documentation

1. Update `docs/guides/LEARNING_TESTS_GUIDE.md` with a "Getting Started" section pointing to `/ll:init` and the master switch.
2. Update `skills/init/SKILL.md` documentation to mention the new question.
3. Update `skills/configure/SKILL.md` to surface `learning_tests.enabled` as a togglable setting.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Config file restructured**: The config module is now `scripts/little_loops/config/features.py` (not a single `config.py`). `LearningTestsConfig` is at line 322, the `feature_enabled()` helper at line 13, and the `SyncConfig` pattern (`enabled: bool = False`) at line 427.
- **Schema constraint**: `config-schema.json:847-858` sets `"additionalProperties": false` — this must be removed or the new `enabled` and `discoverability` properties will be rejected against existing config files.
- **`feature_enabled()` already exists**: `scripts/little_loops/config/features.py:13-34` provides `feature_enabled(config_dict, "learning_tests.enabled")` that traverses raw dicts and returns `False` for missing keys. The new `is_learning_tests_enabled()` wrapper proposed in Phase 1 is a semantic convenience, not a new capability. Downstream callers that already have access to a raw config dict can use `feature_enabled()` directly; the `BRConfig` property path (`config.learning_tests.enabled`) is preferred for typed access.
- **Init skill structure**: `skills/init/interactive.md` has `TOTAL = 8` (line 15) and 8 mandatory rounds. Adding a learning_tests round means incrementing to `TOTAL = 9`. Round 4 (Product Analysis, lines 232-258) is the structural template to replicate.
- **Allowed-tools canonical list**: `skills/init/SKILL.md` Step 10 (lines 510-534) already includes `Bash(ll-learning-tests:*)` in its canonical list — no change needed there. It does NOT include `Skill(ll:explore-api)`, which the Yes path should append separately (not baked into the canonical list, since it's conditional on opt-in).
- **Learning tests module**: Currently `scripts/little_loops/learning_tests.py` is a single file, not a package. Creating `scripts/little_loops/learning_tests/__init__.py` will shadow the existing module. The existing code must be migrated into the package (rename `learning_tests.py` → `learning_tests/records.py` or similar) or the new helper should go in a different location.
- **Doc-wiring tests**: `scripts/tests/test_feat1756_init_wiring.py` and `scripts/tests/test_feat1757_configure_wiring.py` establish the pattern for asserting that skill docs contain expected round/section references — a similar test file should be created for this feature.
- **Serialization**: `BRConfig.to_dict()` at `core.py:572-573` only serializes `stale_after_days` — it needs to export `enabled` and `discoverability` when the fields are added.

## Integration Map

### Files to Modify
- `config-schema.json:847-858` — Extend `learning_tests` schema with `enabled` and `discoverability` properties; remove `"additionalProperties": false`
- `scripts/little_loops/config/features.py:322-332` — Extend `LearningTestsConfig` dataclass with `enabled: bool = False` and `DiscoverabilityConfig` sub-dataclass
- `scripts/little_loops/config/core.py:202-204` — `_parse_config()` wiring (already dispatches to `LearningTestsConfig.from_dict()`, no change needed if `from_dict` handles new fields)
- `scripts/little_loops/config/core.py:572-573` — `to_dict()` must export `enabled` and `discoverability` in addition to `stale_after_days`
- `skills/init/SKILL.md` — Add opt-in question, scaffold handlers, and Step 6 summary display entry
- `skills/init/interactive.md` — Add new round for learning_tests opt-in (following Round 4 Product Analysis pattern); increment `TOTAL` counter
- `skills/configure/SKILL.md` — Add `learning-tests` to argument-hint list and area mapping table
- `skills/configure/areas.md` — Add per-area handler for `learning_tests` section (enable/disable + sub-property config)
- `docs/guides/LEARNING_TESTS_GUIDE.md` — Add "Getting Started" section

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_config_schema.py:120-134` — extend `test_learning_tests_in_schema` with `enabled` and `discoverability` property assertions
- `skills/configure/show-output.md` — add `## learning_tests --show` section (following `## design_tokens --show` pattern at line 178)

### New Files
- `scripts/little_loops/learning_tests/__init__.py` — Package init with `is_learning_tests_enabled(config) -> bool` helper. NOTE: `scripts/little_loops/learning_tests.py` currently exists as a single-file module. Creating `learning_tests/` as a package will shadow it. Either migrate the existing code into the package (e.g., `learning_tests/records.py`) or place the helper elsewhere (e.g., `scripts/little_loops/config/features.py` alongside the existing `feature_enabled()`).
- `scripts/tests/test_init_learning_tests.py` — Tests for yes-path, no-path, re-prompt suppression, default-false
- `scripts/tests/test_feat1743_init_wiring.py` — Doc-wiring test asserting: init interactive.md has new round, TOTAL incremented, init SKILL.md references learning_tests, configure areas.md has learning-tests section (following `test_feat1756_init_wiring.py` and `test_feat1757_configure_wiring.py` patterns)

### Dependent Files (Callers/Importers)
- FEAT-1742 (discoverability hook) — Reads `learning_tests.enabled` and `discoverability.mode`
- FEAT-1739 (learning-tests-audit loop) — Checks `enabled` before running
- `scripts/little_loops/loops/assumption-firewall.yaml` — Gate loop; should log hint when `learning_tests.enabled: false`
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — Gate sub-loop; same hint pattern
- `scripts/little_loops/loops/integrate-sdk.yaml` — Integration loop; same hint pattern
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — Third-party API loop; same hint pattern
- `scripts/little_loops/config/core.py:202-204` — `BRConfig._parse_config()` loads `learning_tests` section via `LearningTestsConfig.from_dict()`
- `scripts/little_loops/config/core.py:572-573` — `BRConfig.to_dict()` serializes `learning_tests`; must export new fields
- `scripts/little_loops/config/__init__.py:47` — Re-exports `LearningTestsConfig` in public API

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/__init__.py:30,47,84` — docstring mentions `ll-learning-tests`; imports and re-exports `main_learning_tests` (if CLI registration surface changes)

### Similar Patterns
- FEAT-749 — Allowed-tools registration in init; this issue follows the same wiring pattern
- `skills/init/interactive.md:232-258` — Round 4 (Product Analysis) opt-in question; structurally identical Yes/No flow to replicate for learning_tests
- `config-schema.json:954-1014` — `sync` section with `"enabled": false` default; opt-in schema pattern to follow
- `scripts/little_loops/config/features.py:427-442` — `SyncConfig` dataclass with `enabled: bool = False`; exact `from_dict` pattern to replicate in `LearningTestsConfig`
- `scripts/little_loops/config/features.py:13-34` — `feature_enabled(config_data, dot_path)` helper already exists and works on raw dicts; the new `is_learning_tests_enabled()` can wrap it for semantic clarity
- `scripts/tests/test_feat1756_init_wiring.py` + `test_feat1757_configure_wiring.py` — doc-wiring test pattern to verify init/configure docs reference the new round/area

### Tests
- `scripts/tests/test_init_learning_tests.py` — New test file for init flow (yes/no paths, re-prompt suppression, default-false)
- `scripts/tests/test_feat1743_init_wiring.py` — New doc-wiring regression test (round presence, TOTAL counter, cross-references)
- `scripts/tests/test_config.py:2098-2128` — Extend `TestLearningTestsConfig` and `TestBRConfigLearningTestsIntegration` with `enabled` and `discoverability` field tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_config_schema.py:120-134` — extend `test_learning_tests_in_schema` with assertions for `enabled` and `discoverability` properties (following `test_design_tokens_in_schema` at line 136 as pattern)
- `scripts/tests/test_config.py:2113-2128` — add `test_learning_tests_round_trip_to_dict` to `TestBRConfigLearningTestsIntegration` (follows `test_design_tokens_round_trip_to_dict` at line 2190; no `to_dict` coverage exists for learning_tests today)

### Documentation
- `docs/guides/LEARNING_TESTS_GUIDE.md` — Add "Getting Started" section linking to init flow
- `docs/reference/CONFIGURATION.md:556-572` — Document new `learning_tests.enabled` and `learning_tests.discoverability` fields

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md:247` — update directory tree if `learning_tests.py` becomes `learning_tests/` package (the implementation may avoid this by placing the helper in `config/features.py` instead — confirm approach before touching this file)

### Configuration
- `.ll/ll-config.json` — `learning_tests` block written by init
- `.claude/settings.json` — allowed-tools registration for `ll-learning-tests` and `Skill(ll:explore-api)`

## Implementation Steps

1. **Schema**: Read `config-schema.json:847-858`. Add `enabled` (boolean, default `false`), `discoverability` sub-object with `mode` (enum `"off"|"warn"|"block"`, default `"warn"`) and `skip_packages` (array<string>). Follow `sync` section pattern at `config-schema.json:954-1014`. Remove `"additionalProperties": false` so new fields are accepted.
2. **Config dataclass**: In `scripts/little_loops/config/features.py:322-332`, add `enabled: bool = False` to `LearningTestsConfig` and a `DiscoverabilityConfig` sub-dataclass (model after `SyncConfig` at line 427). Update `from_dict()` to read both new fields.
3. **Serialization**: Update `BRConfig.to_dict()` at `scripts/little_loops/config/core.py:572-573` to export `enabled` and `discoverability` alongside `stale_after_days`.
4. **Feature flag helper**: Add `is_learning_tests_enabled(config) -> bool` — either as a standalone function wrapping the existing `feature_enabled()` at `features.py:13`, or placed directly in `config/features.py`. Returns `False` when block is absent or `enabled` is false.
5. **Init skill — interactive.md**: Add a new round for learning_tests opt-in, following the Round 4 (Product Analysis) pattern at `skills/init/interactive.md:232-258`. Use `AskUserQuestion` with Yes/No. Increment `TOTAL` counter at line 15. On Yes: track `LEARNING_TESTS_ENABLED=true`.
6. **Init skill — SKILL.md**: Add scaffold handlers in Step 8 (Write Configuration) following the conditional template deployment pattern at lines 327-341. On Yes: create `.ll/learning-tests/.gitkeep`, write `learning_tests: { enabled: true, ... }` to config. On No: write `learning_tests: { enabled: false }`. Add `[LEARNING TESTS]` section to Step 6 summary display (lines 142-214). In Step 10 (Allowed Tools, lines 510-534), conditionally append `Skill(ll:explore-api)` to the allow list when Yes was selected. Update Step 12 completion message.
7. **Configure skill**: Add `learning-tests` to the area mapping table and argument-hint list in `skills/configure/SKILL.md`. Add per-area handler in `skills/configure/areas.md` (following `allowed-tools` area pattern at line 780). Surface `enabled`, `stale_after_days`, and `discoverability.mode` as togglable.
8. **Downstream consumers** (Phase 3): Update `scripts/little_loops/loops/assumption-firewall.yaml`, `ready-to-implement-gate.yaml`, `integrate-sdk.yaml`, `adopt-third-party-api.yaml` to add an initial state checking `learning_tests.enabled` — route to hint log + continue (don't block). Wire FEAT-1742 discoverability hook and FEAT-1739 audit loop to consult the switch when those issues are implemented.
9. **Tests**: Create `scripts/tests/test_init_learning_tests.py` covering yes-path, no-path, re-prompt suppression, default-false. Extend `scripts/tests/test_config.py` `TestLearningTestsConfig` (line 2098) and `TestBRConfigLearningTestsIntegration` (line 2113) with new field tests. Create `scripts/tests/test_feat1743_init_wiring.py` for doc-wiring assertions (following `test_feat1756_init_wiring.py` pattern).
10. **Docs**: Update `docs/guides/LEARNING_TESTS_GUIDE.md` with Getting Started section; update `docs/reference/CONFIGURATION.md:556-572` to document new schema fields.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. **Schema test extension**: In `scripts/tests/test_config_schema.py:120-134`, extend `test_learning_tests_in_schema` to assert `enabled` (boolean) and `discoverability` (object with `mode` and `skip_packages`) exist in the schema properties. Follow the `test_design_tokens_in_schema` pattern at line 136.
12. **Round-trip serialization test**: Add `test_learning_tests_round_trip_to_dict` to `TestBRConfigLearningTestsIntegration` in `scripts/tests/test_config.py` (after line 2128). Follow `test_design_tokens_round_trip_to_dict` at line 2190 — write a config file, load `BRConfig`, call `to_dict()`, and assert `enabled` and `discoverability` keys are present with correct values.
13. **Configure show-output**: Add a `## learning_tests --show` section to `skills/configure/show-output.md`, following the `## design_tokens --show` pattern at line 178. Display `enabled`, `stale_after_days`, and `discoverability.mode`.
14. **CLI init registration**: Verify `scripts/little_loops/cli/__init__.py:30,47,84` — no changes needed unless the CLI entry-point signature changes, but confirm `ll-learning-tests` remains correctly registered after the feature flag is added.
15. **ARCHITECTURE.md**: If the implementation converts `learning_tests.py` into `learning_tests/` package, update `docs/ARCHITECTURE.md:247` directory tree. If the helper is placed in `config/features.py` instead (avoiding the shadowing problem), this step is not applicable.

## Acceptance Criteria

- `config-schema.json` includes `learning_tests.enabled: boolean` with `default: false` and `learning_tests.discoverability.mode: enum["off", "warn", "block"]` with `default: "warn"`.
- `/ll:init` asks one question about enabling the Learning Test Registry, with reasonable copy explaining the feature.
- On Yes: `.ll/ll-config.json` gets `learning_tests: { enabled: true, ... }`; `.ll/learning-tests/.gitkeep` exists; `.claude/settings.json` allowed-tools includes `ll-learning-tests` and `Skill(ll:explore-api)`.
- On No: `.ll/ll-config.json` gets `learning_tests: { enabled: false }` (explicit opt-out).
- Re-running `/ll:init` against a project with `enabled` already set (either value) does not re-prompt for this question.
- A new helper `is_learning_tests_enabled(config)` returns `False` when the block is missing or `enabled` is unset/false.
- Test file `scripts/tests/test_init_learning_tests.py` covers yes-path, no-path, re-prompt suppression, and default-false semantics.
- `LEARNING_TESTS_GUIDE.md` has a "Getting Started" section linking to the init flow.

## API/Interface

### Config Schema Extension

`config-schema.json` — `learning_tests` block extended with:

- `enabled` (`boolean`, default: `false`) — Master switch. When `false`, all LT-related surfaces are silenced.
- `discoverability.mode` (`enum: "off" | "warn" | "block"`, default: `"warn"`) — Controls how learning-test gaps are surfaced during implementation.
- `discoverability.skip_packages` (`array<string>`, default: `["std", "typing", "os", "sys"]`) — Packages excluded from discoverability checks.

### New Helper

```python
# scripts/little_loops/learning_tests/__init__.py
def is_learning_tests_enabled(config: dict) -> bool:
    """Return True if the learning-tests registry is opted-in via config."""
```

Returns `False` when the `learning_tests` block is absent or `enabled` is unset/false.

### Init Skill

`skills/init/SKILL.md` — One new `AskUserQuestion` prompt (Yes/No) offering learning-test registry opt-in during project setup.

## Dependencies

- **FEAT-1742** (discoverability hook) consumes `learning_tests.enabled` and `learning_tests.discoverability.mode` from this schema. Either issue can ship first, but FEAT-1742 should not be considered complete until this issue's schema is in place — otherwise the hook has no master switch.
- **FEAT-749** (allowed-tools registration in init) is the pattern this issue follows for the allowed-tools wiring step.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Impact

- **Priority**: P3 — Important onboarding/plumbing for the EPIC-1694 learning-tests ecosystem, but not blocking critical user-facing functionality. All existing projects are backward-compatible (implicit opt-out via absent config block).
- **Effort**: Medium — Touches config schema, config loader, init skill, configure skill, a new helper module, tests, and documentation across ~8 files.
- **Risk**: Low — New schema properties default to `false` (opt-out), preserving all existing behavior. No breaking changes to existing APIs or CLI contracts.
- **Breaking Change**: No

## Labels

`feat`, `init`, `config`, `learning-tests`, `feature-flag`, `onboarding`, `adoption`, `captured`

---

**Done** | Created: 2026-05-27 | Priority: P3

## Resolution

Implemented `learning_tests.enabled` master switch across config schema, dataclass, init skill, and configure skill.

### Changes Made
- **config-schema.json**: Added `enabled` (boolean, default false) and `discoverability` (object with `mode` and `skip_packages`) to `learning_tests` block
- **features.py**: Added `DiscoverabilityConfig` sub-dataclass and `enabled: bool = False` + `discoverability` fields to `LearningTestsConfig`
- **core.py**: Updated `to_dict()` to serialize `enabled` and `discoverability`
- **interactive.md**: Added Round 8 (Learning Tests opt-in), bumped TOTAL to 9, renumbered subsequent rounds
- **init/SKILL.md**: Added [LEARNING TESTS] summary, materialization handler (Step 8 item 7), conditional `Skill(ll:explore-api)` wiring (Step 10), completion message entries (Step 12), updated round count to 8–9
- **configure/SKILL.md**: Added `learning-tests` to argument-hint, area mapping, interactive pagination, --list output, arguments list
- **configure/areas.md**: Added `## Area: learning_tests` handler with enable/stale_days/discoverability config
- **configure/show-output.md**: Added `## learning_tests --show` section
- **test_config_schema.py**: Extended `test_learning_tests_in_schema` with enabled/discoverability assertions
- **test_config.py**: Added enabled/discoverability tests + round-trip to_dict test
- **test_feat1743_init_wiring.py**: New doc-wiring regression test (round, TOTAL, references, round count)
- **test_feat1743_configure_wiring.py**: New doc-wiring regression test (area mapping, args, areas, show-output)
- **test_feat1756_init_wiring.py**: Updated `TOTAL = 9` and `8–9 rounds` assertions for bumped round count

## Session Log
- `/ll:ready-issue` - 2026-05-29T05:26:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e745131-624d-49cb-98a7-3efb2d40ebc0.jsonl`
- `/ll:wire-issue` - 2026-05-29T05:21:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff8ff2f7-0c9f-4d20-9728-5e8161811fb0.jsonl`
- `/ll:refine-issue` - 2026-05-29T05:10:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b69922a-cfcc-4ebf-9ec9-2af756567dc9.jsonl`
- `/ll:format-issue` - 2026-05-29T02:45:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f33cbf4f-64fd-4485-8964-c58bfa3f4303.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:24:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d67c925-b04f-4086-8575-fc25fa08257e.jsonl`
- `/ll:confidence-check` - 2026-05-29T05:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c770381-3da1-4222-96c6-b14e2da38bfc.jsonl`
- `/ll:manage-issue feature implement FEAT-1743` - 2026-05-29T05:42:15Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73cb6551-c995-43ba-ab5d-f74023697a2e.jsonl`
