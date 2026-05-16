---
captured_at: '2026-05-02T19:50:27Z'
completed_at: '2026-05-03T04:12:28Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
status: done
---

# ENH-1331: Enforce description: field in loop YAML; migrate comment-based descriptions

## Summary

The `/ll:analyze-loop` skill's Step 3b-1 reads the loop's declared goal from
`ll-loop show <name> --json`, expecting a top-level `description` key in the
JSON output. `cmd_show --json` delegates to `fsm.to_dict()`, which only emits
`description` when `FSMLoop.description is not None` — and that field is
populated solely from the parsed YAML value `data.get("description")`. A
comment such as `# Description: my goal` at the top of a loop YAML file is
invisible to the YAML parser, so the field is always `None` and the skill
reports "(no description provided)" even when intent text exists in the file.

The fix is two-pronged:

1. **Enforce the `description:` field** as a required YAML field in new loops.
   `ll:create-loop` already emits it; templates and docs should make it
   explicit.
2. **Migrate existing violations** — scan built-in and project loops for files
   that lack a `description:` key (or use `# Description:` comments) and
   normalize them to use the proper YAML field.

Optionally add comment-parsing as a fallback in `_load_loop_meta` /
`load_loop_with_spec` to handle user-written loops in external projects that
can't be migrated here.

## Current Behavior

When a built-in loop YAML file uses a comment (`# Description: my goal`) instead
of a YAML key, the YAML parser ignores it. `FSMLoop.description` is always `None`
in this case. `ll-loop show <name> --json` omits the `"description"` key entirely,
and `/ll:analyze-loop` reports "(no description provided)" in Step 3b-1 even though
intent text exists in the file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **All 43 top-level built-in loop YAMLs already carry a `description:` key** (plus `lib/apo-base.yaml` and `oracles/oracle-capture-issue.yaml`). Zero files use `# Description:` comments. The mass-migration premise of Step 2 is moot for the in-tree built-ins; the issue is now primarily a **guardrail** problem (prevent regressions + warn externally-managed loops), not a remediation problem.
- `KNOWN_TOP_LEVEL_KEYS` in `scripts/little_loops/fsm/validation.py:78` **already lists `"description"`**, so no unknown-key warning fires when the field is missing. A dedicated missing-description check must be added — the existing unknown-keys warning will not catch it.
- `FSMLoop.description: str | None = None` (`scripts/little_loops/fsm/schema.py:602`) is read via `data.get("description")` in `from_dict()` and conditionally emitted by `to_dict()` only when not `None` (`schema.py:618`). The CLI side (`info.py:_load_loop_meta`) reads `spec.get("description", "") or ""` and `cmd_show` reads `spec.get("description", "").strip()` from the raw spec dict — neither path scans comments.
- No existing comment-parsing pattern exists in `scripts/little_loops/fsm/` or `scripts/little_loops/cli/loop/`. The only comment-aware text scan in the codebase is `git_operations.py:253` for `.gitignore`. The optional fallback (Step 3) would be the first such pattern in the FSM/loop layer.

## Expected Behavior

All built-in loop YAML files have a top-level `description:` key. `ll-loop show
<name> --json` always includes `"description"` for built-in loops. `/ll:analyze-loop`
reads a non-empty goal in Step 3b-1 for every built-in loop. `ll-loop validate`
emits a warning when a loop file is missing the `description:` field.

## Motivation

Without a machine-readable description, `analyze-loop` cannot perform goal
alignment assessment (Step 3b-3), which is one of the skill's most valuable
outputs. All built-in loops should serve as a reference implementation, so
they must all carry a proper `description:` field.

## Scope Boundaries

- **In scope**: Auditing all built-in loop YAML files for missing `description:` keys; migrating `# Description:` comments to proper `description: |` YAML fields; adding a missing-description warning to `ll-loop validate`; optional comment-parsing fallback in `_load_loop_meta` / `load_loop_with_spec` for externally-managed loops.
- **Out of scope**: Changing the storage format or schema of user-managed project loop files; modifying FSM evaluation logic; enforcing the field in existing third-party extensions that cannot be migrated here.

## Implementation Steps

1. **Audit (already done by `/ll:refine-issue` research)**: `grep -rL "^description:"
   scripts/little_loops/loops/*.yaml` returned **zero violators**. All 43 top-level
   built-ins (and the 2 subdirectory files) carry a `description:` key. Skip migration.
2. **~~Migrate built-in loops~~** — N/A; no violators.
3. **Validation warning in `validate_fsm`** (primary work): in
   `scripts/little_loops/fsm/validation.py`, inside `validate_fsm()`, append a
   `ValidationError(path="<root>", message="No 'description' field defined. Add a
   top-level description: key.", severity=ValidationSeverity.WARNING)` when
   `not fsm.description`. Mirror the structure of the unknown-key warning at
   `validation.py:724`. `cmd_validate` (`config_cmds.py:11`) already prints
   warnings via `print(f"  ⚠ {w}")` — no CLI change needed.
4. **Regression guard test**: extend `scripts/tests/test_builtin_loops.py:test_all_validate_as_valid_fsm`
   (line 36) to also assert no warning containing "description" is produced for
   any built-in. This makes the policy CI-enforced for future built-ins.
5. **Validate-warning unit tests**: add to `scripts/tests/test_ll_loop_commands.py`
   `TestValidation` (pattern: line 75) and `scripts/tests/test_fsm_schema.py`
   `TestLoadAndValidate` (pattern: lines 1604/1624).
6. **Optional fallback for externally-managed loops**: in `_load_loop_meta`
   (`info.py`) and/or `load_loop_with_spec` (`_helpers.py`), read raw text once,
   regex-scan for `^# Description:\s*(.*)$`, then `yaml.safe_load`, and inject the
   captured value only when `data.get("description")` is absent. No precedent for
   pre-`safe_load` text scanning exists in the FSM layer — consider whether the
   complexity is worth it given that `ll:create-loop` already emits the field and
   the validate-time warning will catch user-authored loops on first `validate`/`run`.
7. **`ll:create-loop` template confirmation**: verify `skills/create-loop/SKILL.md`
   template includes `description:` (already true per audit) and add a one-line
   test that asserts the wizard's generated YAML contains a `description:` key.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Fix `scripts/tests/fixtures/fsm/valid-loop.yaml` — add a top-level `description: "A simple test loop"` field so `TestLoadAndValidate.test_load_valid_yaml` continues to pass `assert warnings == []` after the new warning is added.
9. Fix `scripts/tests/test_fsm_schema.py::TestLoadAndValidate.test_unknown_top_level_keys_warn` — add `description: test` to the inline loop YAML in that test (or change the assertion from `len(unknown_warnings) == 1` to a message-content filter) so the count assertion doesn't break when the second WARNING fires.
10. Add `scripts/tests/test_fsm_validation.py` tests — two unit tests for the new validate_fsm check: one asserting `ValidationSeverity.WARNING` with description-related message when `fsm.description` is `None`; one asserting no such warning when a description is set.
11. Update `skills/review-loop/reference.md` — add V-17 row to the `## First-Pass Checks` table for the new missing-description warning (check ID, severity, message pattern).
12. Update `docs/reference/API.md::validate_fsm` — add bullet to "Checks performed" section for the missing-description warning.
13. (Optional) Verify `scripts/tests/test_fsm_fragments.py` — confirm its `unknown_warnings == []` assertions use message-content filters (safe) rather than `warnings == []` (would break); fix any `assert warnings == []` patterns.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `validate_fsm()` — append `ValidationError(severity=WARNING, path="<root>", message="...")` when `fsm.description` is falsy. Pattern matches the existing unreachable-state warning emitted later in the same function.
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop_with_spec()` (optional fallback) — would need to read raw text before `yaml.safe_load`, scan for `^# Description:`, and inject into spec dict.
- `scripts/little_loops/cli/loop/info.py` — `_load_loop_meta()` (optional fallback, same pattern as above; or share helper with `_helpers.py`).
- `skills/create-loop/SKILL.md` — confirmed already documents `description:` field; no doc change required (verify only).

**No YAML migration required** — audit found zero violators. Drop `scripts/little_loops/loops/*.yaml` from the modification list.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/config_cmds.py:11` — `cmd_validate()` already iterates `for w in warnings: print(f"  ⚠ {w}")` — new warning surfaces automatically without changes.
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()` calls `load_loop_with_spec()` (line ~636) and reads `spec.get("description", "").strip()` from the raw dict; affected by the optional fallback.
- `scripts/little_loops/cli/loop/__init__.py:21-22` — imports both `cmd_validate` and `cmd_show` (router; no change).
- Skills consuming description via `ll-loop show --json`: `skills/analyze-loop/SKILL.md` (Step 3b-1, the original motivator).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — calls `load_and_validate()` with `fsm, _ = load_and_validate(path)` (warnings discarded); no code change needed, but confirms new warning is silently absorbed during `ll-loop run`. [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — calls `load_and_validate()` during FSM execution setup; same discard pattern, no change needed. [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — exports `ValidationError`, `validate_fsm`, and `load_and_validate` as public API; no change needed but confirms these are part of the public surface. [Agent 1 finding]
- `skills/assess-loop/SKILL.md` — references `ll-loop show` and loop inspection; consumes description via the same path as `analyze-loop`. [Agent 1 finding]
- `skills/review-loop/SKILL.md` — step 2c-1 already handles absent `description:` by falling back to YAML comments; orthogonal to the new validator warning but confirm the skill still works after the change. [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:724` — unknown top-level keys check builds `ValidationError(path="<root>", message=..., severity=ValidationSeverity.WARNING)` and appends to `unknown_key_warnings`. **This is the exact pattern to mirror** for the missing-description warning.
- `scripts/little_loops/fsm/validation.py:53` — `ValidationError.__str__` renders as `[WARNING] <path>: <message>`, so the printed line will be `  ⚠ [WARNING] <root>: ...`.
- No existing pre-`yaml.safe_load` text-scan pattern in the FSM/loop layer (closest: `git_operations.py:253` for `.gitignore`). The optional fallback would be the first such pattern; consider reading file text once, regex-scanning for `^# Description:\s*(.*)$`, then `yaml.safe_load(text)` and injecting only if `data.get("description")` is absent.

### Tests
- **Validate warning** — extend `scripts/tests/test_ll_loop_commands.py` `TestValidation` (around line 75 `test_validate_with_unreachable_state_prints_warning`); pattern: write loop YAML to `tmp_path` without `description:`, call `cmd_validate`, assert `"⚠"` in `capsys.readouterr().out` and assert the missing-description message text.
- **Direct `load_and_validate`** — add to `scripts/tests/test_fsm_schema.py` `TestLoadAndValidate` (around lines 1604/1624); pattern: `_, warnings = load_and_validate(loop_yaml); assert any("description" in w.message.lower() for w in warnings if w.severity == ValidationSeverity.WARNING)`.
- **Built-in loops still clean** — extend `scripts/tests/test_builtin_loops.py:test_all_validate_as_valid_fsm` (line 36) to assert no built-in loop produces a missing-description warning (regression guard so a future loop without `description:` fails CI).
- **`ll-loop show --json` includes `description`** — pattern in `scripts/tests/test_ll_loop_commands.py` `TestCmdShowJson.test_show_json_output` (line 2424) demonstrates the `cmd_show` JSON invocation and `json.loads(capsys.readouterr().out)` assertion shape.
- **Optional fallback** — if implemented, add a test that loads a YAML containing only `# Description: foo` (no key) and asserts `fsm.description == "foo"` (or the relevant value) via `load_loop_with_spec` / `_load_loop_meta`.
- **`validate_fsm` unit tests** — add to `scripts/tests/test_fsm_validation.py` (follow `TestExtraRoutesReachability` pattern): assert `validate_fsm(fsm)` returns a `ValidationSeverity.WARNING` matching the description message when `fsm.description` is `None`; assert no such warning when `fsm.description` is set.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/fsm/valid-loop.yaml` — **must add `description:` field** (or update `TestLoadAndValidate.test_load_valid_yaml` assertion at line 1545); currently triggers `assert warnings == []` failure when the new warning fires. [Agent 2/3 finding]
- `scripts/tests/test_fsm_schema.py::TestLoadAndValidate.test_unknown_top_level_keys_warn` — **will break**: asserts `assert len(unknown_warnings) == 1` where `unknown_warnings` filters by `WARNING` severity; the loop YAML in that test has no `description` field, adding a second `WARNING` and making the assertion fail. Fix by adding `description:` to the inline YAML, or filter the assertion by message content. [Agent 2/3 finding]
- `scripts/tests/test_fsm_validation.py` — primary `validate_fsm` unit test file; new description-warning unit tests fit here naturally (follow `TestExtraRoutesReachability` and `TestRateLimitFieldValidation` patterns). NOT the same as `test_fsm_schema.py`. [Agent 1/3 finding]
- `scripts/tests/test_fsm_fragments.py` — calls `load_and_validate` and asserts `unknown_warnings == []` (filtered by `"Unknown top-level keys"` message); message filter is safe, but loop fixtures here likely lack `description:` fields — verify no `assert warnings == []` style assertions exist. [Agent 1 finding]

### Documentation
- `skills/create-loop/SKILL.md` — verified already includes `description:` in template; no edit needed.
- Consider adding a one-line note in `docs/reference/` (FSM loop schema doc, if present) calling out `description:` as recommended but enforced via warning.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/reference.md` — `## First-Pass Checks (from ll-loop validate)` table lists V-1 through V-16; the new missing-description warning needs a new row (e.g., V-17) with its check ID, severity mapping, and message pattern so `review-loop` skill can categorize and report it correctly. [Agent 2 finding]
- `docs/reference/API.md` — `#### validate_fsm` section documents checks as a bullet list; the new description warning is not listed and must be added. [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — documents `description: string` as optional; add a note that its absence produces a validator `WARNING` after this change. [Agent 2 finding]

### Configuration
- N/A

## Acceptance Criteria

- [ ] All built-in loop YAML files have a `description:` field (no comment-only descriptions)
- [ ] `ll-loop show <name> --json` always includes `"description"` for built-in loops
- [ ] `/ll:analyze-loop` Step 3b-1 reads a non-empty goal for all built-in loops
- [ ] `ll-loop validate <name>` emits a warning when `description:` is absent
- [ ] (Optional) `_load_loop_meta` falls back to `# Description:` comment for externally-managed loops

## API/Interface

N/A - No public API changes. The optional comment-parsing fallback in `_load_loop_meta` is internal to the CLI and backward compatible (additive behavior only).

## Impact

- **Priority**: P3 - Quality improvement; doesn't block core loop functionality but degrades `analyze-loop` goal alignment for all built-in loops
- **Effort**: Small - YAML field additions are mechanical; validation check and optional fallback are isolated
- **Risk**: Low - Additive changes; promoting a comment to a YAML key is non-breaking for all consumers
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `captured`

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-03 | Priority: P3

## Resolution

Added a missing-description warning to `validate_fsm` so loops without a top-level
`description:` field surface an actionable hint (consumed by `cmd_validate`,
`/ll:review-loop`, `/ll:analyze-loop`, and `/ll:assess-loop`). Audit confirmed all
44 in-tree built-in/oracle loops already define the field, so no YAML migration was
required — the change is purely a guardrail against future regressions.

**Changes:**
- `scripts/little_loops/fsm/validation.py` — new WARNING emitted when `fsm.description` is falsy
- `scripts/tests/fixtures/fsm/valid-loop.yaml` — added `description:` so existing
  `assert warnings == []` continues to pass
- `scripts/tests/test_fsm_schema.py::test_unknown_top_level_keys_warn` — filtered
  unknown-key warnings by message content; added `description:` to inline YAML
- `scripts/tests/test_fsm_validation.py` — new `TestDescriptionFieldValidation`
  (3 cases: missing, present, empty-string)
- `scripts/tests/test_fsm_schema.py::TestLoadAndValidate` — 2 new
  `load_and_validate` tests covering both branches
- `scripts/tests/test_ll_loop_commands.py::TestValidation` — `cmd_validate` prints
  `⚠ ... description ...` line
- `scripts/tests/test_builtin_loops.py::test_all_have_description_field` — CI
  regression guard so future built-ins can't ship without the field
- `skills/review-loop/reference.md` — V-17 row in First-Pass Checks table
- `docs/reference/API.md::validate_fsm` — bullet for the new check
- `docs/generalized-fsm-loop.md` — note that absence triggers a validator WARNING

**Verification:**
- `pytest scripts/tests/` — 5626 passed (2 pre-existing marketplace version
  failures unrelated to this issue, confirmed against main before changes)
- `ruff check` — all changed files clean
- `mypy scripts/little_loops/fsm/validation.py` — no issues

**Acceptance criteria:**
- [x] All built-in loop YAML files have a `description:` field (audit confirmed)
- [x] `ll-loop show <name> --json` always includes `"description"` for built-in loops
- [x] `/ll:analyze-loop` Step 3b-1 reads a non-empty goal for all built-in loops
- [x] `ll-loop validate <name>` emits a warning when `description:` is absent
- [ ] (Optional) `_load_loop_meta` falls back to `# Description:` comment for
      externally-managed loops — deferred; the validate-time warning is
      sufficient for now and avoids being the first pre-`safe_load` text-scan
      pattern in the FSM/loop layer (per issue Step 6 guidance)


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **File span across subsystems**: 9 required files touch validation core, 5 test files, and 2 doc files — each individual change is small and mechanical, but coordination across subsystems increases implementation slip risk
- **Pre-existing test assertions will break**: `test_load_valid_yaml` (valid-loop.yaml lacks description) and `test_unknown_top_level_keys_warn` (warning count assertion) will fail immediately after adding the warning; these must be patched in the same commit to keep CI green — documented in wiring analysis but requires careful sequencing

## Session Log
- `/ll:ready-issue` - 2026-05-03T03:44:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f2644eb-fc81-4e02-908e-faf86597a644.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87358b2c-9b77-4155-850b-f68fcd6ad7f0.jsonl`
- `/ll:wire-issue` - 2026-05-03T03:39:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/035378c1-815a-4b96-89c0-1ba3c61fa7dc.jsonl`
- `/ll:refine-issue` - 2026-05-03T03:32:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6fd1f5c-51a7-4e84-84c1-5a8a613dc5ed.jsonl`
- `/ll:format-issue` - 2026-05-02T19:54:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c7505b5-ede1-476a-a6b7-a18e3c4c8571.jsonl`
- `/ll:manage-issue` - 2026-05-03T04:12:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cae81b93-4c91-4b4b-a51b-578258d7b392.jsonl`
