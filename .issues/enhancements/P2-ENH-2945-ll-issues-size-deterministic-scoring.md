---
id: ENH-2945
title: "ll-issues size: deterministic size scoring for issue-size-review"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- FEAT-2947
labels:
- cli
- issues
- sizing
---

# ENH-2945: `ll-issues size <id> --json` — deterministic size scoring

## Summary

`skills/issue-size-review/SKILL.md` (466 lines) Phases 1–3 are a fully countable scoring rubric the LLM computes by hand; Phase 6 is ID/file scaffolding. Move both into `ll-issues size`; the skill keeps Phases 4–5 (split-decision judgment).

## Current Behavior

- Phase 1 (L82–110): glob type dirs / resolve sprint IDs via `ll-issues path`.
- Phase 2 (L114–126): the scoring table — +2 file-path count patterns, +2 sections >300 words, +3 multiple `##` subsections, +2 cross-issue references, +2 >800 words total; max 11.
- Phase 3 (L128–174): score→label mapping (0–2 Small … 8+ Very Large), `Edit` of `size:` frontmatter, `git add`.
- Phase 6 (L272–330): `next-id`, filename templating, session-log JSONL hunting (L282–289), parent `status: done`, staging.

## Expected Behavior

`ll-issues size <id|--all|--sprint NAME> [--write] --json` — computes the Phase 2 signals and total, maps to the label, emits `{id, score, label, signals:{...}}`; `--write` stamps `size:` frontmatter. The skill becomes: run CLI → for Large/Very Large, do Phase 4 (sub-task identification, independently-shippable test, never-split-by-artifact-type and TDD-wiring rules, sequential-vs-parallel judgment) and Phase 5 → child creation via FEAT-2947's `create`/`finalize-decomposition` once available (session-log via `ll-issues append-log`, per ENH-2939).

## Proposed Solution

Word/section/reference counting over `issue_parser.parse_file` output; label table as data. `--write` via `frontmatter.update_frontmatter`. Keep the signal weights in one place (module constant) so `issue-size-review --auto` (used by autodev's guard2 path) and the CLI can't diverge.

**Ordering (soft dep on FEAT-2947)**: Phase 6's child-creation mechanics can only be deleted once `ll-issues create` exists. Land FEAT-2947 first within Wave 2; if this issue ships earlier, scope it to Phases 1–3 only and leave Phase 6's slimming to a follow-up rather than half-converting it.

## Implementation Steps

1. Implement scoring + label mapping + `--write`.
2. Slim `skills/issue-size-review/SKILL.md` Phases 1–3 and the mechanical parts of Phase 6.
3. Tests: fixture issues hitting each signal and each label boundary; `--write` idempotency.

## Program Design

### Types

- `SizeScore: dataclass`
  - `id: str`
  - `score: int`
  - `label: str`  (Small | Medium | Large | Very Large)
  - `signals: dict[str, int]`
- `SIZE_SIGNAL_WEIGHTS: dict[str, int]` — module constant, single source for skill + CLI

### Signatures

- `compute_size(issue: IssueInfo, body: str) -> SizeScore` — file-path counts, >300-word sections, `##` subsection count, cross-issue refs, >800-word total
- `label_for(score: int) -> str` — 0–2 Small / 3–4 Medium / 5–7 Large / 8+ Very Large
- `write_size(issue_path: Path, score: SizeScore) -> None` — `frontmatter.update_frontmatter`

### Call Path

- `compute_size()` -> `find_issues()` (existing, `issue_parser.py`)
- `write_size()` -> `update_frontmatter()` (existing, `frontmatter.py`)

## Scope Boundaries

- In scope: scoring/label/`--write` subcommand; slimming Phases 1–3 and mechanical Phase 6 steps of issue-size-review.
- Out of scope: Phase 4–5 split judgment (stays LLM), child-issue creation (FEAT-2947), autodev routing changes that consume the score.

## Impact

- **Priority**: P2 - Feeds autodev's guard2/size-review path with a deterministic score instead of hand-counted signals
- **Effort**: Small - Countable signals over parsed issues
- **Risk**: Low - Read-only by default; `--write` stamps one frontmatter key

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues size --json` reproduces the skill's scoring table exactly (fixtures at boundaries 2/3, 7/8)
- [ ] Skill retains only Phase 4–5 judgment + child-creation orchestration
- [ ] No JSONL session-log hunting remains in the skill
- [ ] Phase 6's ID/filename templating is either deleted in favor of `ll-issues create` (FEAT-2947 landed) or explicitly deferred — never left half-converted
- [ ] pytest coverage in `scripts/tests/`
