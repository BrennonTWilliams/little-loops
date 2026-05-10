---
id: ENH-1412
type: ENH
priority: P3
status: open
captured_at: '2026-05-10T00:49:33Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1412: Refine Change Surface rubric to credit enumerated mechanical fanouts

## Summary

The `confidence-check` Criterion D (Change Surface, `skills/confidence-check/SKILL.md:354-369`) scores by raw count of callers/dependents — 11+ → 0/25. This penalizes mechanical-fanout issues (e.g. text substitutions across an enumerated file list) the same as unbounded blast-radius code changes, even when the fanout is fully enumerated and grep-verifiable. Refine the rubric to distinguish "code blast radius" from "enumerated mechanical fanout" so outcome confidence reflects the actual risk.

## Current Behavior

Criterion D maps caller/dependent count directly to a score:

| Finding | Score |
|---------|-------|
| 0-2 callers/dependents — isolated change | 25 |
| 3-5 callers/dependents — manageable surface | 18 |
| 6-10 callers/dependents — broad surface | 10 |
| 11+ callers/dependents — very wide blast radius | 0 |

For a uniform mechanical sweep like FEAT-1407 (43 markdown files, all `BUG|FEAT|ENH` → `BUG|FEAT|ENH|EPIC`), this scores 0/25 even though:
- Every site is enumerated in "Files to Touch"
- A verification grep is provided that proves completeness
- A doc-wiring pytest asserts the outcome
- There are no callers to break — only edit sites to apply substitutions to

The result: outcome_confidence collapses to ~60 (MODERATE) on issues whose actual implementation risk is low and bounded. The score is misleading rather than informative.

## Expected Behavior

Criterion D distinguishes two risk patterns and scores each on its real risk:

**Pattern A — Code blast radius** (current rubric): unchanged. N callers of a function/API where each caller is a potential breakage. Score by count.

**Pattern B — Enumerated mechanical fanout**: text substitutions, type-list additions, schema-row additions across N enumerated files where each site is uniform. Score by *verifiability of completeness*, not by N:

| Finding | Score |
|---------|-------|
| Sites enumerated + verification grep + automated test asserting completeness | 25 |
| Sites enumerated + verification grep, no automated test | 18 |
| Sites enumerated, no verification command | 10 |
| Sites not enumerated (unbounded sweep) | 0 |

Detection heuristic: if the issue's "Files to Touch" enumerates a specific list AND the change description is uniform (e.g. "add EPIC to all `BUG|FEAT|ENH` references"), apply Pattern B. Otherwise Pattern A.

After this change, FEAT-1407-style issues score 25/25 on Change Surface (it has all three: enumeration, verification grep at line 228-231, doc-wiring test specified at line 263) — outcome confidence rises from 60 to ~85, matching the actual risk profile.

## Use Case

**Who**: A maintainer running `/ll:confidence-check` on a coordinated documentation sweep or type-list update.

**Context**: The issue lists 20-50 files to touch, all changes are mechanical substitutions, and the issue includes a verification grep + a doc-wiring pytest. Today this scores 60 outcome confidence, prompting reviewers to ask "should we break this up?" The answer is no — splitting just adds coordination cost without reducing risk.

**Goal**: Have the rubric reflect that an enumerated, grep-verifiable mechanical sweep is *less* risky than an unbounded code change with the same caller count.

**Outcome**: Outcome confidence becomes a useful signal. Mechanical sweeps with verification score high; sweeps without enumeration or verification score low. The score guides the right action (write a verification grep, write a wiring test) instead of pushing toward unnecessary decomposition.

## Motivation

- Outcome confidence is currently misleading on a recurring issue archetype (sweep/wiring updates). FEAT-1407 is the immediate example; FEAT-1389's other children and any future EPIC-style coordinated rollouts will hit the same pattern.
- Decomposing mechanical sweeps to "raise the score" is an anti-pattern: it multiplies PRs/sessions, creates partial-state windows where some categories are updated and others aren't, and adds coordination overhead with no real risk reduction.
- The rubric refinement encodes a useful judgment: *verifiability beats blast radius*. Issues that include a one-line grep proving completeness should be rewarded, which also creates a positive feedback loop pushing future issues to include verification commands.
- This is the lightest of the options surveyed in conversation — a rubric edit (~20 lines), no schema changes, no new fields, no new issue types.

## Alternatives Considered

**Split Criterion A (Complexity) into Breadth × Depth** (tracked separately as ENH-1413). Today Criterion A scores by raw file count (`skills/confidence-check/SKILL.md:312-318`), so a 43-file uniform substitution scores the same as a 43-file architectural rewrite. Splitting A into Breadth (number of sites) and Depth (per-site complexity) would let a wide-but-shallow sweep score well without any Pattern A/B classifier. It also fixes a real double-count: FEAT-1407 currently gets penalized on both A (11+ files = 0) and D (11+ dependents = 0) for the same underlying breadth.

**Why both, not either**: Breadth/Depth on A measures the *intrinsic shape* of the change (how many sites × how complex each). Verifiability on D measures the *de-risking artifacts* attached to the issue (enumeration + grep + wiring test). A shallow 43-file sweep with no grep and no test is still risky; one with both is not — Depth alone doesn't distinguish those. The two refinements compose: A captures shape, D captures de-risking. ENH-1412 stays scoped to the D verifiability ladder; ENH-1413 covers the A double-count.

**Why not fold verifiability into a Phase 4.5 risk-suppression rule instead of a D scoring lever**: rejected because outcome_confidence is the surfaced number; downgrading verifiability to a risk-phrase suppression doesn't move the score that drives reviewer behavior.

## Proposed Solution

1. Edit `skills/confidence-check/SKILL.md` Criterion D (lines 354-369):
   - Rename heading from "Change Surface" to "Change Surface / Fanout Verifiability" (or similar) to reflect the dual concept.
   - Add a "Detection method" preamble that classifies the change as Pattern A (code blast radius) or Pattern B (enumerated mechanical fanout). Heuristic: if the issue body uses words like "all", "every", "across", "each" together with an enumerated "Files to Touch" list of >5 markdown/config/template files and the changes are uniform substitutions → Pattern B.
   - Replace the single scoring table with two: Pattern A retains the current count-based table; Pattern B uses a verifiability-based table (enumeration + verification grep + automated test).
   - **Model after Criterion 3 (lines 219-263)** — the existing canonical fork-rubric template, which already presents type-specific (BUG/FEAT/ENH) headings + per-variant scoring tables under a single criterion.
2. Add a new **Phase 4.8** to `skills/confidence-check/SKILL.md` (after the existing Phase 4.7 at line 511) that suppresses a "large file surface" risk phrase when Pattern B + the full verification chain is detected. Mirror the existing Phase 4.6 / 4.7 signal-phrase suppression template (lines 471-511): list signal phrases, run them against the Outcome Risk Factors content written by Phase 4.5, and either suppress the phrase or set a frontmatter flag with idempotent Edit + check-mode skip. (Note: Phase 4.5 itself is the write-back phase — `### Phase 4.5: Findings Write-Back`, lines 419-466 — and currently contains no suppression-rule scaffolding nor any "large file surface" phrase; the suppression must live in a new sibling phase, not inside 4.5.)
3. Add 1-2 examples to the skill showing Pattern A vs Pattern B scoring (one count-based code change, one enumerated mechanical sweep like FEAT-1407). Use inline markdown tables — the existing examples convention (e.g. `skills/confidence-check/SKILL.md:650-657`).
4. Re-run `/ll:confidence-check` on FEAT-1407 to verify outcome_confidence rises from 60 to a value matching the new rubric (expected ≥80).

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md` and confirm exact lines:
   - Criterion D heading + scoring table: lines 354-369.
   - Phase 4.5 (Findings Write-Back, the surfaced-output phase): lines 419-466.
   - Phase 4.6 / 4.7 (existing signal-phrase flag-write phases — the template to mirror): lines 471-511.
   - CLI flags section: lines 400-416 (`--score-change-surface` at line 415).
2. Draft the dual-pattern rubric for Criterion D using Criterion 3 (lines 219-263) as the structural template:
   - Maintain the four-part Criterion structure (`#### Criterion D: ... (0-25 points)` → `**What to check**` → `**Detection method**` → `**Scoring**`).
   - Within Detection method, add classification step ("Pattern A — Blast Radius" vs "Pattern B — Enumerated Mechanical Fanout") with the heuristic.
   - Replace the single scoring table with two: bold-labeled `**Pattern A — Blast Radius**:` + current count-based table; `**Pattern B — Enumerated Mechanical Fanout**:` + new verifiability-based table.
3. Add a new **Phase 4.8** after line 511 — a signal-phrase suppression for "large file surface" risk when Pattern B + verification chain are present. Use the Phase 4.6 / 4.7 boilerplate verbatim: `Skip this phase if CHECK_MODE is true`, scan Phase 4.5's Outcome Risk Factors output, define `**Signal phrases**` bullet list, idempotent Edit on frontmatter, terminal log line. (No edit to Phase 4.5 itself — it currently has no risk-phrase scaffolding.)
4. Add a worked example (or two) using inline markdown tables, modeled after the existing example block at `skills/confidence-check/SKILL.md:650-657`.
5. Verify: re-run `/ll:confidence-check` on FEAT-1407; confirm Criterion D rises from 0 → 25 (or 18) and outcome_confidence rises accordingly. Spot-check on a code-fanout issue (e.g. one of the recent BUG-13xx issues that touch many call sites) to confirm Pattern A still applies.
6. Add a regression test to `scripts/tests/test_confidence_check_skill.py` if its style admits prose-rubric assertions (e.g. asserting both "Pattern A" and "Pattern B" headings + the verifiability-table rows are present in `skills/confidence-check/SKILL.md`); otherwise rely on the FEAT-1407 manual re-score as the verification artifact.
7. Update related docs only if they reproduce the rubric inline: `docs/reference/API.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `docs/reference/COMMANDS.md` (audit each for rubric prose; many only mention `/ll:confidence-check` by name and do not need updating).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. If the criterion heading is renamed (e.g., "Change Surface" → "Change Surface / Fanout Verifiability"), update `scripts/little_loops/cli/issues/refine_status.py` `print_legend()` at line 546 — hardcodes `"Outcome criterion D – Change Surface (0–25)"` and will diverge from the skill heading if left unchanged.
9. If the criterion label changes, update `scripts/little_loops/issue_parser.py` — `IssueInfo.score_change_surface` field docstring at line 246 names `"Criterion D – Change Surface"`.
10. Audit `docs/reference/ISSUE_TEMPLATE.md` Frontmatter Fields table row for `score_change_surface` — update description string if criterion name changes (currently: `"Outcome criterion D – Change Surface (0–25)"`).
11. Add regression tests to `scripts/tests/test_confidence_check_skill.py` — add `TestCriterionDDualPattern` and `TestPhase48LargeFileSurfaceSuppression` using the `_phase_text()` heading-search pattern (see Tests section for full code). These classes mirror `TestDecisionNeededFlagWriteBack` and `TestMissingArtifactsFlagWriteBack` exactly.

## Acceptance Criteria

- `skills/confidence-check/SKILL.md` Criterion D distinguishes Pattern A (code blast radius) from Pattern B (enumerated mechanical fanout) with separate scoring tables, structured to match the four-part criterion template (heading / What to check / Detection method / Scoring) and the type-fork precedent of Criterion 3.
- A documented heuristic exists for classifying which pattern applies, based on issue content (uniform language + enumerated Files to Touch + small per-site change footprint).
- Pattern B scoring rewards enumeration, verification grep, and automated wiring tests.
- A new Phase 4.8 (mirroring the Phase 4.6 / 4.7 signal-phrase template at lines 471-511) suppresses a "large file surface" risk phrase when Pattern B applies and the verification chain is present. Phase 4.5 itself is left structurally unchanged.
- Re-running `/ll:confidence-check` on FEAT-1407 produces outcome_confidence ≥ 80 (was 60).
- A code-fanout issue (Pattern A) re-scored under the new rubric produces the same score as before — no regression on the original use case.

## API/Interface

No CLI/API changes. The `confidence-check` CLI flags (`--score-change-surface`, etc., `skills/confidence-check/SKILL.md:400-416` — the bash block plus the explanatory bullets) remain unchanged — only the rubric the LLM applies before invoking the CLI changes. The frontmatter field written by `--score-change-surface` is `score_change_surface`; no schema or handler changes are needed in `scripts/little_loops/cli/issues/set_scores.py` or `scripts/little_loops/cli/issues/__init__.py`.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Criterion D rubric (lines 354-369); add new Phase 4.8 after the current Phase 4.7 (which ends at line 511); add 1-2 worked examples following the inline-table format at lines 650-657. Phase 4.5 itself (lines 419-466) is **not** modified — the suppression scaffolding is a new sibling phase, not an edit inside 4.5.
- `scripts/little_loops/cli/issues/refine_status.py` — `print_legend()` at line 546 hardcodes `"Outcome criterion D – Change Surface (0–25)"`; update label to match new criterion heading if renamed [Agent 2 finding]
- `scripts/little_loops/issue_parser.py` — `IssueInfo.score_change_surface` field docstring names "Change Surface"; update if criterion label changes [Agent 2 finding]
- (Optional) `docs/reference/ISSUE_TEMPLATE.md` — field row names "Change Surface" and "Criterion D" in the Frontmatter Fields table; update description string if criterion name changes [Agent 2 finding]
- (Optional) `docs/reference/API.md` if it cross-references the rubric (audit before editing — most references are by name only).
- (Optional) `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` if it discusses confidence scoring approaches (audit before editing).
- (Optional) `docs/reference/COMMANDS.md` if it reproduces the rubric inline (audit before editing).

### Dependent Files (Callers/Importers)
The rubric is LLM-applied prose; "callers" are commands/skills/loops that invoke `/ll:confidence-check`. None of these need code changes — they observe a numeric `score_change_surface` (0/10/18/25) whose shape is unchanged. Listed for awareness during verification:
- **Skills**: `skills/manage-issue/SKILL.md`, `skills/issue-workflow/SKILL.md`, `skills/decide-issue/SKILL.md`, `skills/wire-issue/SKILL.md`, `skills/issue-size-review/SKILL.md`.
- **Commands**: `commands/refine-issue.md`, `commands/create-sprint.md`, `commands/help.md`.
- **FSM loops**: `scripts/little_loops/loops/autodev.yaml`, `scripts/little_loops/loops/issue-refinement.yaml`, `scripts/little_loops/loops/refine-to-ready-issue.yaml`, `scripts/little_loops/loops/recursive-refine.yaml`.
- **CLI plumbing (no change required)**: `scripts/little_loops/cli/issues/set_scores.py:46-47` (handles `score_change_surface` frontmatter write); `scripts/little_loops/cli/issues/__init__.py` (registers `--score-change-surface` flag).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass has `score_change_surface` field (lines 241-246); no code change required — rubric refinement is upstream of the field definition [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_readiness.py` — validates `outcome_confidence` against configured thresholds; no code change required [Agent 1 finding]
- `scripts/little_loops/cli/issues/refine_status.py` — displays `score_change_surface` in `ll-issues refine-status` output; no code change required [Agent 1 finding]
- `scripts/little_loops/cli/issues/show.py` — shows `score_change_surface` in `ll-issues show` JSON/table output; no code change required [Agent 1 finding]
- `scripts/little_loops/config/features.py` — reads `outcome_confidence` for confidence-first sort strategy; no code change required [Agent 1 finding]

### Similar Patterns
- **Dual-pattern / type-fork rubric template**: `skills/confidence-check/SKILL.md:219-263` (Criterion 3 — the only existing forked criterion in the file). Uses bold-labeled per-variant headings and one full scoring table per branch under a single criterion. Direct model for the new Pattern A / Pattern B Criterion D layout.
- **Single-table criterion template** (style baseline for the unforked headers): Criteria A, B, and C in `skills/confidence-check/SKILL.md` (the file has Criteria A-D only — there is no Criterion E despite the original capture's wording).
- **Signal-phrase suppression / flag-write template**: `skills/confidence-check/SKILL.md:471-511` (Phases 4.6 and 4.7) — boilerplate for the new Phase 4.8: `Skip if CHECK_MODE`, `**Signal phrases**` bullet list, idempotent Edit on frontmatter, terminal log line.
- **Detection-heuristic preamble precedents** for the Pattern A vs B classifier: `skills/format-issue/SKILL.md:161-171` (keyword-count signal scan) and `skills/decide-issue/SKILL.md:96-118` (regex-pattern option-detection ladder).
- **Inline worked-example table format**: `skills/confidence-check/SKILL.md:650-657` (Scenario | Readiness | Outcome | Interpretation) and `skills/issue-size-review/SKILL.md:112-119` (criterion + points + how-to-detect columns).

### Tests
- `scripts/tests/test_confidence_check_skill.py` — primary skill unit-test file; check whether its style supports prose-rubric assertions (e.g. presence of "Pattern A" and "Pattern B" headings) and add a small regression assertion if so.
- `scripts/tests/test_set_scores_cli.py` — covers `--score-change-surface` CLI behavior; **no change needed** (rubric refinement is upstream of the CLI, score-write contract is unchanged).
- **Live-verification artifact** (primary): re-run `/ll:confidence-check` on FEAT-1407 (Pattern B comparator) and on one Pattern A code-fanout issue (e.g. a recent BUG-13xx with many call sites) and capture before/after `outcome_confidence`.

_Wiring pass added by `/ll:wire-issue`:_

**Tests to write** (new classes in `scripts/tests/test_confidence_check_skill.py`, following the `_phase_text()` heading-search pattern used by `TestDecisionNeededFlagWriteBack` and `TestMissingArtifactsFlagWriteBack`):

```python
class TestCriterionDDualPattern:
    """Criterion D must distinguish Pattern A (code blast radius) from Pattern B (enumerated mechanical fanout)."""

    def _criterion_d_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("#### Criterion D:")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_pattern_a_heading_present(self) -> None:
        assert "Pattern A" in self._criterion_d_text()

    def test_pattern_b_heading_present(self) -> None:
        assert "Pattern B" in self._criterion_d_text()

    def test_verifiability_table_row_present(self) -> None:
        assert "verification grep" in self._criterion_d_text()

    def test_original_count_table_retained_for_pattern_a(self) -> None:
        assert "0-2 callers" in self._criterion_d_text()


class TestPhase48LargeFileSurfaceSuppression:
    """Phase 4.8 must exist and mirror the Phase 4.6/4.7 boilerplate."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.8:")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_8_heading_exists(self) -> None:
        assert "Phase 4.8:" in SKILL_FILE.read_text()

    def test_check_mode_guard_present(self) -> None:
        assert "CHECK_MODE" in self._phase_text()

    def test_no_ask_user_question(self) -> None:
        assert "AskUserQuestion" not in self._phase_text()

    def test_signal_phrases_documented(self) -> None:
        text = self._phase_text()
        assert "large file surface" in text or "Signal phrases" in text
```

**Tests unaffected** (no code changes needed — field name, type, and CLI contract are unchanged):
- `scripts/tests/test_set_scores_cli.py` — test values are arbitrary, not scoring-table milestones
- `scripts/tests/test_issue_parser.py` — roundtrip parse/display of `score_change_surface`; arbitrary fixture values
- `scripts/tests/test_refine_status.py` — display behavior unchanged; uses arbitrary fixture values
- `scripts/tests/test_issues_cli.py` — round-trip parsing/display tests; unaffected
- `scripts/tests/test_builtin_loops.py` — FSM state topology tests; routing unchanged
- `scripts/tests/test_issue_size_review_skill.py` — reads `outcome_confidence`; unaffected
- `scripts/tests/test_action.py` — tests skill invocation mechanics; unaffected

### Documentation
- (Optional) `docs/reference/API.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `docs/reference/COMMANDS.md` — audit each before editing; most reference confidence-check by name without reproducing the rubric.

### Configuration
- N/A

## Impact

- **Priority**: P3 — improves the informativeness of an existing metric; not blocking, but the current state is actively misleading on a recurring issue archetype.
- **Effort**: Small — single skill file edit, ~30-50 lines of rubric content; verification by re-running confidence-check on FEAT-1407 and one code-fanout comparator.
- **Risk**: Low — touches a scoring rubric the LLM applies; no infrastructure or schema changes; reversible.
- **Breaking Change**: No. Existing scored issues retain their stored scores; only future scoring runs are affected.

## Labels

`enhancement`, `confidence-check`, `rubric`, `captured`

## Related

- FEAT-1407: the trigger case — 43-file mechanical sweep scoring 60 outcome_confidence despite full enumeration + verification grep + planned wiring test.
- FEAT-1389: parent EPIC; future children may hit the same scoring pattern.
- ENH-1413: sibling refinement — split Criterion A (Complexity) into Breadth × Depth to fix the file-count double-count between A and D. Composes with this issue but is independently mergeable.

## Session Log
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2c7ce99-47aa-48a1-876b-c2f744b66423.jsonl`
- `/ll:wire-issue` - 2026-05-10T04:08:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62659fe4-d489-47aa-b301-b9bdee7803ac.jsonl`
- `/ll:refine-issue` - 2026-05-10T03:46:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d75ce7f-2881-4167-a665-bd1bbb4f69da.jsonl`
- `/ll:format-issue` - 2026-05-10T02:01:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/983e540e-227c-4cd1-bd1c-d34619c7c558.jsonl`
- `/ll:capture-issue` - 2026-05-10T00:49:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba13deab-d917-4b01-b05e-c45e8583e56f.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P3
