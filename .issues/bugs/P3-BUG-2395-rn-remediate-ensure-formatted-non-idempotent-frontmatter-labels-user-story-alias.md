---
id: BUG-2395
title: rn-remediate ensure_formatted re-formats every run (frontmatter labels + User
  Story/Use Case alias)
type: bug
status: open
priority: P3
captured_at: '2026-06-29T16:59:29Z'
discovered_date: 2026-06-29
discovered_by: capture-issue
relates_to:
- ENH-2360
- ENH-1392
- ENH-2398
- ENH-2399
labels:
- rn-remediate
- format-guard
- idempotency
- loop
decision_needed: false
confidence_score: 100
outcome_confidence: 88
score_complexity: 8
score_test_coverage: 16
score_ambiguity: 10
score_change_surface: 8
implementation_order_risk: true
---

# BUG-2395: rn-remediate ensure_formatted re-formats every run (frontmatter labels + User Story/Use Case alias)

## Summary

The `ensure_formatted` Phase-0 gate in `rn-remediate.yaml` is **non-idempotent**:
it demands `## Labels` and `## User Story` as **body** headers for feature issues,
but the canonical issue format cannot supply either, so `/ll:format-issue --auto`
never satisfies the gate. Every `rn-implement`/`rn-remediate` run that re-encounters
such an issue re-detects the same "missing required sections" gap and burns a
redundant format pass that changes nothing the gate checks for. Surfaced while
auditing why `rn-implement` re-formatted FEAT-2387 across runs 155343 and 161824.

## Current Behavior

`ensure_formatted` (`scripts/little_loops/loops/rn-remediate.yaml:79-140`) flags a
required template section as missing whenever `"## " + title` is absent from the
issue body (`rn-remediate.yaml:124`):

```python
missing = [t for t in required if ("## " + t) not in body]
```

For `feat`, `ll-issues sections feat` marks `Labels` (common) and `User Story`
(type) as required. FEAT-2387 carries its labels in **frontmatter** (`labels:`,
populated: host-compat, portfolio, init, upgrade) and uses a `## Use Case`
section. The gate therefore prints, on every run:

```
Needs formatting — missing required sections for FEAT-2387: Labels; User Story
```

routes to `format_issue` → `/ll:format-issue --auto`, which adds **neither**
section (verified: the formatted file still has `## Use Case`, no `## Labels`,
no `## User Story`), then routes to `assess`. The next run repeats the identical
detection. Bounded to one pass *within* a run (`format_issue` → `assess`
unconditionally, no oscillation), but wasteful *across* runs.

## Expected Behavior

The format gate is idempotent: once an issue is in canonical form, a subsequent
run does NOT re-flag it for formatting. Specifically:

- Sections migrated to frontmatter (`Labels`, per ENH-1392) are not demanded as
  body headers.
- Known section aliases (`User Story` ⇄ `Use Case`) count as satisfied.

## Steps to Reproduce

1. Take any feature issue whose labels live in `labels:` frontmatter (canonical
   post-ENH-1392) and that uses `## Use Case` rather than `## User Story` — e.g.
   `FEAT-2387`.
2. Run `ll-loop run rn-remediate "FEAT-2387"` (or `rn-implement` with it queued).
3. Observe `ensure_formatted` emit `Needs formatting — missing required sections
   ... Labels; User Story` and run `format_issue`.
4. Run it again. Observe the identical detection and a second redundant format
   pass — the gate never converges.

## Root Cause

`rn-remediate.yaml:124` (`ensure_formatted`) equates "required section" with the
literal presence of a `## <title>` body header for **every** required title from
`ll-issues sections feat`. Two of those required titles are unsatisfiable by the
canonical formatter:

- **Labels** — `ll-migrate-labels` (ENH-1392) moved labels from a `## Labels`
  body section into the `labels:` frontmatter field. The required-section
  template still lists `Labels` as a required **body** section, and
  `format-issue --auto` won't recreate the deprecated location.
- **User Story** — the feature template requires `## User Story`; capture/refine
  produce `## Use Case` (the v2.0 rename noted in capture-issue's own docs), and
  `format-issue --auto` does not synthesize a User Story.

Either deficiency leaves the gate permanently unsatisfiable.

## Proposed Fix

Primary (gate-level, in `ensure_formatted`):

```python
FRONTMATTER_SECTIONS = {"Labels"}          # ENH-1392 moved these out of the body
ALIASES = {"User Story": ["User Story", "Use Case"]}
missing = []
for t in required:
    if t in FRONTMATTER_SECTIONS:
        continue
    titles = ALIASES.get(t, [t])
    if not any(("## " + a) in body for a in titles):
        missing.append(t)
```

Deeper (upstream, preferred): stop marking `Labels` as a required **body**
section in the `feat`/`bug`/`enh` templates returned by `ll-issues sections`
(it is a frontmatter field post-ENH-1392), so every consumer — `ensure_formatted`,
`format-issue --check`, etc. — stops chasing a phantom section. Reconcile the
`User Story`/`Use Case` naming in one direction across the template and the
formatter.

> **Selected:** Option B (Upstream template fix) — three JSON edits in `*-sections.json` propagate automatically to `is_formatted()` and `ensure_formatted` via existing deprecated guard; no Python or YAML code changes required.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-29.

**Selected**: Option B — Upstream template fix (`*-sections.json`)

**Reasoning**: The three `*-sections.json` template files are the single source of truth consumed by both `is_formatted()` and `ensure_formatted` at runtime — demoting `Labels.required: true` → `false` and `User Story.level: "required"` → `"optional"` cascades the fix to all consumers with zero Python or YAML code changes. `is_formatted()` already has the deprecated guard (`not defn.get("deprecated", False)`) that makes User Story disappear automatically, and `ensure_formatted` reads the live JSON from `ll-issues sections`, so template edits propagate directly. Option A would have created a parallel re-implementation of required-section extraction logic in the YAML heredoc with no codebase precedent and a test-string coupling maintenance burden.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (gate-level fix) | 1/3 | 1/3 | 1/3 | 2/3 | 5/12 |
| Option B (upstream template fix) | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |

**Key evidence**:
- **Option A**: Reuse score 1/3 — introduces a `FRONTMATTER_SECTIONS` dict pattern with no codebase precedent; creates a second parallel copy of required-section extraction logic (`is_formatted()` is the reference but not callable from YAML heredoc); test-string coupling requires manual sync with YAML on each change.
- **Option B**: Reuse score 3/3 — follows the exact `deprecated: true` + `required: false` / `level: "optional"` pattern already applied to Context, Edge Cases, UI/UX Details, and five other sections; `ensure_formatted` inline Python queries `required`/`level` live via `ll-issues sections` so template change propagates without touching the YAML; no currently-passing tests break.

## Integration Map

- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` state (~L79-140), the gate body to fix.
- `ll-issues sections` provider — the required-section template marking `Labels` / `User Story` required.
- `skills/format-issue` — the formatter that must produce whatever the gate requires (or vice-versa).
- ENH-2360 — the (done) enhancement that introduced this format guard; this bug is a regression in its idempotency.
- ENH-1392 / `ll-migrate-labels` — moved labels to frontmatter, the origin of the `Labels` mismatch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify — Selected: Option B (template-only)

> **CORRECTION (2026-06-29, post-decide):** The earlier "Both Options (Required
> Regardless)" claim that `issue_parser.py:is_formatted()` needs a
> `FRONTMATTER_SECTIONS = {"Labels"}` Python bypass is a **stale Option-A
> artifact and is WRONG under the selected Option B.** Verified against source:
> `is_formatted()` (`issue_parser.py:84-96`) builds its `required` set *live*
> from the template, honoring `required`/`level`/`deprecated`. Demoting
> `Labels.required → false` removes Labels from that set automatically; `User
> Story` is already `deprecated: true` so `is_formatted()` already excludes it.
> **No `issue_parser.py` change is required.** Likewise the `ensure_formatted`
> gate reads `required`/`level` live via `ll-issues sections`, so the same
> template edits fix the gate with **no YAML change.**
>
> **Real source surface under Option B = 5 one-line JSON edits** (see below).
> The struck Option-A scaffolding (`FRONTMATTER_SECTIONS` Python edit,
> `TestIsFormatted` shell-execution tests) is removed from the plan.

The five edits:
- `scripts/little_loops/templates/feat-sections.json` — `common_sections.Labels.required: true → false` AND `type_sections.User Story.level: required → optional` (already `deprecated: true`)
- `scripts/little_loops/templates/bug-sections.json` — `common_sections.Labels.required: true → false`
- `scripts/little_loops/templates/enh-sections.json` — `common_sections.Labels.required: true → false`
- `scripts/little_loops/templates/epic-sections.json` — `common_sections.Labels.required: true → false`

**Regression check (verified, NOT a risk):** after demotion the per-type
`required` set stays non-empty (feat/bug/enh retain 6 sections incl. Summary,
Current/Expected Behavior, Impact, Status + their type section; epic retains
Goal/Scope/Children + Summary/Impact/Status). So `is_formatted()` does NOT
short-circuit to vacuous `True` (the `if not required: return True` guard at
`issue_parser.py:92` is not reached), and
`test_fmt_x_for_missing_required_sections` stays green.

#### ~~Files to Modify — Gate-Level Fix (Option A)~~ (NOT SELECTED — retained for history)
- `scripts/little_loops/loops/rn-remediate.yaml` lines 102–127 — inline Python inside `ensure_formatted` `action:` block; add `FRONTMATTER_SECTIONS = {"Labels"}` and `ALIASES = {"User Story": ["User Story", "Use Case"]}` dicts before the `missing` list comprehension, update that comprehension to skip frontmatter sections and accept any alias

#### Files to Modify — Upstream Template Fix (Option B, preferred)
- `scripts/little_loops/templates/feat-sections.json` — two changes: (1) `type_sections.User Story` (line 148): change `"level": "required"` → `"level": "optional"` since the entry is already `deprecated: true`; (2) `common_sections.Labels` (line 113): change `"required": true` → `"required": false` (it is a frontmatter field post-ENH-1392, not a body section)
- `scripts/little_loops/templates/bug-sections.json` — same `common_sections.Labels` change (also has `"required": true`)
- `scripts/little_loops/templates/enh-sections.json` — same `common_sections.Labels` change (also has `"required": true`)
- `scripts/little_loops/templates/epic-sections.json` — same `common_sections.Labels` change (`"required": true` at line 61); EPIC issues with frontmatter labels trigger the same false-positive in `ensure_formatted` [wiring pass 2]
- If upstream fix only: `scripts/little_loops/loops/rn-remediate.yaml` inline Python may still benefit from a `deprecated` guard (`if meta.get("deprecated"): continue`) to future-proof against new deprecated-but-still-required entries

#### Dependent Files (Context / Callers)
- `scripts/little_loops/cli/issues/sections.py` — `cmd_sections()`: passthrough that reads and prints the template JSON verbatim; no logic change needed
- `scripts/little_loops/issue_template.py` — `resolve_templates_dir()`, `assemble_issue_markdown()`: assembler still includes `Labels` in `creation_variants.full.include_common`; new issues still get `## Labels` in body until the assembler is updated (separate concern, not blocking this bug)
- `scripts/little_loops/cli/migrate_labels.py` — `_migrate_content()` / `_remove_labels_section()`: confirms `## Labels` is permanently stripped from body post-ENH-1392; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/sync.py` — calls `load_issue_sections()` at line 700; template consumer for GitHub sync issue creation; unaffected by `required` flag changes but affected if `include_common` lists change [Agent 1 finding]

#### Tests (Option B — deterministic acceptance gate)

The acceptance signal is **deterministic** (pure Python/shell, no LLM, no
loop-rerun): a frontmatter-labels + `## Use Case` feat issue must report
formatted via both `is_formatted()` and the gate shell. This is cheaper and
higher-signal than "run rn-remediate twice."

- `scripts/tests/test_issue_parser.py` — add `TestIsFormatted` with **direct
  Python unit tests** (no shell execution): (a) a feat fixture with `labels:`
  frontmatter, `## Use Case`, no `## Labels`/`## User Story`, and NO
  `/ll:format-issue` session-log line → `is_formatted()` returns `True` via
  criterion 2 (structural path — the path this fix exercises); (b) a sparse
  fixture missing a genuinely-required section (e.g. `## Impact`) → returns
  `False` (proves demotion didn't gut the check). Use `templates_dir` pointing
  at the real templates. Model after `test_refine_status.py:1245`.
- `scripts/tests/test_rn_remediate.py` — add `TestEnsureFormatted` exercising the
  gate's inline shell on a feat fixture with frontmatter labels + `## Use Case`:
  assert exit 0 ("Formatted: all required sections present"). Model after
  `TestDiagnoseAmbiguityWireDiscrimination` (line 1277) — the only class that
  extracts and runs inline shell from a YAML action via `subprocess.run`.
- `scripts/tests/test_ll_issues_sections.py` — update expected required-section
  list to drop `Labels` (all 4 types) and `User Story` (feat).
- **Template guard test** (in `test_ll_issues_sections.py` or
  `test_issue_template.py`): assert that for each of feat/bug/enh/epic the
  computed `required` set is non-empty after the demotions — pins the verified
  "no vacuous-True regression" finding so a future template edit can't silently
  empty it.

_Tests that may break (verify, fix if needed):_
- `scripts/tests/test_refine_status.py` — `TestRefineStatusFormatColumn._make_fully_formatted_bug()` (line 1060) includes a `## Labels` body section; it stays formatted (Labels now optional, never demanded). (a) add a complementary fixture WITHOUT `## Labels` asserting `formatted=True`; (b) confirm `test_fmt_x_for_missing_required_sections()` (line 1133) still returns `formatted=False` — its fixture is missing several still-required sections, so demotion doesn't rescue it.
- `scripts/tests/test_next_action.py` — `test_needs_format()` (line 68): confirm its fixture is still missing a still-required section so it still asserts `NEEDS_FORMAT`. `test_needs_verify()` (line 91) is criterion-1 only, safe.
- `scripts/tests/test_issue_template.py` — assembly tests: `Labels.required: false` does not remove Labels from `creation_variants.full.include_common`, so the assembler still emits `## Labels` for new issues (separate concern, see Follow-ups). Verify no assertion couples `required` to assembly inclusion.

> **STRUCK (Option-A scaffolding — do NOT implement):** the
> `FRONTMATTER_SECTIONS = {"Labels"}` edit to `is_formatted()` and any
> shell-execution `TestIsFormatted` modeled on Option A. `is_formatted()` needs
> no code change under Option B; its test is a plain Python call.

#### Scope Note
The `Labels` mismatch affects **all four types** (bug, feat, enh, epic) — `common_sections.Labels.required: true` appears in all four `*-sections.json` templates including `epic-sections.json:61` [wiring pass 2]. The `User Story` alias mismatch is **feat-only** (only `feat-sections.json` has the deprecated `type_sections.User Story` entry with `level: required`).

#### Extended Scope: `is_formatted()` in `issue_parser.py` — fixed transitively by Option B

`is_formatted()` is template-driven, so Option B fixes it with no code change:

| Code path | reads `required`/`level` live? | fixed by Option B template edit? |
|-----------|-------------------------------|----------------------------------|
| `ensure_formatted` inline Python (`rn-remediate.yaml`) | ✅ via `ll-issues sections` | ✅ Labels & User Story drop out of required |
| `is_formatted()` (`issue_parser.py:84-96`) | ✅ via `load_issue_sections` | ✅ Labels drops out; User Story already excluded by deprecated guard |

`is_formatted()` is called by:
- `scripts/little_loops/cli/issues/next_action.py:cmd_next_action()` (line 47) — routes `NEEDS_FORMAT` if not formatted
- `scripts/little_loops/cli/issues/refine_status.py:cmd_refine_status()` (lines 338, 363, 443) — `formatted` field
- `scripts/little_loops/cli/issues/show.py` (line 196) — `fmt` field in `--json` output

After Option B, all three report `is_formatted() = True` for post-ENH-1392
frontmatter-labels issues — the same template edit that fixes the loop gate fixes
the CLI reporting paths. **No explicit `FRONTMATTER_SECTIONS` Python bypass is
needed** (correction above supersedes the earlier "regardless of option" claim).

> **NOTE — separable hardening, NOT in scope here:** the `ensure_formatted`
> gate's inline Python lacks a `deprecated` guard that `is_formatted()` has. It
> works correctly for this bug because Option B demotes `User Story` to
> `optional` (so it never enters the required list). But a *future*
> deprecated-but-`required` section would re-trigger the gate while
> `is_formatted()` stays correct. Spun out to a follow-up ENH (see Impact →
> Follow-ups) rather than bundled, to keep this fix at 5 JSON lines.

#### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### is_formatted` entry documents criterion 2 as "All required sections for its type template are present as `##` headings"; update to note that `Labels` satisfies criterion 2 via frontmatter (no body heading required post-ENH-1392) [Agent 2 finding]
- `docs/reference/ISSUE_TEMPLATE.md` — `## Quick Reference` table has `| **Labels** | ✓ | MEDIUM | Categorization |`; if Option B (template change), update `✓` to indicate frontmatter field, not required body heading [Agent 2 finding]
- `commands/ready-issue.md` — `#### Required Sections` checklist at line 140 hardcodes "(Summary, Current Behavior, Expected Behavior, Impact, **Labels**, Status)"; remove `Labels` from this enumeration when template is updated [Agent 2 finding]

#### Test Patterns to Follow
- `test_builtin_loops.py:7270` — `TestRnRemediateAssessRouting` class: model for YAML-loop state routing regression tests (uses `yaml.safe_load` + key assertions)
- `test_refine_status.py:1245` — `test_fmt_checkmark_after_append_session_log_entry()`: model for `is_formatted()` behavior tests
- `test_rn_remediate.py:TestDiagnoseAmbiguityWireDiscrimination` (line 1277) — only class that extracts and executes inline shell from a YAML action string via `subprocess.run`; use as the template for `TestEnsureFormatted` bash-execution tests [Agent 3 finding]

## Implementation Steps

_Selected: Option B (template-only). Test-first so the fix cannot ship unanchored._

1. Add regression tests (red before the fix): `TestIsFormatted` in
   `test_issue_parser.py` (direct Python call — frontmatter-labels + `## Use
   Case` feat → `is_formatted()` True via criterion 2) and `TestEnsureFormatted`
   in `test_rn_remediate.py` (gate inline shell exits 0). Add the template-guard
   test (per-type `required` set non-empty after demotion).
2. Apply Option B: 5 one-line JSON edits — `Labels.required: false` in
   feat/bug/enh/epic + `User Story.level: optional` in feat. No Python, no YAML.
3. Verify deterministically (no loop rerun): full pytest green +
   `is_formatted(FEAT-2387)` True + `ll-issues show --json FEAT-2387` reports
   `"formatted": true`. (Optional LLM confirmation: one `rn-remediate FEAT-2387`
   run shows `ensure_formatted` exit 0 with no `format_issue`.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references:_

**Step 1 — Regression test** (`scripts/tests/test_rn_remediate.py`):
- Add `class TestEnsureFormatted` following the `_load_loop()` pattern used throughout this file
- Test A (feat, frontmatter labels + Use Case): construct a minimal issue body string with `## Use Case` and `## Acceptance Criteria` but no `## Labels`/`## User Story`; mock `ll-issues sections feat` to return the real `feat-sections.json`; assert the gate shell action exits 0
- Test B (bug, frontmatter labels): same pattern for a bug issue body; assert exits 0
- Test C (template guard, Option B): assert `feat-sections.json` does not mark `User Story` as `level: required` and that `Labels.required` is `false` in all four `*-sections.json`; assert the per-type computed `required` set is non-empty (no vacuous-True regression)

**Step 2 — Apply Option B** (the only source change; 5 one-line JSON edits):
- `scripts/little_loops/templates/feat-sections.json`: `type_sections.User Story.level: "required" → "optional"` (already `deprecated: true`) AND `common_sections.Labels.required: true → false`
- `scripts/little_loops/templates/bug-sections.json`: `common_sections.Labels.required: true → false`
- `scripts/little_loops/templates/enh-sections.json`: `common_sections.Labels.required: true → false`
- `scripts/little_loops/templates/epic-sections.json`: `common_sections.Labels.required: true → false`
- No `issue_parser.py` change; no `rn-remediate.yaml` change (both consume `required`/`level` live from these templates).
- Confirm all four patched: `grep -A4 '"Labels"' scripts/little_loops/templates/*-sections.json | grep '"required"'` should show `false` everywhere.

**Step 3 — Verify (deterministic; no loop rerun required)**:
- `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_rn_remediate.py scripts/tests/test_ll_issues_sections.py scripts/tests/test_refine_status.py scripts/tests/test_next_action.py scripts/tests/test_issue_template.py -v` — full green, incl. new `TestIsFormatted` / `TestEnsureFormatted` and the template-guard test.
- `python -c "from pathlib import Path; from little_loops.issue_parser import is_formatted; print(is_formatted(Path(__import__('subprocess').check_output(['ll-issues','path','FEAT-2387']).decode().strip())))"` → `True`.
- `ll-issues show --json FEAT-2387 | python -m json.tool | grep -i formatted` → `"formatted": true`.
- _Optional confirmation only (LLM cost):_ `ll-loop run rn-remediate "FEAT-2387"` once — `ensure_formatted` exits 0 without calling `format_issue`. Not required for acceptance; the deterministic checks above pin idempotency.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add `TestIsFormatted` tests in `scripts/tests/test_issue_parser.py` — **direct Python unit tests** (call `is_formatted(path, templates_dir=...)`, NOT shell execution); model after `test_refine_status.py:1245`. [Corrected: earlier "shell-executed inline code / FRONTMATTER_SECTIONS bypass" note was Option-A scaffolding — `is_formatted()` gets no code change under Option B.]
5. Update `scripts/tests/test_refine_status.py` — (a) add fixture variant of `_make_fully_formatted_bug()` without `## Labels` body section and assert `formatted=True`; (b) run `test_fmt_x_for_missing_required_sections()` against remaining sections to confirm it still returns `False` after demotion
6. Verify `scripts/tests/test_next_action.py:68` `test_needs_format()` — confirm its sparse fixture is still missing a still-required section so it still asserts `NEEDS_FORMAT` (no `is_formatted()` code change is made; behavior shifts only via the template demotion)
7. Update `docs/reference/API.md` `#### is_formatted` criterion 2 description — note that `Labels` is no longer a required section (demoted to optional in the templates post-ENH-1392), so no `## Labels` body heading is needed; `is_formatted()` derives this from the template, no special-case code
8. Update `commands/ready-issue.md` `#### Required Sections` enumeration at line 140 — remove `Labels` from hardcoded list when template is changed (Option B)
9. Update `docs/reference/ISSUE_TEMPLATE.md` `## Quick Reference` table — change Labels row to indicate frontmatter field (not required body heading)
10. Fix `scripts/little_loops/templates/epic-sections.json` line 61 — demote `Labels.required: true` → `false`; EPIC issues share the same `common_sections.Labels` pattern as bug/feat/enh and will trigger the same `ensure_formatted` false-positive without this fix [wiring pass 2]

## Impact

Wasted LLM cost: one redundant `/ll:format-issue --auto` call per affected issue
per run, plus the assess churn it triggers. No data loss (bounded within a run),
but it muddies audit traces (every run looks like it "did formatting work") and
will recur for any frontmatter-labels / `Use Case` feature issue in a queue.

### Follow-ups (spun out to keep this fix at 5 JSON lines)

- **ENH-2398** — `ensure_formatted` gate Python lacks the `deprecated` guard that
  `is_formatted()` has; a future deprecated-but-`required` section would
  re-trigger the gate. Hardening, not needed for this bug (Option B demotes
  `User Story` to optional so it never enters the required list).
- **ENH-2399** — issue assembler still emits `## Labels` in the body for *new*
  issues (`creation_variants.full.include_common` in `issue_template.py`); demoting
  `Labels.required` does not change assembly. Cosmetic divergence, separate concern.

## Labels

See `labels:` frontmatter (ENH-1392 canonical location): rn-remediate,
format-guard, idempotency, loop.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-29 (re-check after decide-issue + wire-issue)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → PROCEED WITH CAUTION

### Outcome Risk Factors
- Broad file surface (~12 distinct change sites: 4 JSON templates + `issue_parser.py` + 4 test files + 3 doc files) — per-site changes are mechanical-to-local; Pattern B verifiability is strong for the JSON template changes — confirm all 4 sites patched via `grep -rn '"required": true' scripts/little_loops/templates/*-sections.json | grep Labels`
- Test co-deliverables must be created: `TestEnsureFormatted` in `test_rn_remediate.py` (model: `TestDiagnoseAmbiguityWireDiscrimination` at line 1277) and `TestIsFormatted` in `test_issue_parser.py` (model: `test_refine_status.py:1245`); implement tests first so the fix cannot ship without the gate anchored

### Re-score after reconciliation (2026-06-29)

**Outcome Confidence: 72 → 88.** The 72 was driven by a self-inflicted
contradiction: the body carried pre-decision Option-A scaffolding (an
`is_formatted()` `FRONTMATTER_SECTIONS` Python edit + shell-execution
`TestIsFormatted`) claimed "required regardless of option," which is false under
the selected Option B. Verified against source:

- `is_formatted()` (`issue_parser.py:84-96`) and the `ensure_formatted` gate both
  read `required`/`level` **live** from the templates → Option B's 5 JSON edits
  fix all paths with **zero Python/YAML code change**.
- Real source surface collapses from "~12 sites" to **5 one-line JSON edits** +
  2 test additions + 3 doc touch-ups.
- The one genuine regression risk (demoting Labels empties the `required` set →
  `is_formatted()` returns vacuous `True`) was **checked and ruled out**: every
  type retains 6+ required sections. A template-guard test pins this.
- Verification is now **deterministic** (Python call + gate shell exit-code, no
  loop rerun), removing the LLM-variance leak from the old "run it twice" plan.

Residual risk (why not higher than 88): the test co-deliverables still must be
authored correctly, and three doc sites must stay in sync — both mechanical but
human-touchable.

## Session Log
- manual reconciliation - 2026-06-29 - reconciled plan to selected Option B: struck stale Option-A `is_formatted()`/shell-test scaffolding (verified template-driven, no Python needed), swapped loop-rerun for deterministic acceptance gate, ruled out empty-required regression, spun out ENH-2398/ENH-2399; outcome_confidence 72 → 88
- `/ll:confidence-check` - 2026-06-29T19:00:00Z - re-check after decide-issue + wire-issue
- `/ll:wire-issue` - 2026-06-29T18:01:03 - `ea38ba49-3bae-4693-9961-165fbf1039bb.jsonl`
- `/ll:decide-issue` - 2026-06-29T17:51:59 - `8c3daa4b-4028-4226-906a-ce3f4ce3cbf0.jsonl`
- `/ll:confidence-check` - 2026-06-29T18:00:00Z - `731877a1-f87f-45a9-9b54-bc79d2670047.jsonl`
- `/ll:wire-issue` - 2026-06-29T17:34:50 - `6e7f3935-97bf-49e7-ae66-2a288f6facbc.jsonl`
- `/ll:refine-issue` - 2026-06-29T17:13:42 - `96fe54fe-15ef-4297-a43e-b66fbe724afb.jsonl`
- `/ll:format-issue` - 2026-06-29T17:03:47 - `ab200a7b-136d-451d-a3bd-cd32423bbc9e.jsonl`
- `/ll:capture-issue` - 2026-06-29T16:59:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0eccd4fa-7376-4b01-a54f-59cedd5d98e6.jsonl`

---

## Status

open
