---
id: BUG-3333
type: BUG
title: Port Searched-No-Hits evidence contract to codebase-analyzer and codebase-pattern-finder
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T20:52:00Z'
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3333: Port Searched-No-Hits evidence contract to codebase-analyzer and codebase-pattern-finder

## Summary

BUG-3330 gave `agents/codebase-locator.md` a `### Searched, No Hits` output
group and matching evidence rules so negative claims ("symbol not found")
carry the same citation discipline as positive ones. The fix was
deliberately scoped to `codebase-locator.md` only — the agent where the
reproduction occurred — but the underlying failure mechanism (a filtered
Grep miss generalized into a tree-wide negative claim) is not unique to it.

## Current Behavior

`agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` have no
`### Searched, No Hits` output group, no filtered-vs-unfiltered scope
language, and no negative-claim vocabulary anywhere (confirmed 0 repo-wide
hits for the string `"Searched, No Hits"` in both files). A filtered
Grep/Glob miss inside either agent's tool-restricted search (no Bash) can
therefore be generalized into an unfiltered "not found"/"no caller"/"pattern
not present" claim with no citation discipline forcing the agent to state
the scope actually searched or re-run unfiltered first — the same mechanism
BUG-3330 fixed for `codebase-locator.md` alone.

## Expected Behavior

Both `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`
carry a `### Searched, No Hits` output group (under `## Output Format`) and a
matching `## What NOT to Do` prohibition bullet, ported from
`agents/codebase-locator.md:84-101,135-139,167-169` and adapted to each
agent's own negative-claim vocabulary: "no caller found for `X`" / "`Y` is
unreachable from any traced entry point" for `codebase-analyzer.md`, and "no
existing convention found for `X`" / "`Y` pattern not present in this
codebase" for `codebase-pattern-finder.md`. Every explicitly named target not
confirmed by a citation elsewhere in the output gets a mandatory row stating
the scope searched, with re-run-unfiltered-before-asserting-absence and the
caller-scoped exception carried over unchanged.

## Motivation

`agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` share
the same section skeleton (`## Output Format` -> `## Important Guidelines`
-> `## What NOT to Do`) and the same no-Bash, Grep-only tool restriction as
`codebase-locator.md`. Either can assert an equally damaging false negative
off the same mechanism — e.g. "nothing calls this function" or "this branch
is unreachable" — from a filtered search that only covers a language/path
slice of the tree.

## Steps to Reproduce

1. `grep -n "Searched, No Hits" agents/codebase-analyzer.md agents/codebase-pattern-finder.md`
2. Observe zero matches in both files (contrast with `agents/codebase-locator.md`, which has the group at lines 84-101 post-BUG-3330).
3. Ask the `codebase-analyzer` or `codebase-pattern-finder` subagent a question whose answer is a negative claim scoped by a filtered search (e.g. "does anything call `X`?" restricted to one directory/language) — observe the response state the negative as unqualified rather than citing the searched scope, since neither agent's prompt requires it.

## Proposed Solution

Port the `### Searched, No Hits` contract from BUG-3330's fix to
`agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`,
adapted to each agent's negative-claim vocabulary (e.g. "no caller found",
"pattern not present"):

- A mandatory output row for every explicitly named target not confirmed by
  a citation elsewhere in the output.
- Each row states the scope actually searched; a `type:`/`glob:`/`path:`
  filtered miss is evidence about that slice only.
- Re-run unfiltered before asserting absence, except when the caller scoped
  the question to a path or file type.
- Named exclusions carry the hit count inside the excluded path.
- One row per distinct target — no aggregate negatives.
- A matching prohibition bullet in `## What NOT to Do`.

See BUG-3330 for the root cause (filtered-Grep generalized into an
unfiltered negative) and the proven row wording/shape to reuse.

## Integration Map

### Files to Modify
- `agents/codebase-analyzer.md`, `agents/codebase-pattern-finder.md` — see Codebase Research Findings below for exact insertion points.

### Dependent Files (Callers/Importers)
- See Codebase Research Findings below (`.codex/agents/codebase-pattern-finder.toml`, `.claude-plugin/plugin.json`, `docs/reference/API.md`, host mirrors regenerated via `ll-adapt --apply`).

_Wiring pass added by `/ll:wire-issue`:_
- `.codex/agents/codebase-pattern-finder.toml` — confirmed present on disk (corrects the refine-issue research note above that called this "not confirmed present"); `# generated by ll-adapt` header confirmed at line 1, regenerate via `ll-adapt --apply` after the source files change, do not hand-edit.
- No skill, command, or doc file needs an edit as a result of this change: `skills/wire-issue/SKILL.md`, `skills/manage-issue/SKILL.md` (+`templates.md`), `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md` (+`wave1-prompts.md`), `commands/scan-codebase.md`, `commands/audit-architecture.md`, `commands/iterate-plan.md`, and `docs/guides/GRAPH_DISCOVERY_GUIDE.md` all invoke `codebase-analyzer`/`codebase-pattern-finder` by `subagent_type` and prompt only — none restate the agents' internal Output Format contract, so none go stale from a prose-only addition to the agent files.

### Similar Patterns
- `agents/codebase-locator.md:84-101,135-139,167-169` — the BUG-3330 source pattern being ported.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — see Codebase Research Findings below for the exact `DOC_STRINGS_PRESENT` tuple format and insertion point.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — append new `(doc_path, needle, issue_id)` tuples to `DOC_STRINGS_PRESENT` (list ends at line 277), mirroring the BUG-3330 comment+tuple block at lines 262-276; no new test function needed, `test_string_present_in_doc` (lines 288-294) auto-parametrizes over appended tuples.
- Confirmed no conflicting `DOC_STRINGS_ABSENT` entry (list starts line 299) forbids this wording for either target file — nothing breaks or needs inversion.
- `scripts/tests/test_enh3098_refine_issue_graph_seeding.py:26-30` (`RESEARCH_AGENTS` tuple) and `:147-158` (`TestResearchAgentsStayBashFree`) only gate Bash-tool absence — not reusable for this issue's content assertion, do not extend.

_Wiring pass added by `/ll:wire-issue`:_
- **Existing test constraint to respect (not a new test)**: `scripts/tests/test_wiring_skills_and_commands.py:301-302` (`DOC_STRINGS_ABSENT`, ENH-1299) forbids the literal substring `"file:line"` in both `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`. The source passage being ported (`agents/codebase-locator.md:74-101`) contains that exact substring in the sentence immediately preceding the negative-claim paragraph (the citation-format rule "not a line number (no `file:line`)"). The paragraph at lines 84-101 itself does not contain it, so copying exactly the scoped range (`84-101,135-139,167-169`, per Implementation Steps) stays clean — but widening the copied excerpt to include the preceding citation-format sentence would silently break `test_string_absent_from_doc` for both files. See Wiring Phase for the corresponding caution bullet.

### Documentation
- N/A — confirmed no doc file restates the agents' Output Format contract (see Codebase Research Findings below).

_Wiring pass added by `/ll:wire-issue`:_
- No documentation needs updating: `docs/ARCHITECTURE.md:71-73` only lists both files inside a directory-tree block; no prose elsewhere restates the agents' Output Format contract.

### Configuration
- N/A or list config files

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

**Files to Modify (research):**
- `agents/codebase-analyzer.md` — add a `### Searched, No Hits` group to `## Output Format`, a matching negative-claim paragraph, and a prohibition bullet in `## What NOT to Do`. Currently has no `### Searched, No Hits` string, no filtered-vs-unfiltered scope language, and no negative-claim vocabulary anywhere (confirmed 0 repo-wide hits for `"Searched, No Hits"` in this file).
- `agents/codebase-pattern-finder.md` — same three additions, adapted to this agent's vocabulary ("pattern not present" rather than "symbol not found"). Same 0-hits confirmation.

**Dependent Files (research):**
- `scripts/tests/test_wiring_skills_and_commands.py:301-302` — already carries an unrelated `DOC_STRINGS_ABSENT` pair asserting `"file:line"` is absent from both `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` (ENH-1299); this is the established precedent for a paired two-file test-tuple addition, but for a *different* rule. This issue's own additions belong in `DOC_STRINGS_PRESENT` (see Tests below).
- `.claude-plugin/plugin.json:22,24` — registers both agent files; no change needed, paths are unaffected.
- `docs/reference/API.md:12402,12404` — agent reference table rows for both agents; BUG-3330's precedent left the analogous `codebase-locator` row (`:12403`) unedited since the row content stayed accurate — same expected outcome here.
- Host mirrors (generated, not hand-edited) — **8 files, all confirmed present on disk** by directory listing: `.qwen/agents/{codebase-analyzer,codebase-pattern-finder}.md`, `.gemini/agents/{codebase-analyzer,codebase-pattern-finder}.md`, `.kimi-code/agents/{codebase-analyzer,codebase-pattern-finder}.md`, `.codex/agents/{codebase-analyzer,codebase-pattern-finder}.toml`. (An earlier revision of this note called `.codex/agents/codebase-pattern-finder.toml` "not confirmed present by Grep — inferred by naming convention only"; that is superseded — the file exists. Do not re-litigate.) BUG-3330's precedent: regenerate via `ll-adapt --host <host> --apply` after the source files change; never hand-edit. See Implementation Steps 5.

**Conventions in Force:**
- The three research agents (`codebase-locator.md`, `codebase-analyzer.md`, `codebase-pattern-finder.md`) share one section skeleton — `## Output Format` → `## Important Guidelines` → `## What NOT to Do` → closing "REMEMBER" → `## When to use` — evidence: structural comparison across all three files (this is the same skeleton fact BUG-3330 recorded when scoping its own fix to `codebase-locator.md` alone).
- Every prior instruction-language change to one of these three agent files in this suite is paired with a `DOC_STRINGS_PRESENT` tuple `(doc_path, exact_substring, issue_id)`, comment-tagged with the issue ID above the block — evidence: `scripts/tests/test_wiring_skills_and_commands.py:253-276` (the BUG-3260 and BUG-3330 precedent entries).
- A single test class can parametrize a shared property across all three agent files at once via a `RESEARCH_AGENTS` fixture list, rather than one-off per-file assertions — evidence: `scripts/tests/test_enh3098_refine_issue_graph_seeding.py:147-151`, class `TestResearchAgentsStayBashFree`.

**Tests (research):**
- `scripts/tests/test_wiring_skills_and_commands.py` — add `DOC_STRINGS_PRESENT` tuples for each new substring introduced in both files (mirroring the three BUG-3330 tuples at lines 266-276, tagged `BUG-3333`), consumed by `test_string_present_in_doc()` (line 288).
- No existing test currently gates the *content* of `### Searched, No Hits` sections beyond string-presence; `TestResearchAgentsStayBashFree` in `scripts/tests/test_enh3098_refine_issue_graph_seeding.py:147` only gates the Bash-tool restriction, not this issue's wording.

**Documentation (research):**
- No dedicated doc page describes the `### Searched, No Hits` contract outside the agent files and BUG-3330's own issue text; `docs/ARCHITECTURE.md` and `docs/reference/API.md` only list these agents in directory/reference tables, no prose to update.

**Configuration (research):**
- N/A — no config files involved; `.claude-plugin/plugin.json` registration paths are unaffected by prose-only changes.

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Verbatim source text confirmed for the port (grounds the `path:line` citations already in this issue's Wiring Phase and Similar Patterns entries with the actual content, per claim-grounding — a symbol/line resolving is not the same as the claim about it holding):
  - `agents/codebase-locator.md:84-101` (negative-claim prose, precedes the fenced Output Format example): "Negative claims carry the same discipline. A `### Searched, No Hits` row is mandatory for every requested symbol not cited in an evidence-bearing group above ... Each row must state the scope actually searched — a row naming a narrowing filter (`type:`, `glob:`, `path:`) is evidence about that slice only and must never be reported as tree-wide absence. Re-run the pattern unfiltered ... except when the caller scoped the question to a path or file type ... Exclusions ... must be named in the row and carry the hit count inside the excluded path ... One row per distinct symbol; no aggregate negatives."
  - `agents/codebase-locator.md:135-138` (sample rows inside the fenced template, immediately after `### Inferred, Unconfirmed`, fence closes at 139): `### Searched, No Hits` heading followed by three example rows, e.g. `` - `attach_evaluators` — searched repo-wide with no glob or type filter — 0 hits ``.
  - `agents/codebase-locator.md:165-169` (`## What NOT to Do`, last two bullets): "Don't return a path because the requested feature/issue *proposes* to build something there ... Don't assert a symbol is absent from the tree on the strength of a filtered search — a `type:`/`glob:`/`path:`-narrowed miss is evidence about that slice only."
- Confirmed repo-wide: the only file under `agents/*.md` using any of "Searched, No Hits" / "no hits" / "not found" / "absence of evidence" phrasing today is `agents/codebase-locator.md` (at lines 84 and 135) — `codebase-analyzer.md` and `codebase-pattern-finder.md` have zero existing negative-claim vocabulary to reconcile with, confirming this issue's Decision Rules note that exact wording is this issue's own call, not a copy of locator's symbol-specific phrasing.
- Confirmed `codebase-analyzer.md`'s evidence idiom is anchor/function-based ("anchor-based references (function/class names)", frontmatter description + `## Important Guidelines`), and `codebase-pattern-finder.md`'s is `**Found in**: \`path\` in \`function()\`` — neither uses locator's Grep-match-citation model, so the ported prose block introduces the scope/re-run/exclusion vocabulary net-new to both files rather than aligning it with existing text.

## Program Design

### Types
- N/A — no data-shape change; these are agent-prompt markdown files, not typed code.

### Signatures
- `DOC_STRINGS_PRESENT: list[tuple[str, str, str]]` (`scripts/tests/test_wiring_skills_and_commands.py:253-276`) — the `(doc_path, exact_substring, issue_id)` tuple contract this issue's new pinned strings must follow, same shape as the BUG-3330 precedent tuples at lines 266-276.
- `test_string_present_in_doc(project_root, doc_rel, needle, issue_id)` (`scripts/tests/test_wiring_skills_and_commands.py:289-294`) — the parametrized assertion that consumes each new tuple; no new test function is needed, only new tuples.

**Exact needles to pin (decide here, not at implementation time).** Because Decision Rules deliberately adapt the wording per agent, BUG-3330's three needles cannot be reused as shared literals — two of them (`"row is mandatory for every requested symbol"`, `"searched repo-wide with no glob or type filter"`) are locator-specific. Pin one structural needle plus one vocabulary needle per file, six tuples total:

```python
# BUG-3333: port BUG-3330's negative-claim evidence discipline to the other
# two research agents — a mandatory "### Searched, No Hits" row per requested
# target, re-anchored to each agent's own output template, unfiltered before
# asserting absence.
("agents/codebase-analyzer.md", "### Searched, No Hits", "BUG-3333"),
("agents/codebase-analyzer.md", "searched repo-wide with no glob or type filter", "BUG-3333"),
("agents/codebase-analyzer.md", "no caller found for", "BUG-3333"),
("agents/codebase-pattern-finder.md", "### Searched, No Hits", "BUG-3333"),
("agents/codebase-pattern-finder.md", "searched repo-wide with no glob or type filter", "BUG-3333"),
("agents/codebase-pattern-finder.md", "pattern not present in this codebase", "BUG-3333"),
```

The `searched repo-wide with no glob or type filter` needle is shared across all three agents by design — it is the row-format string, which stays identical; only the target vocabulary differs. Confirm none of these six needles contains the literal `file:line` (they do not) before appending, per the ENH-1299 constraint in the Wiring Phase.

**Needle placement**: each vocabulary needle (`no caller found for`, `pattern not present in this codebase`) must appear verbatim in at least one sample row inside its file's fenced `### Searched, No Hits` group (the rows added in Implementation Steps 2), mirroring how locator's row-format needle lives in its sample rows at `agents/codebase-locator.md:136-137`. The `### Searched, No Hits` heading needle is satisfied by both the prose paragraph and the in-fence group heading.

### Call Path
`DOC_STRINGS_PRESENT` list literal -> `pytest.mark.parametrize("doc_rel, needle, issue_id", DOC_STRINGS_PRESENT)` (`test_wiring_skills_and_commands.py:288`) -> `test_string_present_in_doc()` reads `agents/codebase-analyzer.md` / `agents/codebase-pattern-finder.md` off `project_root` and asserts each `needle` substring is present.

### Decision Rules
- **Negative-claim vocabulary per agent** (adapts BUG-3330's "symbol not found" wording to each agent's own domain): `codebase-analyzer.md` should phrase its `### Searched, No Hits` rows in call/caller/branch terms (e.g. "no caller found for `X`", "`Y` is unreachable from any traced entry point") since its existing vocabulary in `## Analysis Strategy` → `### Step 2: Follow the Code Path` is entirely about tracing calls that *do* exist; `codebase-pattern-finder.md` should phrase rows in pattern-existence terms (e.g. "no existing convention found for `X`", "`Y` pattern not present in this codebase") since its existing vocabulary in `## Search Strategy` is entirely positive-case. Neither file has ANY existing negative-claim phrase today (confirmed by analyzer research — no prior art to preserve, so exact wording is this issue's own call to make, not a copy of codebase-locator's symbol-specific phrasing).
- **Scope discipline and re-run rule**: both files carry the identical `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` tool restriction as `codebase-locator.md` (no Bash — confirmed structurally identical and gated by `TestResearchAgentsStayBashFree`), so the filtered-vs-unfiltered-scope rule and the unfiltered-re-run-before-asserting-absence rule from `codebase-locator.md`'s `## Output Format` (lines 90-99) apply unchanged to both — the mechanism BUG-3330 diagnosed (a `type:`/`glob:`/`path:`-narrowed Grep miss generalized into a tree-wide claim) is not specific to file-location search.
- **Escape hatch**: same as `codebase-locator.md` — when the caller explicitly scoped the question to a path or file type, the row states that caller-supplied scope instead of requiring a fresh unfiltered re-run.
- **Mandatory-row trigger must be re-anchored per file (do not copy locator's phrasing verbatim)**: `agents/codebase-locator.md:85-87` states the rule as "mandatory for every requested symbol not cited in an **evidence-bearing group above**". That phrase is meaningful only because locator's `## Output Format` is explicitly partitioned into evidence-bearing groups versus `### Inferred, Unconfirmed` (`:78-83`, `:131-133`). Neither target file has that partition — `codebase-analyzer.md`'s fenced template is a narrative analysis (`### Overview` → `### Entry Points` → `### Core Implementation` → `### Data Flow` → `### Key Patterns` → `### Configuration` → `### Error Handling`, lines 75-121) and `codebase-pattern-finder.md`'s is a pattern catalog (`### Pattern 1` → `### Pattern 2` → `### Testing Patterns` → `### Pattern Usage in Codebase` → `### Related Utilities`, lines 74-130). Copying the sentence unchanged leaves the trigger undefined in both. Re-anchor it against each file's own template sections:
  - `codebase-analyzer.md` — a row is mandatory for every symbol, function, or entry point the caller asked you to trace that does not appear under `### Entry Points`, `### Core Implementation`, or `### Data Flow`.
  - `codebase-pattern-finder.md` — a row is mandatory for every pattern, convention, or utility the caller asked for that does not appear as a `### Pattern N` section (or under `### Testing Patterns` / `### Related Utilities`).
  - The remaining four rules (searched-scope statement, unfiltered re-run with caller-scoped exception, named-exclusion hit counts, one-row-per-target) port unchanged; only the trigger clause is rewritten.

## Implementation Steps

Each of the two source files needs **two** insertions, not one — the prose paragraph *and* a `### Searched, No Hits` group inside the fenced template (locator carries both: prose at `:84-101`, sample rows at `:135-139` inside its fence). Steps 1 and 2 are deliberately split along that line.

1. Insert the adapted negative-claim **prose paragraph** from `agents/codebase-locator.md:84-101` immediately before the `## Output Format` fence in each file — `agents/codebase-analyzer.md` (heading line 70, fence opens line 74) and `agents/codebase-pattern-finder.md` (heading line 69, fence opens line 73) — re-anchoring the mandatory-row trigger per Program Design → Decision Rules.
2. Add a `### Searched, No Hits` **group with sample rows inside each fenced template**, mirroring `agents/codebase-locator.md:135-139`:
   - `agents/codebase-analyzer.md` — after `### Error Handling` (lines 118-121), immediately before the closing fence at line 122.
   - `agents/codebase-pattern-finder.md` — after `### Related Utilities` (lines 128-130), immediately before the closing fence at line 131. **Note the nested fence**: this template contains an inner ` ```javascript ` block at lines 80-104, so line 131 is the *outer* closing fence; do not insert against the first ` ``` ` encountered after line 73.
3. Add the matching prohibition bullet to `## What NOT to Do` in both files (mirroring `agents/codebase-locator.md:167-169`) — analyzer heading line 133 (bullets 135-146), pattern-finder heading line 172 (bullets 174-184).
4. Append the six `DOC_STRINGS_PRESENT` tuples verbatim from Program Design → Signatures to `scripts/tests/test_wiring_skills_and_commands.py` (after line 276, before the closing `]` at line 277) and run `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` to verify.
5. **Regenerate the eight host mirrors** — this step is mandatory and unguarded by any test (see the caution below). Use `--only` to scope each run to one agent, so the diff is exactly the 8 target files — a bare `ll-adapt --host <host> --apply` regenerates *every* agent for that host and would sweep any unrelated drifted mirror into the commit, breaking the `git status` check below:
   ```bash
   for host in codex gemini kimi-code qwen; do
     ll-adapt --host "$host" --only codebase-analyzer --apply
     ll-adapt --host "$host" --only codebase-pattern-finder --apply
   done
   ```
   `ll-adapt` takes exactly one `--host` and one `--only` per invocation (`ll-adapt --help`), so all eight run. This rewrites `.codex/agents/{codebase-analyzer,codebase-pattern-finder}.toml` and `.{gemini,kimi-code,qwen}/agents/{codebase-analyzer,codebase-pattern-finder}.md` — 8 files, all carrying a `# generated by ll-adapt` header. Never hand-edit them. Confirm with `git status` that exactly these 8 show as modified; BUG-3330's commit (`96ec85c54`) regenerated the 4 locator mirrors as part of the same change.
6. Run the full suite: `python -m pytest scripts/tests/`.

**Caution — mirror staleness is not caught by the test suite.** Nothing asserts mirror content matches the source agent files; `scripts/tests/test_adapters.py:1176-1203` only checks that each `.gemini/agents/*.md` *exists* and carries a degraded-mode marker. Skipping step 5 leaves eight stale mirrors behind a fully green `python -m pytest scripts/tests/`, so step 5 cannot be inferred from a passing run — verify it by diff.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Port from `agents/codebase-locator.md:84-101` (negative-claim paragraph: mandatory-row rule, searched-scope statement, unfiltered-re-run rule with caller-scoped exception, exclusion-hit-count rule, one-row-per-symbol rule), `:135-139` (sample `### Searched, No Hits` rows inside the fenced example block), and `:167-169` (the `## What NOT to Do` prohibition bullet).
- `agents/codebase-analyzer.md` — insert the adapted negative-claim paragraph before the `## Output Format` fence (heading at line 70, fence spans 74-122, section ends at line 123 before `## Important Guidelines` at line 124); this agent's Output Format is a single fenced template with no negative-space section today (stops at `### Error Handling`, lines 118-121), so a `### Searched, No Hits`-equivalent group must also be added inside the fence. Add the matching prohibition bullet to `## What NOT to Do` (heading line 133, bullets 135-146, ends before `## REMEMBER...` at line 148).
- `agents/codebase-pattern-finder.md` — same shape: insert the adapted paragraph before the `## Output Format` fence (heading at line 69, fence spans 73-131, section ends at line 133 before `## Pattern Categories to Search`); same fenced-template-has-no-negative-section gap. The in-fence group goes after `### Related Utilities` (lines 128-130), immediately before the closing fence at line 131 — **this template nests an inner ` ```javascript ` fence at lines 80-104**, so line 131 is the outer close, not the first ` ``` ` after the fence opens. Add the matching prohibition bullet to `## What NOT to Do` (heading line 172, bullets 174-184, ends before `## REMEMBER...` at line 186).
- **Host-mirror regeneration is part of the implementation, not a follow-up** — see Implementation Steps 5 for the four `ll-adapt --host <host> --apply` invocations and the 8 files they rewrite. It is unguarded by any test.
- Append the corresponding `DOC_STRINGS_PRESENT` tuples to `scripts/tests/test_wiring_skills_and_commands.py` (append after line 276, before the closing `]` at line 277), tagged `BUG-3333`.
- **Caution**: do not widen the copied excerpt from `agents/codebase-locator.md:84-101` to include the preceding citation-format sentence ("not a line number (no `file:line`)") — that sentence contains the literal substring `file:line`, which `scripts/tests/test_wiring_skills_and_commands.py:301-302` (`DOC_STRINGS_ABSENT`, ENH-1299) asserts is absent from both target files. Copying exactly lines 84-101 (the negative-claim paragraph only) stays clean.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Each of `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` gains a `### Searched, No Hits` group under its `## Output Format` section (currently absent — 0 repo-wide hits confirmed for that string in both files), a negative-claim paragraph carrying the same scope/re-run/exclusion/one-row-per-target rules as `agents/codebase-locator.md:84-101`, and a matching prohibition bullet in `## What NOT to Do` (mirroring `agents/codebase-locator.md:167-169`).
- The new pinned wording is covered by new `DOC_STRINGS_PRESENT` tuples in `scripts/tests/test_wiring_skills_and_commands.py` (mirroring the BUG-3330 precedent block at lines 262-276), tagged `BUG-3333`; `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` passes with the new tuples included.
- The four generated host mirrors (`.qwen/`, `.gemini/`, `.kimi-code/`, `.codex/`) are regenerated via `ll-adapt --apply` after the two source files change, per the BUG-3330 precedent (`## Resolution`) — not hand-edited.
- `docs/reference/API.md:12402,12404` reference-table rows for both agents are checked for continued accuracy; BUG-3330's precedent left the analogous row unedited when its content stayed correct.

## Impact

- **Priority**: P3 - Not a live false-negative report (unlike BUG-3330's originating incident); closes a known gap in two agents sharing the same failure mechanism, but no reproduction has yet surfaced a harmful output from either.
- **Effort**: Small - Prose-only port of an already-proven contract (BUG-3330) into two files with an identical section skeleton, plus mirrored test tuples; no new mechanism to design.
- **Risk**: Low - Additive prompt instructions only; no code path changes, no existing behavior removed.
- **Breaking Change**: No

## Related Issues

- BUG-3330 — origin of the `### Searched, No Hits` contract, fixed for
  `codebase-locator.md` only

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-27T19:22:26 - `7839b9c3-7a0f-4732-a76a-0e00fbd4022d.jsonl`
- `/ll:wire-issue` - 2026-08-27T19:15:03 - `44ca8d09-8ec6-4d45-87da-fd9e70de0ac6.jsonl`
- `/ll:refine-issue` - 2026-08-27T19:07:11 - `fe439746-77d7-4eee-9bd7-848cc9185040.jsonl`
- `/ll:format-issue` - 2026-08-27T19:00:26 - `fcccc5bc-b39a-4a39-b315-dea54077e260.jsonl`
- `/ll:confidence-check` - 2026-08-27T00:14:38 - `e7618186-c78c-476b-842e-6bec80373242.jsonl`
- `/ll:wire-issue` - 2026-08-27T00:11:24 - `a7af0123-9321-4794-adc6-9737b10d1d10.jsonl`
- `/ll:refine-issue` - 2026-08-27T00:05:23 - `9041f420-0661-44f2-86c3-c7d0ad98ee7f.jsonl`
- `/ll:capture-issue` - 2026-08-26T20:52:06 - `0bf7be52-4470-4341-8647-365e248c9992.jsonl`
