---
id: FEAT-953
type: FEAT
title: "as-a-user eval harness skill from issue IDs"
priority: P3
status: open
discovered_date: 2026-04-04
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 71
---

# FEAT-953: as-a-user eval harness skill from issue IDs

## Summary

Create a new `/ll:create-eval-from-issues` skill that accepts one or more Issue IDs (open or completed), reads each issue's context and acceptance criteria, derives as-a-user evaluation criteria from that context, and generates a ready-to-run FSM harness YAML containing a `check_skill` evaluation gate that simulates a real user verifying the feature works as described.

## Current Behavior

There is no automated way to go from an issue file to a `check_skill`-based eval harness. Users must hand-author the harness YAML and write evaluation criteria manually, referencing the issue content by memory.

## Expected Behavior

Running `/ll:create-eval-from-issues FEAT-919 ENH-950` should:
1. Read each named issue file and extract relevant context (title, use case, acceptance criteria, proposed solution)
2. Synthesize concise "did this work as a user would expect?" evaluation criteria from that context
3. Generate a harness YAML containing a `check_skill` state with those criteria embedded in an `llm_structured` evaluation prompt
4. Write the harness to `.loops/<slug>.yaml` and print validation output

For a single issue: produce a Variant A (single-shot) harness targeting the issue's skill.
For multiple issues: produce a Variant B (multi-item) harness that iterates over each issue's associated skill.

## Use Case

**Who**: A developer using little-loops who has implemented one or more issues and wants automated validation of the result

**Context**: After running `/ll:manage-issue` or completing implementation work, they want a structured eval harness that tests the feature from a real user's perspective — without hand-authoring YAML

**Goal**: Generate a valid FSM harness YAML that exercises the skill described in the issue(s) and evaluates success using the issue's acceptance criteria and use case language

**Outcome**: A `.loops/eval-harness-<slug>.yaml` file written to disk, validated by `ll-loop validate`, and ready to run immediately with `ll-loop run`

## Motivation

The `check_skill` evaluation gate is the highest-fidelity phase in the harness pipeline — it's the only phase that evaluates from a real user's perspective. But it's currently the hardest to author because it requires translating issue language into a precise, testable evaluation prompt. This skill closes that gap: an issue already contains the user story, use case, and acceptance criteria; those are exactly the inputs needed to define a meaningful as-a-user eval.

This also enables a "issue-to-harness-to-loop" workflow: refine an issue → generate a harness → run the loop unattended.

## Acceptance Criteria

- [ ] Running `/ll:create-eval-from-issues FEAT-919` resolves the issue file and writes `.loops/eval-harness-feat-919.yaml`
- [ ] Generated harness contains a `check_skill` state with synthesized as-a-user evaluation criteria drawn from the issue's use case and acceptance criteria
- [ ] Single issue → Variant A harness (`initial: execute`); 2+ issues → Variant B harness with `discover` state iterating over issue IDs
- [ ] Generated harness passes `ll-loop validate` before being written to disk
- [ ] Both open and completed issue IDs are accepted as input
- [ ] Synthesized criteria include the observable success signal and failure signal from the issue context

## Proposed Solution

### Skill: `/ll:create-eval-from-issues`

**Arguments**: one or more issue IDs (e.g., `FEAT-919`, `ENH-950`)
**Output**: `.loops/eval-harness-<slug>.yaml`

**Steps:**

1. **Resolve issue files** — use `ll-issues` to resolve each ID to a file path; support both open and completed issues.
2. **Extract evaluation context** — from each issue, extract:
   - `title` — the feature being evaluated
   - Use Case / User Story section — what does success look like to the user?
   - Proposed Solution / Implementation Steps — scope of what was built
   - Acceptance criteria (if present in any section)
3. **Synthesize as-a-user criteria** — compose an `llm_structured` evaluation prompt that asks "did the user experience work as the issue described?" Include:
   - The specific use case / workflow to exercise
   - The observable signal that indicates success
   - The failure signal (error, missing element, wrong behavior)
4. **Select harness variant**:
   - 1 issue → Variant A (single-shot) with `initial: execute`
   - 2+ issues → Variant B (multi-item) with `discover` state iterating over issue IDs
5. **Generate YAML** following the structure in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, with:
   - `execute` state: invokes the issue's associated skill (inferred from issue content or prompted)
   - `check_skill` state: runs as-a-user simulation with synthesized criteria
   - `check_invariants` state: diff size guard
6. **Validate** via `ll-loop validate` before writing and report result.

### Example output (single issue)

```yaml
name: "eval-harness-feat-919"
initial: execute
max_iterations: 5
states:
  execute:
    action: "/ll:manage-issue FEAT IMPLEMENT 919"
    action_type: prompt
    next: check_skill

  check_skill:
    action: >
      Use the JSON schema generation feature as described in FEAT-919.
      Navigate to the schema builder, provide a sample input, and confirm
      that a valid JSON schema is generated without errors.
    action_type: prompt
    timeout: 180
    evaluate:
      type: llm_structured
      prompt: >
        Did the skill successfully exercise the JSON schema generation flow
        from FEAT-919? Confirm: (1) the schema builder accepted input,
        (2) a valid JSON schema was returned, (3) no errors occurred.
        Answer YES only if all three conditions are met. Otherwise NO with
        which condition failed.
    on_yes: check_invariants
    on_no: execute

  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: done
    on_no: execute

  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `skills/create-eval-from-issues/SKILL.md` — new skill definition
- `skills/create-eval-from-issues/skill.md` (or `prompt.md`) — implementation prompt
- `commands/create-eval-from-issues.md` — slash command entry point

### Dependent Files (Callers/Importers)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add reference to this skill in "Creating a Harness" section
- `skills/create-loop/loop-types.md` — optionally reference as an alternative entry point for check_skill harnesses
- `.claude-plugin/plugin.json` — register new skill

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — static hardcoded help text; add `create-eval-from-issues` to AUTOMATION & LOOPS section (~line 149–158) and quick reference table (~line 244–251) [Agent 1]
- `docs/reference/COMMANDS.md` — full command-by-command reference; needs new entry for `/ll:create-eval-from-issues` [Agent 1]

### Similar Patterns
- `skills/create-loop/` — existing harness creation wizard; this skill is a focused alternative for the `check_skill` path
- `skills/refine-issue/` — reads issue files and extracts structured content
- `scripts/little_loops/loops/harness-single-shot.yaml` — template for generated output
- `scripts/little_loops/loops/harness-multi-item.yaml` — template for multi-issue output

### Tests
- `scripts/tests/` — add unit tests for criteria synthesis logic and YAML generation

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:38` — skill count `24 → 25`; manual (not in `DOC_FILES` for `ll-verify-docs`) [Agent 2]
- `.claude/CLAUDE.md:56` — Commands & Skills listing; add `create-eval-from-issues`^ to Automation & Loops category [Agent 2]
- `README.md:89` — skill count `24 → 25` (auto-fixable via `ll-verify-docs --fix`) [Agent 1/2]
- `README.md:206-231` — Skills table; add new row for `create-eval-from-issues`^ (manual) [Agent 2]
- `CONTRIBUTING.md:125` — skill count `24 → 25` (auto-fixable) [Agent 1/2]
- `CONTRIBUTING.md:126-147` — explicit skill directory tree; add `create-eval-from-issues/` entry (manual) [Agent 2]
- `docs/ARCHITECTURE.md:26,99` — skill counts in Mermaid diagram and directory tree header (auto-fixable) [Agent 1/2]
- `docs/ARCHITECTURE.md:100-155` — explicit skill directory listing; add `create-eval-from-issues/` alphabetically (manual) [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — `commands/create-eval-from-issues.md` is NOT needed.** Skills under `skills/*/SKILL.md` are auto-discovered by the plugin manifest (`/.claude-plugin/plugin.json:20` — `"skills": ["./skills"]`). A parallel `commands/` entry would duplicate the registration.

**Key integration points:**
- `scripts/little_loops/cli/issues/show.py:17` — `_resolve_issue_id()` handles all three ID formats (`953`, `FEAT-953`, `P3-FEAT-953`); searches all categories including completed/deferred
- `scripts/little_loops/cli/issues/show.py:360` — `cmd_show()` with `--json` flag outputs `{path, title, summary, status, issue_id}` — use `ll-issues show <ID> --json` to extract context
- `scripts/little_loops/cli/loop/config_cmds.py:11` — `cmd_validate()` implements `ll-loop validate`; resolves `.loops/<name>.yaml` first, then built-ins
- `scripts/little_loops/fsm/validation.py:292` — `validate_fsm()` checks state refs, terminal state existence, required evaluator fields
- `scripts/little_loops/fsm/validation.py:77` — `KNOWN_TOP_LEVEL_KEYS`; generated YAML must only use these top-level keys
- `scripts/little_loops/loops/harness-multi-item.yaml:118-134` — exact `check_skill` state YAML structure to model for Variant B
- `scripts/little_loops/loops/harness-single-shot.yaml:93-111` — commented `check_skill` block for Variant A

**Model skill files:**
- `skills/create-loop/SKILL.md:1-8` — canonical skill frontmatter (`description`, `allowed-tools` with glob-restricted Bash)
- `skills/manage-issue/SKILL.md:1-22` — argument declarations pattern (`argument-hint`, `arguments` list with `name/description/required`)
- `skills/create-loop/SKILL.md:174-208` — save-and-validate sequence (mkdir, check-exists, Write tool, `ll-loop validate`)
- `commands/refine-issue.md:70-99` — all-categories issue locate shell pattern

**Test files:**
- `scripts/tests/test_outer_loop_eval.py:1-140` — structural test pattern for a specific loop YAML (exact model to follow)
- `scripts/tests/test_create_loop.py:35-56` — `tmp_path/.loops` fixture + `ll-loop validate` CLI invocation pattern
- `scripts/tests/test_builtin_loops.py:46-86` — `test_expected_loops_exist` registry (update only if harness ships as built-in)
- `scripts/tests/test_fsm_schema.py:1-78` — `FSMLoop`, `load_and_validate`, `validate_fsm` import helpers
- `scripts/tests/test_issues_cli.py` — existing `ll-issues` CLI tests for reference

## Implementation Steps

1. Read `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (already loaded) and `docs/guides/LOOPS_GUIDE.md` to understand required YAML structure for `check_skill` harnesses
2. Create `skills/create-eval-from-issues/SKILL.md` with skill metadata
3. Implement the prompt/instruction file that drives:
   - Issue file resolution (via `ll-issues show <ID>`)
   - Context extraction (title, use case, proposed solution, acceptance criteria)
   - Criteria synthesis into `llm_structured` evaluation prompt
   - Variant A vs Variant B selection based on issue count
   - YAML generation and `ll-loop validate` call
4. Register in `commands/create-eval-from-issues.md` and `plugin.json`
5. Add a reference from `AUTOMATIC_HARNESSING_GUIDE.md` → "See also: `/ll:create-eval-from-issues`"
6. Write tests for the YAML generation logic

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete references for each step:

1. **Harness guide already understood** — `harness-single-shot.yaml` uses `initial: execute`, `max_iterations: 5`, `timeout: 3600`; `harness-multi-item.yaml` uses `initial: discover`, `max_iterations: 200`, `timeout: 14400`; both include `import: [lib/common.yaml]`
2. **Create `skills/create-eval-from-issues/SKILL.md`** — copy frontmatter from `skills/create-loop/SKILL.md:1-8`; add `arguments` block from `skills/manage-issue/SKILL.md:8-21`; `allowed-tools` should include `Bash(ll-issues:*, ll-loop:*, mkdir:*, test:*)`; no separate `prompt.md` — `SKILL.md` is both metadata and full instruction body
3. **Implement prompt body**:
   - Issue resolution: `ll-issues show <ID> --json` → parse `path` field; handles open and completed IDs via `_resolve_issue_id()` at `show.py:17`
   - `check_skill` state: model exactly from `harness-multi-item.yaml:118-134` — fields: `action`, `action_type: prompt`, `timeout`, `evaluate.type: llm_structured`, `evaluate.prompt`, `on_yes`, `on_no`
   - Save sequence: follow `skills/create-loop/SKILL.md:174-208` — `mkdir -p .loops/`, check existing, Write tool, then `ll-loop validate <slug>`
   - Session log: `ll-issues append-log <issue-file> /ll:create-eval-from-issues` (see `commands/refine-issue.md:385-395`)
4. **No `commands/create-eval-from-issues.md` needed** — `"skills": ["./skills"]` in `plugin.json:20` auto-discovers all `skills/*/SKILL.md`; creating a commands/ file would create a duplicate `/ll:create-eval-from-issues` route
5. **Update `AUTOMATIC_HARNESSING_GUIDE.md`** — add "See also" link in the harness creation section
6. **Tests** — create `scripts/tests/test_create_eval_from_issues.py` modeled on `test_outer_loop_eval.py:1-140`:
   - `TestEvalHarnessVariantA` — 1 issue → `initial: execute`, has `check_skill` state with `llm_structured` evaluator
   - `TestEvalHarnessVariantB` — 2+ issues → `initial: discover`, has `discover` and `advance` states
   - `TestEvalHarnessValidation` — generated YAML passes `ll-loop validate` (follow `test_create_loop.py:35-56` tmp_path pattern)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `commands/help.md` — add `create-eval-from-issues` entry to AUTOMATION & LOOPS section (~line 149–158) and quick reference table (~line 244–251)
8. Update `docs/reference/COMMANDS.md` — add command reference entry for `/ll:create-eval-from-issues`
9. Update `.claude/CLAUDE.md:38,56` — bump skill count from 24 to 25; add `create-eval-from-issues`^ to the Automation & Loops listing in Commands & Skills section
10. Run `ll-verify-docs --fix` — auto-updates skill counts in `README.md:89`, `CONTRIBUTING.md:125`, `docs/ARCHITECTURE.md:26,99`
11. Manually add `create-eval-from-issues/` to directory listings in `README.md:206-231` (skills table), `CONTRIBUTING.md:126-147` (directory tree), and `docs/ARCHITECTURE.md:100-155` (skill listing)

## Impact

- **Priority**: P3 — Useful workflow accelerator; not blocking anything current
- **Effort**: Medium — Requires issue parsing logic, criteria synthesis prompt, and YAML templating; no new infrastructure
- **Risk**: Low — Read-only issue parsing + file write; no destructive operations
- **Breaking Change**: No

## API/Interface

```bash
# Single issue → single-shot harness
/ll:create-eval-from-issues FEAT-919

# Multiple issues → multi-item harness
/ll:create-eval-from-issues FEAT-919 ENH-950

# Completed issue (harness to verify regression doesn't recur)
/ll:create-eval-from-issues BUG-347
```

Output file written to: `.loops/eval-harness-<slug>.yaml`

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Harness YAML structure, `check_skill` phase spec, evaluation pipeline |
| `docs/guides/LOOPS_GUIDE.md` | FSM field reference, evaluator catalog |
| `scripts/little_loops/loops/harness-single-shot.yaml` | Template for Variant A output |
| `scripts/little_loops/loops/harness-multi-item.yaml` | Template for Variant B output |

## Labels

`feature`, `loops`, `harness`, `eval`, `captured`

## Status

**Open** | Created: 2026-04-04 | Priority: P3

---

## Session Log
- `/ll:confidence-check` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5687071-7876-4a35-b7e9-92c5939ccb33.jsonl`
- `/ll:wire-issue` - 2026-04-05T23:43:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc42f8b7-ff6d-415c-84bd-3f5e4acbdf99.jsonl`
- `/ll:refine-issue` - 2026-04-05T23:31:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6ae4919-971a-4b3a-a67d-3ca5428504f5.jsonl`
- `/ll:format-issue` - 2026-04-05T23:24:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80483a00-b614-43e6-8ba2-461cc77fadae.jsonl`
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdd75d9a-15c4-4632-b6fd-adac60caf156.jsonl`
