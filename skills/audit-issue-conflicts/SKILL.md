---
name: audit-issue-conflicts
description: Use when asked to detect conflicting requirements or incompatible decisions across open issues.
disable-model-invocation: false
argument-hint: "[EPIC-NNNN | ID,ID,ID,...] [--auto] [--dry-run] [--cross-theme]"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - AskUserQuestion
  - Bash(git:*)
  - Bash(ll-issues:*)
  - Bash(python3:*)
arguments:
  - name: epic_id
    description: "Optional positional EPIC-NNNN (bare NNNN accepted), or a comma-separated list of issue IDs (TYPE-NNN or bare NNN per item). EPIC-NNNN scopes the audit to that EPIC's transitive children plus the EPIC file itself. A comma-separated list scopes the audit to exactly those issues (no transitive expansion). Omitted scans the full backlog."
    required: false
  - name: flags
    description: "Optional flags: --auto (apply all recommendations without prompting), --dry-run (report only, no changes), --cross-theme (add Phase 2b cross-batch fingerprint sweep to catch conflicts spanning thematic groups)"
    required: false
metadata:
  short-description: Use when asked to detect conflicting requirements or incompatible decisions acro
trigger_fixtures:
  should_fire:
    - "detect conflicting requirements across these open issues"
    - "find incompatible decisions between issues in this epic"
  should_not_fire:
    - "check whether this issue is ready to implement"
    - "review epic health and audit stalled children"
---

# Audit Issue Conflicts

You are tasked with scanning all open issues for semantic conflicts, synthesizing a ranked conflict report, and optionally applying recommended resolutions — either interactively (default), automatically (`--auto`), or as a report only (`--dry-run`).

## Configuration

This skill uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`

---

## Phase 0: Parse Flags

```
AUTO_MODE = false
DRY_RUN = false
CROSS_THEME = false

# Auto-enable in automation contexts
if ARGUMENTS contains "--dangerously-skip-permissions" or env LL_NON_INTERACTIVE is set or env DANGEROUSLY_SKIP_PERMISSIONS is set: AUTO_MODE = true

# Explicit flags
if ARGUMENTS contains "--auto": AUTO_MODE = true
if ARGUMENTS contains "--dry-run": DRY_RUN = true
if ARGUMENTS contains "--cross-theme": CROSS_THEME = true
```

### Positional EPIC scope (optional)

Parse an optional positional argument that scopes the audit to a single EPIC's
transitive children. The token is any `$ARGUMENTS` word that does **not** start
with `--`. When present, normalize and validate it into `SCOPE_EPIC`; when
absent, leave `SCOPE_EPIC` empty (preserving today's full-backlog behavior).

```bash
SCOPE_EPIC=""
declare -a SCOPE_ISSUE_LIST
for tok in $ARGUMENTS; do
    case "$tok" in
        --*) continue ;;                       # flags handled above
        *[,]*)
            # Comma-separated explicit issue-ID list (TYPE-NNN or bare NNN per
            # token, mixed types allowed). Resolves to SCOPE_ISSUE_LIST; leaves
            # SCOPE_EPIC empty. No transitive expansion.
            IFS=',' read -ra RAW_IDS <<< "$tok"
            for raw_id in "${RAW_IDS[@]}"; do
                [ -z "$raw_id" ] && continue
                # `ll-issues path` resolves both TYPE-NNN and bare NNN forms
                # (case-insensitive) directly, so no local normalization needed.
                resolved_path=$(ll-issues path "$raw_id" 2>/dev/null)
                if [ -z "$resolved_path" ] || [ ! -f "$resolved_path" ]; then
                    echo "ERROR: '$raw_id' does not resolve to an existing issue."
                    exit 1
                fi
                SCOPE_ISSUE_LIST+=("$resolved_path")
            done
            break
            ;;
        *)
            # Normalize: accept EPIC-NNNN or bare NNNN (case-insensitive).
            up=$(printf '%s' "$tok" | tr '[:lower:]' '[:upper:]')
            case "$up" in
                EPIC-*) SCOPE_EPIC="$up" ;;
                *[!0-9]*)
                    echo "ERROR: positional argument '$tok' is not an EPIC id (expected EPIC-NNNN or a bare number)."
                    exit 1
                    ;;
                *) SCOPE_EPIC="EPIC-$up" ;;      # bare digits → EPIC-NNNN
            esac
            # Validate the EPIC resolves to an existing EPIC file.
            if ! ll-issues list --type EPIC --json \
                 | python3 -c "import json,sys; ids={i['id'] for i in json.load(sys.stdin)}; sys.exit(0 if '$SCOPE_EPIC' in ids else 1)"; then
                echo "ERROR: '$SCOPE_EPIC' is not a valid EPIC (no matching EPIC file found)."
                exit 1
            fi
            break
            ;;
    esac
done
```

Log the active mode:
- `--auto` → "Running in auto-apply mode: all recommendations will be applied without prompting."
- `--dry-run` → "Running in dry-run mode: conflict report will be output, no files will be modified."
- `--cross-theme` → "Cross-theme sweep enabled: Phase 2b will check for conflicts spanning thematic batch boundaries."
- neither → "Running in interactive mode: each recommendation will require approval."
- `SCOPE_EPIC` set → "Scoped to $SCOPE_EPIC: auditing only its transitive children (plus the EPIC file)."
- `SCOPE_ISSUE_LIST` set → "Scoped to ${#SCOPE_ISSUE_LIST[@]} explicit issue IDs: auditing only those issues."

---

## Phase 1: Load Issues

Collect the active issue files to audit. When `SCOPE_EPIC` is set (from Phase 0),
restrict the set to that EPIC's **transitive** children (reusing the
cycle-guarded resolution in `ll-issues list --parent`, transitive since
ENH-2481) plus the EPIC file itself. Otherwise load the full active backlog.

```bash
declare -a ISSUE_FILES
declare -i TERMINAL_COUNT=0

if [[ ${#SCOPE_ISSUE_LIST[@]} -gt 0 ]]; then
    # Explicit-list mode: exactly the resolved paths from Phase 0, no
    # transitive expansion, no active-status filtering.
    ISSUE_FILES=("${SCOPE_ISSUE_LIST[@]}")
    echo "Scoped to ${#ISSUE_FILES[@]} explicit issue IDs"
elif [[ -n "$SCOPE_EPIC" ]]; then
    # Scoped mode: transitive children of SCOPE_EPIC (plus the EPIC file).
    # --status all + in-extractor filter (the bare default drops in_progress /
    # blocked children, and --status takes a single value, not a CSV list).
    while IFS= read -r f; do
        [ -f "$f" ] || continue
        ISSUE_FILES+=("$f")
    done < <(
        ll-issues list --parent "$SCOPE_EPIC" --status all --json | python3 -c "
import json, sys
active = {'open', 'in_progress', 'blocked'}
for i in json.load(sys.stdin):
    if (i.get('status') or 'open') in active and i.get('path'):
        print(i['path'])
"
    )
    # Append the EPIC file itself so it is fingerprinted alongside its children.
    EPIC_PATH=$(ll-issues path "$SCOPE_EPIC" 2>/dev/null)
    [ -f "$EPIC_PATH" ] && ISSUE_FILES+=("$EPIC_PATH")
    echo "Scoped to $SCOPE_EPIC: ${#ISSUE_FILES[@]} issues (transitive children + EPIC file)"
else
    # Unscoped mode: full active backlog. `ll-issues list` with no --type
    # filter covers bugs/features/enhancements/epics in one call, so EPIC
    # files are fingerprinted too (ENH-2634).
    while IFS= read -r f; do
        [ -f "$f" ] || continue
        ISSUE_FILES+=("$f")
    done < <(
        ll-issues list --status all --json | python3 -c "
import json, sys
active = {'open', 'in_progress', 'blocked'}
for i in json.load(sys.stdin):
    if (i.get('status') or 'open') in active and i.get('path'):
        print(i['path'])
"
    )
    TERMINAL_COUNT=$(( $(ll-issues list --status all --json | python3 -c "import json,sys; print(len(json.load(sys.stdin)))") - ${#ISSUE_FILES[@]} ))
    echo "Found ${#ISSUE_FILES[@]} active issues (excluded $TERMINAL_COUNT terminal issues)"
fi

# NOTE: ISSUE_FILES/TERMINAL_COUNT are local to this one Bash call (echo
# summary only) — state can't persist across calls, so Phase 4b re-derives
# active status per target via `ll-issues show --json` instead of reading this.

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found"
    exit 0
fi
```

For each file, parse from the filename:
- **ID** (e.g., `FEAT-1028`, `BUG-042`)
- **Type** (`BUG`, `FEAT`, `ENH`, `EPIC`)
- **Priority** (`P0`–`P5`)

Then read the file to extract:
- **Title** (from `# heading`)
- **Summary** section
- **Integration Map** / **Implementation Steps** / **Objectives** sections (first 300 chars each)

---

## Phase 2: Conflict Detection

Batch issues **3–5 per Task call**. Spawn all batch Task calls in a **single message** (parallel).

For each batch, look for four conflict types — `requirement` (Issue A requires X,
Issue B requires not-X), `objective` (two issues solve the same problem
differently), `architecture` (incompatible technical approaches), and `scope`
(partial scope overlap) — and, for each pair, emit structured records with
`conflict_type`, `severity` (high/medium/low), `issues`, `description`,
`recommendation` (merge/deprecate/split/add_dependency/update_scope), and
`proposed_change`. The full Task prompt template (per-issue input block, severity
rubric, recommendation glossary) lives in the companion file
[conflict-detection-prompt.md](conflict-detection-prompt.md); use it verbatim as
the batch prompt.

Wait for **all batch agents'** results synchronously in this same turn before proceeding.

Handle agent failures: if a batch agent fails, retry once. If retry fails, log a warning for those issues and continue.

---

## Phase 2b: Cross-Theme Fingerprint Sweep (`--cross-theme` only)

**Skip this phase unless `CROSS_THEME = true` (`--cross-theme` flag).**

After Phase 2's intra-batch pass, run a fast non-LLM overlap check across all issue pairs — including pairs that span batch boundaries — and dispatch targeted single-pair agents for any cross-batch pair with file overlap.

### Step 1: Extract Fingerprints

For each issue file collected in Phase 1, extract its structured fingerprint:

```bash
ll-issues fingerprint <issue-path>
```

This outputs JSON: `{"id": "...", "files_to_modify": [...], "key_terms": [...]}`. Collect all fingerprints.

### Step 2: Identify Cross-Batch Overlap Pairs

For every pair `(A, B)` where A and B were in **different Phase 2 batches**, check:

- **File overlap** (primary signal): `|A.files_to_modify ∩ B.files_to_modify| ≥ 2`
  OR Jaccard `|A.files_to_modify ∩ B.files_to_modify| / |A.files_to_modify ∪ B.files_to_modify| ≥ 0.25`
- **Key-term fallback**: if either issue has no `files_to_modify` entries, apply when Jaccard of `key_terms` ≥ 0.15

Skip pairs already evaluated in Phase 2. Cap at **30 additional pairs** to bound token cost (≤30% overhead for ≤100 base issues in batches of 3–5).

### Step 3: Dispatch Pair Agents

For each pair above threshold, spawn one Task agent using the same conflict-detection prompt template as Phase 2, but with exactly those two issues as the batch. Spawn all cross-theme pair agents in a **single message** (parallel).

Handle agent failures: if a pair agent fails, log a warning and skip that pair.

### Step 4: Merge Cross-Theme Findings

Collect all cross-theme conflict records. These feed into Phase 3's deduplication step without special handling — Phase 3 merges by `issues` pair membership regardless of whether the finding came from a Phase 2 batch or a Phase 2b pair agent.

**Cost note**: Phase 2b dispatches one agent per overlapping cross-batch pair. For 50 issues in 10 batches of 5, expect ≤10 additional agents (≤20% overhead). The 30-pair cap bounds worst-case cost.

---

## Phase 3: Synthesize Report

Aggregate all batch findings:

1. **Deduplicate**: merge any identical conflict pairs reported by overlapping batches
2. **Group by severity**: high → medium → low
3. **Within each severity group**: sort by issue priority (P0 first)

If no conflicts were found across all batches:

```
================================================================================
AUDIT ISSUE CONFLICTS
================================================================================

No conflicts detected among [N] active issues.

All issues appear to have compatible requirements, objectives, architecture
decisions, and scope boundaries.
================================================================================
```

Output this message and stop (exit 0).

Otherwise, display the conflict report:

```
================================================================================
AUDIT ISSUE CONFLICTS
================================================================================

Issues scanned: [N]
Conflicts found: [C] ([H] high / [M] medium / [L] low)

## HIGH SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 1 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

## MEDIUM SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 2 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

## LOW SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 3 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

================================================================================
```

---

## Phase 4: Apply Recommendations

### Dry-Run Mode (`--dry-run`)

Output the report (Phase 3) and stop. Do not modify any issue files.

```
Dry-run mode: no changes applied.
```

### Auto Mode (`--auto`)

Apply **all** recommendations without prompting, **regardless of severity** —
high, medium, and low-severity conflicts are all applied. For each conflict,
execute the appropriate action (see Phase 4b below). (There is no
severity-based skip in `--auto`; that only happens in interactive mode, and
only when the user explicitly declines.)

### Interactive Mode (default)

For each conflict, present an `AskUserQuestion` prompt with options shaped by
recommendation type. The exact question/option templates for each recommendation
type (**merge / deprecate**, **add_dependency**, **split / update_scope**) live
in the companion file [interactive-prompts.md](interactive-prompts.md).

---

## Phase 4b: Execute Approved Changes

Phase 5 stages changes with `git add -u` (see below), so no file-path list needs
to be tracked across Bash calls. Keep a running mental tally for the Phase 6 report — **applied**, **skipped
(idempotent)**, and **skipped (target not active)** — updated as you process
each recommendation below; there is no shell variable for these, since state
does not survive between separate Bash tool invocations.

For each approved recommendation:

### merge / deprecate

1. Identify the issue to be **kept** and the one to be **closed/superseded**
2. Before editing either the kept or closed issue file, verify the write-side active-set guard for each target: **(1) Membership** — the target's ID must be one of the active issues collected in Phase 1 (the roster the model read while parsing issue files). If not, skip this action and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`; count it toward the "skipped (target not active)" tally. **(2) TOCTOU re-check** — run `ll-issues show TARGET-ID --json | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('raw_status') in ('open','in_progress','blocked') else 1)"` (use `raw_status`, not the display-cased `status` field). If the exit code is non-zero, skip this action and log `[skipped: TARGET status is CURRENT_STATUS — not active]`; count it toward the same tally.
3. If merging scope: before appending, read the kept issue file and check whether `## Scope Addition` already contains a reference to `[CLOSED-ID]`. If found, skip the append and log `[idempotent: Scope Addition for CLOSED-ID already present]`. Otherwise, append a `## Scope Addition` note to the kept issue file:

```markdown

---

## Scope Addition

**Source**: Merged from [CLOSED-ID] during `/ll:audit-issue-conflicts` conflict resolution.

[Relevant scope absorbed from CLOSED-ID]
```

4. Add a resolution section to the closed issue file: before appending, check whether `## Resolution` is already present in the closed issue file. If found, skip and log `[idempotent: Resolution already present]`. Otherwise, append:

```markdown

---

## Resolution

- **Completed**: YYYY-MM-DD
- **Reason**: Superseded by [KEPT-ID] via conflict resolution audit
- **Proposed change**: [proposed_change from conflict record]
```

5. Close the superseded issue via the canonical status writer — do not hand-edit its frontmatter `status:` field:

```bash
ll-issues set-status [CLOSED-ID] cancelled --reason superseded
```

   Then record the supersession edge on the **kept** issue: read its frontmatter and add/append `[CLOSED-ID]` to its `supersedes:` list via Edit (create it as a single-item list if absent). `ll-issues link --supersedes` doesn't exist yet (FEAT-2842 doesn't cover it), so this is a direct frontmatter Edit, not a CLI call — it's what makes `ll-issues show [CLOSED-ID]` derive the reverse `Superseded by` row.

6. Both files were just edited via `Edit`/`ll-issues set-status`/`ll-issues link` above — Phase 5's `git add -u` will pick them up; no separate tracking step is needed.

7. Append session log to closed issue:

```bash
ll-issues append-log "[issue-file-path]" /ll:audit-issue-conflicts
```

8. Append session log to kept issue:

```bash
ll-issues append-log "[kept-issue-path]" /ll:audit-issue-conflicts
```

### add_dependency

Before appending, verify the write-side active-set guard: **(1) Membership** — the dependent issue's ID must be one of the active issues collected in Phase 1. If not, skip and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`; count it toward "skipped (target not active)". **(2) TOCTOU re-check** — run `ll-issues show TARGET-ID --json | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('raw_status') in ('open','in_progress','blocked') else 1)"` (`raw_status`, not the display-cased `status`). If the exit code is non-zero, skip and log `[skipped: TARGET status is CURRENT_STATUS — not active]`; count it toward the same tally.

Write the edge with `ll-issues link` — idempotent/list-aware/validating, so reruns never duplicate a `blocked_by:`/`depends_on:` key or drop earlier entries (FEAT-2842). Run `ll-issues link [ISSUE-A] --blocked-by [ISSUE-B]` (hard stop — honoured by every consumer, incl. `ll-issues sequence`) or `ll-issues link [ISSUE-A] --depends-on [ISSUE-B]` (soft ordering — non-fatal if absent/complete), per the user's interactive-prompt choice. Default to `--blocked-by` when unsure. `ll-issues link` already wrote the file — Phase 5's `git add -u` will stage it.

Then append session log:

```bash
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

### split / update_scope

Before appending to each affected issue, apply two guards: **(1) Write-side active-set guard** — the target's ID must be one of the active issues collected in Phase 1, and `ll-issues show TARGET-ID --json | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('raw_status') in ('open','in_progress','blocked') else 1)"` must exit 0 (`raw_status`, not the display-cased `status`). If the membership check fails, skip and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`; count it toward "skipped (target not active)". If the status re-check fails (non-zero exit), skip and log `[skipped: TARGET status is CURRENT_STATUS — not active]`; count it toward the same tally. **(2) Idempotency check** — check whether `## Scope Boundary` is already present in that file and already references `[OTHER-ID]`. If found, skip the append and log `[idempotent: Scope Boundary for OTHER-ID already present]`. Otherwise, append a scope boundary note:

```markdown

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [Specific scope clarification. E.g., "This issue covers X only. Related issue [OTHER-ID] covers Y."]
```

Then append session log — Phase 5's `git add -u` will stage the edit:

```bash
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

---

## Phase 5: Cleanup

Stage only files the audit modified. Phase 4b only ever edits already-tracked
issue files (append-only edits, status flips, frontmatter edges) — it never
creates new ones — so `git add -u` scoped to the issues directory stages
exactly those changes and nothing untracked (same idiom as
`skills/map-dependencies/SKILL.md`, BUG-1976):

```bash
git add -u {{config.issues.base_dir}}/
```

---

## Phase 6: Final Report

```
================================================================================
AUDIT ISSUE CONFLICTS — COMPLETE
================================================================================

## SUMMARY
- Issues scanned: [N]
- Conflicts found: [C]
- Recommendations applied: [A]
- Skipped (idempotent): [I]
- Skipped (user declined or no-op): [S]
- Skipped (target not active): [SKIPPED_INACTIVE_COUNT]
- Could not evaluate: [W]

## APPLIED CHANGES
- [ISSUE-A] vs [ISSUE-B]: [action taken, e.g., "FEAT-200 closed, scope merged into FEAT-100"]
- [ISSUE-A]: [action taken, e.g., "blocked_by: FEAT-300 added to frontmatter"]

## SKIPPED (IDEMPOTENT)
- [ISSUE-A] vs [ISSUE-B]: Scope Boundary for OTHER-ID already present — no duplicate appended

## SKIPPED (TARGET NOT ACTIVE)
- [ISSUE-X]: [skipped: TARGET not in active set (not loaded in Phase 1)]
- [ISSUE-Y]: [skipped: TARGET status is done — not active]

## UNCHANGED
- [ISSUE-A] vs [ISSUE-B]: user declined recommendation (interactive mode only — `--auto` applies every severity)

## SKIPPED (evaluation errors)
- [file]: Could not evaluate (subagent failure)

## GIT STATUS
All changes staged in {{config.issues.base_dir}}/

================================================================================
```

---

See [examples.md](examples.md) for usage examples and related commands.

## Output Evidence Contract

See [verbatim-output.md](verbatim-output.md) — cite conflict evidence with exact quotes, not paraphrase.
