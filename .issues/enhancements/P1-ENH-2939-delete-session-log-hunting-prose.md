---
id: ENH-2939
title: Delete session-log JSONL-hunting prose in favor of ll-issues append-log
type: ENH
priority: P1
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T01:56:43Z'
parent: EPIC-2938
epic: EPIC-2938
program_design_not_applicable: true
relates_to:
- ENH-2950
- ENH-2952
labels:
- skills
- cleanup
- determinism
confidence_score: 99
outcome_confidence: 96
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2939: Delete session-log JSONL-hunting prose in favor of `ll-issues append-log`

## Summary

Markdown-only cleanup (no Python changes) removing prose that duplicates an existing CLI, and establishing the session-log convention the rest of EPIC-2938 adopts. Cheapest child; do first.

**Descoped after review** (2026-07-31), because neither remaining item fit a markdown-only issue:

- decide-issue's option-detection prose → **ENH-2950**. It cannot delegate to `ll-issues check-decidable`: that command is exit-code only (`locate_enumerable_options` returns just `(count, heading)`), while Phase 3b *materializes* `**Option A**`/`**Option B**` blocks into the file. Delegating requires widening the locator's return shape — a Python change.
- the 17-site flag-parse block → **ENH-2952**. The consolidation is not obviously a net context win and needs measurement first; bundling it would have blocked this sweep.

## Current Behavior

**Session-log JSONL hunting**: 7 files (`audit-claude-config`, `capture-issue`, `confidence-check`, `go-no-go`, `issue-size-review`, `manage-issue`, `scope-epic`) instruct the LLM to find the current session log by scanning `~/.claude/projects/` for the dash-encoded project dir and the most recently modified `.jsonl`. 11 other files already call `ll-issues append-log` or `little_loops.session_log.append_session_log_entry` — so the convention exists and these 7 are the stragglers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction — actual count is 6, not 7**: `skills/audit-claude-config/SKILL.md` (and its companions `report-template.md`, `wave1-prompts.md`) contain no session-log append step and no `~/.claude/projects` hunting prose at all in the current tree. It appears clean already (or the step was removed since this issue was captured). Verify at implementation time before editing it.
- Exact hunting-prose locations in the 6 files that do need the sweep:
  - `skills/capture-issue/SKILL.md:304-311` — step 5 ("Append session log entry"), single occurrence
  - `skills/confidence-check/SKILL.md:353-360` — single occurrence
  - `skills/go-no-go/SKILL.md:469-482` (under `## Session Log`) — single occurrence, phrased as "**Locate the session JSONL**"
  - `skills/issue-size-review/SKILL.md:282-289` and `skills/issue-size-review/SKILL.md:310-317` — **two** independent occurrences (child-issue write, parent-issue write)
  - `skills/manage-issue/SKILL.md:418-422` (short pointer, step "1.5. Append Session Log Entry") **+** `skills/manage-issue/templates.md:386-395` ("Session Log Entry Format" section, holds the actual hunting sentence and entry template) — one logical site split across two files
  - `skills/scope-epic/SKILL.md:317-322` (canonical instruction) plus two delegating references at lines 347 and 376 ("same pattern as EPIC")
- `scripts/little_loops/session_log.py::append_session_log_entry(issue_path, command, session_jsonl=None)` already does the exact resolution the prose describes manually, via `get_current_session_jsonl()` (globs the project's Claude Code session dir, excludes `agent-*`, picks max-mtime `.jsonl`). The CLI (`ll-issues append-log`, wired in `scripts/little_loops/cli/issues/append_log.py::cmd_append_log`) takes only `issue_path` and `log_command` — there is no session-path argument to supply, so the hunting prose is fully redundant in every one of the 6 files.
- No test greps `commands/*.md`/`skills/*/SKILL.md` for forbidden `~/.claude/projects` phrasing or required `ll-issues append-log` usage — `scripts/tests/test_session_log.py` only tests the underlying Python helper.

## Expected Behavior

All 7 JSONL-hunting blocks replaced with `ll-issues append-log <issue_path> "<command>"` (or a one-line pointer to `little_loops.session_log.append_session_log_entry` where a path-only variant is needed). No skill or command instructs scanning `~/.claude/projects/`.

## Integration Map

### Files to Modify

- `skills/capture-issue/SKILL.md:304-311`
- `skills/confidence-check/SKILL.md:353-360`
- `skills/go-no-go/SKILL.md:469-482`
- `skills/issue-size-review/SKILL.md:282-289` and `:310-317` (two sites)
- `skills/manage-issue/SKILL.md:418-422` and `skills/manage-issue/templates.md:386-395` (split site)
- `skills/scope-epic/SKILL.md:317-322` (canonical) and `:347`, `:376` (delegating references — update if they quote the hunting sentence directly, otherwise they already point at the fixed canonical block)
- `skills/audit-claude-config/SKILL.md` — verify only; research found no hunting prose to remove here

### Similar Patterns (canonical replacement template)

- `commands/refine-issue.md:561-573` — fullest, most-replicated shape: Bash-tool lead-in sentence → fenced `ll-issues append-log <path> /ll:<command>` → fallback caveat sentence → fenced backtick-format fallback line. Matched byte-for-byte (modulo command name) by `commands/ready-issue.md:358-368`, `commands/tradeoff-review-issues.md:281-291`/`:333-343`, `commands/verify-issues.md:174-186`, `commands/scan-codebase.md:314-326`, `skills/decide-issue/SKILL.md:447-457`, `skills/wire-issue/SKILL.md:408-418`.
- Terser variant with no fallback block: `skills/audit-issue-conflicts/SKILL.md:370-411`, `skills/spike/SKILL.md:234-238` — bare `ll-issues append-log "[issue-file-path]" /ll:<command>`.
- Path-only Python-helper variant (the "one-line pointer" this issue's Expected Behavior mentions): `skills/format-issue/SKILL.md:331-351` — inline `python3 -c` snippet calling `append_session_log_entry(Path('ISSUE_FILE_PATH'), '/ll:format-issue')`.

### Tests

- No existing test covers the markdown convention itself; `scripts/tests/test_session_log.py` and `scripts/tests/test_issues_cli.py:3824-3898` cover only the Python helper/CLI.

_Wiring pass added by `/ll:wire-issue`:_
- No test currently enforces AC1 ("no skill/command instructs scanning `~/.claude/projects/`") — add one. Precedent already exists for the positive half of this shape: `scripts/tests/test_decide_issue_skill.py:200-216` (`class TestSessionLogCall`) asserts `"ll-issues append-log" in phase8_text` scoped to a phase-slice of `skills/decide-issue/SKILL.md`; `scripts/tests/test_reconcile_issue_command.py:78-81` does the command-file equivalent for `commands/reconcile-issue.md`. A new test should follow this section-slice + substring-assert convention (not a golden-file diff — that style doesn't exist in this suite) and assert **both halves** per file: `"ll-issues append-log" in content` (or the `append_session_log_entry` pointer for `templates.md`) and `"~/.claude/projects" not in content`. [Agent 3 finding]

## Proposed Solution

Pure markdown edits. Reuse points: `ll-issues append-log`, `scripts/little_loops/session_log.py::append_session_log_entry`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Copy `commands/refine-issue.md:561-573`'s block verbatim (only the `/ll:<command>` name changes) into each of the 6 target sites — it's the shape 7 other files already share, so it's the safest choice for consistency:

```markdown
After updating the issue, use the Bash tool to append a session log entry:

​```bash
ll-issues append-log <path-to-issue-file> /ll:<command-name>
​```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

​```
- `/ll:<command-name>` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
​```
```

For `skills/manage-issue/SKILL.md` + `templates.md`, since there's no existing two-file-split precedent, remove the hunting sentence from both: replace `SKILL.md:418-422`'s pointer with the CLI call directly, and replace `templates.md:386-395`'s "Session Log Entry Format" hunting sentence with a one-line note that the format is produced automatically by `append_session_log_entry`.

## Implementation Steps

1. Sweep the 7 session-log files; replace hunt-prose with the CLI/helper call.
2. Run `ll-verify-skills` and `python -m pytest scripts/tests/` (no behavior change expected).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Verify `skills/audit-claude-config/SKILL.md` (+ `report-template.md`, `wave1-prompts.md`) first — research found no hunting prose there; confirm before treating it as a sweep target.
2. Replace hunting prose in the 6 confirmed files with the canonical block from `commands/refine-issue.md:561-573`, substituting the command name (`/ll:capture-issue`, `/ll:confidence-check`, `/ll:go-no-go`, `/ll:issue-size-review` ×2 sites, `/ll:manage-issue`, `/ll:scope-epic`).
3. For `skills/manage-issue/`, edit both `SKILL.md:418-422` and `templates.md:386-395`.
4. Add a regression test enforcing AC1 (see Integration Map → Tests → wiring-pass note): assert `"ll-issues append-log" in content` and `"~/.claude/projects" not in content` for each of the 6 target files, following `scripts/tests/test_decide_issue_skill.py:200-216`'s section-slice pattern. [Agent 3 finding]
5. Run `ll-verify-skills` and `python -m pytest scripts/tests/test_session_log.py -v` plus the full suite (no behavior change expected — these are prose-only edits, not calls into `session_log.py`).

## Acceptance Criteria

- [x] No skill/command instructs scanning `~/.claude/projects/` for session JSONL files
- [x] All 7 files call `ll-issues append-log` (or the `session_log` helper where a path-only variant is needed)
- [x] `ll-verify-skills` passes; `python -m pytest scripts/tests/` green
- [x] Net markdown reduction recorded in the PR/commit description

> ⚠ Research note (`/ll:refine-issue`): `skills/audit-claude-config/SKILL.md` was not found to contain hunting prose in the current tree — see Current Behavior → Codebase Research Findings. Verify at implementation time whether this criterion should scope to the 6 confirmed files instead of 7.

## Program Design

### Types

- N/A — markdown-only change; no Python types added or modified

### Signatures

Existing surfaces consumed (unchanged):
- `ll-issues append-log <issue_path> <log_command>`
- `little_loops.session_log.append_session_log_entry(...)`

## Scope Boundaries

- In scope: prose deletion/replacement in the 7 session-log files.
- Out of scope: any Python/CLI changes; decide-issue option detection (ENH-2950); the flag-parse block (ENH-2952).

## Impact

- **Priority**: P1 - Cheapest child; sets the session-log convention the rest of EPIC-2938 adopts
- **Effort**: Small - Markdown edits only, 7 files
- **Risk**: Low - No behavior change; verified by ll-verify-skills + existing tests

---

## Resolution

- **Status**: Done
- **Completed**: 2026-08-01

Swept all 6 confirmed hunting-prose sites (`skills/audit-claude-config/SKILL.md` verified clean per prior research, no edit needed) with the `commands/refine-issue.md:561-573` canonical block: `ll-issues append-log <path> /ll:<command>` plus a manual-format fallback. `skills/manage-issue/` split site (`SKILL.md` + `templates.md`) collapsed to a one-line pointer + fallback-only reference respectively, and `SKILL.md`'s session-log section was trimmed further to keep the file under `ll-verify-skills`'s 500-line cap after the edit.

Net byte count across the 7 touched files: -293 bytes (line count rose slightly, +8, because the canonical block trades a single hunting sentence for an executable command + explicit fallback — but total prose footprint dropped).

Added `scripts/tests/test_session_log_prose_sweep.py` (14 tests, parametrized over the 6 files) asserting both `"ll-issues append-log" in content` and `"~/.claude/projects" not in content`, per the wiring-pass note and `test_decide_issue_skill.py`'s section-slice precedent.

`python -m pytest scripts/tests/` has one pre-existing, unrelated failure (`test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`, ENH-2923/ENH-2925 prose drift) confirmed present on `main` before this change (reproduced via `git stash`). `ll-verify-skills` passes clean.

## Status

**Done** | Created: 2026-07-31 | Priority: P1

## Notes

Originally scoped as three sweeps; items 1 and 3 were split to ENH-2950 and ENH-2952 respectively after review found neither could be done markdown-only.

_Wiring pass added by `/ll:wire-issue`:_ `.gemini/skills/` and `.kimi-code/skills/` hold checked-in `ll-adapt`-generated copies of 5 of the 6 target files (`capture-issue`, `confidence-check`, `go-no-go`, `manage-issue`, `scope-epic` — `issue-size-review` has no host-adapted copy). These copies are already drifted from source independent of this issue (confirmed: `skills/capture-issue/SKILL.md` has been edited since `.gemini`'s copy last regenerated, with no corresponding `ll-adapt` re-run), and no test gates `.gemini`/`.kimi-code` content parity — regenerating them is not established repo practice per-edit. FYI only, not added to Implementation Steps: run `ll-adapt --host gemini --apply` / `ll-adapt --host kimi --apply` afterward if you want these copies to reflect the cleanup sooner rather than at the next scheduled adapt pass. [Agent 1 finding]

## Session Log
- `/ll:manage-issue` - 2026-08-01T01:56:36 - `7c54f229-9ea2-4347-bbf8-25da4b88edbd.jsonl`
- `/ll:ready-issue` - 2026-08-01T01:48:37 - `54418d3e-5969-486e-aac9-560b45049b27.jsonl`
- `/ll:confidence-check` - 2026-08-01T01:47:14 - `791535d4-3cff-4346-93b9-0e3280b0be01.jsonl`
- `/ll:wire-issue` - 2026-08-01T01:45:11 - `a05b2d4d-343c-4b0d-abfd-0fa1d7bf496d.jsonl`

- `/ll:refine-issue` - 2026-08-01T01:36:22 - `2fbdd891-b4ef-4136-bace-68161bf30dac.jsonl`
