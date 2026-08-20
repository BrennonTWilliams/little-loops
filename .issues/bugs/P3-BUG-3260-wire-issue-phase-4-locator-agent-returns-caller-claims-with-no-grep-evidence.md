---
id: BUG-3260
type: BUG
title: wire-issue Phase 4 locator agent returns caller claims with no grep evidence
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
testable: true
program_design_not_applicable: true
relates_to:
- ENH-3258
- ENH-2578
captured_at: '2026-08-20T00:20:11Z'
completed_at: '2026-08-20T03:29:14Z'
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

1. **Silent dependence**: if a caller ever skips confirmation for a hit that "looks
   obvious", these land in the Integration Map unchallenged.
2. **Erosion**: the same agent is used by `/ll:refine-issue`, where hits are consumed as
   research leads with a *weaker* confirmation discipline than wire-issue's.

One run is not a rate. This issue records a concrete observation, not a measurement.

**Not a cost argument.** An earlier revision listed "every fabricated claim buys a wasted
confirmation grep" as a third consequence. That is inverted by the fix chosen below: Layer
B greps *every* returned path, real ones included, so total grep count goes **up**, not
down. The trade this issue makes is more greps in exchange for a deterministic gate — not
fewer greps.

## Proposed Solution

Two layers. **Layer A is a prerequisite for Layer B, not defense-in-depth** — see the
correction below. The prompt amendment alone is also not sufficient — see the BUG-2726
caution in Codebase Research Findings and the model note below.

**Layer A (prerequisite): amend the return contract to carry per-path evidence.** Require,
per returned path, **the symbol or pattern that matched** — state explicitly that a path
may not be returned on the basis of what the issue *proposes* to build, and add a separate
"inferred, unconfirmed" group so a genuine hunch has a home. This is a wording change and
is not self-enforcing on its own; its purpose is to produce the field Layer B greps.

**Layer B (the deterministic gate): extend confirm-before-map to Agent 1's own output.**
Phase 3.6's confirm-before-map today covers only `ll-code`-seeded candidates fed *into*
Agent 1's "Already-known callers"/"Key symbols" slots — it does not touch Agent 1's
free-form findings. That is an uncovered input, not a working rule. What actually caught
the four fabrications in the observed run was a human running greps by hand. Add a
caller-side confirmation step in Phase 5: **every path Agent 1 returns is grepped for the
match string Agent 1 itself cited under Layer A**, executed by the wire-issue skill on the
main model, before that path may enter `MISSING_WIRING` or the Integration Map. A
fabricated citation fails its own grep, so this does not depend on the sub-agent's honesty
and is checkable without an LLM.

**Why the any-symbol formulation was rejected (correction, 2026-08-19).** An earlier
revision made Layer B primary and Layer-A-independent by having it grep each returned path
for **any** symbol in Phase 3's `key_symbols` set, asserting that this "would have caught
all four recorded fabrications, which had zero hits for any traced symbol." That assertion
is false. Re-running it against the four recorded paths:

| Claimed path | hits for *any* traced symbol | any-symbol gate |
|---|---|---|
| `hooks/sweep_stale_refs.py` | 0 | caught |
| `config/core.py` | 3 | survives |
| `issue_parser.py` | 19 | survives |
| `tests/test_issue_parser.py` | 61 | survives |

It catches **1 of 4**. The greps that originally caught the fabrications were *per-claim
targeted* ones ("does this file actually read that config key?"), not any-symbol ones — the
Current Behavior section is accurate; the independence argument built on top of it was not.
The any-symbol rule is near-toothless in exactly the common case: a topically-adjacent file
claimed for the wrong reason. Hence the reordering — the per-path match string is the only
thing that makes the gate bite, so Layer A must land first.

**Second reason the any-symbol rule was wrong: it false-drops registration and config
files.** Agent 1's contract includes registration/manifest and config-file groups
(`MISSING_WIRING.registrations_to_add`, `schema_coupling`). Those files legitimately
contain zero Python symbols — they carry an entry-point name, a dotted module path, a
config key, or a basename. An any-symbol gate empties those categories mechanically,
trading fabrications for exactly the misses the Risk section warns against. Grepping the
agent's own cited match string avoids this: for a registration file the agent cites
whatever actually matched there.

Two constraints on Layer A that must be honored or it makes output worse, not better:

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
four confabulations, and it made Layer A alone a poor bet: more prompt words instructing a
Haiku agent to self-verify is close to the approach BUG-2726 explicitly rejected. The pin
has been changed to `sonnet` ahead of this issue's implementation, with
`docs/reference/API.md`'s agent table and the `.qwen/`, `.kimi-code/`, `.codex/` mirrors
regenerated. Treat the model as a controlled variable when measuring this fix: the pin
change alone may move the rate, so a before/after comparison must not attribute its effect
to the prompt change.

**Layer A placement (decided): `agents/codebase-locator.md`, the shared definition.** This
was previously left open as an implement-time decision; the research below already settles
it. Layer B is wire-issue-only by construction, so `commands/refine-issue.md:256` and
`skills/manage-issue/SKILL.md:111-119` — both consuming the same bare-path contract, and
refine-issue with explicitly weaker confirmation discipline — get **no** protection at all
unless Layer A lands in the shared definition. The other two call sites are not exposed:
`commands/ready-issue.md:95-101` returns binary EXISTS/NOT_FOUND verdicts per known path,
and `skills/audit-claude-config/wave1-prompts.md:134` audits config files rather than
tracing callers. Amending only wire-issue's Phase 4 block would fix the one caller that
already has a deterministic gate and leave the two that don't.

**Sizing constraint (blocking).** `skills/wire-issue/SKILL.md` is at exactly **500 lines**,
the hard cap enforced by `scripts/tests/test_enh494_skill_companions.py:21`
(`SKILL_LINE_LIMIT = 500`). Any line added to Phase 5 or Phase 8a fails that test. Layer B
must therefore land as a **new flat companion file** under `skills/wire-issue/` —
`evidence-confirmation.md` — referenced from Phase 5 by a one-line pointer, following the
existing companion pattern (`graph-discovery-layer.md`, `behavior-parity.md`,
`caller-suitability-gate.md`, `prose-dependency-gate.md`, `static-coupling-layer.md`). Net
line change to `SKILL.md` must be ≤ 0. This also determines where the Layer B
`DOC_STRINGS_PRESENT` needle lives — in the companion, not in `SKILL.md`.

**Where the offsetting line comes from (concrete).** The pointer is +1, so one line must
go. `SKILL.md` uses a bare `---` phase separator inconsistently already — 16 of them, with
none at all between the Phase 3.7 block and Phase 5 — so deleting the separator (and its
adjacent blank line) that sits between Phase 5 and Phase 6 frees 2 lines with no content
loss and no new inconsistency. Any equivalent formatting reclaim is fine; the point is that
"net ≤ 0" needs a named source, not a hope that something will turn up at implement time.

## Integration Map

### Files to Modify
- `skills/wire-issue/evidence-confirmation.md` (new file) — **new companion file, Layer B.** Holds the
  caller-side Grep confirmation rule for Agent 1's returned paths. New file rather than
  inline Phase 5 text because `SKILL.md` is at the 500-line cap
- `skills/wire-issue/SKILL.md` Phase 5 — **Layer B, required.** One-line pointer to the
  companion above. Net line change to this file must be ≤ 0 (see sizing constraint)
- `scripts/tests/test_enh494_skill_companions.py` — add `SKILLS_DIR / "wire-issue" /
  "evidence-confirmation.md"` to `EXPECTED_COMPANIONS` (line 24). Its
  `test_skill_links_to_companion` then gates that the Phase 5 pointer actually exists — a
  free enforcement of the pointer at no extra test-authoring cost
- `agents/codebase-locator.md` — **Layer A**, shared definition. Placement decided (see
  Proposed Solution); wire-issue's Phase 4 Agent 1 prompt block is *not* amended, so
  `/ll:refine-issue` and `/ll:manage-issue` inherit the stricter contract
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
- `scripts/tests/` has no harness for agent-prompt compliance. Behavioral verification is a
  wiring run on an unwired issue, checking that returned paths carry evidence — advisory
  only, see Verification

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT`
  (list at line 27, consumed by `test_string_present_in_doc` at line 264) is the existing
  static-string-presence-check pattern to follow for a new test: add a
  `("agents/codebase-locator.md", "<required evidence-citation phrase>", "BUG-3260")` row
  for Layer A. This only asserts the instruction text demands a citation — no runtime
  harness exists to check an agent's actual output, which the issue's own Tests section
  already anticipates. Add a **second** row for Layer B asserting the confirmation rule's
  phrase is present in `skills/wire-issue/evidence-confirmation.md` — the companion file,
  **not** `SKILL.md`, since the 500-line cap forces the rule text out of `SKILL.md`. Same
  constraint applies: the phrase must not contain the literal substring `"file:line"`.
- `scripts/tests/test_enh494_skill_companions.py` — `SKILL_LINE_LIMIT = 500` at line 21.
  `skills/wire-issue/SKILL.md` is at **exactly 500 lines** today, so this test is the
  binding constraint on Layer B's shape. It also enforces the flat-companion convention
  (companions live directly under `skills/wire-issue/`, not in a subdirectory), which
  `evidence-confirmation.md` must follow. Add the new companion to `EXPECTED_COMPANIONS`
  (line 24) so `test_companion_exists` / `test_companion_non_empty` /
  `test_skill_links_to_companion` all cover it.
- Back in `scripts/tests/test_wiring_skills_and_commands.py` (**not** the ENH-494 file —
  an earlier revision said "same file" here and was wrong), `DOC_STRINGS_ABSENT` at line
  275 already contains rows forbidding the literal
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
  likely proximate cause of the four fabrications and the reason Layer A alone was judged
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

1. **Layer A (first — Layer B depends on it)** — amend `agents/codebase-locator.md`
   (placement decided; see Proposed Solution) to require the matched symbol or pattern per
   returned path (from Grep output; the no-`Read` rule stays intact and must be restated so
   the two instructions do not read as contradictory), and to forbid returning a path on
   the basis of what the issue *proposes* to build.
2. Add a separate "inferred, unconfirmed" group so genuine hunches have a home and the
   tightening does not suppress real callers.
3. **Layer B** — add caller-side confirmation of Agent 1's returned paths, written to a
   **new companion file** `skills/wire-issue/evidence-confirmation.md` and referenced from
   `SKILL.md` Phase 5 by a one-line pointer (`SKILL.md` is at the 500-line cap — see the
   sizing constraint in Proposed Solution; net line change to `SKILL.md` must be ≤ 0). The
   rule: one targeted Grep per returned path **for the match string that path was returned
   with** (Layer A's evidence field), before the path may enter `MISSING_WIRING` or the
   Integration Map. Unconfirmed paths are dropped or demoted, never silently mapped. State
   plainly that this extends Phase 3.6's confirm-before-map to a previously uncovered
   input; it does not modify or weaken the existing rule.
4. **Degradation rule for a path that arrives with no evidence field** (Layer A ignored, or
   an older host mirror in play): treat it as *inferred, unconfirmed* and keep it out of
   `MISSING_WIRING` — do **not** fall back to grepping the `key_symbols` set, which catches
   1 of 4 known fabrications and false-drops registration/config files (see Proposed
   Solution). Failing closed on a missing field is both simpler and stricter than the
   any-symbol fallback an earlier revision specified.
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
- **Gate (deterministic, blocking)** — Layer B's confirmation step is ordinary skill logic
  and should be asserted the same way: a `DOC_STRINGS_PRESENT` row for the confirmation
  rule in `skills/wire-issue/evidence-confirmation.md`, plus the `EXPECTED_COMPANIONS` row
  that gates the Phase 5 pointer.
- **Measurement (advisory, non-blocking)** — 3 wiring runs across 2 issues, counting per
  run: paths returned, paths surviving confirmation, paths in the "inferred, unconfirmed"
  bucket. The reportable number is the share of returned paths that fail confirmation. With
  n=6 runs this is directional, not significant — record it as an observation in the same
  spirit as the original one-run report, and do not gate the merge on it.
- **The before/after comparison is not available; do not claim one.** An earlier revision
  proposed re-running the ENH-3000 wiring pass as the "before" baseline. ENH-3000 is still
  `open`, but it now carries the 8-file Integration Map produced by the very pass that
  surfaced this bug, and Agent 1's prompt instructs "Exclude files already in the
  'already known' lists" (`skills/wire-issue/SKILL.md:181`). A re-run therefore sees a
  materially different input than the original and is not comparable. Select **two issues
  that have not yet been wired**, with symbol counts comparable to ENH-3000's, and report
  the "after" side only — the four recorded fabrications remain the historical baseline,
  with the caveat that they came from a different issue and a different model pin.
- Confirm in the same runs that paths the pass returns and confirms are genuine callers, so
  the tightening has not traded fabrications for misses.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Create `skills/wire-issue/evidence-confirmation.md` and point Phase 5 ("Diff — Find
  Missing Wiring") at it with a one-line reference — this is where Layer B lives. It cannot
  be inlined: `SKILL.md` is at the 500-line cap, and the offsetting line to delete is named
  in Proposed Solution. Three rules to write: (a) every path Agent 1 returns is confirmed by
  one targeted Grep **for the match string Agent 1 cited for that path** before it may enter
  `MISSING_WIRING`; (b) a path arriving with no evidence field is treated as inferred and
  held out — no any-symbol fallback; (c) whether the "inferred, unconfirmed" bucket flows
  into `MISSING_WIRING` at all, or is held back/flagged separately from confirmed callers.
  Rule (a) is the deterministic gate and **requires Layer A to land first** — the per-path
  match string is the thing being grepped. Two earlier revisions got this wrong in opposite
  directions: one specified a per-path symbol Agent 1 does not return, the other "fixed"
  that with an any-symbol grep that catches only 1 of the 4 recorded fabrications and
  mechanically empties the registration/config categories. See the correction table in
  Proposed Solution.
- Update `skills/wire-issue/SKILL.md` Phase 8a ("Integration Map Updates") — decide whether
  the evidence citation is inlined into the Dependent Files write template alongside the
  `[Agent 1 finding]` marker, and whether "inferred, unconfirmed" entries get a distinct
  marker so a reader of the issue file can tell confirmed callers from inferred ones. Any
  text added here counts against the same 500-line cap; move it to the companion if it
  does not fit within the budget freed by Phase 5's pointer.
- Layer A lands in `agents/codebase-locator.md` (decided), so `commands/refine-issue.md:256`
  and `skills/manage-issue/SKILL.md:111-119` inherit the new contract automatically — verify
  each still handles the new evidence field and the "inferred, unconfirmed" bucket
  correctly, since neither has wire-issue's Phase 5/8a diff-and-write logic.
  (`commands/iterate-plan.md:60` is a prose mention with no prompt block — nothing to
  verify there.) Neither inherits Layer B, which is wire-issue-only logic; the
  shared-definition change is the only protection they get, and it is the reason placement
  was resolved in favor of the shared definition.
- Add a `DOC_STRINGS_PRESENT` row to `scripts/tests/test_wiring_skills_and_commands.py`
  (line 27 / `test_string_present_in_doc` at line 264) asserting the chosen
  evidence-citation phrase appears in `agents/codebase-locator.md`, plus a second row for
  Layer B's confirmation phrase in `skills/wire-issue/evidence-confirmation.md` — but avoid
  the literal substring `"file:line"`, which `DOC_STRINGS_ABSENT` (line 275, ENH-1299)
  already forbids in `skills/wire-issue/SKILL.md`.
- Keep `skills/wire-issue/SKILL.md` at or below 500 lines
  (`scripts/tests/test_enh494_skill_companions.py:21`); it sits at exactly 500 today, so
  this is a blocking gate on the whole change, not a style note.
- After landing the content change, run `ll-adapt --apply` (per host) to regenerate the
  `.qwen/`, `.gemini/`, `.kimi-code/` markdown mirrors and `.codex/agents/
  codebase-locator.toml` — `scripts/tests/test_adapt_agents_for_codex.py` only checks
  presence/structure of the `.codex` TOML, not content parity, so a stale mirror will not
  fail tests on its own.
- Check `docs/reference/API.md`'s agent reference table row for `codebase-locator`
  ("without reading contents") for staleness against the new evidence requirement.

## Program Design

N/A — `program_design_not_applicable: true`. This is an agent-prompt (markdown) change:
no types, no signatures, no runtime call path. Two design decisions are resolved in
Proposed Solution: Layer A's placement (`agents/codebase-locator.md`, the shared
definition) and the layer ordering (Layer A is a prerequisite for Layer B, because the
per-path match string is what Layer B greps).

## Impact

- **Priority**: P3 - manual greps caught the damage in the observed run, so no bad wiring
  reached the issue file; the exposure is an undocumented dependence on whoever is running
  the pass noticing. Kept at P3, but note the containment is a human habit, not the
  automated rule the original write-up credited
- **Effort**: Small-Medium - Layer A is a prompt amendment to `agents/codebase-locator.md`
  (placement decided). Layer B is new skill logic rather than wording, and must land as a
  new companion file because `skills/wire-issue/SKILL.md` is at the 500-line cap — so the
  change also carries a small extraction/pointer edit to Phase 5. Two
  `DOC_STRINGS_PRESENT` rows plus one `EXPECTED_COMPANIONS` row. The model pin is already
  done
- **Risk**: Low-Medium - a stricter return contract can only narrow what the agent reports,
  and Layer B only drops paths that fail a Grep. The cost of over-tightening is a missed
  real caller, which nothing else protects against, so the prompt must still permit inferred
  paths in a separate group and Layer B must demote rather than silently discard. The
  specific over-tightening to watch is registration/manifest and config files, which carry
  entry-point names, dotted module paths, or config keys rather than traced symbols — the
  measurement runs below must confirm those categories are still populated, since the
  rejected any-symbol formulation would have emptied them wholesale
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Agent 1's return contract and the evidence it must carry.
- **In scope**: extending confirm-before-map's *coverage* to Agent 1's free-form findings
  (Layer B). An earlier revision of this issue put confirm-before-map wholly out of scope
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
- `/ll:manage-issue` - 2026-08-20T03:28:45 - `b53bcbd5-a74b-4728-8b8d-3d8652663576.jsonl`
- `/ll:ready-issue` - 2026-08-20T03:18:07 - `4793e2e4-b77c-4e97-b189-22309d7a9634.jsonl`
- `/ll:confidence-check` - 2026-08-20T03:14:21 - `fba7d942-77f7-49f6-95c3-8eb3b5d9922d.jsonl`
- `/ll:confidence-check` - 2026-08-20T02:01:25 - `76b0acab-555b-45f1-82d8-192edcfbe30a.jsonl`
- `/ll:confidence-check` - 2026-08-20T00:54:45 - `91e7e492-9dd3-4528-be48-070fc252ab93.jsonl`
- `/ll:wire-issue` - 2026-08-20T00:45:46 - `4761f525-f803-4f98-9c12-b34258391e30.jsonl`
- `/ll:refine-issue` - 2026-08-20T00:39:34 - `319ac0b1-cd90-4d0c-9495-41a3d1945bec.jsonl`
- `/ll:format-issue` - 2026-08-20T00:34:43 - `e7d34bea-c87b-4a82-888d-cad944c750e2.jsonl`
