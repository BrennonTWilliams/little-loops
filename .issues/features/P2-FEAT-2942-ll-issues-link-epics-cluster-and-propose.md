---
id: FEAT-2942
title: "ll-issues link-epics: cluster orphan issues and propose EPIC assignment/synthesis"
type: FEAT
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
blocked_by:
- ENH-2941
relates_to:
- FEAT-2947
labels:
- cli
- issues
- epics
---

# FEAT-2942: `ll-issues link-epics` — cluster orphans and propose EPIC assignment/synthesis

## Summary

`skills/link-epics/SKILL.md` (362 lines) asks the LLM to *be* a numerical algorithm: hand-computed Jaccard scoring of every orphan × EPIC pair (L87–99, L133–138), HIGH/MEDIUM/LOW bucketing at 0.7/0.4 thresholds, tier-then-score sorting (L150), **union-find clustering** of unmatched orphans (L215–225), frequency-ranked title synthesis and modal-priority selection (L242–253), and both-direction frontmatter wiring with post-write re-read checks (L173–188, L282–324). Move all of it into a CLI; the LLM keeps only naming/validating synthesized EPICs.

## Current Behavior

The skill's prose Jaccard has already diverged from `text_utils.py` (documented in-file at L100–105). Every run pays ~340 lines of algorithm-as-instructions, and clustering correctness depends on the model executing union-find faithfully.

## Expected Behavior

`ll-issues link-epics --mode assign|synthesize [--threshold N] [--apply] --json`:

- **assign**: score orphans against existing EPICs, emit ranked proposals `{orphan, epic, score, tier}`. Proposals only; `--apply` writes `parent:` + `## Children` via existing wiring code.
- **synthesize**: union-find cluster unmatched orphans on pairwise similarity; emit clusters with member lists, modal priority, and a frequency-derived *placeholder* title.
- `/ll:link-epics` skill **delegates to** this CLI (map-dependencies-style) — the two do not coexist as independent implementations. Skill's remaining LLM work: name/validate synthesized EPICs, sanity-check odd cluster members, then apply via the CLI/`ll-issues link`.

## Proposed Solution

Build on ENH-2941's consolidated similarity (`text_utils.py`). Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes, `issue_parser.find_issues` for corpus.

**Soft dep on FEAT-2947 — do not implement EPIC creation here.** Synthesize mode emits *cluster proposals*, not EPIC files; the actual creation call is `ll-issues create --type EPIC` (FEAT-2947). If FEAT-2947 has not landed, synthesize mode still ships proposal-only and the skill creates the EPIC as it does today. Two independent ID-allocation/templating implementations is exactly the duplication this epic exists to remove.

**Naming/output collision note**: `ll-issues clusters` already exists and visualizes *dependency-edge* clusters. This subcommand scores *text-similarity* clusters — keep the name `link-epics`, and make `--json` output shapes clearly distinct (documented in help text).

## Implementation Steps

1. assign mode (scoring + proposals + `--apply`).
2. synthesize mode (union-find + placeholder titles).
3. Rewrite `skills/link-epics/SKILL.md` to delegate (~362 → well under 100 lines).
4. Tests: fixture corpus with known clusters; threshold/tier boundaries; `--apply` writes both directions and is idempotent.

## Use Case

A maintainer with dozens of orphan issues runs `ll-issues link-epics --mode assign --json`, reviews ranked orphan→EPIC proposals, applies the good ones with `--apply`, then runs `--mode synthesize` to get clustered candidates for new EPICs — supplying only the final EPIC names themselves.

## Program Design

### Types

- `EpicProposal: dataclass` — `orphan_id: str`, `epic_id: str`, `score: float`, `tier: Literal["HIGH", "MEDIUM", "LOW"]`
- `ClusterProposal: dataclass` — `member_ids: list[str]`, `placeholder_title: str`, `modal_priority: str`, `pairwise_min_score: float`

### Signatures

- `propose_assignments(orphans: list[IssueInfo], epics: list[IssueInfo], threshold: float) -> list[EpicProposal]`
- `synthesize_clusters(orphans: list[IssueInfo], min_score: float) -> list[ClusterProposal]` — union-find over pairwise `calculate_word_overlap`
- `apply_assignment(proposal: EpicProposal) -> None` — via `frontmatter.update_frontmatter` + EPIC `## Children` append

### Call Path

- `propose_assignments()` -> `find_issues()` (existing) -> `calculate_word_overlap()` (existing, `text_utils.py`)
- `apply_assignment()` -> `update_frontmatter()` (existing, `frontmatter.py`)

## Impact

- **Priority**: P2 - Removes the worst algorithm-as-prose offender (~340 lines) and its documented divergence
- **Effort**: Medium - Two modes; assign/synthesize independently shippable
- **Risk**: Low-Medium - Proposals-only default; writes gated behind `--apply`

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] Both modes emit deterministic JSON proposals; no writes without `--apply`
- [ ] `skills/link-epics/SKILL.md` contains no scoring/clustering algorithm prose
- [ ] Similarity comes solely from `text_utils.py` (no local stop-word list)
- [ ] Help text distinguishes this from `ll-issues clusters`
- [ ] No ID allocation, slugging, or EPIC-file templating in this subcommand — creation is delegated to `ll-issues create` (FEAT-2947) or left to the skill
- [ ] pytest coverage in `scripts/tests/`

## Notes

assign and synthesize are independently shippable — split into two issues if the union-find + synthesis half exceeds ~a day.
