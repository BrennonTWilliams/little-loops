---
id: FEAT-1273
type: FEAT
priority: P4
status: backlog
title: "ll-logs: extract subcommand core (--project, --all, --cmd)"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false
parent_issue: FEAT-1272
confidence_score: 80
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 22
score_change_surface: 25
size: Very Large
---

# FEAT-1273: ll-logs: extract subcommand core (--project, --all, --cmd)

## Summary

Add the `extract` subcommand to `scripts/little_loops/cli/logs.py` (created in FEAT-1271). Implements `--project`, `--all`, and `--cmd` flags, and writes filtered JSONL to `logs/<project-slug>/<session-id>.jsonl`.

## Parent Issue
Decomposed from FEAT-1272: ll-logs: extract subcommand and logs/index.md generation

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
  little-loops/
    e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl
  my-other-project/
    ...
```

## Implementation Steps

1. **Add `extract` subcommand to `logs.py`**:
   - Add `extract` parser to existing `add_subparsers` with `--project`, `--all`, `--cmd` flags
   - Implement extraction logic:
     - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup; null-check: `if folder is None: print("Error: project not found"); return 1`
     - For `--all`: iterate using `discover_all_projects()` helper from FEAT-1271
     - Stream-parse JSONL directly (NOT `extract_user_messages()` — that returns `UserMessage` objects; raw dicts needed): `open(jsonl_file, encoding="utf-8")` → strip line → skip blank/JSONDecodeError → `json.loads(line)` (see `user_messages.py:437-450`); `OSError` caught at line 452
     - Detect ll-relevance via:
       - (a) `record.get("type") == "queue-operation" and record.get("operation") == "enqueue" and "/ll:" in record.get("content", "")`
       - (b) `type: "user"` records matching `re.compile(r"<command-name>/ll:[^<]+</command-name>")`
       - (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
     - Write filtered records to `logs/<project-slug>/<session-id>.jsonl` as `json.dumps(record) + "\n"` per line
     - `--cmd <tool>`: additional filter for specific ll- tool name in Bash tool-use blocks
   - Agent file exclusion: `[f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]`

2. **Multi-subcommand argparse pattern**: follow `scripts/little_loops/cli/history.py:35-281` — `add_subparsers(dest="command")`, root-level `add_config_arg(parser)`, `if not args.command: parser.print_help(); return 1`, dispatch chain returns `0`/`1`

3. **Logger setup**: `configure_output(config.cli)` then `logger = Logger(use_color=use_color_enabled())` (see `history.py:196-197`)

### Wiring Phase

4. Confirm `scripts/little_loops/cli/__init__.py` has `main_logs` import and `__all__` entry (FEAT-1271)
5. Confirm `scripts/pyproject.toml` has `ll-logs` entry point registered (FEAT-1271)
6. Add `TestExtract` to `scripts/tests/test_ll_logs.py`:
   - `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)` for single-project
   - `patch("pathlib.Path.home", return_value=tmp_path)` for multi-project
   - Use `_write_jsonl(path, records)` helper pattern from `test_user_messages.py:109` (instance method on `TestExtractUserMessages`)
   - Verify `logs/<slug>/<session>.jsonl` written correctly

_Wiring pass added by `/ll:wire-issue`:_

7. Add `class TestMainLogsIntegration` to `scripts/tests/test_cli.py` — integration tests following pattern at `scripts/tests/test_issue_history_cli.py:71-137`; add after `TestExtract` passes

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `extract` subcommand

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — imports `main_logs` (**handled by FEAT-1271**)
- `scripts/pyproject.toml:65-66` — registers `ll-logs` entry point (**handled by FEAT-1271**)

### Similar Patterns
- `scripts/little_loops/user_messages.py:383` — `extract_user_messages()` signature reference
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern
- `scripts/little_loops/cli/history.py:35-281` — canonical multi-subcommand template

### Tests
- `scripts/tests/test_ll_logs.py` — add `class TestExtract`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — add `class TestMainLogsIntegration` following pattern at `scripts/tests/test_issue_history_cli.py:71-137`; add after `TestExtract` passes [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:101-119` — CLI Tools section missing `ll-logs` entry (**FEAT-1006 scope**) [Agent 2 finding]
- `commands/help.md:216-233` — CLI TOOLS block missing `ll-logs` entry (**FEAT-1006 scope**) [Agent 2 finding]
- `skills/init/SKILL.md:428-446` — permissions allowlist missing `"Bash(ll-logs:*)"` (**FEAT-1006 scope**) [Agent 2 finding]
- `skills/configure/areas.md:823` — "All ll- commands" description/count missing `ll-logs` (**FEAT-1006 scope**) [Agent 2 finding]
- `docs/reference/CLI.md` — no `### ll-logs` section exists (**FEAT-1005 scope**) [Agent 2 finding]
- `README.md:90` — "16 CLI tools" count needs updating to 17 (**FEAT-1005 scope**) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/user_messages.py:671` — session ID in raw records is `record.get("sessionId", "")` — needed to derive output path `logs/<slug>/<session-id>.jsonl`; group records by session ID into a `dict[str, list[dict]]` before writing
- `scripts/little_loops/user_messages.py:436-454` — JSONL stream-parsing spans lines 436-454; the `except OSError: continue` wrapping the entire per-file block is at lines 452-454 — must be included, not just the inner JSON loop
- `scripts/little_loops/cli/messages.py:154-157` — "project not found" error uses `logger.error()` not `print()`: `logger.error(f"No Claude project folder found for: {cwd}")` + `logger.error(f"Expected: ~/.claude/projects/{str(cwd).replace('/', '-')}")` → return 1
- `scripts/little_loops/session_log.py:78` — agent-file exclusion filter (`[f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]`) confirmed in production use here; line 62 is the enclosing function definition start (`get_current_session_jsonl`)
- `discover_all_projects()` fallback: if FEAT-1271 does not expose this helper, use `(Path.home() / ".claude" / "projects").iterdir()` directly (pattern from FEAT-1272:60)
- `scripts/tests/test_user_messages.py:109-113` — `_write_jsonl` is an instance method on `TestExtractUserMessages` (starts at 109, not 103); `TestExtract` must define its own equivalent
- `scripts/tests/test_issue_history_cli.py:71-137` — pattern for `TestMainLogsIntegration` in `scripts/tests/test_cli.py` (FEAT-1272 wiring phase item 6 — add after `TestExtract` passes)
- `scripts/little_loops/doc_counts.py:258-261` — `setdefault` grouping idiom to use when bucketing raw records by `sessionId`: `buckets.setdefault(session_id, []).append(record)` — no equivalent helper exists; implement inline

#### `--project` flag: path vs slug semantics

`get_project_folder(cwd: Path | None = None)` takes a filesystem `Path`, not a slug string. The `<slug>` placeholder in the Expected Behavior section refers to the output directory name, not the flag value. Recommended implementation:

- `extract_parser.add_argument("--project", type=Path, help="Working directory of the target project (default: cwd)")`
- `cwd_path = args.project or Path.cwd()`
- `folder = get_project_folder(cwd_path)` → null-check with `logger.error()`
- Output slug: `cwd_path.resolve().name` (last path component, e.g. `little-loops`)
- Command: `ll-logs extract --project /Users/brennon/AIProjects/brenentech/little-loops`

This mirrors the `--cwd` pattern in `scripts/little_loops/cli/messages.py:75-157`.

## Acceptance Criteria

- [ ] `ll-logs extract --all` populates `logs/` with filtered JSONL entries
- [ ] `ll-logs extract --project <slug>` works for a specific project
- [ ] `ll-logs extract --cmd <tool>` filters by ll- tool name
- [ ] `TestExtract` test class passes

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small — extend existing module, ~50-70 LOC + tests
- **Risk**: Low — additive; no changes to existing code paths
- **Breaking Change**: No

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- **Blocking dependency unresolved**: FEAT-1271 (`logs.py` with `main_logs()` + argparse skeleton) is still `status: backlog`. `logs.py` does not exist — confirmed via filesystem check. FEAT-1273 adds the `extract` subcommand to that file and cannot begin until FEAT-1271 ships.
- **No test baseline**: `test_ll_logs.py` is created by FEAT-1271. Validate FEAT-1271 tests pass before writing `TestExtract`.

### Outcome Risk Factors
- **Test coverage gap**: No pre-existing coverage for `logs.py`; failures in edge cases won't surface until `TestExtract` is written. Issue specifies test patterns well — risk is execution discipline, not design.

---

## Session Log
- `/ll:refine-issue` - 2026-04-23T16:18:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07a47fb6-8632-4877-9913-24ec54282745.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b076981b-7d7b-4b64-a1a3-5ed38628c25c.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7c42afa-de19-4417-8d4e-005c53340f64.jsonl`
- `/ll:wire-issue` - 2026-04-23T16:12:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d97b518-78c3-49c4-8549-7ccd67634795.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:07:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1bc36a2-7234-434a-b02e-6f5019b6400b.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
