---
id: ENH-2941
title: "Similarity foundation: consolidate Jaccard into text_utils and add ll-issues find-similar + batch fingerprint compare"
type: ENH
priority: P1
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
blocks:
- FEAT-2942
labels:
- cli
- issues
- similarity
- drift
---

# ENH-2941: Similarity foundation — `ll-issues find-similar` on a single Jaccard implementation

## Summary

Word-overlap similarity is specified in prose in at least three places — `skills/link-epics/SKILL.md` L87–99, `skills/capture-issue/SKILL.md` L195–200, and `commands/normalize-issues.md`'s confidence formula — while `scripts/little_loops/text_utils.py` (`extract_words` L131, `calculate_word_overlap` L148) is the canonical implementation. link-epics L100–105 explicitly documents that the prose and Python stop-word lists have already diverged. Consolidate onto `text_utils.py` and expose it as `ll-issues find-similar`.

## Current Behavior

- capture-issue Phase 2 (L165–231) asks the LLM to run an awk status filter, extract 3+-char words minus a stop-word list, and hand-compute `intersection / union` against every open issue.
- No CLI exists for "which existing issues resemble this text": `ll-issues search` is filter/sort (substring/field matching), `ll-issues fingerprint` is single-file extraction with no comparison mode.

## Expected Behavior

- `ll-issues find-similar "<title or text>" [--against open|all] [--threshold 0.4] [--limit N] --json` → ranked candidates `{id, title, path, score}`.
- `ll-issues find-similar --batch [--threshold] --json` → pairwise similarity over the corpus (fills the "no batch fingerprint similarity" gap; input for dedup/conflict tooling).
- `skills/capture-issue/SKILL.md` Phase 2 dedup becomes one CLI call; LLM keeps conversation mining, drafting, and the accept/merge decision on returned candidates.
- Distinction from `ll-issues search` stated in `--help` and docs: `search` filters/sorts by fields and substrings; `find-similar` scores fuzzy text similarity. They may share `issue_parser.find_issues` plumbing but have different contracts.

## Proposed Solution

Thin CLI over `text_utils.extract_words`/`calculate_word_overlap` + `issue_parser.find_issues` (include done/cancelled under `--against all`). Ensure `ll-issues fingerprint` output is reusable here; add `--json` to fingerprint if missing. Thresholds default from config where `capture-issue` currently reads them.

## Implementation Steps

1. Add `find_similar` module under `scripts/little_loops/cli/issues/`; wire subparser + alias.
2. Single-text mode, then `--batch` pairwise mode.
3. Slim `skills/capture-issue/SKILL.md` Phase 2 (~65 lines of prose → one call).
4. Update the normalize-issues confidence prose reference (full conversion lands in ENH-2944; here just stop restating the formula).
5. Tests: known-similar/dissimilar fixture pairs, threshold behavior, `--batch` output shape, stop-word source is `text_utils` only.

## Program Design

### Types

- `SimilarityMatch: dataclass` — `id: str`, `title: str`, `path: str`, `score: float`
- `SimilarityPair: dataclass` — `a: str`, `b: str`, `score: float` (batch mode)

### Signatures

- `find_similar(text: str, against: Literal["open", "all"], threshold: float, limit: int, issues_dir: Path) -> list[SimilarityMatch]` — built on `text_utils.extract_words` / `calculate_word_overlap` + `issue_parser.find_issues`
- `batch_similarity(threshold: float, issues_dir: Path) -> list[SimilarityPair]`
- Subparser wiring in `scripts/little_loops/cli/issues/__init__.py` (`find-similar`, alias `fs`)

### Call Path

- `find_similar()` -> `find_issues()` (existing, `issue_parser.py`) -> `extract_words()` -> `calculate_word_overlap()` (existing, `text_utils.py`)

## Scope Boundaries

- In scope: the two similarity modes, `--json` output, capture-issue Phase 2 slimming, removing prose Jaccard/stop-word restatements.
- Out of scope: clustering or EPIC proposal logic (FEAT-2942), embedding/FTS-based similarity, normalize-issues' full conversion (ENH-2944).

## Impact

- **Priority**: P1 - Foundation child; FEAT-2942 hard-blocks on it and ENH-2944 soft-depends
- **Effort**: Small - Thin CLI over existing `text_utils` + `issue_parser`
- **Risk**: Low - Pure read/score; deterministic outputs

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [ ] `ll-issues find-similar` returns ranked JSON candidates; deterministic for fixed input
- [ ] No skill/command markdown restates the Jaccard formula or a stop-word list
- [ ] capture-issue's dedup phase is a single CLI invocation
- [ ] Issue body distinction vs `ll-issues search` documented in help text
- [ ] pytest coverage in `scripts/tests/`

## Notes

If `--batch` starts growing clustering features, stop — clustering belongs to FEAT-2942.
