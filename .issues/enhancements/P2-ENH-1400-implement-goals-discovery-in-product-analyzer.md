---
discovered_date: 2026-05-09
discovered_by: audit
blocked_by: [ENH-1402]
---

# ENH-1400: Implement `goals_discovery` in product-analyzer

## Summary

The `config-schema.json` defines `product.goals_discovery` (`max_files`, `required_files`) for auto-discovering product goals from existing documentation when `ll-goals.md` is absent. Neither `skills/product-analyzer/SKILL.md` nor `commands/scan-product.md` reads or acts on these fields — the skill hard-stops with `skipped_reason: goals_file_missing` instead. This makes product-analyzer a no-op on any project that hasn't manually created a goals file, preventing it from being a first-class skill.

## Current Behavior

When `ll-goals.md` is absent, `skills/product-analyzer` exits immediately with `skipped_reason: goals_file_missing`. The `goals_discovery` config fields (`max_files`, `required_files`) defined in `config-schema.json:720-738` are never read or acted upon. `commands/scan-product.md` also hard-stops before the skill is even called, adding a duplicate gate.

## Expected Behavior

When `ll-goals.md` is absent, the skill falls back to synthesizing a temporary goals context from existing project documentation (README, roadmaps, vision docs, CONTRIBUTING) rather than exiting. The synthesized context is clearly marked as `discovered` vs `goals-defined` in output metadata so consumers can distinguish authoritative goals from inferred ones.

## Motivation

Product-analyzer is a no-op on any project that hasn't manually created a `ll-goals.md` file, which includes all new or bootstrapped projects. This prevents it from functioning as a first-class skill. The config schema already defines `goals_discovery` with `max_files` and `required_files` fields — the implementation gap is that these fields are never consumed. Wiring them up would make product-analyzer self-bootstrapping.

## Proposed Solution

### 1. `skills/product-analyzer/SKILL.md`

**Change guardrail**: Remove the hard-stop on missing goals file. Instead, route to discovery.

**Add Section 2b — Goals Discovery** (runs when goals file is absent):

```
1. Read config: goals_discovery.max_files (default 5), goals_discovery.required_files (default ["README.md"])
2. Warn if required_files are missing
3. Discover candidate files using these patterns (in priority order):
   - goals_discovery.required_files entries
   - **/ROADMAP*.md, **/roadmap*.md
   - **/vision*.md, **/goals*.md
   - **/requirements*.md, **/product*.md
   - README.md (always included)
   - CONTRIBUTING.md
4. Read up to max_files files
5. Synthesize a temporary goals context:
   - Infer primary persona from README "for" / "who uses" language
   - Infer priorities from section headers, feature lists, roadmap items
   - Mark with goals_source: discovered and discovered_from: [list of files]
6. Proceed with analysis using synthesized context
```

**Update output metadata**:
```yaml
analysis_metadata:
  goals_source: [explicit|discovered]  # new field
  discovered_from: ["README.md", ...]  # only when goals_source: discovered
```

**Update `skipped_reason`**: Only stop if `product.enabled: false` (explicit opt-out). Remove `goals_file_missing` as a terminal condition.

### 2. `commands/scan-product.md`

- **Remove** the hard-exit block on missing goals file (Step 1.2)
- Replace with: "If goals file missing, note that discovery mode will be used — the skill handles it"
- Remove the redundant goals-file read in Step 2 when the skill will discover independently (or keep it for the summary display but don't fail on absence)

## Acceptance Criteria

- `/ll:scan-product` on a project with only `README.md` and no `ll-goals.md` produces meaningful findings
- Output metadata clearly indicates `goals_source: discovered`
- If `required_files` are missing, a warning is shown but analysis still proceeds
- `max_files` limit is respected — never reads more than configured limit
- With an explicit `ll-goals.md`, behavior is unchanged (`goals_source: explicit`)

## Scope Boundaries

- **In scope**: Goals discovery fallback in `skills/product-analyzer` and removing the duplicate gate in `commands/scan-product.md`
- **Out of scope**: Creating or modifying `ll-goals.md` files; changes to `ll:init` or `ll:configure`; modifying the `goals_discovery` config schema itself (already defined)
- **Out of scope**: Quality of synthesized goals relative to hand-authored `ll-goals.md` — discovery is best-effort inference, not a replacement

## Integration Map

### Files to Modify
- `skills/product-analyzer/SKILL.md` — remove hard-stop, add Section 2b discovery logic, update output metadata schema
- `commands/scan-product.md` — remove hard-exit block at Step 1.2, update Step 2 to not fail on absent goals file

### Dependent Files (Callers/Importers)
- `commands/scan-product.md` — top-level caller of `skills/product-analyzer`

### Similar Patterns
- `config-schema.json:720-738` — `goals_discovery` schema (read-only reference, no changes needed)

### Tests
- TBD — search for existing product-analyzer tests: `grep -r "product.analyzer\|scan.product\|goals_discovery" scripts/tests/`

### Documentation
- TBD — check if any docs describe the goals-file-missing behavior: `grep -r "goals_file_missing\|ll-goals" docs/`

### Configuration
- `config-schema.json:720-738` — already defines `goals_discovery.max_files` and `goals_discovery.required_files`; no schema changes needed

## Impact

- **Priority**: P2 — product-analyzer is a no-op on all projects without a manually-created goals file, blocking its adoption
- **Effort**: Medium — new fallback path in SKILL.md; minimal change to scan-product.md; config schema already defined
- **Risk**: Low — new code path only runs when `ll-goals.md` is absent; existing behavior when file is present is unchanged
- **Breaking Change**: No

## Evidence

- `config-schema.json:720-738` — `goals_discovery` schema defined but never consumed
- `skills/product-analyzer/SKILL.md:44-48` — hard-stop on missing goals file
- `commands/scan-product.md:72-88` — duplicate hard-stop before skill is even called

## Labels

`enhancement`, `captured`, `product-analyzer`

## Status

**Open** | Created: 2026-05-09 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:12:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe401f22-7fbb-48c3-8ae7-e1588507294c.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): ENH-1403's conditional goals-read strategy (trust injected GOALS_CONTENT from the caller, skip independent read) is mutually exclusive with this issue's independent goals-file discovery approach. Required sequencing: ENH-1402 ships first (establishes config-driven path contract) → this issue (ENH-1400, discovery fallback uses that config-driven path) → ENH-1403 (conditional skip when GOALS_CONTENT is injected). ENH-1403 must not implement the conditional goals-read until ENH-1400's fallback path is stable and merged.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): This issue targets existing and legacy projects that were initialized without a goals file. ENH-1401 (wire product setup into init) addresses the complementary case: new projects created via `/ll:init` going forward will always have `ll-goals.md`. The two issues are not redundant — ENH-1401 prevents the missing-goals-file problem for future projects; this issue provides the retrofit path for projects already in place.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue specifies that the *skill* (`product-analyzer`) performs goals discovery when `ll-goals.md` is absent. However, ENH-1403 establishes that the *command* (`scan-product`) is the sole owner of goals reading and the skill trusts injected content. These must be coordinated: the correct resolution is that **`scan-product` (the command) performs discovery when the goals file is absent and injects the synthesized context**, rather than the skill doing it internally. Implement ENH-1400's discovery logic in `commands/scan-product.md` so the skill remains stateless with respect to goals sourcing. Related: ENH-1403.
