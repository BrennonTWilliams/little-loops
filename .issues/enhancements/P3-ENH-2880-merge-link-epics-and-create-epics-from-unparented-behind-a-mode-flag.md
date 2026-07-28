---
id: ENH-2880
title: Merge link-epics and create-epics-from-unparented behind a mode flag
type: ENH
priority: P3
status: done
captured_at: '2026-07-28T02:07:33Z'
completed_at: '2026-07-28T04:45:53Z'
discovered_date: 2026-07-28
labels:
- skills
relates_to:
- ENH-2877
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2880: Merge link-epics and create-epics-from-unparented behind a mode flag

Follow-up from the ENH-2877 skill-merge audit — Tier 1 candidate C1.

## Summary

`skills/link-epics/` and `skills/create-epics-from-unparented/` are self-declared
inverse operations over an identical input population, using identical scoring
machinery, duplicated as prose across two files. Merge them into one skill with a
`mode` argument (`assign` | `synthesize`).

## Current Behavior

Two skills, both of which:

- start from the same population — open BUG/FEAT/ENH issues with no `parent:`
  frontmatter field;
- score with **Jaccard similarity on title + summary text**;
- accept `--auto` and `--min-score`;
- write `parent: EPIC-NNN` into the child and update the EPIC's `## Children`
  section.

`create-epics-from-unparented`'s own description states it is "*the inverse of
`/ll:link-epics`*". The difference is solely the target: assign orphans to
**existing** EPICs, versus synthesize **new** EPICs from the orphan pool.

**The duplication has already produced drift.** `--min-score` defaults diverge:
`link-epics` uses 0.7 with `--auto` and 0.0 without; `create-epics-from-unparented`
uses a flat 0.3. Nothing forces those to be reconciled or even compared, because
they live in separate prose bodies.

## Expected Behavior

One skill covering both directions, with the orphan-discovery query, the Jaccard
scoring description, and the write-back procedure stated **once**.

## Motivation

This is a maintenance-cost argument, and deliberately not a menu-footprint one.

The ENH-2877 audit established that `ll-verify-skill-budget` is at **516 / 2000
tokens — 74% headroom**, so there is no live token pressure motivating any
consolidation. ENH-2877's own guidance is that a candidate whose only argument is
"fewer entries in the menu" should be recommended *against*. This candidate does
not rely on that argument: the shared logic is duplicated prose that has
**already** drifted on a user-visible default, which is a realized defect rather
than a hypothetical one.

## Proposed Solution

One skill (retaining the name `link-epics`) with a `mode` argument:

- `mode: assign` — score orphans against existing EPICs and link accepted
  proposals. Current `link-epics` behavior.
- `mode: synthesize` — cluster orphans and propose new EPIC files. Current
  `create-epics-from-unparented` behavior.

Shared: orphan discovery, Jaccard scoring, `--auto`, `--min-score`, write-back.
Mode-specific: `--min-cluster` (synthesize only), and mode-conditional
`--min-score` defaults preserving today's tuned values rather than picking one.

**Precedent for the shape**: `skills/manage-issue/SKILL.md` dispatches on an
`action` argument across five behaviors; `skills/configure/SKILL.md` dispatches
internally on an `area` argument across ~20 areas. Both are the model here.

### What would be lost

Two clean single-purpose files become one file carrying a mode conditional.
Mode-conditional defaults are a genuine readability cost — the reason the two
defaults drifted is that they were never side by side, but putting them side by
side means a reader must now track which mode they are in.

## Scope Boundaries

**In scope**

- Merging `link-epics` and `create-epics-from-unparented` into one skill under
  the retained name `link-epics`, with a `mode` argument.
- Reconciling the `--min-score` default drift between the two, per mode.
- Updating the skill catalog in `.claude/CLAUDE.md`, `commands/help.md`, and docs.

**Out of scope**

- **Any other merge candidate.** ENH-2877's Tier 2 and Tier 3 findings
  (`debug-loop-run`/`audit-loop-run`, `confidence-check`/`go-no-go`,
  `product-analyzer`/`scan-product`, `review-loop`/`simplify-loop`, the
  workflow-analysis pipeline, and the `refine-issue`/`wire-issue`/`reconcile-issue`
  cluster) were each examined and **recommended against**. Do not opportunistically
  fold any of them in.
- **Any router or change to name-based dispatch.** ENH-2877 explicitly rejects
  that shape; individually addressable skills are load-bearing for FSM states,
  MR-12 validation, and `ll-action`/`ll-queue`.
- Changing the Jaccard scoring algorithm itself, or the EPIC file format.
- A deprecation shim for `/ll:create-epics-from-unparented` — the name is
  removed outright (0 automation references).

**Backwards compatibility**: `/ll:create-epics-from-unparented` stops resolving.
No FSM loop, `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` entry, or `ll-*` bridge
references it, so the break is confined to direct user invocation and must be
noted in the changelog.

## Integration Map

### Dispatch-site check (ENH-2877 AC #2)

**Clean — no name-based dispatch site is affected.**

| Site | `link-epics` | `create-epics-from-unparented` |
|------|--------------|-------------------------------|
| Loop corpus `/ll:<name>` refs (`scripts/little_loops/loops/`) | 0 | 0 |
| `_VERIFIER_SKILLS` (`cli/action.py:30`) | no | no |
| `_REVIEWER_SKILLS` (`cli/action.py:49`) | no | no |
| `ll-*` thin bridge in `skills/` | none | none |
| `skills/configure/areas.md` allowlist | n/a — that preset covers `ll-` CLI entry points, not skill names | n/a |

Remaining references are docs and tests only. Retaining the name `link-epics`
keeps even those stable for one of the two.

### Files

- `skills/link-epics/SKILL.md` (259 lines) — merge target.
- `skills/create-epics-from-unparented/SKILL.md` (341 lines) — removed.
- `scripts/little_loops/text_utils.py` — `extract_words()` (131),
  `calculate_word_overlap()` (148); the Jaccard primitive both describe.
- Docs listing the command catalog: `.claude/CLAUDE.md` § Commands & Skills,
  `commands/help.md`, `docs/` references to either name.
- `scripts/tests/` — any test asserting the skill inventory or either name.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — current line counts and neither skill actually calls `text_utils.py`.**
As of this refinement pass, `skills/link-epics/SKILL.md` is **280 lines** and
`skills/create-epics-from-unparented/SKILL.md` is **361 lines** (combined ~641,
not the 600 stated above — reconfirm against `wc -l` at implementation time
since both have likely drifted further). More importantly: **neither skill
file actually invokes `text_utils.py`'s `extract_words()`/`calculate_word_overlap()`**
— both are pure prose `SKILL.md` skills with no backing Python module, and each
independently *re-describes* the word-extraction/Jaccard algorithm in prose.
That prose is byte-for-byte identical between the two files (Word Extraction
section: `link-epics/SKILL.md:103-111` vs
`create-epics-from-unparented/SKILL.md:77-85`; Jaccard formula block:
`link-epics/SKILL.md:113-119` vs `create-epics-from-unparented/SKILL.md:87-95`)
— but it is **not the same stop-word list** as `_COMMON_WORDS` in
`text_utils.py:98-128`. The prose list has `add`, `use`, `new`, `via`, `per`,
`set`, `run`, `all`, `also`, `any`, `into`, `more`, `one`, `its`, `when`,
`their`, `they`, `which` that `_COMMON_WORDS` lacks, and `_COMMON_WORDS` has
`should`, `would`, `could`, `may`, `might`, `must`, `file`, `code`, `issue`,
`had`, `were` that the prose lacks. This is a **second, independent drift**
beyond the `--min-score` default divergence already documented above — the
merge should either (a) reconcile the shared prose block against
`text_utils.py`'s actual `_COMMON_WORDS`, noting this is a pre-existing
inconsistency predating the merge, or (b) explicitly scope that reconciliation
out and note both algorithms remain prose-described, not code-invoked.

**Additional shared-vs-mode-specific prose boundaries** (beyond the
`--min-score` drift already noted):
- Orphan discovery: both skills independently issue three
  `ll-issues list --status open --type {BUG,FEAT,ENH} --json` calls + an
  identical `orphans = [i for i in data if not i.get("parent")]` filter, but
  `create-epics-from-unparented` additionally passes `--include-summary` and
  consumes `orphan["summary"]` directly, while `link-epics` does per-orphan
  `Read` + regex extraction (`## Summary\n(.+?)(?=\n##|\Z)`) instead. Worth
  standardizing on `--include-summary` in the merged skill to drop the
  per-orphan `Read` calls from `assign` mode.
- `parent:` write-back block (near-identical, including the
  `⚠ CHILD_ID already has parent: <value>, skipping` warning) —
  `link-epics/SKILL.md:185-202` vs
  `create-epics-from-unparented/SKILL.md:276-293`.
- Mode-specific logic with **no counterpart** in the other skill: `link-epics`
  has EPIC discovery (lines 43-61), best-match-per-orphan selection (121-125),
  confidence tiers (127-131), and a post-write consistency check (221-233,
  explicitly a stand-in for `ll-issues epic-consistency` pending FEAT-2332).
  `create-epics-from-unparented` has greedy pairwise cluster-merge (97-116,
  O(n²), structurally different from link-epics's fixed-EPIC-set lookup),
  title/summary synthesis (120-150), singleton surfacing via a second
  `AskUserQuestion` (190-213), and per-cluster `ll-issues next-id` allocation
  with duplicate-ID retry (220-228). None of this mode-specific logic overlaps
  and all of it must be preserved in the merged skill's per-mode branches.

**Dispatch precedent detail** (refines the Proposed Solution's precedent
claim): `manage-issue/SKILL.md`'s `action` dispatch is not a `case` statement
— it's a single linear phase pipeline where each phase carries its own
action-conditional skip/branch clause inline (e.g. `SKILL.md:191`
`**Skip this phase if**: ... action is verify or plan ...`). `configure/SKILL.md`
layers two dispatch axes instead: a mapping **table** for `area` values
(`### 2. Area Mapping`) plus separate `## Mode: --flag` top-level sections for
flag-triggered behavior. Given `mode: assign|synthesize` branches into two
almost entirely disjoint procedures (not a handful of conditional lines), the
`configure`-style `## Mode: --flag` section shape is the closer structural fit
for Step 3's merged-file layout, not `manage-issue`'s inline-conditional shape.

**Additional catalog/doc references beyond `.claude/CLAUDE.md`/`commands/help.md`**
(Scope Boundaries says "and docs" — these are the concrete hits):
- `docs/reference/COMMANDS.md` — entries for both skills.
- `docs/reference/CLI.md:173` — example `ll-action invoke link-epics --args --auto`.
- `CONTRIBUTING.md:193-201` — lists both skills in the skill inventory tree.
- `skills/link-epics/agents/openai.yaml` and
  `skills/create-epics-from-unparented/agents/openai.yaml` — Codex host
  adapters; the latter must be deleted alongside the skill directory.

**Test files needing updates** (more specific than "any test asserting the
skill inventory"):
- `scripts/tests/test_link_epics_skill.py` (75 lines) — structural tests
  including `test_relates_to_not_used_for_child_wiring` (asserts
  `"6b. Update EPIC relates_to:"` is NOT in the file, per ENH-2330); this file
  becomes the natural home for merged-skill structural tests since no
  equivalent `test_create_epics_from_unparented_skill.py` exists.
- `scripts/tests/test_wiring_cli_registry.py:34-35` — asserts
  `commands/help.md` and `.claude/CLAUDE.md` contain the literal string
  `"create-epics-from-unparented"` tagged `FEAT-2338`; remove/update these
  rows.
- `scripts/tests/test_wiring_skills_and_commands.py:303-304` — `DOC_FILES_MUST_EXIST`
  parametrized rows asserting `skills/create-epics-from-unparented/SKILL.md`
  and its `agents/openai.yaml` physically exist; remove these rows when the
  directory is deleted.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:141` — project-tree diagram lists
  `├── create-epics-from-unparented/ # User-invoked` as a skill directory
  entry; must be removed when the directory is deleted. [Agent 1/2 finding]
- `skills/review-epic/SKILL.md:102`, `skills/capture-issue/SKILL.md:495`,
  `skills/issue-workflow/SKILL.md:77,164` — each references `/ll:link-epics`
  by its retained name in user-facing suggestion text or the skill catalog
  table. Not broken by the merge (the name survives), but written assuming
  today's assign-only behavior — worth a one-line mention of `mode:
  synthesize` if these are touched, otherwise no change required. [Agent 1/2
  finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:177` — states "**42 skills**"; deleting
  `skills/create-epics-from-unparented/` drops the real count to 41. This is
  not just stale prose — `scripts/tests/test_doc_counts.py`'s
  `TestVerifyDocumentation` (backing `ll-verify-docs`) computes the actual
  skill count live via `count_files("skills", "*/SKILL.md", ...)` and fails
  on mismatch, so this line must be updated or the doc-count gate breaks.
  [Agent 2/3 finding]
- `docs/reference/API.md` — documents `extract_words()`/`calculate_word_overlap()`
  with examples; unaffected by the merge itself (neither skill actually calls
  these, per the existing refine-issue finding) but confirm no example
  implies either skill invokes them. [Agent 1 finding, low priority]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py:1001,1055,1058,1173-1174` — checked and
  confirmed **not** a wiring gap: these `unparented` hits are
  `ll-issues list --group-by-epic`'s "Unparented" display section, unrelated
  to the `create-epics-from-unparented` skill name. No change needed.
  [Agent 3 finding, false-lead ruled out]
- No dedicated `test_create_epics_from_unparented_skill.py` exists to port
  assertions from — confirmed via glob, only `SKILL.md` +
  `agents/openai.yaml` exist under that skill directory. [Agent 3 finding]
- No existing mode/action-dispatch test pattern to imitate: neither
  `manage-issue` (`action` arg) nor `configure` (`area` arg) has a dedicated
  dispatch-structure test file — `test_link_epics_skill.py`'s flat
  `SKILL_FILE.read_text()` substring-assertion style (its own existing
  pattern) is the closest template for new `mode: assign`/`mode: synthesize`
  assertions. [Agent 3 finding]

## Implementation Steps

1. Diff the two `SKILL.md` bodies to isolate genuinely shared prose from
   mode-specific prose.
2. Reconcile the `--min-score` default drift explicitly — decide per mode and
   document why, rather than collapsing to a single value.
3. Write the merged `skills/link-epics/SKILL.md` with `mode` dispatch.
4. **Check the 500-line cap**: 259 + 341 = 600 lines concatenated. The merged
   file must come in under 500 (`ll-verify-skills`), or extract to a companion
   file per the ENH-494 pattern. Do not assume the merge fits.
5. Delete `skills/create-epics-from-unparented/`.
6. Update the catalog in `.claude/CLAUDE.md`, `commands/help.md`, and docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6a. Remove the `create-epics-from-unparented/` entry from the project-tree
    diagram in `docs/ARCHITECTURE.md:141`.
6b. Decrement "42 skills" to "41 skills" in `README.md:177` — enforced live by
    `test_doc_counts.py`'s `TestVerifyDocumentation`.
6c. Remove the two `create-epics-from-unparented` rows from
    `scripts/tests/test_wiring_cli_registry.py:34-35`.
6d. Remove the two `DOC_FILES_MUST_EXIST` rows for
    `skills/create-epics-from-unparented/SKILL.md` and its `agents/openai.yaml`
    from `scripts/tests/test_wiring_skills_and_commands.py:303-304`.
6e. Extend `scripts/tests/test_link_epics_skill.py` with assertions for the
    new `mode: assign`/`mode: synthesize` dispatch (no existing dispatch-test
    pattern to copy — follow this file's own flat substring-assertion style).

7. Run `python -m pytest scripts/tests/`, `ll-verify-skills`,
   `ll-verify-skill-budget`, `ll-verify-docs`.

## Impact

- **Users**: `/ll:create-epics-from-unparented` stops resolving. This is a
  breaking change to a user-facing name with no deprecation shim proposed —
  acceptable given 0 automation references, but it should be called out in the
  changelog.
- **Maintenance**: one orphan-discovery + scoring description instead of two.
- **Risk**: Low. No automation path touches either name.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Commands & Skills catalog listing both names; the "Prefer Skills over Agents" and skill-authoring conventions |
| `docs/ARCHITECTURE.md` | Skill/command surface and the FEAT-1896 bridge pattern that scopes what counts as a real skill |

## Session Log
- `/ll:manage-issue` - 2026-07-28T04:45:31 - `00041c0b-3526-41ec-b743-a686380c429a.jsonl`
- `/ll:ready-issue` - 2026-07-28T04:34:18 - `150dbe3d-d6d3-4b6c-9a7a-a4d006246aa3.jsonl`
- `/ll:wire-issue` - 2026-07-28T04:31:59 - `da3bc647-9b2e-4290-9698-71bdc0cfba1c.jsonl`
- `/ll:refine-issue` - 2026-07-28T04:26:17 - `ac55af27-083f-4b11-ba74-495feeeefc0d.jsonl`
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

open
