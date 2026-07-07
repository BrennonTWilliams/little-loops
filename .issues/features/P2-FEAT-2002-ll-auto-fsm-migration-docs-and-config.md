---
id: FEAT-2002
title: Update docs and config for ll-auto FSM migration and AutoManager soft-deprecation
type: FEAT
priority: P2
status: deferred
parent: EPIC-1867
blocked_by:
- FEAT-2001
size: Very Large
relates_to:
- FEAT-1902
confidence_score: 70
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2002: Update docs and config for ll-auto FSM migration and AutoManager soft-deprecation

## Summary

Update all documentation and configuration files to reflect that `ll-auto` is now a thin
shim over `ll-loop run ll-auto`, and that `AutoManager.run()` is soft-deprecated. Update
test documentation that describes the rewritten test classes.

## Parent Issue

Decomposed from FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Use Case

After FEAT-2000 (FSM YAML) and FEAT-2001 (shim + tests) are merged, update all
references to `AutoManager` in docs and config to reflect the new architecture and
soft-deprecation.

## Depends On

FEAT-2001 must be merged first — docs reflect the final implementation.

## Implementation Steps

14. Update `config-schema.json` `"sqlite"` description (lines 1291–1302) — the exact current
    text at line 1293 is:
    ```
    "AutoManager.__init__() wires SQLiteTransport directly for ll-auto runs without requiring events.transports config."
    ```
    Replace with a note that the FSM shim now delegates wiring (e.g. `"ll-loop run ll-auto delegates
    to the FSM shim, which wires SQLiteTransport directly for ll-auto runs without requiring
    events.transports config."`).
    Also update `scripts/tests/test_wiring_skills_and_commands.py` **line 89**:
    ```python
    ("config-schema.json", "AutoManager", "ENH-1734"),
    ```
    Replace `"AutoManager"` with the new anchor string that will appear in the updated description.

15. Update documentation files:
    - `docs/ARCHITECTURE.md` — three locations to update:
      1. **Sequence diagram** (lines 337–380): replace `participant Manager as AutoManager` and
         the `CLI->>Manager: Initialize with config` flow with shim delegation to `ll-loop run ll-auto`
      2. **Class diagram** (lines 753–759): mark `AutoManager { +run() int }` as soft-deprecated
         (add `<<deprecated>>` annotation or a note)
      3. **Transport table row** (line 539) and the note at line 541: both contain
         `AutoManager.__init__() wires SQLiteTransport directly`; replace with FSM-shim ownership
         description. The wiring test assertion at `test_wiring_guides_and_meta.py` **line 128**:
         ```python
         ("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734"),
         ```
         must be updated to match the new anchor string in ARCHITECTURE.md.
    - `docs/reference/API.md` (lines 2029+):
      - `### AutoManager` section: add deprecation notice; update the behavior note at
        **line 2084** (`AutoManager creates an internal EventBus and wires SQLiteTransport...`)
        to reflect that `AutoManager.run()` is soft-deprecated in favor of the FSM loop
      - `### main_auto` section (line 3185): update description from "Process all backlog issues
        sequentially in priority order" to describe shim behavior (`delegates to ll-loop run ll-auto`)
    - `docs/reference/CONFIGURATION.md` — **two** locations to update:
      1. `events.sqlite` section (**lines 1168–1178**): the note currently ends with
         `ll-auto writes issue lifecycle events live via AutoManager's internal transport`
         — update to reflect FSM shim ownership. This anchor is asserted by
         `test_wiring_reference_docs.py`: `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")`
      2. **Line 1110** — `**\`ll-auto\` exclusion:**` note: currently states `cli/auto.py does not
         construct an EventBus`; after FEAT-2001 the shim delegates to `ll-loop run ll-auto` which
         DOES construct EventBus — update or remove this exclusion note. *(This location is not
         in the original Files to Touch list — added by codebase research.)*
    - `docs/reference/CLI.md` — `### ll-auto` section (**lines 217–257**): update the prose
      description to describe shim behavior and FSM delegation instead of direct `AutoManager`
      invocation; flags table and examples may remain unchanged if the CLI surface doesn't change

18. Update test documentation after FEAT-2001 rewrites the E2E test classes:
    - `docs/development/E2E_TESTING.md` — section "3. Sequential Execution Workflow (ll-auto)"
      (**lines 49–102**): update to reflect new shim assertion patterns in
      `TestSequentialExecutionWorkflow` (class at line 96); the section currently describes
      `ll-auto --dry-run` listing issues without processing — update if shim changes that behavior
    - `docs/development/TESTING.md` — two locations:
      1. `TestSequentialWorkflowIntegration` docstring (**line 578**):
         `"""Integration tests for sequential issue processing (AutoManager)."""`
         — update to reflect that `main_auto()` delegates to the FSM shim
      2. `TestAutoArgumentParsing` class (**line 673**): the `_parse_auto_args` helper and
         `test_ll_auto_dry_run` mock of `main_auto` — update if shim changes argument handling

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

19. Update `scripts/tests/test_wiring_guides_and_meta.py` **line 128** — change the parametrized
    entry:
    ```python
    ("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734"),
    ```
    to the new anchor string chosen for ARCHITECTURE.md transport table (e.g., `"ll-loop run ll-auto"`
    or whatever delegating phrase replaces `AutoManager.__init__()` at line 539).
20. Update `scripts/tests/test_wiring_reference_docs.py` — two assertions to update:
    - Change `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")` to match the new
      anchor string in CONFIGURATION.md (from the events.sqlite section at lines 1168–1178)
    - Verify `("docs/reference/API.md", "SQLiteTransport", "ENH-1734")` still resolves after
      API.md edits (the `SQLiteTransport` mention at API.md:2084 is inside the AutoManager
      behavior description — if that paragraph is rewritten, ensure `SQLiteTransport` is still
      present in the new text)
21. Add a new versioned CHANGELOG entry for FEAT-2002 under the correct `## [X.Y.Z] - DATE` section

## Acceptance Criteria

- [ ] `config-schema.json` (lines 1291–1302) no longer states `AutoManager.__init__()` wires
      SQLiteTransport; updated to reflect FSM shim ownership
- [ ] `test_wiring_skills_and_commands.py` L89 anchor updated to match new `config-schema.json` text
- [ ] `docs/ARCHITECTURE.md` sequence diagram (L337–380), class diagram (L753–759), and transport
      table (L539/L541) reflect soft-deprecation and FSM delegation
- [ ] `docs/reference/API.md` — `### AutoManager` (L2029+) marked deprecated; behavior note at
      L2084 updated; `### main_auto` (L3185) described as shim
- [ ] `docs/reference/CONFIGURATION.md` events.sqlite note (L1168–1178) updated; AND `ll-auto
      exclusion` note (L1110) updated/removed — both `test_wiring_reference_docs.py` assertions pass
- [ ] `docs/reference/CLI.md` `### ll-auto` section (L217–257) reflects FSM delegation
- [ ] `docs/development/E2E_TESTING.md` (L49–102) and `docs/development/TESTING.md` (L578, L673)
      updated for new test shapes
- [ ] All wiring tests pass: `test_wiring_guides_and_meta.py`, `test_wiring_skills_and_commands.py`, `test_wiring_reference_docs.py`

## Files to Touch

- `config-schema.json` — update `"sqlite"` description (lines 1291–1302, exact phrase at L1293)
- `scripts/tests/test_wiring_skills_and_commands.py` — update anchor string (L89: `("config-schema.json", "AutoManager", "ENH-1734")`)
- `scripts/tests/test_wiring_guides_and_meta.py` — update anchor at L128: `("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734")` to the new anchor string after ARCHITECTURE.md is edited
- `scripts/tests/test_wiring_reference_docs.py` — update anchor `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")` to the new anchor string if `AutoManager` is removed or renamed in CONFIGURATION.md; also verify `("docs/reference/API.md", "SQLiteTransport", "ENH-1734")` still passes after API.md edits
- `docs/ARCHITECTURE.md` — sequence diagram (L337–380), class diagram (L753–759), transport table (L539) + note (L541)
- `docs/reference/API.md` — `### AutoManager` (L2029+, behavior note at L2084) + `### main_auto` (L3185)
- `docs/reference/CONFIGURATION.md` — **two locations**: events.sqlite section note (L1168–1178); AND `**ll-auto exclusion:**` note (L1110) — *newly identified by codebase research*
- `docs/reference/CLI.md` — `### ll-auto` section (lines 217–257)
- `docs/development/E2E_TESTING.md` — section "3. Sequential Execution Workflow (ll-auto)" (L49–102)
- `docs/development/TESTING.md` — `TestSequentialWorkflowIntegration` docstring (L578) + `TestAutoArgumentParsing` (L673)
- `scripts/tests/test_cli_e2e.py` — `TestSequentialExecutionWorkflow` doc-assertion patterns need update if E2E_TESTING.md describes new shim assertions

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/auto.py` — imports and instantiates `AutoManager`, calls `manager.run()`; the code-side source-of-truth for what the docs describe [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — exports `main_auto()`; registered as the `ll-auto` entry point [Agent 1 finding]
- `scripts/little_loops/__init__.py` — re-exports `AutoManager` in `__all__` (public API surface); if soft-deprecation needs a deprecation warning, this is where it would live [Agent 1 finding]
- `scripts/pyproject.toml` — `ll-auto = "little_loops.cli:main_auto"` entry point registration [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_manager.py` — **`AutoManager` is defined here** (not in `cli/auto.py`); class starts around line 1021; `AutoManager.__init__()` constructs `EventBus` + `SQLiteTransport` + `StateManager` + `DependencyGraph`; `AutoManager.run()` contains the main issue-processing loop. This is the canonical reference for all docs that describe `AutoManager` behavior.
- **Pre-FEAT-2001 status confirmed**: no shim logic, no `ll-loop` delegation, no FSM runner exists in `cli/auto.py` yet. `loops/ll-auto.yaml` does not exist in the repository.
- **Exact wiring test assertions requiring change** (confirmed by codebase analysis):
  - `test_wiring_guides_and_meta.py:128`: `("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734")`
  - `test_wiring_skills_and_commands.py:89`: `("config-schema.json", "AutoManager", "ENH-1734")`
  - `test_wiring_reference_docs.py`: `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")`
  - `test_wiring_reference_docs.py`: `("docs/reference/API.md", "SQLiteTransport", "ENH-1734")` — verify this still passes after API.md edits (SQLiteTransport mentioned in behavior note at L2084)
- **Newly identified gap**: `docs/reference/CONFIGURATION.md:1110` contains a `**\`ll-auto\` exclusion:**` note stating `cli/auto.py does not construct an EventBus` — this will be incorrect after FEAT-2001 since the shim delegates to `ll-loop run ll-auto` which constructs EventBus. This line was NOT in the original Files to Touch list.
- `docs/reference/CONFIGURATION.md:1168–1178` — the `events.sqlite` note ends with `ll-auto writes issue lifecycle events live via AutoManager's internal transport` — update to reflect FSM shim ownership.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py` — **will break**: parametrized case `("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734")` asserts the exact string `AutoManager.__init__()` must remain present in ARCHITECTURE.md; update this case to the new FSM-delegation anchor string when editing ARCHITECTURE.md [Agent 2/3 finding]
- `scripts/tests/test_wiring_reference_docs.py` — **will break**: parametrized case `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")` asserts `AutoManager` string in CONFIGURATION.md; update if that string is removed; also verify `("docs/reference/API.md", "SQLiteTransport", "ENH-1734")` still passes after API.md changes [Agent 2/3 finding]
- `scripts/tests/test_cli_e2e.py` (`TestSequentialExecutionWorkflow`) — referenced in Step 18 for E2E_TESTING.md updates; not in Files to Touch but the doc section being updated describes this class's test patterns [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — line 38 `ll-auto --help` quickstart, line 246 `SQLiteTransport` in package tree comment; advisory — low-priority unless shim changes the CLI surface [Agent 2 finding]
- `CHANGELOG.md` — needs a new versioned entry for FEAT-2002 under the concrete `## [X.Y.Z] - DATE` section (not `[Unreleased]`); prior ENH-1733/1734 entries at lines 283–284 are historical, leave as-is [Agent 2 finding]

## Impact

- **Priority**: P2
- **Effort**: Small — documentation and config string updates only; no logic changes
- **Risk**: Low — docs-only; wiring tests verify correctness of anchor strings

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-07_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- **Hard blocker unresolved**: FEAT-2001 ("Convert ll-auto CLI to thin shim over ll-loop") is still open, and FEAT-2000 (FSM YAML definition, which blocks FEAT-2001) is also open. This issue explicitly requires FEAT-2001 to be merged first — the documentation must reflect the final implementation, not a hypothetical one.
- **Replacement text is undetermined**: The new descriptions for `AutoManager` soft-deprecation and FSM delegation in 5 doc files and `config-schema.json` can only be finalized after FEAT-2001's implementation is settled.

## Verification Notes (2026-06-13)

2026-06-13: Wiring-test file references are accurate. Doc file line numbers cannot be pinned until FEAT-2001 merges — verify exact line numbers in ARCHITECTURE.md, API.md, CONFIGURATION.md, CLI.md, E2E_TESTING.md, TESTING.md before finalizing replacement text. Issue correctly blocked on FEAT-2001.

2026-06-18 (NEEDS_UPDATE): FEAT-2001 is still open (blocked on FEAT-2000; `loops/ll-auto.yaml` doesn't exist). This issue remains correctly blocked; replacement text for the docs remains undetermined. No action needed until FEAT-2001 merges. Wiring-test anchor assertions (`test_wiring_guides_and_meta.py:128`, `test_wiring_reference_docs.py`) verified as still correct for current code state.

## Deferral Note

**Deferred** (2026-07-07, backlog grooming) — see EPIC-1867 for the full rationale and re-activation criteria. Summary: 0 of 4 EPIC-1867 layers delivered five weeks after capture; the docs/config migration cannot be finalized while the underlying shim (FEAT-2001) is deferred and the orchestrators are still actively gaining Python behavior (ENH-2182, ENH-2210, `--feature-branches` override). Doc text for "ll-auto is an FSM shim over ll-loop" is undetermined until the orchestrator surface stabilizes.

## Session Log
- `/ll:verify-issues` - 2026-06-27T19:13:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:13:12 - `a3378f94-e4e2-4f51-9e6c-9fff5f286332.jsonl`
- `/ll:refine-issue` - 2026-06-07T18:28:24 - `50077b98-472a-456e-9164-a749267bb4f6.jsonl`
- `/ll:wire-issue` - 2026-06-07T18:22:57 - `7b81aa2e-d394-4723-837f-0505a69e6a12.jsonl`
- `/ll:issue-size-review` - 2026-06-07T00:00:00Z - `5db94c28-db76-4bed-885c-95a49da744cb.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `01a315e4-c27c-446d-a7d2-e5f761a37096.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `fc119638-a173-48bd-871e-be09b44bfd2b.jsonl`
