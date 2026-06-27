---
id: FEAT-2338
title: create-epics-from-unparented skill
type: FEAT
priority: P3
status: open
captured_at: '2026-06-27T01:47:26Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-2338: create-epics-from-unparented skill

## Summary

Add a new `/ll:create-epics-from-unparented` skill (or an `--create` flag on `/ll:link-epics`) that clusters orphaned issues by thematic similarity and proposes new EPIC definitions to cover them — the inverse operation of `/ll:link-epics`. The current `/ll:link-epics` skill only links unparented issues to **existing** EPICs; when no EPICs exist yet (or when orphaned issues don't fit any existing EPIC), users have no guided way to synthesize EPICs from the orphan pool.

## Current Behavior

`/ll:link-epics` discovers open issues without a `parent:` field, scores each against **existing** open EPICs via Jaccard similarity, and proposes assignments. If no open EPICs exist, it stops with:

```
No open EPICs found. Create an EPIC first, then run /ll:link-epics again.
```

There is no skill that goes the other direction — clustering unparented issues by theme and drafting new EPIC files for them.

## Expected Behavior

A new skill (e.g. `/ll:create-epics-from-unparented`) that:

1. Discovers all open BUG/FEAT/ENH issues without a `parent:` field (same orphan detection as `/ll:link-epics` Step 3).
2. Clusters them by Jaccard similarity into thematic groups.
3. For each cluster above a minimum-size threshold (e.g. ≥ 2 issues), proposes an EPIC title and summary derived from the cluster's shared vocabulary.
4. Presents proposals via `AskUserQuestion` (multi-select) — user picks which EPICs to create.
5. For accepted proposals: creates a new EPIC file (via `ll-issues next-id`), writes `parent:` back to each child, and updates the EPIC's `## Children` section — mirroring the write-back logic in `/ll:link-epics` Step 6.
6. Lone issues that don't cluster with anything are surfaced as singletons the user can optionally wrap in a single-child EPIC or leave unparented.

## Motivation

`/ll:link-epics` and this new skill form a complete "organize your backlog" pair:
- **link-epics**: orphans → existing EPICs
- **create-epics-from-unparented**: orphans → new EPICs

Without both, a project starting from scratch (no EPICs yet) has no guided workflow for promoting clusters of related issues into coordination EPICs. The user must manually draft every EPIC before any linking can happen.

## Use Case

A project has 40 open issues accumulated from `/ll:scan-codebase` with no EPICs. The user runs `/ll:create-epics-from-unparented` and is presented with five proposed EPICs derived from the natural clusters: "CLI UX", "Issue Format v2", "Loop Harness Quality", "Host Compatibility", and "Release Tooling". They accept three, reject two, and the skill creates the EPIC files, links the children, and stages everything for commit.

## Acceptance Criteria

1. `/ll:create-epics-from-unparented` skill file exists at `skills/create-epics-from-unparented/SKILL.md` and is invocable via Claude Code.
2. Running the skill discovers all open BUG/FEAT/ENH issues without a `parent:` field (same orphan detection as `/ll:link-epics`).
3. Issues are clustered by Jaccard similarity; pairs below `--min-score` (default: 0.3) are not merged into a cluster.
4. Clusters with fewer than `--min-cluster` (default: 2) issues are treated as singletons and surfaced separately.
5. EPIC proposals are presented via `AskUserQuestion` (multi-select); user can accept any subset including none.
6. For each accepted proposal: a new EPIC file is created via `ll-issues next-id`, `parent:` is written back to each child issue, and the EPIC's `## Children` section is populated — mirroring the write-back logic of `/ll:link-epics`.
7. Singleton issues are surfaced separately with the option to wrap in a single-child EPIC or leave unparented.
8. `skills/link-epics/SKILL.md` Usage Examples section is updated to reference the new sister skill.
9. `.claude/CLAUDE.md` Issue Discovery command list includes `create-epics-from-unparented`^.

## Proposed Solution

**Option A — standalone skill `create-epics-from-unparented`**

> **Selected:** Option A — standalone skill — all inverse operations in the codebase use standalone sister skills; no precedent for dual-direction flags, and Option B risks the 500-line ceiling and requires expanding link-epics' allowed-tools.

Mirrors the structure of `skills/link-epics/SKILL.md` but in reverse:
- Step 1: Parse args (`--auto`, `--min-cluster 2`, `--min-score 0.3`)
- Step 2: Discover orphaned issues (same as link-epics Step 3)
- Step 3: Cluster via greedy Jaccard merge (issues with pairwise score ≥ threshold go into the same cluster)
- Step 4: Synthesize EPIC title + summary from each cluster's top shared terms + existing titles
- Step 5: Present proposals via `AskUserQuestion`
- Step 6: Create accepted EPICs (`ll-issues next-id`, write file, write-back `parent:` to children, update `## Children`)
- Step 7: Report + stage

**Option B — `--create` flag on `/ll:link-epics`**

Extend `link-epics` with `--create` to enter "propose new EPICs" mode after the "no existing EPICs" check. Simpler surface area, but conflates two operations in one skill.

Option A is recommended: cleaner separation of concerns, separate `argument-hint`, and the skill is independently invocable without confusion about which direction it operates.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option A — standalone skill `create-epics-from-unparented`

**Reasoning**: Every inverse/counterpart operation in this codebase uses standalone sister skills (verify-issue-loop/adversarial-verify-loop, scope-epic/review-epic) — no skill uses a flag to switch between two mutually exclusive inverse operations. Option B would require adding `Write` to link-epics' `allowed-tools`, risks breaching the 500-line `ll-verify-skills` ceiling (~296 + ~200 ≈ 490+ lines), and introduces the codebase's first dual-direction flag with no established precedent. Option A reuses orphan detection, Jaccard utilities, write-back logic (Steps 6a–6d), and the Codex bridge pattern directly from existing skills (reuse score 3/3 vs. 1/3).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (standalone skill) | 3/3 | 2/3 | 2/3 | 3/3 | 10/12 |
| Option B (--create flag) | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- **Option A**: All inverse operations in codebase use standalone sister skills; reuse score 3/3 — orphan detection, Jaccard scoring, write-back Steps 6a–6d, and Codex bridge are all direct copy-adapt from existing skills.
- **Option B**: Zero precedent for `--create` flag across all 67 skills; `Write` not in link-epics' `allowed-tools`; 500-line ceiling at risk; `--min-cluster` arg is meaningless in link mode.

## Integration Map

### Files to Modify
- `skills/link-epics/SKILL.md` — update Usage Examples to reference the new sister skill
- `.claude/CLAUDE.md` — add `create-epics-from-unparented`^ to Issue Discovery command list

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — update skill count (line 77: `**38 skills**` → `**39 skills**`)
- `CONTRIBUTING.md` — update count (line 122: `# 38 skill definitions` → `# 39 skill definitions`) and add `create-epics-from-unparented/` entry alphabetically in the explicit skills directory listing under "Project Structure"
- `docs/ARCHITECTURE.md` — update count in 2 places (line 26 flowchart TB: `38 composable skills` → `39`; line 111 directory tree: `# 38 skill definitions` → `# 39`) and add `create-epics-from-unparented/` subdirectory entry
- `docs/reference/COMMANDS.md` — add row for `create-epics-from-unparented`^ in the skill summary table (around lines 1010–1044)
- `commands/help.md` — add `create-epics-from-unparented` to the `ISSUE DISCOVERY` block and `## Quick Reference Table`

### New Files
- `skills/create-epics-from-unparented/SKILL.md` — skill definition
- `skills/create-epics-from-unparented/agents/openai.yaml` — Codex bridge (follow pattern from `skills/link-epics/agents/openai.yaml`)

### Dependent Files (Callers/Importers)
- N/A — skill-only change; no Python modules introduced, no existing callers to update

### Similar Patterns
- `skills/link-epics/SKILL.md` — primary pattern to mirror; the new skill is the inverse operation (orphans → new EPICs vs. orphans → existing EPICs)

### Tests
- No Python unit tests needed for skill logic (skill is LLM-instruction-only)
- Manual verification: run against a project with 10+ orphaned issues and no EPICs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` — add `DOC_STRINGS_PRESENT` entry asserting `create-epics-from-unparented` appears in `.claude/CLAUDE.md`; follow pattern of `review-epic`/`scope-epic` entries (lines 29–33) [update]
- `scripts/tests/test_wiring_guides_and_meta.py` — update count literal assertions: `"38 composable skills"` → `"39 composable skills"` and `"# 38 skill definitions"` → `"# 39 skill definitions"` [update]
- `scripts/tests/test_wiring_skills_and_commands.py` — add parametrized entries for `skills/create-epics-from-unparented/SKILL.md` and `skills/create-epics-from-unparented/agents/openai.yaml` file existence [update]
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` — auto-runs against new skill; will fail unless `name:`, `metadata.short-description:` (≤80 chars), and `agents/openai.yaml` are all present [auto-verified, no edit needed]
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit.test_all_skills_within_limit` — auto-runs against new skill; will fail if SKILL.md exceeds 500 lines [auto-verified, no edit needed]

### Documentation
- `docs/reference/API.md` — no changes (skill-only, no Python API surface)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-epic/SKILL.md` — optional: add companion hint in "no linked children" Next steps block: `• /ll:create-epics-from-unparented to propose new EPICs from unparented issues`
- `skills/capture-issue/SKILL.md` — optional: add new skill as upstream complement to `/ll:link-epics` in the Step 4 workflow note
- `skills/issue-workflow/SKILL.md` — optional: add `create-epics-from-unparented`^ to the Issue Refinement command table and command list

### Configuration
- N/A

## Implementation Steps

1. Create `skills/create-epics-from-unparented/SKILL.md` following the 7-step structure above (Option A).
2. Add Codex bridge at `skills/create-epics-from-unparented/agents/openai.yaml`.
3. Update `skills/link-epics/SKILL.md` Usage Examples section to mention the new skill.
4. Update `.claude/CLAUDE.md` Issue Discovery list.
5. Manually verify end-to-end on a project with orphaned issues.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update skill counts in documentation from `38` → `39`: `README.md` line 77, `CONTRIBUTING.md` line 122, `docs/ARCHITECTURE.md` lines 26 + 111; also add `create-epics-from-unparented/` to the explicit directory listings in `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`.
7. Add skill row to `docs/reference/COMMANDS.md` skill summary table.
8. Add skill to `commands/help.md` — `ISSUE DISCOVERY` block and `## Quick Reference Table`.
9. Update wiring tests: add `DOC_STRINGS_PRESENT` entry in `test_wiring_cli_registry.py`; update count literals (38 → 39) in `test_wiring_guides_and_meta.py`; add file-existence parametrized entries in `test_wiring_skills_and_commands.py`.
10. Run `ll-verify-docs` and `python -m pytest scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` to confirm all wiring checks pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### SKILL.md Frontmatter Template (mirror `skills/link-epics/SKILL.md` lines 1–21)

```yaml
---
name: create-epics-from-unparented
description: Cluster orphaned issues by thematic similarity and propose new EPIC definitions to cover them — the inverse of /ll:link-epics.
disable-model-invocation: true
argument-hint: "[--auto] [--min-cluster <n>] [--min-score <threshold>]"
model: sonnet
allowed-tools:
  - AskUserQuestion
  - Edit
  - Read
  - Write
  - Bash(ll-issues:*)
  - Bash(git:*)
arguments:
  - name: flags
    description: "--auto to create all clusters without prompting; --min-cluster 2 to set minimum issues per cluster; --min-score 0.3 to set Jaccard threshold"
    required: false
metadata:
  short-description: Cluster orphaned issues by similarity and propose new EPICs to cover them.
---
```

#### Orphan Discovery (verbatim from `skills/link-epics/SKILL.md` Step 3)

```bash
ll-issues list --status open --type BUG --json
ll-issues list --status open --type FEAT --json
ll-issues list --status open --type ENH --json
```

Filter: `orphans = [i for i in data if not i.get("parent")]`. Build score text: `title + " " + summary_text` (extract summary with `re.search(r"## Summary\n(.+?)(?=\n##|\Z)", content, re.DOTALL)`).

#### Jaccard Clustering Algorithm (greedy merge)

- Word extraction: lowercase, 3+ char alphabetic tokens, excluding the 28-word stop list from `skills/link-epics/SKILL.md` Step 4.
- Score: `|words_A ∩ words_B| / |words_A ∪ words_B|`; empty sets → 0.0.
- Greedy merge: iterate pairs sorted by descending score; if score ≥ `MIN_SCORE`, merge the lower-ID issue into the higher-ID issue's cluster.
- Clusters with `|members| < MIN_CLUSTER` are surfaced as singletons.

#### AskUserQuestion Multi-Select Label Format

Single question, `multiSelect: true`. One option per cluster:
```
label: "Cluster N → new EPIC \"<synthesized title>\" (K issues)"
description: "ISSUE-A, ISSUE-B, ISSUE-C — <shared terms>"
```

Sort by descending cluster size.

#### EPIC File Format to Generate

```yaml
---
id: EPIC-NNN          # from ll-issues next-id immediately before Write
title: <synthesized title>
type: EPIC
priority: P3          # inherit from most-common child priority
status: open
captured_at: "<date -u +"%Y-%m-%dT%H:%M:%SZ">"
discovered_date: <YYYY-MM-DD>
discovered_by: create-epics-from-unparented
relates_to: []        # populated in 6b write-back
---
```

Call `ll-issues next-id` **immediately before each Write** — never batch-allocate IDs upfront. If the PostToolUse hook reports the file was deleted (duplicate integer ID), call `ll-issues next-id` again and retry.

#### Write-Back Step Sequence (mirror `skills/link-epics/SKILL.md` Step 6a–6d)

- **6a**: `Edit` to insert `parent: EPIC-NNN` before the closing `---` of each child's frontmatter.
- **6b**: `Edit` to update `relates_to:` in the EPIC frontmatter — three-case branch (absent / empty `[]` / inline populated list).
- **6c**: `Edit` to append to `## Children` (or insert the section before `## Status` / end of file):
  ```
  - **CHILD_ID** — child issue title
  ```
- **6d**: `git add "<child_path>"` + `git add "<epic_path>"` per explicit path — never `git add .issues/` (sweeps unrelated files; see BUG-1976).

#### Codex Bridge Format (follow `skills/link-epics/agents/openai.yaml`)

```yaml
interface:
  display_name: "Create Epics from Unparented"
  short_description: "Cluster orphaned issues by Jaccard similarity and propose new EPIC definitions."
```

## Impact

- **Priority**: P3 — Useful for backlog organization but non-blocking; users can manually create EPICs before running `/ll:link-epics`.
- **Effort**: Medium — Mirrors the 7-step link-epics skill structure with added clustering logic and EPIC file creation; no Python code changes.
- **Risk**: Low — New files only; no modifications to existing Python logic or APIs; skill-only surface.
- **Breaking Change**: No

## Labels

`skills`, `issue-management`, `epics`, `backlog-organization`

## Session Log
- `/ll:confidence-check` - 2026-06-27T03:00:00 - `96ae5770-0ec2-48fd-992a-05dd5658edf0.jsonl`
- `/ll:wire-issue` - 2026-06-27T02:22:59 - `c1277e67-74f1-489b-b65b-3a42430f1289.jsonl`
- `/ll:decide-issue` - 2026-06-27T02:08:18 - `f8198fd5-0d5d-4335-952f-f7c46090643f.jsonl`
- `/ll:refine-issue` - 2026-06-27T01:58:14 - `ecb4de22-fc6c-4d9c-a3ff-59ffe4dd546e.jsonl`
- `/ll:format-issue` - 2026-06-27T01:50:38 - `187c77f9-2ea8-4a5a-9945-69c2d38afc96.jsonl`
- `/ll:capture-issue` - 2026-06-27T01:47:26Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

## Status

- [ ] Implementation started
