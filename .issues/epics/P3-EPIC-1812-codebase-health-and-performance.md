---
id: EPIC-1812
title: Codebase Health & Performance
type: EPIC
priority: P3
status: open
discovered_date: 2026-05-30
discovered_by: link-epics
relates_to: [ENH-972, ENH-974, ENH-975, ENH-976, ENH-839]
---

# EPIC-1812: Codebase Health & Performance

## Summary

Five targeted performance and code-quality improvements to the little-loops Python codebase:
fix an O(n) list.pop(0) in BFS clustering, deduplicate code-fence stripping logic spread across
three modules, eliminate a double-scan in IssueParser.parse_file, precompile regex patterns in
detect_manual_patterns, and split the monolithic layout.py diagram renderer into focused modules.

## Motivation

These issues were all discovered by codebase scanning and represent real but non-urgent
inefficiencies. Each is small enough to implement independently, but together they form
a coherent "tighten the screws" pass that reduces technical debt and improves performance
for large issue graphs and session logs.

## Goal

When this epic is done:
- BFS clustering uses collections.deque for O(1) popleft
- Code-fence stripping lives in a single shared utility module
- IssueParser.parse_file makes one pass over content instead of two
- detect_manual_patterns uses module-level precompiled regex
- layout.py is split into focused modules by diagram type

## Scope

### In scope

- ENH-972: Replace `list.pop(0)` with `collections.deque.popleft` in `_build_coupling_clusters`
- ENH-974: Extract shared code-fence stripping into a single utility function
- ENH-975: Refactor `IssueParser.parse_file` to single-pass content scanning
- ENH-976: Precompile regex patterns at module level in detect_manual_patterns
- ENH-839: Split `layout.py` diagram rendering into focused modules

### Out of scope

- New features or behavior changes
- Broader architectural refactoring beyond the five targets
- Performance benchmarking infrastructure (use existing tests as regression guard)

## Children

- **ENH-972** — BFS queue uses O(n) `list.pop(0)` in `_build_coupling_clusters`
- **ENH-974** — Code-fence stripping logic duplicated across 3 modules
- **ENH-975** — `IssueParser.parse_file` double-scans content for session log data
- **ENH-976** — `detect_manual_patterns` recompiles regex patterns on each call
- **ENH-839** — Split layout.py diagram rendering into focused modules

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — Child issues with missing `status:` frontmatter:
- ENH-972, ENH-974, ENH-975, ENH-976, ENH-839: all verified as open (bugs confirmed present in code) ✓
- However, these issues may be missing `status:` in their frontmatter — run `/ll:normalize-issues` to fix
- Core claims are accurate (O(n) pop, duplicated regex, double scan all confirmed by code inspection) ✓

## Session Log
- `/ll:verify-issues` - 2026-06-01T03:08:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
