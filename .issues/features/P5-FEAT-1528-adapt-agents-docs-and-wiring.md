---
id: FEAT-1528
type: FEAT
priority: P5
status: closed
parent: FEAT-1526
---

# FEAT-1528: Documentation and wiring integration for ll-adapt-agents-for-codex

## Summary

Update all documentation, configure-areas counts, and doc-assertion wiring tests
after `ll-adapt-agents-for-codex` ships (FEAT-1527). This child covers steps 5 and
8-11 of FEAT-1526. **Must merge after FEAT-1527.**

## Parent Issue

Decomposed from FEAT-1526: Adapt agents/*.md for Codex Subagents

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

## Key Constraint

Areas.md count increment (22 → 23) and all 6 wiring-test assertion updates MUST land in the
same commit — otherwise the test suite fails between commits.

## Execution Order

Depends on FEAT-1527. Can be drafted in parallel once CLI interface is known, but merges after.

## Session Log
- `/ll:issue-size-review` - 2026-05-16T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0de5eba4-6630-4b6f-ac14-f65397d900bb.jsonl`
