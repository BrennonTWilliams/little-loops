---
id: BUG-3448
type: BUG
title: 'main suite red: priority-regex allowlist drift in mcp_server/tools.py and
  corpus baseline 569>562'
priority: P2
status: open
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T06:12:59Z'
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3448: main suite red: priority-regex allowlist drift in mcp_server/tools.py and corpus baseline 569>562

## Summary

The authoritative test gate on `main` fails 3 tests in `scripts/tests/test_issue_parser.py`
for reasons unrelated to any individual change: the priority-regex allowlist drifted out
of sync with `scripts/little_loops/mcp_server/tools.py` (line-number drift), and the
corpus-differential baseline constant no longer matches the grown `.issues/` corpus
(569 > 562). Both are stale-test-constant bugs, not production regressions.

## Current Behavior

`python -m pytest scripts/tests/` on `main` (verified 2026-09-11 at f1905f8e1^, with and
without unrelated working-tree changes) fails 3 tests in `scripts/tests/test_issue_parser.py`:

- `TestPriorityRegexCompletenessAllowlist::test_no_unallowlisted_raw_priority_regex` —
  `new raw priority regex not in the allowlist: {'mcp_server/tools.py': [846, 1001]}`
- `TestPriorityRegexCompletenessAllowlist::test_allowlist_entries_still_exist` —
  `stale allowlist entries: ['mcp_server/tools.py:795', 'mcp_server/tools.py:941']`
- `TestBug3295ContainmentCorpusDifferential::test_total_report_count_does_not_exceed_post_bug_3413_baseline` —
  `corpus report total 569 exceeds post-BUG-3413 baseline 562`

## Expected Behavior

- The authoritative local gate (`python -m pytest scripts/tests/`) exits 0 on `main`.
- The priority-regex allowlist matches HEAD's `scripts/little_loops/mcp_server/tools.py`
  (new raw regexes at lines 846/1001 either allowlisted with justification or converted
  to `resolve_priority`; stale entries at 795/941 removed).
- The corpus differential baseline accounts for the current `.issues/` corpus size (569).

## Impact

- **Priority**: P2 — the authoritative CI gate (`python -m pytest scripts/tests/`, run by
  the self-hosted runner on every push to `main`) is red for reasons unrelated to any
  individual change, masking real regressions.
- **Effort**: Small — allowlist line-number refresh + baseline bump (or making the
  baseline corpus-relative).
- **Risk**: Low — test-infra only.

Discovered during BUG-3443's full-suite verification (failures reproduced with the
BUG-3443 edit stashed, proving pre-existence on `main`).

## Steps to Reproduce

1. `python -m pytest scripts/tests/test_issue_parser.py -k "Allowlist or total_report_count"`
2. Observe the 3 failures above.

## Root Cause

- `scripts/little_loops/mcp_server/tools.py` moved/grew (most recently 3fe6a1dac
  `feat(mcp): add skills_list`) without updating the raw-priority-regex allowlist in
  `test_issue_parser.py` — line drift made entries 795/941 stale and exposed 846/1001.
- The `.issues/` corpus grew past the hard-coded `_POST_BUG_3413_TOTAL_REPORTS = 562`
  baseline; the count is a corpus-size function, so recent issue creation (BUG-3443
  session-log appends, BUG-3447 edits) trips it.
- [Review 2026-09-11] A second file drifted after capture: subsequent
  `issue_parser.py` commits (most recently 1fb35f5a9) shifted the four allowlisted
  raw-regex lines there by +40, so the same failing allowlist pair now also reports
  `issue_parser.py` stale entries and unallowlisted replacements. Same failure mode,
  same refresh treatment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Exact anchors: the stale allowlist entry is the `"mcp_server/tools.py": {795: ..., 941: ...}` dict at `scripts/tests/test_issue_parser.py:4887-4889`; the failing baseline constant `_POST_BUG_3413_TOTAL_REPORTS = 562` sits at `:5763` with its succession comment at `:5751-5762`; the baseline sweep `rglob("*.md")` over all of `.issues/` at `:5792` includes done/cancelled files, so mere issue creation grows the total.
- This is the third recorded position for the same two conceptual allowlist entries: 588/683 (BUG-3286 survivor table) → 795/941 (allowlist) → 846/1001 (current). Both current hits are JSON-schema fields `"pattern": "^P[0-5]$"` for the `priority` arguments of the MCP tools registered as `issues_query` and `issue_capture` (implemented by `_tool_issues_query` at `scripts/little_loops/mcp_server/tools.py:81` and `_tool_issue_capture` at `:258`) — added/shifted by `3fe6a1dac feat(mcp): add skills_list`, same category both prior generations were allowlisted under.
- The allowlist's own maintenance comment (`test_issue_parser.py:4819-4823`) anticipates this exact failure mode: "Re-derive line numbers by re-running the scan below if this test fails after an unrelated edit shifts lines."
- [Review 2026-09-11] Live re-run of the two failing allowlist tests reports a second drifted file beyond the two above: stale `issue_parser.py` entries at 1916/4060/4064/4085 with their replacements at 1956/4100/4104/4125 — a uniform +40 shift of the same four allowlisted regexes (`_DEP_ID_RE`, the filename-shape comment, `_parse_type_and_id`'s directory-fallback extraction, `_generate_id_from_filename`'s prefix strip). Categories are unchanged, so these are in-place line-number refreshes keeping the existing justification strings; no new convert-vs-allowlist discrimination needed beyond confirming the regexes themselves are unmodified at the new positions.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

**Option A**: Add a new successively-named ceiling constant (e.g. `_POST_BUG_3448_TOTAL_REPORTS = 569`, re-measured at fix time), leaving `_POST_BUG_3413_TOTAL_REPORTS = 562` in place as documented history — matching the in-file succession convention (525 → 490 → 535 → 562, `scripts/tests/test_issue_parser.py:5751-5762`) where each corpus widening added a new named constant rather than bumping the old one.

> **Selected:** Option A — replicates the BUG-3413 succession precedent exactly (reuse 3/3, zero new infrastructure); scored 11/12 vs Option B 5/12. See Decision Rationale below.

**Option B**: Replace the absolute ceiling with a corpus-relative ceiling (`_max_total_reports(corpus_md_count)`) or a managed regenerable baseline (a JSON data file regenerated wholesale by a CLI flag, the shape held by `scripts/little_loops/cli/verify_evidence.py:1937-1954`) so mere issue creation no longer trips the gate. No existing test in the suite uses a corpus-relative ceiling (nearest precedent: CLI-regenerated JSON baselines); note this issue's Program Design calls this "preferred if the differential's signal is per-file rather than absolute-count based", and the test does carry per-file signal (`_PINNED_CLEARED` frozenset at `test_issue_parser.py:5743`).

**Recommended**: Option A — matches the established succession convention exactly, is test-infra-only, and is the fastest path to un-reding the authoritative gate; revisit Option B as its own enhancement if the baseline trips again from corpus growth alone.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-11.

**Selected**: Option A

**Reasoning**: Option A replicates the suite's one recorded ceiling-succession event — BUG-3413 added `_POST_BUG_3413_TOTAL_REPORTS = 562` and retained `_PRE_FIX_TOTAL_REPORTS = 525` as dead documented history (`scripts/tests/test_issue_parser.py:5751-5763`) — reusing the sweep loop, assert shape, and failure message verbatim with zero new infrastructure (evidence-agent reuse score 3/3). Option B's corpus-relative half (`_max_total_reports(corpus_md_count)`) has zero precedent anywhere in the repo, and its managed-baseline half would need a test-side CLI-regenerated JSON data file that contradicts Implementation Step 4 (`git diff --stat scripts/little_loops/` empty) while still requiring an absolute counterweight per the `test_baseline_size_is_bounded` precedent (`scripts/tests/test_verify_evidence.py:1077-1081`) — shifting sensitivity from corpus growth to backlog growth rather than eliminating it.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- On Option A: exact BUG-3413 precedent (new bug-named constant, old constant retained, assert swap, test named for the ceiling-setting bug). Caveat carried forward: the succession is a single recorded event — intermediate totals 490/535 were comment-recorded, not constants — and the absolute-ceiling shape remains the only corpus-gate shape that trips from corpus growth alone; revisit Option B as its own enhancement if the gate trips again from corpus growth alone.
- On Option B: strong pattern-level precedent (two production `--update-baseline` CLIs with full test matrices) but no drop-in utilities — `regressions()` is payload-typed to `PrivateRefFinding`; `_max_total_reports` is entirely novel test machinery.

## Program Design

### Types

- No new production types — this is test-infra only; both fixes are test-constant
  refreshes in `scripts/tests/test_issue_parser.py`.

### Signatures

- `_ALLOWLIST: dict[str, dict[int, str]]` — refreshed dict literal: the
  `mcp_server/tools.py` entries `{795: ..., 941: ...}` replaced by `{846: ..., 1001: ...}`,
  each with a justification string, after confirming the raw regexes at the new lines
  can't trivially use `resolve_priority`; plus the `issue_parser.py` entries
  `{1916, 4060, 4064, 4085}` replaced by `{1956, 4100, 4104, 4125}` keeping their
  existing justification strings (uniform +40 line shift, categories unchanged —
  see Review finding in Root Cause research)
- `_POST_BUG_3413_TOTAL_REPORTS: int` — `562` bumped to `569` (measured at fix time), or
  replaced by a corpus-relative ceiling so mere issue creation no longer trips the gate
- `_max_total_reports(corpus_md_count: int) -> int` — optional corpus-relative ceiling
  helper, the preferred alternative to the constant bump if the differential's signal
  is per-file rather than absolute-count based

### Call Path

`test_no_unallowlisted_raw_priority_regex` → `_ALLOWLIST` (refreshed) → raw-regex scan of
`scripts/little_loops/mcp_server/tools.py`; and
`test_total_report_count_does_not_exceed_post_bug_3413_baseline` →
`_POST_BUG_3413_TOTAL_REPORTS` (bumped or corpus-relative) → corpus differential total
over `.issues/`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Convert-vs-allowlist discriminator (BUG-3286): a raw `P[0-5]`/`P\d` regex must convert to `resolve_priority` (`scripts/little_loops/issue_parser.py:92`) only when it resolves planning priority from an issue **filename**; JSON-schema patterns for CLI/MCP argument values are allowlisted under a categorical justification. Both new hits (`tools.py:846`, `:1001`) are the latter → allowlist, not convert. Complete production `resolve_priority` call-site list: `sync.py:327`, `cli/issues/format_check.py:360`, `cli/issues/show.py:82`, `issue_parser.py:4024`, `cli/issues/normalize.py:145`.
- No corpus-relative ceiling helper of the `_max_total_reports` shape exists anywhere in `scripts/tests/` (searched unfiltered); every existing live-corpus gate is an absolute constant ceiling, an exact per-file pin, an expect-empty assert, or a managed JSON baseline regenerated by CLI flag. The corpus-relative option is therefore novel test machinery, not an existing pattern being reused.
- Allowlist justification string formula held by existing entries: `"<what it is>, not <the policed thing>"` — the prior mcp entries read "JSON-schema pattern for a priority argument, not a filename read"; the refreshed entries should follow the same shape.

## Integration Map

### Files to Modify

- `scripts/tests/test_issue_parser.py` — the only file needing edits: the `_ALLOWLIST` `"mcp_server/tools.py"` entry (`:4887-4889`), the `_ALLOWLIST` `"issue_parser.py"` block (`:4867-4881`, four line-number refreshes — see Review findings), and the corpus ceiling constant(s) (`:5751-5763`)
  > ⚠ Superseded — issue's own prose also needs edits

### Dependent Files (Callers/Importers)

- None — test-infra only. `scripts/little_loops/mcp_server/tools.py` is scanned by the test, not modified; `resolve_priority` and its five production call sites are read for the discriminator, not changed.

_Wiring pass added by `/ll:wire-issue`:_
- Informational, no edits needed — suite-exit-code consumers currently red-blocked by this bug and unblocked by the fix: loop verify states (`scripts/little_loops/loops/general-task.yaml` `run_final_tests`, `fix-quality-and-tests.yaml`, `auto-refine-and-implement.yaml`, `evaluation-quality.yaml`, `oracles/code-run-gate.yaml`) and the EPIC verify gate (`scripts/little_loops/parallel/orchestrator.py` `_verify_branch`), all via `.ll/ll-config.json` `test_cmd`; `scripts/little_loops/prepatch_check.py` runs only diff-derived node IDs [Agent 2 finding]. Confirmed no external code imports or calls the `_ALLOWLIST` or baseline constants (repo-wide, 0 hits) [Agent 1 finding]

### Conventions in Force

- Corpus-total baselines pin an absolute ceiling constant named for the owning bug, with the measured total recomputed from live `.issues/` at runtime; superseded constants stay in place as documented history — evidence: succession 525 → 490 → 535 → 562 at `test_issue_parser.py:5751-5762`
- When an unrelated edit shifts lines, the allowlist maintenance protocol is to re-derive line numbers by re-running the scan, not to loosen the guard — evidence: `test_issue_parser.py:4819-4823`
- Corpus guards that expect a permanently-empty offender set assert emptiness with no baseline constant (immune to corpus growth by construction) — evidence: `TestCorpusHasNoPriorityDrift` (`test_issue_parser.py:4766`), `test_prose_dep_sweep_gate.py:23`

### Tests

- `scripts/tests/test_issue_parser.py:4804` — `TestPriorityRegexCompletenessAllowlist`: the failing pair (`test_no_unallowlisted_raw_priority_regex` `:4904`, `test_allowlist_entries_still_exist` `:4931`); both directions must pass after the refresh
- `scripts/tests/test_issue_parser.py:5729` — `TestBug3295ContainmentCorpusDifferential`: the failing baseline test plus `_PINNED_CLEARED` per-file clears (`:5743`, `:5765`), which must keep passing untouched
- `scripts/tests/test_issue_parser.py:85` — `TestResolvePriority`: the resolver contract; unchanged by this fix but shares the file
- `scripts/tests/test_enh_3444_mcp_skills_list.py` — covers the `skills_list` tool whose addition (3fe6a1dac) shifted `tools.py` lines; unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_evidence.py:1027` — `TestRepoGate::test_no_new_unverifiable_evidence`: a **4th red test on `main`** (live-confirmed 2026-09-11 at HEAD; also recorded in the P3-BUG-3447 and P2-FEAT-3445 verification notes). Currently failing on 2 evidence-unverifiable spans **in this issue's own file** — [Current Behavior] at `:30` and [Root Cause] at `:64` — so fixing the 3 named tests alone does not green the suite [Agent 2+3 finding, live-verified]
- `scripts/tests/test_feat3304_artifact_dashboard.py:648-668` — `TestAllowlistVersionLockstep::test_allowlist_and_version_change_together`: closest pattern if a retention guard for the superseded `562` constant is wanted; no existing test enforces superseded-constant retention (convention only) [Agent 3 finding]

### Documentation

- None required — test-infra only. (`docs/reference/API.md:924` / `docs/reference/CLI.md:2338` describe the `priority_drift` production gate, not these tests.)

## Implementation Steps

1. The allowlist matches HEAD: `tools.py:846` and `:1001` entered with categorical justifications (JSON-schema priority-arg pattern, not a filename read), `795`/`941` removed; `issue_parser.py` entries `1916/4060/4064/4085` refreshed to `1956/4100/4104/4125` with existing justifications kept — verified by `python -m pytest scripts/tests/test_issue_parser.py -k "Allowlist"` exiting 0
2. The corpus differential holds for the current corpus under the option selected from Proposed Solution (constant succession or corpus-relative ceiling) — verified by `python -m pytest scripts/tests/test_issue_parser.py -k "total_report_count"` exiting 0
3. The authoritative gate is green: `python -m pytest scripts/tests/` exits 0
   > ⚠ Superseded — 4th red test also blocks suite exit 0
4. No production file changes accompany the fix: `git diff --stat scripts/little_loops/` is empty

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Clear the 2 evidence-unverifiable spans in this issue's own prose — in [Current Behavior], the verbatim allowlist-failure message attributed to `test_issue_parser.py`, and in [Root Cause], the commit subject attributed to the `tools.py` path — by rephrasing the quote/attribution or suppressing a reviewed counter-example, so `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` passes and the gate can reach exit 0. Identify the spans by content, not by the line numbers recorded above: they move with any edit to this file (the wiring pass recorded them at 30/64; the review re-run found them at 36/70).

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- Review (pre-implementation, Claude Code session) - 2026-09-11 - `session_01Ufn7Lt5Vb6e8PjyCZg5eUs`
- `/ll:confidence-check` - 2026-09-11T15:33:50 - `8cdcde34-85c0-4f2c-9a74-cdf6cbe6dedb.jsonl`
- `/ll:wire-issue` - 2026-09-11T15:30:55 - `1132d6e1-b9ee-4bab-bed0-a3378ccc90b6.jsonl`
- `/ll:decide-issue` - 2026-09-11T15:17:37 - `7f075240-78da-40ae-8be8-2aed20585a34.jsonl`
- `/ll:refine-issue` - 2026-09-11T15:04:49 - `b43da4e6-a103-422c-95e7-8acd36afebbc.jsonl`
- `/ll:format-issue` - 2026-09-11T14:47:41 - `ea28103f-853d-4789-8f33-11dd1c461351.jsonl`
