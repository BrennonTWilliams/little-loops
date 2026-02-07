# ENH-275: Document missing CLI tools and commands - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-275-document-missing-cli-tools-and-commands.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

Three documentation files are missing entries for recently-added tools, commands, and modules:

- **README.md** documents 5 of 10 CLI tools (missing `ll-sprint`, `ll-sync`, `ll-workflows`, `ll-verify-docs`, `ll-check-links`)
- **docs/COMMANDS.md** is missing 3 commands (`find_demo_repos`, `manage_release`, `tradeoff_review_issues`)
- **docs/API.md** Module Overview table has 19 modules, missing 3 (`frontmatter`, `doc_counts`, `link_checker`)

### Key Discoveries
- CLI tools are documented in README.md:393-479 with `### ll-<name>` + description + bash code block pattern
- Commands are in docs/COMMANDS.md with `### /ll:<name>` in detailed sections + rows in quick reference table
- API modules are in docs/API.md with `## little_loops.<name>` sections and a Module Overview table at lines 16-40
- All Python source for CLI tools and modules exists and has docstrings

## Desired End State

All 10 CLI tools documented in README.md, all commands documented in docs/COMMANDS.md, and all modules documented in docs/API.md.

### How to Verify
- `ll-verify-docs` passes (no count mismatches)
- All tests pass
- All linting passes

## What We're NOT Doing

- Not changing CLAUDE.md CLI tools list (already up to date)
- Not adding CONTRIBUTING.md entries (separate concern)
- Not documenting private functions in API.md (only public API)
- Not refactoring existing documentation

## Implementation Phases

### Phase 1: Update README.md with 5 missing CLI tools

#### Overview
Add `ll-sprint`, `ll-sync`, `ll-workflows`, `ll-verify-docs`, `ll-check-links` to the CLI Tools section.

#### Changes Required

**File**: `README.md`
**Insert after**: line 479 (end of `ll-history` section), before line 481 (`## Command Override`)

Add entries following the established pattern (H3 heading, one-line description, bash code block with aligned comments):

- `ll-sprint` — Sprint management (create, run, list, show, delete)
- `ll-sync` — Sync local issues with GitHub Issues (status, push, pull)
- `ll-workflows` — Workflow sequence analysis (step 2 of workflow analysis pipeline)
- `ll-verify-docs` — Verify documented counts match actual file counts
- `ll-check-links` — Check markdown docs for broken links

#### Success Criteria
- [ ] All 5 tools added with correct format matching existing entries
- [ ] Usage examples sourced from actual argparse epilog text

---

### Phase 2: Update docs/COMMANDS.md with 3 missing commands

#### Overview
Add `tradeoff_review_issues`, `find_demo_repos`, and `manage_release` to both detailed and quick reference sections.

#### Changes Required

**File**: `docs/COMMANDS.md`

1. **Detailed section**: Insert entries in their category sections:
   - `/ll:tradeoff_review_issues` → Issue Management section (after `/ll:iterate_plan`, line 114)
   - `/ll:find_demo_repos` → Auditing & Analysis section (after `/ll:analyze-workflows`, line 163)
   - `/ll:manage_release` → Git & Workflow section (after `/ll:cleanup_worktrees`, line 187)

2. **Quick reference table**: Add rows at appropriate positions:
   - `tradeoff_review_issues` after `iterate_plan` (line 266)
   - `find_demo_repos` after `analyze-workflows` (line 270)
   - `manage_release` after `cleanup_worktrees` (line 274)

#### Success Criteria
- [ ] All 3 commands in detailed section with correct format
- [ ] All 3 commands in quick reference table
- [ ] Descriptions match command file frontmatter

---

### Phase 3: Update docs/API.md with 3 missing modules

#### Overview
Add `frontmatter`, `doc_counts`, and `link_checker` modules to the Module Overview table and add individual module sections.

#### Changes Required

**File**: `docs/API.md`

1. **Module Overview table** (lines 16-40): Add 3 rows:
   - `little_loops.frontmatter` | YAML frontmatter parsing
   - `little_loops.doc_counts` | Documentation count verification
   - `little_loops.link_checker` | Link validation for markdown docs

2. **Individual module sections** (after line 3381, end of sprint section): Add `---` separated sections for each module following the summary documentation pattern (Public Functions table, Data Classes, Example).

#### Success Criteria
- [ ] 3 rows added to Module Overview table
- [ ] 3 module sections added with classes, functions, and examples
- [ ] Follows existing documentation conventions

---

## Testing Strategy

### Automated Verification
- `python -m pytest scripts/tests/` — all tests pass
- `ruff check scripts/` — linting passes
- `python -m mypy scripts/little_loops/` — type checking passes

### Manual Verification
- Documentation reads naturally and matches existing patterns
- All entries are accurate (descriptions match actual code behavior)

## References

- Issue: `.issues/enhancements/P3-ENH-275-document-missing-cli-tools-and-commands.md`
- CLI entry points: `scripts/pyproject.toml:47-56`
- CLI implementations: `scripts/little_loops/cli.py:1374` (sprint), `cli.py:2166` (sync), `cli.py:2308` (verify-docs), `cli.py:2398` (check-links)
- Workflow analyzer: `scripts/little_loops/workflow_sequence_analyzer.py:1-21`
- Command files: `commands/find_demo_repos.md`, `commands/manage_release.md`, `commands/tradeoff_review_issues.md`
- Python modules: `scripts/little_loops/frontmatter.py`, `scripts/little_loops/doc_counts.py`, `scripts/little_loops/link_checker.py`
