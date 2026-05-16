---
id: ENH-1378
type: ENH
priority: P3
decision_needed: false
completed_at: 2026-05-06T00:00:00Z
status: done
---

# ENH-1522: Rename `analyze-loop` → `debug-loop-run` and `assess-loop` → `audit-loop-run`

## Summary

Rename two loop analysis skills to better reflect their purpose: `analyze-loop` becomes `debug-loop-run` (emphasizing per-run debugging) and `assess-loop` becomes `audit-loop-run` (emphasizing effectiveness auditing). All references across skill definitions, FSM loop YAML, tests, documentation, and commands were updated atomically.

## Motivation

The old names did not clearly communicate what each skill does at a glance:
- `analyze-loop` sounded like it analyzed the loop definition; it actually debugs a specific run's execution history.
- `assess-loop` was too generic; `audit-loop-run` signals effectiveness auditing of a completed run.

## Resolution

### Files Changed

**Skill directories (git mv):**
- `skills/analyze-loop/` → `skills/debug-loop-run/`
- `skills/assess-loop/` → `skills/audit-loop-run/`

**SKILL.md content:**
- `skills/debug-loop-run/SKILL.md` — updated self-invocation examples, `discovered_by` frontmatter field, test file reference
- `skills/audit-loop-run/SKILL.md` — updated self-invocation examples, cross-references to `/ll:debug-loop-run`

**FSM loop YAML (functional):**
- `scripts/little_loops/loops/outer-loop-eval.yaml` — updated `/ll:analyze-loop` and `/ll:assess-loop` action strings in `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` states

**Test files (git mv + content):**
- `test_analyze_loop_synthesis.py` → `test_debug_loop_run_synthesis.py` — updated docstring, skill path references, inline comments
- `test_assess_loop_skill.py` → `test_audit_loop_run_skill.py` — updated docstring, skill path references, assertion error messages
- `test_enh1146_doc_wiring.py` — updated `ANALYZE_LOOP` path constant and error message strings
- `test_enh1268_doc_wiring.py` — updated class names (`TestAnalyzeLoopCommandsWiring` → `TestDebugLoopRunCommandsWiring`, etc.), method names (`_analyze_loop_section` → `_debug_loop_run_section`, etc.), section header search strings, and error messages
- `test_enh1115_doc_wiring.py` — updated error message string
- `test_outer_loop_eval.py` — updated `"analyze-loop" in state.get("action")` and `"assess-loop" in state.get("action")` assertions
- `test_builtin_loops.py` — updated docstring comment referencing old skill names

**Documentation:**
- `.claude/CLAUDE.md` — Automation & Loops skill list
- `commands/help.md` — skill name in usage block and quick-reference list
- `commands/loop-suggester.md` — keyword table entry
- `docs/reference/COMMANDS.md` — section headers (`### \`/ll:debug-loop-run\``, `### \`/ll:audit-loop-run\``), usage examples, "See also" links, skill summary table
- `README.md` — command table and skill table
- `CONTRIBUTING.md` — skills directory tree
- `CHANGELOG.md` — all historical and current entries referencing old names
- `docs/ARCHITECTURE.md` — skills directory tree
- `docs/generalized-fsm-loop.md` — comment referencing goal-alignment skills
- `docs/guides/LOOPS_GUIDE.md` — all `/ll:analyze-loop` and `/ll:assess-loop` references
- `scripts/little_loops/loops/README.md` — `outer-loop-eval` description

**Python source:**
- `scripts/little_loops/fsm/validation.py` — comment referencing old skill names (lines 600–601)

## Verification

Post-rename grep across all active code surfaces confirmed zero remaining references to `analyze-loop` or `assess-loop`. All 419 unrelated-to-rename tests passed; 9 pre-existing failures in `test_enh1115_doc_wiring.py` and `test_enh1146_doc_wiring.py` (throttle events and LLEvent count) were present before this change.

## Labels

`enhancement`, `rename`, `loops`, `debug-loop-run`, `audit-loop-run`

## Status

Completed
