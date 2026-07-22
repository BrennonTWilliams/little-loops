---
name: decide-issue
description: Use when asked to select the winning implementation option for an issue with decision_needed.
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(wc:*)
  - Bash(git:*)
  - Bash(ll-issues:*)
  - Agent
metadata:
  short-description: Use when asked to select the winning implementation option for an issue with dec
---

# Decide Issue

Resolves multi-option implementation decisions by gathering codebase evidence for each option and selecting the best fit. Where `/ll:refine-issue --auto` deposits competing approaches and sets `decision_needed: true`, this skill closes the loop — scoring every option and annotating the winner directly in the issue file.

## When to Use

Run after `/ll:refine-issue` when `decision_needed: true` is set in the issue frontmatter:
- The Proposed Solution section contains 2+ competing implementation options
- The pipeline is blocked because no single approach has been selected
- You want an evidence-based decision rather than a gut-check pick

Can also be run manually on any issue that has multiple options in its Proposed Solution, even without `decision_needed: true`.

## Arguments

```
/ll:decide-issue [<issue-id>] [--auto] [--dry-run] [--validate-only]
```

| Flag | Meaning |
|------|---------|
| `--auto` | Non-interactive mode: write decision without prompting |
| `--dry-run` | Preview the decision without modifying the issue file |
| `--validate-only` | Probe decidability only (Phases 1–2.5); no scoring, no writes. Exit 0 if there is something to decide, exit 1 with `OPTIONS_MISSING` otherwise (ENH-2443) |
| `--deposit-attempted` | Internal runtime flag, not a CLI arg — Phase 2.5 sets this after invoking `/ll:refine-issue --auto` once, bounding the auto-recovery retry to a single attempt per invocation (ENH-2443) |

**Examples:**
```bash
/ll:decide-issue FEAT-948
/ll:decide-issue ENH-277 --auto
/ll:decide-issue BUG-042 --auto --dry-run
/ll:decide-issue FEAT-398 --auto --validate-only
```

---

## Phase 1: Parse Arguments

```
ISSUE_ID = ""
AUTO_MODE = false
DRY_RUN = false
VALIDATE_ONLY = false
DEPOSIT_ATTEMPTED = false   # internal — never read from ARGUMENTS; set by Phase 2.5 itself

# Auto-enable in automation contexts
if ARGUMENTS contains "--dangerously-skip-permissions" or env LL_NON_INTERACTIVE is set or env DANGEROUSLY_SKIP_PERMISSIONS is set: AUTO_MODE = true

# Explicit flags
if ARGUMENTS contains "--auto": AUTO_MODE = true
if ARGUMENTS contains "--dry-run": DRY_RUN = true
if ARGUMENTS contains "--validate-only": VALIDATE_ONLY = true

# Extract issue ID (first non-flag token)
for token in ARGUMENTS:
    if not starts with "--": ISSUE_ID = token; break

if ISSUE_ID is empty:
    print "Error: issue_id is required"
    print "Usage: /ll:decide-issue [ISSUE_ID] [--auto] [--dry-run] [--validate-only]"
    exit 1
```

---

## Phase 2: Locate Issue File

```bash
FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
    exit 1
fi
```

Read the full issue file to extract:
- YAML frontmatter (particularly `decision_needed`)
- The full "## Proposed Solution" section text
- Issue title and type for context

---

## Phase 2.5: Decidability Gate (ENH-2443)

Before spending a full scoring pass (or, for direct/FSM callers, before running at all),
determine whether there is anything to decide. Run the **same extraction patterns as Phase
3** (Patterns 1–4, including the Pattern 4 → `## Codebase Research Findings` /
`## Implementation Status` widening when Proposed Solution yields 0) to compute `OPTIONS`.
Do not score, do not spawn agents, do not write to the issue file in this phase.

**Branch:**
- `OPTIONS >= 1` → decidable. If `VALIDATE_ONLY`: exit 0. Otherwise: continue to Phase 3
  (which re-runs extraction normally; the Phase 2.5 count is a pre-check, not a cache).
- `OPTIONS == 0`:
  - If `VALIDATE_ONLY`: emit `OPTIONS_MISSING` (see token shape below) and exit 1.
  - If not `VALIDATE_ONLY` and `AUTO_MODE = true` and `DEPOSIT_ATTEMPTED = false`: invoke
    `/ll:refine-issue ${ISSUE_ID} --auto` once, set `DEPOSIT_ATTEMPTED = true`, then re-run
    the Phase 2.5 extraction against the (possibly changed) issue content. Whether the
    re-scan now finds `OPTIONS >= 1` or still `OPTIONS == 0`, `DEPOSIT_ATTEMPTED` is now
    `true`, so the next bullet's condition applies — fall through to Phase 3, which falls
    through to Phase 3b's inline provisional-language scan when `AUTO_MODE = true` and
    `OPTIONS == 0` (Pattern D can lock in a clear winner even when no formal
    `### Option A/B` blocks exist). `MANUAL_REVIEW_RECOMMENDED` is no longer emitted from
    this phase: an exhausted retry now reaches Phase 3b before any manual-review
    disposition is considered, rather than short-circuiting to one.
  - If not `VALIDATE_ONLY` and (`AUTO_MODE = false` or `DEPOSIT_ATTEMPTED = true`): fall
    through to Phase 3 unchanged — Phase 3's own `OPTIONS` empty-handling (interactive
    "nothing to decide" message, or Phase 3b's inline scan in auto mode) already covers
    this case and remains the source of truth for non-validate-only runs that reach it a
    second time.

### `OPTIONS_MISSING` token shape

```
## RESULT: OPTIONS_MISSING
reason: decision_needed is true but ## Proposed Solution has no enumerable alternatives
suggested_command: /ll:refine-issue ${ISSUE_ID} --auto
exit_code: 1
```

---

## Phase 3: Extract Options

Scan the Proposed Solution section for options using these patterns (in order of precedence). If Proposed Solution yields 0 options, repeat the scan over `## Codebase Research Findings` and `## Implementation Status` — refined issues often deposit options there.

### Pattern 1 — Section Headers
```
Match: lines matching /^### Option [A-Z0-9]/i
Example: ### Option A, ### Option B, ### Option C
Extract: the header text as the option title; body text until next ### or ## as option description
```

### Pattern 2 — Bold Labels
```
Match: lines starting with **Option [A-Z0-9]** or **Option [0-9]+**
Example: **Option A (recommended)**: ..., **Option B**: ...
Extract: the bold label (stripped of **) as option title; rest of the line and following paragraph as description
```

### Pattern 3 — Numbered Top-Level Items
```
Match: numbered list items at top level: /^[0-9]+\.\s+\*\*Option/ or /^[0-9]+\.\s+[A-Z][^.]+approach/
Example: 1. **Option A** (chosen): ..., 2. Use existing utility ...
Extract: the item label or leading phrase as option title; full item text as description
Note: only apply this pattern if Pattern 1 and Pattern 2 found 0 options
```

### Pattern 4 — Bullet-List Options
```
Match: bullet items naming lettered/numbered options: /^[-*]\s+\(([a-z0-9])\)\s+/ or /^[-*]\s+\*?\*?Option\s+([A-Z0-9])/
Example: - (a) useEffect in SettingsSheet…, - (b) Hoist into App.tsx…, - **Option A**: …
Extract: the (x)/Option label as option title; body text until the next bullet or heading as description
Note: only apply if Patterns 1–3 found 0 options
```

### Option Count Check

After extraction:

**Auto-mode bullet-list handling**: if the ONLY options found came from Pattern 4 and `AUTO_MODE = true`, do NOT route them to Phase 4 scoring — automation must not re-litigate an informal list the author may have already settled. Set `OPTIONS = 0` so flow proceeds to Phase 3b, where Pattern D resolves the case: a declarative recommendation marker naming one of the bullet options locks it in; absent a marker, `decision_needed` stays `true` for human review. In interactive mode, Pattern-4 options ARE scored through Phases 4–7 normally.

- If `OPTIONS` is empty and `AUTO_MODE = false`: print `No options found in Proposed Solution — nothing to decide.` and exit cleanly
- If `OPTIONS` is empty and `AUTO_MODE = true`: proceed to Phase 3b (Inline Decision Scan)
- If `len(OPTIONS) == 1`: print `Only one option present — no decision required. Clearing decision_needed if set.` then proceed to Phase 7 (frontmatter update only: set `decision_needed: false`)
- If `len(OPTIONS) >= 2`: proceed to Phase 4

---

## Phase 3b: Inline Decision Scan (AUTO_MODE only)

**Precondition**: `AUTO_MODE = true` AND `OPTIONS = 0` after Phase 3 pattern scan.

### Phase 3b-i: Skip resolved questions

Before scanning for provisional language, collect all numbered list items under the `## Open Questions` section and check each for a resolution marker:

- `✅ RESOLVED`, `✔ RESOLVED`, `**RESOLVED**`, `> **RESOLVED**`

Markers appear inline after the bold question label, e.g.:
`**Fork vs. flag.** ✅ **RESOLVED** (2026-06-04 by …)`

**If the `## Open Questions` section exists with items and they are ALL marked resolved, and `decision_needed: true`**:

1. Output:
   ```
   ## RESULT: NO_ACTIONABLE_DECISIONS — all questions already marked resolved
   decision_needed remains true (human-required decision; automation cannot clear a flag it did not earn)
   ```
2. Do NOT edit the issue file.
3. Do NOT clear `decision_needed` — leave it as `true`.
4. Exit 0, then proceed to Phase 8 (Append Session Log) only. Skip Phases 4–7 and Phase 9.

**If the section is absent, has no items, or has at least one unresolved item**, fall through to the provisional-language scan below — do NOT take the `NO_ACTIONABLE_DECISIONS` exit. An absent `## Open Questions` section is not "nothing to decide": options and recommendations commonly live in `## Proposed Solution` or `## Codebase Research Findings`. When the section exists, scope the scan to its unresolved items only.

---

Scan ALL sections of the issue file (not just `## Proposed Solution`) for provisional decision language using these patterns:

### Provisional Pattern A — Parenthetical `(e.g., ...)`
```
Match: parenthetical containing `e.g.,` followed by a concrete name
Example: (e.g., completed_at: frontmatter field)
Candidate: the specific approach named inside the parenthetical
```

### Provisional Pattern B — Inline `TBD` design marker
```
Match: `TBD` used as a placeholder for a design decision (not a research gap)
Surrounding context must name a single approach being considered
Example: "field name: TBD (leaning toward completed_at)"
Candidate: the approach mentioned in the surrounding sentence
```

### Provisional Pattern C — Definitive replacement language
```
Match: phrases like "fundamental rethink" / "must be replaced with" / "should be replaced by"
Example: "the existing approach must be replaced with direct file writes"
Candidate: the concrete replacement approach named
```

### Provisional Pattern D — Declarative recommendation
```
Match: prose naming a winning option without a provisional wrapper:
  **Recommended**: (b)  /  the recommendation is now (b)  /  Refresh N supersedes prior — (a)+(b)
Candidate: the referenced option(s); multi-part winners like (a)+(b) are allowed.
Requirement: the referent must exist as a Pattern-4 bullet option in `## Proposed Solution` or
`## Codebase Research Findings` (existing-bullet case), OR the referent must be one of 2+
concrete alternatives named inline in an unresolved `## Open Questions` item (ENH-2715) — e.g.
"could do X or Y" with a stated preference; no pre-existing bullet is required for this shape,
since the alternatives are materialized as structured options in Resolution Logic step 1 below.
A marker (or an Open-Questions item naming a preference among 2+ alternatives) with a
resolvable referent is a **clear winner** — treat as decided.
```

For each provisional pattern match, read 3–5 lines of surrounding context to determine if one approach is clearly stated (not merely listed as a possibility).

### Resolution Logic

Classify each match as:
- **Clear winner**: the provisional wrapper names exactly one concrete approach and surrounding context treats it as the intended design.
- **Ambiguous**: multiple alternatives listed, no single preference expressed.

**If exactly one clear winner is found:**

1. **Materialize alternatives, if not already structured (ENH-2715)**: check whether the clear
   winner's named alternatives already exist as `### Option A`/`### Option B` (Pattern 1) or
   `**Option A**`/`**Option B**` (Pattern 2) blocks under `## Proposed Solution`. They do NOT
   for two cases this step exists to handle: (a) the referent is only a Pattern-4 bullet (`- (a)
   ...` / `- (b) ...`), or (b) the referent is an Open-Questions-named alternative with no
   pre-existing bullet at all. For either case, rewrite the named alternatives in place as
   `**Option A**`/`**Option B**` blocks under `## Proposed Solution`, reusing the exact
   bold-label template `commands/refine-issue.md`'s "Decision-Point Formatting" rule already
   produces (ENH-2607) — additive/rewrite-in-place of the same prose already matched, never
   inventing alternatives beyond what was named:
   ```markdown
   **Option A**: [first alternative, verbatim from the existing text]

   **Option B**: [second alternative, verbatim from the existing text]
   ```
   If the alternatives were already structured as Pattern 1/2 blocks, this step is a no-op —
   proceed directly to step 3.
2. **Re-scan and route to full scoring (ENH-2715)**: after materializing, re-run the Phase 3
   extraction. If it now finds `OPTIONS >= 2` (the materialized blocks match Pattern 2): log
   `✓ Phase 3b: materialized informal decision as structured options — proceeding to Phase 4
   scoring`, then proceed directly to **Phase 4** (Gather Codebase Evidence) for full
   evidence-based scoring instead of the lock-in-only exit in step 3. Phase 4–7 independently
   adds the `> **Selected:**` callout and `### Decision Rationale` subsection once scoring
   completes, and Phase 7b sets `decision_needed: false` — skip steps 3–4 below for this path.
3. **Lock in without scoring** (alternatives were already structured, or materialization found
   no 2+-alternative shape to reformat): edit the issue text to make the approach declarative —
   for Patterns A–C remove the provisional qualifier (`e.g.,`/parenthetical wrapper, `TBD`,
   `"must be replaced with"`); for Pattern D add a `> **Selected:** (x) — per the stated
   recommendation` callout on the recommended bullet. State the concrete approach as decided.
4. Use the Edit tool (inline `---` block replacement — same pattern as Phase 7b) to set `decision_needed: false` in the issue frontmatter:
   ```
   READ the current --- frontmatter block (from opening --- to closing ---)
   FIND the decision_needed field:
     IF field exists: replace its value with false
     IF field absent: add decision_needed: false after the last existing field
   USE Edit tool to replace the entire --- block with the updated block
   ```
   **Idempotency**: if `decision_needed` is already `false`, skip the write and log `✓ decision_needed already false — no update needed`.
5. Log: `✓ Phase 3b: resolved provisional decision — [approach] locked in; decision_needed set to false`
6. Proceed to Phase 8 (Append Session Log) and Phase 9 (Output Report), skipping Phases 4–7 — except the materialize-and-score path in step 2, which proceeds through Phase 4–7 normally before reaching Phase 8/9.

**If no clear winner (zero candidates or all ambiguous):**
1. Log: `✗ Phase 3b: no resolvable provisional decision found — leaving decision_needed unchanged`
2. Leave `decision_needed: true` unchanged.
3. Exit cleanly — do not prompt the user, do not ask interactive questions.
4. Proceed to Phase 8 (Append Session Log) only — skip Phases 4–7 and Phase 9's normal report.

---

## Phase 4: Gather Codebase Evidence (Parallel Agents)

Spawn one `ll:codebase-pattern-finder` Agent **per option** in a **single message** with multiple Agent tool calls (parallel spawn). Use `run_in_background: false` and wait for all results synchronously in this same turn before proceeding.

See [reference.md](reference.md) for the full per-option agent prompt template (what to find,
what to return: evidence for/against, reuse score, fit summary).

**Wait for ALL agents' results synchronously in this same turn before proceeding to Phase 5.**

---

## Phase 5: Score Each Option

For each option, produce a score across 4 dimensions (0–3 each, 12 max):

| Dimension | 0 | 1 | 2 | 3 |
|-----------|---|---|---|---|
| **Consistency** | Contradicts existing patterns | Partial fit | Mostly consistent | Matches patterns exactly |
| **Simplicity** | High complexity, many new abstractions | Moderate complexity | Mostly straightforward | Minimal code, no new abstractions |
| **Testability** | Hard to isolate/mock | Requires significant test scaffolding | Testable with some effort | Easily unit-testable |
| **Risk** | High risk (broad surface, unknowns) | Medium risk | Low risk, contained scope | Negligible risk |

**Scoring rules:**
- Use the agent evidence from Phase 4 to inform the Consistency score (agent's `reuse_score` feeds directly)
- Apply scores based on the option description and codebase findings — not assumptions
- If two options tie, prefer the one with higher Consistency (codebase fit is the tiebreaker)
- Document specific evidence citations for each score

Produce a per-option scoring record:

```
OPTIONS_SCORED:
  - title: "Option A"
    scores: { consistency: N, simplicity: N, testability: N, risk: N }
    total: N/12
    evidence_for: [key findings]
    evidence_against: [key findings]
  - title: "Option B"
    ...

SELECTED: title of highest-scoring option
RATIONALE: 2-3 sentence explanation citing evidence
```

---

## Phase 6: Prepare Annotation

Build the annotation content before any file writes:

### Selected Option Callout

Locate the winning option's text in the issue. Insert immediately after the option's title/label line:

```markdown
> **Selected:** [option title] — [one-line rationale]
```

### Decision Rationale Subsection

Append to the end of the Proposed Solution section. See [reference.md](reference.md) for the
full `### Decision Rationale` template (selected option, reasoning, scoring summary table, key
evidence).

---

## Phase 7: Apply Changes

**If `DRY_RUN` is true**: skip all file writes — output the full annotation content in the DRY RUN PREVIEW block (see Phase 9 output report) then exit.

### 7a: Annotate Issue File

Use the Edit tool to:
1. Insert the `> **Selected:** ...` callout immediately after the winning option's title line in the Proposed Solution section
2. Append the `### Decision Rationale` subsection at the end of the Proposed Solution section (before the next `##` heading)

**Idempotency rule**: if the issue already contains a `### Decision Rationale` section, skip the annotation write and log `⚠ Decision already annotated — skipping annotation (idempotent)`. Only proceed to the frontmatter update.

### 7b: Update Frontmatter

Set `decision_needed: false` in the issue's YAML frontmatter using the Edit tool inline `---` block replacement pattern:

```
READ the current --- frontmatter block (from opening --- to closing ---)
FIND the decision_needed field:
  IF field exists: replace its value with false
  IF field absent: add decision_needed: false after the last existing field

USE Edit tool to replace the entire --- block with the updated block
```

**Idempotency**: if `decision_needed` is already `false`, skip the write and log `✓ decision_needed already false — no update needed`.

Append a decision entry to the log (silent no-op when the decisions log is absent). Storage is hybrid — a legacy `.ll/decisions.yaml` flat file and/or `.ll/decisions.d/*.json` fragments — so gate on either (a fresh, never-compacted install has only the fragment dir):

```bash
if [ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]; then
    ll-issues decisions add \
      --type=decision \
      --category="architecture" \
      --issue="{{issue_id}}" \
      --rule="$SELECTED_OPTION_TITLE" \
      --rationale="$RATIONALE" \
      --alternatives-rejected="$ALTERNATIVES_REJECTED" \
      2>/dev/null || true
fi
```

---

## Phase 8: Append Session Log

```bash
ll-issues append-log <path-to-issue-file> /ll:decide-issue
```

If `ll-issues` is not available, append manually to the Session Log section:

```
- `/ll:decide-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

Stage the updated file:

```bash
git add "{{issue_file_path}}"
```

---

## Phase 9: Output Report

See [reference.md](reference.md) for the full Output Report template (issue summary,
options table, scoring table, decision, changes applied, dry-run preview, next steps).

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:refine-issue --auto` — deposits implementation options, sets `decision_needed: true`
- **After**: `/ll:wire-issue` — traces callers and integration points for the now-selected implementation approach

### When to Use vs. Related Commands

| Skill | Purpose |
|-------|---------|
| `refine-issue` | Fills knowledge gaps; may deposit competing options |
| `decide-issue` | Selects the best option from competing alternatives using codebase evidence |
| `wire-issue` | Traces all wiring touchpoints for the selected implementation |
| `confidence-check` | Evaluates implementation readiness score |

`decide-issue` is specifically for the "refine-issue deposited multiple options but hasn't selected one" problem. It consumes `decision_needed: true` and produces a clear, annotated winner so the pipeline can continue.

### FSM callers

FSM `shell` states cannot invoke slash commands directly (no LLM dispatch from a
subprocess), so `--validate-only` is a skill-level flag for direct/interactive use only.
FSM-driven loops (`rn-remediate`, `autodev`) instead call the deterministic companion CLI
`ll-issues check-decidable <ID>` — a pure-Python re-implementation of the same Patterns
1–4 counting logic (no LLM, no scoring, no write) — as a cheap pre-`decide` gate: exit 0
means "decide has something to act on", exit 1 routes the loop through
`/ll:refine-issue --auto` to deposit options before retrying (ENH-2443). This mirrors the
`ensure_formatted` → `ll-issues format-check` precedent (ENH-2426): the skill documents
the human-facing behavior, a companion CLI gives automation a real non-LLM evaluator.
