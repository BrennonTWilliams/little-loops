---
name: link-epics
description: Assign orphaned issues to existing EPICs or synthesize new EPICs from them, via Jaccard similarity scoring.
disable-model-invocation: true

argument-hint: "[--mode assign|synthesize] [--auto] [--min-score <threshold>] [--min-cluster <n>]"
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
    description: "--mode assign|synthesize (default: assign); --auto to apply proposals without prompting; --min-score 0.5 to set the Jaccard threshold; --min-cluster 2 (synthesize only) to set minimum issues per cluster"
    required: false
metadata:
  short-description: Assign orphans to EPICs, or synthesize new EPICs from them, via similarity.
---

# Link Epics

Discovers open BUG/FEAT/ENH issues without a `parent:` frontmatter field and scores
them by Jaccard similarity on title + summary text. Two modes cover the two
directions of the same operation:

- **`mode: assign`** (default) — score orphans against **existing** open EPICs and
  link accepted proposals.
- **`mode: synthesize`** — cluster orphans by similarity to each other and propose
  **new** EPIC files to cover them.

---

## Step 1: Parse Arguments

- Parse `MODE` from `--mode <value>`. Default: `assign`.
- Set `AUTO=true` if `--auto` is present.
- Parse `MIN_SCORE` from `--min-score <value>` if present (a float between 0.0 and 1.0).
  Per-mode defaults when not given (the two modes were tuned independently and are
  **not** reconciled to a shared value — see Rationale below):
  - `mode: assign` — `0.7` if `--auto`, else `0.0` (show all proposals).
  - `mode: synthesize` — `0.3` regardless of `--auto`.
- `mode: synthesize` only: parse `MIN_CLUSTER` from `--min-cluster <value>` (integer
  ≥ 1). Default: `2`.

**Rationale for not reconciling `--min-score` defaults**: `assign` scores an orphan
against a curated existing-EPIC population (higher signal expected per pair, so a
higher bar is appropriate); `synthesize` scores orphan-to-orphan pairs to *discover*
a grouping, where a lower bar surfaces more candidate clusters for the user to
accept or reject. Collapsing to one value would bias one mode's proposal volume.

---

## Step 2: Discover Orphaned Open Issues (shared)

Issues under `{{config.issues.base_dir}}` are found via three separate calls
(one per type, since `--type` is single-valued), using `--include-summary` so no
per-orphan `Read` is needed:

```bash
ll-issues list --status open --type BUG --json --include-summary
ll-issues list --status open --type FEAT --json --include-summary
ll-issues list --status open --type ENH --json --include-summary
```

Filter orphans directly from the JSON output: the `parent` key is `null` when
absent. Keep only issues where `parent` is `null`:

```python
orphans = [i for i in data if not i.get("parent")]
```

For each orphan, record its `id`, `path`, `title`, and `summary` (already embedded
by `--include-summary`). Build score text: `orphan_score_text = title + " " + summary`.

If no orphaned issues exist, report:
```
No orphaned open issues found. All open issues already have a parent EPIC assigned.
```
Stop.

---

## Step 3: Word Extraction and Jaccard Similarity (shared)

From each score text:
1. Lowercase all text.
2. Extract all alphabetic tokens of 3+ characters.
3. Exclude common stop words: `the`, `and`, `for`, `that`, `this`, `with`, `have`,
   `from`, `are`, `was`, `not`, `will`, `all`, `but`, `can`, `its`, `one`, `any`,
   `also`, `when`, `been`, `which`, `their`, `they`, `into`, `more`, `has`, `add`,
   `use`, `new`, `via`, `per`, `set`, `run`.

```
score = |words_A ∩ words_B| / |words_A ∪ words_B|
```

If either word set is empty: `score = 0.0`. This prose block is **not** invoked from
`little_loops/text_utils.py`'s `extract_words()`/`calculate_word_overlap()` — the two
implementations describe an equivalent Jaccard formula independently, and their stop
word lists diverge from each other as a pre-existing inconsistency unrelated to this
merge. Not reconciled here; out of scope.

---

## Mode: `--mode assign` (default)

### A1: Discover Open EPICs

```bash
ll-issues list --status open --type EPIC --json
```

Parse the JSON output. For each EPIC, record its `id`, `path`, and `title`. Then:

1. Read the file content.
2. Strip frontmatter (everything between the first `---` pair).
3. Extract summary: find text under `## Summary` heading using pattern
   `## Summary\n(.+?)(?=\n##|\Z)` with DOTALL matching.
4. Build score text: `epic_score_text = epic_title + " " + summary_text`.

If no open EPICs exist, report:
```
No open EPICs found. Create an EPIC first, then run /ll:link-epics again.
```
Stop.

### A2: Score and Select

For each orphan × EPIC pair, compute the Jaccard score (Step 3). For each orphan,
select the **best-matching EPIC** (highest score). Skip pairs with `score = 0.0`.
Apply the `MIN_SCORE` filter — drop proposals where `score < MIN_SCORE`.

**Confidence Tiers**: **HIGH** (score ≥ 0.7), **MEDIUM** (score ≥ 0.4), **LOW**
(score > 0.0 and < 0.4).

If no proposals remain after filtering, report:
```
No matching EPICs found above the score threshold (MIN_SCORE=<value>).
Try /ll:link-epics --min-score 0.2 to lower the threshold, or run without
--min-score to see all proposals.
```
Stop.

### A3: Proposal Flow

Sort proposals: HIGH first, then MEDIUM, then LOW; within each tier, by score
descending.

**Interactive (no `--auto`)**: present via `AskUserQuestion`:

```yaml
questions:
  - question: "Link these orphaned issues to their proposed epics? Select all you want to apply."
    header: "Proposals"
    multiSelect: true
    options:
      - label: "ENH-123 → EPIC-42 (HIGH 0.82)"
        description: "title-of-enh-123 — title-of-epic-42"
```

Apply only selected proposals. If nothing is selected, report `No assignments made.`
and stop.

**Auto (`--auto`)**: skip the prompt, apply all proposals where `score >= MIN_SCORE`.
Report: `Auto mode: applying N proposal(s) with score ≥ MIN_SCORE.`

### A4: Apply Assignments

For each accepted proposal (child orphan → parent EPIC):

1. **Write `parent:` to child.** Read the child file, use `Edit` to insert
   `parent: EPIC-NNN` before the closing `---` of the frontmatter block. If
   `parent:` already exists with a non-null value, skip and log:
   `⚠ CHILD_ID already has parent: <existing_value>, skipping.`
2. **Update EPIC `## Children`.** If it exists, append a bullet in the
   canonical rendered shape:

   ```markdown
   - **CHILD_ID** — child issue title (open)
   ```

   The trailing `(open)` reflects the child's status at write time. This
   format mirrors what `ll-issues epic-progress EPIC-NNN --format markdown`
   emits under `- **Children**` (single home for child membership in the
   rendered form per ENH-162 AC #2). If the section does not exist, insert
   it before `## Status` (or at end of file).

3. **Post-write consistency check.** Re-read the child's frontmatter and confirm
   `parent:` equals the EPIC ID; confirm the child ID appears in the EPIC's
   `## Children` section. If either check fails, emit a non-blocking warning:
   `⚠ Post-write consistency check failed for CHILD_ID: parent: not set to
   EPIC-NNN or child absent from ## Children`. This substitutes for
   `ll-issues epic-consistency` until FEAT-2332 ships.

   > **Note (ENH-162)**: never write child IDs into `relates_to:` — containment
   > lives in `parent:` only. `relates_to:` is for peer/see-also links
   > between EPICs and sibling issues.
4. **Stage both files**: `git add "child_issue_path"` and `git add "epic_path"`.

### A5: Report Results

```
Linked N orphaned issue(s) to EPICs:

  ✓ ENH-123 → EPIC-42 (HIGH 0.82) — issue title
  ✓ BUG-55  → EPIC-42 (MEDIUM 0.51) — issue title
  ✗ FEAT-77  — no match above threshold (best score: 0.12)

Files staged. Run /ll:commit to commit the changes.
```

### Usage Examples

```bash
/ll:link-epics                              # interactive, MIN_SCORE=0.0
/ll:link-epics --auto                       # apply HIGH-tier (≥0.7) without prompting
/ll:link-epics --min-score 0.4              # interactive, MEDIUM+ only
/ll:link-epics --auto --min-score 0.5       # auto with custom threshold
```

---

## Mode: `--mode synthesize`

### S1: Cluster Orphans by Jaccard Similarity

1. Compute pairwise Jaccard scores (Step 3) for all orphan pairs.
2. Sort pairs by descending score.
3. Iterate pairs: if `score ≥ MIN_SCORE`, merge the two issues into the same cluster
   using union-find (or equivalent) — merging A and B means any future pair
   involving either can trigger further merges into the same cluster.
4. Issues that never pair at `score ≥ MIN_SCORE` form singleton clusters (size 1).

Partition results: **clusters** (`|members| ≥ MIN_CLUSTER`) become EPIC proposals;
**singletons** (`|members| < MIN_CLUSTER`) are surfaced separately.

If fewer than 2 orphans exist, report:
```
Fewer than 2 orphaned open issues found — nothing to cluster.
All open issues already have a parent EPIC assigned, or there are too few orphans to group.
```
Stop.

If no clusters exist (all singletons), report and skip to S3 (Singletons):
```
No clusters found above the threshold (MIN_SCORE=<value>, MIN_CLUSTER=<value>).
All <N> orphaned issues remain unclusterable. Surfacing as singletons below.
```

### S2: Synthesize EPIC Titles and Summaries

For each cluster:

- **Title**: collect word tokens (post-stopword-filter) across the cluster, rank by
  frequency, take the top 3–5 terms, compose a capitalized title (e.g.
  `["cli", "output", "format"]` → `"CLI Output Format"`). If ambiguous or fewer than
  2 unique high-frequency terms, fall back to the most common word across the
  cluster's issue titles directly.
- **Summary**: 1–2 sentences using the shared vocabulary and issue titles:
  `Group of <N> related issues concerning <top shared terms>. Includes: <ISSUE-A>
  (<title>), <ISSUE-B> (<title>), ...`
- **Priority**: most-common priority among cluster members; ties break to the
  highest priority (lowest P-number).

Sort clusters by descending member count before presenting.

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
        description: "FEAT-10, BUG-22, ENH-31, FEAT-45, ENH-67 — cli output format display"
```

If nothing is selected, report `No EPICs created.` and proceed to Singletons.

**Auto (`--auto`)**: create an EPIC for every cluster with `|members| ≥ MIN_CLUSTER`.
Report: `Auto mode: creating N EPIC(s) from clusters with ≥ MIN_CLUSTER issues.`

**Singletons**: after handling clusters, if singletons exist present them via a
second `AskUserQuestion` (`multiSelect: true`, one option per singleton: "Wrap
FEAT-99 in its own EPIC"). In `--auto` mode, skip this prompt and report:
`Auto mode: skipping N singleton(s) (use interactive mode to optionally wrap them).`

### S4: Create Accepted EPICs and Write-Back

For each accepted proposal (cluster or singleton-wrap):

1. **Allocate EPIC ID** via `ll-issues next-id`, called **immediately before each
   Write** — never batch-allocate upfront. If the PostToolUse hook reports the file
   was deleted (duplicate integer ID), call `ll-issues next-id` again and retry.
2. **Determine path**:
   `{{config.issues.base_dir}}/epics/<PRIORITY>-<EPIC_ID>-<slugified-title>.md`
   (slugify: lowercase, non-alphanumeric → `-`, collapse repeats).
3. **Write the EPIC file** with `Write`:

```markdown
---
id: EPIC-NNN
title: <synthesized title>
type: EPIC
priority: <inherited priority>
status: open
captured_at: "<TODAY, date -u +%Y-%m-%dT%H:%M:%SZ>"
discovered_date: <DATE_ONLY, date -u +%Y-%m-%d>
discovered_by: link-epics
relates_to: []
---

# EPIC-NNN: <synthesized title>

## Summary

<synthesized summary>

## Children

- **CHILD_ID_1** — child issue 1 title (open)
- **CHILD_ID_2** — child issue 2 title (open)
```

> **Note (ENH-162)**: `relates_to:` is reserved for peer/see-also cross-references
> between EPICs and sibling issues. Child IDs must NOT be listed in `relates_to:` —
> containment is expressed via `parent:` on each child, and the rendered child
> membership lives in the EPIC's `## Children` section (mirrored by
> `ll-issues epic-progress EPIC-NNN --format markdown`). The canonical rendered
> form of child membership is the CLI output, not `relates_to:`.

4. **Write `parent:` back to each child** — same `Edit`-before-closing-`---`
   procedure as A4 step 1; same skip-and-warn behavior on an existing non-null
   `parent:` value.
5. **Stage all files** by explicit path (`git add "<epic_path>"`,
   `git add "<child_path>"` per child) — never `git add .issues/` (sweeps unrelated
   files; see BUG-1976).

### S5: Report Results

```
Created N EPIC(s) from M orphaned issue(s):

  ✓ EPIC-42 "CLI Output Format" (5 issues)
      • FEAT-10 — issue title
      • BUG-22  — issue title

  ⊘ 2 singleton(s) left unparented: FEAT-99, BUG-7

Files staged. Run /ll:commit to commit the changes.
```

If nothing was created (user declined all proposals), report:
```
No EPICs created. Run /ll:link-epics --mode assign to assign orphans to existing EPICs.
```

### Usage Examples

```bash
/ll:link-epics --mode synthesize                                # interactive
/ll:link-epics --mode synthesize --auto                         # create all clusters
/ll:link-epics --mode synthesize --min-cluster 3                # stricter grouping
/ll:link-epics --mode synthesize --min-score 0.2                # broader clusters
/ll:link-epics --mode synthesize --auto --min-cluster 2 --min-score 0.25
```

---

## Choosing a Mode

Run `--mode synthesize` first when no EPICs exist yet, or orphaned issues don't fit
any existing EPIC — it clusters orphans by thematic similarity and proposes new EPIC
files. Then run `--mode assign` (the default) to link any remaining orphans to the
newly created (or pre-existing) EPICs.
