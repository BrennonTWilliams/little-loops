---
id: ENH-1143
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1140
related: [ENH-1138, ENH-1134, ENH-1141, ENH-1142]
size: Medium
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1143: 429 Resilience — Circuit Breaker Skills & API.md Wiring Updates

## Summary

Update skills and API reference docs to expose `rate_limits` config to users: (1) add `rate_limits: RateLimitsConfig` to `docs/reference/API.md` CommandsConfig description, (2) add `rate_limits` display block to `skills/configure/show-output.md`, (3) add `rate_limits` question round to `skills/configure/areas.md` interactive flow, (4) optionally add `circuit_breaker_enabled`/`circuit_breaker_path` to `skills/create-loop/reference.md` and `loop-types.md`.

## Parent Issue

Decomposed from ENH-1140: 429 Resilience — Prose Doc Updates (Loops Guide, Config, Architecture)

## Expected Behavior

### 1. `docs/reference/API.md:100` — CommandsConfig attribute

Add `rate_limits: RateLimitsConfig` to the `CommandsConfig` attribute description alongside `confidence_gate`, `tdd_mode`, `max_refine_count`.

### 2. `skills/configure/show-output.md:68-83` — `commands --show` output

Add `rate_limits` display block (all 4 keys with defaults) to the `/ll:configure commands --show` output template so users can see circuit-breaker settings.

### 3. `skills/configure/areas.md:308-403` — interactive configure flow

Add a `rate_limits` question round to the interactive `commands` configure flow, exposing at minimum `circuit_breaker_enabled` and `circuit_breaker_path` as configurable knobs.

### 4. `skills/create-loop/reference.md:939-968` and `loop-types.md:791-795` — rate-limit fields (optional)

Add `circuit_breaker_enabled` and `circuit_breaker_path` to the rate-limit fields prose and YAML examples. Currently only `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` are documented; the two circuit-breaker keys are invisible to loop authors.

## Integration Map

### Files to Modify

- `docs/reference/API.md` — `CommandsConfig` attribute list (~line 100)
- `skills/configure/show-output.md` — `commands --show` output template (~lines 68-83)
- `skills/configure/areas.md` — interactive commands configure flow (~lines 308-403)
- `skills/create-loop/reference.md` — rate-limit fields section (~lines 939-968) [optional]
- `skills/create-loop/loop-types.md` — rate-limit YAML example (~lines 791-795) [optional]

### Codebase Research Findings

- **Full RateLimitsConfig schema**: `scripts/little_loops/config/automation.py:112-146` — 4 keys with exact defaults:
  - `max_wait_seconds: int = 21600`
  - `long_wait_ladder: list[int] = [300, 900, 1800, 3600]`
  - `circuit_breaker_enabled: bool = True`
  - `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`
- **Config nesting**: serialized under `commands.rate_limits` at `config/core.py:411-415`; `CommandsConfig` declares `rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)` at `automation.py:158`
- **API.md gap**: `CommandsConfig` row at `API.md:100` uses inline-parenthetical style — description reads `Command customization (includes \`confidence_gate: ConfidenceGateConfig\`, \`tdd_mode: bool\`)`. Extend the parenthetical (do NOT add a sub-table — API.md convention keeps sub-types inline)
- **show-output.md gap**: `/ll:configure commands --show` template at lines 68-83 lists `pre_implement`, `post_implement`, `confidence_gate` (nested block), `tdd_mode`, `max_refine_count` — no `rate_limits`. Mirror the `confidence_gate:` nested-block pattern (parent key unindented, 4-space indent for children, column-aligned `(default: ...)` inline)
- **areas.md gap**: interactive commands flow at lines 308-403 — Current Values block (311-323) + Round 1 (325-374, 4 questions) + Round 2 (376-403, 2 questions: TDD bool + Max refines int-choice). No `rate_limits` questions. Boolean prompt pattern uses exactly 3 options: `"{{current <key>}} (keep)"`, `"true"`, `"false"`
- **create-loop gaps**: `reference.md:939-968` documents 5 rate-limit keys but omits `circuit_breaker_enabled` and `circuit_breaker_path`. Existing prose cites defaults as "Defaults from `commands.rate_limits.<key>`". `loop-types.md:791-795` YAML uses inline comments `# optional: <explanation> (default from commands.rate_limits.<key>, <human value>)`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — new test file needed, follow pattern in `scripts/tests/test_create_extension_wiring.py`; assert `"rate_limits: RateLimitsConfig"` in `API.md`, `"circuit_breaker_enabled"` and `"circuit_breaker_path"` in `show-output.md`, `areas.md`, `reference.md`, and `loop-types.md` [Agent 3 finding]
- `scripts/tests/test_create_extension_wiring.py:56-58` — existing test reads `areas.md` and asserts `"Authorize all 14"` is present; new `areas.md` content must not disturb this string (constraint, not to update) [Agent 2 finding]

### Patterns to Follow

- **API.md CommandsConfig row** (`docs/reference/API.md:100`): extend existing parenthetical → `(includes \`confidence_gate: ConfidenceGateConfig\`, \`tdd_mode: bool\`, \`rate_limits: RateLimitsConfig\`)`
- **show-output.md `rate_limits:` block** — mirror `confidence_gate:` structure at lines 73-76:
  ```
    rate_limits:
      max_wait_seconds:        {{config.commands.rate_limits.max_wait_seconds}}        (default: 21600)
      long_wait_ladder:        {{config.commands.rate_limits.long_wait_ladder}}        (default: [300, 900, 1800, 3600])
      circuit_breaker_enabled: {{config.commands.rate_limits.circuit_breaker_enabled}} (default: true)
      circuit_breaker_path:    {{config.commands.rate_limits.circuit_breaker_path}}    (default: .loops/tmp/rate-limit-circuit.json)
  ```
- **areas.md bool-prompt template** (mirrors `tdd_mode` at lines 376-388):
  ```yaml
  - header: "Circuit breaker"
    question: "Enable cross-worktree rate-limit circuit breaker?"
    options:
      - label: "{{current circuit_breaker_enabled}} (keep)"
      - label: "true"
        description: "Yes, coordinate rate-limit state across worktrees (default)"
      - label: "false"
        description: "No, disable circuit breaker"
    multiSelect: false
  ```
- **areas.md Current Values block** — add `rate_limits:` nested block after `max_refine_count` (line 322) mirroring the `confidence_gate:` nesting pattern

### Tests

- All existing tests are unaffected by these prose-only skill changes
- **ENH-1141 test file does NOT yet exist** — no `test_enh1138*`, `test_enh1141*`, or `test_*doc_wiring*` found in `scripts/tests/`. When ENH-1141 lands, it will likely assert substrings added by this issue
- **Test template**: `scripts/tests/test_create_extension_wiring.py` is the canonical pattern — one `class Test<Concept>Wiring` per target file, one `content = FILE.read_text(); assert "<substring>" in content` per required change, no fixtures or mocks

## Implementation Steps

1. **Update `docs/reference/API.md:100`** — add `rate_limits: RateLimitsConfig` to the `CommandsConfig` attribute list
2. **Update `skills/configure/show-output.md:68-83`** — add `rate_limits` display block showing all 4 keys with their defaults
3. **Update `skills/configure/areas.md:308-403`** — add a `rate_limits` question round after the existing Round 2, exposing `circuit_breaker_enabled` (bool prompt) and `circuit_breaker_path` (string prompt)
4. _(Optional)_ **Update `skills/create-loop/reference.md:939-968`** — add `circuit_breaker_enabled: bool` and `circuit_breaker_path: str` to the rate-limit fields documentation
5. _(Optional)_ **Update `skills/create-loop/loop-types.md:791-795`** — add `circuit_breaker_enabled` and `circuit_breaker_path` to the rate-limit YAML example

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Create `scripts/tests/test_circuit_breaker_doc_wiring.py` — one `class TestXxxWiring` per target file, using `Path.read_text()` + `assert "<substring>" in content` (zero fixtures, zero mocks); assert all strings added by steps 1–5 are present in the modified files; follow `test_create_extension_wiring.py` exactly

## Acceptance Criteria

- `docs/reference/API.md` `CommandsConfig` lists `rate_limits: RateLimitsConfig`
- `/ll:configure commands --show` output template includes the `rate_limits` block
- Interactive `commands` configure flow allows setting `circuit_breaker_enabled` and `circuit_breaker_path`

## Session Log
- `/ll:ready-issue` - 2026-04-17T06:43:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9253dba-044a-4492-bd2a-c8135b63d643.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d263f7b-fc36-4cab-8a74-a78825b49d65.jsonl`
- `/ll:wire-issue` - 2026-04-17T06:40:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05017e96-f5f9-48c7-8516-44ca084f620b.jsonl`
- `/ll:refine-issue` - 2026-04-17T06:36:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8cd9c76-1934-4bbf-95dc-7b9f55681882.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e20512e-4152-4cfc-9884-2846f71c2341.jsonl`

---

## Status
- [x] Completed

## Resolution

Implemented 2026-04-17. Surfaced `rate_limits` config block in all user-facing
documentation and skills so users can discover and configure cross-worktree
circuit-breaker knobs added by ENH-1134.

**Files modified:**
- `docs/reference/API.md` — extended `CommandsConfig` row parenthetical with `rate_limits: RateLimitsConfig`
- `skills/configure/show-output.md` — added `rate_limits` nested block (4 keys + defaults) to `commands --show` template
- `skills/configure/areas.md` — added `rate_limits` to Current Values block; added Round 3 with 2 questions (circuit breaker enable, circuit path)
- `skills/create-loop/reference.md` — documented `circuit_breaker_enabled` and `circuit_breaker_path` in rate-limit fields section
- `skills/create-loop/loop-types.md` — added circuit-breaker YAML lines to the rate-limit example
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — 9 wiring assertions across 5 target files

**Verification:** 4912 tests pass, ruff clean. Pre-existing mypy `wcwidth` import-stub warning unrelated to this change.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T06:47:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/459c2294-9b6d-47c2-9f97-328232145283.jsonl`
- `/ll:manage-issue` - 2026-04-17T00:00:00Z - implementation
