---
id: ENH-1497
type: ENH
priority: P4
status: open
captured_at: "2026-05-16T13:04:12Z"
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
relates_to: [FEAT-1486, FEAT-1493, BUG-1494]
labels: [captured, codex, skills-api, parity]
---

# ENH-1497: Audit `disable-model-invocation: true` skills for Codex exposure

## Summary

16 skills carry `disable-model-invocation: true` in their SKILL.md frontmatter and are deliberately skipped by `ll-adapt-skills-for-codex`. Some of these (e.g. `cleanup-loops`, `debug-loop-run`) are genuinely user-only and should remain hidden from model invocation. Others may have been flagged conservatively and could safely be exposed in Codex. Audit each, decide per-skill, and either remove the flag or document why exclusion is correct.

## Current Behavior

`ll-adapt-skills-for-codex` skips any SKILL.md with `disable-model-invocation: true`. Per the Codex audit, the skipped skills include:

`update-docs`, `update`, `cleanup-loops`, `debug-loop-run`, `audit-issue-conflicts`, `workflow-automation-proposer`, `review-loop`, `audit-claude-config`, `rename-loop`, `improve-claude-md`, plus ~6 more.

A Codex user has no way to discover these. From Claude Code, the same flag means "don't auto-invoke" but the slash command still works — different semantics that don't translate cleanly to Codex's Skills API.

## Expected Behavior

A documented decision exists per skill: either
- The flag is removed (skill is exposed in Codex), or
- A comment / convention captures *why* the skill is intentionally user-only (and the adapter's skip behavior is the correct outcome)

Optionally: introduce a separate Codex-specific opt-in mechanism (e.g. `codex-expose: true` even when `disable-model-invocation: true`) for skills that should be discoverable from Codex but not auto-invoked by the Claude Code model.

## Motivation

`disable-model-invocation: true` was originally a Claude Code concept — it prevents the model from auto-firing a skill while leaving slash-command access intact. The flag was extended to act as the Codex adapter's skip signal, conflating two distinct semantics:

1. "Don't auto-invoke from the model" (Claude Code)
2. "Don't expose to Codex at all" (current adapter behavior)

For some skills (1) is correct but (2) is overly restrictive. A Codex user invoking `/ll:rename-loop` explicitly is not auto-invocation; the skill should arguably be available.

## Proposed Solution

1. Inventory all 16 skills with the flag and triage each into one of three buckets:
   - **Keep skipped** — genuinely never useful from Codex (e.g. `update`, which mutates the plugin install)
   - **Expose** — remove the `disable-model-invocation: true` flag; the original Claude Code reason no longer holds or never did
   - **Expose with caveat** — introduce a sibling flag for "Codex-discoverable but not Claude-Code auto-invokable"
2. Document the decision in a short table in `HOST_COMPATIBILITY.md` or `docs/codex/README.md` (once ENH-1495 lands)
3. Update `ll-adapt-skills-for-codex` if a new flag is introduced

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` (a subset of the 16) — flag adjustments per the audit decisions
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — adjust skip logic if a new flag is introduced
- `docs/reference/HOST_COMPATIBILITY.md` or `docs/codex/README.md` — document the per-skill decisions

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py` — assert each documented decision is honored

## Implementation Steps

1. List all 16 skills with `disable-model-invocation: true` and the rationale for each (read SKILL.md headers)
2. Decide per-skill: keep / expose / expose-with-new-flag
3. Apply frontmatter changes
4. Update adapter if a new flag is introduced
5. Document the rationale table in user-facing docs
6. Re-run `ll-adapt-skills-for-codex` and verify Codex discovers the newly exposed skills

## Impact

- **Priority**: P4 — Quality-of-life parity item; not blocking
- **Effort**: Small/Medium — mostly per-skill decisions and frontmatter edits
- **Risk**: Low — Behavior changes are opt-in per skill
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` | Documents `ll-adapt-skills-for-codex` and the `disable-model-invocation` skip rule |
| `docs/reference/HOST_COMPATIBILITY.md` | Where the per-skill decision matrix should live |


## Blocks

- FEAT-1493
- BUG-1494

## Labels

`enh`, `captured`, `codex`, `skills-api`, `parity`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
