---
id: FEAT-1528
type: FEAT
priority: P5
status: done
parent: FEAT-1526
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-16T21:58:37Z
---

# FEAT-1528: Documentation and wiring integration for ll-adapt-agents-for-codex

## Summary

Update all documentation, configure-areas counts, and doc-assertion wiring tests
after `ll-adapt-agents-for-codex` ships (FEAT-1527). This child covers steps 5 and
8-11 of FEAT-1526. **Must merge after FEAT-1527.**

## Parent Issue

Decomposed from FEAT-1526: Adapt agents/*.md for Codex Subagents

## Use Case

A developer who has already run `ll-adapt-skills-for-codex --apply` wants to also adapt
their ll agents for Codex CLI. They look up `ll-adapt-agents-for-codex` in the CLI reference,
the Codex getting-started guide, and the HOST_COMPATIBILITY matrix to understand what it does
and how to invoke it — but none of those surfaces currently list the tool. After FEAT-1528 lands,
all documentation surfaces are updated and wiring tests enforce their presence, so the developer
can discover and use the feature without reading source code.

## Current Behavior

`ll-adapt-agents-for-codex` is fully implemented (FEAT-1527 shipped) but undocumented: it
appears in none of the Codex guides, HOST_COMPATIBILITY matrix, CLI reference, `commands/help.md`,
or `.claude/CLAUDE.md`. Wiring tests do not assert its presence. The `configure/areas.md`
authorize count (22) and README tool counts are stale.

## Expected Behavior

Every documentation surface listed in the Acceptance Criteria is updated to include
`ll-adapt-agents-for-codex`; six stale wiring-test assertions are corrected; the new
`TestFeat1526LlAdaptAgentsWiring` class covers all codex doc surfaces; the `areas.md` count
increments to 23 and README counts update atomically in the same commit.

## Acceptance Criteria

### Doc updates
- [ ] `docs/reference/HOST_COMPATIBILITY.md`: Codex `agent_select` cell → ✓ (or `(partial — model-spawned)`)
- [ ] `docs/codex/README.md`: rewrite `--agent` deferred entry to point at `ll-adapt-agents-for-codex`
- [ ] `docs/codex/usage.md`: add `ll-adapt-agents-for-codex --apply` under "Adapting Claude artifacts for Codex" (new section or "Current Limitations")
- [ ] `docs/reference/CLI.md`: add `### ll-adapt-agents-for-codex` section
- [ ] `commands/help.md`: one-line entry in CLI TOOLS block
- [ ] `.claude/CLAUDE.md` "CLI Tools" section: one-line entry for `ll-adapt-agents-for-codex`
- [ ] `skills/configure/areas.md`: increment authorize count (22 → 23) and append CLI name
- [ ] `README.md`: increment `"24 typed CLI tools"` → `"25 typed CLI tools"` (line ~46) and `"25 CLI tools"` → `"26 CLI tools"` (line ~166)
- [ ] `docs/codex/getting-started.md`: add `ll-adapt-agents-for-codex --apply` as companion step after `ll-adapt-skills-for-codex --apply` in "Skill and command discovery"
- [ ] `CONTRIBUTING.md` "Adding Agents" section: add post-creation adapter note referencing `ll-adapt-agents-for-codex --apply`

### Wiring test updates (must be atomic with doc changes above)
- [ ] `scripts/tests/test_create_extension_wiring.py`:
  - `TestConfigureAreasWiring.test_count_updated_to_17`: `"Authorize all 22"` → `"Authorize all 23"`
  - `TestFeat1229LlActionWiring.test_configure_areas_count_is_17`: same update
  - `TestFeat1045DocUpdates.test_readme_tool_count_is_20`: `"24 typed CLI tools"` → `"25 typed CLI tools"`
  - `TestFeat1229LlActionWiring.test_readme_tool_count_is_20`: same update
  - Add `TestFeat1526LlAdaptAgentsWiring` class — follow `TestFeat1486LlAdaptSkillsWiring` as model, checking `help.md`, `.claude/CLAUDE.md`, `CLI.md`, `areas.md`, and Codex docs for `ll-adapt-agents-for-codex`
- [ ] `scripts/tests/test_ll_logs_wiring.py`: `"Authorize all 22"` → `"Authorize all 23"`
- [ ] `scripts/tests/test_feat1504_doc_wiring.py`: `"Authorize all 22"` → `"Authorize all 23"`
- [ ] `pytest scripts/tests/test_create_extension_wiring.py scripts/tests/test_ll_logs_wiring.py scripts/tests/test_feat1504_doc_wiring.py` passes

## Implementation Steps

1. Update `skills/configure/areas.md` (22 → 23) and `README.md` counts **atomically** with wiring test updates below.
2. Update the 6 stale assertions across `test_create_extension_wiring.py`, `test_ll_logs_wiring.py`, and `test_feat1504_doc_wiring.py` in the same commit as step 1.
3. Add `TestFeat1526LlAdaptAgentsWiring` to `test_create_extension_wiring.py`.
4. Update `docs/reference/HOST_COMPATIBILITY.md`, `docs/codex/README.md`, `docs/codex/usage.md`, `docs/reference/CLI.md`, `commands/help.md`, `.claude/CLAUDE.md`.
5. Update `docs/codex/getting-started.md` and `CONTRIBUTING.md`.
6. Run full wiring test suite to verify all assertions pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `skills/init/SKILL.md` — add `"Bash(ll-adapt-agents-for-codex:*)"` to Step 10 permissions allow-list; add one-line entry in each of the two CLAUDE.md boilerplate blocks in Step 11 (follow the `ll-adapt-skills-for-codex` entry as the model)
8. Extend `TestFeat1526LlAdaptAgentsWiring` in `test_create_extension_wiring.py` — add 5 methods: `test_codex_readme_lists_tool`, `test_codex_getting_started_lists_tool`, `test_codex_usage_lists_tool`, `test_init_skill_has_permission`, `test_init_skill_has_boilerplate_entries`
9. Add parallel `ll-adapt-agents-for-codex` assertions to `test_enh1495_doc_wiring.py` — `TestCodexReadmeContent` and `TestCodexGettingStartedContent`; also verify `test_mentions_deferred_intents` still passes if codex/README.md is rewritten

## Files to Modify

- `skills/configure/areas.md`
- `README.md`
- `docs/reference/HOST_COMPATIBILITY.md`
- `docs/codex/README.md`
- `docs/codex/usage.md`
- `docs/reference/CLI.md`
- `commands/help.md`
- `.claude/CLAUDE.md`
- `docs/codex/getting-started.md`
- `CONTRIBUTING.md`
- `scripts/tests/test_create_extension_wiring.py`
- `scripts/tests/test_ll_logs_wiring.py`
- `scripts/tests/test_feat1504_doc_wiring.py`
- `skills/init/SKILL.md` — add `"Bash(ll-adapt-agents-for-codex:*)"` to Step 10 permissions allow-list; add `ll-adapt-agents-for-codex` to both CLAUDE.md boilerplate blocks in Step 11 (no test currently enforces this) [wiring pass]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1495_doc_wiring.py` — `TestCodexReadmeContent.test_mentions_skill_discovery` and `TestCodexGettingStartedContent.test_mentions_skill_discovery` assert only `ll-adapt-skills-for-codex` in codex docs; watch `TestCodexReadmeContent.test_mentions_deferred_intents` for breakage if codex/README.md rewrite removes "deferred" [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1526LlAdaptAgentsWiring` already exists (lines 300-321) but is missing coverage for codex doc surfaces; add methods: `test_codex_readme_lists_tool`, `test_codex_getting_started_lists_tool`, `test_codex_usage_lists_tool`, `test_init_skill_has_permission`, `test_init_skill_has_boilerplate_entries` — follow `TestFeat1486LlAdaptSkillsWiring` and `TestInitSkillWiring` (in `test_feat1504_doc_wiring.py`) as models [Agent 3 finding]
- `scripts/tests/test_enh1495_doc_wiring.py` — no assertions exist for `ll-adapt-agents-for-codex` in codex docs; add counterpart methods to `TestCodexReadmeContent` and `TestCodexGettingStartedContent` [Agent 3 finding]

## Impact

- **Priority**: P5 — Low-priority follow-up; purely doc/test hygiene after FEAT-1527.
- **Effort**: Small — Mechanical doc updates and test assertion changes; no logic changes.
- **Risk**: Low — No runtime behavior changed; only docs and wiring tests.
- **Breaking Change**: No

## Labels

`documentation`, `testing`, `codex`, `wiring`, `child-issue`

## Key Constraint

Areas.md count increment (22 → 23) and all 6 wiring-test assertion updates MUST land in the
same commit — otherwise the test suite fails between commits.

## Execution Order

Depends on FEAT-1527. Can be drafted in parallel once CLI interface is known, but merges after.

## Status

**Open** | Created: 2026-05-16 | Priority: P5 | Depends on: FEAT-1527 (done)

## Resolution

Implemented in a single pass. All documentation surfaces were already updated (FEAT-1527 predecessor committed them), so the work focused on:
- Added `"Bash(ll-adapt-agents-for-codex:*)"` and `"Bash(ll-adapt-skills-for-codex:*)"` to `skills/init/SKILL.md` permissions allow-list
- Added `ll-adapt-agents-for-codex` and `ll-adapt-skills-for-codex` entries to both CLAUDE.md boilerplate blocks in `skills/init/SKILL.md`
- Added 5 new test methods to `TestFeat1526LlAdaptAgentsWiring` (codex doc surfaces + init skill permission/boilerplate)
- Added `test_mentions_agents_tool` to `TestCodexReadmeContent` and `TestCodexGettingStartedContent` in `test_enh1495_doc_wiring.py`
- All 101 wiring tests pass

## Session Log
- `/ll:manage-issue` - 2026-05-16T21:58:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-16T21:55:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a1e46b4-19c0-4f24-88bd-04540704a7e8.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da2b182d-d2c8-4cd4-b53b-d6cec360dbf1.jsonl`
- `/ll:wire-issue` - 2026-05-16T21:49:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/688853eb-bacc-482c-8904-6ba0c2c431f0.jsonl`
- `/ll:refine-issue` - 2026-05-16T21:44:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a639e70b-ef80-4207-a3bb-ddab342a7bf5.jsonl`
- `/ll:refine-issue` - 2026-05-16T21:44:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a639e70b-ef80-4207-a3bb-ddab342a7bf5.jsonl`
- `/ll:issue-size-review` - 2026-05-16T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0de5eba4-6630-4b6f-ac14-f65397d900bb.jsonl`
