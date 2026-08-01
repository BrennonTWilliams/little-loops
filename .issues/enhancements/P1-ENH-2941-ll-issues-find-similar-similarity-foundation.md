---
id: ENH-2941
title: 'Similarity foundation: consolidate Jaccard into text_utils and add ll-issues
  find-similar + batch fingerprint compare'
type: ENH
priority: P1
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T08:01:24Z'
parent: EPIC-2938
epic: EPIC-2938
blocks:
- FEAT-2942
labels:
- cli
- issues
- similarity
- drift
confidence_score: 100
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 20
decision_needed: false
---

# ENH-2941: Similarity foundation — `ll-issues find-similar` on a single Jaccard implementation

## Summary

Word-overlap similarity is specified in prose in three places — `skills/link-epics/SKILL.md` L87–99, `skills/capture-issue/SKILL.md` L195–200 (Phase 2 Scoring), and `skills/capture-issue/SKILL.md` L219 (the FTS-keyword bash regex) — while `scripts/little_loops/text_utils.py` (`extract_words` L131, `calculate_word_overlap` L148) is the canonical implementation. link-epics L100–105 explicitly documents that the prose and Python stop-word lists have already diverged. Consolidate onto `text_utils.py` and expose it as `ll-issues find-similar`.

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

- `ll-issues find-similar "<title or text>" [--against open|all] [--threshold T] [--limit N] --json` → ranked candidates `{id, title, path, score}`.
- `ll-issues find-similar --batch [--against open|all] [--threshold T] [--limit N] --json` → pairwise similarity over the corpus (fills the "no batch fingerprint similarity" gap; input for dedup/conflict tooling).
- `skills/capture-issue/SKILL.md` Phase 2 dedup becomes one CLI call; LLM keeps conversation mining, drafting, and the accept/merge decision on returned candidates.
- Distinction from `ll-issues search` stated in `--help` and docs: `search` filters/sorts by fields and substrings; `find-similar` scores fuzzy text similarity. They may share `issue_parser.find_issues` plumbing but have different contracts.

#### Comparison field: titles only (decided)

Both modes score the input text against each candidate issue's **title**, never its full file body. This is not a free choice:

- The consumer being replaced is already title-vs-title — `skills/capture-issue/SKILL.md` L192 ("Calculate word overlap between new issue title and existing title").
- Jaccard is symmetric, so a 6-word query against a ~500-word issue body caps at `6/500 ≈ 0.012`. Under content mode the configured 0.5/0.8 duplicate bands are mathematically unreachable and every call returns empty. This is why `search_issues_by_content()` (`issue_discovery/search.py:109`) uses a hardcoded `score > 0.1` instead — it is a *precedent for the corpus-scan loop shape only*, not for the comparison field.
- `IssueInfo` (`issue_parser.py:1030`) already carries `title`, so title mode needs no file reads; content mode would require reading all ~2,864 issue files per invocation.

Full-content similarity is **out of scope** — if it is ever wanted it arrives as an explicit `--field content` flag with its own (much lower) threshold default, in a separate issue.

#### Threshold default (decided)

Default is `config.issues.duplicate_detection.similar_threshold` (`0.5`, `config/features.py` L110-123) — the same field `capture-issue`'s Phase 2 prose already interpolates. `--threshold` overrides it. The earlier `0.4` literal in this issue was illustrative and is not the default; `CaptureIssueConfig.dup_overlap_threshold` (`0.7`) governs the *history-DB FTS* warning path only (see Scope Boundaries) and is not read by `find-similar`.

## Proposed Solution

Thin CLI over `text_utils.extract_words`/`calculate_word_overlap` + `issue_parser.find_issues` (include done/cancelled under `--against all`, via `issue_progress._ALL_STATUSES`). Comparison field is the issue **title** and the threshold defaults to `config.issues.duplicate_detection.similar_threshold` — both decided under Expected Behavior above.

~~Ensure `ll-issues fingerprint` output is reusable here; add `--json` to fingerprint if missing.~~ **Correction (research finding)**: `cli/issues/fingerprint.py:66` already unconditionally prints `json.dumps(...)`; there is no `--json` flag to add and nothing to change in that file.

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

### Scope Gap Decision (materialized by `/ll:decide-issue` from the "Scope Gap Flagged" directive below)

**Option A**: Add an Implementation Step to point `skills/link-epics/SKILL.md` Step 3 at `find-similar` (single-text mode, for `A2: Score and Select`) / `find-similar --batch` (pairwise mode, for `S1: Cluster Orphans by Jaccard Similarity`).

**Option B**: Amend Scope Boundaries and AC #2 to explicitly exclude `link-epics` from this issue and defer that wiring to FEAT-2942 (which already touches `link-epics` per this issue's `blocks:` edge).

> **Selected:** Option B — FEAT-2942 already commits to a full link-epics rewrite that would immediately redo any shallow edit made here, and the `--batch` output shape has no verified integration with link-epics' union-find clustering yet.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected**: Option B — amend Scope Boundaries and AC #2 to exclude `link-epics` wiring from ENH-2941; defer it to FEAT-2942.

**Reasoning**: FEAT-2942 (`.issues/features/P2-FEAT-2942-ll-issues-link-epics-cluster-and-propose.md`) already explicitly scopes a full rewrite of `skills/link-epics/SKILL.md` ("delegate, ~362 → well under 100 lines") with its own AC requiring "no scoring/clustering algorithm prose" and "similarity comes solely from `text_utils.py`" — a strict superset of what Option A would achieve. ENH-2941's `blocks: [FEAT-2942]` edge already sequences that work to happen right after this issue lands. Wiring link-epics now (Option A) means editing the same file twice in quick succession — a shallow Jaccard-formula swap here, then FEAT-2942's full clustering-logic rewrite moments later — and would do so using an unverified integration: `find-similar --batch`'s pairwise output shape has never been checked against link-epics' `S1: Cluster Orphans` union-find consumer, since `find-similar` doesn't exist in the codebase yet (this issue creates it). Option B's cost is a text-only AC amendment, which is itself explicitly anticipated by Option B's own wording.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:---:|:---:|:---:|:---:|:---:|
| A — wire link-epics now | 2 | 1 | 1 | 1 | 5/12 |
| B — defer to FEAT-2942 | 3 | 3 | 2 | 3 | **11/12** |

**Key evidence**:
- FEAT-2942 AC #2/#3 already require "no scoring/clustering algorithm prose" and "similarity comes solely from `text_utils.py`" in `link-epics/SKILL.md` — a superset of Option A's scope.
- `skills/link-epics/SKILL.md` Step 3 (L87-105) is small (19 lines, 2 call sites: `A2` under `--mode assign`, `S1` under `--mode synthesize`) but its existing test (`test_jaccard_scoring_documented`, `test_link_epics_skill.py:53-56`) only asserts the literal string "Jaccard" is present — weak backstop for a premature partial edit.
- No `find-similar`/`find-similar --batch` implementation exists yet to verify against link-epics' union-find clustering consumption pattern.

## Implementation Steps

1. Add `find_similar` module under `scripts/little_loops/cli/issues/`; wire subparser + alias.
2. Single-text mode, then `--batch` pairwise mode.
3. Slim `skills/capture-issue/SKILL.md` Phase 2 (~65 lines of prose → one call).
4. ~~Update the normalize-issues confidence prose reference (full conversion lands in ENH-2944; here just stop restating the formula).~~ **Correction (research finding)**: `commands/normalize-issues.md` contains no Jaccard/word-overlap prose to slim — its confidence formula (L176-200) scores type misclassification, unrelated to text similarity. Drop this step; there is nothing to update in that file for this issue.
5. Tests: known-similar/dissimilar fixture pairs, threshold behavior (including that the default reads the config field), title-only comparison guard, `--batch` `--against` default and output shape, stop-word source is `text_utils` only.
9. In `skills/capture-issue/SKILL.md`, annotate the L219 `grep -vE` stop-word regex as an FTS-query shim (not the similarity stop-word list) and leave the `ll-session --fts` block otherwise intact.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. ~~Resolve the link-epics scope gap first~~ **Resolved by `/ll:decide-issue`**: Option B selected — `skills/link-epics/SKILL.md` is explicitly out of scope for this issue (see Scope Boundaries); no implementation step needed here. That wiring is deferred to FEAT-2942, which already scopes a full rewrite of the file.
7. Add docs: `docs/reference/CLI.md` (new `find-similar`/`fs` section), `docs/reference/API.md` (new `main_issues()` table row), `commands/help.md` L276, `.claude/CLAUDE.md` `ll-issues` bullet.
8. Add `scripts/tests/test_capture_issue_skill.py::TestCaptureIssueNearDuplicateCheck` assertion that rewritten Phase 2 prose references `ll-issues find-similar`.
9. After slimming `skills/capture-issue/SKILL.md` Phase 2, regenerate the checked-in host-adapter copies: `ll-adapt --host gemini --apply` and `ll-adapt --host kimi-code --apply` — both `.gemini/skills/capture-issue/SKILL.md` and `.kimi-code/skills/capture-issue/SKILL.md` currently mirror the old Jaccard/dedup prose and go stale otherwise (no existing test compares these checked-in copies against drift from the source). *(added by `/ll:wire-issue`, 2nd pass)*

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

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `.gemini/skills/capture-issue/SKILL.md` L191, L222 — checked-in host-adapter copy generated 1:1 from `skills/capture-issue/SKILL.md` by `ll-adapt --host gemini --apply`; currently mirrors the same Phase 2 dedup/Jaccard prose being slimmed in the source file. Regenerate after the source edit, don't hand-edit [Agent 2 finding, confirmed via direct read]
- `.kimi-code/skills/capture-issue/SKILL.md` L191, L222 — same as above, generated by `ll-adapt --host kimi-code --apply` [Agent 2 finding, confirmed via direct read]

### Scope Gap Flagged — RESOLVED by `/ll:decide-issue`

_See Option A/B decision under Proposed Solution → "Scope Gap Decision" / "Decision Rationale"._

- ~~`skills/link-epics/SKILL.md` `## Step 3: Word Extraction and Jaccard Similarity (shared)` — this file's own prose (stop-word list + `score = |A∩B|/|A∪B|` formula) is one of the "three places" named in this issue's Summary...~~ **Resolved: Option B selected.** Scope Boundaries and AC #2 have been amended to explicitly exclude `skills/link-epics/SKILL.md` from this issue; that file's Jaccard/stop-word prose is deferred to FEAT-2942, which already scopes a full rewrite of it (delegate ~362 → well under 100 lines, with its own AC requiring no scoring/clustering prose). No Implementation Step is needed here for link-epics. [Agent 1 + Agent 2 finding, cross-confirmed; decided per evidence in Decision Rationale]
- ~~`skills/capture-issue/SKILL.md` `#### Search History DB for Near-Duplicates` — decide explicitly whether this FTS-keyword-extraction shim collapses onto `find-similar` output or stays separate~~ **RESOLVED: stays separate.** The `KEYWORDS=$(...)` one-liner (L219) feeds `ll-session search --fts` — a full-text query over `.ll/history.db`, not a Jaccard score over `.issues/`. It answers a different question (*was something like this recently closed/deferred?*) against a different corpus, and its `config.history.capture_issue.dup_overlap_threshold` (0.7) governs a warning band, not ranking. `find-similar` does not read `history.db` and must not absorb it.

  Two consequences, both in scope here:
  1. Its inline ~40-word stop-word regex is a fourth independently-maintained list, so AC #2 would fail if read literally. The regex stays (a bash `grep -vE` cannot call `text_utils`), but a comment must mark it as an FTS-query-keyword shim, explicitly *not* the similarity stop-word list — with `text_utils._COMMON_WORDS` named as canonical for anything that scores.
  2. AC #3 is scoped to the word-overlap pass only (reworded below); the history-DB check remains a second, separate invocation. [Agent 2 finding; decided during pre-implementation review]

### Tests

- `scripts/tests/test_ll_issues_find_similar.py` (new) — model class-for-class on `TestIssuesCLIFingerprint` in `test_ll_issues_fingerprint.py` (one `test_*` per output-shape assertion, `test_find_similar_fs_alias` mirroring `test_fingerprint_fp_alias`); add `--json`/`--limit` flag tests modeled on `TestSearchOutputFormats.test_json_output`/`test_limit` in `test_issues_search.py` [Agent 3 finding]
- Known-similar/dissimilar fixture pairs — no reusable existing fixture; author new ones following the `search_issues_dir` fixture shape in `test_issues_search.py` (temp `.issues/` corpus with deliberately distinct vs. near-duplicate titles/summaries) [Agent 3 finding]
- Title-only guard (new, per pre-implementation review): one fixture issue whose **title** shares almost nothing with the query but whose **body** repeats the query terms heavily. It must score below threshold. A full-content implementation would rank it first, so this test is what makes the "Comparison field" decision enforceable rather than advisory.
- Config-derived threshold test: patch `config.issues.duplicate_detection.similar_threshold` and assert the no-`--threshold` invocation's cutoff moves with it (catches a hardcoded `0.5`/`0.4`).
- `scripts/tests/test_capture_issue_skill.py::TestCaptureIssueNearDuplicateCheck` — add a new assertion (e.g. `test_find_similar_command_documented`) that the rewritten Phase 2 prose references `ll-issues find-similar`/`fs`; this is a coverage gap, not existing breakage — the three existing assertions (`ll-session`, `--kind issue`, `2>/dev/null`) only break if the FTS5-check prose itself is also altered during the Phase 2 rewrite [Agent 3 finding]
- `scripts/tests/test_text_utils.py` (existing, not previously cited) — `TestExtractWords`/`TestCalculateWordOverlap` already directly test `extract_words`/`calculate_word_overlap` edge cases (empty input, stop-word filtering, exact Jaccard fraction, all-empty-set permutations). `test_ll_issues_find_similar.py` should mirror these cases at the CLI layer rather than re-deriving them, per this codebase's "test composed CLI behavior, don't re-verify the library" convention (see `test_ll_issues_fingerprint.py`) [Agent 3 finding, `/ll:wire-issue` 2nd pass]

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

- `find_similar(config: BRConfig, text: str, against: str = "open", threshold: float = None, limit: int = None) -> list[SimilarityMatch]`
  - Built on `text_utils.extract_words` / `calculate_word_overlap` + `issue_parser.find_issues`. Scores against `IssueInfo.title` only (see Expected Behavior → "Comparison field").
- `batch_similarity(config: BRConfig, against: str = "open", threshold: float = None, limit: int = None) -> list[SimilarityPair]`
  - Same `against` axis as single mode; also title-only.
- Subparser wiring in `scripts/little_loops/cli/issues/__init__.py` (`find-similar`, alias `fs`)

**Annotation notes** (the lines above are kept comma-free inside the parens so the `program_design_nonspecific` linter can parse them; write the real code with the precise types): `against` is `Literal["open", "all"]`; `threshold` and `limit` are `float | None` / `int | None`, where `None` means "resolve from config" (threshold) and "no cap" (limit); make `against`/`threshold`/`limit` keyword-only with a `*` marker.

**Parameter note**: both take `config: BRConfig`, not an `issues_dir: Path` — `find_issues()` (`issue_parser.py:1684`) is `find_issues(config, ...)` and there is no `issues_dir`-taking variant. An earlier draft of this section said `issues_dir: Path`, which contradicted the Call Path below.

### Batch-mode scale

`--against all` is the whole corpus: **2,864 issue files at time of writing → ~4.1M pairs**. `--against open` is 66 issues → ~2,145 pairs. Hence:

- `--batch` defaults to `--against open`; `--against all` is opt-in and expected to be slow (O(n²) `set` intersections; no index).
- Pairwise loop follows `issue_history/coupling.py`'s `analyze_coupling()` shape (`for i, a in enumerate(items): for b in items[i+1:]`), applying the threshold filter inline during pair generation so only surviving pairs are retained in memory.
- Word-sets are extracted **once per issue** before the pairwise loop, not recomputed per pair.
- `--limit` truncates the sorted output; it does not bound the comparison work.

### Call Path

- `find_similar()` -> `find_issues(config, ...)` (existing, `issue_parser.py:1684`) -> `extract_words()` -> `calculate_word_overlap()` (existing, `text_utils.py`)

### Codebase Research Findings (line-drift correction)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **All `issue_parser.py` line citations in this issue are stale again** (a prior refine pass already attempted one correction, but the file has grown further since). Verified current locations at this worktree's HEAD:
  - `find_issues()` — cited elsewhere in this issue as `:1508`, `:1526`, and `:1684` (three different values across sections) — is actually at `issue_parser.py:1718`. Signature confirmed unchanged: `find_issues(config: BRConfig, category=None, skip_ids=None, only_ids=None, type_prefixes=None, status_filter: set[str] | None = None, *, skip_blocked=False) -> list[IssueInfo]` — `config` is the first positional arg and `status_filter` exists exactly as this issue's plan assumes.
  - `_matches_status()` — cited as `:1551`/`:1569` — is actually at `issue_parser.py:1761`. Behavior confirmed: `status_filter is None` excludes `done`/`cancelled`/`deferred` (the "open" default); an explicit set (e.g. `issue_progress._ALL_STATUSES`) is membership-tested directly.
  - `find_issues_for_graph()` — cited as `:1633`/`:1651` — is actually at `issue_parser.py:1843`. Confirmed still the wrong helper for `--against all` per this issue's existing guidance (preserves `deferred` for dependency edges, a different semantic).
  - `IssueInfo` — cited as `issue_parser.py:1030` — the dataclass docstring actually starts at `:1073`, with fields beginning at `:1110`. The path attribute is confirmed named **`path`** (`:1110`, type `Path`), not `file_path`; `title`/`issue_id` fields confirmed present (`:1114`/`:1113`).
  - Everything else already cited in this issue checked out exactly as written and needs no correction: `text_utils._COMMON_WORDS`/`extract_words`/`calculate_word_overlap` (`:98`/`:131`/`:148`), `DuplicateDetectionConfig`/`CaptureIssueConfig` (`config/features.py:111-123`, `:1086-1096`), `issue_progress._ALL_STATUSES` (`:12`), `coupling.py`'s pairwise loop shape and inline threshold filter (`:50-72`), and `cmd_fingerprint`'s function-body-local `text_utils` import (`fingerprint.py:31-32`).
  - No `itertools.combinations` usage exists anywhere under `scripts/` (grep-confirmed) — `coupling.py`'s manual `for i, a in enumerate(...): for b in items[i+1:]` is the only corpus-wide pairwise idiom in the codebase, with no competing convention to reconcile.
- **Test invocation style clarified** (not previously stated in this issue's Tests section): `test_ll_issues_fingerprint.py::TestIssuesCLIFingerprint` invokes the CLI via `patch.object(sys, "argv", [...])` then calls `main_issues()` directly (imported inside the `with patch.object(...)` block) — it does **not** call `cmd_fingerprint()` directly and does **not** shell out via `subprocess`. `test_ll_issues_find_similar.py` should follow this exact invocation shape for consistency with its sibling test file.

## Scope Boundaries

- In scope: the two similarity modes (title-only comparison), `--json` output, capture-issue Phase 2 Scoring slimming, removing prose Jaccard/stop-word restatements in `skills/capture-issue/SKILL.md`.
- Out of scope: clustering or EPIC proposal logic (FEAT-2942), embedding/FTS-based similarity, full-content (`--field content`) similarity, normalize-issues' full conversion (ENH-2944), **`skills/link-epics/SKILL.md` Step 3's Jaccard/stop-word prose — deferred to FEAT-2942, which already scopes a full rewrite of that file** (decided by `/ll:decide-issue`, see Proposed Solution → "Scope Gap Decision"), and **capture-issue's `#### Search History DB for Near-Duplicates` `ll-session --fts` block, which stays a separate invocation** (see Integration Map → Scope Gap Flagged).
- **FYI, not in scope** (`/ll:wire-issue` 2nd pass): `skills/audit-issue-conflicts/SKILL.md` Phase 2b "Cross-Theme Fingerprint Sweep" (L224-248) restates its own Jaccard formulas (`|A∩B|/|A∪B| ≥ 0.25` file overlap, `≥ 0.15` key-term overlap) against `ll-issues fingerprint` output — a fourth hand-maintained site the Summary's "three places" count didn't catch. It scores `files_to_modify`/`key_terms`, not titles, so it is a genuinely different comparison domain than `find_similar`/`batch_similarity` and correctly stays out of this issue's replacement scope — flagged here only so the "consolidated onto text_utils.py" framing isn't read as exhaustive.

## Impact

- **Priority**: P1 - Foundation child; FEAT-2942 hard-blocks on it and ENH-2944 soft-depends
- **Effort**: Small - Thin CLI over existing `text_utils` + `issue_parser`
- **Risk**: Low - Pure read/score; deterministic outputs

## Status

**Done** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [x] `ll-issues find-similar` returns ranked JSON candidates; deterministic for fixed input
- [x] Both modes score against issue **titles** only; a fixture pair that is title-dissimilar but body-similar scores below threshold (guards against a full-content implementation slipping in)
- [x] Threshold defaults to `config.issues.duplicate_detection.similar_threshold`; `--threshold` overrides. A test asserts the default tracks the config field rather than a hardcoded literal
- [x] `--batch` accepts `--against open|all` and defaults to `open`
- [x] No skill/command markdown *in scope of this issue* restates the Jaccard formula or a stop-word list — `skills/capture-issue/SKILL.md` Phase 2 Scoring prose is fully slimmed; `skills/link-epics/SKILL.md` Step 3 is explicitly out of scope (deferred to FEAT-2942, see Scope Boundaries). The capture-issue L219 FTS-keyword `grep -vE` regex is exempt but must carry a comment marking it a query shim, not the similarity stop-word list
- [x] capture-issue's **word-overlap dedup pass** is a single CLI invocation (the separate `ll-session --fts` history-DB check is unaffected and remains a second call)
- [x] Issue body distinction vs `ll-issues search` documented in help text
- [x] pytest coverage in `scripts/tests/`

## Resolution

Added `ll-issues find-similar`/`fs` (`scripts/little_loops/cli/issues/find_similar.py`):
title-only Jaccard scoring via `text_utils.extract_words`/`calculate_word_overlap`
over `issue_parser.find_issues`, single-text mode and `--batch` pairwise mode,
threshold defaulting to `config.issues.duplicate_detection.similar_threshold`.
Slimmed `skills/capture-issue/SKILL.md` Phase 2 to a single CLI call (regenerated
`.gemini`/`.kimi-code` host-adapter copies via `ll-adapt --apply`), annotated the
L219 FTS-keyword regex as a query shim distinct from the canonical stop-word list,
and documented the new sub-command in `docs/reference/CLI.md`, `docs/reference/API.md`,
`commands/help.md`, and `.claude/CLAUDE.md`. `skills/link-epics/SKILL.md` remains
explicitly out of scope (deferred to FEAT-2942 per the Scope Gap Decision above).
14 new tests in `scripts/tests/test_ll_issues_find_similar.py` plus one added
assertion in `test_capture_issue_skill.py`; full suite passes except two
pre-existing, unrelated failures (`test_opencode_adapter` bun/tsc type-defs,
`test_prose_dep_sweep_gate` ENH-2923/ENH-2925 drift) confirmed present on the
branch baseline before this change.

## Notes

If `--batch` starts growing clustering features, stop — clustering belongs to FEAT-2942.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-31_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- ~~The "Scope Gap Flagged" section documents an open decision on `skills/link-epics/SKILL.md` Step 3~~ **Stale — both scope gaps are now closed**: link-epics deferred to FEAT-2942 (`/ll:decide-issue`, Option B), and the capture-issue FTS shim resolved as "stays separate" during pre-implementation review. AC #2 is now verifiable as written.
- Moderate breadth: ~10 change sites span new CLI code, a subparser edit, two skill-markdown files, four docs files, and two test files. Sequence commits by subsystem (CLI + tests, then skill slimming, then docs) to keep review tractable.

## Session Log
- `/ll:manage-issue` - 2026-08-01T08:01:11 - `b865d1ca-4351-4131-97e0-7aad8c77f96a.jsonl`
- `/ll:confidence-check` - 2026-08-01T07:49:07 - `d9a5d04a-a4c8-49de-8060-4b4fb877f926.jsonl`
- `/ll:wire-issue` - 2026-08-01T07:47:48 - `8e52e041-5e03-486c-bb5e-8ec3e15672e7.jsonl`
- `/ll:refine-issue` - 2026-08-01T07:41:14 - `a50e91e5-bf14-4bdf-860d-57036ce8ec72.jsonl`
- `/ll:decide-issue` - 2026-08-01T03:33:35 - `8d629237-6e8e-4fce-b70b-99b321168357.jsonl`
- `/ll:decide-issue` - 2026-08-01T03:29:58 - `8d629237-6e8e-4fce-b70b-99b321168357.jsonl`
- `/ll:confidence-check` - 2026-08-01T02:21:26 - `01c8092d-4a0b-4561-9d74-6ed782c0fd00.jsonl`
- `/ll:decide-issue` - 2026-08-01T02:18:49 - `a581959f-feb1-4836-b054-1873762e2efd.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:17:10 - `59471451-3cbc-48fe-998a-1caf4de5dce5.jsonl`
- `/ll:confidence-check` - 2026-08-01T02:12:52 - `847ba1b6-a9a3-4c07-b3be-3f3ad4d7d56b.jsonl`
- `/ll:wire-issue` - 2026-08-01T02:09:43 - `b1084b85-efda-47f8-9cf6-6100bbc37ed1.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:03:22 - `eae3de4d-5262-4bd0-962c-47d8e77024a5.jsonl`
