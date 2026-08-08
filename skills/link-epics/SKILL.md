---
name: link-epics
description: Assign orphaned issues to existing EPICs, or cluster them into new-EPIC proposals, via `ll-issues link-epics`.
disable-model-invocation: true

argument-hint: "[--mode assign|synthesize] [--threshold <score>] [--auto]"
model: sonnet
allowed-tools:
  - AskUserQuestion
  - Write
  - Edit
  - Read
  - Bash(ll-issues:*, git:*)

arguments:
  - name: flags
    description: "--mode assign|synthesize (default: assign); --threshold 0.5 to set the min score (default: config.issues.link_epics.min_score); --auto to apply/create proposals without prompting"
    required: false
metadata:
  short-description: Assign orphans to EPICs, or cluster them into new-EPIC proposals.
---

# Link Epics

Scoring, tiering, and clustering all live in `ll-issues link-epics` — this skill
only parses arguments, presents the CLI's proposals, and (in `synthesize` mode)
names/creates the resulting EPICs, since EPIC-file creation is not yet part of
the CLI (tracked separately as FEAT-2947).

- **`mode: assign`** (default) — score orphans against **existing** open EPICs;
  apply accepted proposals via the CLI's `--apply`.
- **`mode: synthesize`** — cluster orphans against each other; the CLI returns
  proposal clusters only, this skill names and creates the EPIC files.

`ll-issues link-epics` scores *text similarity* between orphan/EPIC titles —
distinct from `ll-issues clusters`, which visualizes existing *dependency-edge*
relationships between issues that already declare `blocked_by`/`depends_on`.

---

## Step 1: Parse Arguments

- `MODE` from `--mode <value>`. Default: `assign`.
- `THRESHOLD` from `--threshold <value>` if present; otherwise omit the flag and
  let the CLI fall back to `config.issues.link_epics.min_score`.
- `AUTO=true` if `--auto` is present.

---

## Mode: `--mode assign` (default)

### A1: Get Proposals

```bash
ll-issues link-epics --mode assign --json ${THRESHOLD:+--threshold "$THRESHOLD"}
```

Parse `{"proposals": [{orphan_id, epic_id, score, tier}, ...], "applied": []}`. If
`proposals` is empty, report:
```
No orphan-to-EPIC proposals found above the score threshold.
```
Stop.

### A2: Proposal Flow

**Interactive (no `--auto`)**: present proposals via `AskUserQuestion`:

```yaml
questions:
  - question: "Link these orphaned issues to their proposed epics? Select all you want to apply."
    header: "Proposals"
    multiSelect: true
    options:
      - label: "ENH-123 → EPIC-42 (HIGH 0.82)"
        description: "orphan title — epic title"
```

`ll-issues link-epics --apply` applies every proposal at or above `THRESHOLD` — it
has no single-pair apply. If the user accepts only a subset, raise `THRESHOLD` to
just above the highest rejected proposal's score before A3, so `--apply` picks up
exactly the accepted set. If nothing is selected, report `No assignments made.` and
stop.

**Auto (`--auto`)**: skip the prompt, go straight to A3.

### A3: Apply Assignments

```bash
ll-issues link-epics --mode assign --apply --json ${THRESHOLD:+--threshold "$THRESHOLD"}
```

This writes `parent:`/`epic:` on each orphan and appends to the target EPIC's
`## Children` section (idempotent — safe to re-run). Stage the touched files:

```bash
git add -u {{config.issues.base_dir}}/
```

### A4: Report Results

```
Applied N orphan→EPIC assignment(s):

  ✓ ENH-123 → EPIC-42 (HIGH 0.82)
  ✓ BUG-55  → EPIC-42 (MEDIUM 0.51)

Files staged. Run /ll:commit to commit the changes.
```

---

## Mode: `--mode synthesize`

### S1: Get Cluster Proposals

```bash
ll-issues link-epics --mode synthesize --json ${THRESHOLD:+--threshold "$THRESHOLD"}
```

Parse `{"clusters": [{member_ids, placeholder_title, modal_priority,
pairwise_min_score}, ...], "applied": []}`. `--apply` is **not** supported for this
mode (EPIC creation is deliberately kept out of the CLI — FEAT-2947). If `clusters`
is empty, report:
```
No orphan clusters found above the score threshold — nothing to synthesize.
```
Stop.

### S2: Name and Validate Clusters

For each cluster, review `placeholder_title` (frequency-derived from member
titles) and `member_ids`. Replace the placeholder with a clearer title when the
frequency-derived one is awkward or ambiguous; sanity-check that every member
actually belongs (drop odd-fit members from the proposal rather than forcing the
CLI's transitive grouping — clustering can chain unrelated issues together
through a shared intermediate).

### S3: Proposal Flow

**Interactive (no `--auto`)**: one `AskUserQuestion`, `multiSelect: true`, options
sorted by descending cluster size:

```yaml
questions:
  - question: "Which EPIC proposals should be created? Select all you want to create."
    header: "EPIC Proposals"
    multiSelect: true
    options:
      - label: "Cluster 1 → new EPIC \"CLI Output Format\" (5 issues)"
        description: "FEAT-10, BUG-22, ENH-31, FEAT-45, ENH-67"
```

If nothing is selected, report `No EPICs created.` and stop.

**Auto (`--auto`)**: create an EPIC for every returned cluster.

### S4: Create Accepted EPICs and Write-Back

For each accepted cluster:

1. **Allocate EPIC ID** via `ll-issues next-id`, called **immediately before each
   `Write`** — never batch-allocate upfront. If the PostToolUse hook reports the
   file was deleted (duplicate integer ID), call `ll-issues next-id` again and
   retry.
2. **Determine path**:
   `{{config.issues.base_dir}}/epics/<PRIORITY>-<EPIC_ID>-<slugified-title>.md`
   (slugify: lowercase, non-alphanumeric → `-`, collapse repeats). `<PRIORITY>` is
   the cluster's `modal_priority`.
3. **Write the EPIC file** with `Write`:

```markdown
---
id: EPIC-NNN
title: <validated title>
type: EPIC
priority: <modal_priority>
status: open
captured_at: "<TODAY, date -u +%Y-%m-%dT%H:%M:%SZ>"
discovered_date: <DATE_ONLY, date -u +%Y-%m-%d>
discovered_by: link-epics
relates_to: []
---

# EPIC-NNN: <validated title>

## Summary

Group of <N> related issues: <member titles, comma-separated>.

## Children

- **CHILD_ID_1** — child issue 1 title (open)
- **CHILD_ID_2** — child issue 2 title (open)
```

> **Note (ENH-162)**: `relates_to:` is reserved for peer/see-also cross-references
> between EPICs and sibling issues — never list child IDs there; containment is
> `parent:` on each child plus the `## Children` section above.

4. **Write `parent:`/`epic:` back to each child.** The new EPIC did not exist
   when `ll-issues link-epics --mode assign` last ran, so its `--apply` path
   cannot cover this write — insert `parent: EPIC-NNN` and `epic: EPIC-NNN`
   into each child's frontmatter block directly (same fields `apply_assignment()`
   writes for `assign` mode). If `parent:` already has a non-null value, skip
   and log: `⚠ CHILD_ID already has parent: <existing_value>, skipping.`
5. **Stage all files** by explicit path (`git add "<epic_path>"`,
   `git add "<child_path>"` per child) — never `git add .issues/` (sweeps unrelated
   files; see BUG-1976).

### S5: Report Results

```
Created N EPIC(s) from M orphaned issue(s):

  ✓ EPIC-42 "CLI Output Format" (5 issues)
      • FEAT-10 — issue title
      • BUG-22  — issue title

Files staged. Run /ll:commit to commit the changes.
```

If nothing was created (user declined all proposals), report:
```
No EPICs created. Run /ll:link-epics --mode assign to assign orphans to existing EPICs.
```

---

## Choosing a Mode

Run `--mode synthesize` first when no EPICs exist yet, or orphaned issues don't fit
any existing EPIC — it clusters orphans by thematic similarity and proposes new EPIC
files. Then run `--mode assign` (the default) to link any remaining orphans to the
newly created (or pre-existing) EPICs.

## Usage Examples

```bash
/ll:link-epics                              # assign mode, interactive
/ll:link-epics --auto                       # assign mode, apply without prompting
/ll:link-epics --threshold 0.4              # assign mode, interactive, custom threshold
/ll:link-epics --mode synthesize            # synthesize mode, interactive
/ll:link-epics --mode synthesize --auto     # synthesize mode, create all clusters
```
