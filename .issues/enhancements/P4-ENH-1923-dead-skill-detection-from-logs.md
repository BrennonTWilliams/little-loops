---
id: ENH-1923
title: 'Dead-skill detection: never-invoked skills from log corpus'
type: ENH
priority: P4
status: done
captured_at: '2026-06-04T02:27:34Z'
completed_at: '2026-06-06T02:16:12Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- ENH-1921
labels:
- captured
- ll-logs
- find-dead-code
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 16
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 23
---

# ENH-1923: Dead-skill detection — never-invoked skills from log corpus

## Summary

Cross-reference the ll skill/command catalog against the log corpus to flag
skills that are **never invoked** in any real session — discoverability or value
candidates for `/ll:find-dead-code`.

## Current Behavior

`find-dead-code` analyzes code references but has no usage signal: a skill can be
fully wired and referenced yet never actually invoked by any user. Such skills
are invisible to current dead-code analysis.

`ll-logs stats` (ENH-1921, done) provides per-skill invocation counts from
`skill_events` in `.ll/history.db`, but it only reports what was observed — it
has no catalog side to compare against. There is no `--never-invoked` flag and
no set-difference step in the current codebase.

## Expected Behavior

A new `ll-logs dead-skills` subcommand (or `ll-logs stats --never-invoked` flag)
lists catalog skills/commands with zero invocations across the corpus within
`--window-days`, separating "never invoked" from "rarely invoked" (below a
configurable threshold). Supports `--json` output for machine consumption.

## Motivation

A skill nobody triggers is either undiscoverable or low-value. Usage-grounded
dead-skill detection complements reference-based dead-code analysis.

## Proposed Solution

Add a `dead-skills` subcommand to `ll-logs` (in `scripts/little_loops/cli/logs.py`)
following the same pattern as the existing `stats` subcommand:

1. **Build catalog set** — enumerate `skills/*/SKILL.md` using
   `_load_skill_descriptions()` from `verify_triggers.py` (or inline the same
   `skills_dir.glob("*/SKILL.md")` pattern used in `doc_counts.py:check_skill_budget()`);
   enumerate `commands/*.md` using `commands_dir.glob("*.md")` as in
   `adapt_skills_for_codex.py:_process_commands()`.
2. **Build observed-invocation set** — call `_aggregate_skill_stats(db_path, window_days=args.window_days)`
   (already exists in `logs.py`) which returns `dict[str, dict[str, int]]` from
   `skill_events` in `.ll/history.db`.
3. **Name normalization** — skill directory basenames may carry an `ll-` prefix
   (e.g. `skills/ll-commit/`) while `skill_events.skill_name` records the
   invocation without it (e.g. `"commit"`). Apply a normalization step when
   computing the set difference: strip the `ll-` prefix from catalog keys, or
   read the `name:` frontmatter field (parsed by `frontmatter.py:parse_skill_frontmatter()`).
4. **Compute difference** — `never_invoked = catalog_names - observed_names`;
   `rarely_invoked = {n for n, c in observed.items() if c["invocations"] <= threshold}`.
5. **Output** — use `table()` and `print_json()` from `cli/output.py`; support
   `--json` via `add_json_arg()` from `cli_args.py`. JSON shape: list of
   `{"skill": str, "invocations": int, "tier": "never"|"rarely"}`.

**Note**: `find-dead-code` (`commands/find-dead-code.md` / `skills/ll-find-dead-code/`) is a
Claude prompt command, not a Python API. Integration means `find-dead-code` can
call `ll-logs dead-skills --json` as a shell step to pull the never-invoked list
as an additional signal, not a Python import.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `_cmd_dead_skills(args, logger)` handler;
  add `dead-skills` subparser in `_build_parser()`; add dispatch branch in `main_logs()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — exports `main_logs`; no changes needed
- `scripts/pyproject.toml` — `ll-logs` entry point already registered as
  `little_loops.cli:main_logs`; no changes needed

### Reusable Utilities (Read-Only)
- `scripts/little_loops/cli/verify_triggers.py` — `_load_skill_descriptions(skills_dir)`:
  canonical skill catalog loader; returns `dict[str, tuple[str, Path]]` from
  `skills/*/SKILL.md` frontmatter
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — `_process_commands()`:
  reference for `commands_dir.glob("*.md")` enumeration pattern
- `scripts/little_loops/doc_counts.py` — `check_skill_budget()`: shows how to
  exclude bridge skills (`BRIDGE_MARKER = "Bridged from \`commands/"`) and
  `disable-model-invocation: true` skills from the catalog count
- `scripts/little_loops/frontmatter.py` — `parse_skill_frontmatter()`: shared
  SKILL.md frontmatter parser used across CLI tools
- `scripts/little_loops/cli_args.py` — `add_json_arg()`: adds `-j`/`--json`
  `store_true` flag; call on the new subparser immediately after its options
- `scripts/little_loops/cli/output.py` — `print_json()` and `table()`: output
  rendering used by all `ll-logs` subcommands

### Integration with find-dead-code
- `skills/ll-find-dead-code/SKILL.md` — bridge stub for the command
- `commands/find-dead-code.md` — Claude prompt command; can shell out to
  `ll-logs dead-skills --json` as an additional signal step

### Tests
- `scripts/tests/test_ll_logs.py` — extend with a new `TestDeadSkills` class;
  use `_populate_skill_events()` helper (already exists at line 1319) to seed
  `skill_events`; mock `skills/` and `commands/` dirs with a catalog fixture

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` — `DOC_STRINGS_PRESENT` list needs new triples asserting `"dead-skills"` appears in `docs/reference/CLI.md` and `.claude/CLAUDE.md`; follow the pattern of existing ll-logs assertions [Agent 2 finding]

### Documentation
- `docs/reference/API.md` — document `ll-logs dead-skills` subcommand and flags
- `.claude/CLAUDE.md` — update ll-logs subcommand list (line ~184)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-logs` subcommands table (line ~1707) needs a `dead-skills` row; add flags table for `--window-days`, `--threshold`, `--json`; add `dead-skills` to the `--all`/`--project` mutual-exclusion note; add example invocations [Agent 2 finding]
- `docs/ARCHITECTURE.md` — inline comment at line ~250 lists ll-logs subcommands (`discover/extract/sequences/stats/tail`); add `dead-skills` to that list [Agent 2 finding]
- `commands/help.md` — `ll-logs` tool description parenthetical (line ~281) needs `dead-skills` mention for dead-skill detection signal [Agent 2 finding]

### Configuration
- N/A — no new config keys required; `--window-days` reuses the existing stats
  convention

## Implementation Steps

1. **Add `_cmd_dead_skills(args, logger)` to `logs.py`**
   - Reuse `_aggregate_skill_stats(db_path, window_days=args.window_days)` for
     observed invocation counts (already handles multi-project via `--all`)
   - Enumerate catalog: `sorted(skills_dir.glob("*/SKILL.md"))` following
     `verify_triggers.py:_load_skill_descriptions()`; also enumerate
     `sorted(commands_dir.glob("*.md"))` for command stems
   - Apply name normalization: strip `ll-` prefix from skill dir names; read
     `name:` frontmatter field via `frontmatter.py:parse_skill_frontmatter()` when present
   - Exclude bridge skills (contain `BRIDGE_MARKER`) and `disable-model-invocation: true`
     entries (follow `doc_counts.py:check_skill_budget()`)
   - Compute `never_invoked = catalog_names - observed_names` and optional
     `rarely_invoked` tier below `--threshold` (default: 3 invocations)
   - Emit `table()` output with columns `["Skill", "Invocations", "Tier"]` or
     `print_json()` list of `{"skill", "invocations", "tier"}`

2. **Wire subparser in `_build_parser()`** (same file, around line 821)
   - Add `dead_skills_parser = subparsers.add_parser("dead-skills", help="...")` 
   - Add `--project`/`--all` mutually exclusive group (same as stats subparser)
   - Add `--window-days`, `--threshold` (int, default 3), and `add_json_arg()`

3. **Add dispatch in `main_logs()`** (around line 957)
   - `if args.command == "dead-skills": return _cmd_dead_skills(args, logger)`

4. **Add `TestDeadSkills` class to `test_ll_logs.py`**
   - Follow `TestStats` test shape at line 1351
   - Use `_populate_skill_events()` to seed corpus with known skills
   - Pass a tmp `skills/` dir with SKILL.md stubs and `commands/` dir with `.md` stubs
   - Assert never-invoked skills appear in output; assert observed skills do not
   - Assert `--json` output shape: list with `skill`, `invocations`, `tier` keys

5. **Update `docs/reference/API.md`** — add `ll-logs dead-skills` entry

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/CLI.md` — add `dead-skills` row to the `### ll-logs` subcommands table; add flags table (`--window-days`, `--threshold`, `--json`); add `dead-skills` to the `--all`/`--project` mutual-exclusion note; add example invocations (e.g. `ll-logs dead-skills --project . --json`)
7. Update `docs/ARCHITECTURE.md` — add `dead-skills` to the inline comment at line ~250 that lists ll-logs subcommands
8. Update `commands/help.md` — extend the `ll-logs` tool description parenthetical to mention dead-skill detection
9. Update `scripts/tests/test_wiring_cli_registry.py` — add `DOC_STRINGS_PRESENT` triples asserting `"dead-skills"` appears in `docs/reference/CLI.md` and `.claude/CLAUDE.md`

## Acceptance Criteria

- `ll-logs dead-skills --project <dir> --json` outputs a list where a skill
  present in `skills/*/SKILL.md` but absent from `skill_events` appears with
  `"invocations": 0, "tier": "never"`.
- A skill with invocations > 0 and <= threshold appears with `"tier": "rarely"`.
- A skill with invocations > threshold does not appear in the output.
- Output correctly distinguishes a known never-invoked skill from a used one in fixtures.
- Bridge skills (`BRIDGE_MARKER`) and `disable-model-invocation: true` skills are
  excluded from the catalog (same exclusions as `check_skill_budget()`).

## Success Metrics

- Output correctly distinguishes a known never-invoked skill from a used one in fixtures.

## Scope Boundaries

- Out: deciding to delete a skill — this only flags candidates for human/find-dead-code review.
- Out: auto-creating ENH issues for never-invoked skills (leave that to find-dead-code command).

## Impact

- **Priority**: P4 — useful complement to existing dead-code analysis but no active user pain; low urgency
- **Effort**: Small — enumerate catalog files + diff against stats output; no new infrastructure
- **Risk**: Low — additive read-only feature; no changes to existing skill or log behavior
- **Breaking Change**: No

Adds a usage dimension to dead-code review; surfaces discoverability gaps.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/ll-find-dead-code/`; `commands/find-dead-code.md`

## Labels

captured, ll-logs, find-dead-code

## Status

open

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map has wrong path for the logs module: `scripts/little_loops/logs.py` → should be `scripts/little_loops/cli/logs.py`. Also, the skill directory referenced is `skills/find-dead-code/` but actual dir is `skills/ll-find-dead-code/`.

_Corrected by `/ll:refine-issue` on 2026-06-05 — paths fixed and integration map enriched with research findings._

## Session Log
- `/ll:ready-issue` - 2026-06-06T02:06:44 - `771feb09-1baf-4bc1-ab78-5335e9d58af1.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `8e08f497-2fcf-4b4b-9ae0-2a00c506422b.jsonl`
- `/ll:wire-issue` - 2026-06-06T02:02:20 - `9e891511-e9ea-4d36-a888-bd1a019970fb.jsonl`
- `/ll:refine-issue` - 2026-06-06T01:57:22 - `54096b77-a519-4758-9881-2e2ff04c43a0.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:format-issue` - 2026-06-04T03:10:33 - `6828653f-c5aa-47bf-a167-82e4553412d0.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
