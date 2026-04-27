---
captured_at: "2026-04-27T15:38:43Z"
discovered_date: "2026-04-27"
discovered_by: capture-issue
decision_needed: false
missing_artifacts: true
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
size: Very Large
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
- `agents/codebase-pattern-finder.md` — has the same `file:line references` convention at lines 11 and 65; update alongside `codebase-analyzer.md` or its output will re-contaminate downstream prompts.
- `skills/wire-issue/SKILL.md` — update output templates in the section emitting "Dependent Files / Documentation / Tests" subsections.
- `skills/manage-issue/templates.md` — replace all "file:line references" prompt strings.
- `commands/refine-issue.md` — update prompts in `Agent 2: codebase-analyzer`, `Agent 3: codebase-pattern-finder`, and the `Gap Detection` table.
- `hooks/prompts/continuation-prompt-template.md` — *optional, see Scope Boundaries*.
- `skills/ready-issue/SKILL.md` (or `verify-issues`) — add lint check; reuse anchor resolver.
- `scripts/little_loops/cli/issues/__init__.py` — add `anchor-sweep` subparser block and dispatch branch in `main_issues()`; update epilog string (referenced in "Existing Infrastructure" section but must be listed here as a required edit).
- New: `scripts/little_loops/issues/__init__.py` + `scripts/little_loops/issues/anchors.py` (anchor resolver module).
- New: `scripts/little_loops/issues/anchor_sweep.py` (sweeper), with thin CLI wrapper as `scripts/little_loops/cli/issues/anchor_sweep.py` following the `check_readiness.py` pattern.

### Dependent Files (Callers/Importers)

- `commands/manage-issue.md` and the `manage-issue` skill — invoke `codebase-analyzer`. Behavior changes transitively once the agent definition changes; verify nothing in those skills *parses* `file:line` from agent output.
- Any skill that calls `wire-issue` or `refine-issue` as a sub-step (check `ll-auto`, `ll-parallel`, `ll-sprint` orchestrators in `scripts/little_loops/`) — same transitive concern.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/issue-workflow/SKILL.md` — integrates all five affected commands (`refine-issue`, `wire-issue`, `manage-issue`, `ready-issue`, `verify-issues`); behavior changes transitively when agent output convention changes.
- `scripts/little_loops/loops/autodev.yaml` — FSM loop that invokes `refine-issue`, `wire-issue`, and `ready-issue` as states; verify no state expects `file:line` in its output matching logic.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — invokes refine, ready, verify steps; same transitive check.
- `scripts/little_loops/loops/recursive-refine.yaml` — invokes refine steps.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — invokes the full pipeline.
- `scripts/little_loops/loops/issue-refinement.yaml` — invokes refine steps.

### Similar Patterns

- `templates/enh-sections.json` `quality_checks.common` already lists the anchor preference as a quality criterion — the lint in step 3 just operationalizes it. Check `bug-sections.json` and `feat-sections.json` for matching entries; add if missing.

### Tests

- `scripts/tests/` — add unit tests for the anchor resolver (function-walk-back, markdown section heading lookup).
- Add an integration test that runs `wire-issue` against a sample issue and asserts the output contains no `:[0-9]+` patterns.
- Add a `verify-issues` test asserting the lint flags a contaminated fixture.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_anchors.py` — new test file for `scripts/little_loops/issues/anchors.py`; follow pattern from `test_ll_issues_atomic_write.py` (one class per logical unit, `tmp_path` for I/O, module docstring citing ENH-1298). Cover: function walk-back, class walk-back, markdown section heading lookup, code-fence exclusion, and no-anchor-found fallback.
- `scripts/tests/test_enh1298_doc_wiring.py` — structural test asserting that `commands/refine-issue.md`, `skills/wire-issue/SKILL.md`, `agents/codebase-analyzer.md`, and `agents/codebase-pattern-finder.md` no longer contain `file:line` language patterns after the edit pass; follow pattern from `test_refine_issue_command.py`.
- `scripts/tests/test_issue_discovery.py:252-264` — `test_extract_line_numbers` — update if `_extract_line_numbers` regex is modified; currently has one test case asserting `src/file.py:20-30` yields `{20, 30}`. [update if regex changes]
- `scripts/tests/test_dependency_mapper.py:54-115` — `TestExtractFilePaths` — add test cases for anchor-format input (e.g. `file.py` with no `:N` suffix); current tests don't explicitly verify line-number stripping. [add cases]
- `scripts/tests/test_text_utils.py` — add direct tests for `extract_file_paths`, `_STANDALONE_PATH`, and `_CODE_FENCE`; currently only tests `extract_words`/`calculate_word_overlap`/`score_bm25`. [add cases]

### Documentation

- `docs/reference/ISSUE_TEMPLATE.md` — already correct; no changes needed.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — already correct; no changes needed.
- `CHANGELOG.md` — add entry describing the policy enforcement and backlog sweep (concrete `## [X.Y.Z]` section per project changelog conventions, not Unreleased).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-issues` section (lines 474–718) needs a new `anchor-sweep` subcommand entry with flag table and example (mirrors the `check-readiness` entry pattern).
- `docs/reference/API.md` — `main_issues` subcommands table (around line 2976) needs a new `anchor-sweep` row.
- `docs/ARCHITECTURE.md` — `cli/issues/` directory tree block (around line 208) needs a line for `anchor_sweep.py`.
- `README.md` — `### ll-issues` section (around line 466) needs an `anchor-sweep` example line.
- `.claude/CLAUDE.md` line 116 — `ll-issues` subcommand list needs `anchor-sweep` added to the parenthetical enumeration.

### Configuration

- N/A — no config schema changes.

### Existing Infrastructure to Reuse

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/text_utils.py` in `extract_file_paths()` — `_STANDALONE_PATH` regex already matches `file.py:42` style (captures then strips the `:N` suffix); `_CODE_FENCE` regex provides code-fence exclusion. Both are directly reusable for the detector.
- `scripts/little_loops/issue_discovery/matching.py` in `_extract_line_numbers()` — the `:(\d+)(?:-(\d+))?` capturing pattern shows the established `re.finditer` convention for extracting line numbers from issue text.
- `scripts/little_loops/doc_counts.py` in `fix_counts()` — canonical two-phase sweep-and-rewrite pattern (collect hits, then fix grouped by file). Follow this shape for the sweeper.
- `scripts/little_loops/dependency_mapper/operations.py` in `fix_dependencies()` — `dry_run` parameter convention, `FixResult` dataclass return type.
- `scripts/little_loops/file_utils.py` — `atomic_write()` for safe issue-file rewrites.
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` / `update_frontmatter()` for any frontmatter edits during a sweep.
- `scripts/little_loops/cli/issues/__init__.py` in `main_issues()` — dispatch table; add `anchor-sweep` sub-parser and case here following the existing `check-readiness` / `check-flag` pattern.
- `scripts/little_loops/cli/issues/check_readiness.py` — model for `cmd_anchor_sweep()` function signature (`config: BRConfig, args: argparse.Namespace) -> int`) and `--check` exit-code convention.
- `scripts/little_loops/issue_parser.py` in `_strip_code_fences()` — closest structural analogue for a line-by-line stateful scanner (state machine over `content.split("\n")`).

**Note on directory**: `scripts/little_loops/issues/` does not exist yet — creating `anchors.py` there also requires a new `__init__.py`. No `ast_utils.py` exists in the package; the anchor resolver must be written using Python stdlib `ast` module.

**Note on templates**: All three section templates (`enh-sections.json`, `bug-sections.json`, `feat-sections.json`) already contain the anchor preference in `quality_checks.common`. No template changes needed.

## Implementation Steps

1. **Update `agents/codebase-analyzer.md`** first (highest leverage, single file). Verify by running `refine-issue` on a sample issue and checking output uses anchors.
2. **Update the four downstream files** (`wire-issue`, `manage-issue/templates.md`, `refine-issue`, optionally `continuation-prompt-template`). These are pure text edits to prompt templates and example blocks.
3. **Build the anchor resolver** (function-walk-back for code files, section-heading lookup for markdown). Lives in `scripts/little_loops/`.
4. **Build the sweeper** that uses the resolver to rewrite references in existing issue files. Run it once against `.issues/**/*.md` (active dirs only — leave `completed/` alone since those are historical record).
5. **Extend `ready-issue` (preferred) with the lint check** that uses the same resolver to flag and optionally auto-fix new contamination.
6. **Verification**: re-run the audit query (`grep -rE '\.(py|md|ts):[0-9]+|line [0-9]+' .issues/{bugs,features,enhancements}`) and confirm hit count drops to zero. Run `wire-issue` and `refine-issue` against a fixture and confirm output is anchor-only.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `agents/codebase-pattern-finder.md` to the text-edit pass in Step 2 — update lines 11 and 65 where "Returns actual code snippets with file:line references" and "Include file:line references" appear; otherwise `codebase-pattern-finder` will re-contaminate downstream issues during `refine-issue` runs.
8. Register `anchor-sweep` in `scripts/little_loops/cli/issues/__init__.py` — add `subs.add_parser("anchor-sweep", ...)`, a lazy import of the subcommand module, a dispatch branch in `main_issues()`, and update the epilog string; follow the `check_readiness` / `check_flag` pattern added in the recent commit.
9. Update `docs/reference/CLI.md` — add `anchor-sweep` section under `### ll-issues` (flag table + example).
10. Update `docs/reference/API.md` — add `anchor-sweep` row in the `main_issues` subcommands table.
11. Update `docs/ARCHITECTURE.md` — add `anchor_sweep.py` entry to the `cli/issues/` directory tree block.
12. Update `README.md` and `.claude/CLAUDE.md` — add `anchor-sweep` example / listing to the `ll-issues` sections.
13. Write `scripts/tests/test_issues_anchors.py` — unit tests for `resolve_anchor()` covering function walk-back, class walk-back, markdown section heading lookup, code-fence exclusion, and no-anchor-found fallback.
14. Write `scripts/tests/test_enh1298_doc_wiring.py` — structural assertions that the primary target files no longer contain `file:line` language patterns after the edit pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 exact targets**: `agents/codebase-analyzer.md` — change the `Important Guidelines` rule (`"Always include file:line references for claims"`) and rewrite all `file.js:N` examples in the `## Output Format` section to anchor style (e.g., `` `handlers/webhook.js` in `handleWebhook()` ``). Also update the `description` YAML frontmatter which says "precise file:line references" and "exact file:line references".
- **Step 2 exact targets**: `skills/wire-issue/SKILL.md` Phase 4 agent prompt (`"Return analysis with specific file:line references."`), Phase 8a Integration Map templates (`` `path/to/caller.py:42` ``), and Phase 10 output report template. `skills/manage-issue/templates.md` sections: Codebase Analyzer Prompt (line 32), Research Findings Template (lines 57-68), Enhanced Plan Template `[file:line]` slots, Session Continuation Template. `commands/refine-issue.md` Agent 2 and Agent 3 prompts, Gap Detection table "Which file:line contains the bug" row, and Integration Map populate templates.
- **Step 3 (anchor resolver)**: New package `scripts/little_loops/issues/` needs `__init__.py` + `anchors.py`. For code files: use `ast.parse(source)` and walk nodes to find the last `FunctionDef`/`AsyncFunctionDef`/`ClassDef` whose `node.lineno ≤ target_line`. For markdown files: scan `lines[:target_line][::-1]` for `^#{1,6}\s+` heading. Use `_CODE_FENCE` regex from `text_utils.py` to exclude code-fence spans before scanning.
- **Step 4 (sweeper)**: Follow `fix_counts()` in `doc_counts.py` — two-phase shape: (1) scan issue files using `_STANDALONE_PATH` pattern from `text_utils.py` to collect `(path, line_number)` matches outside code fences, call resolver, collect `(file_path, span, replacement)` tuples; (2) apply grouped by file with `atomic_write()` from `file_utils.py`. Add `--dry-run` following `fix_dependencies()` in `dependency_mapper/operations.py`. Register as `anchor-sweep` in `main_issues()` dispatch table in `cli/issues/__init__.py`.
- **Step 5 (ready-issue lint)**: Insert new bullet in `### Code References` block under `### 2. Validate Issue Content`. Add new correction category `[anchor_rewrite]` to the `CORRECTIONS_MADE` list in Phase 5 auto-correction. The existing `_CODE_FENCE` / `_STANDALONE_PATH` machinery from `text_utils.py` drives the detection.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-27_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- `skills/ready-issue/SKILL.md` does not exist — the ready-issue implementation lives at `commands/ready-issue.md`; the Integration Map path needs correction before Step 5 can be executed cleanly.
- Large transitive caller surface — 14 files reference `codebase-analyzer` and 6 FSM loops invoke the pipeline; the verification step (confirming no state parses `file:line` from agent output) spans a broad surface.
- New Python package with no existing code — the stdlib `ast` walk-back for function resolution has edge cases (nested closures, decorators, conditional defs); plan extra time for this component and validate thoroughly before the sweep.
- Batch sweep risk — 49 active issue files will be rewritten by an unproven resolver; a `--dry-run` pass is essential before committing the sweep to avoid silent corruption.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-27T16:22:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6805eb58-0b32-4596-a10d-4137f4b7cce1.jsonl`
- `/ll:wire-issue` - 2026-04-27T16:00:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d54eeff-f86d-4b23-8cfc-7b8fbdbb1bdb.jsonl`
- `/ll:refine-issue` - 2026-04-27T15:51:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5a45a6d-6d80-457a-8641-7851f84d3dca.jsonl`
- `/ll:format-issue` - 2026-04-27T15:44:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/933853fd-592c-42de-a9cd-023028367dfd.jsonl`

- `/ll:confidence-check` - 2026-04-27T17:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:capture-issue` - 2026-04-27T15:38:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee48ea9f-1e1e-44a3-be08-80264f2f9ca1.jsonl`

- `/ll:issue-size-review` - 2026-04-27T17:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- manual review - 2026-04-27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6004b6bd-98cd-4890-a69a-b3c5136d203f.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-27
- **Reason**: Issue too large for a single session; decomposed into focused child issues.

### Decomposed Into

- ENH-1299: Fix `file:line` references in issue-authoring pipeline source files (pure text edits, no code)
- ENH-1300: Build anchor resolver module and backlog sweeper (`ll-issues anchor-sweep`)

### Note

Step 3 of the original proposal (extending `ready-issue` with an anchor lint check) was not captured in either child at decomposition time. That scope should be tracked as a follow-on issue if the lint gate is still desired after ENH-1299 and ENH-1300 land.

---

**Decomposed** | Created: 2026-04-27 | Priority: P2
