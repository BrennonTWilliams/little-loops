---
id: ENH-1909
title: Make planning-skill history injection configurable via history.planning_skills
type: ENH
priority: P4
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T00:00:00Z'
completed_at: '2026-06-06T20:02:23Z'
discovered_by: review
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1905
labels:
- history-db
- configurability
confidence_score: 98
outcome_confidence: 77
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 20
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

~~1. Add `history.planning_skills` (list[str]) to `config-schema.json` with default `["create-sprint", "scope-epic", "manage-issue", "review-epic"]`.~~ **DONE** — `config-schema.json:1454-1459` and `HistoryConfig.planning_skills` (`features.py:794`) are fully implemented including `from_dict` deserialization.

2. Add a `--for-skill <name>` flag to `ll-history-context` (`history_context.py`). Flag type: `type=str, default=None` (string value, not boolean). In `_build_parser()` (lines 51–96), add alongside existing flags. In `main_history_context()`, insert the guard **after** the `--effort` dispatch block (lines 143–164) and before the main issue-context path (~line 165):
   ```python
   if args.for_skill is not None:
       from little_loops.config import BRConfig
       cfg = BRConfig(Path.cwd())
       if args.for_skill not in cfg.history.planning_skills:
           return 0
   ```
   In each wired planning skill, replace the unconditional effort guard with a single self-gating call:
   ```bash
   EFFORT=$(ll-history-context --for-skill create-sprint --effort {{issue_id}} 2>/dev/null || true)
   ```
   Skills remain config-naive: if `EFFORT` is empty (skill not in list), they skip injection.

3. Extend `scripts/tests/test_history_context_cli.py` (class `TestHistoryContextEffortFlag`, lines 191–245) with a `TestForSkillFlag` class. Follow the established triplet: (a) skill in config → proceeds normally, (b) skill not in config → exits 0 with empty output, (c) empty list → exits 0 with empty output. Also add doc-wiring needles to `test_wiring_cli_registry.py` (`--for-skill` in `docs/reference/CLI.md`) and `test_wiring_skills_and_commands.py` (guard present in each of the four skill files).

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
- ~~`config-schema.json`~~ — **DONE** (`history.planning_skills` at `config-schema.json:1454-1459`)
- `scripts/little_loops/cli/history_context.py` — add `--for-skill <name>` (string flag) in `_build_parser()` lines 51–96; insert guard in `main_history_context()` after `--effort` block (~line 165) reading `cfg.history.planning_skills` via `BRConfig(Path.cwd())`
- `commands/create-sprint.md:366` — replace unconditional `ll-history-context ISSUE_ID --effort` with `ll-history-context --for-skill create-sprint --effort ISSUE_ID`
- `skills/scope-epic/SKILL.md:100` — same, `--for-skill scope-epic`
- `skills/manage-issue/SKILL.md:108` — same, `--for-skill manage-issue`
- `skills/review-epic/SKILL.md:121` — same, `--for-skill review-epic`

### Tests
- `scripts/tests/test_history_context_cli.py` — add `TestForSkillFlag` class modeled after `TestHistoryContextEffortFlag` (lines 191–245): triplet of (skill in list, skill not in list, empty list). **Config isolation**: use `monkeypatch.chdir(tmp_path)` and write a `ll-config.json` under `tmp_path` so `BRConfig(Path.cwd())` picks up the custom `planning_skills` list; or patch `BRConfig` directly. The `TestHistoryContextEffortFlag` class does not show this pattern — it must be added fresh.
- `scripts/tests/test_wiring_skills_and_commands.py` — add `DOC_STRINGS_PRESENT` needle for `--for-skill` guard in each of the four planning skill files
- `scripts/tests/test_wiring_cli_registry.py` — add needle asserting `--for-skill` appears in `docs/reference/CLI.md`

### Dependent Files (Callers/Importers)
- The four skill files in `Files to Modify` are both modified and the consumers of the new config key
- `scripts/little_loops/config/features.py:794` — `HistoryConfig.planning_skills` field (already done)
- `scripts/little_loops/config/core.py:647` — `BRConfig.to_dict()` already serializes `planning_skills`
- Any skill added to `history.planning_skills` by a user becomes an additional caller

### Documentation
- `docs/reference/CLI.md` — add `--for-skill <name>` to `ll-history-context` flags table; verified by `test_wiring_cli_registry.py`
- `docs/reference/API.md` — `### main_history_context` flags block currently lists `ISSUE_ID`, `--file PATH`, `--db PATH`, `--effort`; add `--for-skill NAME` row [Agent 2 finding]
- `.claude/CLAUDE.md` — `ll-history-context` bullet in `## CLI Tools`; may need `--for-skill` mention

### Configuration
- `config-schema.json:1454-1459` — **DONE**; schema already has `planning_skills` with correct default and description
- `.ll/ll-config.json` — user-facing config where `history.planning_skills` is set (no code change; users opt in/out here)

### Similar Patterns
- `history.effort_fields` (ENH-1905) — same config-or-default contract; `--effort` branch at `history_context.py:143-164` is the direct implementation model

## Implementation Steps

1. ~~Add `history.planning_skills` to `config-schema.json`~~ — **DONE** (`config-schema.json:1454`, `features.py:HistoryConfig.planning_skills` at line 794)

2. In `scripts/little_loops/cli/history_context.py`:
   - In `_build_parser()` (line ~80, after `--effort` flag): add `parser.add_argument("--for-skill", type=str, default=None, metavar="NAME", help="Exit 0 with no output if NAME is not in history.planning_skills.")`
   - In `main_history_context()` (line ~165, after the `if args.effort:` block ends): insert guard using `BRConfig(Path.cwd())` → `cfg.history.planning_skills` (same pattern as `--effort` branch at lines 143–164); return 0 with no output if skill not in list

3. In each of the four planning skill files, replace the unconditional effort guard:
   - `commands/create-sprint.md:366`: `EFFORT=$(ll-history-context --for-skill create-sprint --effort ISSUE_ID 2>/dev/null || true)`
   - `skills/scope-epic/SKILL.md:100`: `EFFORT=$(ll-history-context --for-skill scope-epic --effort PARENT_ISSUE_ID 2>/dev/null || true)`
   - `skills/manage-issue/SKILL.md:108`: `EFFORT=$(ll-history-context --for-skill manage-issue --effort {{issue_id}} 2>/dev/null || true)`
   - `skills/review-epic/SKILL.md:121`: `EFFORT=$(ll-history-context --for-skill review-epic --effort CHILD_ISSUE_ID 2>/dev/null || true)`

4. In `scripts/tests/test_history_context_cli.py`, add `TestForSkillFlag` class (modeled after `TestHistoryContextEffortFlag` lines 191–245) with three cases: (a) skill in default list → proceeds normally; (b) skill not in list → returns 0 with empty output; (c) `planning_skills: []` in config → returns 0 with empty output. Use `monkeypatch.chdir(tmp_path)` + write `ll-config.json` to `tmp_path` so `BRConfig(Path.cwd())` sees the test config. Add doc-wiring needles in `test_wiring_skills_and_commands.py` and `test_wiring_cli_registry.py`.

5. Update `docs/reference/API.md` — add `--for-skill NAME` to the `### main_history_context` flags block (alongside existing `--effort`, `--file PATH`, `--db PATH`).

6. Run `python -m pytest scripts/tests/test_history_context_cli.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_wiring_cli_registry.py -v`

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

_Added by `/ll:verify-issues` on 2026-06-04_

**Verdict: NEEDS_UPDATE** — `history.planning_skills` config key exists in BOTH `config-schema.json` (line 1432) AND `scripts/little_loops/config/features.py:758` (`HistoryConfig` class with `from_dict` deserialization). The config infrastructure is fully implemented — including defaults and `from_dict` support. Remaining work: `--for-skill` flag on `ll-history-context` CLI, and per-skill guards in scope-epic/manage-issue/review-epic/create-sprint skill files. Previous verification (2026-06-03) noted only schema existence; the Python config class implementation was missed.

- `/ll:verify-issues` - 2026-06-05 - Config schema and HistoryConfig class ARE implemented (`history.planning_skills` in config-schema.json:1432 and features.py:757). However, `--for-skill` flag does not exist on `ll-history-context`, and no planning skill files have per-skill guards. Issue body should acknowledge the completed config infrastructure as Step 1 done, and focus remaining work on the CLI flag (Step 2) and per-skill integration (Step 3).

## Session Log
- `/ll:ready-issue` - 2026-06-06T19:59:09 - `bc19e9f1-b796-4f10-896b-5f271b0c432a.jsonl`
- `/ll:confidence-check` - 2026-06-06T20:00:00 - `b4bb0afc-7c58-48dd-b83b-753c7f275dfd.jsonl`
- `/ll:wire-issue` - 2026-06-06T19:54:25 - `a9502e41-f43e-4d95-ba3c-278aac8cca71.jsonl`
- `/ll:refine-issue` - 2026-06-06T19:49:39 - `8282f068-b0be-423b-87cf-845d27a0c02b.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-04T22:14:36 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:verify-issues` - 2026-06-04T18:41:58 - `18003f27-33de-416c-b594-e351d9d60c9d.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:format-issue` - 2026-06-03T21:01:30 - `05f0b8cd-d4c6-444a-8f99-5505d4cea6e9.jsonl`

**Update 2026-06-04**: Verdict unchanged (NEEDS_UPDATE). Confirmed `history.planning_skills` exists in both `config-schema.json` (line ~1432) and `scripts/little_loops/config/features.py:758` (`HistoryConfig` class with `from_dict` deserialization). The config infrastructure is fully implemented — including defaults. Remaining work: `--for-skill` flag on `ll-history-context` CLI, and per-skill guards in the four planning skill files. The Integration Map and Implementation Steps sections accurately capture remaining work; the issue body just needs to acknowledge partial completion.
