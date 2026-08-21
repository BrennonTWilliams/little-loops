---
id: BUG-2800
status: done
captured_at: '2026-07-25T15:05:37Z'
completed_at: '2026-07-25T16:13:43Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 92
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 23
priority: P1
---

# BUG-2800: YAML-invalid skill frontmatter + integration guard swallows parse errors

## Summary

Two skill frontmatter blocks — `skills/manage-issue/SKILL.md` and `skills/update-docs/SKILL.md` — contain unquoted `arguments[].description` strings with an embedded `: ` (colon-space), which YAML parses as an illegal nested mapping. `TestRealSkillsIntegrationGuard` in `scripts/tests/test_adapt_skills_for_codex.py` is supposed to catch exactly this class of defect, but both of its test methods (`test_all_real_skills_have_name_field`, `test_all_real_skills_have_metadata_short_description`) wrap the `yaml.safe_load` call in `try/except Exception: continue`, silently skipping any skill whose frontmatter fails to parse instead of failing the guard.

## Current Behavior

- `skills/manage-issue/SKILL.md` line 9: `description: Type of issue (bug|feature|enhancement|epic). Note: epic issues are coordination containers — ...` — the `Note:` mid-string breaks the YAML scalar.
- `skills/update-docs/SKILL.md` line 14: `description: Change window start — date (YYYY-MM-DD) or git ref (default: last commit touching a doc file)` — the `(default:` breaks the YAML scalar.
- Both `test_all_real_skills_have_name_field` and `test_all_real_skills_have_metadata_short_description` (scripts/tests/test_adapt_skills_for_codex.py:340-403) catch the `yaml.safe_load` exception and `continue` to the next file, so these two skills are silently excluded from validation rather than failing the test.
- Verified during this capture that two additional skills have the identical defect and are also silently skipped: `skills/audit-loop-run/SKILL.md` (line 19) and `skills/review-loop/SKILL.md` (line 11).

## Expected Behavior

- `manage-issue` and `update-docs` frontmatter parse as valid YAML (fix by quoting the offending `description:` string values, and by adding `name:` + `metadata:` fields consistent with the rest of the adapted skills — or by re-running `ll-adapt-skills-for-codex --apply` once the underlying description text is parseable).
- `TestRealSkillsIntegrationGuard`'s `except Exception: continue` parse hole is closed so that a `yaml.safe_load` failure on a real skill's frontmatter fails the guard (e.g. `pytest.fail(...)` or `assert False, f"..."`) instead of silently skipping the file.

## Root Cause

- **File**: `skills/manage-issue/SKILL.md`, `skills/update-docs/SKILL.md` (also `skills/audit-loop-run/SKILL.md`, `skills/review-loop/SKILL.md`)
- **Anchor**: `arguments[].description` frontmatter fields
- **Cause**: Unquoted YAML scalar strings containing `: ` are interpreted as the start of a nested mapping, raising a `yaml.scanner.ScannerError` ("mapping values are not allowed here"). The guard test in `TestRealSkillsIntegrationGuard` (scripts/tests/test_adapt_skills_for_codex.py) was written to skip files without an end-of-frontmatter marker, but the same `except Exception: continue` also catches genuine parse errors, masking the defect instead of failing on it.

## Proposed Solution

1. In `skills/manage-issue/SKILL.md` and `skills/update-docs/SKILL.md`, quote the `description:` values under `arguments:` that contain a colon-space sequence (YAML double- or single-quoted scalar).
2. Confirm both files then carry `name:` and `metadata:` fields matching the pattern already present in other adapted `SKILL.md` files (or re-run `ll-adapt-skills-for-codex --apply` after the quoting fix so it regenerates them).
3. In `scripts/tests/test_adapt_skills_for_codex.py`, change the `except Exception: continue` in `test_all_real_skills_have_name_field` and `test_all_real_skills_have_metadata_short_description` to fail the test on parse error, e.g.:
   ```python
   except Exception as e:
       pytest.fail(f"skills/{skill_name}/SKILL.md: invalid frontmatter YAML: {e}")
   ```
4. Re-run the guard and fix any additional skills it now catches (`audit-loop-run`, `review-loop` are already known to have the same defect).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- A **third** method in the same `TestRealSkillsIntegrationGuard` class has the identical `except Exception: continue` hole and was not listed in the original scope: `test_all_real_skills_have_openai_yaml` at `scripts/tests/test_adapt_skills_for_codex.py:416-421` (method starts line 403). It checks `fm.get("disable-model-invocation")` and asserts `skills/<name>/agents/openai.yaml` exists — a skill whose frontmatter fails to parse also silently skips this check. Step 3 above should update all three methods, not two.
- Exact `except` line numbers confirmed: `test_all_real_skills_have_name_field` at `scripts/tests/test_adapt_skills_for_codex.py:356-361`; `test_all_real_skills_have_metadata_short_description` at `:383-388`; `test_all_real_skills_have_openai_yaml` at `:416-421`. All three share the same `fm_end = re.search(r"\n---\s*\n", text[3:])` / `if not fm_end: continue` guard immediately before the try/except — that `continue` is the intentional "no frontmatter block" skip and should stay; only the `except Exception: continue` needs to change.
- Alternative fix shape available in-repo: `scripts/tests/test_enh494_skill_companions.py:71-85` (`TestSkillLineLimit.test_all_skills_within_limit`) shows the established "walk `skills/*/SKILL.md`, accumulate all offenders, single aggregated `assert not offenders` with all paths in the message" convention, rather than failing on the first bad file with `pytest.fail`. Either shape (fail-fast `pytest.fail` per the issue's proposal, or aggregate-and-report like this sibling test) is consistent with codebase convention — fail-fast is simpler and matches the issue's existing proposed diff.
- `skills/manage-issue/SKILL.md` and `skills/update-docs/SKILL.md` currently have **no `name:` field and no `metadata:` block at all** in frontmatter (confirmed by reading both files in full) — so after quoting the fix, both will still fail `test_all_real_skills_have_name_field`/`test_all_real_skills_have_metadata_short_description` unless `name:`/`metadata:` are also added (matches step 2, but worth flagging as not just a quoting fix). Reference shape from a correctly-adapted file, `skills/audit-loop-run/SKILL.md:2` (`name: audit-loop-run`) and `:30-31` (`metadata:` / `short-description:`).
- Related but out of scope: `scripts/little_loops/frontmatter.py:175-217` (`parse_skill_frontmatter()`, the canonical SKILL.md frontmatter reader used by `ll-action`, `ll-artifact`, `tool_catalog.py`, etc.) has the same permissive-fallback shape — on `yaml.YAMLError` it silently degrades to a line-by-line key:value scan instead of raising. This means production code paths (not just the test guard) currently tolerate the same malformed frontmatter without erroring. Not part of this bug's stated scope (which targets the test guard only), but a plausible follow-up if silent degradation in the runtime parser is also undesired.

## Implementation Steps

1. Quote the offending `description:` strings in `manage-issue` and `update-docs` (and `audit-loop-run`, `review-loop` while in the area).
2. Verify `name:`/`metadata:` presence on all four, re-running `ll-adapt-skills-for-codex --apply` if needed (confirmed via research: `manage-issue` and `update-docs` currently have neither field — quoting alone will not make them pass).
3. Change the `except Exception: continue` to a hard failure in all **three** `TestRealSkillsIntegrationGuard` methods: `test_all_real_skills_have_name_field` (scripts/tests/test_adapt_skills_for_codex.py:356-361), `test_all_real_skills_have_metadata_short_description` (:383-388), and `test_all_real_skills_have_openai_yaml` (:416-421 — same defect, not in original scope).
4. Run `python -m pytest scripts/tests/test_adapt_skills_for_codex.py -v` to confirm the guard now passes cleanly and would catch a reintroduced regression.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add a `tmp_path`-based fixture test proving the guard now hard-fails (not silently skips) on a synthetic malformed-frontmatter `SKILL.md` — closes the regression-proofing gap left once the 4 real files are fixed and their parse errors no longer exercise the except branch.
6. Spot-check `scripts/tests/test_wiring_skills_and_commands.py`'s raw substring assertions against `skills/manage-issue/SKILL.md` (e.g. `"status: done"`, `"parent: EPIC-NNN"`) still match after quoting the offending `description:` value.
7. Re-run `ll-verify-triggers` after the fix — its `_load_skill_descriptions()`/`_load_trigger_fixtures()` in `scripts/little_loops/cli/verify_triggers.py` has the same silent-skip shape and currently excludes these 4 skills from trigger collision scoring; confirm no new collision/regression once they're included.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md`
- `skills/update-docs/SKILL.md`
- `skills/audit-loop-run/SKILL.md`
- `skills/review-loop/SKILL.md`
- `scripts/tests/test_adapt_skills_for_codex.py`

### Dependent Files (Callers/Importers)
- N/A for the guard fix itself — but `scripts/little_loops/cli/verify_triggers.py`'s `_load_skill_descriptions()` / `_load_trigger_fixtures()` has the **same-shape** `except yaml.YAMLError: continue` swallow and currently silently drops these 4 skills from the corpus `ll-verify-triggers` scores. Once the 4 SKILL.md files parse cleanly, they become newly visible to trigger precision/recall and cross-skill collision scoring — re-run `ll-verify-triggers` after the fix to confirm no new collision/regression. _(Wiring pass added by `/ll:wire-issue`, not in original scope)_

### Similar Patterns
- Other `SKILL.md` files under `skills/*/SKILL.md` should be spot-checked for the same unquoted-colon defect in `arguments[].description`.
- Other hand-rolled SKILL.md frontmatter readers with permissive/silent-skip fallback shapes exist beyond the guard and `frontmatter.py` (already noted out-of-scope): `scripts/little_loops/doc_counts.py:_parse_skill_frontmatter()` (near-duplicate of `frontmatter.py`, but unaffected here since it only reads the top-level `description`, not the corrupted `arguments[].description`), `scripts/little_loops/cli/action.py:_read_skill_description()`, `scripts/little_loops/cli/generate_skill_descriptions.py:_parse_frontmatter()` — same defect class as prior closed issues BUG-1627/BUG-1616, confirmed unaffected by this fix but a plausible future follow-up. _(Wiring pass added by `/ll:wire-issue`)_

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` (all **three** methods: `test_all_real_skills_have_name_field`, `test_all_real_skills_have_metadata_short_description`, and `test_all_real_skills_have_openai_yaml` — the third shares the same `except Exception: continue` hole, found during refinement research).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — contains raw substring assertions against `skills/manage-issue/SKILL.md` text (e.g. `"status: done"`, `"parent: EPIC-NNN"`). Spot-check after quoting the offending `description:` value that none of these substrings shift or get altered.
- `scripts/tests/test_frontmatter.py::TestParseSkillFrontmatter::test_falls_back_to_line_scan_on_invalid_yaml` (lines ~324-330) — already covers the identical malformed-colon-in-description case via `parse_skill_frontmatter()`'s permissive fallback, and is confirmed out of scope / should remain green and unchanged (it documents intentionally-tolerated runtime behavior, distinct from the test-guard bug being fixed here).
- **Test gap**: no test constructs a deliberately malformed `SKILL.md` fixture to regression-guard the exception-handling fix itself — once the 4 real skills are fixed, the new hard-failure branch in all 3 guard methods is never exercised again by the real-skills walk. Add a `tmp_path`-based fixture test (pattern: earlier `tmp_path / "skills" / "my-skill" / "SKILL.md"` fixtures already used elsewhere in `test_adapt_skills_for_codex.py`) asserting the guard now fails (not silently skips) on a synthetic unquoted-colon-in-description frontmatter block.

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P1 - A test guard whose entire purpose is catching invalid skill frontmatter is currently unable to catch invalid skill frontmatter; four real skills are silently unvalidated.
- **Effort**: Small - one-line change in each of two test methods, plus quoting fixes in four SKILL.md files.
- **Risk**: Low - test-only behavior change plus non-semantic YAML quoting; no runtime logic changes.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` (fix) - 2026-07-25T16:13:17Z - `f9ca1652-616c-45a0-9f8a-aec5b6b00e55.jsonl`
- `/ll:wire-issue` - 2026-07-25T15:59:38 - `b8bcf196-fa53-4c31-b9c6-2e9d46816fc1.jsonl`
- `/ll:refine-issue` - 2026-07-25T15:54:11 - `7c0ec3fc-9272-4910-a2c8-551019ea8d67.jsonl`
- `/ll:capture-issue` - 2026-07-25T15:05:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbb7c091-3f00-4fb8-832d-879e0fbb4eec.jsonl`

---
## Status
**Open** | Created: 2026-07-25 | Priority: P1
