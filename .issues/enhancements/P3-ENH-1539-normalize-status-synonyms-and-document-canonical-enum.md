---
id: ENH-1539
type: enhancement
priority: P3
status: open
captured_at: "2026-05-17T03:25:34Z"
discovered_date: 2026-05-17
discovered_by: capture-issue
---

# ENH-1539: Normalize status synonyms and document canonical enum

## Summary

Coding agents periodically write non-canonical values into issue frontmatter `status:` — most commonly `complete` / `completed` / `finished` — instead of the canonical `done`. A snapshot of `.issues/` today shows 1520 files at `status: done` and 20 at `status: completed`, with stray values like `incomplete`, `pending`, `proven`, and a malformed `status: in` (likely truncated `in_progress`) also present. Because every downstream consumer (`sync.py:277,985`, `issue_manager.py:790`, `issue_lifecycle.py:400`, `issue_discovery/search.py:73`, `cli/deps.py:55`) tests membership in `("done", ...)`, drifted values silently exclude issues from "completed" filters, GitHub close-sync, sprint skip logic, dependency validation, and history exports.

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

- `scripts/little_loops/issue_parser.py` — extend the existing normalization at line ~488 with the synonym map.
- `scripts/little_loops/issue_lifecycle.py` — apply the same map on write paths (`set_status`, the `("done", "cancelled")` checks at line 400 / 872 stay as-is since they now only ever see canonical values).
- `.claude/CLAUDE.md` — add the "Status values" subsection under "Issue File Format" near line 80-ish.
- `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/refine-issue/SKILL.md` — add the one-line reference to the canonical enum.

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

### Similar Patterns

- `issue_parser.py:488-489` is the existing precedent for parser-level status normalization. Extend it; don't duplicate.

### Tests

- `scripts/tests/test_issue_parser.py` (or equivalent) — add cases for each synonym in the map, plus a "unknown value passes through unchanged" case so we don't accidentally swallow real new statuses.
- `scripts/tests/test_issue_lifecycle.py` — verify `set_status("completed")` writes `done` to disk.

### Documentation

- `.claude/CLAUDE.md` — add the canonical enum subsection (see Proposed Solution).
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — already documents `done`; add a one-liner noting that synonyms are coerced on read/write so authors don't worry about it.

### Configuration

- N/A.

## Implementation Steps

1. Extend `issue_parser.py:488` with the `STATUS_SYNONYMS` map and apply it to every parsed status, not just the `open` + `completed_at` case. Add the same coercion to `issue_lifecycle.set_status()`. Add unit tests.
2. Add the canonical enum subsection to `.claude/CLAUDE.md` and a one-line reference in each issue-touching skill (`capture-issue`, `ready-issue`, `manage-issue`, `format-issue`, `refine-issue`).
3. Run a one-shot cleanup pass that rewrites the 20 `status: completed` files (and `status: in` truncations, `status: incomplete` / `pending` / `proven` outliers, after eyeballing what they should actually be) to canonical values. Commit as a single normalization pass.
4. Verify with `grep -rn "status:" .issues/ | grep -oE "status: [a-z_]+" | sort -u` — the output should match the canonical enum exactly.

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

## Session Log
- `/ll:format-issue` - 2026-05-17T03:36:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fdd26cb3-344e-4b60-b7da-2a6f19dd2f75.jsonl`
- `/ll:capture-issue` - 2026-05-17T03:25:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc34edff-2889-4499-9167-9c9f3178d6c1.jsonl`
