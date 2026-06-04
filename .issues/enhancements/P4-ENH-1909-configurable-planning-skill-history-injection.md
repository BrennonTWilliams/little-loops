---
id: ENH-1909
title: Make planning-skill history injection configurable via history.planning_skills
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: '2026-06-03T00:00:00Z'
discovered_by: review
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1905
labels:
- history-db
- configurability
---

# ENH-1909: Make planning-skill history injection configurable via history.planning_skills

## Summary

ENH-1905 hardwires history context into exactly four planning skills
(`create-sprint`, `scope-epic`, `manage-issue`, `review-epic`). There is no
way for a user to opt a skill in or out without modifying the skill file itself.
A `history.planning_skills` config key would let users control this set from
`ll-config.json`, enabling or disabling history reads per-skill without code
changes.

## Current Behavior

After ENH-1905 ships, four skills always invoke `ll-history-context --effort`.
A user who wants to disable history reads for one skill (e.g. `manage-issue`
for a project with no completed issues yet) must edit the skill's SKILL.md
directly.

## Expected Behavior

- `ll-config.json` accepts a `history.planning_skills` key (list of skill
  names, default `["create-sprint", "scope-epic", "manage-issue",
  "review-epic"]`).
- Each planning skill checks whether its own name appears in this list before
  invoking the history guard. If absent, it skips the read silently.
- An empty list (`[]`) disables history reads for all planning skills.
- Skills not in the default list can be opted in by adding them.

## Motivation

As ENH-1905 notes, the wiring is across a broad file surface. Making the
target set configurable avoids the need for users to re-edit multiple SKILL.md
files when their workflow changes (e.g. a new project with no history yet
wanting to suppress noisy "no data" paths, or a user wanting to add
`review-sprint` to the set later).

This is the natural extension of the `history.effort_fields` configurability
pattern established in ENH-1905 — same namespace, same read-from-config-or-
fallback-to-default contract.

## Success Metrics

- `history.planning_skills: []` in `ll-config.json` causes all four planning
  skills to skip the effort read (verified by test asserting no
  `ll-history-context` invocation when config is empty list).
- Adding a fifth skill name to `history.planning_skills` causes that skill to
  invoke the guard (verified by doc-wiring test extension).
- When the config key is absent, behavior is identical to ENH-1905 defaults
  (all four skills active).

## Proposed Solution

1. Add `history.planning_skills` (list[str]) to `config-schema.json` with
   default `["create-sprint", "scope-epic", "manage-issue", "review-epic"]`.
2. Add a `--for-skill <name>` flag to `ll-history-context`. When provided, the
   CLI checks whether `<name>` appears in `history.planning_skills` (config or
   default) and exits with no output if it does not. In each wired planning
   skill, replace the unconditional effort guard with a single self-gating
   call:
   ```bash
   EFFORT=$(ll-history-context --for-skill create-sprint --effort {{issue_id}} 2>/dev/null || true)
   ```
   Skills remain config-naive: if `EFFORT` is empty, they skip injection.
3. Extend `scripts/tests/test_enh1905_doc_wiring.py` with cases covering the
   opt-out path.

## API/Interface

Config key addition:
```json
// ll-config.json
{
  "history": {
    "planning_skills": ["create-sprint", "scope-epic", "manage-issue", "review-epic"]
  }
}
```

## Integration Map

### Files to Modify
- `config-schema.json` — add `history.planning_skills` (array of strings)
- `scripts/little_loops/cli/history_context.py` — add `--for-skill <name>` flag; exit 0 with no output when skill not in `history.planning_skills`
- `commands/create-sprint.md` — replace unconditional guard with `--for-skill create-sprint` call
- `skills/scope-epic/SKILL.md` — same, `--for-skill scope-epic`
- `skills/manage-issue/SKILL.md` — same, `--for-skill manage-issue`
- `skills/review-epic/SKILL.md` — same, `--for-skill review-epic`

### Tests
- `scripts/tests/test_enh1905_doc_wiring.py` — extend with opt-out coverage

### Dependent Files (Callers/Importers)
- The four skill files in `Files to Modify` are both modified and the consumers of the new config key
- Any skill added to `history.planning_skills` by a user will become an additional caller

### Documentation
- N/A — new config key and CLI flag; check `docs/` if `history.effort_fields` config pattern is documented to add a matching entry for `history.planning_skills`; add `--for-skill` to `ll-history-context` man-page / `--help` output

### Configuration
- `config-schema.json` — already in Files to Modify; schema addition
- `.ll/ll-config.json` — user-facing config where `history.planning_skills` is set (no code change; users opt in/out here)

### Similar Patterns
- `history.effort_fields` (ENH-1905) — same config-or-default contract

## Implementation Steps

1. Add `history.planning_skills` (list[str]) to `config-schema.json` with default `["create-sprint", "scope-epic", "manage-issue", "review-epic"]`
2. Add `--for-skill <name>` flag to `ll-history-context` (`history_context.py`): read `history.planning_skills` from config, exit 0 with no output if `<name>` is not in the list
3. Replace the unconditional effort guard in each of the four planning skill files with a single `--for-skill <name> --effort` invocation; skill logic: inject if non-empty, skip if empty
4. Extend `scripts/tests/test_enh1905_doc_wiring.py` with opt-out path test cases (empty list → no invocations; custom list → only named skills invoke guard)

## Scope Boundaries

- **In scope**: `history.planning_skills` config key; per-skill conditional guard.
- **Out of scope**: Per-issue opt-out; dynamically loading skills at runtime;
  any change to which metrics are surfaced (ENH-1905).

## Implementation Notes

This issue should be implemented **after** ENH-1905 is complete and tested.
The conditional guard must reuse the same `|| true` graceful-degradation
pattern — a config-read failure must never abort the skill.

## Impact

- **Priority**: P4 — quality-of-life; depends on ENH-1905.
- **Effort**: Small.
- **Risk**: Low — purely additive config key with a safe default.
- **Breaking Change**: No.

## Labels

`history-db`, `configurability`

---

**Open** | Created: 2026-06-03 | Priority: P4


## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Partially implemented: `history.planning_skills` config key exists in config-schema.json (line 1432) with the correct default list. Remaining: `--for-skill` flag on `ll-history-context` CLI and the per-skill guards in scope-epic, manage-issue skill files.

## Session Log
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:format-issue` - 2026-06-03T21:01:30 - `05f0b8cd-d4c6-444a-8f99-5505d4cea6e9.jsonl`
