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
verify_verdict: VALID
reconcile_attempted: true
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
- `scripts/little_loops/cli/issues/link_epics.py` — add `--deep` flag parsing to
  `add_link_epics_parser()` (line 257-292); add a batched LLM clustering step
  invoked from `synthesize_clusters()` (line 154); add an `evidence` field to
  `ClusterProposal` (line 63-79, currently four fields with no evidence field)
  and its `to_dict()` (line 72-79); extend `cmd_link_epics()`'s JSON/human-readable
  output (line 352-358) to show the cited evidence for `--deep`-sourced clusters.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- The Jaccard clustering logic this issue targets is no longer in `skills/link-epics/SKILL.md` prose — FEAT-2942 landed and moved it into `scripts/little_loops/cli/issues/link_epics.py` (`synthesize_clusters()`, line 154; `cmd_link_epics()`, line 295-359) and `scripts/little_loops/text_utils.py` (`extract_words`, line 387; `calculate_word_overlap`, line 404). `ll-issues link-epics --mode synthesize` is now a Python CLI, not a skill step. See `### Program Design` above for exact signatures and the current call path.
- CLI flag registration (where `--deep` would be added) is `add_link_epics_parser()` (`link_epics.py:257-292`) — `--mode`, `--threshold` (config-backed default via `issues.link_epics.min_score`, `config-schema.json:159-172`), and `--apply` (rejected for `--mode synthesize` at line 310-316) are the existing precedent for how a new flag is wired.
- Test coverage lives in `scripts/tests/test_link_epics_cli.py::TestSynthesizeClusters` (5 methods, lines 104-149) — all call `synthesize_clusters(orphans, min_score=...)` with the current two-parameter signature; none pass a `deep`/LLM parameter, so this suite is the parity contract for the non-`--deep` path.
- `ClusterProposal` (`link_epics.py:63-79`) has no evidence/rationale field today — the issue's evidence-citation requirement needs one added.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

### Types
- `ClusterProposal` — exactly four fields: `member_ids: list[str]`, `placeholder_title: str`, `modal_priority: str`, `pairwise_min_score: float`; defined at `scripts/little_loops/cli/issues/link_epics.py:63-79`. `to_dict()` (line 72-79) serializes exactly those four. No `evidence`/`justification`/`rationale` field exists on this dataclass or on `EpicProposal` (the `--mode assign` sibling, line 44-60). `--deep`'s evidence-citation requirement (this issue's Proposed Solution) needs a new field added here — none of `TestSynthesizeClusters`'s five assertions probe such a field, so adding one is additive, not breaking.

### Signatures
- `synthesize_clusters(orphans: list[IssueInfo], min_score: float) -> list[ClusterProposal]` — the sole function computing clusters today, defined at `link_epics.py:154`. Its five callers in `scripts/tests/test_link_epics_cli.py::TestSynthesizeClusters` (lines 109, 119, 129, 137, 148 — no-edges, chain-via-union-find, modal-priority, placeholder-title-frequency, single-member-not-clustered) all invoke it with exactly this two-parameter signature and none pass a `deep`/LLM parameter, so changing this signature (vs. adding a parallel path) breaks all five.
- `extract_words(text: str) -> set[str]` and `calculate_word_overlap(words1: set[str], words2: set[str]) -> float` — the Jaccard primitives `synthesize_clusters` calls (title only, not summary, despite this issue's "title+summary" framing), defined at `text_utils.py:387` and `text_utils.py:404` respectively. Both are shared by 8+ other modules (`find_similar.py`, `fingerprint.py`, `issue_discovery/matching.py`, `issue_discovery/search.py`, `issue_history/doc_synthesis.py`, `cli/verify_skill_prose.py`, `loops/sft-corpus.yaml`), so changing their existing contract (as opposed to adding new call sites) has blast radius beyond link-epics.
- `resolve_host().build_blocking_json(*, prompt: str, model: str | None = None, json_schema: dict | None = None) -> HostInvocation` — the existing, already-shipped mechanism for a CLI command to make a synchronous LLM call, declared at `host_runner.py:262-270`. Precedent: `decisions.py::_cmd_extract_from_completed()` (line ~716-828) builds a per-issue prompt, calls `build_blocking_json`, conditionally adds `--json-schema` when `HostCapabilities.structured_output` is `True` (`host_runner.py:301`), then runs `subprocess.run([invocation.binary, *invocation.args, ...], capture_output=True, text=True, timeout=120)` with `TimeoutExpired`/`FileNotFoundError`/non-zero-exit handling inline. That precedent calls once per issue in a loop, not batched — a `--deep` implementation wanting one batched call across all candidates would need a new prompt shape, not a reused loop.

### Call Path
`cmd_link_epics()` (`link_epics.py:295-359`, synthesize tail at 349-359) -> `synthesize_clusters(orphans, min_score=threshold)` (`link_epics.py:154`) -> [`extract_words`, `calculate_word_overlap`] (`text_utils.py:170,176`, called inside the pairwise loop) -> result presented via `print_json({"clusters": [...], "applied": []})` or the human-readable `f"[{title}] {ids} (min score: {score:.3f}, modal priority: {priority})"` line (`link_epics.py:352-358`).

A `--deep` path would add: CLI arg parsing in `add_link_epics_parser()` (`link_epics.py:257-292`, alongside `--threshold`/`--apply`, both of which already exist as the flag-registration precedent) -> a pre-filter step feeding into (a modified or wrapped) `synthesize_clusters` to bound the candidate set -> one `resolve_host().build_blocking_json(...)` call (mechanism confirmed above, batching shape not yet precedented) -> a merge of LLM-proposed clusters with Jaccard-only clusters -> an extended `ClusterProposal`/output surface carrying cited evidence, since neither the dataclass nor `cmd_link_epics`'s JSON/human-readable output currently has a field for it.

### Decision Rules
N/A — no new gap kind, gate, or threshold; `--deep` swaps the clustering mechanism rather than introducing a classification rule.

## Implementation Steps

1. Add `--deep` flag parsing to `add_link_epics_parser()` (`link_epics.py:257-292`),
   alongside the existing `--mode`/`--threshold`/`--apply` flags.
2. After Jaccard pre-filtering (`synthesize_clusters()`, `link_epics.py:154`), add
   one batched `resolve_host().build_blocking_json(...)` call (`host_runner.py:262-270`;
   precedent: `decisions.py::_cmd_extract_from_completed()`) for the whole candidate
   set — not per-pair — that proposes clusters and cites the title/summary evidence
   for each grouping.
3. Merge LLM-proposed clusters with any Jaccard-only clusters (dedupe by member
   overlap) before the placeholder-title step (`_placeholder_title()`,
   `link_epics.py:143-151`).
4. Add an `evidence` field to `ClusterProposal` (`link_epics.py:63-79`) and its
   `to_dict()` (line 72-79), then extend `cmd_link_epics()`'s JSON and
   human-readable output (`link_epics.py:352-358`) to show the cited evidence
   alongside each `--deep`-sourced cluster so the user can verify the grouping.
5. Add a `--deep` usage example to the CLI's `--help` text in
   `add_link_epics_parser()` — there is no mode-choosing guidance in `SKILL.md`
   to update since the clustering logic moved to Python (FEAT-2942).

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

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): OUTDATED as of 2026-08-10: blocking
dependency FEAT-2942 has landed (status: done), and as a result the Jaccard
clustering logic this issue targets has moved out of
skills/link-epics/SKILL.md prose entirely into
scripts/little_loops/text_utils.py and
scripts/little_loops/cli/issues/link_epics.py (now a Python CLI: `ll-issues
link-epics --mode synthesize`). The issue's Current Behavior/Proposed
Solution describe modifying skill prose (Step 3, S1 scoring) that no longer
contains the scoring logic — needs rework to target the CLI code instead of
skill markdown.

## Status

**Open** | Created: 2026-08-01 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:reconcile-issue` - 2026-08-11T22:00:08 - `4fa39a29-8b93-4a9a-adb4-d7d71347e160.jsonl`
- `/ll:refine-issue` - 2026-08-11T21:55:43 - `d5d81416-64f3-45f6-83b0-ea146a218034.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:29 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:capture-issue` - 2026-08-01T21:04:44 - `2cabd1bc-5bca-411b-af7d-d8f7d41a247b.jsonl`
