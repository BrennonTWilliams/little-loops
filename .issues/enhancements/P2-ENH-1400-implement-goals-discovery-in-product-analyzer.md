---
discovered_date: 2026-05-09
discovered_by: audit
blocked_by:
- ENH-1402
confidence_score: 90
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
size: Very Large
status: done
completed_at: 2026-05-11T00:00:00Z
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

**Ownership model**: Goals discovery belongs in `commands/scan-product.md` (the command), not in the skill. The skill must remain stateless with respect to goals sourcing — it trusts `GOALS_CONTENT` injected by the command and never reads the filesystem independently for goals. This keeps the skill composable and testable in isolation.

### 1. `commands/scan-product.md`

**Step 1.2 — Discovery path** (replaces hard-exit when goals file is absent):

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
   - Set goals_source: discovered, discovered_from: [list of files]
6. Inject synthesized context as GOALS_CONTENT into the skill invocation
```

**Remove** the duplicate hard-exit block at Step 1.2.

### 2. `skills/product-analyzer/SKILL.md`

**Change guardrail**: Remove the hard-stop on missing goals file. The skill now **always** expects `GOALS_CONTENT` to be injected by the caller (scan-product or any other command). It must not read or discover goals independently.

**Update output metadata** (passed through from injected context):
```yaml
analysis_metadata:
  goals_source: [explicit|discovered]  # set by the command, passed to skill
  discovered_from: ["README.md", ...]  # only when goals_source: discovered
```

**Update `skipped_reason`**: Only stop if `product.enabled: false` (explicit opt-out) or if `GOALS_CONTENT` is absent (caller error). Remove `goals_file_missing` as a terminal condition.

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
- `commands/scan-product.md` — replace hard-exit block at Step 1.2 with discovery logic; inject synthesized GOALS_CONTENT into skill invocation
- `skills/product-analyzer/SKILL.md` — remove hard-stop on missing goals file; remove any independent goals-file read; trust injected GOALS_CONTENT; update output metadata schema

### Dependent Files (Callers/Importers)
- `commands/scan-product.md` — top-level caller of `skills/product-analyzer`

_Wiring pass added by `/ll:wire-issue`:_
- `commands/create-sprint.md` — references `product.goals_file` existence check; skips product analysis when file is missing — behavior may diverge if discovery changes when goals are "available" [Agent 1 finding]
- `skills/issue-workflow/SKILL.md` — lists `/ll:scan-product` in discovery phase workflow; no hard-prereq language, no update needed but informational [Agent 1 finding]

### Similar Patterns
- `config-schema.json:720-738` — `goals_discovery` schema (read-only reference, no changes needed)

### Tests
- `scripts/tests/test_goals_parser.py` — covers `GoalsParser` (parsing structured goals files), not discovery; no direct product-analyzer or scan-product unit tests exist
- `scripts/tests/test_goals_parser_fuzz.py` — fuzz tests for goals parser
- New test coverage needed: add tests that exercise the discovery path (no goals file present, discovery runs from README/ROADMAP files)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — `test_warns_product_without_goals` (line 1649) asserts `"product.enabled is true but goals file not found"` in stderr; after ENH-1400, missing goals file is a valid supported configuration — this assertion must be updated to expect a softer informational notice (or removed if the hook warning is dropped) [Agent 2 finding]
- `scripts/tests/test_hooks_integration.py::test_no_warnings_when_properly_configured` (line 1671) — unaffected (goals file is present in that fixture); no change needed
- New test file `scripts/tests/test_enh1400_product_analyzer_wiring.py` — needed for:
  - Assert `goals_file_missing` is absent from `SKILL.md` after the change (removed from `skipped_reason` enum)
  - Assert `goals_content_missing` is present as the new caller-error `skipped_reason`
  - Assert `### 2. Load Product Goals` section does not contain `Read .ll/ll-goals.md` (independent file read removed)
  - Assert `goals_source` and `discovered_from` appear in the `analysis_metadata` block of `SKILL.md`
  - Assert `goals_discovery.max_files` and `goals_discovery.required_files` interpolations are present in `commands/scan-product.md`
  - Assert hard-exit block ("Goals file not found") is absent from `commands/scan-product.md`
  - Follow the pattern in `scripts/tests/test_enh1362_doc_wiring.py` (`TestAlignIssuesConditionalStep4`) for command content assertions [Agent 3 finding]

### Documentation
- `docs/reference/CONFIGURATION.md:925` — `### product.goals_discovery` section documents the schema fields; may need a behavioral note explaining that these settings are now active (not just declared)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:scan-product` and `### /ll:product-analyzer` sections both carry a "Prerequisites" block listing "Goals file exists (`.ll/ll-goals.md` by default)" as a hard requirement; this prerequisite is no longer strict after ENH-1400 — update both sections [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md` — `### Goal-Oriented Scanning` paragraph states "Requires a product goals file (configured in `ll-config.json`)" — will be inaccurate after ENH-1400; soften to "uses goals file if present, otherwise discovers goals from existing docs" [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — line 167 instructs users to "create `ll-goals.md` by copying `templates/ll-goals-template.md`" as a prerequisite for `/ll:scan-product`; after ENH-1400 this becomes a recommendation rather than a hard requirement [Agent 2 finding]
- `commands/help.md` — `/ll:scan-product` entry description ("based on goals document") implies goals file must exist; soften to reflect discovery fallback [Agent 2 finding]

### Configuration
- `config-schema.json:720-738` — already defines `goals_discovery.max_files` and `goals_discovery.required_files`; no schema changes needed

### Hooks Side-Effect

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/session-start.sh` — `validate_enabled_features()` (lines 134–143) checks if `product.enabled` is true and emits `"Warning: product.enabled is true but goals file not found"` when `ll-goals.md` is absent; after ENH-1400, this is a valid configuration (discovery handles it) — the warning must be downgraded to an informational notice or removed to avoid false alarms on every session startup [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `hooks/scripts/session-start.sh` `validate_enabled_features()` — downgrade the missing-goals-file warning to an informational note or remove it; missing `ll-goals.md` with `product.enabled: true` is a valid configuration after ENH-1400
2. Update `scripts/tests/test_hooks_integration.py` `test_warns_product_without_goals` — update assertion to match the changed hook message (or remove if warning is dropped)
3. Write `scripts/tests/test_enh1400_product_analyzer_wiring.py` — add doc-wiring assertions for both `SKILL.md` and `scan-product.md` changes (see Tests subsection above for full list of assertions)
4. Update `docs/reference/COMMANDS.md` `### /ll:scan-product` and `### /ll:product-analyzer` prerequisite blocks — remove hard "Goals file exists" prerequisite
5. Update `docs/guides/GETTING_STARTED.md` `### Goal-Oriented Scanning` — soften "Requires a product goals file" to reflect discovery fallback
6. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` line ~167 — change from hard instruction ("create ll-goals.md before running scan-product") to recommendation
7. Update `commands/help.md` — soften `/ll:scan-product` description to reflect discovery fallback

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Config access pattern in commands
- New `goals_discovery` values are accessed in `commands/scan-product.md` via `{{config.product.goals_discovery.max_files}}` and `{{config.product.goals_discovery.required_files}}` — the same `{{config.*}}` interpolation used for all other config fields (e.g., `{{config.product.goals_file}}` at line ~67)

### GOALS_CONTENT injection mechanism
- `scan-product.md` `### 2. Load Product Context` (~lines 92-108) reads the goals file and assigns `GOALS_CONTENT` as a named variable
- `### 4. Run Product Analysis` (~line 146) inlines it as `{{GOALS_CONTENT}}` directly in the Skill prompt body (not via env var or formal parameter) under a `## Goals Document` fenced section
- The discovery fallback should populate `GOALS_CONTENT` via the same assignment pattern, then flow into the existing injection at line ~146 unchanged

### Dual skill-level goals read (must remove)
- `skills/product-analyzer/SKILL.md` `### 2. Load Product Goals` (~lines 51-62) instructs the LLM to `Read .ll/ll-goals.md` independently, even when `GOALS_CONTENT` is already present in the prompt — this creates a double read. ENH-1400 must remove (or make conditional) this section so the skill trusts the injected content

### `analysis_metadata` schema (where new fields go)
- `skills/product-analyzer/SKILL.md` lines ~175-184 define the output `analysis_metadata` block; add `goals_source: [explicit|discovered]` and `discovered_from: [...]` at the same level as the existing `goals_file` field

### File discovery patterns to follow
- `skills/init/SKILL.md` lines ~88-108 probes for indicator files by existence-checking each entry in a detect array — the same structural pattern needed for `required_files` and fallback glob candidates
- `skills/audit-docs/SKILL.md` lines ~43-56 uses `find` with glob patterns to collect markdown files — useful for `ROADMAP*.md`, `vision*.md` etc.
- The `warn-but-continue` pattern is established in `skills/init/SKILL.md` lines ~375-378: display a warning, then explicitly state "Always proceed regardless of results"

### `skipped_reason` values after this issue
- Per ENH-1402, once ENH-1400 ships, `goals_file_missing` becomes an invalid `skipped_reason` value; only `not_enabled` (and a new `goals_content_missing` for caller error) should remain

## Impact

- **Priority**: P2 — product-analyzer is a no-op on all projects without a manually-created goals file, blocking its adoption
- **Effort**: Medium — new fallback path in SKILL.md; minimal change to scan-product.md; config schema already defined
- **Risk**: Low — new code path only runs when `ll-goals.md` is absent; existing behavior when file is present is unchanged
- **Breaking Change**: No

## Evidence

- `config-schema.json:767-786` — `goals_discovery` schema defined but never consumed (issue originally cited 720-738; actual location confirmed at 767-786)
- `skills/product-analyzer/SKILL.md` — hard-stop on missing goals file appears in two places: `## Guardrails` (declarative, lines ~24-27) and `### 1. Configuration Check` (procedural, lines ~36-49); `skipped_reason: goals_file_missing` is emitted from the procedural block
- `skills/product-analyzer/SKILL.md` — `### 2. Load Product Goals` (~lines 51-62) re-reads the goals file independently even when `GOALS_CONTENT` is already injected via the prompt — this second read must also be removed
- `commands/scan-product.md:72-88` — duplicate hard-stop before skill is even called; `GOALS_CONTENT` is populated in `### 2. Load Product Context` (~lines 92-108) and injected at line ~146 in `### 4. Run Product Analysis`

## Labels

`enhancement`, `captured`, `product-analyzer`

## Status

**Open** | Created: 2026-05-09 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- Low test coverage for the core discovery logic — primary change sites (`commands/scan-product.md` and `skills/product-analyzer/SKILL.md`) are markdown instruction files without functional unit tests; correctness of the synthesis path can only be validated manually
- Broad documentation surface (5 doc files require language softening); each update is mechanical but requires coordinated attention to avoid inconsistencies
- Minor open question on hook warning treatment — `hooks/scripts/session-start.sh` can have its warning downgraded to an informational notice or removed entirely; the choice should be settled before implementation to avoid downstream test changes

## Session Log
- `/ll:issue-size-review` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a400556-76fe-4ad7-9557-40b6a1c32a72.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00c6c86a-51e1-44a2-8bee-e7557e656625.jsonl`
- `/ll:wire-issue` - 2026-05-11T08:02:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1610ca5d-d284-4153-8290-5ef5dc5360b3.jsonl`
- `/ll:refine-issue` - 2026-05-11T07:58:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09a01cf5-5aee-4263-8e41-7ec8aecf1104.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:39:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:12:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe401f22-7fbb-48c3-8ae7-e1588507294c.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-11
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1442: Goals Discovery — Core Implementation (scan-product, product-analyzer, hooks, tests)
- ENH-1443: Goals Discovery — Documentation Updates

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): ENH-1403's conditional goals-read strategy (trust injected GOALS_CONTENT from the caller, skip independent read) is mutually exclusive with this issue's independent goals-file discovery approach. Required sequencing: ENH-1402 ships first (establishes config-driven path contract) → this issue (ENH-1400, discovery fallback uses that config-driven path) → ENH-1403 (conditional skip when GOALS_CONTENT is injected). ENH-1403 must not implement the conditional goals-read until ENH-1400's fallback path is stable and merged.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): This issue targets existing and legacy projects that were initialized without a goals file. ENH-1401 (wire product setup into init) addresses the complementary case: new projects created via `/ll:init` going forward will always have `ll-goals.md`. The two issues are not redundant — ENH-1401 prevents the missing-goals-file problem for future projects; this issue provides the retrofit path for projects already in place.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue specifies that the *skill* (`product-analyzer`) performs goals discovery when `ll-goals.md` is absent. However, ENH-1403 establishes that the *command* (`scan-product`) is the sole owner of goals reading and the skill trusts injected content. These must be coordinated: the correct resolution is that **`scan-product` (the command) performs discovery when the goals file is absent and injects the synthesized context**, rather than the skill doing it internally. Implement ENH-1400's discovery logic in `commands/scan-product.md` so the skill remains stateless with respect to goals sourcing. Related: ENH-1403.
