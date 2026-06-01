---
id: ENH-1708
title: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check
type: ENH
priority: P3
status: done
parent: EPIC-1707
discovered_date: 2026-05-26
captured_at: '2026-05-26T00:48:43Z'
discovered_by: capture-issue
depends_on:
- ENH-1782
- ENH-1717
blocked_by:
- ENH-1831
decision_needed: false
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 74
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
size: Very Large
---

# ENH-1708: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check

## Summary

Add `.ll/history.db` reads (specifically `user_corrections` and the FTS5 `search_index`) into three high-leverage refinement skills so they can surface "have I been told this before about this issue?" context without prompt bloat. First concrete child of EPIC-1707.

## Motivation

The producer side of `.ll/history.db` records `user_corrections` ("don't mock the database", "use snake_case here") and indexes content via FTS5 on `(kind, ref, anchor, ts)`. But no skill queries it. The three refinement skills below are the highest-leverage consumers because they decide whether an issue is implementation-ready — exactly where prior corrections most often apply:

- **`refine-issue`**: when adding codebase findings to an issue, a prior correction on the touched file is high-signal context.
- **`ready-issue`**: when validating an issue is ready, "user previously corrected our approach on this anchor" should block readiness or surface as a concern.
- **`confidence-check`**: when computing pre-implementation confidence, a recent correction on this issue's scope is a confidence-lowering signal.

Other skills (e.g. `commit`, `open-pr`, `run-tests`) get less value from history reads — they operate on artifacts that already exist, not on decisions about future code.

## Current Behavior

All three skills build their prompt from the issue file + targeted codebase grep results. They have no access to:
- Prior `user_corrections` referencing the issue ID, the file paths it touches, or the anchors it mentions.
- Recent `file_events` showing what's changed near this issue's scope since it was captured.
- Related `issue_events` (e.g., "a similar issue was deferred 2 weeks ago for reason X").

## Expected Behavior

Each of the three skills queries `.ll/history.db` via a small read API (introduced as part of EPIC-1707) and includes the matched rows in its prompt context. Queries are **anchor-driven** — by issue ID, by file path, or by FTS5 phrase from the issue title — not broad time-windowed dumps.

Example for `refine-issue`:
1. Skill loads issue file.
2. Skill extracts file paths from the issue's "Integration Map" or codebase findings.
3. Skill calls `history_reader.find_user_corrections(anchors=[file_path, issue_id])` and `history_reader.recent_file_events(path=file_path, since="30d")`.
4. Matched rows (capped at N=5 per query, dedup'd) are formatted into a "## Historical Context" prompt section.
5. If DB is missing/empty, skill proceeds without the section (no hard failure).

## Scope Boundaries

- **In scope**:
  - Read API methods consumed: `find_user_corrections(anchors)`, `recent_file_events(path, since)`, `search(query, kind, limit)`.
  - Wiring into exactly the three skills listed: `refine-issue`, `ready-issue`, `confidence-check`.
  - Result caps and dedup (avoid prompt bloat).
  - Graceful degradation for missing/empty DB.
  - Unit tests per skill verifying the prompt-section behavior.
- **Out of scope**:
  - Designing the read API itself (owned by EPIC-1707; this is a consumer).
  - Wiring history into other skills (separate children of the EPIC).
  - Schema changes.
  - Cross-project history.

## Integration Map

### History Reader API (Read-Only, No Changes Needed)
- `scripts/little_loops/history_reader.py` — `find_user_corrections(topic, *, limit=10, include_stale=False, db=DEFAULT_DB_PATH) -> list[UserCorrection]`, `recent_file_events(path, *, limit=10, include_stale=False, db=DEFAULT_DB_PATH) -> list[FileEvent]`, `search(query, *, kind=None, limit=10, db=DEFAULT_DB_PATH) -> list[SearchResult]`, `related_issue_events(issue_id, *, limit=20, db=DEFAULT_DB_PATH) -> list[IssueEvent]`

### Files to Modify (Skill Prompts)
- `commands/refine-issue.md` — add new Step 2.5 "Query Historical Context" before the codebase research agents are spawned; add `Bash(ll-session:*)` to `allowed-tools`
- `commands/ready-issue.md` — add DB query step to Step 2 "Validate Issue Content" validation loop; add `Bash(ll-session:*)` to `allowed-tools`
- `skills/confidence-check/SKILL.md` — add DB query in Phase 1 "Gather Context" after loading the issue file; add `Bash(ll-session:*)` to `allowed-tools`

### Bridge Stubs (May Need Allowed-Tools Sync)
- `skills/ll-refine-issue/SKILL.md` — bridge stub to `commands/refine-issue.md`; verify frontmatter allowed-tools matches source command
- `skills/ll-ready-issue/SKILL.md` — bridge stub to `commands/ready-issue.md`; verify frontmatter allowed-tools matches source command

### Additional Files to Modify (Wiring Pass)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — add `ll-history-context = "little_loops.cli.history_context:main"` entry under `[project.scripts]` (Option B only; already noted in step 5 but absent from Integration Map files list)
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.history_context import main_history_context` import and `__all__` entry, matching the pattern used for all other CLI entry points (Option B only)
- `.claude/settings.local.json` — add `"Bash(ll-session:*)"` (Option A) or `"Bash(ll-history-context:*)"` (Option B) to `permissions.allow`; currently absent, which will gate interactive skill testing with permission prompts
- `CHANGELOG.md` — add release entry for the three skill history-context additions (both options), and for `ll-history-context` CLI (Option B)

### Documentation (Wiring Pass)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `### main_history_context` subsection following the `### main_session` pattern (Option B only)
- `docs/reference/CLI.md` — add `### ll-history-context` section documenting `<issue_id>` and `--file <path>` args and output format (Option B only)
- `docs/ARCHITECTURE.md` — add `history_context.py` line to `cli/` directory tree alongside `session.py` entry (Option B only)
- `.claude/CLAUDE.md` — add `ll-history-context` bullet under `## CLI Tools` alongside `ll-session` entry (Option B only)
- `CONTRIBUTING.md` — add `history_context.py` tree entry in `cli/` section (Option B only)
- `commands/help.md` — add `ll-history-context` line to CLI Tools listing block (Option B only)
- `skills/init/SKILL.md` — add `"Bash(ll-history-context:*)"` to the generated `permissions.allow` template array so newly-initialized projects grant the permission automatically (Option B only)

### CLI Consumers (Query Surface via Bash)
- `scripts/little_loops/cli/session.py` — `main_session()`: `search --fts`, `recent --kind`, `related <issue_id>` subcommands back the `ll-session` CLI that skills will call

### Tests
- `scripts/tests/test_history_reader.py` — existing coverage for `TestMissingDatabase`, `TestEmptyTables`, `TestStaleRowFiltering`, `TestFindUserCorrections`, `TestSearch`; copy fixture patterns (`tmp_path`, `ensure_db`, `SQLiteTransport`) for new skill tests
- `scripts/tests/test_refine_issue_command.py` — add tests for history context injection
- `scripts/tests/test_ready_issue_lint.py` — add tests for history context injection
- `scripts/tests/test_confidence_check_skill.py` — add tests for history context injection

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_context_cli.py` — **new test file** (Option B only); test `main()` in `cli/history_context.py` following patterns from `test_ll_session.py` (`TestArgumentParsing`, etc.); cover: DB with matches, no matches, DB missing, empty output guard
- **Test class guidance** (both options): in `test_refine_issue_command.py` add `TestRefineIssueHistoryContextInjection`; in `test_ready_issue_lint.py` add `TestReadyIssueHistoryContextInjection`; in `test_confidence_check_skill.py` add `TestConfidenceCheckHistoryContextInjection` — each class uses the document-wiring structural pattern from `TestConfidenceCheckPhase4CLI._phase_text()` (index section heading, slice to next heading, assert instruction text present)

### Database Schema (Reference)
- `scripts/little_loops/session_store.py` — `_MIGRATIONS[0]` creates `user_corrections` (`id`, `ts`, `session_id`, `content`, `source`) and `search_index` FTS5 (`content`, `kind UNINDEXED`, `ref UNINDEXED`, `anchor UNINDEXED`, `ts UNINDEXED`); `_MIGRATIONS[4]` adds `issue_sessions` VIEW

### Documentation
- `skills/confidence-check/SKILL.md` — update to document new "Historical Context" section in Phase 1
- `commands/refine-issue.md` — update to document new Step 2.5
- `commands/ready-issue.md` — update to document new validation check

## Proposed Solution

Two implementation options; one must be chosen before wiring begins.

### Option A: Multi-call via existing `ll-session` CLI

Add `Bash(ll-session:*)` to each skill's `allowed-tools` and instruct the skill to make two shell calls per skill invocation:

```bash
# Corrections on this issue or its file paths
ll-session search --fts "{{issue_title_keywords}}" --kind correction --limit 5

# Recent file events on files in Integration Map
ll-session recent --kind file --limit 5
```

**Pros**: Zero new code — `ll-session` already exists and works. Output format from `scripts/little_loops/cli/session.py` `main_session()` is `[correction] <content>  (<anchor>)` — ready to include as-is.

**Cons**: Two Bash tool calls per skill invocation; output format is terminal-oriented, not markdown; no deduplication across calls; each skill must implement its own formatting step.

### Option B: New `ll-history-context` CLI entry point

> **Selected:** Option B — new `ll-history-context` CLI — centralized dedup/cap and anchor-driven output match the established thin-CLI pattern in this codebase (reuse score 3/3 vs 2/3 for Option A)

Add a thin `ll-history-context <issue_id> [--file <path>]` CLI in `scripts/little_loops/cli/history_context.py` that:
1. Calls `find_user_corrections(topic=issue_id)` + `search(query=issue_title, kind="correction")` with dedup
2. Renders a ready-to-inject `## Historical Context` markdown block
3. Returns empty string (no output) if DB is missing or no matches

Skills add `Bash(ll-history-context:*)` to `allowed-tools` and call once:

```bash
HIST=$(ll-history-context ENH-1708 2>/dev/null || true)
if [ -n "$HIST" ]; then echo "$HIST"; fi
```

**Pros**: Single Bash call per skill; output is ready-to-inject markdown; dedup and cap live in one place; easier to evolve the format later.

**Cons**: Requires new CLI module, new `pyproject.toml` entry point, new tests; more scope than Option A.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option B — New `ll-history-context` CLI entry point

**Reasoning**: Option B directly matches three established thin-CLI modules (`session.py`, `ctx_stats.py`, `history.py`) in structure and reuses `find_user_corrections()` and `search()` from `history_reader.py` with graceful-missing-DB behavior already tested. Option A has a critical anchor-scoping gap — `ll-session recent --kind file` lacks `--path` filtering, returning global file events instead of the issue-required anchor-driven results, forcing each of the three skills to independently implement formatters and dedup logic without a shared utility.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (ll-session multi-call) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option B (ll-history-context CLI) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- **Option A**: `search --fts … --kind correction` works end-to-end (`test_ll_session.py` lines 395–411 confirmed), but `ll-session recent --kind file` has no `--path` scoping (`session.py` line 227 passes only `kind` and `limit`), returning global file events that do not satisfy the anchor-driven query intent; per-skill formatter/dedup duplication across 3 skills adds ongoing divergence risk.
- **Option B**: `find_user_corrections()` and `search(kind="correction")` exist in `history_reader.py` (lines 130, 198) with `_connect_readonly()` returning `None` on missing DB; `ctx_stats.py`/`session.py` provide direct copy-adapt templates; `test_ll_session.py` `TestMainSession` is the exact test template; all 8–10 documentation touchpoints are pre-mapped in the Integration Map.

## Implementation Steps

1. **Choose implementation option** (see Proposed Solution — `decision_needed: true`): Option A (ll-session multi-call) or Option B (new ll-history-context CLI).

2. **Modify `commands/refine-issue.md`** — add Step 2.5 between "Analyze Issue Content" and "Research Codebase":
   - Add `Bash(ll-session:*)` (Option A) or `Bash(ll-history-context:*)` (Option B) to `allowed-tools` frontmatter
   - Instruction: extract issue ID and any file paths already in the issue; run query; if output non-empty, format as `## Historical Context` section and note it for use in Step 5a gap-filling
   - Cap: include at most 5 rows, skip if DB missing

3. **Modify `commands/ready-issue.md`** — add DB query to Step 2 "Validate Issue Content":
   - Add allowed-tools entry (same as above)
   - Instruction: query corrections for this issue ID; if any match, add as a `Historical Concerns` sub-bullet in the validation checklist with severity `warning`
   - Graceful degradation: if DB missing, skip section silently

4. **Modify `skills/confidence-check/SKILL.md`** — add DB query in Phase 1 "Gather Context" after the issue file is loaded:
   - Add `Bash(ll-session:*)` to `allowed-tools` frontmatter (currently lists `Read`, `Glob`, `Grep`, `Edit`, `Bash(find:*)`, `Bash(git:*)` at lines 6–12)
   - Instruction: query corrections for the issue ID and for each file in Integration Map; each matched correction is a -0.1 signal on the Outcome Confidence Score
   - Cap: at most 5 corrections included; if 0 matches, Outcome Confidence Score is unaffected

5. **If Option B chosen**: scaffold `scripts/little_loops/cli/history_context.py` following the existing pattern in `scripts/little_loops/cli/session.py` `main_session()`; add `ll-history-context = "little_loops.cli.history_context:main"` to `pyproject.toml` `[project.scripts]`

6. **Add tests** for each of the three skills following patterns in `scripts/tests/test_history_reader.py`:
   - Use `tmp_path` + `ensure_db()` from `scripts/little_loops/session_store.py`
   - Use `SQLiteTransport(db)` to seed correction rows for "matches present" case
   - Cover: DB present with matches, DB present with no matches, DB missing, DB empty, stale rows older than 30 days

7. **Update `SKILL.md` docs** for each skill — document the new `## Historical Context` section, when it appears, and the byte-cap guarantee

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Update `.claude/settings.local.json`** — add `"Bash(ll-session:*)"` (Option A) or `"Bash(ll-history-context:*)"` (Option B) to `permissions.allow`; without this, interactive testing of the three skills will prompt for permission on every history query
9. **If Option B**: update `scripts/little_loops/cli/__init__.py` — add import (`from little_loops.cli.history_context import main_history_context`) and `__all__` entry, matching existing pattern
10. **If Option B**: update external docs — `docs/reference/API.md` (`### main_history_context` subsection), `docs/reference/CLI.md` (`### ll-history-context` section), `docs/ARCHITECTURE.md` (directory tree entry), `.claude/CLAUDE.md` (`## CLI Tools` bullet), `CONTRIBUTING.md` (tree entry), `commands/help.md` (CLI listing line), `skills/init/SKILL.md` (permissions template array)
11. **Update `CHANGELOG.md`** — add entry for the three skill wiring additions (both options) and `ll-history-context` CLI (Option B only)

## Impact

- **Priority**: P3 — High value but not blocking; lands after EPIC-1707's read API is defined.
- **Effort**: Medium — three skills × (query + formatter + tests + docs); Option B adds ~1 day for new CLI.
- **Risk**: Medium — stale or irrelevant history actively misleads agents into spurious "concerns" or false confidence drops. Anchor-driven queries + caps mitigate but don't eliminate this.
- **Breaking Change**: No — additive prompt section, omitted when DB has nothing relevant.

## Acceptance Criteria

- `refine-issue`, `ready-issue`, and `confidence-check` each include a "## Historical Context" section in their generated prompts when matches exist.
- Each skill has tests covering: matches present, no matches, DB missing, DB empty.
- Each skill's `SKILL.md` documents the new section and when it appears.
- Per-skill prompt-byte impact when no matches: 0 bytes added.
- Per-skill prompt-byte impact when matches present: capped at ~500 tokens (configurable).

## Related Key Documentation

- `scripts/little_loops/history_reader.py` — read API (all five query functions fully implemented)
- `scripts/little_loops/session_store.py` — DB schema (`_MIGRATIONS[0]` through `_MIGRATIONS[6]`)
- `scripts/tests/test_history_reader.py` — test fixture patterns to copy (`TestMissingDatabase`, `TestEmptyTables`, `TestStaleRowFiltering`)
- `scripts/little_loops/cli/session.py` — existing `ll-session` CLI output format and subcommand structure

## Labels

`enhancement`, `captured`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — Blocker (ENH-1752) is now done; issue is ready to implement.
- `history_reader.py` now EXISTS (249 lines) with `find_user_corrections()`, `recent_file_events()`, `search()`, `related_issue_events()` all implemented ✓
- FTS5 `search_index` table exists ✓
- None of the three target skills (`refine-issue`, `ready-issue`, `confidence-check`) currently import or reference `history_reader` — consumer wiring is the remaining work ✓
- Action: Implementation is unblocked; remove any informal "blocked on ENH-1752" notes and proceed

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Wide file surface from wiring pass** — 21 files total (3 skills + new CLI + pyproject + `__init__.py` + 7 doc files + 4 test files + settings + CHANGELOG); each site is mechanical but coordination breadth increases review overhead. Work from the enumerated Integration Map sequentially; docs pass last.
- **`test_ready_issue_lint.py` is sparse (3 tests)** — adding `TestReadyIssueHistoryContextInjection` to an under-covered file; follow the structural assertion pattern from `test_confidence_check_skill.py` (`_phase_text()`, index by section heading, assert instruction present).

## Session Log
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba34fa14-184f-4634-a086-e871150a0d8d.jsonl`
- `/ll:decide-issue` - 2026-06-01T09:56:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/831c4a34-e82d-488d-b084-d4912e138029.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f852d1a3-b49c-432a-ba01-2926efe363e5.jsonl`
- `/ll:wire-issue` - 2026-06-01T09:48:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c26d3996-cd2d-42e5-9600-0b2cc780f9e2.jsonl`
- `/ll:refine-issue` - 2026-06-01T09:43:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95b7f3c2-3fcd-4f33-80c2-3f6916684161.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T04:19:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f60c9218-3661-4445-8adb-23f9182491a5.jsonl`
- `/ll:verify-issues` - 2026-06-01T03:08:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

- `/ll:capture-issue` - 2026-05-26T00:48:43Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c695cf-9995-4a8f-9ec7-81cdca0d77e5.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session (score: 11/11, Very Large)

### Decomposed Into
- ENH-1846: Scaffold ll-history-context CLI (Option B) with tests and docs
- ENH-1847: Wire ll-history-context into refine-issue, ready-issue, and confidence-check

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

**Done** | Created: 2026-05-26 | Priority: P3
