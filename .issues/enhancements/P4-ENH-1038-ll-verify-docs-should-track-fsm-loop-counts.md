---
discovered_commit: 958a2a63
discovered_branch: main
discovered_date: 2026-04-11 00:00:00+00:00
discovered_by: audit-docs
doc_file: scripts/little_loops/doc_counts.py
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-05-17T12:43:03Z
status: done
---

# ENH-1038: ll-verify-docs should track FSM loop counts

## Summary

Documentation count found by `/ll:audit-docs`. `ll-verify-docs` (via `doc_counts.py`) only tracks commands, agents, and skills counts. FSM loop counts documented in README.md went stale (37 documented vs 38 actual) and were not caught by `ll-verify-docs`.

## Location

- **File**: `scripts/little_loops/doc_counts.py`
- **Section**: `COUNT_TARGETS` dict

## Current Content

```python
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
}
```

## Problem

FSM loop count (documented in README.md as "37 FSM loops") is not tracked by `ll-verify-docs`. A new loop was added without updating the README count, and the mismatch went undetected until a manual audit.

## Expected Content

Add a loop count target to `COUNT_TARGETS` pointing at the top-level YAML files in `scripts/little_loops/loops/` (excluding `lib/` subdirectory, `oracles/` subdirectory, and `README.md`):

```python
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
    "loops": ("scripts/little_loops/loops", "*.yaml"),  # top-level only, not recursive
}
```

The README pattern to match would be `\d+\s+FSM loops?`. The `extract_count_from_line` function may need updating to handle the "FSM loops" phrasing since "loops" is not already a tracked category.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`extract_count_from_line` — No Changes Needed**

The existing else-branch at `doc_counts.py:107` produces `r"(\d+)\s+\w*\s*loops"` for category `"loops"`, which already matches "49 FSM loops" (`\w*` captures "FSM"). Similarly, `fix_counts()` at `doc_counts.py:357` already handles the generic else-branch. Neither function requires modification.

**The real problem**: `count_files()` at `doc_counts.py:82` uses `dir_path.rglob(pattern)`, which descends into `lib/` and `oracles/` subdirectories. Adding `"loops": ("scripts/little_loops/loops", "*.yaml")` as-is would over-count (top-level + subdirs). Two approaches:

---

### Option A: Add `recursive` parameter to `count_files()` (targeted, backward-compatible)

Extend `count_files()` signature with `recursive: bool = True` and update `COUNT_TARGETS` iteration in `verify_documentation()` to support an optional 3rd tuple element:

```python
# count_files updated signature (doc_counts.py:64)
def count_files(directory: str, pattern: str, base_dir: Path | None = None, recursive: bool = True) -> int:
    ...
    return len(list(dir_path.rglob(pattern) if recursive else dir_path.glob(pattern)))

# COUNT_TARGETS with 3-tuple for loops (doc_counts.py:22-26)
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
    "loops": ("scripts/little_loops/loops", "*.yaml", False),  # top-level only
}

# verify_documentation() iteration updated (doc_counts.py:130-131)
for category, target_spec in COUNT_TARGETS.items():
    directory, pattern = target_spec[0], target_spec[1]
    recursive = target_spec[2] if len(target_spec) > 2 else True
    actual_counts[category] = count_files(directory, pattern, base_dir, recursive)
```

### Option B: Switch `count_files()` from `rglob` to `glob` globally (simpler)

> **Selected:** Option B (global glob switch) — already the established pattern in 4+ call sites; aligns `count_files()` with the rest of the codebase and requires no new parameters or tuple extension.

Since no current COUNT_TARGETS entry uses deeply nested directories, switching to non-recursive `glob` is safe for all existing entries. Update the skills pattern from `"SKILL.md"` to `"*/SKILL.md"`:

```python
# count_files uses glob (non-recursive) always (doc_counts.py:82)
return len(list(dir_path.glob(pattern)))

# COUNT_TARGETS — skills pattern updated, loops added (doc_counts.py:22-26)
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "*/SKILL.md"),  # explicit one-level; same files, no behavior change
    "loops": ("scripts/little_loops/loops", "*.yaml"),
}
```

**Trade-off**: Option A is explicit about recursion intent and backward-compatible. Option B is simpler (no new parameters, no tuple extension) but implicitly changes the existing glob strategy.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-17.

**Selected**: Option B (global glob switch)

**Reasoning**: `glob("*/SKILL.md")` is already used in four places in the same codebase (`doc_counts.py:298`, `adapt_skills_for_codex.py:118`, `action.py:54`, `generate_skill_descriptions.py:95`), and `glob("*.yaml")` is the established pattern for top-level loop listing in `info.py:109` and `info.py:117`. Option B removes the sole outlier (`rglob("SKILL.md")` in `count_files()`) and requires no new parameters or tuple structure. The only concrete downside is one test (`test_count_skills_with_subdirs`) that needs its pattern argument updated from `"SKILL.md"` to `"*/SKILL.md"` — a trivial, documented fix.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (recursive param) | 2/3 | 2/3 | 2/3 | 3/3 | 9/12 |
| Option B (global glob) | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `bool=True` default pattern is pervasive but variable-length config tuples are not established; fully backward-compatible with zero call-site changes.
- Option B: `glob("*/SKILL.md")` and `glob("*.yaml")` are the unanimously established patterns across 4+ sites; `rglob("SKILL.md")` in `count_files()` is the sole outlier that Option B corrects.

---

**Bridge skill filtering (both options)**: After resolving the SKILL.md paths, exclude bridge skills by checking file content — follow the `check_skill_budget()` pattern at `doc_counts.py:298-308`:

```python
BRIDGE_MARKER = "Bridged from `commands/"

# Filter inside count_files() or in a new count_skill_files() helper:
paths = [p for p in dir_path.glob("*/SKILL.md") if BRIDGE_MARKER not in p.read_text()]
```

The bridge marker string originates in `scripts/little_loops/cli/adapt_skills_for_codex.py:211`.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Choose Option A or B** for `count_files()` recursion (see Proposed Solution above)
2. **Add `"loops"` to `COUNT_TARGETS`** (`doc_counts.py:22-26`): `("scripts/little_loops/loops", "*.yaml")` with `False` recursion flag (Option A) or plain 2-tuple (Option B)
3. **Update `count_files()` or `COUNT_TARGETS` iteration** (`doc_counts.py:64-82`, `130-131`): implement the chosen option
4. **Add bridge skill filter** (`doc_counts.py`): before counting, skip `skills/*/SKILL.md` files whose body contains `"Bridged from \`commands/"` — reuse the `check_skill_budget()` pattern (lines 298-308)
5. **Add tests** (`scripts/tests/test_doc_counts.py`):
   - `TestCountFiles.test_count_loops_top_level_only`: create `loops/`, `loops/lib/extra.yaml`, `loops/oracles/extra.yaml`, verify only top-level YAMLs counted
   - `TestExtractCountFromLine`: verify `extract_count_from_line("49 FSM loops", "loops")` → `49` (no code change needed, just coverage)
   - `TestVerifyDocumentation`: end-to-end loops mismatch detection
   - `TestVerifyDocumentation.test_skills_excludes_bridge_skills`: bridge SKILL.md (containing marker) excluded from count
6. **Verify README** (`README.md:167`): actual top-level loop count is 49 as of 2026-05-17, matching the current documented value; run `ll-verify-docs` after implementation to confirm

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Update `docs/reference/API.md`** — in `## little_loops.doc_counts` section: (a) update the module-level description from "(commands, agents, skills)" to include "loops"; (b) update the `CountResult` dataclass category comment to include `"loops"`; (c) if Option A is chosen, add a `recursive: bool = True` parameter note to the `count_files` table entry
8. **Update `docs/reference/CLI.md`** — in the `### ll-verify-docs` section (~line 1294): update the one-line description from "(commands, agents, skills)" to include "loops"
9. **If Option B chosen, update `scripts/tests/test_doc_counts.py`** — fix `TestCountFiles.test_count_skills_with_subdirs` (line 33): change `count_files("skills", "SKILL.md", tmp_path)` to use `"*/SKILL.md"` pattern to match the updated `COUNT_TARGETS` skills entry

## Impact

- **Severity**: Low (count drift, not functional breakage)
- **Effort**: Small (add entry to COUNT_TARGETS, update regex matching)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `ll-verify-docs`, `auto-generated`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11; re-verified 2026-05-14

- `doc_counts.py:19-23` — `COUNT_TARGETS` confirmed: only `commands`, `agents`, `skills` keys; no `loops` key
- Feature not yet implemented
- **Loop count (2026-05-14)**: `scripts/little_loops/loops/*.yaml` (top-level only) = **42** files. README claims 47 — drift of 5. Continues to grow without `ll-verify-docs` tracking.

## Blocks

- ENH-977

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/doc_counts.py` — `COUNT_TARGETS` dict (lines 22-26); `count_files()` (lines 64-82) for non-recursive support; add bridge-skill content filter
- `docs/reference/API.md` — `## little_loops.doc_counts` section: update module description from "(commands, agents, skills)" to include "loops"; update `CountResult` category comment example to include `"loops"` [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-verify-docs` section (line ~1294): update description from "(commands, agents, skills)" to include "loops" [Agent 2 finding]

### Dependent Files (No Changes Needed)
- `scripts/little_loops/cli/docs.py:main_verify_docs()` — calls `verify_documentation()`, auto-picks up new COUNT_TARGETS entries
- `scripts/little_loops/cli/docs.py:fix_counts()` — `"loops"` category key handled by generic else-branch at line 357; `r"(\d+)(\s+\w*\s*loops)"` matches "49 FSM loops" correctly
- `scripts/little_loops/cli/__init__.py` — re-exports `main_verify_docs`, `main_verify_skill_budget`, `main_check_links` from `little_loops.cli.docs`; no changes needed [Agent 1 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — defines `ll-verify-docs = "little_loops.cli:main_verify_docs"` CLI entry point; no changes needed but confirms the full invocation chain [Agent 1 finding]
- `scripts/little_loops/loops/docs-sync.yaml` — FSM loop that calls `ll-verify-docs 2>&1` in its `verify_docs` state; will automatically benefit from loops tracking once implemented; no code changes needed [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:109` — uses non-recursive `glob("*.yaml")` on the same loops directory; confirms this is the established approach for top-level-only loop listing
- `scripts/little_loops/doc_counts.py:check_skill_budget()` (lines 298-308) — content-based filter pattern (read file, skip if flag set); replicate for bridge-marker check
- `scripts/little_loops/cli/adapt_skills_for_codex.py:211` — writes the bridge marker: `"Bridged from \`commands/{stem}.md\`"`

### Tests
- `scripts/tests/test_doc_counts.py` — add to existing test classes:
  - `TestCountFiles`: non-recursive loop counting (lib/ and oracles/ excluded)
  - `TestExtractCountFromLine`: `"loops"` key matches "49 FSM loops" phrasing
  - `TestVerifyDocumentation`: loops mismatch detection end-to-end; bridge skill exclusion from skill count
- `scripts/tests/test_cli_docs.py` — `TestMainVerifyDocs` mocks `verify_documentation` entirely; no changes needed, but review to confirm no assertions embed the category list (they do not) [Agent 1 + 2 finding]
- **Option B breakage warning**: if Option B (global `rglob` → `glob` switch) is chosen, `TestCountFiles.test_count_skills_with_subdirs` (line 33) will break — it currently passes because `rglob("SKILL.md")` finds files one level deep; Option B requires changing the test's pattern to `"*/SKILL.md"` to match the updated `COUNT_TARGETS` skills entry [Agent 3 finding]

### Documentation
- `README.md:167` — "49 FSM loops" line; actual count is 49 as of 2026-05-17 (currently accurate, but untracked)
- `docs/reference/API.md` — `## little_loops.doc_counts` section: module description says "(commands, agents, skills)"; `CountResult` category comment example needs "loops" added; if Option A chosen, `count_files` public API table entry needs updated signature [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-verify-docs` description (line ~1294) reads "(commands, agents, skills)"; update to include "loops" [Agent 2 finding]

## Status

**Open** | Created: 2026-04-11 | Priority: P4

## Audit Update — 2026-05-16 (`/ll:audit-docs`)

Two related miscounts surfaced again:

1. **FSM loops** — README.md was updated 2026-05-16 from `47 FSM loops` to `43 FSM loops` (actual top-level count in `scripts/little_loops/loops/*.yaml`). This is the recurring drift this issue exists to prevent. `ll-verify-docs` still does not catch it.

2. **Skills miscount (new sub-task)** — `ll-verify-docs` reports `skills: documented=30, actual=58` at `README.md:165`, `CONTRIBUTING.md:122`, `CONTRIBUTING.md:536`, `docs/ARCHITECTURE.md:26`, and `docs/ARCHITECTURE.md:112`. The documented `30` is correct: `skills/` contains 30 canonical skills + 28 Codex bridge skills (frontmatter body contains `Bridged from \`commands/...\``). `doc_counts.py` should exclude bridges when computing the skill count. Suggested implementation: filter out `SKILL.md` files whose body contains the literal `Bridged from \`commands/`. Without this, every doc that cites a real "30 skills" trips a false positive.

Both fixes live in the same module (`scripts/little_loops/doc_counts.py`) — bundle them in one PR.


## Session Log
- `/ll:manage-issue` - 2026-05-17T12:43:03Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-17T12:39:48 - `e8b4aab6-fa6d-4874-bad6-d507f50ab1dd.jsonl`
- `/ll:confidence-check` - 2026-05-17T13:00:00 - `39c7e9c3-3b31-476f-9814-26d819e8ca94.jsonl`
- `/ll:decide-issue` - 2026-05-17T12:34:48 - `55337b76-90b7-4e24-9b22-649abc2c5405.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00 - `34b269dc-aa27-435a-a6b8-79706e158b32.jsonl`
- `/ll:wire-issue` - 2026-05-17T12:29:49 - `51b9a3e4-e352-480c-a215-95e1a60c9429.jsonl`
- `/ll:refine-issue` - 2026-05-17T12:24:13 - `a3c6b55b-851a-4349-910a-b9b1ae4c2e69.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:04 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:06 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-977 (add `ll-verify-skills`) both modify `scripts/little_loops/doc_counts.py` and `scripts/little_loops/cli/docs.py`. Changes are additive in different sections (ENH-1038 adds to `COUNT_TARGETS`; ENH-977 adds `check_skill_sizes()` and `main_verify_skills()`), but they should be sequenced or merged to avoid conflicts in the same PR. Related: ENH-977.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): Both ENH-1038 and ENH-977 add new logic to `scripts/little_loops/doc_counts.py` without referencing each other. ENH-1038 adds a `loops` key to `COUNT_TARGETS` and extends `extract_count_from_line`; ENH-977 adds `check_skill_sizes()` to the same module. Implement ENH-1038 after ENH-977 lands (or coordinate PR order) to avoid merge conflicts in `doc_counts.py`. Cross-reference ENH-977 in the PR description when landing this change.
