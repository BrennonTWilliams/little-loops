---
id: BUG-3330
type: BUG
title: codebase-locator agent claims verified zero-hit grep for symbols that exist
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T19:31:41Z'
program_design_not_applicable: true
confidence_score: 98
outcome_confidence: 91
score_complexity: 24
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 23
---

# BUG-3330: codebase-locator agent claims verified zero-hit grep for symbols that exist

## Summary

The `codebase-locator` subagent (`agents/codebase-locator.md`) can report a
"confirmed" zero-hit search for a symbol that is actually present in the
target file, contradicting its own Output Format contract, which requires
every returned path to cite the actual Grep hit that produced it.

## Current Behavior

During a `/ll:wire-issue` run, the `ll:codebase-locator` subagent was asked to
trace `attach_evaluators` and `validate_evaluators` as FSM state names in
`scripts/little_loops/loops/workflow-generator.yaml`. Its final summary
stated (verbatim, from the session transcript, not a repo file):

> "attach_evaluators" and "validate_evaluators" as literal symbol names did
> not match anywhere in the codebase — these appear to be state names
> referenced only within the issue text itself... I confirmed this via
> direct grep with zero hits outside `.issues/`.

A direct `grep -n "attach_evaluators\|validate_evaluators" scripts/little_loops/loops/workflow-generator.yaml`
run immediately after by the coordinating session found both strings at
multiple lines (142, 145, 200, 202, 231) as real FSM state names and routing
edges in that exact file.

## Expected Behavior

Per the agent's own Output Format section: "Every returned path must cite
the symbol or pattern your Grep matched there — this is the evidence a
caller checks the path against" and "A path with no Grep hit belongs in the
separate 'Inferred, Unconfirmed' group below, never mixed into an
evidence-bearing group." A negative claim ("X does not exist anywhere")
should carry the same evidentiary discipline: the agent should not assert a
verified zero-hit result unless the search it actually ran (not a
remembered/assumed one) produced zero hits for the *exact* target file, and
should be more conservative about negative claims spanning a multi-symbol,
multi-file search in one final summary.

## Root Cause

**Hypothesis (not yet confirmed against the run transcript): a filtered search
generalized into an unfiltered negative.**

`agents/codebase-locator.md:16` grants `["Read", "Glob", "Grep", "WebFetch",
"WebSearch"]` — no `Bash`. Every search the agent runs therefore goes through
the Grep tool, which accepts `glob`, `type`, and `path` filters. A search
narrowed by any of those (`type: py`, `glob: "*.py"`, `path:
scripts/little_loops/`) returns zero hits for a symbol that exists only in a
YAML file — which is exactly the shape of this reproduction: `attach_evaluators`
and `validate_evaluators` exist as **FSM state names in a `.yaml` file**, not as
Python identifiers. A Python-scoped grep for them is *correctly* empty; the
defect is reporting that empty filtered result as "confirmed... zero hits
outside `.issues/`", a claim about the whole tree.

This reframes the fix. The actionable rule is not "be more conservative about
negatives" (unenforceable) but a specific, checkable one:

> A negative claim must name the filters the search ran under, and must be
> re-run with **no** `glob`/`type`/`path` filter before it can be asserted.

The generic attention-drift concern (multiple symbols traced in one prompt,
only a subset actually searched) is a real secondary contributor and is still
worth guarding, but the filter-scope mechanism is the one that explains this
specific reproduction and the one the fix should lead with.

## Motivation

This was caught only because `/ll:wire-issue`'s Phase 5 has an explicit
evidence-confirmation step ("confirm Agent 1's returned paths against the
evidence it cited... never trust a negative alone") that exists specifically
to catch this class of failure. A caller without that discipline — including
a human reading the agent's summary at face value — would ship a wrong
conclusion: in this case, that two FSM states referenced throughout a bug's
Codebase Research Findings section didn't actually exist, when they did.

## Proposed Solution

Give negative claims the same evidence discipline positive ones already have
(`agents/codebase-locator.md:77-82`), via **a structural output slot rather
than added prose guidance**.

Prose in `## Important Guidelines` is the weakest lever in this file — the
existing `### Inferred, Unconfirmed` group shows the pattern that actually
works here: an unevidenced claim has a designated place in the output
template, and anything that doesn't fit the template is visibly out of
contract. Apply the same shape to negatives with a new group:

```
### Searched, No Hits
- `attach_evaluators` — searched repo-wide with no glob or type filter — 0 hits
- `validate_evaluators` — searched repo-wide with no glob or type filter — 0 hits
- `some_other_symbol` — searched repo-wide, 0 hits outside `.issues/` (3 hits inside)
```

Rules attached to that group:

- **The row is mandatory, not optional — for explicitly named search targets.**
  A row is required for each identifier, path, or pattern **the caller asked
  you to trace** that does not appear cited in an evidence-bearing group above.
  Silence about a requested target is the out-of-contract state — an omitted
  one is indistinguishable from one that was never searched, which is exactly
  the attention-drift failure mode. "Report what you found and stay silent on
  the rest" is *not* a safe harbor: the caller needs to be able to tell
  "searched, nothing there" from "never looked."

  **The mandate is bounded to named targets, deliberately.** Real caller
  prompts (`/ll:wire-issue` Phase 4, `/ll:manage-issue` Phase 1.5) are prose
  that mentions dozens of terms; a rule reading "every symbol named in the
  request" would demand a row for each of them. The agent would then either
  bloat the section past usefulness or quietly drop the rule altogether — and a
  mandate that gets ignored is worse than none, because a *present* `###
  Searched, No Hits` group that is silently incomplete reads as exhaustive.
  Terms you improvised while exploring (synonyms, guessed naming variants) need
  no row; report them only if useful.
- Each row must state the **scope actually searched**. A row that names a
  narrowing filter (`type: py`, `glob: "*.py"`, a `path:` prefix) is evidence
  only about that slice and must not be summarized as tree-wide absence.
- Before writing a row, re-run the pattern **unfiltered** — the whole tree, no
  `glob`/`type`/`path`. This is the step that would have caught the
  reproduction.

  **Carve-out:** when the *caller* scoped the question to a path or file type
  ("is `X` in `foo.yaml`?", "which Python files reference `Y`?"), no unfiltered
  re-run is required — the row states that caller-supplied scope and the claim
  is never generalized past it. Absent that, this rule and the previous one
  would contradict each other: one permits scoped rows, the other forbids
  producing any.
- **Exclusions are allowed but must be named in the row, and carry the count
  inside the excluded path.** The observed failure claimed "zero hits outside
  `.issues/`" — an exclusion, not an unfiltered search, and often a legitimate
  one (a wire-issue caller genuinely wants `.issues/` excluded).

  Note what an exclusion actually *is* here: your Grep tool takes `glob`,
  `type`, and `path` — there is **no exclude parameter**, and you have no Bash.
  So an exclusion is not a narrower search you run; it is an **unfiltered
  search whose hits under the named path you then discount**. Writing the row as
  "searched, excluding `.issues/`" invites the reader (and you) to treat it as a
  filtered search, re-legitimizing the exact narrowing this group exists to
  prevent. Hence the pinned shape — `0 hits outside `.issues/` (3 hits inside)`
  — which carries the discounted hits with it and is self-evidencing. A row
  that silently applies an exclusion while claiming repo-wide scope is the
  defect, not the exclusion itself.
- One row per distinct symbol. No aggregate negatives covering several symbols
  in a single claim (the attention-drift guard).

The contract lives in the Output Format prose; `## What NOT to Do` carries the
matching prohibition (see Implementation Steps).

## Integration Map

### Files to Modify
- `agents/codebase-locator.md` — Output Format and `## What NOT to Do`
  sections

_Wiring pass added by `/ll:wire-issue`:_
- `.claude-plugin/plugin.json:23` — already registers `./agents/codebase-locator.md`; no new entry needed, listed for confirmation only [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:12403` — agent reference table row for `codebase-locator`: "Find WHERE code lives — file paths grouped by purpose, each citing its Grep match; no reading for analysis." Describes the citation contract generically; staleness check recommended after the wording change, edit only if the row's phrasing becomes inaccurate [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — add two new tuples to `DOC_STRINGS_PRESENT` (list starts line 27; BUG-3260 precedent pair at lines 253-261), consumed by `test_string_present_in_doc()` (line 274). **The needles are pinned here, byte-exact — `DOC_STRINGS_PRESENT` is a literal-substring assertion, so leaving the wording to the implementer guarantees test/source drift:**
  - `("agents/codebase-locator.md", "### Searched, No Hits", "BUG-3330")`
  - `("agents/codebase-locator.md", "searched repo-wide with no glob or type filter", "BUG-3330")`
  - `("agents/codebase-locator.md", "row is mandatory for every requested symbol", "BUG-3330")`

  All three strings must appear verbatim in the agent file (the second inside the example rows of the new group; the third inside the Output Format prose). None contains the substring `file:line`.

  **The third needle is load-bearing, not decoration.** The first two pin the *example rows* only — the mandatory-row prose is the actual contract (AC 2) and would otherwise be the one part of this fix no test can observe. Implementation Step 2 must use that exact phrase in the prose sentence.
- **Do NOT add `agents/codebase-locator.md` to `DOC_STRINGS_ABSENT` for `"file:line"` — that tuple can never pass, and this is not a latent TODO.** The `DOC_STRINGS_ABSENT` list (line 284) forbids the literal substring in the sibling agents (`agents/codebase-analyzer.md`, `agents/codebase-pattern-finder.md`) per ENH-1299, but `agents/codebase-locator.md:79` already contains the literal string inside its own prohibition text — ``…not a line number (no `file:line`)`` — added by BUG-3260. The file states the ENH-1299 rule by quoting the forbidden token, so a substring-absence assertion against it is structurally impossible. The pinned wording for this fix complies with the convention in spirit; no test can or should enforce it here [Agent 3 finding; corrected during review]
- No behavioral/integration test exercises the agent's actual runtime grep/citation behavior — all existing coverage is static doc-string presence/absence assertions on the prompt text plus frontmatter-only checks (`test_enh3098_refine_issue_graph_seeding.py`'s `test_agent_has_no_bash_tool`). This is a known gap inherent to prompt-only LLM-agent guidance, not something this fix can close [Agent 3 finding]
- No existing test asserts an exact line count, line number, or file hash for `agents/codebase-locator.md`, and no test breaks from this change [Agent 3 finding]

### Similar Patterns
- `skills/wire-issue/evidence-confirmation.md` already documents the
  downstream mitigation (never trust an agent's negative without
  confirming); this issue is about hardening the upstream agent instead of
  relying solely on downstream callers to catch it

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/SKILL.md:153` — Phase 4 Agent 1 spawn (`subagent_type="ll:codebase-locator"`); inherits the new negative-claim rule automatically, no edit needed [Agent 1 finding]
- `commands/refine-issue.md:256` — spawns `ll:codebase-locator`; inherits automatically [Agent 1 finding]
- `skills/manage-issue/SKILL.md:111-119` — Phase 1.5 Deep Research spawn; inherits automatically [Agent 1 finding]
- `skills/audit-claude-config/SKILL.md:148`, `skills/audit-claude-config/wave1-prompts.md:134` — spawn `codebase-locator`/`ll:codebase-locator`; inherit automatically [Agent 1 finding]
- `commands/ready-issue.md:95-101` — narrow existence-check spawn; not exposed to the fabrication-claim risk class (per BUG-3260 precedent), but does invoke the agent [Agent 1 finding]
- `commands/iterate-plan.md:60` — prose mention only, no prompt block, no change needed [Agent 1 finding]
- `.qwen/agents/codebase-locator.md`, `.kimi-code/agents/codebase-locator.md`, `.gemini/agents/codebase-locator.md`, `.codex/agents/codebase-locator.toml` — byte-identical generated host mirrors; regenerate via `ll-adapt --apply` after the source changes, do not hand-edit [Agent 1 + Agent 2 finding]. **No test gates this**: the drift tests in `scripts/tests/test_adapters.py` (`test_content_drift_detected_and_rewritten`, line 537; `test_openai_yaml_drift_detected_and_rewritten`, line 458) all construct their fixtures under `tmp_path` and never assert the *checked-in* mirrors match source. Skipping the regen therefore ships stale mirrors silently and the suite stays green — treat it as a manual must-do in this issue. (A real staleness gate is out of scope here; file separately if wanted.)
- `skills/wire-issue/evidence-confirmation.md` — Layer B companion that already quotes Layer A's citation requirement. **Decided: do not mirror the new negative-claim language here.** Layer B's value is that it re-greps independently of whatever Layer A claimed; duplicating Layer A's wording adds maintenance coupling between the two files for no new coverage, and a Layer B that merely restates Layer A's rule is weaker, not stronger, than one that verifies against the tree. Out of scope for this fix, not an open question. [Agent 2 finding; resolved during review]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

**Tests**
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` list (from line 27) paired with `test_string_present_in_doc()` (line 274) asserts literal substrings appear in agent/skill markdown files as `(doc_rel, needle, issue_id)` tuples. The BUG-3260 entry — `("agents/codebase-locator.md", "cite the symbol or pattern your Grep matched", "BUG-3260")` — is the precedent for the positive-evidence rule this issue's negative-claim rule extends. No policy document mandates a matching entry for this fix, but every prior instruction-language change to `agents/codebase-locator.md` in this suite was paired with one.
- The same file also has a mirror `DOC_STRINGS_ABSENT` list + `test_string_absent_from_doc()` (line 284/333) for forbidden-phrase assertions, showing the convention covers both "must contain" and "must not contain" checks on agent markdown bodies.

**Conventions in Force**
- All three research agents (`agents/codebase-locator.md`, `agents/codebase-analyzer.md`, `agents/codebase-pattern-finder.md`) share one section skeleton: `## Output Format` → `## Important Guidelines` → `## What NOT to Do` → closing "REMEMBER" paragraph → `## When to use` — evidence: structural comparison across all three files.
- No existing negative-claim wording ("zero hits", "not present anywhere", "confirm before asserting absence") appears anywhere in `agents/*.md` — grepping the directory for this vocabulary returns no hits. The only existing precedent this fix can build on is the positive-evidence citation rule it extends (`agents/codebase-locator.md:77-82`, added by BUG-3260) and the downstream re-grep gate in `skills/wire-issue/evidence-confirmation.md` (Layer B), which stays out of scope (see the Dependent Files entry for the rationale — resolved during review, no longer an open question).

## Implementation Steps

_Line numbers below are omitted deliberately: each edit shifts the ones after
it. Anchor on the section/heading names instead._

1. In `agents/codebase-locator.md`, add a `### Searched, No Hits` group to the
   Output Format **example block**, immediately after the `### Inferred,
   Unconfirmed` group, using the row shapes pinned in the Tests section — at
   least one unfiltered row
   (`` - `symbol` — searched repo-wide with no glob or type filter — 0 hits ``)
   and one named-exclusion row carrying the inside count
   (`` - `symbol` — searched repo-wide, 0 hits outside `.issues/` (3 hits inside) ``).
2. In the Output Format **prose** above that block, alongside the existing
   positive-evidence rule, state the contract for the new group. The
   mandatory-row sentence must contain the pinned phrase **"row is mandatory
   for every requested symbol"** verbatim (Tests section needle 3) — e.g. "A
   `### Searched, No Hits` row is mandatory for every requested symbol not
   cited in an evidence-bearing group above." The prose must also carry:
   - the **bound** on that mandate — it covers identifiers, paths, and patterns
     the caller asked you to trace, not every term mentioned in the prompt and
     not synonyms you improvised while exploring;
   - omission is out of contract, not a safe fallback;
   - each row states the scope actually searched, and a row naming a narrowing
     filter (`type:`, `glob:`, `path:`) is evidence about that slice only and
     must never be reported as tree-wide absence;
   - re-run the pattern unfiltered before writing a row, **except** when the
     caller scoped the question to a path or file type, in which case the row
     states that caller-supplied scope;
   - exclusions are permitted but must be named in the row **and state the hit
     count inside the excluded path** — the Grep tool has no exclude parameter,
     so an exclusion is an unfiltered search whose hits under that path you
     discount, not a narrower search you ran;
   - one row per distinct symbol, no aggregate negatives.
3. In `## What NOT to Do`, add the matching prohibition bullet — this is the
   home BUG-3260 used for its paired rule (the existing final bullet, "Don't
   return a path because the requested feature/issue *proposes* to build
   something there"), and it is the right one here too. Suggested wording:
   `` - Don't assert a symbol is absent from the tree on the strength of a
   filtered search — a `type:`/`glob:`/`path:`-narrowed miss is evidence about
   that slice only ``. Do **not** put this in `## Important Guidelines`: that
   section is a list of search-technique tips, not contract rules.
4. Add the three pinned `DOC_STRINGS_PRESENT` tuples to
   `scripts/tests/test_wiring_skills_and_commands.py` near the BUG-3260 pair
   (lines 253-261).
5. Regenerate the host mirrors: `ll-adapt --apply`. Do not hand-edit
   `.qwen/`, `.gemini/`, `.kimi-code/`, `.codex/` copies. Nothing in the suite
   catches a skipped regen (see Dependent Files), so confirm the four files
   actually changed in `git status`.
6. Check `docs/reference/API.md:12403` for staleness against the new wording;
   the current row ("...each citing its Grep match; no reading for analysis")
   stays accurate under this change, so edit only if that stops being true.
7. Run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the three pinned `DOC_STRINGS_PRESENT` tuples to `scripts/tests/test_wiring_skills_and_commands.py` (near the BUG-3260 pair, lines 253-261) — exact needles in the Tests section above; do not paraphrase them
- The pinned wording avoids the literal substring `"file:line"`, consistent with the ENH-1299 convention — but do **not** add a `DOC_STRINGS_ABSENT` tuple for this file; it cannot pass (see the Tests section for why)
- Regenerate host mirrors after the source edit: `.qwen/agents/codebase-locator.md`, `.kimi-code/agents/codebase-locator.md`, `.gemini/agents/codebase-locator.md`, `.codex/agents/codebase-locator.toml` (via `ll-adapt --apply`, not hand-edited)
- Check `docs/reference/API.md:12403`'s agent table row for staleness against the new wording; update only if it becomes inaccurate
- **Deliberately out of scope** (not "not applicable"): `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`. The textual claim is accurate — neither sibling contains "Grep matched", "no Grep hit", or "zero-hit" language, so the evidence apparatus is unique to `codebase-locator.md` today. But the *failure class* is not: `codebase-analyzer` can assert an equally damaging false negative ("nothing calls this function", "this branch is unreachable") off the same filtered-Grep mechanism described in Root Cause. Scoping this fix to one agent keeps it small and lets the `### Searched, No Hits` shape prove itself on the agent where the reproduction exists; extending it to the siblings is deferred follow-up work, not a settled non-issue.

  **This deferral needs a landing place or it evaporates.** After this fix
  lands, file a follow-up issue (via `/ll:capture-issue`) to port the
  `### Searched, No Hits` contract to `agents/codebase-analyzer.md` and
  `agents/codebase-pattern-finder.md`, referencing BUG-3330 for the
  filtered-Grep root cause and the proven row shape. Do it as a real issue
  file, not a note here — a deferral recorded only inside the issue that
  defers it is invisible the moment that issue is marked `done`.

## Acceptance Criteria

1. `agents/codebase-locator.md` contains a `### Searched, No Hits` group in its
   Output Format example block, with the pinned row wording, including both the
   unfiltered row and a named-exclusion row that states the hit count inside the
   excluded path.
2. The Output Format prose contains the pinned phrase "row is mandatory for
   every requested symbol", bounds that mandate to targets the caller asked to
   trace, carries the caller-scoped carve-out to the unfiltered re-run rule and
   the exclusion-row inside-count rule, and `## What NOT to Do` carries the
   filtered-search prohibition bullet.
3. `scripts/tests/test_wiring_skills_and_commands.py::test_string_present_in_doc`
   passes for all three new `BUG-3330` tuples.
4. The four host mirrors are regenerated from the new source. Verify
   concretely, since no test gates this (see Dependent Files):
   `git status` shows all four of `.qwen/agents/codebase-locator.md`,
   `.gemini/agents/codebase-locator.md`, `.kimi-code/agents/codebase-locator.md`,
   `.codex/agents/codebase-locator.toml` modified, **and**
   `grep -l "Searched, No Hits" .qwen/agents/codebase-locator.md .gemini/agents/codebase-locator.md .kimi-code/agents/codebase-locator.md .codex/agents/codebase-locator.toml`
   lists all four files.
5. `python -m pytest scripts/tests/` exits 0.
6. A follow-up issue exists for porting the `### Searched, No Hits` contract to
   `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`,
   referencing BUG-3330 (see the Wiring Phase out-of-scope note).

**Not an acceptance gate:** re-running the reproduction through the live agent.
An earlier draft of the Implementation Steps proposed this as verification, but a
single non-deterministic LLM run can neither confirm the fix (a pass may be
luck) nor refute it (a failure may be unrelated drift). Do it once as a manual
spot-check — trace `attach_evaluators`/`validate_evaluators` against
`scripts/little_loops/loops/workflow-generator.yaml` via `ll:codebase-locator`
and confirm the summary either cites the real hits or reports the absence as a
scoped `### Searched, No Hits` row rather than a tree-wide "confirmed zero hits"
claim — and record the outcome in Notes. A bad spot-check is a signal to
re-examine the wording, not an automatic blocker.

## Impact

- **Priority**: P2 — a locator agent asserting false negatives can silently
  corrupt any downstream research (issue refinement, wiring passes, codebase
  audits) that treats its output as ground truth
- **Effort**: Small — prompt/instruction change to one agent definition file
- **Risk**: Low — additive guidance, no behavior removal
- **Breaking Change**: No

## Steps to Reproduce

**Probabilistic, not deterministic** — this is LLM agent behavior, so a single
clean run does not disprove the defect and a single bad run is the expected
failure mode rather than a guaranteed one. Reproduce by shape, not by exact
repetition.

1. Spawn the `ll:codebase-locator` agent with a prompt asking it to trace a
   symbol that exists as a YAML key/state name (not a Python identifier) in
   a large file, alongside several other search terms in the same prompt.
2. Let the agent complete its search and report results.
3. Independently `grep -n <symbol> <file>` the same symbol against the same
   file the agent searched.
4. Observe: the agent's summary can claim a "confirmed... zero hits" result
   that direct grep contradicts.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-26T20:46:38 - `4d24c972-60e1-47a9-b765-76e05e1cd46b.jsonl`
- `/ll:confidence-check` - 2026-08-26T20:33:37 - `e1dbeb25-e8a5-4187-bf3f-becfa88318fe.jsonl`
- `/ll:wire-issue` - 2026-08-26T20:16:40 - `782fbb73-240e-4e96-ad04-a421c2fa5e7a.jsonl`
- `/ll:refine-issue` - 2026-08-26T20:08:19 - `fdfe1063-50b8-41a2-aae7-c524a32eadad.jsonl`
- `/ll:format-issue` - 2026-08-26T19:54:03 - `001e5679-9e60-4be1-8880-9ae8bd851f63.jsonl`
- `/ll:capture-issue` - 2026-08-26T19:31:47 - `3b6a461b-67ff-4f6b-9949-d834388d9cff.jsonl`
