---
id: ENH-2944
title: "ll-issues normalize: filename/ID mechanics out of normalize-issues.md"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2941
- ENH-2953
labels:
- cli
- issues
- normalization
---

# ENH-2944: `ll-issues normalize` — filename/ID mechanics

## Summary

`commands/normalize-issues.md` (511 lines — the largest file in EPIC-2938's scope) is dominated by rename/ID bookkeeping the LLM executes by hand. Convert to an `ll-issues` subcommand; the LLM keeps only semantic type-classification review.

**Descoped after review** (2026-07-31): `prioritize --apply` split to **ENH-2953**. It is thin (233 lines, one judgment step) and was being gated behind the meatiest conversion in the epic for no reason. The two share a `git mv` rename helper — whichever lands first owns it.

## Current Behavior

**normalize-issues**: legacy-dir checks (L80–107), per-basename ID regex scans (L117–131), ID→file map + `sort | uniq -d` duplicate detection written to `.loops/tmp/` (L137–154), `ll-issues next-id` + keep-oldest-duplicate rules + slug generation (L215–246), three fixed report tables (L251–289), `git mv` loops (L293–312). Even "type misclassification" (L158–202) is a keyword→type lookup with a `(signals_for_top_type)/(total_signals+1)` confidence formula and a 0.7 cutoff — a Python function, not judgment.

## Expected Behavior

`ll-issues normalize [--check] [--auto] --json` — detects missing/duplicate/malformed IDs, legacy dirs, bad slugs; `--auto` applies renames via `git mv`; `--check` is a deterministic exit-code gate (EPIC convention: no LLM-narrated exits). Keyword-count type classification included; optionally cross-references ENH-2941's `find-similar --batch` for content-duplicate flagging (may land as a follow-up flag).

## Proposed Solution

Reuse `issue_parser` (`find_issues`, `slugify`, `get_next_issue_number`, `is_normalized`) and `frontmatter.py`. Duplicate-keep rule (oldest by git history, else alphabetical) implemented via `git log --follow` or file mtime fallback. Factor the `git mv` rename into a shared helper — ENH-2953 needs the same one.

## Implementation Steps

1. `normalize` detection + `--check`; then `--auto` apply path.
2. Slim `commands/normalize-issues.md` (511 → ~80), keeping semantic type-classification review as the LLM step.
3. Tests: fixture tree with missing/dup/malformed IDs; check-mode exit codes; apply idempotency.

## Program Design

### Types

- `NormalizeFinding: dataclass`
  - `path: Path`
  - `kind: str`  (missing_id | duplicate_id | malformed_id | legacy_dir | bad_slug | type_mismatch)
  - `proposed_path: Path | None`
  - `confidence: float | None`

### Signatures

- `scan_normalize(issues_dir: Path) -> list[NormalizeFinding]` — via `issue_parser.find_issues`, `is_normalized`, `slugify`
- `apply_normalize(findings: list[NormalizeFinding]) -> None` — `git mv`, ID allocation via `get_next_issue_number`
- `classify_type(issue: IssueInfo) -> tuple[str, float]` — keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence

### Call Path

- `scan_normalize()` -> `find_issues()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `apply_normalize()` -> `get_next_issue_number()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: the `normalize` subcommand (`--check`/`--auto`), slimming `commands/normalize-issues.md`, the deterministic exit-code gate, and the shared `git mv` rename helper.
- Out of scope: semantic (LLM) type reclassification, content-duplicate merging (flagging only, via ENH-2941 follow-up), `prioritize` (ENH-2953), changing the P0–P5 taxonomy.

## Impact

- **Priority**: P2 - Converts the largest single file in scope (511 lines) and fixes a narrated exit-code gate
- **Effort**: Medium - normalize is meaty
- **Risk**: Low-Medium - Renames via `git mv` with `--check` preview; collision-safe ID allocation tested

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues normalize --check` exit code is the FSM-usable gate (0 clean / 1 violations)
- [ ] `--auto` renames preserve git history (`git mv`) and never allocate colliding IDs
- [ ] `commands/normalize-issues.md` contains no glob/regex/table-rendering instructions
- [ ] The `git mv` rename helper is shared with (or shareable by) ENH-2953
- [ ] pytest coverage in `scripts/tests/`

## Notes

`prioritize` was split to ENH-2953 so it ships without waiting on this issue's classification heuristics.
