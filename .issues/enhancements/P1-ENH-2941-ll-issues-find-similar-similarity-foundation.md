---
id: ENH-2941
title: 'Similarity foundation: consolidate Jaccard into text_utils and add ll-issues
  find-similar + batch fingerprint compare'
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
confidence_score: 95
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
decision_needed: true
---

# ENH-2941: Similarity foundation — `ll-issues find-similar` on a single Jaccard implementation

## Summary

Word-overlap similarity is specified in prose in at least three places — `skills/link-epics/SKILL.md` L87–99, `skills/capture-issue/SKILL.md` L195–200, and `commands/normalize-issues.md`'s confidence formula — while `scripts/little_loops/text_utils.py` (`extract_words` L131, `calculate_word_overlap` L148) is the canonical implementation. link-epics L100–105 explicitly documents that the prose and Python stop-word lists have already diverged. Consolidate onto `text_utils.py` and expose it as `ll-issues find-similar`.

## Current Behavior

- capture-issue Phase 2 (L165–231) asks the LLM to run an awk status filter, extract 3+-char words minus a stop-word list, and hand-compute `intersection / union` against every open issue.
- No CLI exists for "which existing issues resemble this text": `ll-issues search` is filter/sort (substring/field matching), `ll-issues fingerprint` is single-file extraction with no comparison mode.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Canonical implementation confirmed at `scripts/little_loops/text_utils.py`: `extract_words()` (L131) does `set(re.findall(r"\b[a-z]{3,}\b", text.lower())) - _COMMON_WORDS`; `_COMMON_WORDS` (L98) is a 27-word `frozenset`; `calculate_word_overlap()` (L148) returns `0.0` on empty input else `len(intersection) / len(union)`.
- Already has one Python consumer beyond `fingerprint`: `scripts/little_loops/issue_discovery/matching.py` L11-13 imports `calculate_word_overlap`/`extract_words` directly and aliases them with the comment "Promoted to text_utils.py as public functions; aliased here for backward compat" — this is the precedent pattern for `find_similar`/`batch_similarity` to import directly (no aliasing needed for new code).
- Closest existing functional precedent for single-text-vs-corpus scoring: `scripts/little_loops/issue_discovery/search.py`'s `search_issues_by_content()` (L81) and `find_existing_issue()` Pass 2/3 (L230-309), which already iterate `_get_all_issue_files(config)` and score title/content overlap using the aliased `text_utils` functions — closer to `find_similar`'s single-text mode than `fingerprint.py` is.
- `issue_parser.find_issues()` (L1508) defaults to `status_filter=None`, and `_matches_status` (L1551) excludes `done`/`cancelled`/`deferred` in that case — this is the "open" behavior for `--against open`. For `--against all`, pass an explicit status_filter set including `done`/`cancelled`; do **not** use `find_issues_for_graph()` (L1633) — that helper preserves `deferred` for dependency-edge resolution, a different semantic than "all" here.
- `ll-issues fingerprint` (`cli/issues/fingerprint.py` L66) already unconditionally prints `json.dumps(result, indent=2)` — it has no `--json` flag because it needs none. The Proposed Solution's "add `--json` to fingerprint if missing" is moot; there is nothing to add there.
- Stop-word list count: there are **four**, not three, independently-maintained lists — `text_utils._COMMON_WORDS` (27 words, canonical), `capture-issue/SKILL.md`'s inline Scoring prose (implicit, no full enumerated list), `capture-issue/SKILL.md`'s history-DB bash one-liner at L219 (~40 words, distinct set), and `link-epics/SKILL.md` Step 3 (L90-95, 35 words). `link-epics/SKILL.md` L101-105 already self-documents this drift in its own prose.
- **Discrepancy**: `commands/normalize-issues.md` was checked directly and contains **no** Jaccard/word-overlap/duplicate-scoring prose. Its "confidence formula" (L176-200) scores *type misclassification* (BUG/FEAT/ENH/EPIC signal-count ratio), not text similarity, and its "duplicate" language (L35, 38, 149-156) refers to duplicate issue *IDs* (filename/frontmatter collisions), not duplicate text. The Summary's claim of a third Jaccard-prose location in this file, and Implementation Step 4's instruction to "update the normalize-issues confidence prose reference," do not match the file's actual content — see Implementation Steps below for the correction.

## Expected Behavior

- `ll-issues find-similar "<title or text>" [--against open|all] [--threshold 0.4] [--limit N] --json` → ranked candidates `{id, title, path, score}`.
- `ll-issues find-similar --batch [--threshold] --json` → pairwise similarity over the corpus (fills the "no batch fingerprint similarity" gap; input for dedup/conflict tooling).
- `skills/capture-issue/SKILL.md` Phase 2 dedup becomes one CLI call; LLM keeps conversation mining, drafting, and the accept/merge decision on returned candidates.
- Distinction from `ll-issues search` stated in `--help` and docs: `search` filters/sorts by fields and substrings; `find-similar` scores fuzzy text similarity. They may share `issue_parser.find_issues` plumbing but have different contracts.

## Proposed Solution

Thin CLI over `text_utils.extract_words`/`calculate_word_overlap` + `issue_parser.find_issues` (include done/cancelled under `--against all`). Ensure `ll-issues fingerprint` output is reusable here; add `--json` to fingerprint if missing. Thresholds default from config where `capture-issue` currently reads them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Existing typed-config threshold precedent (Convention A — the one this issue's "default from config" language matches): `DuplicateDetectionConfig` (`scripts/little_loops/config/features.py` L110-123) exposes `exact_threshold: float = 0.8` / `similar_threshold: float = 0.5` at `config.issues.duplicate_detection.*`; `CaptureIssueConfig.dup_overlap_threshold: float = 0.7` (L1085-1096) at `config.history.capture_issue.dup_overlap_threshold`. Both are already consumed by `issue_discovery/search.py` (L185-186, L245) and `issue_discovery/matching.py`'s `FindingMatch` classification methods (L85-141) — `find_similar`'s threshold defaults should read from these same typed fields rather than introducing a new config key.
- Subcommand module shape to follow: `cli/issues/fingerprint.py`'s `cmd_fingerprint(config, args) -> int` — module-body-local imports (e.g. `from little_loops.text_utils import extract_words` inside the function, not at module top), `int` exit codes, errors to `sys.stderr`.
- Dataclass-to-JSON convention in this codebase: every `cli/issues/*.py` dataclass defines a hand-written `to_dict()` method (e.g. `EpicDrift` in `epic_consistency.py` L41-85) — none use `dataclasses.asdict()`. `SimilarityMatch`/`SimilarityPair` should follow the same `to_dict()` pattern.
- Pairwise/batch-mode precedent (new — not previously cited): `issue_history/coupling.py`'s `analyze_coupling()` (L16-93, pairwise loop L50-72) is the closest existing O(n²) all-vs-all Jaccard precedent in the codebase — `for i, file_a in enumerate(files): for file_b in files[i+1:]:` (not `itertools.combinations`), threshold filter applied inline during pair generation, results sorted descending by strength before return. No existing `ll-issues` subcommand has a `--batch`/pairwise CLI flag (checked `clusters.py`, `impact_effort.py` — both single-pass groupings, not pairwise); `batch_similarity()` is genuinely new at the CLI layer, but this library-layer function is the closest model for its pairwise loop shape.
- `to_dict()` serialization precedent for float scores: `CouplingPair.to_dict()`/`CouplingAnalysis.to_dict()` (`issue_history/models.py` L191-216) round scores via `round(self.coupling_strength, 3)` rather than emitting raw floats — `SimilarityMatch.score`/`SimilarityPair.score` should follow the same 3-decimal rounding in `to_dict()`.
- `calculate_word_overlap()`'s empty-set short-circuit (`text_utils.py:148`) returns `0.0` if *either* input word-set is empty (not just both) — an issue with an empty/very-short title or a corpus file that fails to yield extracted words silently ranks last rather than raising; `find_similar`/`batch_similarity` should preserve this degrade-not-error posture rather than special-casing it.
- Existing single-text-vs-corpus precedent (`search_issues_by_content()`, `issue_discovery/search.py:81`) applies a **hardcoded, non-configurable** `score > 0.1` minimum (line 109) and wraps per-file scoring in `try/except Exception: continue` (lines 111-112) to tolerate malformed corpus files during the scan — `find_similar`'s configurable `--threshold` generalizes the hardcoded value; its batch-mode file scan should adopt the same defensive per-file try/except.
- Import-eagerness nuance for the new subcommand: `cli/issues/__init__.py`'s ~25 `cmd_*` imports (lines 22-72, including `cmd_fingerprint`) are eager at the top of `main_issues()`, not lazy per-dispatch (only `sections` deviates, importing lazily at its own dispatch branch, line 922-923) — `cmd_find_similar` should follow the majority eager-import pattern at the `main_issues()` top level, while `text_utils`/`issue_parser` imports stay lazy *inside* `cmd_find_similar` itself (mirroring `cmd_fingerprint`'s existing two-tier import style).
- Minor line-drift correction (no semantic change): file/line refs cited in earlier research have shifted as the codebase grew — `find_issues()` is now at `issue_parser.py:1526` (was L1508), `_matches_status` at `:1569` (was L1551), `find_issues_for_graph()` at `:1651` (was L1633). For `--against all`, `issue_progress.py` defines `_ALL_STATUSES = frozenset({"open", "in_progress", "blocked", "done", "cancelled", "deferred"})` (line 12) — pass this frozenset directly as `status_filter` (not `find_issues_for_graph`'s non-terminal subset).

## Implementation Steps

1. Add `find_similar` module under `scripts/little_loops/cli/issues/`; wire subparser + alias.
2. Single-text mode, then `--batch` pairwise mode.
3. Slim `skills/capture-issue/SKILL.md` Phase 2 (~65 lines of prose → one call).
4. ~~Update the normalize-issues confidence prose reference (full conversion lands in ENH-2944; here just stop restating the formula).~~ **Correction (research finding)**: `commands/normalize-issues.md` contains no Jaccard/word-overlap prose to slim — its confidence formula (L176-200) scores type misclassification, unrelated to text similarity. Drop this step; there is nothing to update in that file for this issue.
5. Tests: known-similar/dissimilar fixture pairs, threshold behavior, `--batch` output shape, stop-word source is `text_utils` only.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Resolve the link-epics scope gap first** (see Integration Map "Scope Gap Flagged"): either add a step to point `skills/link-epics/SKILL.md` Step 3 at `find-similar`/`find-similar --batch`, or amend Scope Boundaries/AC #2 to explicitly exclude it and defer to FEAT-2942.
7. Add docs: `docs/reference/CLI.md` (new `find-similar`/`fs` section), `docs/reference/API.md` (new `main_issues()` table row), `commands/help.md` L276, `.claude/CLAUDE.md` `ll-issues` bullet.
8. Add `scripts/tests/test_capture_issue_skill.py::TestCaptureIssueNearDuplicateCheck` assertion that rewritten Phase 2 prose references `ll-issues find-similar`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Subparser wiring precedent: `cli/issues/__init__.py`'s `search` subparser (L270-358) shows the `--json`/`-j` `action="store_true"` and `--limit`/`-n` `type=int, metavar="N"` conventions to reuse; every subparser ends with `add_config_arg(...)`. Dispatch is a flat `if args.command == "...": return cmd_...(config, args)` chain (L862-925), not a registry — add a line there for `find-similar`. No subcommand currently registers the `fs` alias (confirmed via grep), so it's free to use.
- Test template: `scripts/tests/test_ll_issues_fingerprint.py`'s `TestIssuesCLIFingerprint` — one `test_*` method per output-shape assertion, plus a dedicated alias-invocation test (`test_fingerprint_fp_alias`) — direct model for testing the `fs` alias.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_discovery/matching.py` L11-13 — aliases `extract_words`/`calculate_word_overlap`; unaffected by the CLI-layer consolidation (no signature change), but confirm it still imports cleanly [Agent 1 finding]
- `scripts/little_loops/issue_discovery/search.py` — `search_issues_by_content()`/`find_existing_issue()` use the aliased functions via `matching.py`; unaffected [Agent 1 finding]
- `scripts/little_loops/cli/issues/fingerprint.py` L32 — existing caller of `extract_words`; unaffected [Agent 1 finding]
- `scripts/little_loops/issue_history/doc_synthesis.py` — calls `extract_words` (`score_relevance`, `_compute_corpus_stats`); unaffected [Agent 1 finding, confirmed via `ll-code callers-of`]
- `scripts/little_loops/config/features.py` L110-123, L1085-1096 — defines `DuplicateDetectionConfig`/`CaptureIssueConfig.dup_overlap_threshold`, the threshold fields `find_similar` should default from; no change to these fields themselves [Agent 1 finding]

### Files to Modify (new)

- `docs/reference/CLI.md` — add a `#### \`ll-issues find-similar\` / \`ll-issues fs\`` section, modeled on the adjacent `#### \`ll-issues fingerprint\` / \`ll-issues fp\`` entry (arg table + `**Output (JSON):**` + `**Examples:**`) [Agent 2 finding]
- `docs/reference/API.md` — add a `find-similar` row to the `main_issues()` sub-commands table, alongside the existing `fingerprint` row [Agent 2 finding]
- `commands/help.md` L276 — add `find-similar` to the `ll-issues` subcommand summary line [Agent 1/2 finding]
- `.claude/CLAUDE.md` — add `find-similar`/`fs` to the `ll-issues` CLI Tools bullet [Agent 2 finding]

### Scope Gap Flagged (not auto-resolved — needs an explicit decision)

- `skills/link-epics/SKILL.md` `## Step 3: Word Extraction and Jaccard Similarity (shared)` — this file's own prose (stop-word list + `score = |A∩B|/|A∪B|` formula) is one of the "three places" named in this issue's Summary, and this issue's own Scope Boundaries lists "removing prose Jaccard/stop-word restatements" as in-scope, and AC #2 requires "No skill/command markdown restates the Jaccard formula or a stop-word list." But **Implementation Steps has no step covering link-epics** — only capture-issue's Phase 2 (Step 3) is listed, and Step 4 (which would have touched normalize-issues) was struck as moot. The link-epics prose block itself self-documents as "out of scope" for a *different*, earlier issue — that disclaimer predates ENH-2941 and does not resolve ENH-2941's own scope language. **Resolve before implementation**: either add an Implementation Step to point link-epics Step 3 at `find-similar` (single-text mode for `A2: Score and Select`) / `find-similar --batch` (pairwise mode for `S1: Cluster Orphans by Jaccard Similarity`), or explicitly amend Scope Boundaries/AC #2 to exclude link-epics and defer it to FEAT-2942 (which already touches link-epics per this issue's `blocks:` edge) [Agent 1 + Agent 2 finding, cross-confirmed]
- `skills/capture-issue/SKILL.md` `#### Search History DB for Near-Duplicates` — the `KEYWORDS=$(...)` bash one-liner (L219 in current text) embeds its own independent ~40-word stop-word regex feeding `ll-session search --fts`, distinct from the main Phase 2 Scoring prose named in Implementation Step 3. Decide explicitly whether this FTS-keyword-extraction shim collapses onto `find-similar` output or stays separate (it isn't a Jaccard score, so may legitimately stay) [Agent 2 finding]

### Tests

- `scripts/tests/test_ll_issues_find_similar.py` (new) — model class-for-class on `TestIssuesCLIFingerprint` in `test_ll_issues_fingerprint.py` (one `test_*` per output-shape assertion, `test_find_similar_fs_alias` mirroring `test_fingerprint_fp_alias`); add `--json`/`--limit` flag tests modeled on `TestSearchOutputFormats.test_json_output`/`test_limit` in `test_issues_search.py` [Agent 3 finding]
- Known-similar/dissimilar fixture pairs — no reusable existing fixture; author new ones following the `search_issues_dir` fixture shape in `test_issues_search.py` (temp `.issues/` corpus with deliberately distinct vs. near-duplicate titles/summaries) [Agent 3 finding]
- `scripts/tests/test_capture_issue_skill.py::TestCaptureIssueNearDuplicateCheck` — add a new assertion (e.g. `test_find_similar_command_documented`) that the rewritten Phase 2 prose references `ll-issues find-similar`/`fs`; this is a coverage gap, not existing breakage — the three existing assertions (`ll-session`, `--kind issue`, `2>/dev/null`) only break if the FTS5-check prose itself is also altered during the Phase 2 rewrite [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Test naming precedent for the batch/pairwise function specifically (distinct from `TestIssuesCLIFingerprint`'s CLI-invocation style already cited above): `scripts/tests/test_issue_history_advanced_analytics.py`'s `TestAnalyzeCoupling` (L359, function-level, includes dedicated `test_boundary_*`/`test_weak_*_filtered` threshold-edge methods) alongside `TestCouplingPair`/`TestCouplingAnalysis` (L293/L326, one class per dataclass for its `to_dict()`) — model `TestFindSimilar`/`TestBatchSimilarity` and `TestSimilarityMatch`/`TestSimilarityPair` the same way.

### Documentation

- See "Files to Modify (new)" above — `docs/reference/CLI.md`, `docs/reference/API.md`, `commands/help.md`, `.claude/CLAUDE.md` [Agent 2 finding]

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-31_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- The "Scope Gap Flagged" section documents an open decision on `skills/link-epics/SKILL.md` Step 3: either add an Implementation Step pointing it at `find-similar`/`find-similar --batch`, or amend Scope Boundaries/AC #2 to explicitly exclude link-epics and defer to FEAT-2942. Resolve before implementing — AC #2 ("No skill/command markdown restates the Jaccard formula...") cannot be verified as satisfied while this is undecided.
- Moderate breadth: ~10 change sites span new CLI code, a subparser edit, two skill-markdown files, four docs files, and two test files. Sequence commits by subsystem (CLI + tests, then skill slimming, then docs) to keep review tractable.

## Session Log
- `/ll:confidence-check` - 2026-08-01T02:21:26 - `01c8092d-4a0b-4561-9d74-6ed782c0fd00.jsonl`
- `/ll:decide-issue` - 2026-08-01T02:18:49 - `a581959f-feb1-4836-b054-1873762e2efd.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:17:10 - `59471451-3cbc-48fe-998a-1caf4de5dce5.jsonl`
- `/ll:confidence-check` - 2026-08-01T02:12:52 - `847ba1b6-a9a3-4c07-b3be-3f3ad4d7d56b.jsonl`
- `/ll:wire-issue` - 2026-08-01T02:09:43 - `b1084b85-efda-47f8-9cf6-6100bbc37ed1.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:03:22 - `eae3de4d-5262-4bd0-962c-47d8e77024a5.jsonl`
