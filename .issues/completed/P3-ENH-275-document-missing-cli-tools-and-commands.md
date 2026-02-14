---
discovered_commit: 59ef770
discovered_branch: main
discovered_date: 2026-02-07T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-275: Document missing CLI tools and commands across docs

## Summary

Documentation issue found by `/ll:audit-docs`. Several CLI tools and slash commands exist in the codebase but are not documented.

## Missing CLI Tools

The following CLI tools are registered in `scripts/pyproject.toml` under `[project.scripts]` but missing from README.md CLI Tools section:

| Tool | Entry Point | Status |
|------|-------------|--------|
| `ll-sprint` | `little_loops.cli:main_sprint` | Undocumented in README |
| `ll-sync` | `little_loops.cli:main_sync` | Undocumented in README |
| `ll-workflows` | `little_loops.workflow_sequence_analyzer:main` | Undocumented in README |
| `ll-verify-docs` | `little_loops.cli:main_verify_docs` | Undocumented in README |
| `ll-check-links` | `little_loops.cli:main_check_links` | Undocumented in README |

## Missing Commands from docs/COMMANDS.md

The following command files exist in `commands/` but are not listed in `docs/COMMANDS.md`:

| Command | File |
|---------|------|
| `/ll:find_demo_repos` | `commands/find_demo_repos.md` |
| `/ll:manage-release` | `commands/manage_release.md` |
| `/ll:tradeoff-review-issues` | `commands/tradeoff_review_issues.md` |

## Missing API Modules from docs/API.md

| Module | Purpose |
|--------|---------|
| `little_loops.frontmatter` | YAML frontmatter parsing |
| `little_loops.doc_counts` | Documentation count verification |
| `little_loops.link_checker` | Link validation |

## Files to Update

1. **README.md** — Add CLI tool sections for `ll-sprint`, `ll-sync`, `ll-workflows`, `ll-verify-docs`, `ll-check-links`
2. **docs/COMMANDS.md** — Add entries for `find_demo_repos`, `manage_release`, `tradeoff_review_issues` in both detailed and quick reference sections
3. **docs/API.md** — Add module entries for `frontmatter`, `doc_counts`, `link_checker`

## Impact

- **Severity**: Medium (users cannot discover available tools through docs)
- **Effort**: Medium
- **Risk**: Low

## Labels

`enhancement`, `documentation`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `README.md`: Added CLI tool documentation for `ll-sprint`, `ll-sync`, `ll-workflows`, `ll-verify-docs`, `ll-check-links`
- `docs/COMMANDS.md`: Added detailed + quick reference entries for `find_demo_repos`, `manage_release`, `tradeoff_review_issues`
- `docs/API.md`: Added Module Overview rows and full documentation sections for `frontmatter`, `doc_counts`, `link_checker`

### Verification Results
- Tests: PASS (2619 passed)
- Lint: PASS (pre-existing test file issues only)
- Types: PASS
