---
discovered_commit: 5d6419bad2fa3174b9f2c4062ef912bba5205e1a
discovered_branch: main
discovered_date: 2026-02-25
discovered_by: audit-architecture
focus_area: organization
confidence_score: 92
outcome_confidence: 88
---

# ENH-507: Add `__all__` exports to 20 public root-level modules

## Summary

Architectural issue found by `/ll:audit-architecture`. 20 of the 24 root-level modules in `scripts/little_loops/` are missing `__all__` definitions, leaving their public API implicit and undeclared.

## Current Behavior

20 of 24 root-level modules in `scripts/little_loops/` are missing `__all__` definitions. Only 4 modules currently declare `__all__`: `config.py`, `cli_args.py`, `user_messages.py`, and `workflow_sequence_analyzer.py`. Without `__all__`, star imports (`from module import *`) leak internal helpers and names imported from other modules, and IDEs/type checkers have no explicit public API boundary to work with.

## Expected Behavior

All 24 root-level `.py` modules in `scripts/little_loops/` define `__all__` listing only their intended public exports — non-underscore-prefixed names defined in that module, excluding names re-exported from other modules. After the change, `from little_loops.module import *` imports only the declared public API.

## Motivation

Without `__all__`, the public API of each module is implicit and undeclared:
- **IDE tooling**: Auto-complete surfaces private helpers alongside public API
- **Type checking**: mypy and pyright produce less accurate public boundary results
- **Star import semantics**: `from module import *` leaks internal names and re-exported names
- **Documentation**: No machine-readable signal for what is intended as public API

## Location

- **Files**: `scripts/little_loops/*.py` (20 modules)
- **Module**: `little_loops.*`

## Finding

### Current State

Only 4 of 24 root-level modules define `__all__`:
- `config.py` ✓
- `cli_args.py` ✓
- `user_messages.py` ✓
- `workflow_sequence_analyzer.py` ✓

**Missing `__all__`** (20 modules):

```
dependency_graph.py
doc_counts.py
frontmatter.py
git_operations.py
goals_parser.py
issue_lifecycle.py
issue_manager.py
issue_parser.py
issue_template.py
link_checker.py
logger.py
logo.py
output_parsing.py
session_log.py
sprint.py
state.py
subprocess_utils.py
sync.py
text_utils.py
work_verification.py
```

Note: `dependency_mapper` is a package directory, not a `.py` file — excluded from scope.

Without `__all__`, `from little_loops.module import *` (used in some test helpers and `__init__.py` re-exports) imports every name including private helpers and imported names from other modules. IDE auto-complete and type checkers also produce less accurate results.

### Impact

- **IDE tooling**: Auto-complete shows private helpers alongside public API
- **Type checking**: `mypy` and `pyright` report less precise public API boundaries
- **`import *` semantics**: Without `__all__`, star imports leak internal names
- **Documentation**: No machine-readable signal for what's intended as public API

## Proposed Solution

Add `__all__` to each module listing only its intended public exports.

### Suggested Approach

1. For each of the 20 modules listed below, add `__all__ = [...]` after the module docstring and imports
2. Exclude:
   - Private helpers (`_prefixed`)
   - Names imported from other modules (unless intentionally re-exported via `noqa: F401`)
   - Implementation-only dataclasses used only internally

### Public Names Per Module (Enumerated)

Researched 2026-03-06 by reading each module. Names are non-underscore-prefixed and defined in that module, except where noted as intentional re-exports.

```python
# dependency_graph.py
__all__ = ["WaveContentionNote", "DependencyGraph", "refine_waves_for_contention"]

# doc_counts.py
__all__ = [
    "DOC_FILES", "COUNT_TARGETS",
    "CountResult", "VerificationResult", "FixResult",
    "count_files", "extract_count_from_line", "verify_documentation",
    "format_result_text", "format_result_json", "format_result_markdown", "fix_counts",
]

# frontmatter.py
__all__ = ["parse_frontmatter", "strip_frontmatter"]

# git_operations.py
# Note: EXCLUDED_DIRECTORIES, filter_excluded_files, verify_work_was_done are imported
# from work_verification with `noqa: F401` — they are intentional re-exports.
__all__ = [
    "COMMON_GITIGNORE_PATTERNS", "GitignorePattern", "GitignoreSuggestion",
    "check_git_status", "get_untracked_files", "suggest_gitignore_patterns",
    "add_patterns_to_gitignore",
    # intentional re-exports from work_verification:
    "EXCLUDED_DIRECTORIES", "filter_excluded_files", "verify_work_was_done",
]

# goals_parser.py
__all__ = ["Persona", "Priority", "ProductGoals", "validate_goals"]

# issue_lifecycle.py
__all__ = [
    "FailureType", "classify_failure",
    "verify_issue_completed", "create_issue_from_failure",
    "close_issue", "complete_issue_lifecycle",
    "defer_issue", "undefer_issue",
]

# issue_manager.py
__all__ = [
    "timed_phase", "run_claude_command", "run_with_continuation",
    "detect_plan_creation", "check_content_markers",
    "IssueProcessingResult", "process_issue_inplace", "AutoManager",
]

# issue_parser.py
__all__ = [
    "ISSUE_ID_PATTERN",
    "is_normalized", "is_formatted", "slugify", "get_next_issue_number",
    "ProductImpact", "IssueInfo", "IssueParser",
    "find_issues", "find_highest_priority_issue",
]

# issue_template.py
__all__ = ["load_issue_sections", "assemble_issue_markdown"]

# link_checker.py
__all__ = [
    "MARKDOWN_LINK_PATTERN", "BARE_URL_PATTERN",
    "DEFAULT_IGNORE_PATTERNS", "DEFAULT_DOC_FILES",
    "LinkResult", "LinkCheckResult",
    "extract_links_from_markdown", "is_internal_reference",
    "should_ignore_url", "check_url", "check_markdown_links",
    "load_ignore_patterns",
    "format_result_text", "format_result_json", "format_result_markdown",
]

# logger.py
__all__ = ["Logger", "format_duration"]

# logo.py
__all__ = ["get_logo", "print_logo"]

# output_parsing.py
__all__ = [
    "SECTION_PATTERN", "TABLE_ROW_PATTERN", "STATUS_PATTERN", "VALID_VERDICTS",
    "parse_sections", "parse_validation_table", "parse_status_lines",
    "parse_ready_issue_output", "parse_manage_issue_output",
]

# session_log.py
__all__ = [
    "parse_session_log", "count_session_commands",
    "get_current_session_jsonl", "append_session_log_entry",
]

# sprint.py
__all__ = ["SprintOptions", "SprintState", "Sprint", "SprintManager"]

# state.py
__all__ = ["ProcessingState", "StateManager"]

# subprocess_utils.py
__all__ = [
    "OutputCallback", "ProcessCallback",
    "CONTEXT_HANDOFF_PATTERN", "CONTINUATION_PROMPT_PATH",
    "detect_context_handoff", "read_continuation_prompt", "run_claude_command",
]

# sync.py
__all__ = ["SyncedIssue", "SyncResult", "SyncStatus", "GitHubSyncManager"]

# text_utils.py
__all__ = [
    "SOURCE_EXTENSIONS",
    "extract_file_paths", "extract_words", "calculate_word_overlap", "score_bm25",
]

# work_verification.py
__all__ = ["EXCLUDED_DIRECTORIES", "filter_excluded_files", "verify_work_was_done"]
```

## Scope Boundaries

- **In scope**: Adding `__all__` to the 20 root-level modules in `scripts/little_loops/*.py` listed in `## Finding`
- **Out of scope**: Sub-packages (`fsm/`, `cli/`, `parallel/`); changing existing module structure or behavior; modifying public API

## Integration Map

### Files to Modify
- 20 modules in `scripts/little_loops/`: `dependency_graph.py`, `doc_counts.py`, `frontmatter.py`, `git_operations.py`, `goals_parser.py`, `issue_lifecycle.py`, `issue_manager.py`, `issue_parser.py`, `issue_template.py`, `link_checker.py`, `logger.py`, `logo.py`, `output_parsing.py`, `session_log.py`, `sprint.py`, `state.py`, `subprocess_utils.py`, `sync.py`, `text_utils.py`, `work_verification.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/__init__.py` — uses named imports only (no star imports); already defines its own `__all__`. Adding `__all__` to individual modules does not affect this file's behavior.

### Star Import Consumer Analysis (Researched 2026-03-06)
- **`from little_loops.X import *`**: Zero occurrences found across the entire `scripts/` tree. No consumer of star imports exists.
- **`from little_loops import *`**: Zero occurrences found anywhere in the repository.
- **Conclusion**: Adding `__all__` is purely a documentation and tooling hygiene improvement. There are no existing star-import consumers whose behavior would change.

### Similar Patterns
- 4 modules already define `__all__`: `config.py`, `cli_args.py`, `user_messages.py`, `workflow_sequence_analyzer.py`

### Tests
- N/A — additive change; no existing tests should break

### Documentation
- N/A

### Configuration
- N/A

## Success Criteria

The implementation is complete when ALL of the following are true:

1. **Coverage**: `grep -r "^__all__" scripts/little_loops/*.py` returns exactly 24 matches (all root-level `.py` files including the 4 that already have `__all__`).
2. **Content correct**: Each of the 20 modules lists the public names enumerated in the "Public Names Per Module" table above (no underscore-prefixed names, no silently leaked imports).
3. **Tests pass**: `python -m pytest scripts/tests/` exits 0 — no regressions introduced.
4. **Mypy clean**: `python -m mypy scripts/little_loops/` reports no new errors related to `__all__`.
5. **No behavior change**: `from little_loops.X import *` in a test shell resolves only the declared names (verifiable via `dir()` on the module after star import).

## Implementation Steps

1. Add `__all__ = [...]` to each of the 20 modules using the names enumerated in "Proposed Solution" above — no further research needed.
2. For `git_operations.py`: include the three intentional re-exports from `work_verification` (marked with `noqa: F401`) in its `__all__`.
3. Run `python -m pytest scripts/tests/` and `python -m mypy scripts/little_loops/` to confirm no regressions.
4. Verify coverage with `grep -c "^__all__" scripts/little_loops/*.py | grep -v ":0"` — should show 24 files.

## Impact

- **Priority**: P5 — Low severity; additive change with no behavior impact
- **Effort**: Small — Text editing only across 20 files
- **Risk**: Low — Additive change, no behavior change
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | Module public API reference — `little_loops.*` root modules listed (line 45) |

## Labels

`enhancement`, `architecture`, `auto-generated`

---

## Tradeoff Review Note

**Reviewed**: 2026-02-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | LOW |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Clean hygiene improvement but LOW utility for a CLI/plugin project where star imports and IDE auto-complete accuracy are not pressing concerns. Blocked by FEAT-488. Consider batching with other cleanup work when the blocker resolves rather than tracking as a standalone priority.

## Refinement Notes

- **2026-03-06** — `/ll:refine-issue --auto` cycle 2: Researched all 20 modules by reading source files. Enumerated exact `__all__` contents for every module in Proposed Solution. Confirmed zero `from little_loops.X import *` or `from little_loops import *` consumers anywhere in the repo — adding `__all__` has no behavioral impact on existing callers. Added explicit, machine-verifiable Success Criteria section (grep count, pytest, mypy, dir() check). Updated Integration Map with star-import consumer analysis. Re-scored: confidence_score=92 (was 81, +11 from enumerating public names and explicit criteria), outcome_confidence=88 (was 73, +15 from measurable success criteria and confirmed zero star-import consumers).

- **2026-03-06** — `/ll:refine-issue --auto` cycle 1: Fixed "19 modules" in Suggested Approach step 1 (was inconsistent with "20 modules" stated throughout rest of document). Flagged knowledge gap: the "Blocked By: FEAT-488" dependency is spurious — adding `__all__` to modules is a pure text-editing task with no logical dependency on the `--idle-timeout` CLI flag (FEAT-488). The blocker was likely set by workflow convention rather than technical dependency. The FEAT-488 → ENH-507 relationship in FEAT-488's "Blocks" section is also questionable. Implementer should confirm whether the block is intentional (e.g., batch-in-same-PR preference) or can be removed. No additional knowledge gaps found; implementation path is clear and self-contained. Re-scored: confidence_score=81, outcome_confidence=73 (above 70 threshold).

## Verification Notes

- **2026-03-05** — VALID. 20 modules in `scripts/little_loops/` still missing `__all__`; only `config.py`, `cli_args.py`, `user_messages.py`, `workflow_sequence_analyzer.py` have it. Module list unchanged from prior audit.
- **2026-03-06** — VALID. Counts confirmed: 25 total `.py` files, 5 with `__all__` (including `__init__.py`, excluded from scope as package init), 20 without. Title corrected from "19" to "20" to match body text.

## Session Log
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is comprehensive with full list of 19 modules needing __all__; no knowledge gaps identified
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by FEAT-488
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `docs/reference/API.md` (line 45) to Related Key Documentation
- `/ll:verify-issues` - 2026-03-03 - Corrected module list: removed `dependency_mapper.py` (it's a package), added `issue_template.py`, `output_parsing.py`, `text_utils.py` (which does NOT have `__all__`). Count updated from 19→20 missing, 5→4 with `__all__`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:verify-issues` - 2026-03-06T07:14:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7a87dd5-a8d5-4b8f-9271-78a1114bf527.jsonl` — Title corrected 19→20 to match body counts
- `/ll:refine-issue` - 2026-03-06 - cycle 2: Read all 20 modules, enumerated exact __all__ lists, confirmed zero star-import consumers, added explicit Success Criteria; re-scored confidence_score=92, outcome_confidence=88
- `/ll:refine-issue` - 2026-03-06 - Fixed "19 modules" inconsistency in Suggested Approach; flagged spurious FEAT-488 blocker dependency; re-scored confidence_score=81, outcome_confidence=73 (now above 70 threshold)
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: 20 modules still missing __all__

## Status

**Open** | Created: 2026-02-25 | Priority: P5

## Blocked By

- FEAT-488
