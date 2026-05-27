---
id: FEAT-1743
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T18:24:59Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1742
- FEAT-1738
- FEAT-1287
- FEAT-1286
- FEAT-749
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

## Implementation Steps

1. Read `config-schema.json:847-858` and the current `/ll:init` skill (`skills/init/SKILL.md`).
2. Extend `learning_tests` schema with `enabled`, `discoverability.mode`, `discoverability.skip_packages`.
3. Add config loader helper for the master switch.
4. Add the init question + Yes/No handlers; gate the scaffold steps on Yes.
5. Add allowed-tools wiring for `ll-learning-tests` and `Skill(ll:explore-api)` (model after FEAT-749 implementation).
6. Update FEAT-1742 (when implemented) and FEAT-1739 to consult the switch; add the soft hint to direct-invocation paths in `proof-first-task` / `assumption-firewall` / `ready-to-implement-gate`.
7. Add tests in `scripts/tests/test_init_learning_tests.py` covering: yes-path scaffolds config + dir + allowed-tools; no-path writes explicit opt-out; re-running init does not re-prompt; switch defaults to false when block is absent.
8. Update `LEARNING_TESTS_GUIDE.md` and `init` / `configure` skill docs.

## Acceptance Criteria

- `config-schema.json` includes `learning_tests.enabled: boolean` with `default: false` and `learning_tests.discoverability.mode: enum["off", "warn", "block"]` with `default: "warn"`.
- `/ll:init` asks one question about enabling the Learning Test Registry, with reasonable copy explaining the feature.
- On Yes: `.ll/ll-config.json` gets `learning_tests: { enabled: true, ... }`; `.ll/learning-tests/.gitkeep` exists; `.claude/settings.json` allowed-tools includes `ll-learning-tests` and `Skill(ll:explore-api)`.
- On No: `.ll/ll-config.json` gets `learning_tests: { enabled: false }` (explicit opt-out).
- Re-running `/ll:init` against a project with `enabled` already set (either value) does not re-prompt for this question.
- A new helper `is_learning_tests_enabled(config)` returns `False` when the block is missing or `enabled` is unset/false.
- Test file `scripts/tests/test_init_learning_tests.py` covers yes-path, no-path, re-prompt suppression, and default-false semantics.
- `LEARNING_TESTS_GUIDE.md` has a "Getting Started" section linking to the init flow.

## Dependencies

- **FEAT-1742** (discoverability hook) consumes `learning_tests.enabled` and `learning_tests.discoverability.mode` from this schema. Either issue can ship first, but FEAT-1742 should not be considered complete until this issue's schema is in place — otherwise the hook has no master switch.
- **FEAT-749** (allowed-tools registration in init) is the pattern this issue follows for the allowed-tools wiring step.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `init`, `config`, `learning-tests`, `feature-flag`, `onboarding`, `adoption`, `captured`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-27T18:24:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d67c925-b04f-4086-8575-fc25fa08257e.jsonl`
