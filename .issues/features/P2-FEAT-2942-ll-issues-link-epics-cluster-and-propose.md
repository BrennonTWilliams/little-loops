---
id: FEAT-2942
title: 'll-issues link-epics: cluster orphan issues and propose EPIC assignment/synthesis'
type: FEAT
priority: P2
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-08T08:47:14Z'
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
confidence_score: 90
outcome_confidence: 77
verify_verdict: VALID
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2942: `ll-issues link-epics` — cluster orphans and propose EPIC assignment/synthesis

## Summary

`skills/link-epics/SKILL.md` (362 lines) asks the LLM to *be* a numerical algorithm: hand-computed Jaccard scoring of every orphan × EPIC pair (L87–99, L133–138), HIGH/MEDIUM/LOW bucketing at 0.7/0.4 thresholds, tier-then-score sorting (L150), **union-find clustering** of unmatched orphans (L215–225), frequency-ranked title synthesis and modal-priority selection (L242–253), and both-direction frontmatter wiring with post-write re-read checks (L173–188, L282–324). Move all of it into a CLI; the LLM keeps only naming/validating synthesized EPICs.

## Current Behavior

The skill's prose Jaccard has already diverged from `text_utils.py` (documented in-file at L100–105). Every run pays ~340 lines of algorithm-as-instructions, and clustering correctness depends on the model executing union-find faithfully.

## Expected Behavior

`ll-issues link-epics --mode assign|synthesize [--threshold N] [--apply] --json`:

- **assign**: score orphans against existing EPICs, emit ranked proposals `{orphan, epic, score, tier}`. Proposals only; `--apply` writes the orphan-side `parent:` (frontmatter, via `frontmatter.update_frontmatter` directly — **not** `ll-issues link`, which only manages `blocked_by`/`depends_on`/`relates_to` and has no `parent`/`epic` branch) and the EPIC-side `## Children` append.
- **synthesize**: union-find cluster unmatched orphans on pairwise similarity; emit clusters with member lists, modal priority, and a frequency-derived *placeholder* title.
- `/ll:link-epics` skill **delegates to** this CLI (map-dependencies-style) — the two do not coexist as independent implementations. Skill's remaining LLM work: name/validate synthesized EPICs, sanity-check odd cluster members, then apply via this CLI directly (not `ll-issues link`, which does not cover EPIC assignment).
- **`parent`/`epic` frontmatter decision**: this issue file itself sets both `parent:` and `epic:` (see frontmatter above), matching corpus convention elsewhere. `apply_assignment()` must write **both** fields, not `parent:` alone — writing only one when the corpus convention is both will read as a bug against existing issues.

## Proposed Solution

Build on ENH-2941's consolidated similarity (`text_utils.py`). Reuse `frontmatter.update_frontmatter` directly for writes (`ll-issues link` / `link.py` has no `parent`/`epic` field support — see Expected Behavior — so it is not a write path for this issue), `issue_parser.find_issues` for corpus.

Reuse `find_similar.batch_similarity(threshold=...)` (`find_similar.py:104-143`) as the pairwise edge source for **both** modes instead of writing a third scoring loop: it already runs the O(n²) pairwise `calculate_word_overlap` scan and returns `SimilarityPair`, which is exactly the edge list `synthesize_clusters()`'s union-find needs (member selection = filter pairs to orphans) and exactly what `propose_assignments()` needs (member selection = orphan vs. EPIC-typed candidates). This likely requires adding a candidate-set/`type_prefixes` param to `batch_similarity()` rather than duplicating its scan.

**Scoring input decision**: `IssueInfo` (the type both signatures below take) has no `summary` field, and `find_similar`/`batch_similarity` score titles only. As written, this CLI would score title-vs-title, which is materially noisier (two 6-word titles) than the skill's current title+`## Summary` behavior. Either accept the title-only regression explicitly, or lift `list_cmd.py:94+`'s `--include-summary` body-extraction into the shared scoring layer (`text_utils.py`/`find_similar.py`) so both this CLI and `find-similar` benefit.

**Threshold config decision**: do not reuse `issues.duplicate_detection.similar_threshold` (default 0.5) as-is — its semantics are "this is a duplicate," it's consumed by `find_similar.py:47-57` as a dedup gate, and the skill's own default for assign mode is 0.0 (show all proposals, `--auto` raises to 0.7). Reusing the dedup key as-is would silently drop MEDIUM/LOW proposals and overload one config knob for two purposes. Add a new key, e.g. `issues.link_epics.min_score`, instead of repurposing `similar_threshold`.

**Orphan/EPIC corpus definition**: "orphan" = open `BUG`/`FEAT`/`ENH` issue with both `parent: null` and `epic: null` (`find_issues(type_prefixes={"BUG", "FEAT", "ENH"})` filtered on those fields). EPIC side = open `EPIC` issues. `find_issues` excludes `deferred` issues by default — state explicitly whether `deferred` orphans/EPICs are in or out of scope for scoring.

**Soft dep on FEAT-2947 — do not implement EPIC creation here.** Synthesize mode emits *cluster proposals*, not EPIC files; the actual creation call is `ll-issues create --type EPIC` (FEAT-2947). If FEAT-2947 has not landed, synthesize mode still ships proposal-only and the skill creates the EPIC as it does today. Two independent ID-allocation/templating implementations is exactly the duplication this epic exists to remove.

**Naming/output collision note**: `ll-issues clusters` already exists and visualizes *dependency-edge* clusters. This subcommand scores *text-similarity* clusters — keep the name `link-epics`, and make `--json` output shapes clearly distinct (documented in help text).

## Implementation Steps

1. assign mode (scoring + proposals + `--apply`).
2. synthesize mode (union-find + placeholder titles).
3. Rewrite `skills/link-epics/SKILL.md` to delegate (~362 → well under 100 lines).
4. Tests: fixture corpus with known clusters; threshold/tier boundaries; `--apply` writes both directions and is idempotent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- Test coverage precedent for a fixture corpus with known clusters/threshold boundaries: `scripts/tests/test_link_epics_skill.py` (`TestJaccardScoringBuckets`, line 154-193) and `scripts/tests/test_ll_issues_find_similar.py` already establish this shape for the shared `text_utils.py` scoring layer this issue builds on.
- `--apply` idempotency precedent: `scripts/tests/test_link_cli.py` covers `ll-issues link`'s idempotent-write behavior, the closest existing test model for `apply_assignment()`'s round-trip-safe write.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Reconcile `skills/link-epics/SKILL.md`'s frontmatter `argument-hint` (currently `--auto`/`--min-score`/`--min-cluster`) with the new CLI's actual flags (`--mode`/`--threshold`/`--apply`) — don't just delegate under stale flag names.
- Update `skills/link-epics/agents/openai.yaml`'s `interface.short_description` to drop Jaccard-specific wording, following `skills/map-dependencies/agents/openai.yaml`'s algorithm-agnostic phrasing.
- Rewrite `docs/reference/COMMANDS.md`'s `/ll:link-epics` description (line 102), skill catalog row (line 1037), and `--auto`-flag reference table entry (line 16) to describe delegation instead of inline Jaccard/tier scoring.
- Implement `apply_assignment()`'s `## Children` body-section append using `scripts/little_loops/cli/issues/epic_consistency.py`'s `_section_bounds()`/`atomic_write()` pattern (line 88/209) — no existing shared helper covers markdown body-section mutation.
- Model `synthesize_clusters()` on `scripts/little_loops/cli/issues/clusters.py`'s `_get_components()` (line 323) adjacency/BFS shape, swapping BFS for union-find and structural edges for `calculate_word_overlap() >= min_score` edges.
- Decide and implement the `--threshold` config-default: reuse `config-schema.json`'s `issues.duplicate_detection.similar_threshold` (update its description away from the dedup-specific wording) or add a new schema key — either way, cover it in `scripts/tests/test_config_schema.py`.
- Rewrite `scripts/tests/test_link_epics_skill.py`'s `TestLinkEpicsSkillExists` flag/section-heading assertions (`test_auto_flag`, `test_min_score_flag`, `test_min_cluster_flag`, `test_assign_mode_section`, `test_synthesize_mode_section`, `test_post_write_validation_referenced`) to match the delegated skill's actual content; `TestUpdateFrontmatterRoundTrip`/`TestJaccardScoringBuckets` survive as-is.
- Add `--apply`-gated JSON output tests following `scripts/tests/test_ll_issues_prioritize.py`'s `TestJsonOutput` pattern (`{"findings": [...], "applied": [...]}` shape).
- Add CLI parser/dispatch registration following `epic_consistency.py`'s `add_epic_consistency_parser`/`cmd_epic_consistency` pair in `scripts/little_loops/cli/issues/__init__.py`.

## Use Case

A maintainer with dozens of orphan issues runs `ll-issues link-epics --mode assign --json`, reviews ranked orphan→EPIC proposals, applies the good ones with `--apply`, then runs `--mode synthesize` to get clustered candidates for new EPICs — supplying only the final EPIC names themselves.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Stale-citation corrections (re-confirmed 2026-08-08)**: `epic_consistency.py`'s `_section_bounds()` is at line **98** (not 88) and `fix_epic()` is at line **227** (not 209). `add_epic_consistency_parser`/`cmd_epic_consistency` register in `scripts/little_loops/cli/issues/__init__.py` via import at lines **50-52**, parser call at line **948**, dispatch at lines **1035-1036** (not "line 244/277") — the module-owns-parser *pattern* these citations support is otherwise correctly characterized.
- `skills/link-epics/SKILL.md` is currently **384 lines**, not "~362" as stated in Summary/Implementation Step 3. Its internal prose is unchanged (still full Jaccard scoring + union-find in prose), but line citations have drifted: union-find clustering is now at L229-239 (was cited L215-225), title/priority synthesis at L254-269 (was L242-253), EPIC create/write-back at L296-345 (was L282-324), frontmatter wiring at L171-201 (was L173-188).
- `verify_skill_prose.py`'s `union_find_cluster_merge` `ProseMarker` is at lines **103-108** (not "97-108" as stated in Notes).
- Re-confirmed unchanged: `batch_similarity()`'s signature (`find_similar.py:104-113`) still has no candidate-filtering/`type_prefixes` param — the Proposed Solution's flagged addition is still required, not yet done. `scripts/little_loops/cli/issues/link_epics.py` does not yet exist. No `issues.link_epics.min_score` schema key exists yet.

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register the new `link-epics` subcommand parser and dispatch branch. Two registration conventions coexist in this file: module-owns-parser (`add_link_parser`/`cmd_link` in `link.py`, `add_prioritize_parser`/`cmd_prioritize` in `prioritize.py`) vs. parser-inlined-in-`__init__.py` with only `cmd_*` in the module (`clusters.py`, `find_similar.py`). `add_epic_consistency_parser`/`cmd_epic_consistency` (line 244/277) is the module-owns-parser pair to follow most closely — same shape as `link.py`/`prioritize.py`.
- `scripts/little_loops/cli/issues/link_epics.py` (new) — would house `propose_assignments`, `synthesize_clusters`, `apply_assignment` per this issue's own Program Design section
- `skills/link-epics/SKILL.md` — rewrite to delegate, per Expected Behavior. `skills/map-dependencies/SKILL.md` is the concrete delegation template already in this codebase: CLI-only invocations (`ll-deps analyze`, `ll-deps validate`, `ll-deps apply`, `ll-deps fix`, `ll-deps tree`), an `## Examples` table, an `## Auto Mode Behavior` section, no algorithm prose, and `allowed-tools` scoped to `Bash(ll-deps:*, git:*)` — narrower than `link-epics`'s current `[AskUserQuestion, Edit, Read, Write, Bash(ll-issues:*), Bash(git:*)]`, which is broad because it currently does writes itself. **Frontmatter `argument-hint` mismatch**: current SKILL.md advertises `[--mode assign|synthesize] [--auto] [--min-score <threshold>] [--min-cluster <n>]`, but this issue's own CLI signature is `--mode assign|synthesize [--threshold N] [--apply]` — no `--auto`/`--min-score`/`--min-cluster`. The rewrite must reconcile these flag names, not just delegate under the old ones.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/link-epics/agents/openai.yaml` — Codex host-bridge metadata; `interface.short_description` currently reads `"Assign orphans to EPICs, or synthesize new EPICs from them, via Jaccard similarity"` (algorithm-specific). `skills/map-dependencies/agents/openai.yaml` keeps its `short_description` algorithm-agnostic — update this file in step with the SKILL.md rewrite.
- `docs/reference/COMMANDS.md:102` (`### /ll:link-epics` description) and `:1037` (skill catalog table row) — both describe the *current* Jaccard-prose behavior ("using Jaccard similarity scoring... HIGH/MEDIUM/LOW confidence tiers"); rewrite to describe delegation. `docs/reference/COMMANDS.md:16` also lists `link-epics` in an `--auto`-flag reference table — needs updating/removing if `--auto` is dropped per the argument-hint mismatch above.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_skill_prose.py:97-108` already asserts a `union_find_cluster_merge` marker with `owner_cli="ll-issues link-epics"` — this lint currently expects `skills/link-epics/SKILL.md` to still contain union-find/cluster-merge prose; it will need the CLI to exist and the skill to be rewritten before this marker's intended (CLI-exists) state can be reached
- `scripts/little_loops/cli/issues/format_check.py:108-115` (`_fix_prose_deps`) is the established precedent for one `ll-issues` subcommand invoking another subcommand's `cmd_*` function in-process rather than duplicating its write path — relevant if `apply_assignment()` needs `ll-issues link`'s cycle-safe write path for any field it doesn't own directly

### Conventions in Force
- Two competing conventions govern proposal-vs-write gating: `prioritize.py:184-189` and `format_check.py:92-103` default to proposal-only and require an explicit `--apply` to write; `link.py:82-88` instead defaults to writing and requires an explicit `--dry-run` to preview. This issue's Expected Behavior already specifies `--apply`, i.e. the `prioritize`/`format_check` shape, not `link`'s.
- `--json`/`-j` is added via `add_json_arg()` (`cli_args.py:310-317`); most callers gate with `if getattr(args, "json", False): print_json(...)` (e.g. `clusters.py:595-616`), but `find_similar.py` always emits raw `json.dumps(...)` with no text mode — both conventions coexist in this CLI.
- `--threshold` is config-defaulted rather than hardcoded, per `find_similar.py:47-57`'s `threshold=None` → `config.issues.duplicate_detection.similar_threshold` fallback.
- **Capability-search correction (ENH-3045)**: the original claim here — "no union-find/disjoint-set implementation exists anywhere in `scripts/little_loops/` today (confirmed by grep)" — searched by algorithm name, not capability, and was materially incomplete: `find_similar.batch_similarity()` (`scripts/little_loops/cli/issues/find_similar.py:104-143`) already performs the exact O(n²) pairwise `calculate_word_overlap` scan that produces the edge list `synthesize_clusters()`'s union-find needs — found by searching for the input/output shape (`list[IssueInfo]` in, pairwise-scored edges out) and the callers of the shared `calculate_word_overlap()` primitive. `synthesize_clusters()`'s union-find step over that edge list is still new code with no existing implementation, but its input is not built from scratch — the Proposed Solution's "Reuse `find_similar.batch_similarity()`" bullet above already states this; this note reconciles the two. The only existing *clustering* algorithm, `clusters.py:_get_components()` (BFS over dependency-edge adjacency), clusters on a structurally different input (existing relationship edges, not pairwise text similarity) and is not reusable for the union-find half.
- `update_frontmatter()` (`frontmatter.py:439-469`) only touches the YAML block. There is no existing helper for appending to a markdown body section — `apply_assignment()`'s EPIC-side write (append to `## Children`) has no existing shared helper. `link.py`'s `_write_reciprocal()` (lines 179-202) is the closest precedent (read → merge into existing list field → `update_frontmatter()` → write) but only covers frontmatter list fields, not prose section bodies.
- **Flag-vocabulary collision (second wiring pass)**: `skills/link-epics/SKILL.md`'s frontmatter `description` and `.claude/CLAUDE.md`'s skill-catalog line already establish a *prose-parsed* flag vocabulary for `/ll:link-epics` — `--mode`, `--min-score`, `--min-cluster`, `--auto` — that is separate from and only partially overlapping with this issue's new *argparse-level* `ll-issues link-epics` flags (`--mode`, `--threshold`, `--apply`; no cluster-size flag). `--min-score`/`--threshold` and `--auto`/`--apply` are different names for related concepts. Any doc or skill prose describing "link-epics flags" after this rewrite must disambiguate which layer (skill invocation vs. CLI subcommand) it's naming, not conflate the two vocabularies.
- **Config description duplication (second wiring pass)**: `config-schema.json`'s `issues.duplicate_detection.similar_threshold` description ("Jaccard similarity threshold above which a finding is treated as similar (update existing issue)") is hand-duplicated, not schema-generated, in `docs/reference/CONFIGURATION.md:335`, `docs/reference/API.md:449`, and `docs/reference/CLI.md:1791`. None of these three are covered by `test_config_schema.py` (which checks structure/defaults, not description prose) — if the schema description is reworded away from the dedup-specific framing (per the Proposed Solution's Threshold config decision), these three doc lines will silently drift unless updated in the same change.

_Wiring pass added by `/ll:wire-issue`:_
- **More concrete body-section-append precedent than `_write_reciprocal()`**: `scripts/little_loops/cli/issues/epic_consistency.py`'s `_section_bounds()` (line 88, regex-locates a `## Heading` section's start/end) + `fix_epic()` (line 209, builds new bullets, splices into or appends the section, writes via `atomic_write`) is the closest existing "append to a markdown body section" implementation in this codebase — same `## Children` heading `apply_assignment()` needs to target. Either reuse `_section_bounds()` directly or hand-roll the same pattern.
- `scripts/little_loops/cli/issues/clusters.py`'s `_get_components()` (line 323, BFS over an adjacency `dict[str, set[str]]`, returns `list[list[str]]` sorted by size descending) is the closest existing clustering shape to model `synthesize_clusters()` against — same input/output shape as union-find over pairwise similarity, differing only in algorithm (BFS vs union-find) and edge derivation (structural fields vs `calculate_word_overlap` ≥ `min_score`).
- **Config threshold decision**: `--threshold`'s config-default could reuse `config-schema.json`'s existing `issues.duplicate_detection.similar_threshold` (min 0.0/max 1.0, default 0.8) — but its schema description ("...treated as similar (update existing issue)") is written for `find_similar`'s dedup use case and would read misleadingly for epic-assignment scoring if reused as-is without an update. Alternatively add a new schema key; either choice is covered by `scripts/tests/test_config_schema.py`.

### Tests
- `scripts/tests/test_link_epics_skill.py` — existing structural tests for the current skill, including `TestJaccardScoringBuckets` (line 154-193, asserts `calculate_word_overlap`/`extract_words` directly) and `TestUpdateFrontmatterRoundTrip` (line 97-127) — both already treat `text_utils.py`/`frontmatter.py` as source of truth even though the skill prose doesn't call them yet
- `scripts/tests/test_link_cli.py` — existing `ll-issues link` subcommand tests, the closest precedent for testing an idempotent frontmatter-writing subcommand
- `scripts/tests/test_ll_issues_find_similar.py` — existing tests for the ENH-2941 similarity foundation this issue builds on
- `scripts/tests/test_text_utils.py`, `scripts/tests/test_frontmatter.py`, `scripts/tests/test_issue_parser.py` — unit coverage for the three reused modules

_Wiring pass added by `/ll:wire-issue` (second pass):_
- `scripts/little_loops/dependency_mapper/models.py:11-50,86-102` (`DependencyProposal` + `ParallelSafePair`, combined into one `DependencyReport`) is the closest existing precedent for a report combining a per-candidate scoring dataclass with a grouped/clustered dataclass — the same shape split as `EpicProposal`/`ClusterProposal`. `scripts/tests/test_dependency_mapper.py:811-930` (`TestFormatReport.test_format_with_proposals`, `TestFormatReportConflictInfo.test_parallel_safe_section`, `test_medium_conflict_level`) shows the fixture-construction and threshold-bucketing-assertion pattern to follow for `EpicProposal`/`ClusterProposal` test fixtures.
- Confirmed no action needed: `scripts/little_loops/cli/help.py:54` is a bare skill-name string in the catalog, valid regardless of flag changes; `scripts/tests/test_cli_doctor_full.py:175` constructs its `ProseFinding` synthetically with `scan_prose` mocked out, so it does not depend on real `SKILL.md` content and needs no change.

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/tests/test_link_epics_skill.py` needs a near-total pass, not just additions** — most of `TestLinkEpicsSkillExists` (lines 11-94) asserts literal substrings from the *current* algorithm-prose SKILL.md that will go stale under delegation: `test_auto_flag` (17-19, asserts `"--auto"` — new flag is `--apply`), `test_min_score_flag` (21-23, asserts `"--min-score"` — new flag is `--threshold`), `test_min_cluster_flag` (88-90, asserts `"--min-cluster"` — not in the new CLI signature at all), `test_config_issues_base_dir` (35-37, asserts the `{{config.issues.base_dir}}` macro — the `map-dependencies` delegation template doesn't use this macro in bash invocations), `test_assign_mode_section`/`test_synthesize_mode_section` (80-86, assert exact `"## Mode: `--mode assign`"`-style headings with no equivalent in the delegation template), `test_post_write_validation_referenced` (65-70, asserts `"Post-write consistency"` — that responsibility moves into `apply_assignment()` in Python once delegated). `TestUpdateFrontmatterRoundTrip` (97-127) and `TestJaccardScoringBuckets` (154-193) exercise `frontmatter.py`/`text_utils.py` directly, not SKILL.md content — these survive and are reusable as `link_epics.py` unit-test seeds.
- `scripts/tests/test_epic_consistency.py`'s `TestEpicConsistencyFix`/`TestEpicConsistencyIdempotency` (lines 357-544, esp. `test_fix_preserves_existing_description`, `test_fix_does_not_drop_category_b_entries`, `test_fix_is_idempotent`) is the test pattern to follow for `apply_assignment()`'s `## Children` body-section append + round-trip idempotency — pairs with the `_section_bounds()`/`fix_epic()` implementation precedent noted above.
- `scripts/tests/test_ll_issues_prioritize.py`'s `TestJsonOutput` (lines 309-355) is the closest precedent for `--apply`-gated JSON output shape (`{"findings": [...], "applied": [...]}`, `applied == []` without `--apply`) — matches this issue's own `assign`/`synthesize` proposal-vs-apply distinction more directly than `test_link_cli.py`'s boolean write-vs-dry-run shape.

### Documentation
- `docs/reference/CLI.md` — needs a new `link-epics` entry
- `docs/reference/API.md` — needs `propose_assignments`/`synthesize_clusters`/`apply_assignment` entries (already flagged in Related Key Documentation)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — see Files to Modify above (lines 16, 102, 1037) for the specific Jaccard-prose and `--auto`-table passages that need rewriting.
- FYI (no action here): `.issues/enhancements/P4-ENH-2979-deep-flag-llm-clustering-link-epics.md` is an open, unimplemented ENH written entirely against the *current* SKILL.md prose structure (names "Step 3, S1" of the skill as its insertion point for a `--deep` LLM-clustering flag). Once this issue lands, ENH-2979's plan is stale — its hook point becomes `synthesize_clusters()` in the new `link_epics.py` module, not a SKILL.md step. ENH-2979 will need its own Integration Map rewritten before implementation; out of scope to edit here.

_Wiring pass added by `/ll:wire-issue` (second pass):_
- `skills/issue-workflow/SKILL.md:77` and `:164` — describe `/ll:link-epics [--auto]` "via similarity scoring" in the pipeline invocation list and the skill-reference table; stale against the delegated CLI's actual flags (`--mode`/`--threshold`/`--apply`, no `--auto`) and against the "no inline algorithm" outcome of delegation. Update alongside the SKILL.md rewrite. (`skills/review-epic/SKILL.md:102` and `skills/capture-issue/SKILL.md:471` were checked and only name the invocation with no flag/algorithm detail — confirmed no change needed there, nor in their `.gemini/`/`.kimi-code/` host-parity mirrors.)

### Behavior Parity

_Wiring pass added by `/ll:wire-issue`, validated against ENH-3045's motivating-defects retrospective:_
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `skills/link-epics/SKILL.md` | Scores orphan × EPIC similarity on title + `## Summary` body text | CHANGED | `IssueInfo` has no `summary` field, and `find_similar`/`batch_similarity` score titles only — see the "Scoring input decision" note above. This CLI would score title-only unless `--include-summary`-style body extraction is lifted into the shared scoring layer. Accept the narrowed corpus explicitly, or fix before shipping — do not let it pass silently. |
| `skills/link-epics/SKILL.md` | HIGH/MEDIUM/LOW confidence tiers at 0.7/0.4 score thresholds | DROPPED | The tier boundaries appear nowhere in this issue's CLI signature or `EpicProposal` shape — only a `score`/`tier` field is declared, with no threshold constants carried into Program Design or Proposed Solution. Must be restated (as literal 0.7/0.4 constants) in the new module if tiering is still wanted, or explicitly dropped in favor of raw scores. |
| `skills/link-epics/SKILL.md` | "Orphan" = an open BUG/FEAT/ENH issue with no `parent:` frontmatter field | PRESERVED (must be restated) | This definition exists only in the skill prose being replaced; `synthesize_clusters`/`propose_assignments`'s Program Design section does not state it. Must be written into the new CLI module's docstring or Program Design before implementation, or the CLI silently redefines "orphan" from scratch. |

## Program Design

### Types

- `EpicProposal: dataclass` — `orphan_id: str`, `epic_id: str`, `score: float`, `tier: Literal["HIGH", "MEDIUM", "LOW"]` — tier boundaries: `score >= 0.7` → HIGH, `0.4 <= score < 0.7` → MEDIUM, `score < 0.4` → LOW (carried over from the skill being deleted, `SKILL.md` L137-138; not documented anywhere else in this issue). State whether these boundaries are configurable or hardcoded, and cover the 0.4/0.7 boundary cases in Acceptance Criteria.
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

- [x] Both modes emit deterministic JSON proposals (tiebreak: score desc, then `orphan_id`, then `epic_id` — float ties are common on short titles); no writes without `--apply`
- [x] `--apply` is undefined/unsupported for `--mode synthesize` (synthesize is proposal-only; EPIC creation is delegated to FEAT-2947 per the Proposed Solution). `--apply --mode synthesize` must error out rather than silently create EPIC files, until FEAT-2947 lands.
- [x] `skills/link-epics/SKILL.md` contains no scoring/clustering algorithm prose
- [x] Similarity comes solely from `text_utils.py` (no local stop-word list)
- [x] Help text distinguishes this from `ll-issues clusters`
- [x] No ID allocation, slugging, or EPIC-file templating in this subcommand — creation is delegated to `ll-issues create` (FEAT-2947) or left to the skill
- [x] pytest coverage in `scripts/tests/`

## Notes

assign and synthesize are independently shippable — split into two issues if the union-find + synthesis half exceeds ~a day.

Before relying on it as the post-rewrite gate: confirm whether `verify_skill_prose.py:97-108`'s `union_find_cluster_merge` marker (`owner_cli="ll-issues link-epics"`) currently has an `ll-prose-ok` suppression in `skills/link-epics/SKILL.md` — if not, this lint is either already live-failing or not wired to that file, and either way it needs to be resolved as part of the skill rewrite in Implementation Step 3.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Resolves this section's own open question (re-confirmed 2026-08-08)**: `skills/link-epics/SKILL.md` currently has no `<!-- ll-prose-ok: ... -->` suppression comment anywhere in the file. So `verify_skill_prose.py`'s `union_find_cluster_merge` marker (`owner_cli="ll-issues link-epics"`, lines 103-108) is presumably live-failing against this file today, or not currently wired to run against skill markdown at all — either way, no suppression needs to be removed as part of the Implementation Step 3 rewrite; the rewrite just needs to make the marker's pattern (`union[- ]find|cluster[- ]merge`) stop matching once the prose is deleted.

## Related Key Documentation

- `.claude/CLAUDE.md` — this issue adds a new `ll-issues link-epics` subcommand to the CLI tool catalog and rewrites `skills/link-epics/SKILL.md` to delegate to it, the same skills-lean-on-CLI pattern CLAUDE.md documents for other `ll-issues` subcommands.
- `docs/reference/API.md` — the new CLI mode functions (`propose_assignments`, `synthesize_clusters`, `apply_assignment`) belong in the `cli/*` entry-point and `issue_parser`/`frontmatter` module reference this doc maintains.

## Session Log
- `/ll:manage-issue` - 2026-08-08T08:46:31 - `fe603bea-85b7-4aa7-a60d-5423c4a6cc1a.jsonl`
- `/ll:ready-issue` - 2026-08-08T08:15:54 - `1d4b547f-0d25-4762-94b4-2dd18b1f5cac.jsonl`
- `/ll:confidence-check` - 2026-08-08T08:14:14 - `3a5d7099-220a-48a1-b42d-67707edf996a.jsonl`
- `/ll:verify-issues` - 2026-08-08T08:12:04 - `2a35add7-fbc6-45f7-8e88-603c0569c14c.jsonl`
- `/ll:wire-issue` - 2026-08-08T08:10:04 - `fb876f78-e82e-4f6f-9b37-8d5b7d4d5811.jsonl`
- `/ll:refine-issue` - 2026-08-08T08:03:17 - `24708135-16a6-4942-81ff-6da0a4166ca1.jsonl`
- `/ll:wire-issue` - 2026-08-05T01:57:18 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:confidence-check` - 2026-08-04T20:32:13 - `9a232634-c75e-4ea0-9ef9-0d29e428f8df.jsonl`
- `/ll:wire-issue` - 2026-08-04T20:28:15 - `acac065d-330f-47d4-a8a4-9d824238c902.jsonl`
- `/ll:refine-issue` - 2026-08-04T20:19:43 - `785f4a65-d938-4ebb-bae2-5c9ee18b9757.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T00:26:02 - `6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`
