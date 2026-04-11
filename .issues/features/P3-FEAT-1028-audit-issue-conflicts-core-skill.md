---
discovered_date: 2026-04-10
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 85
parent_issue: FEAT-1027
blocks: FEAT-1029
---

# FEAT-1028: audit-issue-conflicts — Core Skill Implementation

## Summary

Create `skills/audit-issue-conflicts/SKILL.md` — the primary skill file implementing conflict detection, recommendation synthesis, interactive approval loop, and `--auto`/`--dry-run` modes.

## Parent Issue

Decomposed from FEAT-1027: Issue Conflict Audit Skill with Auto-Apply

## Current Behavior

No skill file exists at `skills/audit-issue-conflicts/SKILL.md`. The skill cannot be invoked.

## Expected Behavior

Running `/ll:audit-issue-conflicts` will:
1. Load and analyze all open issues (bugs/, features/, enhancements/)
2. Detect conflicts across: requirements, objectives, architectural decisions, and scope overlap
3. Synthesize findings into a conflict report with recommended changes (merge, close, update, reorder)
4. In interactive mode: present recommendations and ask for user approval before applying
5. With `--auto` flag: skip approval and directly apply all recommended changes
6. With `--dry-run` flag: output the conflict report without modifying any issue files

## Use Case

**Who**: Developer managing a project backlog in little-loops

**Context**: After accumulating many issues across bugs, features, and enhancements, the developer wants to sanity-check the backlog before a sprint planning session to ensure no issues conflict, duplicate work, or have incompatible architectural decisions.

**Goal**: Run `/ll:audit-issue-conflicts` to get a ranked list of conflicting or overlapping issues with recommended resolutions (merge, deprecate, split, add dependency).

**Outcome**: The developer reviews the conflict report, approves recommended changes interactively (or uses `--auto` for unattended cleanup), and ends with a cleaner, more consistent backlog.

## Acceptance Criteria

- [ ] `skills/audit-issue-conflicts/SKILL.md` exists and is auto-discovered via `"skills": ["./skills"]` in `.claude-plugin/plugin.json`
- [ ] Loads all open issues from `{{config.issues.base_dir}}/{bugs,features,enhancements}/*.md`
- [ ] Detects all four conflict types: requirement, objective, architecture, scope overlap
- [ ] Outputs conflict report ranked by severity (high/medium/low) with issue IDs and conflict descriptions
- [ ] In interactive mode, presents each recommendation with accept/reject prompt via `AskUserQuestion` before applying any changes
- [ ] With `--auto` flag, applies all recommendations without prompting
- [ ] With `--dry-run` flag, outputs report without modifying any issue files
- [ ] When no conflicts detected, outputs "No conflicts found" and exits with code 0
- [ ] Each recommendation includes: `conflict_type`, `severity`, `affected issue IDs`, `description`, `proposed_change`
- [ ] Session log entry appended to each modified issue file via `ll-issues append-log`

## Proposed Solution

### Frontmatter

Model directly from `skills/audit-claude-config/SKILL.md:1-19`:

```yaml
---
description: |
  Use when the user asks to audit issues for conflicts, detect conflicting requirements or objectives across open issues, find incompatible architecture decisions, or says "check my backlog for conflicts." Supports auto-apply and dry-run modes.

  Trigger keywords: "audit issue conflicts", "detect conflicts", "conflicting issues", "backlog conflicts", "incompatible issues", "conflict audit", "check for conflicts"
argument-hint: "[--auto] [--dry-run]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - Bash(git:*)
  - Bash(ll-issues:*)
arguments:
  - name: flags
    description: "Optional flags: --auto (apply all recommendations without prompting), --dry-run (report only, no changes)"
    required: false
---
```

### Flag Parsing

Use substring match on `$FLAGS` (pattern: `skills/wire-issue/SKILL.md:55-65`):
- Check `$DANGEROUSLY_SKIP_PERMISSIONS` first → `AUTO_MODE=true`
- Then `--auto` → `AUTO_MODE=true`
- Then `--dry-run` → `DRY_RUN=true`

### Issue Loading

Glob `{{config.issues.base_dir}}/{bugs,features,enhancements}/*.md`. Parse ID/type/priority from filename; extract Summary, Integration Map, Implementation Steps, Objectives sections from content.

### Conflict Detection Engine

Batch issues 3-5 at a time (pattern: `commands/tradeoff-review-issues.md:48-127`). Spawn all batch Task calls in a single message. Each task returns structured conflict records.

Conflict taxonomy:
- **Requirement conflicts**: Issue A requires X, Issue B requires not-X
- **Objective conflicts**: Two issues solve the same problem differently
- **Architecture conflicts**: Incompatible technical approaches (e.g., sync vs async, different data models)
- **Scope overlap**: Issues that partially duplicate each other

### Recommendation Synthesis

Aggregate all batch findings. Group by severity (high → medium → low). Output ranked conflict table.

### Interactive Approval Loop

Per-recommendation `AskUserQuestion` (pattern: `commands/tradeoff-review-issues.md:183-213`) with option shapes by recommendation type:
- **merge** (high/medium): "Yes, consolidate" / "No, keep separate" / "Add dependency instead"
- **deprecate** (any): "Yes, close this issue" / "No, keep active" / "Demote priority instead"
- **split** (medium): "Yes, note the split needed" / "No, keep as-is"
- **add_dependency** (low/medium): "Yes, add blocked_by frontmatter" / "No, skip"
- **update_scope** (low/medium): "Yes, append scope note" / "No, skip"

Skip entirely in `--auto` mode.

### Cleanup

After all approvals applied: `git add {{config.issues.base_dir}}/` in one shot (pattern: `commands/tradeoff-review-issues.md:300-303`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**1. Frontmatter correction — `AskUserQuestion` and `model: sonnet` missing**

The proposed frontmatter lists `allowed-tools` without `AskUserQuestion`. Skills using it in interactive mode must list it explicitly (pattern: `skills/go-no-go/SKILL.md:1-18`, `skills/wire-issue/SKILL.md:1-18`). Also add `model: sonnet` as used by `go-no-go`, `map-dependencies`, and `wire-issue`:

```yaml
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - AskUserQuestion
  - Bash(git:*)
  - Bash(ll-issues:*)
```

**2. Issue loading — exact bash pattern**

Use this pattern from `skills/confidence-check/SKILL.md:112-127` (also `skills/format-issue/SKILL.md:115-131`):

```bash
declare -a ISSUE_FILES
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        while IFS= read -r file; do
            ISSUE_FILES+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | sort)
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found"
    exit 0
fi
echo "Found ${#ISSUE_FILES[@]} active issues to evaluate"
```

**3. AskUserQuestion — exact YAML shapes per recommendation type**

Pattern from `commands/tradeoff-review-issues.md:184-213` and `skills/review-loop/SKILL.md:313-325`:

```yaml
# merge / deprecate recommendation
questions:
  - question: "Conflict [SEVERITY]: [ISSUE-A] vs [ISSUE-B] — [brief description]. Apply recommendation?"
    header: "[ISSUE-A] vs [ISSUE-B]"
    multiSelect: false
    options:
      - label: "Yes, apply — [proposed_change summary]"
        description: "[specific action, e.g., merge scope into ISSUE-A, close ISSUE-B]"
      - label: "No, keep both as-is"
        description: "Leave both issues unchanged"
      - label: "Add dependency instead"
        description: "Add blocked_by frontmatter to link them"

# add_dependency recommendation
questions:
  - question: "Add blocked_by link: [ISSUE-A] depends on [ISSUE-B]?"
    header: "[ISSUE-A]"
    multiSelect: false
    options:
      - label: "Yes, add blocked_by frontmatter"
        description: "Appends blocked_by: [ISSUE-B] to [ISSUE-A] frontmatter"
      - label: "No, skip"
        description: "Leave both issues unchanged"
```

**4. `overlap_detector.py` — unrelated module, do not confuse**

`scripts/little_loops/parallel/overlap_detector.py` exists and performs _file-modification_ overlap detection for parallel processing safety (tracks which files each in-flight issue will touch). This is categorically different from the semantic/requirement conflict detection this skill performs. Do not reference or reuse it in the new skill.

**5. `## Configuration` section required in skill body**

All skills using `{{config.issues.base_dir}}` include a `## Configuration` section immediately after the frontmatter (pattern: `skills/format-issue/SKILL.md:25-31`, `skills/capture-issue/SKILL.md:26-33`). Add this as the first body section:

```markdown
## Configuration

This skill uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`
```

**6. `ll-issues append-log` — per modified file, then one `git add`**

Call `ll-issues append-log <path> /ll:audit-issue-conflicts` for _each_ issue file modified (pattern: `commands/tradeoff-review-issues.md:254`, `skills/wire-issue/SKILL.md:367`). After all per-file log appends, stage everything with a single `git add {{config.issues.base_dir}}/`.

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — **new file to create** (primary deliverable)

### Dependent Files (Callers/Importers)
- `.claude-plugin/plugin.json` — **no change needed**; `"skills": ["./skills"]` at line 20 auto-discovers all `skills/*/SKILL.md` files

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — **manual registration required** (hardcoded, not auto-discovered); skill listing at lines 44-80 (ISSUE REFINEMENT block) and line 254 (Quick Reference Table `**Issue Refinement**:`) needs `audit-issue-conflicts` added; handled in FEAT-1029 [Agent 1 finding]

### Similar Patterns
- `skills/audit-claude-config/SKILL.md` — audit pattern with severity-grouped findings, `--fix`/`--non-interactive` flags
- `commands/tradeoff-review-issues.md` — multi-issue LLM batch evaluation with per-recommendation `AskUserQuestion` approval loop
- `skills/wire-issue/SKILL.md:55-65` — flag parsing pattern

### Tests
- Covered in FEAT-1029 (wiring + tests)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_audit_issue_conflicts_skill.py` — **new file** (FEAT-1029 deliverable); 7 structural assertions against `skills/audit-issue-conflicts/SKILL.md`; follow `test_improve_claude_md_skill.py` pattern: use `PROJECT_ROOT = Path(__file__).parent.parent.parent` anchored path and guard every content assertion with `assert SKILL_FILE.exists()` before reading (FEAT-1029 stub uses relative path — must use absolute `PROJECT_ROOT`-anchored path instead) [Agent 3 finding]
- `scripts/tests/test_skill_expander.py` — existing; `TestResolveContentPath.test_finds_skill_md` at line 59 uses `tmp_path` isolation, unaffected by the new skill file [Agent 3 finding]
- `ll-verify-docs` will surface a count mismatch (actual=26 vs documented=25) the moment the skill file is created — this is not a pytest failure but a CLI gate enforced by `scripts/little_loops/doc_counts.py` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

All locations below are FEAT-1029's implementation scope, but FEAT-1028's deliverable triggers each of them. Two entries are **gaps in FEAT-1029's current wiring spec** and must be added to FEAT-1029.

- `commands/help.md:44-80` — ISSUE REFINEMENT block; add `/ll:audit-issue-conflicts` entry (manual — not auto-discovered) [Agent 1 finding]
- `commands/help.md:254` — Quick Reference Table `**Issue Refinement**:` list; add `audit-issue-conflicts` [Agent 1 finding]
- `README.md:89` — `**25 skills**` count; bump to `**26 skills**` [Agent 2 finding]
- `README.md:108-123` — Issue Refinement table; add row for `audit-issue-conflicts` [Agent 2 finding]
- `README.md:207-235` — Skills table; add row _(gap: not in FEAT-1029's wiring spec)_ [Agent 2 finding]
- `CONTRIBUTING.md:125` — `25 skill definitions`; bump to `26` [Agent 2 finding]
- `CONTRIBUTING.md:128-129` — skills directory tree; insert `audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` [Agent 2 finding]
- `docs/ARCHITECTURE.md:26` — mermaid `SKL[Skills<br/>25 composable skills]`; bump to `26` [Agent 2 finding]
- `docs/ARCHITECTURE.md:99` — `# 25 skill definitions`; bump to `26` [Agent 2 finding]
- `docs/ARCHITECTURE.md:104-107` — skills directory listing; insert `audit-issue-conflicts/` entry [Agent 2 finding]
- `docs/reference/COMMANDS.md:14` — `--dry-run` consumer list; add `audit-issue-conflicts` [Agent 2 finding]
- `docs/reference/COMMANDS.md:15` — `--auto` consumer list; add `audit-issue-conflicts` [Agent 2 finding]
- `docs/reference/COMMANDS.md:~204` — add `### /ll:audit-issue-conflicts` subsection after `/ll:tradeoff-review-issues` [Agent 2 finding]
- `docs/reference/COMMANDS.md:584-641` — Quick Reference Table; add row _(gap: not in FEAT-1029's wiring spec)_ [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:484` — "Plan a Feature Sprint" recipe; insert `/ll:audit-issue-conflicts` step before `/ll:tradeoff-review-issues` [Agent 2 finding]
- `.claude/CLAUDE.md:52` — `**Issue Refinement**:` list; add `audit-issue-conflicts`^ [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/doc_counts.py:12-16` — defines `DOC_FILES = ["README.md", "CONTRIBUTING.md", "docs/ARCHITECTURE.md"]`; globs actual `skills/**/SKILL.md` count at runtime; will report a mismatch (actual=26 vs documented=25) the moment `skills/audit-issue-conflicts/SKILL.md` is created, until FEAT-1029's doc count updates are applied [Agent 2 finding]

## Implementation Steps

1. **Define skill frontmatter** — copy template above into `skills/audit-issue-conflicts/SKILL.md`
2. **Write flag parsing section** — check `$DANGEROUSLY_SKIP_PERMISSIONS`, then `--auto`, `--dry-run` via substring match
3. **Write issue loading section** — glob all three active issue dirs; parse ID/type/priority/title from filename; read content
4. **Write conflict detection section** — batch 3-5 issues per Task call; parallel spawn; structured output per batch
5. **Write recommendation synthesis + report** — aggregate; group by severity; output ranked table
6. **Write interactive approval loop** — per-type `AskUserQuestion` shapes; skip in `--auto` mode; no-op in `--dry-run` mode
7. **Write "no conflicts" path** — detect empty findings; output `"No conflicts found"` and exit 0
8. **Write session log + git cleanup** — `ll-issues append-log` per modified file; `git add {{config.issues.base_dir}}/` at end

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Ensure `skills/audit-issue-conflicts/` directory is created (the directory itself, not just the SKILL.md) — plugin auto-discovery requires the directory to exist
10. Run `ll-verify-docs` after FEAT-1028 is complete to confirm the expected count mismatch (actual=26, documented=25) — this is the gate FEAT-1029 resolves
11. Note for FEAT-1029 implementer: 2 doc locations are **missing from FEAT-1029's current wiring spec** — add them: `README.md:207-235` (Skills table) and `docs/reference/COMMANDS.md:584-641` (Quick Reference Table)

## API/Interface

```
/ll:audit-issue-conflicts          # interactive mode
/ll:audit-issue-conflicts --auto   # auto-apply all recommendations
/ll:audit-issue-conflicts --dry-run  # report only, no changes
```

Recommendation object structure:
```python
{
  "conflict_type": "objective",  # requirement | objective | architecture | scope
  "severity": "medium",          # low | medium | high
  "issues": ["FEAT-100", "FEAT-200"],
  "description": "Both issues implement caching but use incompatible backends",
  "recommendation": "merge",     # merge | deprecate | split | add_dependency | update_scope
  "proposed_change": "Close FEAT-200, add its scope to FEAT-100"
}
```

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Medium - New skill markdown file with LLM-based analysis
- **Risk**: Low - Read-heavy; `--auto` mode is the only write risk surface
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `skill`

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db48a35e-dc5e-4578-b3f1-212165c748a3.jsonl`
- `/ll:wire-issue` - 2026-04-11T04:54:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc02110f-791b-4d28-8939-9cbe80285b23.jsonl`
- `/ll:refine-issue` - 2026-04-11T04:48:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c055bc82-6b32-4f45-9a62-42ac720066fa.jsonl`
- `/ll:format-issue` - 2026-04-11T04:44:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac0f5055-ba7b-4abd-b883-79aeb90e1531.jsonl`
- `/ll:issue-size-review` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1583f95-f6e7-426b-b174-369fd745725e.jsonl`
