---
name: create-epics-from-unparented
description: Cluster orphaned issues by thematic similarity and propose new EPIC definitions to cover them — the inverse of /ll:link-epics.
disable-model-invocation: true
argument-hint: "[--auto] [--min-cluster <n>] [--min-score <threshold>]"
model: sonnet
allowed-tools:
  - AskUserQuestion
  - Edit
  - Read
  - Write
  - Bash(ll-issues:*)
  - Bash(git:*)
arguments:
  - name: flags
    description: "--auto to create all clusters without prompting; --min-cluster 2 to set minimum issues per cluster; --min-score 0.3 to set Jaccard threshold"
    required: false
metadata:
  short-description: Cluster orphaned issues by similarity and propose new EPICs to cover them.
---

# Create Epics from Unparented

Discovers open BUG/FEAT/ENH issues without a `parent:` frontmatter field, clusters
them by Jaccard similarity on title + summary text, and proposes new EPIC files for
each cluster. The inverse operation of `/ll:link-epics` — where that skill assigns
orphans to **existing** EPICs, this skill synthesizes **new** EPICs from the orphan pool.

---

## Step 1: Parse Arguments

Extract flags from the arguments:

- Set `AUTO=true` if `--auto` is present.
- Parse `MIN_CLUSTER` from `--min-cluster <value>` if present (integer ≥ 1).
  - Default: `MIN_CLUSTER = 2`.
- Parse `MIN_SCORE` from `--min-score <value>` if present (float between 0.0 and 1.0).
  - Default: `MIN_SCORE = 0.3`.

---

## Step 2: Discover Orphaned Open Issues

Issues under `{{config.issues.base_dir}}` are found via three separate calls
(one per type, since `--type` is single-valued):

```bash
ll-issues list --status open --type BUG --json
ll-issues list --status open --type FEAT --json
ll-issues list --status open --type ENH --json
```

Filter orphans from the JSON output: the `parent` key is `null` when absent. Keep
only issues where `parent` is `null` — these are **orphaned issues**.

```python
orphans = [i for i in data if not i.get("parent")]
```

For each orphan:
1. Record its `id`, `path`, and `title` from the JSON.
2. Read the file content (needed for summary extraction in scoring).
3. Extract summary: find text under `## Summary` heading using pattern
   `## Summary\n(.+?)(?=\n##|\Z)` with DOTALL matching.
4. Build score text: `orphan_score_text = orphan_title + " " + summary_text`.

If fewer than 2 orphaned issues exist, report:
```
Fewer than 2 orphaned open issues found — nothing to cluster.
All open issues already have a parent EPIC assigned, or there are too few orphans to group.
```
Stop.

---

## Step 3: Cluster Orphans by Jaccard Similarity

### Word Extraction

From each orphan's score text:
1. Lowercase all text.
2. Extract all alphabetic tokens of 3+ characters.
3. Exclude common stop words: `the`, `and`, `for`, `that`, `this`, `with`, `have`,
   `from`, `are`, `was`, `not`, `will`, `all`, `but`, `can`, `its`, `one`, `any`,
   `also`, `when`, `been`, `which`, `their`, `they`, `into`, `more`, `has`, `add`,
   `use`, `new`, `via`, `per`, `set`, `run`.

### Jaccard Similarity

For each pair of orphans A and B:

```
score = |words_A ∩ words_B| / |words_A ∪ words_B|
```

If either word set is empty: `score = 0.0`.

### Greedy Cluster Merge

1. Compute pairwise scores for all orphan pairs.
2. Sort pairs by descending score.
3. Iterate pairs: if `score ≥ MIN_SCORE`, merge the two issues into the same cluster.
   - Use union-find (or equivalent): merging A and B into a cluster means any future
     pair involving either A or B can trigger further merges into the same cluster.
4. Issues that never appear in a pair with `score ≥ MIN_SCORE` form singleton clusters
   (cluster size = 1).

After clustering, partition results:
- **Clusters**: groups with `|members| ≥ MIN_CLUSTER` — these become EPIC proposals.
- **Singletons**: groups with `|members| < MIN_CLUSTER` — surfaced separately.

If no clusters exist (all orphans are singletons), skip to Step 5 (Singletons) after
reporting:
```
No clusters found above the threshold (MIN_SCORE=<value>, MIN_CLUSTER=<value>).
All <N> orphaned issues remain unclusterable. Surfacing as singletons below.
```

---

## Step 4: Synthesize EPIC Titles and Summaries

For each cluster, derive a proposed EPIC title and summary:

### Title Synthesis

1. Collect all word tokens (post-stopword-filter) across all issues in the cluster.
2. Rank by frequency descending.
3. Take the top 3–5 terms as the "shared vocabulary."
4. Compose a title from the top terms, capitalizing each word. Examples:
   - `["cli", "output", "format"]` → `"CLI Output Format"`
   - `["loop", "harness", "evaluation"]` → `"Loop Harness Evaluation"`
5. If the title is ambiguous or less than 2 unique high-frequency terms exist, fall back
   to a title derived from the most common word in the cluster's issue titles directly.

### Summary Synthesis

Write 1–2 sentences that describe the cluster's theme using the shared vocabulary and
the individual issue titles. Format:

```
Group of <N> related issues concerning <top shared terms>. Includes: <ISSUE-A> (<title>),
<ISSUE-B> (<title>), ...
```

### Priority Inheritance

Set the proposed EPIC's `priority` to the most-common priority value among the cluster's
members. Break ties by taking the highest priority (lowest P-number).

Sort clusters by descending member count before presenting.

---

## Step 5: Proposal Flow

### Interactive Mode (no `--auto`)

Present all cluster proposals via `AskUserQuestion` (one question, `multiSelect: true`):

```yaml
questions:
  - question: "Which EPIC proposals should be created? Select all you want to create."
    header: "EPIC Proposals"
    multiSelect: true
    options:
      - label: "Cluster 1 → new EPIC \"CLI Output Format\" (5 issues)"
        description: "FEAT-10, BUG-22, ENH-31, FEAT-45, ENH-67 — cli output format display"
      - label: "Cluster 2 → new EPIC \"Loop Harness Evaluation\" (3 issues)"
        description: "FEAT-12, ENH-28, FEAT-55 — loop harness evaluation quality"
```

Sort options by descending cluster size. Apply only the proposals the user selects.

If the user selects nothing, report:
```
No EPICs created.
```
Then proceed to Step 5b (Singletons).

### Auto Mode (`--auto`)

Skip the prompt. Create an EPIC for every cluster with `|members| ≥ MIN_CLUSTER`.
Report:
```
Auto mode: creating N EPIC(s) from clusters with ≥ MIN_CLUSTER issues.
```

---

## Step 5b: Singleton Surfacing

After handling cluster proposals (or if no clusters exist), surface all singleton
issues (orphans not in any qualifying cluster).

If singletons exist, present them via `AskUserQuestion` (one question, `multiSelect: true`):

```yaml
questions:
  - question: "These orphaned issues did not cluster with others. Wrap any in a single-child EPIC?"
    header: "Singletons"
    multiSelect: true
    options:
      - label: "Wrap FEAT-99 in its own EPIC"
        description: "FEAT-99: title-of-feat-99 — no cluster match above threshold"
      - label: "Wrap BUG-7 in its own EPIC"
        description: "BUG-7: title-of-bug-7 — no cluster match above threshold"
```

In `--auto` mode: skip the singleton prompt entirely. Report:
```
Auto mode: skipping N singleton(s) (use interactive mode to optionally wrap them).
```

---

## Step 6: Create Accepted EPICs and Write-Back

For each accepted proposal (cluster or singleton-wrap):

### 6a. Allocate EPIC ID

Call `ll-issues next-id` **immediately before each Write** — never batch-allocate IDs
upfront. If the PostToolUse hook reports the file was deleted (duplicate integer ID),
call `ll-issues next-id` again and retry.

```bash
EPIC_ID=$(ll-issues next-id)
```

### 6b. Determine EPIC file path

Use the standard filename pattern:
```
{{config.issues.base_dir}}/epics/<PRIORITY>-<EPIC_ID>-<slugified-title>.md
```

Slugify the proposed title: lowercase, replace spaces and non-alphanumeric with `-`,
collapse repeated `-`.

### 6c. Write the EPIC file

```bash
TODAY=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_ONLY=$(date -u +"%Y-%m-%d")
```

EPIC frontmatter and body template:

```markdown
---
id: EPIC-NNN
title: <synthesized title>
type: EPIC
priority: <inherited priority>
status: open
captured_at: "<TODAY>"
discovered_date: <DATE_ONLY>
discovered_by: create-epics-from-unparented
relates_to: [CHILD_ID_1, CHILD_ID_2, ...]
---

# EPIC-NNN: <synthesized title>

## Summary

<synthesized summary>

## Children

- **CHILD_ID_1** — child issue 1 title
- **CHILD_ID_2** — child issue 2 title
```

Use the `Write` tool to create the EPIC file at the path determined in 6b.

### 6d. Write `parent:` back to each child issue

Read the child file. Add `parent: EPIC-NNN` to the YAML frontmatter using `Edit` to
insert the line before the closing `---` of the frontmatter block:

```
# Before (last field in frontmatter):
status: open
---

# After:
status: open
parent: EPIC-NNN
---
```

If `parent:` already exists with a non-null value, skip this child and log:
`⚠ CHILD_ID already has parent: <existing_value>, skipping write-back.`

### 6e. Stage all files

```bash
git add "<epic_path>"
git add "<child_path_1>"
git add "<child_path_2>"
...
```

Stage each file by explicit path — never use `git add .issues/` (sweeps unrelated files;
see BUG-1976).

---

## Step 7: Report Results

Print a summary of all created EPICs and their linked children:

```
Created N EPIC(s) from M orphaned issue(s):

  ✓ EPIC-42 "CLI Output Format" (5 issues)
      • FEAT-10 — issue title
      • BUG-22  — issue title
      • ENH-31  — issue title
      • FEAT-45 — issue title
      • ENH-67  — issue title

  ✓ EPIC-43 "Loop Harness Evaluation" (3 issues)
      • FEAT-12 — issue title
      • ENH-28  — issue title
      • FEAT-55 — issue title

  ⊘ 2 singleton(s) left unparented: FEAT-99, BUG-7

Files staged. Run /ll:commit to commit the changes.
```

If nothing was created (user declined all proposals), report:
```
No EPICs created. Run /ll:link-epics to assign orphans to existing EPICs.
```

---

## Usage Examples

```bash
# Interactive mode: present cluster proposals, user selects which EPICs to create
/ll:create-epics-from-unparented

# Auto mode: create EPICs for all clusters without prompting
/ll:create-epics-from-unparented --auto

# Require at least 3 issues to form a cluster (stricter grouping)
/ll:create-epics-from-unparented --min-cluster 3

# Lower the Jaccard threshold to 0.2 for broader clusters
/ll:create-epics-from-unparented --min-score 0.2

# Combine: auto-create with custom thresholds
/ll:create-epics-from-unparented --auto --min-cluster 2 --min-score 0.25
```

**Sister skill:** Use `/ll:link-epics` after creating EPICs to assign any remaining
orphaned issues to the newly created (or existing) EPICs via similarity scoring.
