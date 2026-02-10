---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-318: README missing config properties and 3 undocumented sections

## Summary

Documentation issue found by `/ll:audit_docs`. Several config properties are missing from existing README tables, and three entire config sections defined in `config-schema.json` have no README documentation.

## Missing Properties in Existing Tables

### `project` table (line 219-231)

- `test_dir` (default: `"tests"`) - Test directory path

### `issues` table (line 233-256)

- `capture_template` (enum: `"full"` / `"minimal"`, default: `"full"`) - Default template style for captured issues
- `duplicate_detection` object with:
  - `exact_threshold` (default: 0.8) - Jaccard similarity threshold for exact duplicates
  - `similar_threshold` (default: 0.5) - Jaccard similarity threshold for similar issues

## Undocumented Config Sections

### `workflow`

Phase gates, deep research, and plan template settings:
- `phase_gates.enabled` (default: true)
- `phase_gates.auto_mode_skip` (default: true)
- `deep_research.enabled` (default: true)
- `deep_research.quick_flag_skips` (default: true)
- `deep_research.agents` (default: 3 sub-agents)
- `plan_template.sections_recommended` (default: true)
- `plan_template.sections_mandatory` (default: false)

### `prompt_optimization`

Automatic prompt optimization settings (toggle with `/ll:toggle_autoprompt`):
- `enabled` (default: true)
- `mode` (enum: quick/thorough, default: "quick")
- `confirm` (default: true)
- `bypass_prefix` (default: "*")
- `clarity_threshold` (default: 6)

### `continuation`

Session continuation and handoff settings (documented in SESSION_HANDOFF.md but not README):
- `enabled` (default: true)
- `auto_detect_on_session_start` (default: true)
- `include_todos` / `include_git_status` / `include_recent_files` (default: true)
- `max_continuations` (default: 3)
- `prompt_expiry_hours` (default: 24)

## Context

ENH-314 (completed 2026-02-10) explicitly listed these as "out of scope" when adding `sync`, `sprints`, and `documents` sections. This issue covers the remaining gap.

## Impact

- **Severity**: Low (features work without docs, but discoverability suffers)
- **Effort**: Medium (3 new section tables + property additions)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P3
