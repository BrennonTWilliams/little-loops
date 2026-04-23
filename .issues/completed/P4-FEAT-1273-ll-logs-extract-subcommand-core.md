---
id: FEAT-1273
type: FEAT
priority: P4
status: backlog
title: "ll-logs: extract subcommand core (--project, --all, --cmd)"
discovered_date: 2026-04-23
discovered_by: issue-size-review
completed_at: 2026-04-23T21:26:55Z
decision_needed: false
parent_issue: FEAT-1272
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
size: Very Large
---

# FEAT-1273: ll-logs: extract subcommand core (--project, --all, --cmd)

## Summary

Add the `extract` subcommand to `scripts/little_loops/cli/logs.py` (created in FEAT-1271). Implements `--project`, `--all`, and `--cmd` flags, and writes filtered JSONL to `logs/<project-slug>/<session-id>.jsonl`.

## Use Case

**Who**: Developer using the `ll-logs` CLI after automation runs

**Context**: After `ll-sprint` or `ll-auto` executes a set of issues, they want to review which ll- commands were invoked during implementation — for debugging, metrics, or audit purposes.

**Goal**: Extract filtered JSONL session records for a specific project (or all projects) into a structured directory, optionally filtered to a specific ll- tool name.

**Outcome**: Populated `logs/<project-slug>/<session-id>.jsonl` files containing only ll-relevant records, ready for downstream analysis by `ll-workflows` or `ll-history`.

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

## Motivation

The `extract` subcommand enables structured log retrieval for ll- command activity:
- **Auditability**: Currently no way to extract filtered ll- command records from Claude Code session files into a queryable format; this closes that gap for automation runs (`ll-auto`, `ll-sprint`, `ll-parallel`)
- **Foundation for downstream tools**: Provides the data layer consumed by `ll-workflows` (pattern detection) and `ll-history` (topic-filtered analysis)
- **Decomposed scope**: Extracted from FEAT-1272 specifically to keep the extract logic independently testable and shippable

## Implementation Steps

1. **Add `extract` subcommand to `logs.py`**:
   - **Extend `_is_ll_relevant()` (`logs.py:23`) with type (c)** — add assistant Bash tool_use detection (see Codebase Research Findings below for exact code). Do this first; `discover` will also benefit.
   - Add `extract` parser to `_build_parser()` (`logs.py:150`) with `--project`/`--all` as a required mutually-exclusive group and `--cmd` as an optional filter; also update the epilog to include extract examples.
   - Implement `_cmd_extract()`:
     - For `--project`: call `get_project_folder(cwd_path)` (already imported from `user_messages`); use `logger.error()` on None (see `messages.py:154-157`)
     - For `--all`: call `discover_all_projects(logger)` (`logs.py:81`) — returns decoded absolute paths; convert each to its project folder via `get_project_folder(path)`
     - JSONL scanning loop: mirror `_has_ll_activity()` (`logs.py:58-78`) — `glob("*.jsonl")` → skip `agent-*` → open/stream → `json.loads` → `_is_ll_relevant()` → `OSError: continue`
     - Group records by `record.get("sessionId", "")` using `buckets.setdefault(session_id, []).append(record)` (no helper; implement inline)
     - Apply `--cmd` secondary filter if set: keep only records where the Bash tool_use input contains the cmd string
     - Write each session bucket to `Path.cwd() / "logs" / slug / f"{session_id}.jsonl"` as `json.dumps(record) + "\n"` per line; `slug = cwd_path.resolve().name`

2. **Multi-subcommand argparse pattern**: follow `scripts/little_loops/cli/history.py:35-281` — `add_subparsers(dest="command")`, root-level `add_config_arg(parser)`, `if not args.command: parser.print_help(); return 1`, dispatch chain returns `0`/`1`

3. **Logger setup**: `configure_output(config.cli)` then `logger = Logger(use_color=use_color_enabled())` (see `history.py:196-197`)

### Wiring Phase

4. Confirm `scripts/little_loops/cli/__init__.py` has `main_logs` import and `__all__` entry (FEAT-1271)
5. Confirm `scripts/pyproject.toml` has `ll-logs` entry point registered (FEAT-1271)
6. Add `TestExtract` to `scripts/tests/test_ll_logs.py`:
   - Define `_make_project_dir(self, claude_projects, home, subpath, records)` following `TestDiscover._make_project_dir()` (`test_ll_logs.py:33-64`) — same signature and structure
   - Patch `Path.cwd()` to a tmpdir so `Path.cwd() / "logs" / slug / session.jsonl` is resolvable
   - `patch("pathlib.Path.home", return_value=home)` for multi-project (`--all`)
   - Verify `(tmpdir / "logs" / slug / f"{session_id}.jsonl")` exists with correct JSONL lines after `main_logs()` returns 0

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
- `discover_all_projects()` — **now exists at `logs.py:81`** (FEAT-1271 shipped); call directly, no fallback needed. Signature: `discover_all_projects(logger: Logger) -> list[Path]` (returns decoded absolute paths, not claude project dirs).
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

#### Post-FEAT-1271 state: what `logs.py` already provides

_Added by `/ll:refine-issue` (second pass) — reflects current `logs.py` state:_

- **`_is_ll_relevant(record)` at `logs.py:23`** — already implements types (a) and (b). For type (c) (assistant Bash tool-use with ll- commands), **extend this function** rather than re-implementing detection inline. Type (c) structure from `user_messages.py:573-594`:
  ```python
  if record_type == "assistant":
      message = record.get("message", {})
      content = message.get("content", [])
      if isinstance(content, list):
          for block in content:
              if (isinstance(block, dict)
                      and block.get("type") == "tool_use"
                      and block.get("name") == "Bash"):
                  cmd = block.get("input", {}).get("command", "")
                  if re.search(r'\bll-\w+', cmd):
                      return True
  ```
  Adding type (c) to `_is_ll_relevant()` also improves `discover` (projects where the assistant ran ll- tools will now be surfaced).

- **`_has_ll_activity()` at `logs.py:58-78`** — demonstrates the exact per-project JSONL scanning pattern extract needs. Extract's inner loop should mirror this: `glob("*.jsonl")` → skip `agent-*` → open/stream → strip/skip-blank → `json.loads` → catch `json.JSONDecodeError` → call `_is_ll_relevant()` → catch `OSError: continue` at file level.

- **`--cmd` filter helper**: After collecting ll-relevant records, apply a secondary filter. Implement inline or as `_cmd_matches(record: dict, cmd: str) -> bool` — check Bash tool_use blocks: `block["input"]["command"]` contains the tool name (e.g. `"ll-history"` in `"ll-history --project ..."`). Use `cmd in block.get("input", {}).get("command", "")`.

- **`--project` / `--all` mutual exclusion**: Use `argparse.add_mutually_exclusive_group(required=True)` on the extract subparser so exactly one of `--project` or `--all` is required:
  ```python
  group = extract_parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--project", type=Path, ...)
  group.add_argument("--all", action="store_true", ...)
  ```

- **Output directory anchoring**: No `logs_dir` config key exists in `BRConfig`. Output `logs/<slug>/<session-id>.jsonl` is relative to `Path.cwd()` at call time. Use `out_dir = Path.cwd() / "logs" / slug` for both `--project` and each project in `--all`.

- **`_build_parser()` epilog** (`logs.py:155-161`) — currently only shows `discover` and `tail` examples. Add:
  ```
  %(prog)s extract --all             # Extract all projects to logs/
  %(prog)s extract --project /path  # Extract one project to logs/<slug>/
  %(prog)s extract --all --cmd ll-history  # Filter to ll-history invocations
  ```

- **TestExtract setup**: `TestDiscover._make_project_dir()` (`test_ll_logs.py:33-64`) is the closest helper pattern. `TestExtract` should define its own `_make_project_dir()` (same signature) and additionally patch `Path.cwd()` to a tmpdir so output files go to `<tmpdir>/logs/<slug>/`. Verify `(tmpdir / "logs" / slug / session_id).with_suffix(".jsonl")` exists with correct JSONL content.

## Acceptance Criteria

- [x] `ll-logs extract --all` populates `logs/` with filtered JSONL entries
- [x] `ll-logs extract --project <slug>` works for a specific project
- [x] `ll-logs extract --cmd <tool>` filters by ll- tool name
- [x] `TestExtract` test class passes

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

## Labels

`cli`, `feature`, `backlog`

---

## Session Log
- `/ll:ready-issue` - 2026-04-23T21:17:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20acc632-e912-4343-bd87-3aa34c666161.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2ac7f45-a691-4f7e-820a-9a5dce6ec5b2.jsonl`
- `/ll:refine-issue` - 2026-04-23T21:12:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3202701a-3983-4304-a685-f583cfb8bd22.jsonl`
- `/ll:format-issue` - 2026-04-23T21:03:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e421608d-71ec-42e1-8580-6044c8db9f3a.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:18:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07a47fb6-8632-4877-9913-24ec54282745.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b076981b-7d7b-4b64-a1a3-5ed38628c25c.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7c42afa-de19-4417-8d4e-005c53340f64.jsonl`
- `/ll:wire-issue` - 2026-04-23T16:12:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d97b518-78c3-49c4-8549-7ccd67634795.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:07:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1bc36a2-7234-434a-b02e-6f5019b6400b.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Resolution

Implemented `extract` subcommand in `scripts/little_loops/cli/logs.py`:
- Extended `_is_ll_relevant()` with type (c): assistant Bash tool-use calling `ll-` commands
- Added `_cmd_matches()` helper for `--cmd` secondary filter
- Added `_cmd_extract()` implementing `--project`/`--all` scanning and JSONL output
- Added `extract` subparser with mutually-exclusive `--project`/`--all` group and optional `--cmd`
- Added `TestIsLlRelevantAssistantBash` (4 tests) and `TestExtract` (6 tests) to `test_ll_logs.py`
- All 26 tests in `test_ll_logs.py` pass; no regressions in full suite

## Status

**Completed** | Created: 2026-04-23 | Completed: 2026-04-23 | Priority: P4
