---
id: FEAT-808
priority: P3
type: FEAT
status: open
title: "go-no-go skill for adversarial issue implementation assessment"
discovered_date: "2026-03-19"
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 90
---

# FEAT-808: go-no-go skill for adversarial issue implementation assessment

## Summary

Create a new `/ll:go-no-go` skill that evaluates whether an issue should be implemented by launching two isolated background agents to argue for and against, then using an impartial LLM-as-judge agent to deliver a final go/no-go determination with reasoning.

## Motivation

The existing `/ll:confidence-check` skill scores readiness and outcome confidence, but does not surface adversarial arguments or produce a binary decision. A go/no-go skill fills the gap between "this issue is well-understood" and "this issue is worth implementing right now" by forcing explicit pro and con research before a deterministic verdict is reached. This is especially valuable before committing sprint capacity to complex or ambiguous issues.

## Use Case

A developer is reviewing a sprint and wants to quickly validate whether FEAT-712 is worth picking up. They run `/ll:go-no-go FEAT-712`. Two background agents independently research the codebase and argue for/against the implementation. A judge agent weighs both arguments and outputs: **GO** — the feature aligns with existing patterns, has clear acceptance criteria, and low risk of regression. Or **NO-GO** with blocking reasons.

## Acceptance Criteria

- [ ] Skill accepts one or more comma-separated Issue IDs, a sprint name, or no argument (defaults to highest-priority open/active issue)
- [ ] Two isolated background agents are launched concurrently: one argues **for** implementation, one argues **against**
- [ ] Each agent performs real codebase research (file reads, grep, etc.) to ground its argument
- [ ] A third isolated background agent receives both arguments and acts as an impartial LLM-as-judge
- [ ] Judge produces a final **GO** or **NO-GO** verdict with structured reasoning
- [ ] Results are displayed clearly in the terminal with the verdict, key arguments from each side, and judge rationale
- [ ] When multiple issues are provided, each is evaluated independently and results are summarized in a table
- [ ] `--check` mode exits 0 on GO, exits 1 on NO-GO (enables FSM `evaluate: type: exit_code` gating)

## Implementation Steps

1. Create `skills/go-no-go/SKILL.md` following the existing skill structure (see `skills/confidence-check/SKILL.md` as reference)
2. Define argument structure: pro-agent prompt, con-agent prompt, judge prompt with both arguments as input — all as inline prompts within the SKILL.md (no separate agent files in `agents/`)
3. Implement issue resolution logic: parse args → resolve sprint name to issue list via `cat {{config.sprints.sprints_dir}}/<name>.yaml` → default to highest-priority open issue (P0→P5 loop over `{{config.issues.base_dir}}/{bugs,features,enhancements}/`)
4. Use `Agent` tool with `run_in_background: true` and `isolation: "worktree"` for the two adversarial agents; launch both in a SINGLE message
5. Collect outputs from both background agents when notified of completion
6. Launch judge agent (inline prompt) with both argument texts injected as context
7. Format and display the verdict using the `=` separator line convention
8. Add `--check` mode: exits 0 on GO, exits 1 on NO-GO (follow `skills/confidence-check/SKILL.md:466-478` pattern)
9. Register in `.claude-plugin/plugin.json`: **no per-skill entry needed** — adding `skills/go-no-go/` directory is sufficient (plugin scans `./skills/` directory automatically per `.claude-plugin/plugin.json:20`)
10. Add to `CLAUDE.md` command catalog: add `` `go-no-go`^ `` to the "Planning & Implementation" category line; increment "18 skills" count to "19 skills" at line 38

## API/Interface

```
/ll:go-no-go [<issue-id>[,<issue-id>...] | <sprint-name>]
```

**Examples:**
```bash
/ll:go-no-go                      # evaluate highest-priority open issue
/ll:go-no-go FEAT-808             # evaluate single issue
/ll:go-no-go FEAT-808,ENH-712     # evaluate multiple issues
/ll:go-no-go sprint-2026-Q1       # evaluate all issues in named sprint
```

**Output format:**
```
## Go/No-Go: FEAT-808

### For (Pro-Implementation)
[argument summary from pro agent]

### Against (Con-Implementation)
[argument summary from con agent]

### Judge Verdict: GO ✓ / NO-GO ✗
[judge reasoning]
```

## Integration Map

### Files to Create
- `skills/go-no-go/SKILL.md` — the new skill (primary deliverable)

### Files to Modify
- `.claude/CLAUDE.md:38` — increment "18 skills" → "19 skills"
- `.claude/CLAUDE.md:53` — add `` `go-no-go`^ `` to "Planning & Implementation" category

### Dependent Files (No Modification Needed)
- `.claude-plugin/plugin.json:20` — skill auto-discovered via `"./skills"` directory scan; no per-skill entry required

### Reference Patterns
- `skills/confidence-check/SKILL.md:1-18` — frontmatter template (`description`, `model`, `allowed-tools`)
- `skills/confidence-check/SKILL.md:36-70` — argument parsing bash pseudocode (flag detection, token loop, `$ARGUMENTS`)
- `skills/confidence-check/SKILL.md:86-101` — issue file resolution via `find | grep -E "[-_]${ISSUE_ID}[-_.]"`
- `skills/manage-issue/SKILL.md:77-84` — highest-priority default (P0→P5 loop with `ls $P-*.md | head -1`)
- `skills/confidence-check/SKILL.md:466-478` — `--check` mode exit-code pattern
- `skills/confidence-check/SKILL.md:483-525` — verdict output format with `=` separator lines
- `skills/confidence-check/SKILL.md:549-556` — batch result table format (when multiple issues)
- `skills/confidence-check/SKILL.md:447-453` — session log append pattern
- `skills/confidence-check/SKILL.md:43-44` — `--dangerously-skip-permissions` auto-mode detection

### Sprint Resolution (from a skill)
Sprint name → issue list: `cat {{config.sprints.sprints_dir}}/<sprint-name>.yaml` and parse the `issues:` YAML list (format: `scripts/little_loops/sprint.py:187-203`). No `ll-sprint` subcommand outputs this list as JSON.

### Tests That May Need Updating
- `scripts/tests/test_doc_counts.py` — verifies documented skill counts match actual file counts; will fail after adding the new skill directory if counts aren't updated in `CLAUDE.md`

## Related Files

- `skills/confidence-check/SKILL.md` — reference implementation for skill structure, argument parsing, output format, --check mode
- `.claude-plugin/plugin.json` — skill auto-registration (directory scan, no per-skill entry needed)
- `.claude/CLAUDE.md` — command catalog entry (line 38 count, line 53 category list)

## Session Log
- `/ll:refine-issue` - 2026-03-19T03:23:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe93df18-9bd8-4ea2-b803-eb08b9798bc3.jsonl`
- `/ll:capture-issue` - 2026-03-19T03:10:22Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e62307c-bbbf-4088-99bc-a42ef930c75f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2bce9f8b-7339-49ed-88ba-ffe6b245d592.jsonl`
