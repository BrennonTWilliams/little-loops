---
captured_at: "2026-04-27T15:38:43Z"
discovered_date: "2026-04-27"
discovered_by: capture-issue
---

# ENH-1298: Convert issue-authoring pipelines from `file:line` to anchor-based references

## Summary

The project's issue-authoring guidelines mandate anchor-based code references (function/class names) and explicitly prohibit line numbers because line numbers drift. Five core orchestration components contradict that policy — they actively *generate*, *prompt for*, and *bake into issue markdown* `file:line` references. As a result, ~52% of active issue files (38 of 73) already contain line numbers, and every refine/wire pass adds more. This enhancement updates the offending components to emit anchors instead, then sweeps the existing backlog and adds a lint to prevent regression.

## Current Behavior

The documented preference (in `docs/reference/ISSUE_TEMPLATE.md` under "Proposed Solution" and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` under "Quality Standards") states:

> Use anchor-based references (function/class names) — line numbers drift, anchors don't.

But the issue-authoring pipeline contradicts it in five places:

1. **`agents/codebase-analyzer.md`** — root upstream. The `Output Format` section's worked example uses `handlers/webhook.js:15-32` style throughout. The `Important Guidelines` section contains the rule "**Always include file:line references** for claims". This agent is invoked by `refine-issue`, `manage-issue`, and others, so its output convention propagates downstream.
2. **`skills/wire-issue/SKILL.md`** — the documented output template (under the section that emits the "Dependent Files (Callers/Importers)", "Documentation", and "Tests" subsections) shows `path/to/caller.py:42`, `docs/relevant.md:23`, `tests/test_integration.py:88` as the demonstrated format. These literal strings get copied into issue files.
3. **`skills/manage-issue/templates.md`** — agent-prompt templates (10+ instances) say "Return detailed analysis with specific file:line references" and result placeholders read `[Discovery 1 with file:line reference]`, `[Similar implementation at file:line]`, etc.
4. **`commands/refine-issue.md`** — the `Agent 2: codebase-analyzer` and `Agent 3: codebase-pattern-finder` prompt blocks request "specific file:line references"; the `Gap Detection` table has a row literally asking "Which file:line contains the bug".
5. **`hooks/prompts/continuation-prompt-template.md`** — handoff template uses `[file:line]` placeholders. *(Lower priority — this template governs intra-session continuation, not issue authoring. Include only if scope allows; see Scope Boundaries.)*

There is currently no validator that rejects line-number references in issue body text, so contamination compounds.

## Expected Behavior

- Issue-authoring pipelines emit anchor-based references: `in function _cmd_sprint_run()`, `under section "Output Format"`, `near class IssueParser` — never `foo.py:42`.
- The five offender files no longer prompt agents for `file:line` and no longer include `file:line` in their output templates / examples.
- Existing active issues (~38 files) have their line-number references rewritten to anchors.
- `ready-issue` (or `verify-issues`) flags `file:line` patterns in issue body text as a quality finding.

## Motivation

**Why this matters:**
- **Backlog rot is already happening.** ~52% of active issues carry references that go stale every time the cited file changes. Most of the references were added by `wire-issue` and `refine-issue` *automatically* — so users following the docs' advice are still getting drift-prone artifacts.
- **The policy is being silently overwritten.** A user who manually authors an issue with anchor references will see them augmented (and effectively replaced) with line numbers the next time `refine-issue` or `wire-issue` runs.
- **Root cause is concentrated.** Five files do ~all the damage, with `codebase-analyzer` as the upstream source. A focused fix stops the bleeding entirely; without it, any backlog sweep gets re-contaminated on the next refine pass.
- **Documented quality criterion already exists** — the file `templates/enh-sections.json` already lists "Proposed Solution should use anchor-based code references (function/class names) instead of line numbers" under `quality_checks.common`. The infrastructure to enforce is partially in place; we just don't act on it.

## Proposed Solution

Three coordinated changes, sequenced so the sweep doesn't re-contaminate:

### 1. Stop the bleeding upstream — rewrite the five offender files

For each, replace `file:line` patterns with anchor-based equivalents in *examples, prompts, and templates*:

- **`agents/codebase-analyzer.md`** (highest leverage): rewrite the `Output Format` worked example to use `in handleWebhook()` / `under section "Request Validation"` style. Replace the `Important Guidelines` rule "Always include file:line references" with "Always include anchor-based references (function/class names; section headings for markdown files) — never raw line numbers". The agent's *capability* of finding line numbers is fine; its *output convention* is what changes.
- **`skills/wire-issue/SKILL.md`**: update the templates under "Callers / importers", "Documentation", and "Tests" so example entries read `path/to/caller.py — calls affected_function() in handle_request()` instead of `path/to/caller.py:42 — calls affected_function()`.
- **`skills/manage-issue/templates.md`**: replace "with file:line references" with "with function/class anchors (e.g. `in function foo()`, `near class Bar`)" across all 10+ instances.
- **`commands/refine-issue.md`**: update the three agent prompts and the `Gap Detection` table to ask for anchors. Update the gap row to "Which function/class contains the bug".
- **`hooks/prompts/continuation-prompt-template.md`**: optional — this is intra-session handoff, not Issues. *Recommended scope: defer unless the team has time. The risk of leaving it is small.*

### 2. Sweep existing backlog

Add a one-shot script (or sweeper skill) that, for each active issue file:
- Finds matches of `\.(py|md|ts|tsx|js|json|yaml):[0-9]+(-[0-9]+)?` and `\bline[s]?\s+[0-9]+`.
- For each match, opens the cited file at the cited line and resolves the enclosing function/class via a simple `^(def|class|function|export function|const \w+ =)` walk-back, or section heading for markdown.
- Replaces the reference inline (`foo.py:42` → `foo.py (in function bar())`).
- Leaves a one-line audit comment in the issue's `Session Log` noting how many refs were rewritten.

Reuse: the codebase already has `little_loops/ast_utils.py` style helpers in places — investigate before writing new walk logic.

### 3. Prevent regression

Extend `ready-issue` (preferred — already runs as a gate) or `verify-issues`:
- Scan the issue body for the regex above.
- Treat any hit as a quality finding (not a hard block) with auto-fix suggestion that names the enclosing function. Reuses the resolver from step 2.

## Integration Map

### Files to Modify

- `agents/codebase-analyzer.md` — rewrite `Output Format` worked example and `Important Guidelines` rule (root upstream — fix this first or downstream changes won't hold).
- `skills/wire-issue/SKILL.md` — update output templates in the section emitting "Dependent Files / Documentation / Tests" subsections.
- `skills/manage-issue/templates.md` — replace all "file:line references" prompt strings.
- `commands/refine-issue.md` — update prompts in `Agent 2: codebase-analyzer`, `Agent 3: codebase-pattern-finder`, and the `Gap Detection` table.
- `hooks/prompts/continuation-prompt-template.md` — *optional, see Scope Boundaries*.
- `skills/ready-issue/SKILL.md` (or `verify-issues`) — add lint check; reuse anchor resolver.
- New: a sweeper script or skill (location TBD — likely `scripts/little_loops/issues/anchor_sweep.py` plus a `commands/ll:anchor-sweep.md` thin wrapper, OR fold into `ready-issue --fix`).

### Dependent Files (Callers/Importers)

- `commands/manage-issue.md` and the `manage-issue` skill — invoke `codebase-analyzer`. Behavior changes transitively once the agent definition changes; verify nothing in those skills *parses* `file:line` from agent output.
- Any skill that calls `wire-issue` or `refine-issue` as a sub-step (check `ll-auto`, `ll-parallel`, `ll-sprint` orchestrators in `scripts/little_loops/`) — same transitive concern.

### Similar Patterns

- `templates/enh-sections.json` `quality_checks.common` already lists the anchor preference as a quality criterion — the lint in step 3 just operationalizes it. Check `bug-sections.json` and `feat-sections.json` for matching entries; add if missing.

### Tests

- `scripts/tests/` — add unit tests for the anchor resolver (function-walk-back, markdown section heading lookup).
- Add an integration test that runs `wire-issue` against a sample issue and asserts the output contains no `:[0-9]+` patterns.
- Add a `verify-issues` test asserting the lint flags a contaminated fixture.

### Documentation

- `docs/reference/ISSUE_TEMPLATE.md` — already correct; no changes needed.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — already correct; no changes needed.
- `CHANGELOG.md` — add entry describing the policy enforcement and backlog sweep (concrete `## [X.Y.Z]` section per project changelog conventions, not Unreleased).

### Configuration

- N/A — no config schema changes.

## Implementation Steps

1. **Update `agents/codebase-analyzer.md`** first (highest leverage, single file). Verify by running `refine-issue` on a sample issue and checking output uses anchors.
2. **Update the four downstream files** (`wire-issue`, `manage-issue/templates.md`, `refine-issue`, optionally `continuation-prompt-template`). These are pure text edits to prompt templates and example blocks.
3. **Build the anchor resolver** (function-walk-back for code files, section-heading lookup for markdown). Lives in `scripts/little_loops/`.
4. **Build the sweeper** that uses the resolver to rewrite references in existing issue files. Run it once against `.issues/**/*.md` (active dirs only — leave `completed/` alone since those are historical record).
5. **Extend `ready-issue` (preferred) with the lint check** that uses the same resolver to flag and optionally auto-fix new contamination.
6. **Verification**: re-run the audit query (`grep -rE '\.(py|md|ts):[0-9]+|line [0-9]+' .issues/{bugs,features,enhancements}`) and confirm hit count drops to zero. Run `wire-issue` and `refine-issue` against a fixture and confirm output is anchor-only.

## API/Interface

No public API changes. Internal:

```python
# scripts/little_loops/issues/anchors.py (new)
def resolve_anchor(file_path: str, line_number: int) -> str:
    """Return enclosing function/class/section name for the given file:line.

    Walks back from line_number to find the most recent def/class/function/
    markdown section heading. Returns 'in function foo()' / 'near class Bar' /
    'under section "Title"' / None if no anchor can be resolved (rare).
    """
```

## Impact

- **Priority**: P2 — affects ~52% of active issue corpus today and contaminates more on every refine/wire pass. Not P0/P1 because no functionality is broken; the cost is gradual quality decay of the backlog as a reference artifact.
- **Effort**: Medium — five text-edit files (small), one anchor resolver (medium, ~half a day), one sweeper (small, reuses resolver), one lint extension (small, reuses resolver). Total ~1-2 sessions if the resolver is straightforward.
- **Risk**: Low — text edits to prompts are reversible; sweeper runs git-tracked so changes are reviewable; lint is advisory not blocking. Main risk: anchor resolver produces wrong function name for edge cases (e.g., line inside a nested closure) — mitigated by adding a `(approx)` suffix when resolution is uncertain.
- **Breaking Change**: No — output format change for issue files is backward-compatible (anchors are valid replacements for line numbers in the same prose context).

## Scope Boundaries

**In scope:**
- The five identified offender files in the issue-authoring pipeline.
- Backlog sweep of `.issues/{bugs,features,enhancements}/*.md` only.
- Lint extension to `ready-issue` or `verify-issues`.

**Out of scope:**
- `hooks/prompts/continuation-prompt-template.md` — defer unless time permits. This is intra-session handoff, not issue authoring; line numbers there are arguably appropriate (a session-bounded artifact, not a long-lived issue).
- Rewriting completed issue files in `.issues/completed/` — those are historical record; sweeping them rewrites history without value.
- Changing `CLAUDE.md`'s general guidance to use `file_path:line_number` in *terminal output to the user* — that is a separate concern (output to humans during a session) and the rationale (clickable navigation) does not apply to issue files.
- Any change to `codebase-analyzer`'s analysis *capability* — only its output convention.

## Success Metrics

- **Active issue contamination drops to ≤5%** (vs. ~52% today) after the sweep.
- **Zero new contamination over a 2-week observation window** after fixes land — measured by re-running the audit grep weekly.
- **`ready-issue` lint catches ≥95% of contamination introduced via copy-pasted snippets** — measured by injecting fixtures with known `file:line` patterns.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/ISSUE_TEMPLATE.md` | Canonical statement of the anchor preference (under "Proposed Solution" and the issue-quality checklist). |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | Quality standards section explicitly mandates anchors over line numbers. |
| `templates/enh-sections.json` | `quality_checks.common` already lists the anchor preference as a quality criterion — this issue operationalizes it. |
| `.claude/CLAUDE.md` | Project guidelines (note: contains a `file_path:line_number` instruction for *terminal output*, which is intentionally out of scope). |

## Labels

`enhancement`, `tooling`, `issue-management`, `policy-enforcement`, `captured`

## Session Log
- `/ll:format-issue` - 2026-04-27T15:44:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/933853fd-592c-42de-a9cd-023028367dfd.jsonl`

- `/ll:capture-issue` - 2026-04-27T15:38:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee48ea9f-1e1e-44a3-be08-80264f2f9ca1.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
