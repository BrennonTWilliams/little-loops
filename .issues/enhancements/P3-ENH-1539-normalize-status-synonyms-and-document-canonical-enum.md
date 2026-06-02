---
id: ENH-1539
type: enhancement
priority: P3
status: done
captured_at: '2026-05-17T03:25:34Z'
discovered_date: 2026-05-17
discovered_by: capture-issue
decision_needed: false
implementation_order_risk: true
confidence_score: 98
outcome_confidence: 50
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
size: Very Large
---

# ENH-1539: Normalize status synonyms and document canonical enum

## Summary

Coding agents periodically write non-canonical values into issue frontmatter `status:` — most commonly `complete` / `completed` / `finished` — instead of the canonical `done`. A snapshot of `.issues/` today shows 1410 files at `status: done` and 5 at `status: completed` (down from 20 at capture time, 2026-05-17), with a stray `status: proven` also present. Because every downstream consumer (`sync.py:277,985`, `issue_manager.py:790`, `issue_lifecycle.py:400`, `issue_discovery/search.py:73`, `cli/deps.py:55`) tests membership in `("done", ...)`, drifted values silently exclude issues from "completed" filters, GitHub close-sync, sprint skip logic, dependency validation, and history exports.

Fix with two complementary moves: (1) parser-level coercion that maps known synonyms to canonical values on read (and on write, where we control the path), and (2) a one-line canonical enum statement in `.claude/CLAUDE.md` and the issue-touching skills so agents stop generating drift in the first place.

## Current Behavior

- `.issues/**/*.md` files contain a mix of canonical and synonym status values; nothing rejects or rewrites them.
- `scripts/little_loops/issue_parser.py:488` already has a narrow normalization (`open` + `completed_at` → `done`), but it does not handle `complete`/`completed`/`finished` → `done`, nor `in_progress` variants.
- `issue_lifecycle.py:872` treats `("done", "cancelled", "deferred", "completed")` as terminal in *one* place but most call sites only check `("done", "cancelled")`, so `completed` is half-recognized — terminal-ish but invisible to GitHub close-sync, dependency validation, and sprint skip logic.
- There is no single authoritative enum documented anywhere agents reliably read. `docs/reference/CLI.md:557` lists the filter values inline, but `.claude/CLAUDE.md` and the issue-management skills (`capture-issue`, `ready-issue`, `manage-issue`, `format-issue`, etc.) never state the canonical set.

## Expected Behavior

- Any non-canonical synonym (`complete`, `completed`, `finished`, `in-progress`, `in progress`, plus the obvious truncations) is silently rewritten to its canonical form at parse time, so callers always observe `done` / `cancelled` / `deferred` / `open` / `in_progress` / `blocked`.
- The canonical enum is named once in `.claude/CLAUDE.md` and referenced (not duplicated) from the issue-touching skills, so an agent reading either gets the same answer.
- A one-shot cleanup pass rewrites the existing 20 `status: completed` files (and the handful of other drifts) to canonical values, so the on-disk state matches the parsed state.

## Motivation

- **Correctness, not cosmetics.** Every consumer of "is this issue done?" silently disagrees with every other consumer when the value is `completed` instead of `done`. `ll-sync` will not close the GitHub mirror; `ll-sprint` will not skip it; `ll-deps` will treat it as still-open for dependency validation. This is the kind of bug that surfaces as a deploy-time surprise, not a unit-test failure.
- **The drift is recurring.** This isn't a one-time cleanup — agents will keep generating `completed` until either (a) they read the enum somewhere they actually look, or (b) the parser fixes it for them. Without both, the cleanup pass will need to be re-run.
- **Existing infrastructure is close.** `issue_parser.py:488` already does the same kind of normalization for one specific case; extending it is cheap and localized.

## Proposed Solution

Two complementary changes:

### 1. Parser-level coercion (`issue_parser.py`)

Extend the existing normalization block near `issue_parser.py:488` with a synonym map applied to every parsed status, not just the `open` + `completed_at` case:

```python
STATUS_SYNONYMS = {
    "complete": "done",
    "completed": "done",
    "finished": "done",
    "closed": "done",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "wip": "in_progress",
}
raw_status = frontmatter.get("status", "open")
status = STATUS_SYNONYMS.get(raw_status, raw_status)
```

Apply the same map in `issue_lifecycle.set_status()` (or wherever frontmatter writes go) so values normalize on write as well as read. Decide separately whether to also write-back canonical values to disk on first read — leaning yes, gated behind a quiet log line, so the on-disk state self-heals over time.

### 2. Canonical enum statement in `.claude/CLAUDE.md` + issue-touching skills

Add a short subsection (≤5 lines) to `.claude/CLAUDE.md` under "Issue File Format" naming the canonical enum:

> **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace.

Reference (don't duplicate) this list from the issue-touching skill bodies — `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/format-issue/SKILL.md` — with a one-liner like "Status enum: see `.claude/CLAUDE.md` § Issue File Format."

### 3. One-time cleanup

Run a small script (or `ll-issues` subcommand if one fits) to rewrite the 20 `status: completed` files and the obvious truncations to canonical values. Commit as a single normalization pass.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — extend the existing normalization at line ~488 with the synonym map. Also remove now-dead `"completed"` from the terminal-state tuple in `find_issues()` at line ~872 (becomes unreachable once `completed` normalizes to `done` before the filter runs).
- `scripts/little_loops/issue_lifecycle.py` — apply the same map on write paths (`set_status`, the `("done", "cancelled")` checks at line 400 / 872 stay as-is since they now only ever see canonical values).
- `.claude/CLAUDE.md` — add the "Status values" subsection under "Issue File Format" near line 80-ish.
- `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/refine-issue/SKILL.md` — add the one-line reference to the canonical enum.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()` checks `issue_info.status in ("done", "cancelled", "deferred", "completed")`; the `"completed"` arm becomes dead code after normalization and should be removed to avoid misleading the reader.
- `scripts/little_loops/cli/issues/search.py` — `_load_issues_with_status()` (~line 134) checks status against a middle tuple `("done", "cancelled", "completed")`; same `"completed"` dead-code cleanup needed.
- `scripts/little_loops/frontmatter.py` (or normalize inside `parse_frontmatter()` directly) — **this is the preferred normalization site** so that all direct `parse_frontmatter()` callers (`verify_issue_completed`, `cli/sprint/edit.py`, `cli/sprint/run.py`, etc.) automatically benefit without each needing individual updates.

### Dependent Files (Callers/Importers)

`grep -rn 'status.*"done"' scripts/little_loops/` shows the consumers that benefit:

- `scripts/little_loops/sync.py:277,985` — GitHub close-sync filter
- `scripts/little_loops/issue_manager.py:790` — already-done guard
- `scripts/little_loops/issue_lifecycle.py:400,872` — terminal-state check
- `scripts/little_loops/issue_discovery/search.py:73,399` — duplicate / reopen flow
- `scripts/little_loops/cli/deps.py:43,55` — dependency validation completed-set
- `scripts/little_loops/parallel/orchestrator.py:1248` — orchestrator writes
- `scripts/little_loops/issue_history/parsing.py:330` — history filter

None of these need to change — they continue checking `("done", "cancelled")` and now see exclusively canonical values.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/edit.py` — calls `parse_frontmatter()` directly in a list comprehension (~line 75), checks `.get("status", "open") in ("done", "cancelled")`; benefits automatically if normalization is in `parse_frontmatter()` itself rather than `IssueParser.parse_file()`
- `scripts/little_loops/cli/sprint/run.py` — calls `parse_frontmatter()` directly in `run_sprint()` (~line 187), same check; same dependency on normalization level

**Critical wiring note**: `verify_issue_completed()` in `issue_lifecycle.py` calls `parse_frontmatter(path.read_text())` directly and checks `fm.get("status") in ("done", "cancelled")`. If normalization is placed only in `IssueParser.parse_file()`, `verify_issue_completed()` will still not catch synonyms like `completed`. **Normalization must be placed in `parse_frontmatter()` itself (or equivalently in the `frontmatter.py` module) to cover all callers.** The existing normalization at `issue_parser.py:487-489` is inside `IssueParser.parse_file()` — extending it there is insufficient for the `parse_frontmatter`-direct call sites above.

### Similar Patterns

- `issue_parser.py:488-489` is the existing precedent for parser-level status normalization. Extend it; don't duplicate.

### Tests

- `scripts/tests/test_issue_parser.py` (or equivalent) — add cases for each synonym in the map, plus a "unknown value passes through unchanged" case so we don't accidentally swallow real new statuses.
- `scripts/tests/test_issue_lifecycle.py` — verify `set_status("completed")` writes `done` to disk.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py`: `TestFindIssues.test_find_issues_skips_status_completed` — currently passes because `"completed"` is in the hard-coded skip set at line 872; after normalization the mechanism changes (normalization upstream → skip via `"done"`). The test will still pass, but consider adding an assertion that `info.status == "done"` (not `"completed"`) to document the new code path explicitly.
- `scripts/tests/test_issue_parser_properties.py` — `st.sampled_from(["open", "in_progress", "blocked", "deferred", "done", "cancelled"])` at lines 82 and 307. All values listed ARE canonical, so no change is needed — but verify after the STATUS_SYNONYMS dict is added that none of the canonical values accidentally appear in the synonym map (which would be a logic error).
- `scripts/tests/test_issue_lifecycle.py`: `TestVerifyIssueCompleted` — add a synonym test case: write `status: completed` to a fixture file, call `verify_issue_completed()`, assert it returns `True`. This test will fail until normalization is placed in `parse_frontmatter()` (not just `IssueParser.parse_file()`), making it a useful regression guard for the normalization level decision.

### Documentation

- `.claude/CLAUDE.md` — add the canonical enum subsection (see Proposed Solution).
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — already documents `done`; add a one-liner noting that synonyms are coerced on read/write so authors don't worry about it.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — documents `--status {open,in_progress,blocked,deferred,done,cancelled,all}` filter choices (~line 557); add a one-liner noting that synonyms in on-disk frontmatter are normalized on read, but CLI input must still use canonical values (argparse rejects synonyms before normalization runs).

### Configuration

- N/A.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — no `set_status()` exists**: The issue references `issue_lifecycle.set_status()` but this function does not exist. The actual write paths are four module-level functions that already write canonical string literals directly:
- `close_issue()` → `{"status": "done", "completed_at": ...}` (`issue_lifecycle.py:568`)
- `complete_issue_lifecycle()` → `{"status": "done", "completed_at": ...}` (`issue_lifecycle.py:634`)
- `defer_issue()` → `{"status": "deferred"}` (`issue_lifecycle.py:732`)
- `undefer_issue()` → `{"status": "open"}` (`issue_lifecycle.py:857`)

Since all write paths already emit canonical values, **parser-level coercion alone is sufficient**. Creating a `set_status(path, status)` helper as a central write path is optional and would future-proof against new callers.

**`STATUS_SYNONYMS` confirmed absent**: Grep for `STATUS_SYNONYMS`, `STATUS_ALIASES`, and `STATUS_MAP` across all Python files returns zero matches. The only normalization is the narrow block at `issue_parser.py:487-489`.

**Consumer asymmetry — which consumers handle `"completed"`**:

| Site | Recognizes `"completed"` as terminal? |
|------|--------------------------------------|
| `issue_parser.py:872` (`find_issues`) | Yes |
| `cli/issues/skip.py:40` | Yes |
| `cli/issues/search.py:138` | Yes |
| `issue_lifecycle.py:400` (`verify_issue_completed`) | **No** — misses it |
| `sync.py:277,985` | **No** — issues stay open on GitHub |
| `issue_manager.py:790` | **No** |
| `issue_discovery/search.py:72-80` | **No** — treats as open |
| `cli/deps.py:55` | **No** |
| `issue_history/parsing.py:330` | **No** — excludes from history |

**Canonical enum — authoritative source in code**: `scripts/little_loops/cli/issues/__init__.py` argparse `choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled", "all"]` (appears 3× in `list`, `count`, `sequence` subcommands). Note `"completed"` is absent from this list, confirming it is not canonical.

**`ISSUE_MANAGEMENT_GUIDE.md` already has a status table**: `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` lines 106-119 has `### Frontmatter status Values` with all 6 canonical values; only a one-line note about synonym coercion needs to be added there.

**Test fixtures available**: `scripts/tests/conftest.py` provides `temp_project_dir`, `sample_config`, `mock_logger`, and `sample_issue_info` fixtures. The `sample_issue_info` fixture creates a file at `tmp_path/.issues/bugs/P1-BUG-001-test-bug.md` with `status: open`.

## Implementation Steps

1. Extend `issue_parser.py:487-489` with a `STATUS_SYNONYMS` dict applied to every parsed status, not just the `open` + `completed_at` case. **Note**: `issue_lifecycle.set_status()` does not exist — existing write paths (`close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()`) already write canonical strings, so no write-path changes are needed unless creating a new central helper. Add unit tests in `scripts/tests/test_issue_parser.py` modeled after `TestFindIssues.test_find_issues_skips_status_done` — write frontmatter with `status: completed`, parse, assert `info.status == "done"`. Add a lifecycle test in `scripts/tests/test_issue_lifecycle.py` modeled after `TestVerifyIssueCompleted`, using the `write_text` + `parse_frontmatter()` assertion pattern with fixtures from `conftest.py`.
2. Add the canonical enum subsection to `.claude/CLAUDE.md` between the `Priorities` bullet (line 95) and `## Important Files` (line 97). Add a one-line synonym coercion note to `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:106-119` (the existing `### Frontmatter status Values` table). Add a one-line reference in each issue-touching skill: `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/ll-refine-issue/SKILL.md`.
3. Run a one-shot cleanup pass that rewrites the 5 remaining `status: completed` files (and any `status: in` truncations, `status: proven` outliers) to canonical values. Commit as a single normalization pass.
4. Verify with `grep -rn "status:" .issues/ | grep -oE "status: [a-z_]+" | sort -u` — the output should match the canonical enum exactly.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Normalization level decision**: Place `STATUS_SYNONYMS` normalization inside `parse_frontmatter()` (the low-level function in `frontmatter.py` or equivalent), NOT only in `IssueParser.parse_file()`. This ensures that all direct `parse_frontmatter()` callers — `verify_issue_completed()`, `cli/sprint/edit.py`, `cli/sprint/run.py`, `issue_manager.py:process_issue_inplace()` — benefit automatically without individual updates. The current precedent at `issue_parser.py:487-489` is inside `parse_file()`; move the normalization upstream.
6. **Dead-code cleanup** — once normalization runs, remove the now-unreachable `"completed"` arm from three terminal-state tuples:
   - `issue_parser.py:find_issues()` (line ~872): `("done", "cancelled", "deferred", "completed")` → remove `"completed"`
   - `cli/issues/skip.py:cmd_skip()`: same tuple pattern → remove `"completed"`
   - `cli/issues/search.py:_load_issues_with_status()` (~line 134): middle tuple `("done", "cancelled", "completed")` → remove `"completed"`
7. **Add synonym regression guard** in `scripts/tests/test_issue_lifecycle.py`: a `TestVerifyIssueCompleted` test that writes `status: completed` to a fixture file and asserts `verify_issue_completed()` returns `True`. This test fails until normalization is at the `parse_frontmatter()` level, so it serves as a gate on the normalization level decision (step 5).
8. Update `docs/reference/CLI.md` (~line 557): add a one-liner noting that synonyms in on-disk frontmatter are normalized on read, but CLI `--status` arguments must use canonical values (argparse validates choices before normalization runs).

## Impact

- **Priority**: P3 — silent miscategorization is real but the workaround (manually fix offending files) is trivial when noticed; no production impact.
- **Effort**: Small — ~30 lines of parser code, a doc subsection, plus a one-shot rewrite of 20-ish files.
- **Risk**: Low — additive normalization. The only way to regress is if someone is intentionally relying on `completed` being distinct from `done`, which `issue_lifecycle.py:872` already says it isn't.
- **Breaking Change**: No — parser-level coercion is invisible to callers, and the on-disk rewrite preserves semantic meaning.

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | guidelines | Target location for the canonical enum subsection; agents read this on every session. |
| [docs/reference/API.md](../../docs/reference/API.md) | architecture | `issue_parser`, `issue_lifecycle` modules are documented here; update if signatures change. |

## Labels

`enhancement`, `captured`, `status-normalization`, `agent-compliance`

## Status

**Open** | Created: 2026-05-17 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 50/100 → LOW

### Outcome Risk Factors

- **Broad call surface on `parse_frontmatter()`**: 48 callers across the codebase; even though the normalization is purely additive, not all callers have been audited for status-value dependencies. Run `grep -rn "parse_frontmatter\|\.get.*status" scripts/` after the change and spot-check the highest-traffic call sites.
- **Write tests before modifying `parse_frontmatter()`**: The `TestVerifyIssueCompleted` synonym regression test (step 7 of wiring phase) fails until normalization is placed in `parse_frontmatter()` rather than `IssueParser.parse_file()`. Implement this test first so it acts as a correctness gate confirming the normalization level is right before merging.
- **Cleanup script form unspecified**: Step 3 says "a small script or `ll-issues` subcommand if one fits" — decide before starting so cleanup isn't blocked at the end; a one-liner `sed` or short Python script is sufficient.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-17
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1549: Status synonym normalization — code implementation and tests
- ENH-1550: Status canonical enum — documentation and skill references
- ENH-1551: Status one-shot cleanup pass for non-canonical values in .issues/

## Session Log
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `501863a2-f47e-4a9d-ac6f-42bb4f68fcda.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
- `/ll:wire-issue` - 2026-05-17T08:13:49 - `7566953b-6a4d-4484-b84c-26f7a869ac63.jsonl`
- `/ll:refine-issue` - 2026-05-17T08:06:12 - `9ab87c4d-6a66-49e7-b727-427f181401b0.jsonl`
- `/ll:verify-issues` - 2026-05-17T05:54:39 - `9fb51237-8283-40d3-94ce-bda6ff4b1b33.jsonl`
- `/ll:format-issue` - 2026-05-17T03:36:51 - `fdd26cb3-344e-4b60-b7da-2a6f19dd2f75.jsonl`
- `/ll:capture-issue` - 2026-05-17T03:25:34Z - `fc34edff-2889-4499-9167-9c9f3178d6c1.jsonl`
