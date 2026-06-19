# Wire-Issue: Phase 9.5 — Extract Learning Targets (ENH-2209)

Loaded by `/ll:wire-issue` after Phase 9 (session log). Runs before Phase 10 (output report).

## When to Skip

Skip if `testable: false` in issue frontmatter or `--dry-run` is set.

## Procedure

### 1. Identify External Dependencies

Analyze the full issue text (frontmatter + body) to identify all third-party packages, SDKs, and external API surfaces the implementation plan assumes behavior of.

Include:
- Third-party Python packages (e.g. `anthropic`, `requests`, `boto3`, `stripe`)
- External APIs and cloud services (e.g. Stripe webhooks, GitHub API)
- SDKs for external platforms
- Non-obvious stdlib components whose contract is non-trivial (e.g. `asyncio`, `multiprocessing`)

Exclude:
- Project-internal code
- Standard Python builtins (`str`, `dict`, `list`, `int`, etc.)
- Contract-stable stdlib (`os`, `sys`, `pathlib`, `json`, `re`, `datetime`)

Produce a deduplicated list of short target names (e.g. `["anthropic", "requests", "stripe"]`).

### 2. Check Registry for Each Target

```bash
ll-learning-tests check --stale-aware "<target>"
```

- Exit 0 → proven and fresh (count toward M proven)
- Exit 1 → missing, stale, or refuted (count toward K unproven)

This uses the stale-aware gate from `scripts/little_loops/learning_tests/gate.py` (ENH-2208) — do **not** use `ll-learning-tests check` without `--stale-aware`, which would bypass the staleness threshold.

### 3. Write Frontmatter with Union-Merge

If at least one target was found:

1. Read the current `learning_tests_required` value from the issue file's YAML frontmatter (may be absent, a list, or a scalar string).
2. Build merged list: `existing_targets ∪ new_targets` — preserve existing entries, append new ones, deduplicate by order of first appearance.
3. Update the issue file: set `learning_tests_required: <merged_list>` in frontmatter using the `update_frontmatter` utility from `little_loops.frontmatter`.

If **no targets** were found, do **not** write `learning_tests_required: []` — omit the field entirely (or leave the existing value unchanged if it was already set).

### 4. Emit Summary

Output one of these summary lines before the Phase 10 report:

| Situation | Summary line |
|-----------|-------------|
| Targets found | `Learning targets: Found N external dependencies — M proven, K unproven. Added to learning_tests_required.` |
| Targets found, all proven, field already correct | `Learning targets: All N proven — learning_tests_required unchanged.` |
| No targets found | `Learning targets: None detected — learning_tests_required field omitted.` |

## Implementation Note

The extraction logic is also available as a callable Python module at
`scripts/little_loops/learning_tests/extractor.py` (`extract_learning_targets(issue_text)`),
which ENH-2210 imports directly for sprint pre-flight. Within this skill, Claude
performs the equivalent analysis inline from the issue text already in context.
