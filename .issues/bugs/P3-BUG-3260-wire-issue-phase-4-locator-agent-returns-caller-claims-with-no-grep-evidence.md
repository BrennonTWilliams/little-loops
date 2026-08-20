---
id: BUG-3260
type: BUG
title: wire-issue Phase 4 locator agent returns caller claims with no grep evidence
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
testable: true
program_design_not_applicable: true
relates_to:
- ENH-3258
- ENH-2578
captured_at: '2026-08-20T00:20:11Z'
confidence_score: 100
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3260: wire-issue Phase 4 locator agent returns caller claims with no grep evidence

## Summary

In one `/ll:wire-issue` run (ENH-3000, 2026-08-19), the Phase 4 Agent 1
(`ll:codebase-locator`) returned four caller/consumer claims that had **zero** grep hits.
The graph-discovery confirm-before-map rule caught all four, so no bad wiring reached the
issue file — but the agent is presenting fabricated call sites in the same format and with
the same confidence as real ones.

## Current Behavior

The traced symbol set for that run was: build_ref_index, classify_file_ref,
classify_issue_refs, RefIndex, RefStatus, IssuesConfig, qualified_ref_count,
triage_research_axes, check_format_gaps, plus the proposed config key
issues.untracked_by_design.

Four claims, each checked with a targeted grep that returned nothing:

1. **hooks/sweep_stale_refs.py**, reported as calling the classifier for reference
   classification. The file contains no occurrence of any traced symbol.
2. **issue_parser.py**, reported as reading the proposed config key. That key does not
   exist anywhere in the tree — ENH-3000, the issue being wired, *proposes* creating it.
   The claim inverts cause and effect, reporting a not-yet-existent key as already read.
3. **config/core.py**, reported as having a post-init hook on the issues config dataclass
   serving as the merge point. That dataclass defines no such hook.
4. **tests/test_issue_parser.py**, reported as a verdict-literal consumer. No hits for any
   traced symbol.

The pattern: the agent extrapolated from the issue's *proposed* end state and from
plausible module responsibilities, rather than reporting only what it found.

(Symbol and file names are deliberately unlinked above. Pairing them in the usual
`symbol` / `path` form would make this section's own catalogue of fabricated attributions
register as `mislocated_symbol_ref` findings against this issue.)

## Steps to Reproduce

1. Run `/ll:wire-issue ENH-3000 --auto --dry-run` from the repo root.
2. Read Phase 4 Agent 1's returned groups (Direct importers / Callers / Test files /
   Registration files / Config files).
3. For each returned path, grep it for the traced symbols listed above.

**Observed** (2026-08-19): four returned paths yield zero hits for any traced symbol.
**Expected**: every returned path carries at least one matching occurrence, or is marked
as inferred rather than found.

Not deterministic — this is LLM output, so a re-run may return a different set. The four
recorded fabrications are an existence proof, not a fixed reproduction.

## Expected Behavior

Agent 1 returns only paths it has evidence for, and marks anything inferred as
unconfirmed rather than listing it alongside verified hits.

## Motivation

Confirm-before-map is doing its job, so this is not currently producing bad output — but
it is load-bearing in a way the design may not intend. Three consequences:

1. **Cost**: every fabricated claim buys a wasted confirmation grep.
2. **Silent dependence**: if a caller ever skips confirmation for a hit that "looks
   obvious", these land in the Integration Map unchallenged.
3. **Erosion**: the same agent is used by `/ll:refine-issue`, where hits are consumed as
   research leads with a *weaker* confirmation discipline than wire-issue's.

One run is not a rate. This issue records a concrete observation, not a measurement.

## Proposed Solution

Amend the Agent 1 prompt in `skills/wire-issue/SKILL.md` Phase 4 to require evidence per
returned path — the matched line or symbol — and to state explicitly that a path may not
be returned on the basis of what the issue proposes to build. Consider a separate
"inferred, unconfirmed" group so the agent has somewhere to put a genuine hunch.

Before changing the prompt, check whether `agents/codebase-locator.md` or the shared
agent definition is the better place, since `/ll:refine-issue` shares it.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` Phase 4 Agent 1 prompt — **or**
  `agents/codebase-locator.md`, depending on where the fix belongs. Decide first: the
  shared agent definition is also used by `/ll:refine-issue`, where the same
  extrapolation is less harmful because hits are consumed as leads
- Host mirrors under `.qwen/`, `.gemini/`, `.kimi-code/` regenerate via `ll-adapt` for
  whichever file changes

### Dependent Files (Callers/Importers)
- `skills/wire-issue/graph-discovery-layer.md` — states the confirm-before-map rule that
  currently absorbs these false positives. Not to be weakened; noted because this issue's
  fix reduces (but must not be assumed to eliminate) reliance on it

_Wiring pass added by `/ll:wire-issue`:_
- `skills/manage-issue/SKILL.md:49,102-119` — Phase 1.5 Deep Research spawns
  `subagent_type="ll:codebase-locator"` alongside codebase-analyzer and
  codebase-pattern-finder, with the same bare-grouped-paths return contract as wire-issue's
  Phase 4 Agent 1. This corrects the Codebase Research Findings claim above that this call
  site's "actual prompt text could not be located" — it was found directly at
  `skills/manage-issue/SKILL.md:111-119`, not deferred to `templates.md`. If the fix lands
  in `agents/codebase-locator.md` (shared definition) this caller inherits it automatically;
  if the fix lands only in `skills/wire-issue/SKILL.md`'s Phase 4 prompt block, this caller
  does not and needs its own amendment.
- `commands/iterate-plan.md` — references the locator agent in its planning-research flow;
  another shared-definition caller to check if the fix is scoped narrowly to wire-issue.

### Similar Patterns
- Phase 4 Agents 2 and 3 use the same anchor-based-reference convention; check whether
  they exhibit the same behavior before assuming Agent 1 is unique

_Wiring pass added by `/ll:wire-issue`:_ resolved — confirmed Agent 1 is the outlier. Both
`skills/wire-issue/SKILL.md`'s Agent 2 and Agent 3 prompt blocks already require
anchor-based references, and their underlying agent definitions
(`agents/codebase-analyzer.md:126`, `agents/codebase-pattern-finder.md`) independently
mandate the same and demonstrate it in their Output Format examples. `agents/codebase-
locator.md`'s Output Format example (lines 75-105) has no per-item evidence field at all —
Agent 1 is uniquely under-specified, not representative of a shared gap.

### Tests
- `scripts/tests/` has no harness for agent-prompt compliance. Verification is a
  re-run of the ENH-3000 wiring pass, checking that returned paths carry evidence

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT`
  (list at line 27, consumed by `test_string_present_in_doc` at line 264) is the existing
  static-string-presence-check pattern to follow for a new test: add a
  `("agents/codebase-locator.md", "<required evidence-citation phrase>", "BUG-3260")` row
  (and a matching row for `skills/wire-issue/SKILL.md`'s Phase 4 Agent 1 block, if amended
  there too). This only asserts the instruction text demands a citation — no runtime
  harness exists to check an agent's actual output, which the issue's own Tests section
  already anticipates.
- Same file's `DOC_STRINGS_ABSENT` (line 275) already contains rows forbidding the literal
  string `"file:line"` in `agents/codebase-analyzer.md`, `agents/codebase-pattern-finder.md`,
  and `skills/wire-issue/SKILL.md` (ENH-1299, anchor-based-reference policy). Whatever
  citation phrasing this fix adds to `skills/wire-issue/SKILL.md` must not use the literal
  substring `"file:line"` or it fails an existing test. `agents/codebase-locator.md` is not
  in that forbidden-string list today, so the citation convention chosen for it is currently
  unconstrained by tests — but should still resolve (not deepen) the anchor-based vs.
  `file:line` split noted in the Codebase Research Findings above.

### Documentation
- None expected

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — Agent reference table row for `codebase-locator` currently
  reads "Find WHERE code lives — file paths grouped by purpose without reading contents."
  If the evidence-citation requirement pushes the agent toward reading matched lines as
  proof, "without reading contents" becomes misleading and this row needs a check.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Exact current prompt text** — `skills/wire-issue/SKILL.md:151-190` (Phase 4 Agent 1
  block). The "Return file paths grouped by" instruction (lines 174-179) has no per-path
  citation requirement of any kind; item 6 (line ~171, the `REPLACED_ARTIFACTS`/behavior-
  parity clause) requires "State what was searched" but only for that narrow capability-
  search-negative branch, not for the general caller/importer claims that produced this
  bug's fabrications.
- **`agents/codebase-locator.md`** (134 lines, shared definition) has no evidence-citation
  clause anywhere: its Output Format section (lines 75-105) shows example groupings with
  one-line descriptions and no match-location field, and its "Important Guidelines"/"What
  NOT to Do" sections (107-127) forbid reading file contents, analyzing implementation, or
  critiquing organization — none forbid an unverified claim.
- **Other invocation sites for `subagent_type="ll:codebase-locator"`**, relevant if the fix
  is applied per-call-site rather than in the shared agent definition:
  - `commands/refine-issue.md:256` — structurally the same caller-tracing task as wire-
    issue's; already has a `CONFIRMED SEEDS` block requiring `path:line` for pre-seeded
    graph hits, but the agent's own "Search for" findings (lines 271-283) carry no
    citation requirement, matching this issue's Motivation claim that refine-issue's
    discipline is weaker.
  - `skills/audit-claude-config/wave1-prompts.md:134` — config-file audit task, structurally
    unrelated to caller/dependency tracing.
  - `skills/manage-issue/SKILL.md:111` — prompt text deferred to `templates.md`; a search
    of that file found no matching `codebase-locator`/`subagent_type` block, so this call
    site's actual prompt text could not be located.
  - `commands/ready-issue.md:95-101` — narrow existence-check task ("Verify file paths
    exist... Return: EXISTS or NOT_FOUND"), already returns only a binary verdict per
    known path rather than new discovered claims, so it is not exposed to this bug's
    fabrication risk.
- **`skills/wire-issue/graph-discovery-layer.md` confirm-before-map scope** — the rule
  (lines 26-28, "a hit enters the Integration Map only after its `path:line` Grep
  confirms it") governs only `ll-code` graph-seeded candidates fed into Agent 1's
  "Already-known callers"/"Key symbols" slots (Phase 3.6, `SKILL.md:140-142`), not Agent
  1's own free-form exploratory findings. This means the issue's own account ("the
  graph-discovery confirm-before-map rule caught all four") describes a manual grep
  sanity-check performed by whoever ran the pass, not automated machinery that processes
  Agent 1's raw output — Phase 3.6's automation does not touch Agent 1's own claims at
  all.
- **Reusable evidence-citation vocabulary already in this codebase** — `path:line` is used
  identically in two places: `graph-discovery-layer.md`'s confirm-before-map description
  and `refine-issue.md`'s `CONFIRMED SEEDS` block ("already verified at path:line"). This
  is the closest existing phrasing to extend into Agent 1's return contract, rather than
  inventing new wording. It conflicts, however, with `agents/codebase-analyzer.md:126`'s
  guideline ("**Always include anchor-based references**... never raw line numbers"),
  which `skills/wire-issue/SKILL.md` itself follows for Agent 2 (`:212`) and Agent 3
  (`:244`). `agents/consistency-checker.md:370` uses the opposite convention ("Report
  exact locations (file:line)"). Agent 1's instructions currently specify neither
  convention — the citation-format decision (anchor-based vs. path:line) is unresolved
  codebase-wide, not just for this agent.
- **No existing "confirmed vs. inferred" two-bucket output convention** exists in any
  agent/skill/command prompt in this repo (searched `agents/`, `skills/`, `commands/` for
  `unconfirmed`, `speculative`, `hunch`, `low confidence`). The closest analog,
  `skills/format-issue/SKILL.md:296-315`, buckets user-facing *questions* by confidence
  during issue drafting — a different mechanism for a different purpose, not a template
  to reuse for evidence classification of agent-returned findings.
- **`behavior-parity.md` (ENH-3045) precedent, scope-limited** — already requires quoting
  "the specific line that makes it true" for positive claims about `REPLACED_ARTIFACTS`
  reuse/behavior, and requires stating what was searched for capability-search negatives
  (referenced from wire-issue's Agent 1 and Agent 3 blocks, `SKILL.md:171,242`). This
  existing clause is scoped to those two narrow cases only — it does not cover the general
  caller/importer/consumer claims (items 1-5 of Agent 1's "Find" list) that produced this
  bug's four fabrications, and is not referenced at all from `commands/refine-issue.md`.
- **Prior-art caution (BUG-2726, done)** — a similarly-shaped problem ("prompt lacks
  failure evidence, producing confabulation") was resolved by interpolating concrete
  deterministic values into the prompt (`${prev.state}`, `${captured.<name>.stderr}`,
  etc.) rather than by instructing the LLM to self-verify its own claims. That issue's
  Decision Rationale explicitly rejected an "instruct the LLM to open events.jsonl and
  read stderr" approach as reproducing the exact failure mode being fixed, citing "no
  non-LLM evaluator for whether the prompt picked the right event." No prior issue was
  found that resolved an agent-prompt evidence gap purely through added return-contract
  wording (as this issue's Proposed Solution does) — this is a documented risk to weigh
  when implementing, not a precedent for it.

## Implementation Steps

1. Decide placement — wire-issue's Phase 4 prompt block vs. the shared
   `agents/codebase-locator.md` definition.
2. Amend the return contract to require a matched line or symbol per returned path, and
   to forbid returning a path on the basis of what the issue *proposes* to build.
3. Add a separate "inferred, unconfirmed" group so genuine hunches have a home and the
   tightening does not suppress real callers.
4. Re-run the ENH-3000 wiring pass and confirm the four recorded fabrications do not
   recur, and that the real hits still do.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `skills/wire-issue/SKILL.md` Phase 5 ("Diff — Find Missing Wiring") — add a rule
  for whether the new "inferred, unconfirmed" bucket flows into `MISSING_WIRING` at all, or
  is held back/flagged separately from confirmed callers.
- Update `skills/wire-issue/SKILL.md` Phase 8a ("Integration Map Updates") — decide whether
  the evidence citation is inlined into the Dependent Files write template alongside the
  `[Agent 1 finding]` marker, and whether "inferred, unconfirmed" entries get a distinct
  marker so a reader of the issue file can tell confirmed callers from inferred ones.
- If the fix lands in `agents/codebase-locator.md` (shared definition) rather than only
  wire-issue's Phase 4 block: `commands/refine-issue.md:256`, `skills/manage-issue/
  SKILL.md:111-119`, and `commands/iterate-plan.md` all inherit the new contract
  automatically — verify each still parses/handles the new evidence field and bucket
  correctly, since none of them have wire-issue's Phase 5/8a diff-and-write logic.
- Add a `DOC_STRINGS_PRESENT` row to `scripts/tests/test_wiring_skills_and_commands.py`
  (line 27 / `test_string_present_in_doc` at line 264) asserting the chosen
  evidence-citation phrase appears in `agents/codebase-locator.md` (and in
  `skills/wire-issue/SKILL.md`'s Phase 4 Agent 1 block, if amended there too) — but avoid
  the literal substring `"file:line"`, which `DOC_STRINGS_ABSENT` (line 275, ENH-1299)
  already forbids in `skills/wire-issue/SKILL.md`.
- After landing the content change, run `ll-adapt --apply` (per host) to regenerate the
  `.qwen/`, `.gemini/`, `.kimi-code/` markdown mirrors and `.codex/agents/
  codebase-locator.toml` — `scripts/tests/test_adapt_agents_for_codex.py` only checks
  presence/structure of the `.codex` TOML, not content parity, so a stale mirror will not
  fail tests on its own.
- Check `docs/reference/API.md`'s agent reference table row for `codebase-locator`
  ("without reading contents") for staleness against the new evidence requirement.

## Program Design

N/A — `program_design_not_applicable: true`. This is an agent-prompt (markdown) change:
no types, no signatures, no runtime call path. The only design decision is placement,
covered in Implementation Steps step 1.

## Impact

- **Priority**: P3 - confirm-before-map contains the damage, so no bad wiring is reaching
  issue files today; the cost is wasted confirmation greps and an undocumented dependence
  on that rule
- **Effort**: Small - a prompt amendment, though placement needs deciding first
  (wire-issue's Phase 4 block vs. the shared `agents/` definition that `/ll:refine-issue`
  also uses)
- **Risk**: Low - a stricter return contract can only narrow what the agent reports. The
  cost of over-tightening is a missed real caller, which confirm-before-map does *not*
  protect against, so the prompt should still permit inferred paths in a separate group
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Agent 1's return contract and the evidence it must carry.
- **Out of scope**: the confirm-before-map rule itself, which worked correctly.
- **Out of scope**: `ll-code` accuracy — the graph results in this run were all correct.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-20T00:54:45 - `91e7e492-9dd3-4528-be48-070fc252ab93.jsonl`
- `/ll:wire-issue` - 2026-08-20T00:45:46 - `4761f525-f803-4f98-9c12-b34258391e30.jsonl`
- `/ll:refine-issue` - 2026-08-20T00:39:34 - `319ac0b1-cd90-4d0c-9495-41a3d1945bec.jsonl`
- `/ll:format-issue` - 2026-08-20T00:34:43 - `e7d34bea-c87b-4a82-888d-cad944c750e2.jsonl`
