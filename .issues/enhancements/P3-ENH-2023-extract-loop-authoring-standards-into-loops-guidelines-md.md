---
id: ENH-2023
title: Extract loop-authoring standards into standards/loops-guidelines.md
status: open
priority: P3
type: ENH
created: '2026-06-08'
captured_at: '2026-06-08T18:12:50Z'
discovered_date: '2026-06-08'
discovered_by: capture-issue
testable: false
decision_needed: true
labels:
- docs
- loops
- guidelines
confidence_score: 93
outcome_confidence: 68
score_complexity: 17
score_test_coverage: 12
score_ambiguity: 20
score_change_surface: 19
size: Very Large
parent: EPIC-1811
---

# ENH-2023: Extract loop-authoring standards into standards/loops-guidelines.md

## Summary

Loop-authoring rules, taxonomies, and conventions are currently fragmented across 6+ files with real duplication. Consolidate everything into a single canonical `standards/loops-guidelines.md` so that every other doc references it instead of restating it. This eliminates duplication, reduces drift, and gives authors one authoritative place to consult when designing FSM loops.

## Current Behavior

Loop-authoring rules (MR-1…MR-5), the 7-mode failure taxonomy, and FSM authoring conventions are duplicated verbatim across 6+ files: `.claude/CLAUDE.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/guides/LOOPS_GUIDE.md`, `agents/loop-specialist.md`, and `scripts/little_loops/fsm/validation.py`. No single canonical reference exists; each file must maintain its own copy of the same rules, creating ongoing drift risk.

## Expected Behavior

A canonical `standards/loops-guidelines.md` serves as the single authoritative source for all loop-authoring standards (MR-1…MR-5, optimizer error taxonomy, FSM authoring conventions, 7-mode failure taxonomy). All other files reference this document rather than duplicating its content, eliminating multi-location drift.

## Motivation

Today the standards live in at least six places (`.claude/CLAUDE.md`, `HARNESS_OPTIMIZATION_GUIDE.md`, `generalized-fsm-loop.md`, `LOOPS_GUIDE.md`, `agents/loop-specialist.md`, and `validation.py`), with the MR-1…MR-5 rules and the 7-mode failure taxonomy duplicated verbatim in multiple files. Every duplication is a future drift risk. The canonical "rules doc" pattern is missing.

## Implementation Steps

### New file: `standards/loops-guidelines.md`

Canonical home with these sections in order:

1. **Intro / how to use** — distinguish from `LOOPS_GUIDE.md` (tutorial) and `generalized-fsm-loop.md` (schema). State that `ll-loop validate` is machine enforcement and `scripts/little_loops/fsm/validation.py` is the code source of truth.
2. **Meta-loop design rules (MR-1…MR-5)** — move the rules table from `HARNESS_OPTIMIZATION_GUIDE.md`:90–95 (the cleanest existing version), plus MR-2 baseline-reference WARNING, the "MR-1 is load-bearing" note, suppression flags, and the worked MR-1 example (`loop-composer-adaptive` reassess gate, HARNESS_OPT:101–109). Note which are ERROR vs WARNING and the `meta_self_eval_ok / shared_state_ok / partial_route_ok / artifact_versioning(_ok)` flags.
3. **The canonical meta-loop shape** — one-paragraph summary of `diagnose → propose → apply → measure-externally` + link to `HARNESS_OPTIMIZATION_GUIDE.md § The Canonical Shape` for the full state table.
4. **Optimizer error taxonomy** — move the table from `HARNESS_OPTIMIZATION_GUIDE.md`:119–132.
5. **General FSM authoring conventions** — move both subsections from `generalized-fsm-loop.md`:1670–1715 ("Failure terminals must include a diagnostic action" and "Generator-evaluator loops: never route evaluate failures back to generate").
6. **Loop failure-mode taxonomy** — move the 7-mode table from `agents/loop-specialist.md`:57–65 (ambiguous-output, infinite-cycle, premature-termination, feature-stubbing, drift, self-evaluation bias, evaluator-trivial).
7. **Validating & measuring** — `ll-loop validate` (severities), `diagnose-evaluators` (Bernoulli variance < 0.05 / ≥10 runs), `run --baseline`, `audit-meta`. Link to `AUTOMATIC_HARNESSING_GUIDE.md § Validating Your Harness`.
8. **See Also** — LOOPS_GUIDE, HARNESS_OPTIMIZATION_GUIDE, AUTOMATIC_HARNESSING_GUIDE, generalized-fsm-loop, loop-specialist agent, the research paper, `validation.py`.

### Edits to existing files (replace duplication with references)

- **`.claude/CLAUDE.md` § Loop Authoring (94–162)** — collapse ~70 lines to ~20: keep compact MR-1…MR-5 summary table (rule · one-line · severity · suppress-flag) + "Full rationale, taxonomies, conventions, and the failure-mode taxonomy live in loops-guidelines.md." Keep `diagnose-evaluators` / `run --baseline` one-liners.
- **`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`** — replace §"The Design Rules (MR-1…MR-5)" (84–109) and §"The Optimizer Error Taxonomy" (113–132) with 2-line pointers; keep §"The Canonical Shape" (136–187).
- **`docs/generalized-fsm-loop.md` § Authoring Conventions (1668–1717)** — replace the two subsections with a stub pointer; keep the heading so existing anchors don't 404.
- **`docs/guides/LOOPS_GUIDE.md`** — replace duplicated Playwright rule (~1448) with a one-line reference; add LOOPS-GUIDELINES to meta-loop pointer (~3361–3366) and Further Reading (~4275).
- **`agents/loop-specialist.md` § Failure-Mode Taxonomy (53–65)** — replace definitional table with operational instruction ("classify against the modes in LOOPS-GUIDELINES § Loop failure-mode taxonomy; use the exact mode names") + keep the diagnosis-artifact checklist (87–93).
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `README.md` — add a `loops-guidelines.md` entry to the `## Documentation` section; adjust the "FSM authoring" description on the Loops Guide quick-link (line ~71) to reflect that authoring standards now live in LOOPS-GUIDELINES
- Update `CONTRIBUTING.md` — add `loops-guidelines.md` row to the `standards/` directory table (or create that section if absent) with a one-line description
- Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — append `(see [Loop Authoring Guidelines](../../standards/loops-guidelines.md) § Meta-Loop Design Rules)` after the MR-1 usage note in `§ check_contract` (~line 217) and `§ comparator` (~line 328); add loops-guidelines.md to the `## See Also` section (~line 1055)
- Update `scripts/little_loops/loops/README.md` — change the "loop authoring guidance" pointer at line 173 (currently `docs/ARCHITECTURE.md`) to include a reference to `standards/loops-guidelines.md`
- Update `skills/create-loop/loop-types.md` — add `(see [Loop Authoring Guidelines](../../standards/loops-guidelines.md) § Meta-Loop Design Rules)` after each of the two inline MR-1 compliance assertions (lines ~1488 and ~1505)
- Add wiring assertions to `scripts/tests/test_wiring_guides_and_meta.py` and `scripts/tests/test_wiring_skills_and_commands.py` — new `DOC_FILES_MUST_EXIST` and `DOC_STRINGS_PRESENT` entries confirming `standards/loops-guidelines.md` was created and all pointer replacements landed in the primary source files
- Update `docs/guides/LOOPS_GUIDE.md` ~line 3449–3451 — change the `## Harness Loops` blockquote `normative design rules … live in [CLAUDE.md § Loop Authoring]` to point to `[loops-guidelines.md § Meta-Loop Design Rules]` [wiring pass 3]
- Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` ToC (lines 26–27) — remove the two `#the-design-rules-mr-1mr-5` and `#the-optimizer-error-taxonomy` entries; both sections become 2-line stub pointers with no navigable heading [wiring pass 3]
- Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` `## See Also` (line 243) — change the `.claude/CLAUDE.md § Loop Authoring` description from "the normative MR-1…MR-5 rules" to "compact summary table (normative rules live in loops-guidelines.md)"; add a loops-guidelines.md entry [wiring pass 3]
- Add `DOC_STRINGS_ABSENT` assertions to `scripts/tests/test_wiring_guides_and_meta.py` and `test_wiring_skills_and_commands.py` — the only automated gate verifying that definitional content was removed from source files (not just added to loops-guidelines.md) [wiring pass 3]
- **Clarification for `agents/loop-specialist.md`**: Replace ONLY the definitional table at lines 53–65 with a pointer; the `## Failure modes observed` checklist (lines 87–93) and the `## Operating Guidelines` mode-name prohibition (line 145) **must retain all mode names inline** — these are the machine-greppable artifact schema, not taxonomy duplication. The absence assertion `"| **ambiguous-output** | The loop's exit predicate"` targets the table row format only; `- [ ] ambiguous-output` checklist entries must NOT be removed [wiring pass 4]
- Update `docs/guides/LOOPS_GUIDE.md` lines 2448–2452 — three standalone inline MR-1/MR-3/MR-4 prose-definition paragraphs in `### CLI-Anything Bootstrap`; replace each with a one-line pointer to `loops-guidelines.md § Meta-Loop Design Rules` [wiring pass 4]
- Note for `skills/create-loop/loop-types.md` line 1505 — raw `validation.py:76–94` line-number reference is embedded alongside the MR-1 pointer being added; verify this still resolves or update to the stable function-name anchor (`_validate_meta_loop_evaluation`) [wiring pass 4]
- **DO NOT MODIFY `skills/review-loop/reference.md`** — Lines 40–44 contain an MR-1…MR-5 validation-error reference table used by the review-loop skill itself. This is an operational reference (not a normative prose duplication) and is explicitly out of scope for ENH-2023. A new `DOC_STRINGS_PRESENT` assertion in `test_wiring_skills_and_commands.py` acts as an accidental-deletion guard. [wiring pass 5]
- Update `docs/index.md` — add `standards/loops-guidelines.md` entry to the `## Developer Documentation` section (implied by wiring-pass-2 test assertion but not previously listed as an explicit edit target) [wiring pass 5]
- **Resolve `docs_dir` boundary before creating `standards/loops-guidelines.md`**: `mkdocs.yml` sets `docs_dir: docs`; MkDocs cannot render `standards/loops-guidelines.md` because it is outside that boundary. Recommended resolution: create the file at `docs/standards/loops-guidelines.md` instead and update all pointer links accordingly (relative paths in cross-references must be adjusted). If `standards/` must stay at project root, add a symlink `docs/standards → ../../standards` or remove the `mkdocs.yml` nav entry and the corresponding `DOC_STRINGS_PRESENT` test assertion. [wiring pass 5]
- Update `mkdocs.yml` `nav:` block — add a nav entry for `docs/standards/loops-guidelines.md` (e.g., `- Loop Authoring Guidelines: standards/loops-guidelines.md` under an `Architecture:` or new `Standards:` group). Without this entry, MkDocs builds the file but it does not appear in the site sidebar navigation. [wiring pass 6]

## Integration Map

### Files to Create
- `standards/loops-guidelines.md` — new canonical home (does not exist yet)

### Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `.claude/CLAUDE.md` | 94–162 | Collapse ~70-line prose to ~20-line summary table + `[standards/loops-guidelines.md](../standards/loops-guidelines.md)` pointer |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | 84–109 | Replace `## The Design Rules (MR-1…MR-5)` with 2-line pointer to LOOPS-GUIDELINES; keep `## The Canonical Shape` (136–187) |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | 113–132 | Replace `## The Optimizer Error Taxonomy` with 2-line pointer |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | 26–27 | Remove ToC entries for `#the-design-rules-mr-1mr-5` and `#the-optimizer-error-taxonomy` — both sections become stub pointers with no subsections to navigate to [wiring pass 3] |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | 243 | Update `## See Also` — change description of `.claude/CLAUDE.md § Loop Authoring` from "the normative MR-1…MR-5 rules" to reflect that CLAUDE.md now holds only the compact summary table; add loops-guidelines.md as normative rules destination [wiring pass 3] |
| `docs/generalized-fsm-loop.md` | 1668–1717 | Replace the two `### Authoring Conventions` subsections with stub pointers; preserve the `## Authoring Conventions` heading so existing anchors don't 404 |
| `docs/guides/LOOPS_GUIDE.md` | 1448 | Replace the Playwright failure-routing blockquote with a one-line reference to LOOPS-GUIDELINES |
| `docs/guides/LOOPS_GUIDE.md` | 3361–3366 | Update the meta-loop pointer to include LOOPS-GUIDELINES as the normative rules home |
| `docs/guides/LOOPS_GUIDE.md` | 4272–4280 | Add `- [Loop Authoring Guidelines](../../standards/loops-guidelines.md) — ...` to `## Further Reading` |
| `docs/guides/LOOPS_GUIDE.md` | ~3449–3451 | Update `## Harness Loops` blockquote — replace `[CLAUDE.md § Loop Authoring](../../.claude/CLAUDE.md)` pointer with `[loops-guidelines.md § Meta-Loop Design Rules](../../standards/loops-guidelines.md)` [wiring pass 3] |
| `docs/guides/LOOPS_GUIDE.md` | 2448–2452 | Replace three standalone inline MR-1/MR-3/MR-4 prose-definition paragraphs in `### CLI-Anything Bootstrap` with one-line pointers to `loops-guidelines.md § Meta-Loop Design Rules` [wiring pass 4] |
| `agents/loop-specialist.md` | 53–65 | Replace the definitional 7-mode table with operational pointer ("classify against modes in LOOPS-GUIDELINES § Loop failure-mode taxonomy; use exact mode names"); keep checklist at 87–93 and Operating Guidelines mode-name prohibition at line 145 intact |
| `README.md` | Documentation section | Add `standards/loops-guidelines.md` entry to the standards/reference listing; adjust "FSM authoring" description on the Loops Guide quick-link |
| `CONTRIBUTING.md` | ~169 | Add `loops-guidelines.md` row to the `standards/` directory table (or create that section if absent) |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | ~217, ~328, ~1055 | Add `(see [Loop Authoring Guidelines](../../standards/loops-guidelines.md) § Meta-Loop Design Rules)` after two inline MR-1 usage notes (§ `check_contract` and § `comparator`); add loops-guidelines.md to `## See Also` |
| `scripts/little_loops/loops/README.md` | 173 | Update "loop authoring guidance" pointer to reference `standards/loops-guidelines.md` |
| `skills/create-loop/loop-types.md` | ~1488, ~1505 | Add `(see [loops-guidelines.md](../../standards/loops-guidelines.md) § Meta-Loop Design Rules)` pointer after each MR-1 compliance assertion in the meta-optimize template section |
| `scripts/tests/test_wiring_guides_and_meta.py` | `DOC_FILES_MUST_EXIST`, `DOC_STRINGS_PRESENT` | Add existence assertion for `standards/loops-guidelines.md` and pointer-presence assertions in `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md` [wiring pass 2] |
| `scripts/tests/test_wiring_skills_and_commands.py` | `DOC_STRINGS_PRESENT` | Add assertion that `agents/loop-specialist.md` contains `loops-guidelines.md` pointer after inline taxonomy is replaced [wiring pass 2] |
| `docs/index.md` | `## Developer Documentation` section | Add `standards/loops-guidelines.md` entry to the documentation landing page [wiring pass 5] |
| `mkdocs.yml` | `nav:` block | Add nav entry for `docs/standards/loops-guidelines.md` (e.g., under `Architecture:` or a new `Standards:` section) — without this entry the file builds but does not appear in the MkDocs sidebar [wiring pass 6] |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**MR-2 source discrepancy**: The issue says to include "MR-2 baseline-reference WARNING" from `HARNESS_OPTIMIZATION_GUIDE.md:90–95`, but MR-2 does **not** appear in that table (only MR-1, MR-3, MR-4, MR-5 are rows). MR-2's primary sources are:
- Code: `scripts/little_loops/fsm/validation.py:1079–1094` (`_validate_meta_loop_evaluation`, the baseline-reference WARNING)
- Most complete prose: `docs/reference/CLI.md:569` — "A meta-loop should reference a captured baseline value in a later evaluator (`evaluate.previous`, `evaluate.target`, or `evaluate.source`). This ensures a measure→propose→apply→re-measure spine is present."

**Additional files not in Implementation Steps** that carry duplicated rule content:
- `docs/reference/CLI.md:562–574` — inline MR-1…MR-5 full prose rules under `ll-loop validate`. Whether to replace with a LOOPS-GUIDELINES pointer here is a scope call (the CLI reference currently self-contains the rules for the `validate` command); the issue scopes this out, but the docs team should be aware of it.
- `docs/reference/API.md:4157–4160` — suppress flag documentation (`meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`, `artifact_versioning_ok`).
- `skills/review-loop/reference.md:40–44` — compact MR rules table with suppress flags.

**CLAUDE.md link format** for the new pointer: `[standards/loops-guidelines.md](../standards/loops-guidelines.md)` (relative to `.claude/`).

**Anchor conventions** for headings in loops-guidelines.md: GitHub-style — lowercase, spaces → hyphens, backticks stripped, parens stripped. Example: `## The Design Rules (MR-1…MR-5)` → `#the-design-rules-mr-1mr-5`.

**All 18 line-number claims in the Integration Map verified accurate** against the current codebase (second refinement pass, 2026-06-08). No stale anchors found.

**`.codex/agents/loop-specialist.toml`** — auto-generated Codex mirror of `agents/loop-specialist.md` containing the full 7-mode failure taxonomy (lines 32–38). Since `agents/loop-specialist.md` is in "Files to Modify", the implementer must regenerate this mirror after the edit: run `ll-adapt-agents-for-codex` as a cleanup step. Add this to the post-implementation checklist.

**`scripts/little_loops/loops/integrate-sdk.yaml` lines 205–211** — embeds the full 7-mode taxonomy as a literal table inside a loop YAML action prompt. Out of scope for this doc-only issue, but a latent drift risk if the taxonomy names ever change.

**Expected remaining grep matches after implementation** (not errors — these are intentional or out-of-scope):
- `docs/reference/CLI.md:568–577` — full MR-1…MR-5 inline (out-of-scope per issue note; CLI reference self-contains rules for `validate` command)
- `docs/reference/API.md:4157–4772` — suppress flags in `FSMLoop` pseudocode, MR-1–MR-4 in `validate_fsm` checks (note: MR-5 absent from the 4769–4772 list — pre-existing gap, out of scope)
- `skills/review-loop/reference.md:40–44` — compact MR-1…MR-5 table (out-of-scope per issue note)
- `scripts/little_loops/loops/integrate-sdk.yaml:205–211` — taxonomy in action prompt (operational loop, out-of-scope)
- `.codex/agents/loop-specialist.toml` — regenerate via `ll-adapt-agents-for-codex` after source update
- `CHANGELOG.md` — historical release notes, expected
- `scripts/tests/test_fsm_validation.py`, `test_fsm_schema.py`, `test_rn_implement.py` — test infrastructure, expected
- `scripts/little_loops/fsm/validation.py`, `schema.py` — authoritative code source of truth, expected
- `docs/reference/loops.md` — additional reference file with rule citations; add to grep checklist post-implementation if matches surface

**MR-2 suppress flag** (`validation.py:_validate_meta_loop_evaluation()` lines 1043–1096): MR-1 and MR-2 are both suppressed by `meta_self_eval_ok: true`; there is no separate MR-2 flag. Function docstring at line 1044–1049 states this explicitly.

**Optimizer Error Taxonomy — exact 8 row names** (from `HARNESS_OPTIMIZATION_GUIDE.md:113–133`): Redundant Duplication, Hardcoding, Task-specific Addition, Hallucination, Overengineering, Direct Performance-degrading Update, Overgeneralized Heuristic, Safety Violation. (8 entries — use these exact names when drafting `## The Optimizer Error Taxonomy` in loops-guidelines.md.)

**FSM authoring convention heading names confirmed** (from `generalized-fsm-loop.md:1668–1717`):
- `### Failure Terminals Must Include a Diagnostic Action` (lines 1670–1697): `action_type: prompt` must NOT be placed on the `terminal: true` state; use a preceding `diagnose` state and route `on_error: diagnose`.
- `### Generator-Evaluator Loops: Never Route Evaluate Failures Back to Generate` (lines 1699–1715): `on_no` and `on_error` route forward (to `score`), never back to `generate`.

### Tests
- `scripts/tests/test_fsm_validation.py` — existing coverage for `validation.py` MR rules; no changes needed (doc-only issue)
- `scripts/tests/test_fsm_schema.py` — existing schema coverage; no changes needed

_Wiring pass added by `/ll:wire-issue` (second pass):_
- `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_FILES_MUST_EXIST` entry `("standards/loops-guidelines.md", "ENH-2023")` and `DOC_STRINGS_PRESENT` entries for `"loops-guidelines.md"` in `mkdocs.yml`, `docs/index.md`, and `.claude/CLAUDE.md` to confirm pointer replacements landed [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — add `DOC_STRINGS_PRESENT` entry `("agents/loop-specialist.md", "loops-guidelines.md", "ENH-2023")` to confirm taxonomy pointer was added after the inline table is replaced [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` (third pass) — exact test entry tuples:_

**`test_wiring_guides_and_meta.py` — append to `DOC_FILES_MUST_EXIST`:**
```python
("standards/loops-guidelines.md", "ENH-2023"),
```

**`test_wiring_guides_and_meta.py` — append to `DOC_STRINGS_PRESENT`:**
```python
("README.md", "loops-guidelines.md", "ENH-2023"),
("CONTRIBUTING.md", "loops-guidelines.md", "ENH-2023"),
(".claude/CLAUDE.md", "loops-guidelines.md", "ENH-2023"),
("standards/loops-guidelines.md", "MR-1", "ENH-2023"),
("standards/loops-guidelines.md", "diagnose → propose → apply → measure-externally", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_PRESENT`:**
```python
("agents/loop-specialist.md", "loops-guidelines.md", "ENH-2023"),
```

### Codebase Research Findings

_Added by `/ll:refine-issue` (fourth pass) — code accuracy note:_

**`action_stall` missing from CLAUDE.md prose list**: `validation.py:NON_LLM_EVALUATOR_TYPES` (line 81) includes `action_stall` as a valid MR-1-satisfying evaluator type, as does the MR-1 error message (`validation.py:1069`): `"exit_code, output_numeric, convergence, diff_stall, action_stall, mcp_result"`. The current CLAUDE.md § Loop Authoring prose list and `HARNESS_OPTIMIZATION_GUIDE.md` both omit it. When authoring the MR-1 row in loops-guidelines.md, source the non-LLM evaluator type list from `NON_LLM_EVALUATOR_TYPES` in `validation.py:81` for accuracy. Code-accurate list: `exit_code`, `output_numeric`, `convergence`, `diff_stall`, `action_stall`, `mcp_result`.

### Codebase Research Findings

_Added by `/ll:wire-issue` (third pass) — additional test assertions:_

**`test_wiring_guides_and_meta.py` — append to `DOC_STRINGS_PRESENT`** (5 additional entries verifying wiring touchpoints landed):
```python
("docs/guides/AUTOMATIC_HARNESSING_GUIDE.md", "loops-guidelines.md", "ENH-2023"),
("scripts/little_loops/loops/README.md", "loops-guidelines.md", "ENH-2023"),
("standards/loops-guidelines.md", "ambiguous-output", "ENH-2023"),
("standards/loops-guidelines.md", "Redundant Duplication", "ENH-2023"),
("standards/loops-guidelines.md", "Failure Terminals Must Include a Diagnostic Action", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_PRESENT`** (1 additional entry):
```python
("skills/create-loop/loop-types.md", "loops-guidelines.md", "ENH-2023"),
```

**`test_wiring_guides_and_meta.py` — append to `DOC_STRINGS_ABSENT`** (4 new entries — only automated gate confirming source content was removed, not just added to loops-guidelines.md):
```python
("docs/guides/HARNESS_OPTIMIZATION_GUIDE.md", "| **MR-1** | Every `check_semantic`", "ENH-2023"),
("docs/guides/HARNESS_OPTIMIZATION_GUIDE.md", "| **Redundant Duplication** |", "ENH-2023"),
("docs/generalized-fsm-loop.md", "do NOT put `action_type: prompt` directly on the `terminal: true` state", "ENH-2023"),
("docs/generalized-fsm-loop.md", "Never Route Evaluate Failures Back to Generate", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_ABSENT`** (1 new entry):
```python
("agents/loop-specialist.md", "| **ambiguous-output** | The loop's exit predicate", "ENH-2023"),
```

### Codebase Research Findings

_Added by `/ll:wire-issue` (fourth pass) — additional DOC_STRINGS_ABSENT entries confirming source removals in CLAUDE.md, LOOPS_GUIDE.md, and HARNESS_OPTIMIZATION_GUIDE.md:_

**`test_wiring_guides_and_meta.py` — append to `DOC_STRINGS_ABSENT`** (6 additional entries):
```python
# CLAUDE.md § Loop Authoring collapse: definitional prose that will be removed
(".claude/CLAUDE.md", "~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%)", "ENH-2023"),
(".claude/CLAUDE.md", "`ll-loop validate` enforces rule 2 as ERROR severity", "ENH-2023"),
# LOOPS_GUIDE.md Harness Loops blockquote: old CLAUDE.md pointer replaced by LOOPS-GUIDELINES ref
("docs/guides/LOOPS_GUIDE.md", "normative design rules (diagnosis-first", "ENH-2023"),
# HARNESS_OPTIMIZATION_GUIDE.md ToC entries removed (lines 26–27)
("docs/guides/HARNESS_OPTIMIZATION_GUIDE.md", "#the-design-rules-mr-1mr-5", "ENH-2023"),
("docs/guides/HARNESS_OPTIMIZATION_GUIDE.md", "#the-optimizer-error-taxonomy", "ENH-2023"),
# HARNESS_OPTIMIZATION_GUIDE.md See Also description reworded (line 243)
("docs/guides/HARNESS_OPTIMIZATION_GUIDE.md", "the normative MR-1…MR-5 rules", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_ABSENT`** (1 additional entry — Codex toml mirror regenerated):
```python
(".codex/agents/loop-specialist.toml", "| **ambiguous-output** | The loop's exit predicate", "ENH-2023"),
```

### Codebase Research Findings

_Added by `/ll:wire-issue` (fifth pass) — new test assertions and docs_dir clarification:_

**`test_wiring_guides_and_meta.py` — append to `DOC_STRINGS_ABSENT`** (3 new entries confirming the inline MR prose blocks were removed from `LOOPS_GUIDE.md` § CLI-Anything Bootstrap, lines 2448–2452):
```python
("docs/guides/LOOPS_GUIDE.md", "**Meta-loop discipline (MR-1)**:", "ENH-2023"),
("docs/guides/LOOPS_GUIDE.md", "**Per-run artifact isolation (MR-3)**:", "ENH-2023"),
("docs/guides/LOOPS_GUIDE.md", "**Partial-route dead-end guard (MR-4)**:", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_ABSENT`** (1 new entry confirming the stale line-number reference was removed from `loop-types.md` line 1505):
```python
("skills/create-loop/loop-types.md", "validation.py:76–94", "ENH-2023"),
```

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_PRESENT`** (1 new accidental-deletion guard — fires if `skills/review-loop/reference.md` MR table is accidentally cleared):
```python
("skills/review-loop/reference.md", "| MR-1 | Meta-loop (writes harness artifacts", "ENH-2023"),
```

**`docs_dir` boundary**: `mkdocs.yml` uses `docs_dir: docs`; `standards/loops-guidelines.md` is outside this directory and cannot be referenced in the `nav:` block as written. Recommended resolution: create the canonical file at `docs/standards/loops-guidelines.md` and adjust all relative pointer links (e.g., `.claude/CLAUDE.md` pointer becomes `../docs/standards/loops-guidelines.md`). If project-root `standards/` is preferred, either add a symlink or drop the `mkdocs.yml` nav entry and remove the corresponding `DOC_STRINGS_PRESENT` test. Verified by Agent 2 wiring pass 5.

### Codebase Research Findings

_Added by `/ll:wire-issue` (sixth pass) — mkdocs.yml nav gap and test routing corrections:_

**`mkdocs.yml` nav entry missing** — The file is not in "Files to Modify" but requires a `nav:` addition for `docs/standards/loops-guidelines.md`. Without it, the canonical doc builds but is not navigable in the MkDocs sidebar.

**`test_wiring_skills_and_commands.py` — append to `DOC_STRINGS_PRESENT`** (1 new entry — verifies mkdocs.yml nav entry was added; all existing `mkdocs.yml` assertions live in this file per established convention):
```python
("mkdocs.yml", "loops-guidelines", "ENH-2023"),
```

**Test routing clarification — `.claude/CLAUDE.md` assertion**: The issue spec (wiring pass 2) assigns the `.claude/CLAUDE.md` pointer assertion to `test_wiring_guides_and_meta.py`. However, all existing `.claude/CLAUDE.md` assertions in the test suite live in `test_wiring_cli_registry.py` (per established convention — that file owns `.claude/CLAUDE.md`, `commands/help.md`, and `docs/reference/CLI.md` assertions). Recommend moving `(".claude/CLAUDE.md", "loops-guidelines.md", "ENH-2023")` from `test_wiring_guides_and_meta.py` to `test_wiring_cli_registry.py`:

**`test_wiring_cli_registry.py` — append to `DOC_STRINGS_PRESENT`** (replaces the same entry currently spec'd for `test_wiring_guides_and_meta.py`):
```python
(".claude/CLAUDE.md", "loops-guidelines.md", "ENH-2023"),
```

**Path consistency note**: All test assertions currently use `"standards/loops-guidelines.md"` (project root). If the docs_dir boundary is resolved by using `docs/standards/loops-guidelines.md` (recommended), update all test assertion paths accordingly — including the `DOC_FILES_MUST_EXIST` entry `("standards/loops-guidelines.md", "ENH-2023")` and the five `DOC_STRINGS_PRESENT` entries targeting the file's own content.

### Documentation
- `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` — the empirical study behind the MR rules; loops-guidelines.md should link to it in the See Also section (as HARNESS_OPTIMIZATION_GUIDE.md line 244 already does)

_Wiring pass added by `/ll:wire-issue` (second pass):_
- `docs/ARCHITECTURE.md` — references MR-1…MR-4 and loop-specialist agent; advisory review for whether an additional `[Loop Authoring Guidelines](../standards/loops-guidelines.md)` mention benefits readers here (not required; no inline rule duplication confirmed) [Agent 1 finding]

## Division of Responsibility

- `loops-guidelines.md` = normative rules, taxonomies, and conventions. **New canonical home.**
- `LOOPS_GUIDE.md` = tutorial/reference (how to build & run loops). Unchanged in role.
- `HARNESS_OPTIMIZATION_GUIDE.md` = how-to deep-dive for building harness optimizers. Keeps its how-to; drops rule/taxonomy copies.
- `validation.py` = enforcement source of truth; guidelines doc explains the *why* and points at it.

## Scope Boundaries

- **Out of scope**: No code changes to `validation.py` / `schema.py` — doc-only.
- **Out of scope**: Rewriting or reorganizing `LOOPS_GUIDE.md` (tutorial role unchanged).
- **Out of scope**: Changes to the FSM schema format or `ll-loop` CLI behavior.

## Verification

- `ll-check-links` — confirm no broken markdown links after re-pointing.
- Grep that MR-1…MR-5 / "Optimizer Error Taxonomy" / "never route evaluate failures back to generate" / the 7 mode names now appear authoritatively only in `loops-guidelines.md` (plus the kept CLAUDE.md summary table and code).
- `ll-loop validate <any meta-loop>` still runs unchanged.
- Manual read-through: every "replaced" section resolves to a working `standards/loops-guidelines.md` anchor.
- Run `ll-adapt-agents-for-codex` after updating `agents/loop-specialist.md` to regenerate `.codex/agents/loop-specialist.toml` with the updated failure taxonomy pointer.

## Impact

- **Priority**: P3 - Documentation improvement with no runtime behavior change; reduces ongoing drift risk
- **Effort**: Medium - Requires moving content from 6+ source files, rewriting cross-references throughout the docs tree, and validating links
- **Risk**: Low - Doc-only change; `validation.py`, `schema.py`, and all CLI behavior are untouched
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09; updated 2026-06-10_

**Readiness Score**: 93/100 → PROCEED *(−5 from 98; docs_dir path decision unresolved, ENH-1903 coordination pending)*
**Outcome Confidence**: 68/100 → LOW *(−5 from 73; wiring passes 5–6 introduced path ambiguity in test assertions)*

### Outcome Risk Factors
- File path decision must be resolved before starting — `docs/standards/loops-guidelines.md` vs project-root `standards/loops-guidelines.md` cascades through 7+ DOC_STRINGS_PRESENT/ABSENT assertion paths and all relative links in pointer updates; `mkdocs.yml` `docs_dir: docs` means project-root location cannot be rendered by MkDocs; resolve before starting to avoid rework
- No automated semantic validation of assembled content — DOC_STRINGS_PRESENT/ABSENT entries confirm structural placement and source removal, but cannot validate that `loops-guidelines.md` faithfully reproduces source passages; manual read-through comparing each assembled section against its source is required after assembly
- ENH-1903 coordination required — ENH-1903 (open) touches the same CLAUDE.md § Loop Authoring section; the compaction pass must sequence after ENH-1903 lands or explicitly incorporate its `ll-parallel` note before merging; see Scope Boundary section

## Session Log
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `12a4304b-88ca-46d1-8a44-8ca899bcca11.jsonl`
- `/ll:wire-issue` - 2026-06-10T04:34:06 - `a169cf57-e620-4e48-972e-dd9665d2a3ce.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `753d6ec3-0599-4602-b86b-683f82320685.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `62b84f66-68e2-4bb7-8596-0007f0868fbf.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `37b87700-9806-4243-a3d1-73204120aa82.jsonl`
- `/ll:wire-issue` - 2026-06-10T01:15:00 - `07dab59b-4558-495b-ac0c-665428a59e71.jsonl`
- `/ll:wire-issue` - 2026-06-10T00:47:56 - `92c7b00f-dcbe-4b46-b3a2-9decda4c7786.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `444a3d6e-13a2-4c42-b9b3-615482739169.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:confidence-check` - 2026-06-08T23:55:00Z - `d5e3ed6c-5fc1-4d3d-b2dd-2db860f934e4.jsonl`
- `/ll:wire-issue` - 2026-06-09T04:44:22 - `8bbb2121-bb5c-418c-9148-2f2f52c8d346.jsonl`
- `/ll:confidence-check` - 2026-06-08T23:00:00Z - `53cf785d-6feb-4b2a-9d9f-8d44f50883a4.jsonl`
- `/ll:confidence-check` - 2026-06-08T21:00:00Z - `8b26e8eb-6fcd-4951-9ead-09b00eede5aa.jsonl`
- `/ll:refine-issue` - 2026-06-08T20:47:03 - `0c6be1b2-0553-4e28-bb1f-1f06c6ddae23.jsonl`
- `/ll:confidence-check` - 2026-06-08T20:30:00Z - `6392fbc2-f8f1-4751-8018-9e14c0b2037d.jsonl`
- `/ll:refine-issue` - 2026-06-08T20:08:50 - `c36c1c68-9f6e-46e8-8abb-d442d3aac92e.jsonl`
- `/ll:wire-issue` - 2026-06-08T19:09:30 - `56fd44d8-174d-4ee6-8034-5fd93973393c.jsonl`
- `/ll:refine-issue` - 2026-06-08T18:58:34 - `832c6be5-7dd6-4f1a-a8db-8c7f44c41c9f.jsonl`
- `/ll:confidence-check` - 2026-06-08T18:40:00Z - `a728ce61-598a-41b4-88fb-5495fbc177b9.jsonl`
- `/ll:wire-issue` - 2026-06-08T18:35:23 - `f3c9a78c-ed08-41a1-bd9a-0a5eec650264.jsonl`
- `/ll:refine-issue` - 2026-06-08T18:26:48 - `a7baee9f-1f49-4f76-a6cf-ba753c6eb490.jsonl`
- `/ll:format-issue` - 2026-06-08T18:20:22 - `d2cb716f-e5d7-4d44-ae52-4ac557239353.jsonl`
- `/ll:capture-issue` - 2026-06-08T18:12:50Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/33b0ec92-c443-4316-85ac-84716a417c24.jsonl`

---

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): This issue's compaction pass on `.claude/CLAUDE.md` § Loop Authoring (lines 94–162) must be **coordinated with ENH-1903**. ENH-1903 adds a note to the same CLAUDE.md CLI Tools section documenting `ll-parallel` as the canonical parallel substrate. If ENH-2023 lands before ENH-1903, the compaction pass must explicitly preserve or incorporate the `ll-parallel` note — otherwise the ENH-1903 addition will be silently dropped in the diff. Recommended sequence: ENH-1903 lands first (or its CLAUDE.md addition is included in ENH-2023's diff); ENH-2023 lands second.

## Status

- [x] Issue captured
- [ ] Implementation
- [ ] Verification
