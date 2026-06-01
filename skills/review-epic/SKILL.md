---
name: review-epic
description: Use when asked to review epic health, audit stalled children, check scope drift, find missing coverage, or assess closure readiness. Produces a structured health report and actionable recommendations. Read-only.
argument-hint: "<EPIC-ID> [--skip-drift]"
model: sonnet
allowed-tools:
  - Read
  - Bash(ll-issues:*)
  - Bash(git:*)

arguments:
  - name: epic_id
    description: "EPIC ID to review (e.g., EPIC-42)"
    required: true
  - name: flags
    description: "--skip-drift to skip scope-drift and missing-coverage LLM passes (structural-only, fast mode)"
    required: false
metadata:
  short-description: "Audit EPIC health: stalled children, scope drift, missing coverage."
---

# Review Epic

Audits an EPIC's children for stalled status, scope drift, missing coverage, and closure
readiness. Outputs a structured health report and actionable recommendations. Never
writes to any file — all suggestions require the user to invoke a follow-up command.

---

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:

- Set `EPIC_ID` to the first token (e.g., `EPIC-42`). Uppercase it.
- Set `SKIP_DRIFT=true` if `--skip-drift` is present in flags.
- Read `STALE_DAYS` from `{{config.commands.review_epic.stale_days}}` (default 14).
- Read `ENABLE_SCOPE_DRIFT` from `{{config.commands.review_epic.enable_scope_drift_check}}`
  (default true). Force-disable if `SKIP_DRIFT=true`.

---

## Step 2: Load EPIC and Resolve Children

### 2a. Verify EPIC exists

```bash
ll-issues list --status open,in_progress,blocked,done,cancelled,deferred --type EPIC --json
```

Parse the JSON output. Find the record where `issue_id == EPIC_ID`.

**If not found**, report and stop:

```
✗ EPIC not found: EPIC_ID
  Run `ll-issues list --type EPIC` to see available EPICs.
```

Record the EPIC's `path`, `title`, `status`, and `relates_to` list.

### 2b. Load all issues for child resolution

```bash
ll-issues list --status open,in_progress,blocked,done,cancelled,deferred --json
```

Parse the JSON list as `all_issues`.

### 2c. Resolve children

Use the union of forward and backward links (mirrors `compute_epic_progress()` in
`scripts/little_loops/issue_progress.py`):

```
forward_ids  = set of IDs from the EPIC's `relates_to` list
backward_ids = set of issue_ids where parent == EPIC_ID
child_ids    = forward_ids ∪ backward_ids
children     = [issue for issue in all_issues if issue.issue_id in child_ids]
```

**If no children**, report and stop:

```
================================================================================
EPIC HEALTH REPORT: EPIC_ID — EPIC title
================================================================================

This EPIC has no linked children.

Next steps:
  • /ll:capture-issue -- with "parent: EPIC_ID" to create a child issue
  • /ll:link-epics to assign orphaned issues to this EPIC

================================================================================
```

---

## Step 3: Compute Progress Aggregates

```bash
ll-issues epic-progress EPIC_ID
```

Parse the JSON output for `by_status`, `percent_done`, `total`, and `oldest_open`.

Compute:
- `done_count`    = sum of `by_status` values for `done` and `cancelled`
- `active_count`  = sum for `open`, `in_progress`, `blocked`
- `deferred_count` = `by_status.deferred` or 0
- `oldest_open_age` = `oldest_open.age_days` from the JSON (or null if none)

---

## Step 4: Stall Detection (Non-LLM)

For each child with status `open`, `in_progress`, or `blocked`:

1. Read the child issue file content.
2. Extract the last-activity date using the session-log pattern (same logic as
   `_parse_updated_date()` in `scripts/little_loops/cli/issues/search.py`):
   - Scan the `## Session Log` section for the most recent timestamp line matching
     `` - `/ll:cmd` - YYYY-MM-DDTHH:MM:SS - `path` ``
   - Parse the date portion `YYYY-MM-DD` as the last-activity date.
   - If no session-log entries, fall back to the file's modification date:
     ```bash
     date -r "PATH_TO_FILE" +"%Y-%m-%d"
     ```
3. Compute `days_since_activity = today - last_activity_date`.
4. Flag as **stalled** if `days_since_activity > STALE_DAYS`.

Collect all stalled children as `stalled_children` list with their
`{id, title, status, days_since_activity}`.

---

## Step 5: Scope Drift Classification (LLM Pass)

**Skip this step if `ENABLE_SCOPE_DRIFT=false`.**

Read the EPIC file's `## Summary` section (text after `## Summary` heading, before the
next `##` heading).

For each active child (`open`, `in_progress`, `blocked`), read its `## Summary` section.

Classify each child using the following scoring table. Read the EPIC summary and each
child summary carefully, then assign one classification per child:

**Classification criteria:**

| Classification | Definition |
|----------------|------------|
| `on-theme`     | Child directly implements, fixes, or improves something explicitly named in the EPIC summary, or clearly supports the EPIC's stated goal |
| `tangential`   | Child touches related technology or systems but its stated goal does not map to any area named in the EPIC summary; could belong under a different EPIC |
| `off-theme`    | Child goal contradicts or is entirely unrelated to the EPIC summary; likely belongs under a sibling EPIC or no EPIC |

For each child, produce:
```
{id}: <classification> — <one sentence rationale>
```

Collect only `tangential` and `off-theme` results as `scope_drift_findings`.

---

## Step 6: Missing Coverage Analysis (LLM Pass)

**Skip this step if `ENABLE_SCOPE_DRIFT=false`.**

Parse the EPIC summary for named sub-areas, goals, or deliverable phrases. Look for:
- Quoted feature names, component names, or action phrases
- Numbered or bulleted sub-goals
- Sentences beginning with "will", "should", "must", or "covers"

For each identified sub-area, check whether any child's `## Summary` section covers it.
A child "covers" a sub-area when its summary mentions the same component, action, or
deliverable — exact wording not required, but semantic overlap must be clear.

Collect uncovered sub-areas as `missing_coverage_findings`:
```
{sub-area description}: no child issue covers this area
```

---

## Step 7: Closure Check (Pure)

Check all child statuses from `by_status`:

- **Ready to close** if `done_count == len(children)` (all children are `done` or
  `cancelled`) and `active_count == 0`.
- **Not ready** otherwise — note the count of still-active children.

---

## Step 8: Render Health Report

Output the following Markdown report. Use `N/A` for any section where data is empty.

```
================================================================================
EPIC HEALTH REPORT: EPIC_ID — EPIC title
================================================================================

**Progress**: done_count/total done (percent_done%) · active_count active · deferred_count deferred

### Stalled children  (> STALE_DAYS days without activity)

[For each stalled child]:
- CHILD_ID — CHILD_TITLE
  Status: child_status · Last activity: DATE (days_since_activity days ago)
  Recommendation: `ll-issues set-status CHILD_ID deferred` to park, or `/ll:manage-issue ... CHILD_ID` to resume. For bulk deferral of all stalled children, prefer `ll-issues set-status EPIC_ID done --cascade` to close everything at once.

[If none]: No stalled children detected.

### Scope drift

[For each scope_drift_finding]:
- CHILD_ID [classification] — rationale
  Recommendation: reparent with `ll-issues` edit, or detach by removing `parent: EPIC_ID` from frontmatter

[If none / ENABLE_SCOPE_DRIFT=false]: No scope drift detected. [or: Skipped (--skip-drift).

### Missing coverage

[For each missing_coverage_finding]:
- "sub-area description" — no child issue covers this area
  Recommendation: `/ll:capture-issue` to create a child issue targeting this area

[If none / ENABLE_SCOPE_DRIFT=false]: No missing coverage detected. [or: Skipped (--skip-drift).]

### Closure recommendation

[If ready]: All children done or cancelled — recommend: `ll-issues set-status EPIC_ID done`. Use `--cascade` to close any remaining open children in the same call.
[If not ready]: Not ready (active_count active children)

================================================================================
```

After the banner, add a `## Recommendations` section that lists each runnable command
implied by the findings above, formatted as a numbered checklist:

```
## Recommendations

[N findings — or "No action needed." if all sections are clean]

1. (if stalled children exist) Defer or resume stalled children:
   `ll-issues set-status CHILD_ID deferred`  — park ENH-NNN (stalled N days). Bulk option: `ll-issues set-status EPIC_ID cancelled --cascade`

2. (if scope drift) Reparent or detach drifted children:
   Review CHILD_ID frontmatter to update or remove `parent:` field

3. (if missing coverage) Capture new child issues for uncovered sub-areas:
   `/ll:capture-issue` — describe the missing sub-area and set `parent: EPIC_ID`

4. (if closure-ready) Mark EPIC done:
   `ll-issues set-status EPIC_ID done --cascade`
```

---

## Step 9: Guard Rails

- **Never write to any issue file.** This skill is read-only audit. All mutations are
  user-initiated follow-up commands shown in the Recommendations section.
- **`--skip-drift` mode**: Steps 5 and 6 are skipped; the scope-drift and missing-coverage
  sections display `Skipped (--skip-drift).` instead of findings.
- **Empty EPIC** (Step 2c exit): emit the early-exit message and stop — do not proceed to
  Steps 3–8.
- **EPIC not found** (Step 2a exit): emit the not-found error and stop.
- **Config defaults**: if `{{config.commands.review_epic.stale_days}}` is unavailable,
  use 14. If `{{config.commands.review_epic.enable_scope_drift_check}}` is unavailable,
  default to enabled.

---

## Usage Examples

```bash
# Full audit (stall + scope drift + missing coverage)
/ll:review-epic EPIC-42

# Structural-only audit (skip LLM scope-drift and missing-coverage passes)
/ll:review-epic EPIC-42 --skip-drift
```
