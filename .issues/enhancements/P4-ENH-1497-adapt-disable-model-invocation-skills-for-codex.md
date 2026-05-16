---
id: ENH-1497
type: ENH
priority: P4
status: done
captured_at: '2026-05-16T13:04:12Z'
completed_at: '2026-05-16T13:43:24Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
relates_to:
- FEAT-1486
- FEAT-1493
- BUG-1494
labels:
- captured
- codex
- skills-api
- parity
decision_needed: false
testable: false
confidence_score: 93
outcome_confidence: 75
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1497: Audit `disable-model-invocation: true` skills for Codex exposure

## Summary

16 skills carry `disable-model-invocation: true` in their SKILL.md frontmatter and are deliberately skipped by `ll-adapt-skills-for-codex`. Some of these (e.g. `cleanup-loops`, `debug-loop-run`) are genuinely user-only and should remain hidden from model invocation. Others may have been flagged conservatively and could safely be exposed in Codex. Audit each, decide per-skill, and either remove the flag or document why exclusion is correct.

## Current Behavior

`ll-adapt-skills-for-codex` skips any SKILL.md with `disable-model-invocation: true`. Per the Codex audit, the skipped skills include:

`update-docs`, `update`, `cleanup-loops`, `debug-loop-run`, `audit-issue-conflicts`, `workflow-automation-proposer`, `review-loop`, `audit-claude-config`, `rename-loop`, `improve-claude-md`, plus ~6 more.

A Codex user has no way to discover these. From Claude Code, the same flag means "don't auto-invoke" but the slash command still works — different semantics that don't translate cleanly to Codex's Skills API.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**⚠️ Premise is inaccurate.** Reading `scripts/little_loops/cli/adapt_skills_for_codex.py` shows the adapter does **NOT** read or honor `disable-model-invocation: true`. A `grep` of that file returns zero matches for the key. The only skip paths in `_process_skills()` (lines 109–155) are:

1. `OSError` reading the SKILL.md file (counted as `errors`)
2. `_extract_short_desc()` returns `""` because `description:` is absent/empty
3. SKILL.md already has `name:` + `metadata.short-description:` and `agents/openai.yaml` already exists (counted as "already adapted")

Consequence: **all 16 skills carrying `disable-model-invocation: true` have already been adapted for Codex.** Each has `agents/openai.yaml` present and `name:` + `metadata.short-description:` injected. The lone exception is `skills/update-docs/agents/openai.yaml` (missing — tracked by BUG-1494), which is missing for a different reason (the SKILL.md lacks an injected `name:` field; the flag itself is irrelevant to the skip).

**The real consumer of the flag** is `scripts/little_loops/cli/generate_skill_descriptions.py` `_process_skills()` line 107:

```python
if fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1"):
    print(f"  SKIP   {skill_name} (disable-model-invocation: true)")
    skipped += 1
    continue
```

That tool skips the flagged skills for **token-budget compliance**, not Codex exposure. Doc references in `.claude/CLAUDE.md` (line 129) and `docs/reference/CLI.md` (lines 1252–1423) that imply Codex adaptation honors the flag are **incorrect**.

**Full list of all 16 flagged skills** (each currently exposed in Codex despite the flag):

`analyze-history`, `audit-claude-config`, `audit-docs`, `audit-issue-conflicts`, `audit-loop-run`, `cleanup-loops`, `debug-loop-run`, `improve-claude-md`, `issue-size-review`, `issue-workflow`, `map-dependencies`, `rename-loop`, `review-loop`, `update`, `update-docs`, `workflow-automation-proposer`.

None of the 16 SKILL.md files carry an inline YAML comment (`#`) explaining the rationale for the flag.

## Expected Behavior

A documented decision exists per skill: either
- The flag is removed (skill is exposed in Codex), or
- A comment / convention captures *why* the skill is intentionally user-only (and the adapter's skip behavior is the correct outcome)

Optionally: introduce a separate Codex-specific opt-in mechanism (e.g. `codex-expose: true` even when `disable-model-invocation: true`) for skills that should be discoverable from Codex but not auto-invoked by the Claude Code model.

## Motivation

`disable-model-invocation: true` was originally a Claude Code concept — it prevents the model from auto-firing a skill while leaving slash-command access intact. The flag was extended to act as the Codex adapter's skip signal, conflating two distinct semantics:

1. "Don't auto-invoke from the model" (Claude Code)
2. "Don't expose to Codex at all" (current adapter behavior)

For some skills (1) is correct but (2) is overly restrictive. A Codex user invoking `/ll:rename-loop` explicitly is not auto-invocation; the skill should arguably be available.

## Scope Boundaries

**In scope (Option A — selected):**
- Correcting false documentation in `.claude/CLAUDE.md` (line 129), `docs/reference/CLI.md`, and `docs/reference/HOST_COMPATIBILITY.md` about `ll-adapt-skills-for-codex` skipping `disable-model-invocation: true` skills
- Adding a clarifying note that all 16 flagged skills are currently exposed in Codex

**Out of scope:**
- Code changes to `adapt_skills_for_codex.py` (adapter behavior stays as-is)
- Per-skill `disable-model-invocation` flag triage or removal
- Introduction of a new `codex-expose` flag (Option C)
- Deleting any `agents/openai.yaml` files already generated by FEAT-1486

## Proposed Solution

1. Inventory all 16 skills with the flag and triage each into one of three buckets:
   - **Keep skipped** — genuinely never useful from Codex (e.g. `update`, which mutates the plugin install)
   - **Expose** — remove the `disable-model-invocation: true` flag; the original Claude Code reason no longer holds or never did
   - **Expose with caveat** — introduce a sibling flag for "Codex-discoverable but not Claude-Code auto-invokable"
2. Document the decision in a short table in `HOST_COMPATIBILITY.md` or `docs/codex/README.md` (once ENH-1495 lands)
3. Update `ll-adapt-skills-for-codex` if a new flag is introduced

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Because the adapter never actually skipped these skills (see Codebase Research Findings under Current Behavior), the solution space splits into three meaningfully different options. **This issue needs a decision before implementation.**

**Option A — Docs-only fix (lowest cost, fastest).** Update `.claude/CLAUDE.md:129` and `docs/reference/CLI.md` (~lines 1252–1423) to remove the false claim that `ll-adapt-skills-for-codex` skips `disable-model-invocation: true` skills. Document that the flag affects only `ll-generate-skill-descriptions` (token-budget) and Claude Code's auto-invocation behavior. Add a one-line note that all 16 currently-flagged skills are exposed in Codex by default. No code change; no SKILL.md changes. Accepts the current behavior as correct.

> **Selected:** Option A — Docs-only fix — FEAT-1486 unconditionally adapted all 15/16 flagged skills; no test asserts skip behavior; correcting 2–3 doc files is the minimum viable fix with zero code risk.

**Option B — Implement the documented behavior (medium cost).** Add a `disable-model-invocation` check to `_process_skills()` in `scripts/little_loops/cli/adapt_skills_for_codex.py` (insert after line 123, immediately after `_extract_short_desc()` — see Integration Map). Use the line-split parser pattern from `generate_skill_descriptions._parse_frontmatter()` (lines 29–43) rather than expanding the `yaml.safe_load` call in `_extract_short_desc()`, for consistency with the existing flag consumer. Then per-skill audit and remove the flag from any of the 16 SKILL.md files where Codex exposure is genuinely desired. This is the originally-intended design.

**Option C — Two-flag design (highest cost, most precise).** Implement Option B's skip behavior, then introduce a sibling `codex-expose: true` override flag for skills that want the Claude Code auto-invocation gate without the Codex-skip side effect. Audit the 16 skills and either leave them gated, remove `disable-model-invocation`, or add `codex-expose: true`. Adds a new SKILL.md frontmatter field — coordinate with `docs/reference/HOST_COMPATIBILITY.md` and any other frontmatter validators.

**Recommendation surface (informational, not a decision):** Option A is closest to "do nothing" but requires acknowledging that the FEAT-1486 work effectively decided this issue by adapting all 16 skills without protest. Option B fits the originally-described intent but reverses adaptation that already shipped — at minimum, the 16 already-generated `agents/openai.yaml` files would need to be deleted under `--apply`. Option C is the cleanest semantic split but the most code/doc churn for a P4 issue.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-16.

**Selected**: Option A — Docs-only fix

**Reasoning**: FEAT-1486 unconditionally adapted all 15 of the 16 flagged skills for Codex (15 have `agents/openai.yaml`; the 16th gap is BUG-1494, unrelated to the flag). No test in `test_adapt_skills_for_codex.py` asserts that the adapter skips `disable-model-invocation: true` skills, so there is nothing to protect. Option A formalizes what FEAT-1486 already decided by action: the adapter treats all skills equally, the flag governs only `ll-generate-skill-descriptions` (token budget) and Claude Code auto-invocation. Correcting 2–3 doc files is zero-risk and closes the documentation gap cleanly.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (docs-only) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (implement skip) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option C (two-flag design) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: `adapt_skills_for_codex.py` contains zero references to `disable-model-invocation`; FEAT-1486 ran `--apply` and adapted all 16 unconditionally; doc-only correction pattern is well-established (BUG-597, ENH-1130, etc.).
- **Option B**: `_parse_frontmatter()` and skip guard are directly copy-pasteable from `generate_skill_descriptions.py`, but reversing already-shipped adaptation of 15 skills (requiring yaml deletions) raises meaningful regression risk for a P4 item.
- **Option C**: Zero existing multi-flag override logic anywhere; `user-invocable` is the structural analogue but exercised by no skill in the repo; semantic asymmetry with `generate_skill_descriptions` and `doc_counts` consumers who would not honor `codex-expose`.

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` (a subset of the 16) — flag adjustments per the audit decisions
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — adjust skip logic if a new flag is introduced
- `docs/reference/HOST_COMPATIBILITY.md` or `docs/codex/README.md` — document the per-skill decisions

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py` — assert each documented decision is honored

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_adapt_skills_for_codex` and `main_generate_skill_descriptions` in `__all__`; no changes needed under Options A/B, but if Option C introduces a new CLI entry point, this file gets a new import and `__all__` entry [Agent 1 finding]

### Additional Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — "New Skill Checklist" and "Adding Skills" template block both reference `disable-model-invocation`; if Option C adds `codex-expose`, the checklist needs a third bullet and the SKILL.md template needs the new key. **Caution:** `scripts/tests/test_create_extension_wiring.py::TestEnh1395LlGenerateSkillDescriptionsWiring::test_contributing_md_mentions_disable_model_invocation` asserts the string `"disable-model-invocation"` still appears in CONTRIBUTING.md — do not remove all references [Agent 2 finding]
- `docs/claude-code/skills.md` — `### Frontmatter reference` table (~line 180) lists `disable-model-invocation`; add a `codex-expose` row if Option C is chosen [Agent 2 finding]
- `docs/claude-code/create-plugin.md` — SKILL.md example (~line 111) uses `disable-model-invocation: true`; only update if flag semantics change fundamentally [Agent 2 finding]

### Additional Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_skill_descriptions.py` — **reference implementation to mirror**: `_make_skill(disable_model_invocation: bool = False)` at line 24 and `TestProcessSkills::test_skips_disable_model_invocation_skills` at line 134 are the exact patterns to copy into `test_adapt_skills_for_codex.py`. The boolean is rendered as `"disable-model-invocation: true\n"` inserted before `description:` in the frontmatter string [Agent 3 finding]
- `scripts/tests/test_doc_counts.py` — covers `doc_counts.py` but does NOT cover `check_skill_budget()`'s `disable-model-invocation` skip branch; a unit test with a real skill fixture is missing [Agent 3 finding — gap]
- `scripts/tests/test_cli_docs.py` — `TestMainVerifySkillBudget` exercises `main_verify_skill_budget` via mocked `check_skill_budget`; no direct changes needed but context for side-effect reasoning [Agent 2 finding]
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1486LlAdaptSkillsWiring` asserts `ll-adapt-skills-for-codex` appears in CLAUDE.md, CLI.md, help.md, and areas.md; these assertions are unaffected by this issue [Agent 1/2 finding]
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` — **may break under Option B/C**: `test_all_real_skills_have_name_field()` and `test_all_real_skills_have_metadata_short_description()` iterate all `skills/*/SKILL.md` unconditionally and assert every skill has `name:` and `metadata.short-description:`. If Option B/C causes `_process_skills()` to skip disabled skills and their `agents/openai.yaml` are deleted, these assertions remain valid only if the 16 SKILL.md files retain their already-injected fields. Update both methods to exempt `disable-model-invocation: true` skills if those fields are removed [Agent 2/3 finding]

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — registers `ll-adapt-skills-for-codex = "little_loops.cli:main_adapt_skills_for_codex"` and `ll-generate-skill-descriptions = "little_loops.cli:main_generate_skill_descriptions"` as CLI entry points; only changes if Option C introduces a new CLI tool (unlikely) [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Adapter implementation (primary surface, only if Option B/C selected):**
- `scripts/little_loops/cli/adapt_skills_for_codex.py` in `_process_skills()` (lines 109–155) — insert `disable-model-invocation` skip check immediately after `_extract_short_desc(text)` at line 123, before the `if not short_desc:` guard at ~line 128. Current `_extract_short_desc()` reads only the `description:` key via `yaml.safe_load`; a second read (or wider parse) is required to access `disable-model-invocation`. Mirror the parser pattern from `scripts/little_loops/cli/generate_skill_descriptions.py` `_parse_frontmatter()` (lines 29–43) for consistency.
- `scripts/little_loops/cli/adapt_skills_for_codex.py` in `_extract_short_desc()` (line ~44) — alternative insertion point if expanding the existing `yaml.safe_load` is preferred over a second parser pass.

**Documentation to correct (required under Option A, B, or C):**
- `.claude/CLAUDE.md` line 129 — currently claims `ll-adapt-skills-for-codex` skips `disable-model-invocation: true` skills; this is false.
- `docs/reference/CLI.md` lines ~1252–1423 — `ll-adapt-skills-for-codex` documentation; references the same incorrect skip behavior.
- `docs/reference/HOST_COMPATIBILITY.md` lines 57–72 ("Slash-command and skill discovery") — already correctly states all ll skills are adapted; this is the section to extend with the per-skill decision table.
- `docs/codex/README.md` — does not yet exist; would be created by ENH-1495. If ENH-1495 has not landed, place the decision table in `HOST_COMPATIBILITY.md` instead.

**SKILL.md files carrying the flag (all 16 — read frontmatter when triaging):**
- `skills/analyze-history/SKILL.md` (line 4)
- `skills/audit-claude-config/SKILL.md` (line 4)
- `skills/audit-docs/SKILL.md` (line 4)
- `skills/audit-issue-conflicts/SKILL.md` (line 4)
- `skills/audit-loop-run/SKILL.md` (line 4)
- `skills/cleanup-loops/SKILL.md` (line 4)
- `skills/debug-loop-run/SKILL.md` (line 4)
- `skills/improve-claude-md/SKILL.md` (line 4)
- `skills/issue-size-review/SKILL.md` (line 4)
- `skills/issue-workflow/SKILL.md` (line 4)
- `skills/map-dependencies/SKILL.md` (line 4)
- `skills/rename-loop/SKILL.md` (line 4 — note: has a blank line inside its frontmatter block, the only skill with this quirk)
- `skills/review-loop/SKILL.md` (line 4)
- `skills/update/SKILL.md` (line 4)
- `skills/update-docs/SKILL.md` (line 3 — note: positioned before `argument-hint`, not after `description`; missing `name:` field; also missing `agents/openai.yaml` — see BUG-1494)
- `skills/workflow-automation-proposer/SKILL.md` (line 4)

**Other code paths that read `disable-model-invocation` (for context, do not modify unless explicitly in scope):**
- `scripts/little_loops/cli/generate_skill_descriptions.py` `_process_skills()` line 107 — skips for token-budget compliance during description generation.
- `scripts/little_loops/doc_counts.py` `check_skill_budget()` line 304 — skips disabled skills when measuring skill-listing token footprint.

**Test scaffolding for new flag behavior:**
- `scripts/tests/test_adapt_skills_for_codex.py` `_make_skill()` (line 19) — accepts `extra_frontmatter: str = ""`; add `disable_model_invocation: bool` parameter following the pattern in `scripts/tests/test_generate_skill_descriptions.py` `_make_skill()` (line 25). No existing test in `test_adapt_skills_for_codex.py` covers the flag (the adapter never read it), so a new test class is needed under Option B/C.
- Reference test: `scripts/tests/test_generate_skill_descriptions.py` `TestProcessSkills.test_skips_disable_model_invocation_skills` (line 134) — the exact pattern to mirror.

**Related issues already in flight:**
- BUG-1494 — tracks `update-docs` missing `agents/openai.yaml`; root cause is missing `name:` field, NOT the `disable-model-invocation` flag.
- FEAT-1486 — completed work that adapted all skills (including all 16 flagged ones) for Codex Skills API. Effectively decided this issue toward Option A by adapting everything.
- ENH-1495 — adds `docs/codex/` directory; preferred destination for the decision table once it lands.

## Implementation Steps

1. List all 16 skills with `disable-model-invocation: true` and the rationale for each (read SKILL.md headers)
2. Decide per-skill: keep / expose / expose-with-new-flag
3. Apply frontmatter changes
4. Update adapter if a new flag is introduced
5. Document the rationale table in user-facing docs
6. Re-run `ll-adapt-skills-for-codex` and verify Codex discovers the newly exposed skills

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. Resolve the option in Proposed Solution → Codebase Research Findings before executing these steps._

**Common to all options:**

1. Run `/ll:decide-issue ENH-1497` (or otherwise pick Option A / B / C).
2. Correct documentation in `.claude/CLAUDE.md:129` and `docs/reference/CLI.md` (~lines 1252–1423) to match reality: the adapter does not currently honor `disable-model-invocation`.

**Option A — Docs-only path:**

3. Add a one-line note in `docs/reference/HOST_COMPATIBILITY.md` "Slash-command and skill discovery" (lines 57–72) clarifying that all skills — including those with `disable-model-invocation: true` — are exposed in Codex.
4. Close ENH-1497 as documentation-only resolution. No code or test changes.

**Option B — Implement the documented skip:**

3. Edit `scripts/little_loops/cli/adapt_skills_for_codex.py` `_process_skills()` (after line 123): add a frontmatter read (mirror `generate_skill_descriptions._parse_frontmatter()` lines 29–43) and a `skipped += 1; continue` branch when `disable-model-invocation` is `"true"`.
4. Add test class `TestSkipsDisableModelInvocation` to `scripts/tests/test_adapt_skills_for_codex.py`, mirroring `scripts/tests/test_generate_skill_descriptions.py` `TestProcessSkills.test_skips_disable_model_invocation_skills` (line 134). Extend the local `_make_skill()` helper (line 19) with a `disable_model_invocation: bool = False` parameter.
5. Per-skill triage: for each of the 16 SKILL.md files listed in Integration Map, decide keep/remove. Remove `disable-model-invocation: true` from any skill that should be exposed in Codex. Document each decision (rationale + bucket) in a decision table.
6. Add the decision table to `docs/reference/HOST_COMPATIBILITY.md` "Slash-command and skill discovery" section (or `docs/codex/README.md` if ENH-1495 has landed).
7. Run `ll-adapt-skills-for-codex --apply` and verify only the intended skills are processed; manually delete `agents/openai.yaml` from any skill that was previously adapted but is now in the "keep skipped" bucket.
8. Verify with `python -m pytest scripts/tests/test_adapt_skills_for_codex.py -v`.

**Option C — Two-flag design:**

3. Do Option B step 3 (add skip), then extend `_process_skills()` further: when `disable-model-invocation` is truthy AND `codex-expose` is truthy, continue processing (override). Otherwise skip as in Option B.
4. Update `_make_skill()` and add tests for both flag combinations in `scripts/tests/test_adapt_skills_for_codex.py` — mirror the existing `_make_skill(extra_frontmatter=...)` pattern (line 19).
5. Per-skill triage with three buckets (keep / expose-removeflag / expose-with-codex-expose). For "expose-with-codex-expose" cases, add `codex-expose: true` next to `disable-model-invocation: true` in the SKILL.md frontmatter.
6. Document the new `codex-expose` field in `docs/reference/HOST_COMPATIBILITY.md` and any frontmatter reference docs. Add the per-skill decision table.
7. Steps 7–8 as in Option B.

**Verification (Option B/C):**

- `python -m pytest scripts/tests/test_adapt_skills_for_codex.py -v`
- `ruff check scripts/little_loops/cli/adapt_skills_for_codex.py`
- `ll-adapt-skills-for-codex` (dry run) — confirm intended skills are listed `SKIP`/`DRY` as planned.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

All options:
1. Add a unit test in `scripts/tests/test_doc_counts.py` for `check_skill_budget()` with a skill fixture that has `disable-model-invocation: true` — the skip branch at `doc_counts.py:304` has no unit-level test coverage today.

Option B/C (if `_process_skills()` gains a skip + some skills lose `name:`/`metadata.short-description:`):
2. Update `TestRealSkillsIntegrationGuard.test_all_real_skills_have_name_field()` and `test_all_real_skills_have_metadata_short_description()` in `test_adapt_skills_for_codex.py` to read and skip `disable-model-invocation: true` skills from the assertion loop — otherwise the integration guard will fail for any skill whose fields are removed.

Option C (two-flag design):
3. Update `CONTRIBUTING.md` "New Skill Checklist" and SKILL.md template block with `codex-expose: true` guidance. Do not remove the existing `disable-model-invocation` text — `test_create_extension_wiring.py::TestEnh1395LlGenerateSkillDescriptionsWiring::test_contributing_md_mentions_disable_model_invocation` asserts it is present.
4. Add `codex-expose` row to `docs/claude-code/skills.md` frontmatter reference table (~line 180).

## Impact

- **Priority**: P4 — Quality-of-life parity item; not blocking
- **Effort**: Small/Medium — mostly per-skill decisions and frontmatter edits
- **Risk**: Low — Behavior changes are opt-in per skill
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` | Documents `ll-adapt-skills-for-codex` and the `disable-model-invocation` skip rule |
| `docs/reference/HOST_COMPATIBILITY.md` | Where the per-skill decision matrix should live |


## Blocks

- FEAT-1493
- BUG-1494

## Labels

`enh`, `captured`, `codex`, `skills-api`, `parity`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 66/100 → MODERATE

### Concerns
- Unresolved option choice (A/B/C) — FEAT-1486's silent adaptation of all 16 skills leans toward Option A, but no documented decision exists
- ENH-1495 (docs/codex/ directory) is open; the per-skill decision table falls back to HOST_COMPATIBILITY.md

### Outcome Risk Factors
- Open decision on implementation option (A/B/C) must be resolved before implementing; resolve before implementing to avoid scope creep — run `/ll:decide-issue ENH-1497`
- Option-dependent complexity: Option A is 3 doc files (mechanical); Option B is 16+ SKILL.md sites with a local adapter insert and no explicit verification grep; choosing B or C significantly widens scope
- Per-skill judgment calls for all 16 flagged skills required under Option B/C; no pre-analysis of each skill's suitability included

## Resolution

**Completed**: 2026-05-16 | **Option**: A (docs-only fix)

- Updated `docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]`: removed stale "will flip to ✓ when FEAT-1486 lands" note (FEAT-1486 has landed) and added a clarifying statement that `ll-adapt-skills-for-codex` does not read `disable-model-invocation: true` — all 16 flagged skills are exposed in Codex; the flag governs only `ll-generate-skill-descriptions` and Claude Code auto-invocation.
- Added `TestCheckSkillBudget` test class to `scripts/tests/test_doc_counts.py` covering the `check_skill_budget()` skip branch for `disable-model-invocation: true` skills (previously untested).
- No code changes to `adapt_skills_for_codex.py` (adapter behavior already correct).

## Session Log
- `/ll:manage-issue` - 2026-05-16T13:43:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-16T13:39:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd499936-ee53-457e-84de-a278dc0c82f9.jsonl`
- `/ll:confidence-check` - 2026-05-16T14:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd8fb329-50e2-41f7-8c2e-066d0838e232.jsonl`
- `/ll:decide-issue` - 2026-05-16T13:34:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/138ab84a-9284-4e10-9591-472e1e132e88.jsonl`
- `/ll:confidence-check` - 2026-05-16T13:30:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b02f1089-a7f9-4b74-9715-8b0939c267e6.jsonl`
- `/ll:wire-issue` - 2026-05-16T13:26:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/027bd325-a58f-4ab8-9b27-c48523dba115.jsonl`
- `/ll:refine-issue` - 2026-05-16T13:21:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d491efd-1e9f-48e7-91e7-1d0390a23fbc.jsonl`
- `/ll:format-issue` - 2026-05-16T13:15:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01820f79-a48a-417c-8b0a-1fede13c09b1.jsonl`
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
