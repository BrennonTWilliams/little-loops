---
discovered_date: 2026-05-09
discovered_by: audit
blocked_by: [ENH-1402]
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
- TBD — check for any tests exercising scan-product + product-analyzer interaction

### Documentation
- N/A — internal contract change; no user-facing docs affected

### Configuration
- N/A

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
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:13:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9656e0a3-1e1c-475f-af39-bb776aea9268.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): The conditional goals-read in this issue ("if GOALS_CONTENT is injected by caller, skip independent goals read") conflicts with ENH-1400's approach where the skill independently reads or discovers the goals file. Required sequencing: ENH-1402 (config-driven path) → ENH-1400 (discovery fallback) → this issue (conditional skip). Do not implement the conditional goals-read section until ENH-1400's stable fallback path is merged — otherwise the conditional logic has no stable base to branch from.
