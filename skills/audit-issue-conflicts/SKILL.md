---
name: audit-issue-conflicts
description: Use when asked to detect conflicting requirements or incompatible decisions across open issues.
disable-model-invocation: false
argument-hint: "[EPIC-NNNN] [--auto] [--dry-run] [--cross-theme]"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - AskUserQuestion
  - Bash(git:*)
  - Bash(ll-issues:*)
arguments:
  - name: epic_id
    description: "Optional positional EPIC-NNNN (bare NNNN accepted). When set, scopes the audit to that EPIC's transitive children plus the EPIC file itself, instead of the full backlog."
    required: false
  - name: flags
    description: "Optional flags: --auto (apply all recommendations without prompting), --dry-run (report only, no changes), --cross-theme (add Phase 2b cross-batch fingerprint sweep to catch conflicts spanning thematic groups)"
    required: false
metadata:
  short-description: Use when asked to detect conflicting requirements or incompatible decisions acro
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
for tok in $ARGUMENTS; do
    case "$tok" in
        --*) continue ;;                       # flags handled above
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

---

## Phase 1: Load Issues

Collect the active issue files to audit. When `SCOPE_EPIC` is set (from Phase 0),
restrict the set to that EPIC's **transitive** children (reusing the
cycle-guarded resolution in `ll-issues list --parent`, transitive since
ENH-2481) plus the EPIC file itself. Otherwise load the full active backlog.

```bash
declare -a ISSUE_FILES
declare -i TERMINAL_COUNT=0

if [[ -n "$SCOPE_EPIC" ]]; then
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
    # Unscoped mode: full active backlog. epics/ is included so EPIC files are
    # also fingerprinted (ENH-2634).
    for dir in {{config.issues.base_dir}}/{bugs,features,enhancements,epics}/; do
        [ -d "$dir" ] || continue
        for f in "$dir"*.md; do
            [ -f "$f" ] || continue
            status=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$f")
            case "${status:-open}" in
                open|in_progress|blocked) ISSUE_FILES+=("$f") ;;
                *) TERMINAL_COUNT=$((TERMINAL_COUNT + 1)) ;;
            esac
        done
    done
    echo "Found ${#ISSUE_FILES[@]} active issues (excluded $TERMINAL_COUNT terminal issues)"
fi

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

Wait for **all batch agents** to complete before proceeding.

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

Apply **all** recommendations without prompting. For each conflict, execute the appropriate action (see Phase 4b below).

### Interactive Mode (default)

For each conflict, present an `AskUserQuestion` prompt with options shaped by
recommendation type. The exact question/option templates for each recommendation
type (**merge / deprecate**, **add_dependency**, **split / update_scope**) live
in the companion file [interactive-prompts.md](interactive-prompts.md).

---

## Phase 4b: Execute Approved Changes

Track every modified file path so Phase 5 stages only audit-touched files:

```bash
MODIFIED_FILES=()
SKIPPED_INACTIVE_COUNT=0
```

For each approved recommendation:

### merge / deprecate

1. Identify the issue to be **kept** and the one to be **closed/superseded**
2. Before editing either the kept or closed issue file, verify the write-side active-set guard for each target using the ISSUE_FILES list from Phase 1 context: **(1) Membership** — the target's file path must appear in ISSUE_FILES. If not, skip this action and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`. Increment `SKIPPED_INACTIVE_COUNT`. **(2) TOCTOU re-check** — run `awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' TARGET` and confirm the result matches `open|in_progress|blocked`. If terminal, skip this action and log `[skipped: TARGET status is CURRENT_STATUS — not active]`. Increment `SKIPPED_INACTIVE_COUNT` for each skipped target.
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

- **Status**: Closed - Superseded
- **Completed**: YYYY-MM-DD
- **Reason**: Superseded by [KEPT-ID] via conflict resolution audit
- **Proposed change**: [proposed_change from conflict record]
```

5. Update the closed issue's frontmatter `status: done` using the Edit tool.

6. Track both modified files:

```bash
MODIFIED_FILES+=("[kept-issue-path]" "[closed-issue-path]")
```

7. Append session log to closed issue:

```bash
ll-issues append-log "[issue-file-path]" /ll:audit-issue-conflicts
```

8. Append session log to kept issue:

```bash
ll-issues append-log "[kept-issue-path]" /ll:audit-issue-conflicts
```

### add_dependency

Before appending, verify the write-side active-set guard using the ISSUE_FILES list from Phase 1 context: **(1) Membership** — the dependent issue's file path must appear in ISSUE_FILES. If not, skip and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`. Increment `SKIPPED_INACTIVE_COUNT`. **(2) TOCTOU re-check** — run `awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' TARGET` and confirm the result matches `open|in_progress|blocked`. If terminal, skip and log `[skipped: TARGET status is CURRENT_STATUS — not active]`. Increment `SKIPPED_INACTIVE_COUNT`.

Append either `blocked_by: [ISSUE-B]` (hard stop — must complete first) or `depends_on: [ISSUE-B]` (soft ordering — preferred when no hard dependency exists) to the frontmatter of the dependent issue file using Edit, according to the user's choice from the interactive prompt. Track the modified file:

```bash
MODIFIED_FILES+=("[issue-path]")
```

Then append session log:

```bash
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

### split / update_scope

Before appending to each affected issue, apply two guards: **(1) Write-side active-set guard** — verify the target's file path appears in ISSUE_FILES (from Phase 1) and run `awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' TARGET` to confirm the result matches `open|in_progress|blocked`. If the membership check fails, skip and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`; increment `SKIPPED_INACTIVE_COUNT`. If the status re-check fails, skip and log `[skipped: TARGET status is CURRENT_STATUS — not active]`; increment `SKIPPED_INACTIVE_COUNT`. **(2) Idempotency check** — check whether `## Scope Boundary` is already present in that file and already references `[OTHER-ID]`. If found, skip the append and log `[idempotent: Scope Boundary for OTHER-ID already present]`. Otherwise, append a scope boundary note:

```markdown

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [Specific scope clarification. E.g., "This issue covers X only. Related issue [OTHER-ID] covers Y."]
```

Then track each modified file and append session log:

```bash
MODIFIED_FILES+=("[issue-path]")
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

---

## Phase 5: Cleanup

Stage only files that were modified during Phase 4b — never stage untracked files the audit did not touch:

```bash
for f in "${MODIFIED_FILES[@]}"; do
    git add "$f"
done
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
- [ISSUE-A] vs [ISSUE-B]: user declined recommendation
- [ISSUE-A] vs [ISSUE-B]: no action needed (low severity, skipped in auto mode)

## SKIPPED (evaluation errors)
- [file]: Could not evaluate (subagent failure)

## GIT STATUS
All changes staged in {{config.issues.base_dir}}/

================================================================================
```

---

## Examples

```bash
# Interactive mode: review each conflict and approve/reject
/ll:audit-issue-conflicts

# Scope the audit to a single EPIC's transitive children (plus the EPIC file)
/ll:audit-issue-conflicts EPIC-2457

# Scoped + auto-apply (bare NNNN is normalized to EPIC-NNNN)
/ll:audit-issue-conflicts 2457 --auto

# Auto-apply all recommendations without prompting
/ll:audit-issue-conflicts --auto

# Report only, no changes
/ll:audit-issue-conflicts --dry-run

# Cross-theme sweep: detect conflicts across thematic boundaries
/ll:audit-issue-conflicts --cross-theme

# Cross-theme dry-run: report only, no changes
/ll:audit-issue-conflicts --dry-run --cross-theme
```

## Related Commands

- `/ll:tradeoff-review-issues` — Evaluates utility vs complexity (is it worth doing?)
- `/ll:align-issues` — Validates issues against project goals
- `/ll:map-dependencies` — Traces blocked_by relationships
- `/ll:refine-issue` — Fills knowledge gaps in a single issue

## Output Evidence Contract

See [verbatim-output.md](verbatim-output.md) — cite conflict evidence with exact quotes, not paraphrase.
