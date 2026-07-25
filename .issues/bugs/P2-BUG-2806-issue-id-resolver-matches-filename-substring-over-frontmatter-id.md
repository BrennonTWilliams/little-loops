---
id: BUG-2806
title: Issue ID resolver matches filename substring before frontmatter id (EPIC-2456
  resolved to ENH-2719)
type: BUG
priority: P2
status: done
captured_at: '2026-07-25T18:20:00Z'
completed_at: '2026-07-25T18:49:54Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- issues
- cli
confidence_score: 100
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
---

# BUG-2806: Issue ID resolver matches filename substring before frontmatter id

## Summary

`ll-issues set-status EPIC-2456 done` and `ll-issues path EPIC-2456` both
resolved to `.issues/enhancements/P2-ENH-2719-epic-2456-realized-savings-verification-and-closure-gate.md`
(frontmatter `id: ENH-2719`) instead of
`.issues/epics/P2-EPIC-2456-token-cost-reduction.md` (frontmatter
`id: EPIC-2456`). The ENH's filename contains the lowercase substring
`epic-2456`, and the resolver apparently matches on filename substring
before (or instead of) the frontmatter `id:` field.

## Reproduction

Observed 2026-07-25 with both files present:

```
$ ll-issues set-status EPIC-2456 done
EPIC-2456: done → done          # actually re-stamped ENH-2719 (already done)
$ ll-issues path EPIC-2456
.issues/enhancements/P2-ENH-2719-epic-2456-realized-savings-verification-and-closure-gate.md
```

The epic file itself still had `status: open` afterward and had to be edited
manually.

## Impact

Silent wrong-file writes: any issue whose slug embeds another issue's ID
(a common pattern for closure-gate / follow-up issues named after their
parent) can shadow that ID for every `ll-issues` ID-based operation —
`set-status`, `path`, `show`, likely others sharing the resolver. Automation
(autodev's `mark_deferred`/`set-status` states) would corrupt the wrong
issue's status without any error.

## Expected Behavior

ID resolution must match the frontmatter `id:` field exactly (or the
filename's structured `[TYPE]-[NNN]` segment with type equality), never a
bare substring of the slug. `EPIC-2456` must resolve only to the file whose
frontmatter says `id: EPIC-2456`; if no such file exists, error — not
fall back to a slug substring match.

## Root Cause (suspected)

The shared file-lookup helper in `scripts/little_loops/` issue tooling
(used by `set-status`/`path`/`show`) globs for `*{issue_id.lower()}*` in
filenames rather than parsing frontmatter `id:`. Not yet confirmed —
locate the resolver and confirm before fixing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed.** The resolver is `_resolve_issue_id()` in
  `scripts/little_loops/cli/issues/show.py:39-128`. It never reads
  frontmatter `id:` at all — it parses the user's input into
  `type_prefix`/`numeric_id` (e.g. `EPIC`/`2456`), then globs
  `search_dir.glob(f"*-{numeric_id}-*.md")` (line 107). This matches the
  numeric token anywhere in the filename, including inside the slug
  portion, not just the file's own structured `TYPE-NNN` prefix.
- Type disambiguation (`_matches_type()`, lines 112-114) is also
  filename-substring based: `f"-{type_prefix}-" in path.name.upper()`.
  For `EPIC-2456`, this matches `-EPIC-2456-` embedded inside
  `P2-ENH-2719-epic-2456-realized-savings-...md`'s slug just as validly
  as a genuine `EPIC-...` prefixed file.
- If no filename in the candidate pool matches `_matches_type`, the code
  **silently falls back to the full unfiltered `candidates` list**
  (lines 118-120) — documented as intentional "advisory, not required"
  behavior for a different bug (BUG-2003 stale-prefix tolerance), but it
  is also the fallback path that lets a substring decoy through when the
  genuine file is absent or sorts after it.
- No call to `little_loops.frontmatter.parse_frontmatter()` (or any
  frontmatter `id:` comparison) happens anywhere in `_resolve_issue_id()`
  before a path is chosen and returned.
- **Existing precedent for the correct approach**:
  `scripts/little_loops/issue_parser.py:check_format_gaps()` (lines
  273-280) already compares frontmatter `id:` against a
  filename-derived canonical ID via `_FILENAME_ID_RE`
  (`re.compile(r"(BUG|FEAT|ENH|EPIC)-(\d+)")`, `issue_parser.py:29-31`)
  for its `malformed_id` gap class — the closest in-repo pattern for
  "frontmatter id vs. filename id" reconciliation, though note
  `_FILENAME_ID_RE.search()` itself only anchors on the *first*
  `TYPE-NNN` occurrence and doesn't distinguish structural prefix
  position from a slug-embedded substring, so it isn't a drop-in fix by
  itself — matching must ultimately validate against the file's parsed
  frontmatter `id:`, not just a stricter filename regex.
- A separate, unrelated resolver exists at
  `scripts/little_loops/sprint.py:412 _find_issue_path()` (used only by
  the sprint subsystem) with the same substring-glob shape
  (`f"*-{issue_id}-*.md"`) — worth checking whether it shares this bug,
  though it's out of scope for `set-status`/`path`/`show`.

#### Integration Map

**Files to modify**
- `scripts/little_loops/cli/issues/show.py` — `_resolve_issue_id()`
  (lines 39-128): the single chokepoint fix. Needs to validate
  candidates against parsed frontmatter `id:` (via
  `little_loops.frontmatter.parse_frontmatter()`) rather than filename
  substrings, before falling back to the current advisory-prefix
  behavior for BUG-2003 compatibility.

**Callers (all resolve through the same function — a single fix propagates to all)**
- `scripts/little_loops/cli/issues/path_cmd.py:cmd_path()` (line 24-27) — `ll-issues path`
- `scripts/little_loops/cli/issues/set_status.py:cmd_set_status()` (line 46, 91) — `ll-issues set-status`
- `scripts/little_loops/cli/issues/show.py:cmd_show()` (line 818, 829) — `ll-issues show`
- `scripts/little_loops/cli/issues/set_scores.py` (line 27, 30)
- `scripts/little_loops/cli/issues/check_readiness.py` (line 28, 44)
- `scripts/little_loops/cli/issues/check_flag.py` (line 23, 26)
- `scripts/little_loops/cli/issues/skip.py` (line 29, 33)
- `scripts/little_loops/cli/issues/format_check.py` (line 41, 46)
- `scripts/little_loops/cli/issues/check_decidable.py` (line 26, 29)
- `scripts/little_loops/cli/issues/check_open_questions.py` (line 47, 53)
- `scripts/little_loops/cli/history_context.py` (line 97, 99) — `ll-history-context`
- `scripts/little_loops/loops/rn-remediate.yaml` (line 345, 352) — FSM inline-import call on `$ID`
- `scripts/little_loops/loops/autodev.yaml` (multiple `set-status` call sites) — production dequeue/deferral machinery

**Reusable utilities**
- `little_loops.frontmatter.parse_frontmatter()` (`scripts/little_loops/frontmatter.py:30-95`) — canonical frontmatter parser, already used elsewhere for exact `id:` comparisons; the fix should call this per-candidate rather than re-implementing YAML parsing.
- `scripts/little_loops/cli_args.py:_id_matches()` (lines 290-310) — existing example of exact-equality ID matching (`candidate == pattern`) elsewhere in the codebase, in contrast to `_resolve_issue_id`'s substring `in` checks.

**Tests**
- `scripts/tests/test_show.py:TestResolveIssueId` (lines 74-166) — unit tests for `_resolve_issue_id()`. `test_priority_hint_breaks_tie` (lines 119-132) is the closest existing template for a new regression test: construct two files where one's filename slug embeds the other's numeric ID (mirroring the `EPIC-2456`/`ENH-2719` repro), and assert the frontmatter-`id`-bearing file wins. Existing convention: cite the bug in the test docstring, e.g. `"""... (BUG-2806)"""`, matching `test_priority_hint_breaks_tie`'s `(BUG-2003)`/`(BUG-2733)` style.
- `scripts/tests/test_issues_path.py` — `ll-issues path` CLI-level test coverage; no existing case for substring-shadowing, needs one added alongside the unit test.
- `scripts/tests/test_set_status_cli.py` — `ll-issues set-status` CLI-level tests; same gap.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/sprint.py:412 _find_issue_path()` — a separate resolver with the identical substring-glob shape (`f"*-{issue_id}-*.md"`, line 427), used by `load_from_epic()`, `validate_issues()`, and `load_issue_infos()`. Confirmed genuinely independent of `show.py:_resolve_issue_id()` (no shared helper) and has **no test coverage at all** (grep across `scripts/tests/` finds only its definition site). Already correctly scoped out of this fix by the prior refine pass, but flagging the "untested" detail since a future fix there will need net-new test infrastructure, not just an extension of `test_show.py`'s fixtures.
- `scripts/little_loops/cli_args.py:_id_matches()` (line 290), `scripts/little_loops/issue_parser.py` (imports `_id_matches`, defines `_FILENAME_ID_RE`), `scripts/little_loops/issue_manager.py`, `scripts/little_loops/cli/sprint/run.py` — a related but architecturally separate exact-match utility family, already cited in Integration Map as "Reusable utilities." Confirmed via full-tree grep: none of these import or call `_resolve_issue_id()`, so no wiring changes needed here beyond the existing citation.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- **Fixture gap (must be fixed in the same change, not just added to)**: `scripts/tests/test_show.py:TestResolveIssueId._make_config_with_file()` (lines 77-87) and every inline fixture in the class (including `test_stale_type_prefix_falls_back_to_numeric` at lines 113-117, the BUG-2003 regression test) write frontmatter with `status:` only — **no `id:` field**. A naive "require frontmatter `id:` match" implementation fails every existing test in this class, including BUG-2003's own regression test, unless the fix explicitly treats a missing/absent `id:` as "no frontmatter opinion, fall through to current filename-derived matching" rather than outright rejection. The fix must special-case this, and this file's fixtures are the concrete proof of why.
- `scripts/tests/test_issues_path.py::TestPathPrefixTolerant` (lines 256-395, 6 tests) — these already write `id:` frontmatter via `_make_issue()` (line 19-24, derives `id:` from the title), but the `id:` value never matches the queried stale-prefix ID (that's the point of the test). Confirmed these should keep passing unmodified under frontmatter-first matching, since resolution falls through to the existing numeric-only fallback when no candidate's `id:` matches. No fixture changes needed here — listed for confirmation, not action.
- `scripts/little_loops/frontmatter.py:parse_frontmatter()` (line 30) signature confirmed: `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]`, takes raw file *content* (not a `Path`) and returns `{}` (not a raise) when no frontmatter block exists — the fix's per-candidate call must do `candidate.read_text()` then `.get("id")` with a guard for the fixture-gap case above.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `_resolve_issue_id()` in `scripts/little_loops/cli/issues/show.py` to validate candidates against `parse_frontmatter(candidate.read_text()).get("id")`, treating a missing/absent `id:` as "no opinion" (fall through to current filename-derived matching) rather than rejection.
2. Update `scripts/tests/test_show.py:TestResolveIssueId._make_config_with_file()` and all inline fixtures in the class to add `id:` frontmatter where the test intends an unambiguous frontmatter-backed match; leave BUG-2003's `test_stale_type_prefix_falls_back_to_numeric` fixture without `id:` to prove the "no frontmatter opinion" fallback path still works.
3. Add the new BUG-2806 regression test to `scripts/tests/test_show.py:TestResolveIssueId`, following `test_priority_hint_breaks_tie`'s inline-fixture shape: two files where one's slug embeds the other's numeric ID, asserting the frontmatter-`id`-bearing file wins.
4. Add corresponding CLI-level regression tests to `scripts/tests/test_issues_path.py` and `scripts/tests/test_set_status_cli.py` for the same collision shape.
5. Confirm `scripts/tests/test_issues_path.py::TestPathPrefixTolerant`'s 6 existing tests still pass unmodified (no fixture changes expected there).

## Resolution

`_resolve_issue_id()` (`scripts/little_loops/cli/issues/show.py`) now checks
each numeric-matched candidate's frontmatter `id:` field (via
`parse_frontmatter()`) before falling back to filename-derived matching. When
a candidate's frontmatter `id:` exactly matches the requested `TYPE-NNN`, it
is preferred outright over any other candidate whose filename slug merely
embeds the same digits as a substring. A candidate with no `id:` field is
treated as "no opinion" and still participates in the existing
filename-substring/type-prefix/priority fallback chain, preserving BUG-2003's
stale-type-prefix tolerance and BUG-2733's legacy-dir resolution.

Added regression coverage: `test_show.py::test_frontmatter_id_wins_over_slug_embedded_substring`,
`test_issues_path.py::TestPathFrontmatterIdWinsOverSubstring::test_epic_resolves_over_slug_embedded_enh`,
and `test_set_status_cli.py::test_set_status_frontmatter_id_wins_over_slug_embedded_substring`,
all reproducing the `EPIC-2456`/`ENH-2719` collision shape from the bug report.
Existing `TestResolveIssueId` and `TestPathPrefixTolerant` fixtures were
updated to carry `id:` frontmatter where an unambiguous match was intended,
with `test_stale_type_prefix_falls_back_to_numeric` deliberately left without
`id:` to prove the no-opinion fallback path still works.

## Session Log
- `/ll:confidence-check` - 2026-07-25T00:00:00Z - `9bcb97d1-eeb4-40ba-aefc-97d0464ce27d.jsonl`
- `/ll:wire-issue` - 2026-07-25T18:39:13 - `477986e7-934b-48d8-804b-64e74a23715e.jsonl`
- `/ll:refine-issue` - 2026-07-25T18:33:22 - `7f0f8cd7-b461-4aa9-a899-652fc64b5d70.jsonl`
- `/ll:capture-issue` - 2026-07-25T18:20:00Z

---

## Status
- Status: open
