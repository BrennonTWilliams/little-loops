---
id: ENH-2979
title: '--deep flag: LLM-adjudicated clustering for link-epics synthesize mode'
type: ENH
priority: P4
status: open
captured_at: '2026-08-01T21:03:45Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
parent: EPIC-2938
blocked_by:
- FEAT-2942
---

# ENH-2979: --deep flag: LLM-adjudicated clustering for link-epics synthesize mode

## Summary

`/ll:link-epics --mode synthesize` clusters orphaned issues using plain Jaccard
word-overlap on title+summary text (`skills/link-epics/SKILL.md` Step 3, S1). This
structurally misses thematically-related issues that don't share vocabulary. Add a
`--deep` flag that swaps in an LLM-adjudicated clustering pass instead, pre-filtered
by the existing Jaccard scoring to bound the candidate set sent to the model.

## Current Behavior

`--mode synthesize` computes pairwise Jaccard scores over 3+ char alphabetic tokens
(minus a small stop-word list) from each orphan's title+summary, then union-finds
pairs at or above `MIN_SCORE` (default `0.3`) into clusters. Word-overlap-only
scoring has no stemming, no synonym/embedding awareness, and weights all words
equally — two issues about the same underlying theme phrased with different
vocabulary (e.g. "predicate" vs. "heuristic") score 0 unless they happen to reuse
words verbatim.

Validated live this session: running `/ll:link-epics --mode synthesize` against 11
real orphaned open issues produced a maximum pairwise Jaccard score of 0.06 (between
ENH-2967 and ENH-2971) — far under the 0.3 default threshold — so every orphan fell
out as a singleton despite several being plausibly related in intent (e.g. issues
about heuristic/predicate duplication across autodev.yaml and refine-issue).

## Expected Behavior

A `--deep` flag on `--mode synthesize` clusters orphans by thematic/semantic
relatedness rather than raw vocabulary overlap, while staying inspectable (grounded
in cited evidence) and bounded in cost.

## Motivation

The synthesize mode's whole purpose is to surface EPIC-worthy groupings a human
hasn't noticed yet. A purely lexical similarity metric can only find groupings that
already reuse the same words — exactly the case a human skimming titles would
already catch. The mode is least useful precisely where it's most needed: small,
jargon-heavy engineering backlogs where related issues are phrased independently.

## Proposed Solution

Design agreed with user (this session):

- Keep the existing Jaccard pass (Step 3 / S1 in `skills/link-epics/SKILL.md`) as a
  cheap pre-filter to bound the candidate list — do **not** have the LLM score all
  O(n²) pairs directly; that doesn't scale with orphan count.
- `--deep` sends the pre-filtered candidate list (or, if pre-filtering yields
  nothing, the full orphan list when count is small enough) to an LLM in **one
  batched call** — not one call per pair — to propose thematic clusters.
- The LLM step must **cite which words/phrases** in the issues' titles/summaries
  justify grouping them together — an evidence-contract requirement in the same
  spirit as MR-8's evidence-contract check for FSM `check_semantic` prompts
  (`.claude/CLAUDE.md` § Loop Authoring), applied here to skill prose instead of FSM
  YAML — so clustering output stays inspectable rather than an ungrounded judgment
  call the user can't verify.
- This is a flag on the existing `link-epics` skill (`mode: synthesize`), **not a
  new skill** — same operation, different scoring backend for the clustering step,
  matching the existing `mode: assign` / `mode: synthesize` precedent for branching
  behavior via flags rather than new skill files.
- Default behavior (no `--deep`) is unchanged: pure Jaccard threshold clustering
  exactly as it works today.

## Integration Map

### Files to Modify
- `skills/link-epics/SKILL.md` — add `--deep` flag parsing (Step 1), a batched LLM
  clustering sub-step under S1, and evidence-citation requirements in the S2/S3
  proposal flow.

### Dependent Files (Callers/Importers)
- N/A — `link-epics` is a leaf skill invoked directly via `/ll:link-epics`; no
  other skill or loop shells out to it programmatically.

### Similar Patterns
- `.claude/CLAUDE.md` § Loop Authoring MR-8 (evidence-contract keyword check for
  FSM `check_semantic` prompts) — apply the same "cite verbatim evidence" principle
  to the new LLM clustering prompt, even though MR-8 itself only lints FSM YAML
  (see `reference_mr8_evidence_contract_scope` memory) and won't enforce this
  automatically.

### Tests
- No existing test file covers `link-epics` end-to-end (it's a prose skill, not a
  CLI); manual verification via `/ll:link-epics --mode synthesize --deep` against a
  backlog with known thematically-related-but-lexically-distinct orphans.

### Documentation
- `skills/link-epics/SKILL.md` — usage examples section needs a `--deep` entry.

### Configuration
- N/A

## Implementation Steps

1. Add `--deep` flag parsing to Step 1 alongside `--auto`/`--min-score`.
2. In S1, after Jaccard pre-filtering, add a batched LLM call (one call for the
   whole candidate set, not per-pair) that proposes clusters and cites the
   title/summary evidence for each grouping.
3. Merge LLM-proposed clusters with any Jaccard-only clusters (dedupe by member
   overlap) before S2 title/summary synthesis.
4. Extend S3's proposal presentation to show the cited evidence alongside each
   `--deep`-sourced cluster so the user can verify the grouping.
5. Add a `--deep` usage example and update the mode-choosing guidance at the
   bottom of `SKILL.md`.

## Scope Boundaries

- Not in scope: changing `--mode assign`'s existing-EPIC scoring (Step A2) — this
  issue is scoped to the synthesize-mode clustering step (S1) only.
- Not in scope: replacing Jaccard scoring wholesale or removing the non-`--deep`
  path — `--deep` is strictly additive.
- Not in scope: embeddings/vector-store-based similarity — that's a heavier
  infrastructure lift (model calls per issue + a vector store) than a flag on an
  existing skill; considered and rejected in favor of a batched LLM clustering call
  during design discussion.

## Impact

- **Priority**: P4 - Quality-of-life improvement to an existing skill; no user is
  currently blocked, but `--mode synthesize` is close to a no-op on backlogs like
  this project's current one (11/11 orphans landed as singletons).
- **Effort**: Small - Additive flag on an existing skill's existing mode; reuses
  the current orphan-discovery and Jaccard pre-filter machinery (Step 2, Step 3),
  adds one new batched LLM adjudication step and one new proposal-flow branch.
- **Risk**: Low - Default (non-`--deep`) behavior is unchanged; the new path is
  opt-in.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Note (2026-08-03)

Parented under **EPIC-2938** (Offload mechanical work from `/ll:` skills/commands
into `ll-* Python CLIs`) — this is a sibling of the epic's **FEAT-2942**
(`ll-issues link-epics --mode assign|synthesize`), the same CLI surface this
issue extends.

Worth weighing against the parent epic before implementation: EPIC-2938's
"Shared Conventions" and Motivation are explicitly about *removing*
non-determinism (`--check` gates narrated by the model, Jaccard duplicated in
prose vs. `text_utils.py`) and moving mechanical scoring into deterministic
Python. This issue proposes the opposite direction for one step of that same
CLI — swapping deterministic Jaccard clustering for an LLM-adjudicated pass.
That may still be the right call (the motivation here — pure lexical overlap
structurally misses same-theme, different-vocabulary orphans — is real and
distinct from the determinism concern), but it should be an explicit,
acknowledged tradeoff against EPIC-2938 §Motivation point 2, not an implicit
one. The `--deep` opt-in gate (default path stays deterministic Jaccard) is
the mitigation already designed into this issue.

## Status

**Open** | Created: 2026-08-01 | Priority: P4


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:capture-issue` - 2026-08-01T21:04:44 - `2cabd1bc-5bca-411b-af7d-d8f7d41a247b.jsonl`
