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
trigger_fixtures:
  should_fire:
    - "select the winning implementation option for this issue with decision_needed"
    - "decide the winning implementation option among these"
  should_not_fire:
    - "run a pre-implementation confidence check on this issue"
    - "adversarial review of whether this issue is worth implementing"
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
determine whether there is anything to decide:

```bash
ll-issues locate-options "${ISSUE_ID}" --json
```

Read `count` off the returned JSON as `OPTIONS` — the same call Phase 3 makes, reusing
Phase 3's option-extraction patterns (deterministic pattern precedence: section headers,
bold labels, numbered/bullet items, then the un-preferenced-directive heuristic) rather
than re-deriving them; that precedence lives entirely in
`issue_parser.locate_enumerable_options` (ENH-2950). This phase does no scoring, spawns
no agents, and performs no writes to the issue file — it only reads the CLI's result.

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

Call the same CLI used in Phase 2.5 to get the option spans directly — do not re-scan the
issue text by hand:

```bash
ll-issues locate-options "${ISSUE_ID}" --json
```

The JSON result is `{id, count, pattern, heading, options: [{label, text, start_line, end_line}, ...]}`.
`pattern` names which precedence tier fired: `section_header` (`### Option A`),
`bold_label` (`**Option A**: ...`), `numbered` (`1. **Option A** ...`), `bullet`
(`- (a) ...` / `- **Option A**: ...`), or `provisional_e` (an un-preferenced decision
directive — see Phase 3b). `heading` is the section the options live under (`Proposed
Solution`, or one of its fallback sections — `Codebase Research Findings` /
`Implementation Status` — when Proposed Solution yields nothing; refined issues often
deposit options there instead). Treat each
`options[]` entry's `label`/`text` as the option title/description — the pattern
definitions themselves live only in `issue_parser.py` (ENH-2950); this phase never
re-derives them.

### Option Count Check

After extraction, also run `ll-issues check-unresolved-decisions "${ISSUE_ID}"` (BUG-3278) — the
decision-*group*-aware probe Phase 3b step 4 and Phase 7b gate on. It resolves whole decision
points, not option blocks (a decided 3-option group reports 0, not 2 losers), and covers the
`numbered`/`bullet` tiers plus a co-located Pattern E directive. When 2+ groups are unresolved,
source **`unresolved[0]`** (first group in document order) as the candidate below, not
`locate-options`' raw winner, so an already-decided group is skipped and repeated runs progress.

**Auto-mode bullet-list handling**: if `pattern == "bullet"` and `AUTO_MODE = true`, do NOT route them to Phase 4 scoring — automation must not re-litigate an informal list the author may have already settled. Treat `OPTIONS` as empty so flow proceeds to Phase 3b, where Pattern D resolves the case: a declarative recommendation marker naming one of the bullet options locks it in; absent a marker, a residual bullet-tier group under `--auto` stays a human-review exit by design (`decision_needed` stays `true`; Phase 9 names it). In interactive mode, bullet-pattern options ARE scored through Phases 4–7 normally.

- If `count == 0` and `check-unresolved-decisions` also finds zero groups: `AUTO_MODE = false` → print `No options found in Proposed Solution — nothing to decide.` and exit cleanly; `AUTO_MODE = true` → proceed to Phase 3b. **Exception (BUG-3278 part 4b)**: if `pattern == "decision_rules_numbered"` (BUG-3293 Program Design rulings — never a decision group), keep today's behavior instead — score via `locate-options` — or the flag clears with nothing scored.
- If `unresolved[0]` holds one option (the group-vocabulary re-expression of the old `count == 1` check) and no other group is unresolved: print `Only one option present — no decision required. Clearing decision_needed if set.` then proceed to Phase 7 (7b's own gate re-verifies before writing). This subsumes BUG-3287's `residual_directive is null` guard by construction — the group probe already treats a co-located `provisional_e` directive as a second unresolved group, so a stale read here can never clear a flag Phase 7b would refuse.
- If `unresolved[0]` holds 2+ options, or 2+ groups remain: proceed to Phase 4, scoring `unresolved[0]`'s options.

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

Scan ALL sections of the issue file (not just `## Proposed Solution`) for provisional decision
language. See [reference.md](reference.md) for each pattern's full Match/Example/Candidate shape.

- **Pattern A — Parenthetical `(e.g., ...)`**: candidate is the approach named inside the parenthetical.
- **Pattern B — Inline `TBD` marker**: candidate is the approach named in the surrounding sentence.
- **Pattern C — Definitive replacement language** (`must be replaced with`, `fundamental rethink`): candidate is the concrete replacement approach named.
- **Provisional Pattern D — Declarative recommendation** (`**Recommended**: (b)`, or a stated preference among 2+ alternatives named inline in an unresolved `## Open Questions` item — no pre-existing bullet is required for this shape, since the alternatives are materialized as structured options in Resolution Logic step 1): candidate is the referenced option(s); a resolvable referent is a **clear winner**. Same shape with **no** stated preference → Pattern E below.

### Provisional Pattern E — Un-preferenced decision directive (ENH-2936)

Already detected by the Phase 3 `locate-options` call: `pattern == "provisional_e"` means 2+
concrete alternatives named near an imperative decide-marker, with NO stated preference (Pattern
D above requires one). Bare "X or Y" prose with no imperative marker is explicitly NOT Pattern E.
Scan scope: `## Scope Boundaries`, `## Proposed Solution`, and unresolved `## Open Questions`.
Read `options[0].text` verbatim as the candidates — no separate scan needed. See
[reference.md](reference.md) for the full match shape and worked example.

For each provisional pattern match, read 3–5 lines of surrounding context to determine if one approach is clearly stated (not merely listed as a possibility).

### Resolution Logic

Classify each match as:
- **Pattern E match**: route directly to steps 1–2 below — no preference to classify.
- **Clear winner**: the provisional wrapper names exactly one concrete approach and surrounding context treats it as the intended design.
- **Ambiguous**: multiple alternatives listed, no single preference expressed.

**If a Pattern E match is found, or exactly one clear winner is found:**

1. **Materialize alternatives, if not already structured (ENH-2715)**: check whether the clear
   winner's named alternatives already exist as `### Option A`/`### Option B` (`section_header`) or
   `**Option A**`/`**Option B**` (`bold_label`) blocks under `## Proposed Solution`. They do NOT
   for two cases this step exists to handle: (a) the referent is only a `bullet`-pattern item (`- (a)
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
   If already structured, this step is a no-op: **clear winner** → step 3; **Pattern E match**
   → step 2 (re-scan immediately finds `OPTIONS >= 2`).
2. **Re-scan and route to full scoring (ENH-2715)**: after materializing, re-run the Phase 3
   extraction. If it now finds `OPTIONS >= 2` (the materialized blocks match `bold_label`): log
   `✓ Phase 3b: materialized informal decision as structured options — proceeding to Phase 4
   scoring`, then proceed directly to **Phase 4** (Gather Codebase Evidence) for full
   evidence-based scoring instead of the lock-in-only exit in step 3. Phase 4–7 independently
   adds the `> **Selected:**` callout and `### Decision Rationale` subsection once scoring
   completes, and Phase 7b sets `decision_needed: false` — skip steps 3–4 below for this path.
3. **Lock in without scoring** (alternatives were already structured, or materialization found
   no 2+-alternative shape to reformat): edit the issue text to make the approach declarative —
   for Patterns A–C remove the provisional qualifier (`e.g.,`/parenthetical wrapper, `TBD`,
   `"must be replaced with"`); for Pattern D add a `> **Selected:** (x) — per the stated
   recommendation` callout on the recommended bullet. **Patterns A–C additionally add a
   `> **Selected:** <approach> — per the locked-in provisional resolution` callout on the winning
   option block whenever structured option blocks exist under `## Proposed Solution`** (BUG-3278)
   — without this, step 4's gate below can never see that group as resolved and the auto path
   stalls forever on the single-decision common case. State the concrete approach as decided.
4. Run `ll-issues check-unresolved-decisions "${ISSUE_ID}"` (BUG-3278). **Exit 1 or 2+**: make NO
   frontmatter write; log `✗ Phase 3b: locked in [approach], but N unresolved decision point(s)
   remain — decision_needed remains true`; carry the surviving groups into Phase 9 exactly as
   Phase 7b does; skip to step 6. **Exit 0**: use the Edit tool (inline `---` block replacement —
   same pattern as Phase 7b) to set `decision_needed: false` in the issue frontmatter:
   ```
   READ the current --- frontmatter block (from opening --- to closing ---)
   FIND the decision_needed field:
     IF field exists: replace its value with false
     IF field absent: add decision_needed: false after the last existing field
   USE Edit tool to replace the entire --- block with the updated block
   ```
   **Idempotency**: if `decision_needed` is already `false`, skip the write and log `✓ decision_needed already false — no update needed`.
5. **Exit-0 branch only**: log `✓ Phase 3b: resolved provisional decision — [approach] locked in; decision_needed set to false`.
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

Use the Edit tool on the **selected group** (`unresolved[0]`, per Phase 3):
1. Insert a `> **Selected:** ...` marker for the winning option — placement is per-tier; see
   [reference.md](reference.md)'s Marker-Placement Matrix (`section_header`/`bold_label` → after
   the title line; `bullet`/`numbered` → after the winning bullet; `provisional_e` → **not** a
   callout at all — a bare `**RESOLVED**` prefix on the directive line itself, retirement being
   probe suppression, never `is_group_resolved`).
2. Append a `### Decision Rationale` subsection at the end of the Proposed Solution section (before
   the next `##` heading). Keep the heading literally `### Decision Rationale` — never suffix it
   (`_unapplied_decision`'s strict heading regex depends on the exact form). Disambiguate a second
   decided group sharing a section in the **body** instead: `**Decision point:** <group heading or
   first option label>` as the subsection's first line.

**Idempotency rule (per-group, BUG-3278)**: skip the annotation write only when **the selected
group** is already resolved per `is_group_resolved` — not "a `### Decision Rationale` section
exists anywhere in the issue", which would silently suppress the annotation for every group after
the first and stall convergence. Log `⚠ Decision already annotated for this group — skipping
annotation (idempotent)`.

### 7b: Update Frontmatter

Run `ll-issues check-unresolved-decisions "${ISSUE_ID}"` (BUG-3278) **after** 7a's annotation
write. **Exit 1 or 2+**: make NO frontmatter write; leave `decision_needed: true`; log `⚠
decision_needed remains true — N unresolved decision point(s): <heading:line-range>` naming each
surviving group; carry that line into Phase 9. **Exit 0**: set `decision_needed: false` in the
issue's YAML frontmatter using the Edit tool inline `---` block replacement pattern:

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

### 7c: Propagate Selection

**Entry gates** (skip and log if either fails): `DRY_RUN` is false, and Phase 7b took its exit-0 branch — otherwise log `⚠ Phase 7c: skipped — N decision point(s) still unresolved` and stop.

1. Run `ll-issues format-check "${ISSUE_ID}" --format json` and read `unapplied_decision_detail` (list of `{section, identifier}` pairs).
2. For each pair, locate the identifier's occurrence in `section` and classify against the four rewrite categories in [reference.md](reference.md) — recommendation markers, option-keyed conditionals, imperative steps, explicit propagation checklists.
3. Edit only matches (rewrite/demote/strike per category); flag everything else in Phase 9 without editing it.
4. Re-run `format-check`; a non-empty `unapplied_decision` residual is expected under the bounded-scope rule — carry it to Phase 9's flagged block, no retry.

**Idempotency rule (content-presence, ENH-3280)**: if the post-7a/7b `unapplied_decision` is already empty, skip and log `⚠ Phase 7c: no unpropagated references — skipping (idempotent)`.

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
options table, scoring table, decision, changes applied, dry-run preview, next steps,
and the residual-decisions line Phase 3b step 4 / Phase 7b populate on exit 1).

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:refine-issue --auto` — deposits implementation options, sets `decision_needed: true`
- **After**: `/ll:wire-issue` — traces callers and integration points for the now-selected implementation approach

See [reference.md](reference.md) for the "When to Use vs. Related Commands" table.

### FSM callers

FSM `shell` states cannot invoke slash commands directly (no LLM dispatch from a
subprocess), so `--validate-only` is a skill-level flag for direct/interactive use only.
FSM-driven loops (`rn-remediate`, `autodev`) instead call the deterministic companion CLI
`ll-issues check-decidable <ID>` — a pure-Python re-implementation of the same Patterns
1–4 counting logic (no LLM, no scoring, no write) — as a cheap pre-`decide` gate: exit 0
means "decide has something to act on", exit 1 routes the loop through
`/ll:refine-issue --auto` to deposit options before retrying (ENH-2443). Exit 2 means the
ID could not be resolved (BUG-3294) — a distinct "cannot evaluate" verdict, routed to
`on_error` rather than treated as an exit-1 "no options" no-op. This mirrors the
`ensure_formatted` → `ll-issues format-check` precedent (ENH-2426): the skill documents
the human-facing behavior, a companion CLI gives automation a real non-LLM evaluator.
