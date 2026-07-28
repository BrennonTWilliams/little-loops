---
id: ENH-2877
title: Audit which ll skills are close enough in scope to merge into fewer skills
type: ENH
priority: P3
status: done
discovered_date: 2026-07-27
decision_needed: false
decision: "Option A \u2014 conversational report, follow-up issues as the durable\
  \ artifact. Chosen 2026-07-28; see ## Outcome."
relates_to:
- BUG-2879
- ENH-2880
- ENH-2881
labels:
- skills
completed_at: '2026-07-28T02:23:15Z'
---

# ENH-2877: Audit which ll skills are close enough in scope to merge into fewer skills

Origin: ll-product #ENH-061

No parent EPIC — deliberately standalone. See the rejection note below for why this is not part of a larger consolidation effort.

## Summary

A deliberately scoped-down survivor of a **rejected** proposal. Read the rejection first — it is the more important half of this issue.

## What was rejected, and why

The rejected shape: consolidate the entire command surface into **one** user-invocable skill with sub-commands behind a router table, keeping maintenance tooling out of the `/` menu entirely. The motivation is real — `/` menu pollution gets worse as users install more plugins.

**That shape does not transfer to little-loops, and must not be adopted.** Individually addressable skills are load-bearing here:

- FSM states invoke `/ll:<name>` directly. A router would break slash-command resolution for every loop state that calls a skill by name.
- The MR-12 validation rule, pruning profiles, and `ll-action` / `ll-queue` dispatch all resolve skills by name.
- The menu's token footprint is already governed by an **enforced** mechanism (`ll-verify-skill-budget`), so the cost the source is solving for is already bounded by different means.
- The lazy-loading benefit does not apply either: each `SKILL.md` already loads only on invocation, so little-loops already gets what the source's per-command reference files buy.

This rejection is recorded here so the same proposal is not re-derived from the same source later.

## What survives

A much smaller question with **no architectural change**: some existing skills may be close enough in scope that one skill with a mode flag would serve both. That is worth knowing independently of any router.

## Proposed work

A **read-only audit**, producing a list of merge candidates with the argument for each:

1. Survey existing skills for pairs or clusters with substantially overlapping scope, inputs, or output shape.
2. For each candidate cluster, state what a merged skill would look like, what the mode flag would be, and what would be lost.
3. Explicitly flag any candidate whose merge would change a name that an FSM state, pruning profile, or `ll-action` / `ll-queue` dispatch path currently resolves — those are disqualified or require a migration plan, not a rename.
4. Recommend, do not execute. Merges are separate follow-up issues.

## Current Behavior

The `/ll:*` surface exposes 69 distinct invocable names (40 non-bridge skills +
29 commands). Whether any of them overlap enough in scope to be one skill with a
mode flag has never been assessed, so the question resurfaces whenever an
external source proposes consolidation — as it did via ll-product #ENH-061.

## Expected Behavior

A recorded, evidence-backed answer: which pairs are genuinely mergeable, which
merely look mergeable, and what each merge would break — so the question is
settled by reference rather than re-derived.

## Scope Boundaries

**In scope**: a read-only survey of the skill/command surface; per-candidate
argument, cost, and dispatch-site check; recommendations and follow-up issues.

**Out of scope**: executing any merge; any router or sub-command dispatch table
(explicitly rejected — see "What was rejected, and why"); any change to
name-based dispatch; renaming or removing any skill; `ll-*` bridge/twin pairs
(FEAT-1896 working as designed, excluded by construction).

## Impact

Bounded and non-breaking — this issue changed no code. Its output is three
follow-ups (BUG-2879, ENH-2880, ENH-2881), a recorded rejection of the router
shape so it is not re-derived from the same source, and a standing constraint
that no future merge may be justified on menu footprint while budget headroom
holds.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. This issue changes no
code; the files below are the ones the **audit must read and cross-check
against**, not files to modify._

#### The set being audited (verified on disk, 2026-07-27)

- `skills/` — **71** directories, each with a `SKILL.md`. There is **no static
  manifest**: `.claude-plugin/plugin.json` declares only `"skills": ["./skills"]`.
  Every consumer independently globs `skills_dir.glob("*/SKILL.md")`, so the
  audited set is exactly "every subdirectory of `skills/` containing a `SKILL.md`".
- `commands/` — **29** `*.md` files.
- **Critical inventory correction**: 31 of the 71 skill directories are `ll-*`
  prefixed **thin bridges**, not independent skills. Example:
  `skills/ll-refine-issue/SKILL.md` is 22 lines with
  `disable-model-invocation: true`, fronting `commands/refine-issue.md` (717
  lines). 53 of the 71 `SKILL.md` files carry `disable-model-invocation: true`.
  The genuinely model-invocable surface is **18 skills** (those counted by
  `ll-verify-skill-budget`), not 71. **The audit must not treat an `ll-*` bridge
  and its `commands/*.md` twin as a merge candidate pair** — that is the
  FEAT-1896 skill-bridge pattern working as designed, not scope overlap.

#### Name-based dispatch sites each candidate must be checked against (AC #2)

- `scripts/little_loops/skill_expander.py` — `_resolve_content_path(plugin_root,
  name)`: the actual name→file resolver (tries `skills/{name}/SKILL.md`, then
  `commands/{name}.md`). The single ground-truth resolution site.
- `scripts/little_loops/runner_spec.py` — `_run_skill()` (~line 82): builds the
  literal prompt `f"/ll:{spec.target}"`. Every dispatcher (`ll-action`,
  `ll-harness`, FSM executor) funnels through `run_action()` here (ENH-2668).
- `scripts/little_loops/fsm/validation.py` — `_SKILL_INVOKE_RE =
  re.compile(r"/ll:([a-zA-Z0-9_-]+)")` and `_validate_pruning_profile()` (line
  ~2284) implementing MR-12's three checks.
- `scripts/little_loops/fsm/executor.py` — `_extract_skill_from_action()`
  (~line 3070), same regex, for baseline-arm dispatch.
- `scripts/little_loops/cli/queue.py` — `_classify_action()` (line ~29):
  loop → skill/command → raw-CLI classification, existence-based.
- `scripts/little_loops/cli/action.py` — **hand-maintained frozensets keyed by
  literal skill name**: `_VERIFIER_SKILLS` (9: `ready-issue`,
  `confidence-check`, `go-no-go`, `tradeoff-review-issues`, `refine-issue`,
  `format-issue`, `verify-issues`, `prioritize-issues`, `align-issues`) at line
  30, and `_REVIEWER_SKILLS` (7: `review-epic`, `review-loop`,
  `audit-architecture`, `audit-claude-config`, `audit-docs`, `audit-loop-run`,
  `review-sprint`) at line 49. Merging any listed name silently breaks
  `verdict_events` / `review_events` persistence — these are not derived.
- `skills/configure/areas.md` — "All ll- commands" allowlist preset, gated by
  `ll-verify-cli-allowlist` (BUG-2764).
- **Not a risk**: pruning-profile resolution is *not* keyed on skill name.
  `_effective_pruning_profile(fsm, state)` (validation.py line ~2277) reads
  `state.pruning_profile` → `fsm.pruning_profile` only. The issue body lists
  "pruning profiles" among name-resolving mechanisms; that is imprecise —
  MR-12's *validation* reads skill names, profile *resolution* does not.

#### Loop-invocation census (disqualification weight per name)

Verified via `grep -rhoE "/ll:[a-zA-Z0-9_-]+" scripts/little_loops/loops/`.
Occurrence counts across the loop corpus — higher count = more sites to migrate,
so higher disqualification weight under AC #2:

`refine-issue` 27 · `explore-api` 17 · `decide-issue` 17 · `confidence-check` 15
· `spike` 14 · `commit` 11 · `wire-issue` 10 · `issue-size-review` 9 ·
`capture-issue` 8 · `normalize-issues` 5 · `manage-issue` 4 ·
`tradeoff-review-issues` 3 · `scope-epic` 3 · `reconcile-issue` 3 ·
`ready-issue` 3 · `format-issue` 3 · `debug-loop-run` 3 · `check-code` 3 ·
`audit-loop-run` 3 · `create-loop` 2 · `audit-issue-conflicts` 2 ·
(1 each) `scan-codebase`, `prioritize-issues`, `map-dependencies`,
`iterate-plan`, `go-no-go`, `find-dead-code`, `create-sprint`,
`cleanup-worktrees`.

#### Tooling the audit should reuse rather than reimplement

- `scripts/little_loops/tool_catalog.py` — `_skill_entries()` /
  `_command_entries()`: already walks `skills/*/SKILL.md` + `commands/*.md`
  frontmatter into uniform `ToolDefinition(name, description, input_schema)`.
- `scripts/little_loops/frontmatter.py` — `parse_skill_frontmatter()` (line 175),
  the canonical frontmatter parser.
- `scripts/little_loops/cli/verify_triggers.py` — `_extract_keywords()` (line
  166) yields a per-skill keyword signature; `_detect_collisions()` (line 330)
  is **the repo's existing skill-to-skill overlap detector** (a phrasing
  matching >1 skill description). Closest prior art for scope-overlap scoring.
- `scripts/little_loops/text_utils.py` — `extract_words()` (131) /
  `calculate_word_overlap()` (148): stopword-filtered Jaccard similarity, the
  primitive behind issue dedup.
- `scripts/little_loops/issue_discovery/matching.py` — `MatchClassification` /
  `FindingMatch`: worked example of turning a similarity score into tiered
  recommendations (analogous to "merge candidate" / "related, keep separate" /
  "no overlap").

#### Mode-flag precedent (what a merged skill would look like)

- `skills/manage-issue/SKILL.md` — `arguments:` declares `issue_type`
  (bug|feature|enhancement|epic), `action` (fix|implement|improve|verify|plan),
  and `flags`. One skill, many behavioral modes.
- `skills/configure/SKILL.md` — `area` argument enumerating ~20 config areas
  dispatched internally (`AREA="${area:-}"`), plus `--list`/`--show`/`--reset`.

These two are the shape any merge recommendation should be written against.

#### Budget context — weakens the stated motivation

`ll-verify-skill-budget` measures **description frontmatter only**
(`len(description) // 4`, `doc_counts.py:check_skill_budget()` line 319), summed
across model-invocable skills, default threshold 2000 (`_DEFAULT_BUDGET_TOKENS`,
`doc_counts.py:15`). **Current actual: 516 / 2000 — 74% headroom.** No single
skill is near the per-skill warn threshold (max is `product-analyzer` at 44).

Implication the audit must confront honestly: there is **no live token pressure**
motivating consolidation. The argument for any merge candidate must therefore
rest on maintenance/conceptual cost (two files to keep in sync, ambiguous trigger
routing per `_detect_collisions`), not on menu footprint. A candidate whose only
argument is "fewer entries in the menu" should be recommended *against*.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — the issue specifies **what** to produce but not
**where** it lands. The two precedents in this repo diverge, and the choice
changes what "written list" in AC #1 means._

**Option A**: Conversational report + follow-up issues (the
`commands/audit-architecture.md` / `commands/find-dead-code.md` pattern). The
audit emits a `# Skill Merge Candidate Audit` markdown report inline with
confidence tiers, ends with a `REVIEW_JSON:` tag line for the review-event
pipeline (ENH-2512), and the only durable artifacts are optional `.issues/*.md`
follow-ups created after approval. Cost: the audit body is not re-readable later
without re-running it. Benefit: matches every existing `audit-*` command, adds no
new output convention, and AC #4's "recommend, do not execute" falls out for free.

> **Selected:** 2026-07-28. Executed as a conversational report. Because only two
> of three Tier 1 candidates became follow-up issues, the stated cost was
> mitigated by writing the full candidate ledger — including all Tier 2/3
> rejections and the budget finding — into `## Outcome` below, rather than
> relying on the follow-ups alone to carry it.

**Option B**: Persisted artifact under `.ll/skill-audit/` (the
`commands/analyze-workflows.md` pattern, which writes
`.ll/workflow-analysis/step*.yaml` + `summary-{timestamp}.md`). The audit writes
a durable, diffable candidate list that a later re-run can compare against. Cost:
introduces a new output directory convention and a staleness question (the skill
surface moves). Benefit: re-runnable as a drift check.

**Recommended**: Option A — this is a one-shot recommend-only audit whose output
becomes follow-up issues, which are themselves the durable artifact. Option B's
re-runnability only pays off for a recurring check, which AC #3 ("No skill is
merged... as part of this issue") explicitly says this is not. Note `thoughts/`
is not a candidate for either option.

> **Selected:** Not chosen. Option A was taken instead; see the marker above.

**Decision: Option A confirmed.** The audit emits a conversational
`# Skill Merge Candidate Audit` markdown report ending with a `REVIEW_JSON:` tag
line; the only durable artifacts are optional `.issues/*.md` follow-ups created
after approval. No new persisted-artifact directory convention is introduced.

## Acceptance criteria

- Output is a written list of merge candidates, each with a stated argument and a stated cost.
- Every candidate is checked against name-based dispatch sites, and any that would break one is marked as such.
- No skill is merged, renamed, or removed as part of this issue.
- No router, no change to name-based dispatch.


## Outcome

Audit completed 2026-07-28. **Decision: Option A** — conversational report with
follow-up issues as the durable artifact. This section records the findings that
did *not* become follow-up issues, since Option A's stated cost is that the audit
body is otherwise unrecoverable without re-running it.

### Set audited

69 distinct invocable names: 40 non-bridge skills + 29 commands. Of the 71
`skills/` directories, 31 are `ll-*` thin bridges (FEAT-1896) and were excluded by
construction, per this issue's inventory correction.

### Two findings that constrain all future work here

1. **The stated motivation is empirically dead.** `ll-verify-skill-budget`
   measured **516 / 2000 tokens — 74% headroom**; the largest single skill is
   `capture-issue` at 20. **No merge may be justified on menu footprint.** Any
   future proposal resting on entry count should be closed, not implemented.
2. **The repo's own overlap detector produced no usable signal.**
   `ll-verify-triggers` `_detect_collisions()` reported "No cross-skill collisions
   detected," but every skill scored 0% precision *and* 0% recall — because **zero
   skills declare `trigger_fixtures` at all**. The clean-collision result is an
   artifact of empty input, not evidence. Filed as **BUG-2879**.

### Candidate ledger

**Tier 1 — recommended, follow-ups filed:**

| Candidate | Argument | Status |
|---|---|---|
| `link-epics` + `create-epics-from-unparented` | Self-declared inverses; identical orphan population, Jaccard scoring, write-back. Drift already realized (`--min-score` 0.7/0.0 vs 0.3). 0 dispatch refs. | **ENH-2880** |
| `verify-issue-loop` + `adversarial-verify-loop` | Identical input, allowlist, and 7-step spine; 6 of 8 steps duplicated. 0 dispatch refs. | **ENH-2881** |
| `update-docs` → `audit-docs` | `update-docs` must disambiguate itself from `audit-docs` in its own body — the boundary isn't self-evident from either name. 0 loop refs. **Constraint: `audit-docs` ∈ `_REVIEWER_SKILLS` (`cli/action.py:49`, hand-maintained) — a merge under any new name silently breaks `review_events` persistence.** | **Not filed.** Recommended but deliberately not captured; open a follow-up if wanted. |

**Tier 2 — real overlap, recommended against.** Recorded so these are not
re-derived:

- **`debug-loop-run` + `audit-loop-run`** — highest surface similarity in the
  corpus (identical args, allowlists, resolution step), but they answer different
  questions: *why did it fail* vs *did it achieve its goal despite reporting
  success*. The second is the designated defense against phantom convergence and
  verdict laundering; putting it behind a flag makes it opt-in. Note
  `audit-loop-run` ∈ `_REVIEWER_SKILLS`.
- **`confidence-check` + `go-no-go`** — disqualified on dispatch: `confidence-check`
  has **14 loop refs** and is load-bearing in `autodev.yaml`'s guard chain; both
  ∈ `_VERIFIER_SKILLS`. Mechanisms also differ in kind (dual-score rubric vs
  two-agent adversarial debate with judge).
- **`product-analyzer` + `scan-product`** — a working analyzer/writer split, with
  the routing rule already documented in `product-analyzer`'s description.
  Merging would force the analysis path to acquire `Write`, giving up a
  deliberately narrow allowlist.
- **`review-loop` + `simplify-loop`** — "provably behavior-preserving refactor"
  (resting on `resolve_flow()` round-tripping) and "judgement-based quality
  critique" are different contracts. Mechanically cheap to merge; that isn't an
  argument.
- **`loop-suggester` + `workflow-automation-proposer` + `analyze-workflows`** —
  pipeline stages, not alternatives. `workflow-automation-proposer` is explicitly
  step 3 consuming step 1–2's `.ll/workflow-analysis/*.yaml`. Merging would remove
  the ability to re-run proposals against edited intermediates.

**Tier 3 — rejected on inspection (name similarity only):** `format-issue` +
`normalize-issues` (body sections vs filenames — disjoint); `verify-issues` +
`align-issues` (code claims vs doc references; only argument was footprint);
`prioritize-issues` + `tradeoff-review-issues` + `issue-size-review` (three
distinct scoring axes); **`refine-issue` / `wire-issue` / `reconcile-issue`**
(most tempting cluster — hard-disqualified at 27 + 10 + 3 loop refs, and
`autodev.yaml`'s `check_reconcile_needed` / `dispatch_pre_deferral_remedy` route
between them *by name* as distinct remedies).

### Net

69 invocable names → 66 if all three Tier 1 candidates land. That is the honest
size of the opportunity, earned by maintenance-duplication cost, not menu size.

### Acceptance criteria verification

- ✅ Written list of merge candidates, each with a stated argument and cost.
- ✅ Every candidate checked against name-based dispatch sites; loop-reference
  counts and `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` membership recorded per
  candidate, with breaking cases marked (C3, C5, C6-cluster).
- ✅ No skill merged, renamed, or removed.
- ✅ No router; no change to name-based dispatch.

## Session Log
- `/ll:refine-issue` - 2026-07-28T00:58:44 - `d22ef0a2-9fb8-4039-b636-56bc90ede55c.jsonl`
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

done
