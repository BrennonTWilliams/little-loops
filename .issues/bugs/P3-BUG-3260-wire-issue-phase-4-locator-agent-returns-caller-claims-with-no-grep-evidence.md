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

Two layers, in priority order. The prompt amendment alone is **not** the fix — see the
BUG-2726 caution in Codebase Research Findings and the model note below.

**Layer 1 (primary, deterministic): extend confirm-before-map to Agent 1's own output.**
Phase 3.6's confirm-before-map today covers only `ll-code`-seeded candidates fed *into*
Agent 1's "Already-known callers"/"Key symbols" slots — it does not touch Agent 1's
free-form findings. That is an uncovered input, not a working rule. What actually caught
the four fabrications in the observed run was a human running greps by hand. Add a
caller-side confirmation step in Phase 5: every path Agent 1 returns gets one targeted
Grep for the symbol it was returned under, executed by the wire-issue skill on the main
model, before that path may enter `MISSING_WIRING` or the Integration Map. This does not
depend on the sub-agent's honesty and is checkable without an LLM.

**Layer 2 (defense-in-depth): amend the return contract.** Require evidence per returned
path — the matched symbol or pattern — state explicitly that a path may not be returned
on the basis of what the issue *proposes* to build, and add a separate "inferred,
unconfirmed" group so a genuine hunch has a home.

Two constraints on Layer 2 that must be honored or it makes output worse, not better:

- **Grep output is the evidence; `Read` stays forbidden.** `agents/codebase-locator.md`'s
  Important Guidelines and What NOT to Do sections say "Don't read file contents" and
  "Don't read files to understand implementation". An unqualified "cite the matched line"
  requirement directly contradicts that charter (the agent's `tools` list does include
  `Read`, so the contradiction is live, not theoretical). The amendment must say the
  citation comes from the Grep match, and must leave the no-Read rule intact.
- **Citation format is decided here, not at implement time.** Agent 1 returns the path
  plus **the symbol or pattern that matched**, not a line number. This satisfies
  ENH-1299's anchor-based-reference policy, avoids the literal `file:line` substring that
  `DOC_STRINGS_ABSENT` already forbids in `skills/wire-issue/SKILL.md`, and does not rot
  as files shift. See the unresolved-convention note in Codebase Research Findings.

**Model pin (resolved 2026-08-19).** `agents/codebase-locator.md` ran on `model: haiku` —
the only agent in `agents/` not on `sonnet`. That is a plausible proximate cause of the
four confabulations, and it made Layer 2 alone a poor bet: more prompt words instructing a
Haiku agent to self-verify is close to the approach BUG-2726 explicitly rejected. The pin
has been changed to `sonnet` ahead of this issue's implementation, with
`docs/reference/API.md`'s agent table and the `.qwen/`, `.kimi-code/`, `.codex/` mirrors
regenerated. Treat the model as a controlled variable when measuring this fix: the pin
change alone may move the rate, so a before/after comparison must not attribute its effect
to the prompt change.

Placement for Layer 2: check whether `agents/codebase-locator.md` (shared definition) or
`skills/wire-issue/SKILL.md`'s Phase 4 block is the better place, since `/ll:refine-issue`
and `/ll:manage-issue` share the definition. Layer 1 is wire-issue-only by construction.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` Phase 5 — **Layer 1, required.** Caller-side Grep
  confirmation of Agent 1's returned paths before they may enter `MISSING_WIRING` or the
  Integration Map
- `skills/wire-issue/SKILL.md` Phase 4 Agent 1 prompt — **or**
  `agents/codebase-locator.md`, for Layer 2, depending on where the fix belongs. Decide
  first: the shared agent definition is also used by `/ll:refine-issue`, where the same
  extrapolation is less harmful because hits are consumed as leads
- Host mirrors under `.qwen/`, `.gemini/`, `.kimi-code/`, `.codex/` regenerate via
  `ll-adapt --host <host> --apply` for whichever file changes

_Already landed (2026-08-19, ahead of implementation):_
- `agents/codebase-locator.md` frontmatter — `model: haiku` → `model: sonnet`
- `docs/reference/API.md` agent reference table — model column for `codebase-locator`
- `.qwen/`, `.kimi-code/`, `.codex/` locator mirrors regenerated (`.gemini`'s adapter
  emits no model field, so it is unchanged)

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
- `commands/iterate-plan.md:60` — a single prose bullet in an agent-selection list
  ("**codebase-locator** - To find relevant files and directories"). No prompt block, no
  return-contract handling, nothing to parse. Mentioned only so the inventory of
  shared-definition references is complete; no work is expected here.

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
  already anticipates. Add a **second** row for Layer 1 asserting the Phase 5 confirmation
  rule's phrase is present in `skills/wire-issue/SKILL.md` — same constraint applies, the
  phrase must not contain the literal substring `"file:line"`.
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
- **`agents/codebase-locator.md`** (153 lines, shared definition) has no evidence-citation
  clause anywhere: its Output Format section (`## Output Format`, lines 75-105) shows
  example groupings with one-line descriptions and no match-location field, and its
  `## Important Guidelines` / `## What NOT to Do` sections (107-127) forbid reading file
  contents, analyzing implementation, or critiquing organization — none forbid an
  unverified claim. Those same two sections are the source of the no-`Read` contradiction
  flagged in Proposed Solution: "Don't read file contents" and "Don't read files to
  understand implementation" sit directly against an unqualified cite-the-matched-line
  requirement, while the frontmatter `tools` list does grant `Read`.
- **Model pin was `haiku`** — `agents/codebase-locator.md` frontmatter, the only agent in
  `agents/` not pinned to `sonnet` (all 8 others: analyzer, pattern-finder,
  consistency-checker, loop-specialist, plugin-config-auditor, prompt-optimizer,
  web-search-researcher, workflow-pattern-analyzer). Changed to `sonnet` on 2026-08-19
  ahead of implementing this issue; `docs/reference/API.md`'s agent table and the
  `.qwen/`, `.kimi-code/`, `.codex/` mirrors were regenerated with it. This is the most
  likely proximate cause of the four fabrications and the reason Layer 2 alone was judged
  insufficient — see the BUG-2726 prior-art caution below, which rejected exactly the
  shape of "instruct the model to self-verify" that a prompt-only fix on a Haiku agent
  would have been.
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

1. **Layer 1** — add caller-side confirmation of Agent 1's returned paths to
   `skills/wire-issue/SKILL.md` Phase 5: one targeted Grep per returned path, for the
   symbol it was returned under, before the path may enter `MISSING_WIRING` or the
   Integration Map. Unconfirmed paths are dropped or demoted, never silently mapped.
   State plainly that this extends Phase 3.6's confirm-before-map to a previously
   uncovered input; it does not modify or weaken the existing rule.
2. Decide Layer 2 placement — wire-issue's Phase 4 prompt block vs. the shared
   `agents/codebase-locator.md` definition.
3. **Layer 2** — amend the return contract to require the matched symbol or pattern per
   returned path (from Grep output; the no-`Read` rule stays intact and must be restated
   so the two instructions do not read as contradictory), and to forbid returning a path
   on the basis of what the issue *proposes* to build.
4. Add a separate "inferred, unconfirmed" group so genuine hunches have a home and the
   tightening does not suppress real callers.
5. Verify — see Verification below. Note that the `sonnet` pin already landed, so any
   observed improvement is the pin *and* the prompt change together unless separated.

### Verification

Step 4 of the original plan ("re-run the ENH-3000 wiring pass and confirm the four
fabrications do not recur") is not a test: this issue's own Steps to Reproduce states the
output is non-deterministic and that one run is not a rate. A single clean re-run is
consistent with no change at all. Replace it with:

- **Gate (deterministic, blocking)** — the `DOC_STRINGS_PRESENT` row described under
  Tests. This asserts only that the instruction text exists, and is the sole automated
  gate available. Do not describe it as verifying agent behavior.
- **Gate (deterministic, blocking)** — Layer 1's confirmation step is ordinary skill logic
  and should be asserted the same way: a `DOC_STRINGS_PRESENT` row for the Phase 5
  confirmation rule.
- **Measurement (advisory, non-blocking)** — 3 wiring re-runs across 2 issues (ENH-3000
  plus one other with a comparable symbol count), counting per run: paths returned,
  paths surviving confirmation, paths in the "inferred, unconfirmed" bucket. The
  reportable number is the share of returned paths that fail confirmation, before vs.
  after. With n=6 runs this is directional, not significant — record it as an observation
  in the same spirit as the original one-run report, and do not gate the merge on it.
- Confirm in the same runs that the real hits from the original pass still appear, so the
  tightening has not traded fabrications for misses.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `skills/wire-issue/SKILL.md` Phase 5 ("Diff — Find Missing Wiring") — this is
  where Layer 1 lives. Two rules to add: (a) every path Agent 1 returns is confirmed by one
  targeted Grep for the symbol it was returned under before it may enter `MISSING_WIRING`;
  (b) whether the new "inferred, unconfirmed" bucket flows into `MISSING_WIRING` at all, or
  is held back/flagged separately from confirmed callers. Rule (a) is the deterministic
  gate and does not depend on rule (b) or on Layer 2 landing.
- Update `skills/wire-issue/SKILL.md` Phase 8a ("Integration Map Updates") — decide whether
  the evidence citation is inlined into the Dependent Files write template alongside the
  `[Agent 1 finding]` marker, and whether "inferred, unconfirmed" entries get a distinct
  marker so a reader of the issue file can tell confirmed callers from inferred ones.
- If Layer 2 lands in `agents/codebase-locator.md` (shared definition) rather than only
  wire-issue's Phase 4 block: `commands/refine-issue.md:256` and
  `skills/manage-issue/SKILL.md:111-119` inherit the new contract automatically — verify
  each still handles the new evidence field and the "inferred, unconfirmed" bucket
  correctly, since neither has wire-issue's Phase 5/8a diff-and-write logic.
  (`commands/iterate-plan.md:60` is a prose mention with no prompt block — nothing to
  verify there.) Note that neither inherits Layer 1, which is wire-issue Phase 5 logic;
  the shared-definition change is the only protection they get.
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

- **Priority**: P3 - manual greps caught the damage in the observed run, so no bad wiring
  reached the issue file; the cost is wasted confirmation greps and an undocumented
  dependence on whoever is running the pass noticing. Kept at P3, but note the containment
  is a human habit, not the automated rule the original write-up credited
- **Effort**: Small-Medium - Layer 2 is a prompt amendment (placement to decide first:
  wire-issue's Phase 4 block vs. the shared `agents/` definition that `/ll:refine-issue`
  also uses); Layer 1 adds a confirmation step to Phase 5, which is new skill logic rather
  than wording. Two `DOC_STRINGS_PRESENT` rows. The model pin is already done
- **Risk**: Low - a stricter return contract can only narrow what the agent reports, and
  Layer 1 only drops paths that fail a Grep. The cost of over-tightening is a missed real
  caller, which nothing else protects against, so the prompt must still permit inferred
  paths in a separate group and Layer 1 must demote rather than silently discard
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Agent 1's return contract and the evidence it must carry.
- **In scope**: extending confirm-before-map's *coverage* to Agent 1's free-form findings
  (Layer 1). An earlier revision of this issue put confirm-before-map wholly out of scope
  on the grounds that it "worked correctly"; that reading was wrong. Phase 3.6's rule was
  never applied to this input at all, so there is nothing here that worked — the greps
  that caught the fabrications were manual. Extending coverage is not weakening the rule.
- **Out of scope**: changing confirm-before-map's existing semantics for `ll-code`-seeded
  candidates, which do work correctly.
- **Out of scope**: `ll-code` accuracy — the graph results in this run were all correct.
- **Out of scope**: the missing `ll:` prefix on `subagent_type="codebase-locator"` in
  `skills/audit-claude-config/wave1-prompts.md:134` and `skills/audit-claude-config/
  SKILL.md:148`. Every other call site uses the `ll:`-prefixed form, so this may be a live
  agent-resolution bug, but it is unrelated to evidence citation and belongs in its own
  issue rather than being absorbed here.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-20T02:01:25 - `76b0acab-555b-45f1-82d8-192edcfbe30a.jsonl`
- `/ll:confidence-check` - 2026-08-20T00:54:45 - `91e7e492-9dd3-4528-be48-070fc252ab93.jsonl`
- `/ll:wire-issue` - 2026-08-20T00:45:46 - `4761f525-f803-4f98-9c12-b34258391e30.jsonl`
- `/ll:refine-issue` - 2026-08-20T00:39:34 - `319ac0b1-cd90-4d0c-9495-41a3d1945bec.jsonl`
- `/ll:format-issue` - 2026-08-20T00:34:43 - `e7d34bea-c87b-4a82-888d-cad944c750e2.jsonl`
