---
id: ENH-2209
title: Auto-populate `learning_tests_required` in refine-issue and wire-issue
type: enhancement
priority: P3
status: open
parent: EPIC-2207
depends_on: ENH-2208
relates_to: [ENH-2212]
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2209: Auto-populate `learning_tests_required` in refine-issue and wire-issue

## Summary

The `learning_tests_required: list[str]` frontmatter field must currently be declared manually by issue authors. The `assumption-firewall` loop already extracts external-API assumptions from issue text via LLM. That same extraction logic should run during `/ll:refine-issue` and `/ll:wire-issue` to auto-populate the field, making the gate self-provisioning.

## Current Behavior

`learning_tests_required` must be declared manually in issue frontmatter. The `assumption-firewall` loop already performs external-API assumption extraction but only as a standalone loop step — not during `/ll:refine-issue` or `/ll:wire-issue`. Issues commonly reach implementation without the field populated, causing the discoverability gate to be bypassed entirely.

## Expected Behavior

After `/ll:refine-issue` or `/ll:wire-issue` completes, `learning_tests_required` is automatically populated in the issue's frontmatter. The extraction step runs after the implementation plan section is written, invokes `ll-learning-tests check` for each found target, and writes the full list to frontmatter. Issues with no external dependencies omit the field (not set to `[]`).

## Motivation

Most issue authors don't know to add `learning_tests_required`. The field is only useful if it's populated before implementation begins. Refinement is the natural point to extract and persist assumptions — after the implementation plan is written but before the issue is marked ready.

## Implementation Steps

1. In the `/ll:refine-issue` skill (and `/ll:wire-issue`), after the implementation plan section is written, run an LLM extraction step: "List all external packages, SDKs, or third-party API surfaces that the plan assumes behavior of."
2. Deduplicate and slugify to match registry lookup keys.
3. For each extracted target, run `ll-learning-tests check "<target>"` to determine current registry status.
4. Write the full list to `learning_tests_required:` frontmatter (overwrite if already present).
5. Surface a summary: "Found N external dependencies — M proven, K unproven. Added to `learning_tests_required`."
6. If all are already proven, emit a brief confirmation and skip the field update if it was already correct.

## Success Metrics

- After `/ll:refine-issue` on an issue that mentions `anthropic`, `requests`, or any third-party package, `learning_tests_required` is populated in frontmatter
- Running `/ll:ready-issue` immediately after shows the correct gate status for each entry
- Issues with no external dependencies have `learning_tests_required` omitted (not set to `[]`)

## Scope Boundaries

- **In scope**: Auto-extraction of external API assumptions from implementation plan text in `refine-issue` and `wire-issue`; writing results to `learning_tests_required` frontmatter; surfacing a summary of proven/unproven entries per issue
- **Out of scope**: Creating new learning test records (owned by `/ll:explore-api`); modifying the `assumption-firewall` loop; retroactive population of existing issues; changes to `ll-learning-tests` CLI internals

## Impact

- **Priority**: P3 — Parent EPIC-2207 is not time-sensitive; improves gate reliability without blocking current workflows
- **Effort**: Small — Adds a post-step to two existing skills; extraction logic modeled directly on the assumption-firewall loop
- **Risk**: Low — Additive frontmatter write only; existing issues and skills are unaffected
- **Breaking Change**: No

## Labels

`enhancement`, `workflow`, `learning-tests`, `refine-issue`, `wire-issue`

## Status

**Open** | Created: 2026-06-18 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2208 (stale-aware gate). The implementation should call the stale-aware gate function from `learning_tests_gate.py` (added by ENH-2208) rather than querying `ll-learning-tests check` directly. Calling the raw CLI bypasses the stale-age check, causing the proven/unproven summary to disagree with runtime gate behavior. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2212 (install hook) both produce a proven/unproven summary message for the same logical situation. Without a shared format, users see inconsistent phrasing depending on whether they encounter an unproven package via refine-issue or a `pip install`. The message format (nudge text, proven count, unproven count) must be defined once in the shared gate utility (`scripts/little_loops/learning_tests/gate.py`) and used by both issues. See [[ENH-2212]].

**Note** (added by `/ll:audit-issue-conflicts`): Implementation step 4 ("Write the full list to `learning_tests_required:` frontmatter (overwrite if already present)") must be changed to a union-merge. If `learning_tests_required` already exists in the issue frontmatter (e.g., populated by `/ll:scope-epic` per ENH-2220), the newly extracted targets must be merged into the existing list rather than overwriting it. A re-run of refine-issue on a scoped issue would otherwise silently narrow the package list, dropping targets the scope-epic pass identified. Use set-union semantics: new targets are appended; existing targets are preserved. See [[ENH-2220]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2210's sprint pre-flight includes a fallback that "imports the shared extraction utility from ENH-2209." For this to be importable, ENH-2209 must deliver a Python helper at `scripts/little_loops/learning_tests/extractor.py` exposing `extract_learning_targets(issue_text: str) -> list[str]`. This function wraps the LLM extraction step (or shells out to the assumption-firewall loop) and is what ENH-2210's fallback imports. Without it, ENH-2210's fallback is architecturally unimplementable — the extraction step lives inside a skill prompt, not in a callable Python module. See [[ENH-2210]].

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:29 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:46 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T18:17:31 - `e95db64d-70ee-4f7f-87aa-5e8414c2d4c9.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
