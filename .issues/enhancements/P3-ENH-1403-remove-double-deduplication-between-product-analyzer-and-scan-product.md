---
discovered_date: 2026-05-09
discovered_by: audit
blocked_by: []
decision_needed: false
confidence_score: 100
outcome_confidence: 81
score_complexity: 21
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-11T09:41:29Z
status: done
---

# ENH-1403: Remove double-deduplication between product-analyzer and scan-product

## Summary

Both `skills/product-analyzer/SKILL.md` (Section 6) and `commands/scan-product.md` (Step 5.2) perform deduplication against existing `.issues/` files. This produces inconsistent `skipped` counts in the final report and wastes token budget reading issue files twice.

Additionally, `scan-product` reads `.ll/ll-goals.md` independently (Step 2) and then injects `GOALS_CONTENT` into the skill prompt — but the skill also reads the goals file in its own Section 2. This is a redundant read that could produce inconsistency if the config-resolved path differs between caller and skill.

## Current Behavior

Both `skills/product-analyzer/SKILL.md` (Section 6) and `commands/scan-product.md` (Step 5.2) perform deduplication against existing `.issues/` files, producing inconsistent `skipped` counts and wasting token budget reading issue files twice.

`scan-product` reads `.ll/ll-goals.md` independently (Step 2) and injects `GOALS_CONTENT` into the skill prompt, while the skill also reads the goals file in Section 2 — a redundant read that could produce inconsistency if config-resolved paths differ.

## Expected Behavior

Clear contract established:
- **Skill** (`product-analyzer`) is the sole responsible party for deduplication
- **Command** (`scan-product`) trusts the skill's output and does not re-deduplicate
- Goals file is read once: by the command (which has `Bash` access for git metadata), injected into the skill prompt; the skill trusts injected content

## Motivation

This enhancement would:
- Eliminate token budget waste from reading issue files twice during each scan
- Remove the source of inconsistent `skipped_issues` counts in scan reports
- Prevent potential inconsistency from dual goals-file reads when config-resolved paths differ
- Establish a clear ownership contract: skill owns deduplication, command owns metadata injection

## Implementation Steps

### `commands/scan-product.md`

**Step 5.2 — Remove re-deduplication**:
- Delete: "Deduplicate against existing issues" / "Review `duplicate_of` field in findings" / "Remove findings marked as duplicates"
- Replace with: "Trust the skill's `skipped_issues` list for deduplication — do not re-filter"
- The command should only count and display what the skill already decided

**Step 2 — Clarify goals read**:
- Keep the goals file read (command has `Bash` access, needs content for summary display and skill prompt injection)
- Add a note: "The skill trusts `GOALS_CONTENT` injected in the prompt — it will not re-read the goals file when content is provided"

### `skills/product-analyzer/SKILL.md`

**Section 2 — Conditional goals read**:
- If `GOALS_CONTENT` is present in the invoking prompt, use it directly (trust caller)
- If invoked standalone (no injected content), read from config-resolved `goals_file` path or run discovery (per ENH-1400)

**Section 6 — Deduplication is authoritative**:
- Add: "This is the canonical deduplication step. Callers must not re-deduplicate."

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Preserve the string `product.goals_file` somewhere in the updated `### 2. Load Product Goals` section of `skills/product-analyzer/SKILL.md` — `TestGoalsFilePathFromConfig::test_section2_references_product_goals_file_config` in `scripts/tests/test_enh1402_doc_wiring.py` asserts this string is present; removing it will cause that existing test to fail

## Acceptance Criteria

- The final scan report shows a single consistent `skipped_issues` count
- Goals file is read at most once per `/ll:scan-product` invocation
- Skill can still be invoked standalone (`/ll:product-analyzer`) and performs its own goals load + dedup
- No behavioral change for the user — same findings, same report structure

## Scope Boundaries

- **In scope**: Removing re-deduplication step from `scan-product` Step 5.2; adding conditional goals read to skill Section 2; adding authoritative-dedup note to skill Section 6
- **Out of scope**: Changing the deduplication algorithm or matching logic; modifying the goals file format or discovery logic; any user-visible behavioral change to scan output

## Integration Map

### Files to Modify
- `commands/scan-product.md` — Step 5.2 (remove re-deduplication), Step 2 (clarify goals injection note)
- `skills/product-analyzer/SKILL.md` — Section 2 (conditional goals read), Section 6 (add authoritative-dedup comment)

### Dependent Files (Callers/Importers)
- N/A — skill invoked by `scan-product`; no other callers expected

### Similar Patterns
- N/A — no similar dual-dedup patterns in other skill/command pairs

### Tests
- `scripts/tests/test_enh1402_doc_wiring.py` — existing doc-wiring tests for `product-analyzer` SKILL.md; use as pattern (uses `_section()` helper to scope assertions to named sections)
- New: `scripts/tests/test_enh1403_doc_wiring.py` — assert (a) Section 6 of SKILL.md contains canonical-dedup comment; (b) Section 2 has conditional goals-read; (c) Step 5 of `commands/scan-product.md` no longer contains "Remove findings marked as duplicates" post-fix

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1402_doc_wiring.py` — `TestGoalsFilePathFromConfig::test_section2_references_product_goals_file_config` asserts `"product.goals_file"` appears in `### 2. Load Product Goals` of SKILL.md; the conditional Section 2 rewrite **must retain** the string `product.goals_file` or this existing test will fail [Agent 2 finding]

### Documentation
- N/A — internal contract change; no user-facing docs affected

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed line numbers (verified current):**
- `commands/scan-product.md:95-108` — Step 2: goals file read via `cat {{config.product.goals_file}}`; stored as `GOALS_CONTENT`
- `commands/scan-product.md:142-175` — Step 4: skill invocation; `GOALS_CONTENT` injected verbatim under `## Goals Document` heading in prompt
- `commands/scan-product.md:183-191` — Step 5.2: second dedup pass ("The skill performs initial deduplication / Review `duplicate_of` field / Remove findings marked as duplicates")
- `skills/product-analyzer/SKILL.md:51-62` — Section 2: independent goals file re-read (redundant when `GOALS_CONTENT` already injected)
- `skills/product-analyzer/SKILL.md:161-172` — Section 6: authoritative dedup (exact dupes → `skipped_issues`; near-dupes → `findings` with `duplicate_of:`)

**Conditional goals-read pattern to model:**
- `skills/workflow-automation-proposer/SKILL.md:22-26` — canonical "if `$ARGUMENTS` provided, use them; else look at default location" branching table; use this structure for Section 2's conditional check in product-analyzer

**Blocker status as of 2026-05-11:**
- ENH-1402 completed: commit `cbfafea6 improve(product-analyzer): fix output schema inconsistencies`
- ENH-1400 moved to `.issues/completed/` (git-staged); conditional goals-read implementation is now unblocked per scope boundary sequencing

## Evidence

- `commands/scan-product.md:188-191` — "Deduplicate against existing issues" (redundant)
- `skills/product-analyzer/SKILL.md:160-169` — deduplication in skill (authoritative)
- `commands/scan-product.md:95-108` — goals file read (Step 2)
- `skills/product-analyzer/SKILL.md:51-62` — goals file read again in skill (Section 2)

## Impact

- **Priority**: P3 — Technical cleanup; reduces token waste and report inconsistency; no user-visible behavioral change
- **Effort**: Small — Modifying two markdown files (command + skill); no Python changes required
- **Risk**: Low — Removes a redundant step; skill deduplication is already the authoritative source
- **Breaking Change**: No

## Labels

`enhancement`, `technical-debt`, `captured`

## Status

**Open** | Created: 2026-05-09 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-05-11T09:41:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/` - Completed: removed Step 5.2 re-dedup from scan-product.md, added goals injection note to Step 2, added conditional GOALS_CONTENT read to SKILL.md Section 2, added canonical-dedup comment to Section 6, created test_enh1403_doc_wiring.py (6 tests pass)
- `/ll:ready-issue` - 2026-05-11T09:39:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/417a6bbb-b525-4161-bf7a-cdd08dbcfda7.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/643174cb-56d5-45ff-bad8-a68c2d31c54c.jsonl`
- `/ll:wire-issue` - 2026-05-11T09:35:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c99bc4ca-ca0d-4a98-b81a-1c84c2e97f03.jsonl`
- `/ll:refine-issue` - 2026-05-11T09:29:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9df8857-98f7-49ee-b55f-03c160edd6ec.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:13:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9656e0a3-1e1c-475f-af39-bb776aea9268.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): The conditional goals-read in this issue ("if GOALS_CONTENT is injected by caller, skip independent goals read") conflicts with ENH-1400's approach where the skill independently reads or discovers the goals file. Required sequencing: ENH-1402 (config-driven path) → ENH-1400 (discovery fallback) → this issue (conditional skip). Do not implement the conditional goals-read section until ENH-1400's stable fallback path is merged — otherwise the conditional logic has no stable base to branch from.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue establishes that `scan-product` (the command) is the sole owner of goals reading and the skill trusts injected content. However, ENH-1400 adds a goals-discovery fallback for the case when `ll-goals.md` is absent. These must be coordinated: **the absent-goals discovery logic belongs in `scan-product` (the command), not in the skill**. When the goals file is absent, `scan-product` should run discovery against project docs and inject the synthesized result — keeping the skill stateless with respect to goals sourcing. Related: ENH-1400.
