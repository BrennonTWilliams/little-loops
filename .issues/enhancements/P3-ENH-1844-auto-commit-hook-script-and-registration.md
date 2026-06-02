---
id: ENH-1844
title: Auto-commit hook script (issue-auto-commit.sh) and PostToolUse registration
type: ENH
priority: P3
status: done
parent: ENH-1717
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1844: Auto-commit hook script (issue-auto-commit.sh) and PostToolUse registration

## Summary

Implement `hooks/scripts/issue-auto-commit.sh` and register it in `hooks/hooks.json` as a `PostToolUse` hook matching `Write` and `Edit` events. The script auto-commits issue file changes when `issues.auto_commit` is enabled, with a working-tree guard that skips the commit if other staged/unstaged changes are present.

## Parent Issue

Decomposed from ENH-1717: Auto-commit hooks on Issue file CRUD operations

## Integration Map

### Files to Modify / Created
- `hooks/scripts/issue-auto-commit.sh` — new script (main bash implementation)
- `hooks/hooks.json` — two `PostToolUse` matcher entries added (separate `Write` and `Edit` entries; actual structure uses `{ matcher, hooks: [{ type: "command", command, timeout, statusMessage }] }` nesting)
- `scripts/little_loops/hooks/post_tool_use.py` — `_maybe_auto_commit()` (line 93) — Python in-process counterpart; called from `handle()` (line 205) when `tool_name in {"Write", "Edit"}`; mirrors bash logic exactly with `contextlib.suppress(Exception)` for silent failure

### Shared Utilities
- `hooks/scripts/lib/common.sh` — `ll_resolve_config()` (line 184), `ll_feature_enabled()` (line 198), `ll_config_value()` (line 218) — shared by bash hook
- `scripts/little_loops/config/features.py` — `IssuesConfig.auto_commit: bool = False`, `auto_commit_prefix: str = "chore(issues)"` (lines 204–205); `feature_enabled()` (line 14) is the Python port of `ll_feature_enabled`

### Template / Reference (Not Modified)
- `hooks/scripts/issue-completion-log.sh` — eight-guard chain template: `jq` check → tool name → file path → `.md` extension → `ll_resolve_config` → `ISSUES_BASE_DIR` → path scope → filename pattern
- `hooks/scripts/check-duplicate-issue-id-post.sh` — existing `PostToolUse` hook in the same hooks.json array

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/adapters/codex/hooks.json` — Codex CLI PostToolUse hook routes to the same Python dispatcher; `_maybe_auto_commit()` fires via this path too [Agent 1 finding]
- `hooks/adapters/codex/post-tool-use.sh` — Codex bash shim sets `LL_HOOK_HOST=codex` and calls `python -m little_loops.hooks post_tool_use` [Agent 1 finding]
- `hooks/adapters/opencode/index.ts` — OpenCode `tool.execute.after` event calls `spawnIntent("post_tool_use")` fire-and-forget; auto-commit fires through this path [Agent 1 finding]

### Tests
- `scripts/tests/test_hooks_integration.py` — `TestIssueAutoCommitHook` class (lines 2248–2527); subprocess-level tests covering: non-issue file, disabled, clean-tree commit, custom prefix, dirty-tree guard, Edit verb
- `scripts/tests/test_hook_post_tool_use.py` — `TestIssueAutoCommitPostToolUse` class (lines 444–509); unit tests Python `_maybe_auto_commit()` with `monkeypatch.setattr` subprocess mocking

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — `TestIssuesConfig.test_from_dict_with_defaults()`, `test_from_dict_with_auto_commit()` cover `IssuesConfig.auto_commit`/`auto_commit_prefix` defaults; `TestBRConfigRoundTrip.test_issues_auto_commit_round_trip_to_dict/override()` cover `BRConfig.to_dict()` round-trip [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — `TestConfigSchema.test_issues_auto_commit_in_schema()` asserts schema presence, type (`boolean`), and default (`false`) for both new keys [Agent 3 finding]
- `scripts/tests/test_hook_intents.py` — `TestDispatchIntents.test_dispatch_post_tool_use_happy_path()` covers the full subprocess dispatch path from CLI entry point through `post_tool_use.handle()` [Agent 3 finding]

**Test gap**: No test asserts that `hooks/hooks.json` contains `PostToolUse` entries pointing at `issue-auto-commit.sh` for both `Write` and `Edit` matchers. Pattern exists in `test_codex_adapter.py::TestHooksJson` to follow.

### Documentation
- `docs/ARCHITECTURE.md` — auto-commit feature documented at line 1099
- `docs/reference/CONFIGURATION.md` — `issues.auto_commit` and `issues.auto_commit_prefix` at lines 43, 280
- `config-schema.json` — schema entries at lines 240–249

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — `## Auto-commit on save` paragraph documents the feature, config key, prefix override, and dirty-tree skip behavior [Agent 2 finding]
- `hooks/adapters/codex/README.md` — documents `post_tool_use` as fire-and-forget handler including auto-commit at lines 34–35, 77–96 [Agent 2 finding]

## Prerequisites

Requires ENH-1843 (config layer) to land first so `ll_feature_enabled "issues.auto_commit"` resolves correctly.

## Proposed Solution

### hooks/scripts/issue-auto-commit.sh (new file)

Use `hooks/scripts/issue-completion-log.sh` as the template for:
- stdin JSON parsing (`FILE_PATH` extraction)
- `ll_resolve_config` / `ISSUES_BASE_DIR` scoping
- Filename-pattern guard (`^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}`)
- Exit codes (0 = success/skip, non-zero = error)

Additional logic:
1. Call `ll_feature_enabled "issues.auto_commit"` — exit 0 if disabled
2. Read `auto_commit_prefix` from config (default `"chore(issues)"`)
3. Run `git add "$FILE_PATH"` (idempotent)
4. Guard: `git status --porcelain | grep -v "^[AM]  <escaped-path>" | grep -c .` — if count > 0, print warning and exit 0 (skip commit, don't block)
5. Derive commit verb from operation type (Write=`capture`/`update`, Edit=`update`) and issue ID from filename
6. Run `git commit -m "<prefix>: <verb> <ISSUE-ID> <slug>"`

Commit message format follows `issue_lifecycle.py:_commit_issue_completion()` at line 311.

### hooks/hooks.json

Add new entry to `PostToolUse` array (after `check-duplicate-issue-id-post.sh`):

```json
{
  "type": "PostToolUse",
  "matcher": "Write",
  "command": "bash hooks/scripts/issue-auto-commit.sh",
  "timeout": 5000,
  "statusMessage": "Auto-committing issue file..."
}
```

Also register a second entry for `"matcher": "Edit"`.

## Implementation Steps

1. Create `hooks/scripts/issue-auto-commit.sh` following `issue-completion-log.sh` structure
2. Add commit message generation (verb from tool type, ID from filename)
3. Add working-tree guard using `git status --porcelain`
4. Register two entries in `hooks/hooks.json` (one for Write, one for Edit)
5. Add `TestIssueAutoCommitHook` class to `test_hooks_integration.py`
6. Add `TestIssueAutoCommitPostToolUse` class to `test_hook_post_tool_use.py`

## Acceptance Criteria

- [ ] `auto_commit: false` (default) — hook exits 0 without running git
- [ ] Non-issue file path — hook exits 0 immediately
- [ ] `auto_commit: true`, clean working tree — `git add` + `git commit` run with correct message
- [ ] `auto_commit: true`, dirty working tree — hook skips commit and prints warning
- [ ] Custom `auto_commit_prefix` appears in commit message
- [ ] `capture-issue`'s subsequent `git add` after the hook becomes a harmless no-op

## Tests

- `scripts/tests/test_hook_post_tool_use.py` — add `TestIssueAutoCommitPostToolUse` class following `TestFileEventsWrite` pattern; gate-off test patches subprocess commit and asserts 0 calls when `issues.auto_commit: false`
- `scripts/tests/test_hooks_integration.py` — add `TestIssueAutoCommitHook` class following `TestIssueCompletionLog` pattern (subprocess.run with JSON stdin + tmp_path git repo); cover: non-issue file exit 0, disabled exits 0 without git, enabled runs `git add` + `git commit`, custom prefix, dirty-tree guard

## Similar Patterns

- `hooks/scripts/issue-completion-log.sh` — full path-scoping and filename-pattern guard pattern
- `hooks/scripts/check-duplicate-issue-id-post.sh` — another PostToolUse Write hook in same array
- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()` at line 311 — commit message format (note: stages `git add -A` and uses `(type)` scope in prefix; structurally different from the hook's single-file staging and flat prefix)
- `scripts/little_loops/git_operations.py` — `check_git_status()` at line 161 — working-tree guard pattern
- `scripts/little_loops/hooks/post_tool_use.py` — `_maybe_auto_commit()` at line 93 — Python in-process counterpart; identical verb derivation, commit format, and working-tree guard; `contextlib.suppress(Exception)` for silent failure
- `hooks/scripts/lib/common.sh` — `ll_feature_enabled()` at line 198, `ll_resolve_config()` at line 184, `ll_config_value()` at line 218 — shared bash utilities sourced by the script

## Session Log
- `/ll:refine-issue` - 2026-06-01T08:51:49 - `670784ff-d4f0-40c6-9a7b-020bd45b719d.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
- `/ll:wire-issue` - 2026-06-01T00:00:00Z - `current.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `a7a962c9-d8d6-406a-b38f-3c88d907de2b.jsonl`
