---
name: link-epics
description: Discover orphaned issues and propose parent EPIC assignments via Jaccard similarity scoring.
disable-model-invocation: true

argument-hint: "[--auto] [--min-score <threshold>]"
model: sonnet
allowed-tools:
  - AskUserQuestion
  - Edit
  - Read
  - Bash(ll-issues:*)
  - Bash(git:*)

arguments:
  - name: flags
    description: "--auto to apply HIGH-tier proposals without prompting; --min-score 0.5 to set the minimum Jaccard score threshold"
    required: false
metadata:
  short-description: Discover orphaned issues and propose parent EPIC assignments via similarity.
---

# Link Epics

Discovers open BUG/FEAT/ENH issues without a `parent:` frontmatter field, scores each
against open EPICs using Jaccard similarity on title + summary text, and links accepted
proposals by writing `parent: EPIC-NNN` to the child issue and updating the EPIC's
`## Children` section.

---

## Step 1: Parse Arguments

Extract flags from the arguments:

- Set `AUTO=true` if `--auto` is present.
- Parse `MIN_SCORE` from `--min-score <value>` if present (a float between 0.0 and 1.0).
  - If `--auto` is set and no `--min-score` given: `MIN_SCORE = 0.7` (HIGH-tier default).
  - If `--auto` is not set and no `--min-score` given: `MIN_SCORE = 0.0` (show all proposals).

---

## Step 2: Discover Open EPICs

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

---

## Step 3: Discover Orphaned Open Issues

Issues under `{{config.issues.base_dir}}` are found via three separate calls
(one per type, since `--type` is single-valued):

```bash
ll-issues list --status open --type BUG --json
ll-issues list --status open --type FEAT --json
ll-issues list --status open --type ENH --json
```

Filter orphans directly from the JSON output: the `parent` key is `null` when
absent. Keep only issues where `parent` is `null` — these are **orphaned issues**.

```python
orphans = [i for i in data if not i.get("parent")]
```

No per-file reads needed for orphan detection.

For each orphan:
1. Record its `id`, `path`, and `title` from the JSON.
2. Read the file content (needed for summary extraction in scoring).
3. Extract summary text (same pattern as Step 2).
4. Build score text: `orphan_score_text = orphan_title + " " + summary_text`.

If no orphaned issues exist, report:
```
No orphaned open issues found. All open issues already have a parent EPIC assigned.
```
Stop.

---

## Step 4: Score Orphans Against EPICs

For each orphan × EPIC pair, compute the Jaccard similarity score.

### Word Extraction

From each score text:
1. Lowercase all text.
2. Extract all alphabetic tokens of 3+ characters.
3. Exclude common stop words: `the`, `and`, `for`, `that`, `this`, `with`, `have`,
   `from`, `are`, `was`, `not`, `will`, `all`, `but`, `can`, `its`, `one`, `any`,
   `also`, `when`, `been`, `which`, `their`, `they`, `into`, `more`, `has`, `add`,
   `use`, `new`, `via`, `per`, `set`, `run`.

### Jaccard Similarity

```
score = |words_orphan ∩ words_epic| / |words_orphan ∪ words_epic|
```

If either word set is empty: `score = 0.0`.

### Proposal Selection

For each orphan, select the **best-matching EPIC** (highest score). Skip pairs with
`score = 0.0` (no word overlap). Apply the `MIN_SCORE` filter — drop proposals where
`score < MIN_SCORE`.

### Confidence Tiers

- **HIGH**: score ≥ 0.7
- **MEDIUM**: score ≥ 0.4
- **LOW**: score > 0.0 (and < 0.4)

If no proposals remain after filtering, report:
```
No matching EPICs found above the score threshold (MIN_SCORE=<value>).
Try /ll:link-epics --min-score 0.2 to lower the threshold, or run without
--min-score to see all proposals.
```
Stop.

---

## Step 5: Proposal Flow

Sort proposals: HIGH first, then MEDIUM, then LOW. Within each tier, sort by score
descending.

### Interactive Mode (no `--auto`)

Present all proposals via `AskUserQuestion`:

```yaml
questions:
  - question: "Link these orphaned issues to their proposed epics? Select all you want to apply."
    header: "Proposals"
    multiSelect: true
    options:
      - label: "ENH-123 → EPIC-42 (HIGH 0.82)"
        description: "title-of-enh-123 — title-of-epic-42"
      - label: "BUG-55 → EPIC-42 (MEDIUM 0.51)"
        description: "title-of-bug-55 — title-of-epic-42"
```

Apply only the proposals the user selects. If the user selects nothing, report:
```
No assignments made.
```
Stop.

### Auto Mode (`--auto`)

Skip the prompt. Apply all proposals where `score >= MIN_SCORE` (default 0.7 in
`--auto` mode). Report:

```
Auto mode: applying N proposal(s) with score ≥ MIN_SCORE.
```

---

## Step 6: Apply Assignments

For each accepted proposal (child orphan → parent EPIC):

### 6a. Write `parent:` to child issue

Read the child file. Add `parent: EPIC-NNN` to the YAML frontmatter. Use `Edit` to
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

If `parent:` already exists with a non-null value, skip this file and log a warning:
`⚠ CHILD_ID already has parent: <existing_value>, skipping.`

### 6b. Update EPIC `## Children` section

**If `## Children` exists**: append a bullet at the end of that section:
```markdown
- **CHILD_ID** — child issue title
```

**If no `## Children` section**: insert one before `## Status` (or at end of file if no
`## Status`):
```markdown
## Children

- **CHILD_ID** — child issue title
```

Use `Edit` to apply in-place.

### 6c. Post-write consistency check

After wiring each child, verify:
1. Re-read the child's frontmatter and confirm `parent:` equals the EPIC ID.
2. Confirm the child ID appears in the EPIC's `## Children` section.

If either check fails, emit a non-blocking warning (do not halt):

```
⚠ Post-write consistency check failed for CHILD_ID: parent: not set to EPIC-NNN or child absent from ## Children
```

This inline check substitutes for `ll-issues epic-consistency` until FEAT-2332 ships.

### 6d. Stage both files

```bash
git add "child_issue_path"
git add "epic_path"
```

---

## Step 7: Report Results

Print a summary of all assignments:

```
Linked N orphaned issue(s) to EPICs:

  ✓ ENH-123 → EPIC-42 (HIGH 0.82) — issue title
  ✓ BUG-55  → EPIC-42 (MEDIUM 0.51) — issue title
  ✗ FEAT-77  — no match above threshold (best score: 0.12)

Files staged. Run /ll:commit to commit the changes.
```

---

## Usage Examples

```bash
# Interactive mode: present all proposals, user selects
/ll:link-epics

# Auto mode: apply HIGH-tier (≥0.7) proposals without prompting
/ll:link-epics --auto

# Interactive mode with minimum score filter (show MEDIUM+ only)
/ll:link-epics --min-score 0.4

# Auto mode with custom threshold
/ll:link-epics --auto --min-score 0.5
```

**Sister skill:** When no EPICs exist yet (or orphaned issues don't fit any existing
EPIC), use `/ll:create-epics-from-unparented` first — it clusters orphans by thematic
similarity and proposes new EPIC files. Then run `/ll:link-epics` to assign any
remaining orphans to the newly created EPICs.
