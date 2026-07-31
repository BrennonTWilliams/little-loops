---
id: ENH-2944
title: "ll-issues normalize and prioritize --apply: filename/ID mechanics out of markdown"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2941
labels:
- cli
- issues
- normalization
---

# ENH-2944: `ll-issues normalize` + `prioritize --apply` — filename/ID mechanics

## Summary

`commands/normalize-issues.md` (511 lines — the largest file in EPIC-2938's scope) and `commands/prioritize-issues.md` (233 lines) are dominated by rename/ID bookkeeping the LLM executes by hand. Convert to `ll-issues` subcommands; the LLM keeps only per-issue priority judgment.

## Current Behavior

- **normalize-issues**: legacy-dir checks (L80–107), per-basename ID regex scans (L117–131), ID→file map + `sort | uniq -d` duplicate detection written to `.loops/tmp/` (L137–154), `ll-issues next-id` + keep-oldest-duplicate rules + slug generation (L215–246), three fixed report tables (L251–289), `git mv` loops (L293–312). Even "type misclassification" (L158–202) is a keyword→type lookup with a `(signals_for_top_type)/(total_signals+1)` confidence formula and a 0.7 cutoff — a Python function, not judgment.
- **prioritize-issues**: glob + `^P[0-5]-` regex discovery (L54–67), scripted control-flow gates (L69–83), `git mv` renames (L108–112, L169–173), fixed report tables (L118–139, L177–209), narrated check-mode exit codes (L48–50). Only Step 2 (L145–165) — assigning P0–P5 from impact/severity/effort — is genuine judgment. Notably it uses no `ll-issues` at all today.

## Expected Behavior

- `ll-issues normalize [--check] [--auto] --json` — detects missing/duplicate/malformed IDs, legacy dirs, bad slugs; `--auto` applies renames via `git mv`; `--check` is a deterministic exit-code gate (EPIC convention: no LLM-narrated exits). Keyword-count type classification included; optionally cross-references ENH-2941's `find-similar --batch` for content-duplicate flagging (may land as a follow-up flag).
- `ll-issues prioritize [--apply ID=P2,ID2=P1,...] --json` — lists unprioritized issues (discovery + report), applies renames for a supplied ID→priority map. `/ll:prioritize-issues` shrinks to: read the JSON list, judge priorities, call `--apply`.

## Proposed Solution

Reuse `issue_parser` (`find_issues`, `slugify`, `get_next_issue_number`, `is_normalized`), `frontmatter.py`, and the `--apply k=v` syntax style of `ll-issues set-scores`. Duplicate-keep rule (oldest by git history, else alphabetical) implemented via `git log --follow` or file mtime fallback.

## Implementation Steps

1. `normalize` detection + `--check`; then `--auto` apply path.
2. `prioritize` list + `--apply`.
3. Slim both command files (511 → ~80; 233 → ~60), keeping semantic type-classification review and priority judgment as the LLM steps.
4. Tests: fixture tree with missing/dup/malformed IDs; check-mode exit codes; apply idempotency.

## Program Design

### Types

- `NormalizeFinding: dataclass`
  - `path: Path`
  - `kind: str`  (missing_id | duplicate_id | malformed_id | legacy_dir | bad_slug | type_mismatch)
  - `proposed_path: Path | None`
  - `confidence: float | None`
- `PrioritizeEntry: dataclass`
  - `id: str`
  - `path: Path`
  - `current_priority: str | None`

### Signatures

- `scan_normalize(issues_dir: Path) -> list[NormalizeFinding]` — via `issue_parser.find_issues`, `is_normalized`, `slugify`
- `apply_normalize(findings: list[NormalizeFinding]) -> None` — `git mv`, ID allocation via `get_next_issue_number`
- `classify_type(issue: IssueInfo) -> tuple[str, float]` — keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence
- `apply_priorities(mapping: dict[str, str]) -> list[Path]` — `--apply ID=P2,...` parsing per `set-scores` style

### Call Path

- `scan_normalize()` -> `find_issues()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `apply_normalize()` -> `get_next_issue_number()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: `normalize` (`--check`/`--auto`) and `prioritize` (`--apply`) subcommands; slimming both command files; deterministic exit-code gates.
- Out of scope: semantic (LLM) type reclassification, content-duplicate merging (flagging only, via ENH-2941 follow-up), changing the P0–P5 taxonomy.

## Impact

- **Priority**: P2 - Converts the largest single file in scope (511 lines) and fixes narrated exit-code gates
- **Effort**: Medium - normalize is meaty; prioritize is thin
- **Risk**: Low-Medium - Renames via `git mv` with `--check` preview; collision-safe ID allocation tested

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues normalize --check` exit code is the FSM-usable gate (0 clean / 1 violations)
- [ ] `--auto` renames preserve git history (`git mv`) and never allocate colliding IDs
- [ ] `ll-issues prioritize --apply` performs all renames; LLM supplies only the map
- [ ] Both command files contain no glob/regex/table-rendering instructions
- [ ] pytest coverage in `scripts/tests/`

## Notes

normalize alone is meaty; split prioritize out if the classification heuristics need iteration.
