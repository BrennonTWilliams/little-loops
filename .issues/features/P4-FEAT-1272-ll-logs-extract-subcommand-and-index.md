---
id: FEAT-1272
type: FEAT
priority: P4
status: done
title: "ll-logs: extract subcommand and logs/index.md generation"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false

size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1269
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1272: ll-logs: extract subcommand and logs/index.md generation

## Summary

Add the `extract` subcommand to `scripts/little_loops/cli/logs.py` (created in FEAT-1271). Implements `--project`, `--all`, and `--cmd` flags, structures output as `logs/<project-slug>/<session-id>.jsonl`, and generates `logs/index.md`.

## Parent Issue
Decomposed from FEAT-1269: ll-logs: discover + extract subcommands and entry-point registration

## Depends On
- FEAT-1271 — `logs.py` must exist with `main_logs()` and argparse skeleton before this can be added

## Current Behavior

`ll-logs` exists (post-FEAT-1271) but does not yet support extracting logs to a structured directory.

## Expected Behavior

```bash
ll-logs extract --project <slug>  # Extract logs for one project to logs/<slug>/
ll-logs extract --all             # Extract all projects to logs/
ll-logs extract --cmd <tool>      # Filter by specific ll- CLI tool (e.g., ll-history)
```

Output structure:
```
logs/
  index.md
  little-loops/
    e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl
  my-other-project/
    ...
```

## Implementation Steps

1. **Add `extract` subcommand to `logs.py`**:
   - Add `extract` parser to existing `add_subparsers` with `--project`, `--all`, `--cmd` flags
   - Implement extraction logic:
     - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup
     - For `--all`: iterate `(Path.home() / ".claude" / "projects").iterdir()` using `discover_all_projects()` helper from FEAT-1271
     - Use `extract_user_messages(project_folder, include_agent_sessions=False)` from `user_messages.py:383` or stream-filter JSONL directly
     - Detect ll-relevance via: (a) `queue-operation` records with `ll-` prefix, (b) `type: "user"` records with `<command-name>/ll:` pattern, (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
     - Write filtered records to `logs/<project-slug>/<session-id>.jsonl`
     - `--cmd <tool>`: additional filter for specific ll- tool name in Bash tool-use blocks
   - Structure output: `logs/<project-slug>/<session-id>.jsonl`

2. **Generate `logs/index.md`** after extraction:
   - Iterate `logs/` subdirs, aggregate: project name, JSONL count, date range from `timestamp` fields
   - Write markdown table (no existing analog in CLI layer; see `doc_scraper.py:504-528` for pattern reference)

3. **Verify**: `ll-logs extract --all` and `ll-logs extract --project <slug>` populate `logs/` correctly

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints are identified by wiring analysis — ensure FEAT-1271 has landed before implementing FEAT-1272:_

4. Confirm `scripts/little_loops/cli/__init__.py` has `main_logs` import and `__all__` entry (FEAT-1271)
5. Confirm `scripts/pyproject.toml` has `ll-logs` entry point registered (FEAT-1271)
6. After `TestExtract` passes, add `TestMainLogsIntegration` to `scripts/tests/test_cli.py` following `test_issue_history_cli.py:71-137` pattern
7. Documentation updates (`CLAUDE.md`, `commands/help.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`) are handled by FEAT-1004/FEAT-1005 — no action needed in FEAT-1272

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `extract` subcommand (created in FEAT-1271)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports `main_logs` and exports it in `__all__`; syntax errors in `logs.py` cause all CLI-importing test files to fail collection (**handled by FEAT-1271**)
- `scripts/pyproject.toml:65-66` — registers `ll-logs = "little_loops.cli:main_logs"` entry point (**handled by FEAT-1271**)

### Similar Patterns
- `scripts/little_loops/user_messages.py:383` — `extract_user_messages(project_folder, include_agent_sessions=False)`
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern
- `scripts/doc_scraper.py:504-528` — `_build_node()` directory structure builder (shows `index.md` filepath assignment pattern; NOT a markdown table generator)
- `scripts/little_loops/issue_history/doc_synthesis.py:301-315` — canonical markdown table pattern: header row, `|---|` separator, data rows via f-strings, blank lines surrounding block
- `scripts/little_loops/issue_history/formatting.py:565-595` — second markdown table example (Type Distribution table)
- FEAT-1271's `discover_all_projects()` helper — reuse for `--all` flag

### Tests
- `scripts/tests/test_ll_logs.py` — add to existing file (created in FEAT-1271)
  - `class TestExtract` — integration tests using `tmp_path` + `_write_jsonl()` helper
    - `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)` for single-project
    - `patch("pathlib.Path.home", return_value=tmp_path)` for multi-project
    - `_write_jsonl(path, records)` helper pattern from `test_user_messages.py:109`
    - Verify `logs/<slug>/<session>.jsonl` written correctly
    - Verify `logs/index.md` generated with expected content
- `scripts/tests/test_cli.py:2590+` — add `TestMainLogsIntegration` class (follows `patch.object(sys, "argv", [...])` + `main_logs()` pattern from `test_issue_history_cli.py:71-137`; **scoped to FEAT-1271** but must be present before this feature is tested end-to-end)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_ (**all tracked in FEAT-1004/FEAT-1005 — not in scope for FEAT-1272 itself**)
- `.claude/CLAUDE.md:116` — CLI Tools list; add `ll-logs` after `ll-gitignore`
- `commands/help.md:234` — CLI TOOLS block; add `ll-logs` line
- `skills/init/SKILL.md:430-444,515-532` — both `Bash(ll-logs:*)` allow-entry blocks
- `skills/configure/areas.md:823` — update count `15`→`16` and add `ll-logs` to tool enumeration
- `README.md:241+` — add `### ll-logs` section in CLI Tools
- `docs/reference/CLI.md:1012+` — add `### ll-logs` section; update `--dry-run`/`--quiet`/`--config` "Used by" rows
- `docs/reference/API.md:3185+` — add `### main_logs` entry

## Codebase Research Findings (from FEAT-1269)

- **`extract_user_messages()` full signature**: `extract_user_messages(project_folder: Path, limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False)` — `project_folder` is required positional arg; set `include_agent_sessions=False`
- **JSONL streaming exact pattern** (`user_messages.py:437-450`): `open(jsonl_file, encoding="utf-8")` → strip line → skip blank/JSONDecodeError → `json.loads(line)` — `OSError` caught and silently skipped at line 452
- **No existing CLI-layer `index.md` generation**: write fresh — iterate `logs/` subdirs, aggregate metadata, write markdown table
- **`temp_project_folder` fixture** (`test_user_messages.py:103-107`): `tempfile.TemporaryDirectory()` yielded as `Path`

## Codebase Research Findings (from /ll:refine-issue)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Multi-subcommand argparse pattern**: `scripts/little_loops/cli/history.py:35-281` is the canonical template — `add_subparsers(dest="command")`, root-level `add_config_arg(parser)`, `if not args.command: parser.print_help(); return 1`, then `if args.command ==` dispatch chain, returns `0`/`1`
- **Logger setup sequence** (follow `history.py:196-197`): call `configure_output(config.cli)` then `logger = Logger(use_color=use_color_enabled())`; imports come from `little_loops.cli.output` and `little_loops.logger`
- **JSONL write pattern for raw dicts**: `json.dumps(record) + "\n"` per line (not `.to_dict()` — write the raw parsed dict, not a `UserMessage` object)
- **`<command-name>/ll:` detection** exact location: `user_messages.py:771` — `re.compile(rf"<command-name>/ll:{re.escape(skill)}</command-name>")`; same pattern in `cli/messages.py:193`
- **`queue-operation` record schema (NOW KNOWN — resolved from live JSONL files)**:
  - Fields: `type` (`"queue-operation"`), `operation` (`"enqueue"` | `"dequeue"`), `timestamp` (ISO8601), `sessionId` (UUID), `content` (string, present on `enqueue` only)
  - `content` is either a plain command string (e.g., `"/ll:refine-issue ENH-1253 --auto"`) or a `<task-notification>` XML blob
  - Detection for criterion (a): `record.get("type") == "queue-operation" and record.get("operation") == "enqueue" and "/ll:" in record.get("content", "")`
  - Standalone queue-operation files (2-line enqueue+dequeue) are distinct from inline records in full conversation JSONL files — both patterns exist; stream both when iterating session files
- **Agent file exclusion glob** (more concise form): `session_log.py:78` — `[f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]`
- **`temp_project_folder` fixture** is at `test_user_messages.py:103-107` (the `@pytest.fixture`); **`_write_jsonl` helper** is at `test_user_messages.py:109-113` — it is an instance method (takes `self`) on `TestExtractUserMessages`, not a standalone function
- **`doc_scraper.py:504-528` is `_build_node()`** (NOT a markdown table generator) — it builds a directory/filepath tree and writes `index.md` path assignments; see `issue_history/doc_synthesis.py:301-315` for the actual markdown table pattern (header row → `|---|` separator → f-string data rows → `"\n".join(lines)`)
- **`get_project_folder()` returns `None`** if the encoded project folder doesn't exist on disk — implementation must null-check before iterating session files: `folder = get_project_folder(cwd); if folder is None: print("Error: project not found"); return 1`
- **`extract_user_messages()` returns `UserMessage` objects** (not raw dicts) — for raw JSONL output, use direct stream-parse approach (`user_messages.py:437-450`) rather than `extract_user_messages()`; this is required, not optional

## Acceptance Criteria

- [ ] `ll-logs extract --all` populates `logs/` with filtered JSONL entries
- [ ] `ll-logs extract --project <slug>` works for a specific project
- [ ] `ll-logs extract --cmd <tool>` filters by ll- tool name
- [ ] `logs/index.md` is created with a readable summary (project, JSONL count, date range)
- [ ] `TestExtract` test class passes

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small-Medium — extend existing module, ~60-100 LOC + tests
- **Risk**: Low — additive; no changes to existing code paths
- **Breaking Change**: No

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1271 is an unresolved critical blocker**: `logs.py`, `discover_all_projects()`, `test_ll_logs.py`, and the `ll-logs` pyproject entry point are all created by FEAT-1271, which is still in backlog. FEAT-1272 has nothing to extend until FEAT-1271 merges.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-23T16:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:55:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b35255f7-b6b6-46d3-af77-efb623ea0ed7.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adbd4941-0ef6-48a9-b49a-f6150ed66268.jsonl`
- `/ll:confidence-check` - 2026-04-23T16:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5466f70c-2a0b-41bd-b115-50a7fdab0c35.jsonl`
- `/ll:wire-issue` - 2026-04-23T15:45:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06b56281-3d1e-47d5-8c2d-a2b87d670bd7.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:40:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35ac7496-e8f6-4f6d-8dd0-4b7a2571b36e.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-23
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1273: ll-logs: extract subcommand core (--project, --all, --cmd)
- FEAT-1274: ll-logs: generate logs/index.md after extraction

---

## Status

**Decomposed** | Created: 2026-04-23 | Priority: P4
