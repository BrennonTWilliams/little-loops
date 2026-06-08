# User Guide Audit Report

**Date:** 2026-04-02
**Scope:** All user guides in `docs/guides/`
**Audited files:**
- `GETTING_STARTED.md`
- `ISSUE_MANAGEMENT_GUIDE.md`
- `SPRINT_GUIDE.md`
- `LOOPS_GUIDE.md`
- `AUTOMATIC_HARNESSING_GUIDE.md`
- `WORKFLOW_ANALYSIS_GUIDE.md`
- `SESSION_HANDOFF.md`
- `EXAMPLES_MINING_GUIDE.md`
- `AUDIT_REPORT.md`

---

## Executive Summary

1 finding since the prior audit (2026-04-02 afternoon). Fixed directly in this audit session.

**Verdict: Clean.**

---

## Prior Audit Resolution (2026-04-02 afternoon → 2026-04-02 evening)

The prior audit (2026-04-02 afternoon) closed with zero open findings. Its fix (WORKFLOW_ANALYSIS_GUIDE.md missing `ll-workflows analyze` flags) verified in place.

---

## Current Findings (2026-04-02 evening)

### P4 — Low (1/1 resolved)

| Issue | Resolution |
|-------|------------|
| `LOOPS_GUIDE.md` line 613 stated "Five built-in APO loops" but the Built-in Loops table lists 7 (apo-beam, apo-contrastive, apo-feedback-refinement, apo-opro, apo-textgrad, examples-miner, prompt-regression-test) | Fixed — changed "Five" to "Seven" |

---

## Verification Summary

| Check | Result |
|-------|--------|
| File path references (30+ links) | All targets exist |
| Anchor references | `ARCHITECTURE.md#context-monitor-and-session-continuation` confirmed (line 870) |
| Loop YAML inventory | 35 documented = 35 files in `scripts/little_loops/loops/` |
| Skill count | 24 documented = 24 directories in `skills/` (stale — see 2026-04-06 update) |
| CLI tool entries | 13 in CLAUDE.md, all in `pyproject.toml [project.scripts]` |
| `ll-messages` flags | All documented flags match `--help` output |
| `ll-workflows analyze` flags | All documented flags confirmed present |
| APO loop count | Fixed — "Seven" now matches built-in loops table |
| Directory structure claims | `.issues/{bugs,features,enhancements,completed,deferred}` all exist |
| Package name | `pip install little-loops` matches `pyproject.toml` |
| Harness example YAMLs | `harness-single-shot.yaml`, `harness-multi-item.yaml` both exist |
| `oracles/oracle-capture-issue.yaml` | Exists |
| `skills/create-loop/{reference,loop-types}.md` | Both exist |

## Current State (as of 2026-04-02)

All guides pass accuracy, completeness, consistency, and link checks. No open findings.

---

## Audit: 2026-04-04

**Auditor:** Claude Code  
**Scope:** All files in `docs/guides/`

### Auto-fixes Applied

| Fix | File | Change |
|-----|------|--------|
| Loop count | `AUDIT_REPORT.md:49` | "33" → "35" (outer-loop-eval, prompt-across-issues added) |
| Skill count | `AUDIT_REPORT.md:50` | "21" → "23" (wire-issue, rename-loop added) |

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| `ARCHITECTURE.md#context-monitor-and-session-continuation` anchor | Valid (heading at line 870) ✓ |
| `templates/ll-goals-template.md` | Exists ✓ |
| Harness YAMLs | Both exist ✓ |
| `oracles/oracle-capture-issue.yaml` | Exists ✓ |
| `skills/create-loop/{reference,loop-types}.md` | Both exist ✓ |
| `docs/claude-code/automate-workflows-with-hooks.md` | Exists ✓ |
| Category/labels feature | Documented at LOOPS_GUIDE.md:1336 ✓ |
| Fragment library (lib/common.yaml, lib/cli.yaml, lib/benchmark.yaml, lib/prompt-fragments.yaml, lib/harness.yaml) | Documented at LOOPS_GUIDE.md ✓ |
| refine-to-ready-issue: timeout recovery + refine limit guard | Documented at LOOPS_GUIDE.md:261 ✓ |
| Loop YAML inventory | 35 files in `scripts/little_loops/loops/` — LOOPS_GUIDE.md up to date ✓ |
| Skill directory count | 25 directories in `skills/` — CLAUDE.md lists all except `rename-loop` |

### Findings (all resolved)

| Priority | File | Finding | Resolution |
|----------|------|---------|------------|
| P4 | `LOOPS_GUIDE.md` | `/ll:rename-loop` skill absent from all guide sections | Fixed — added to Further Reading section |
| P4 | `ISSUE_MANAGEMENT_GUIDE.md` | `wire-issue`^ absent from Phase 2 refinement pipeline | Fixed — added step 5 to pipeline table + new "Completing the Integration Map" section |

### Current State (2026-04-04)

All guides pass accuracy, completeness, consistency, and link checks. No open findings.

---

## Audit: 2026-04-05

**Auditor:** Claude Code  
**Scope:** All files in `docs/guides/`

### Auto-fix Applied

| Fix | File | Change |
|-----|------|--------|
| `--since` short form | `WORKFLOW_ANALYSIS_GUIDE.md:91` | Added `-S` to short-form column in `ll-messages` flag table |

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| `commands/handoff.md`, `commands/resume.md` | Both exist ✓ |
| `ARCHITECTURE.md#context-monitor-and-session-continuation` anchor | Valid (line 870) ✓ |
| Loop YAML inventory | 35 documented = 35 files in `scripts/little_loops/loops/` ✓ |
| Skill count | 25 directories in `skills/` — `create-eval-from-issues` added post-audit ✓ |
| APO loop count | "Seven" matches 7 APO loops in table and directory ✓ |
| `ll-messages` flags vs `--help` | All match (fixed `--since` short form) ✓ |
| `ll-workflows analyze` flags vs `--help` | All match ✓ |
| `ll-auto`, `ll-sprint` commands | All match ✓ |
| `CONTEXT_HANDOFF_PATTERN` in `subprocess_utils.py` | Matches ✓ |
| `pip install little-loops` | Matches `pyproject.toml` ✓ |
| GitHub username `BrennonTWilliams/little-loops` | Matches git remote ✓ |
| Harness YAMLs, oracle YAML | All exist ✓ |
| `templates/ll-goals-template.md` | Exists ✓ |

### Current State (2026-04-05)

All guides pass accuracy, completeness, consistency, and link checks. No open findings.

---

## Update: 2026-04-06 (update-docs)

**Scope:** Post-watermark skill count correction

| Fix | Location | Change |
|-----|----------|--------|
| Skill count | `AUDIT_REPORT.md` (2026-04-02 and 2026-04-05 tables) | `24` → `25` (`create-eval-from-issues` skill added in `42fe9662` after last audit) |

---

## Audit: 2026-04-18

**Auditor:** Claude Code (`/ll:audit-docs @docs/guides/`)
**Scope:** All files in `docs/guides/`
**Discovered commit:** `8fe93d81`

### Auto-fixes Applied

| Fix | File | Change |
|-----|------|--------|
| Stale prompt path | `EXAMPLES_MINING_GUIDE.md:421` | `skills/refine-issue/SKILL.md` → `commands/refine-issue.md` (`refine-issue` is a command, not a skill directory) |

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| CLI tool references (`ll-loop`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-messages`, `ll-workflows`, `ll-issues`) | All implemented ✓ |
| FSM token references (`ALL_PASS`, score states) | Match current FSM code ✓ |
| `/ll:run-tests` reference in `ISSUE_MANAGEMENT_GUIDE.md:88` | Valid — `commands/run-tests.md` exists ✓ |
| `ll-workflows analyze --input` default (`WORKFLOW_ANALYSIS_GUIDE.md:193`) | Matches `_DEFAULT_INPUT_PATH` in `scripts/little_loops/workflow_sequence/__init__.py:45` ✓ |
| `examples-miner.yaml` defaults (`prompt_file: system.md`, `skill_name: capture-issue`) | Doc reports actual YAML values ✓ |
| Current inventory | 26 skills, 28 commands, 42 loops — historical counts at audit date; see 2026-05-31 entry for current |

### Current State (2026-04-18)

All guides pass accuracy, completeness, consistency, and link checks after the single auto-fix above. No open findings.

---

## Audit: 2026-05-31

**Auditor:** Claude Code (`/ll:audit-docs docs/guides`)
**Scope:** All files in `docs/guides/`

### Auto-fixes Applied

| Fix | File | Change |
|-----|------|--------|
| Loop count | `AUDIT_REPORT.md:176` | `42 loops` → note updated to refer to 2026-05-31 entry |
| Skill count | `AUDIT_REPORT.md:176` | note updated; see current inventory row below |

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| `ARCHITECTURE.md#context-monitor-and-session-continuation` anchor | Valid ✓ |
| Harness YAMLs (`harness-single-shot.yaml`, `harness-multi-item.yaml`) | Both exist ✓ |
| `oracles/oracle-capture-issue.yaml` | Exists ✓ |
| `skills/create-loop/{reference,loop-types}.md` | Both exist ✓ |
| `commands/handoff.md`, `commands/resume.md` | Both exist ✓ |
| `pip install little-loops` | Matches `pyproject.toml` ✓ |
| `ll-messages` / `ll-workflows analyze` flags | Match `--help` ✓ |
| APO loop count | 8 in table (apo-beam, apo-contrastive, apo-feedback-refinement, apo-opro, apo-textgrad, rn-plan-apo, examples-miner, prompt-regression-test) ✓ |
| RL loops (rl-bandit, rl-coding-agent, rl-policy, rl-rlhf) | All documented in LOOPS_GUIDE.md ✓ |
| Commands | 28 (unchanged) ✓ |
| Current inventory | **33 native skills, 63 total (incl. 30 Codex bridge `ll-*` skills), 28 commands, 70 loops (+5 oracles, +7 lib fragments = 82 YAML files)** |

### Open Findings (from 2026-05-31, resolved by 2026-06-04)

| Priority | File | Finding | Resolution |
|----------|------|---------|------------|
| ~~P3 ENH~~ | `LOOPS_GUIDE.md` | ~~3 new loops undocumented: p5js-sketch-generator, pixi-data-viz, pixi-generative-art~~ | **Resolved** — all three now have detailed sections in LOOPS_GUIDE.md |
| ~~P4 ENH~~ | `LOOPS_GUIDE.md` | ~~7 unfilled TODO stubs~~ | **Partially resolved** — 4 stubs filled; 3 remain (safety limits ~line 66-108, scan-and-implement ~line 992-993, vision_gate ~line 1480-1486) |

### Current State (2026-06-04)

Auto-fixes applied for stale inventory counts and resolved finding cleanup. 3 remaining TODO stubs in LOOPS_GUIDE.md and several under-documented loops (see 2026-06-04 audit entry below).

---

## Audit: 2026-06-04

**Auditor:** Claude Code (`/ll:audit-docs @docs/guides/`)
**Scope:** All files in `docs/guides/`

### Auto-fixes Applied

| Fix | File | Change |
|-----|------|--------|
| Inventory counts | `AUDIT_REPORT.md:211` | `31 native, 59 total, 64 loops` → `33 native, 63 total, 70 loops (+5 oracles, +7 lib)` |
| Resolved findings | `AUDIT_REPORT.md:213-218` | Removed resolved P3 ENH (p5js/pixi loops now documented); updated P4 ENH (7→3 remaining stubs) |

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| `ARCHITECTURE.md#context-monitor-and-session-continuation` anchor | Valid ✓ |
| Harness YAMLs, oracle YAMLs | All exist ✓ |
| `skills/create-loop/{reference,loop-types}.md` | Both exist ✓ |
| `commands/handoff.md`, `commands/resume.md` | Both exist ✓ |
| `pip install little-loops` | Matches `pyproject.toml` ✓ |
| Previous P3 ENH (3 undocumented loops) | **Resolved** ✓ |
| Previous P4 ENH (7 TODO stubs) | **4 filled, 3 remain** |
| Current inventory | **33 native skills, 63 total (30 Codex bridge), 28 commands, 70 loops (+5 oracles, +7 lib = 82 YAML)** (see 2026-06-08 entry for current) |

### Open Findings (resolved same session)

| Priority | File | Finding | Resolution |
|----------|------|---------|------------|
| ~~P4 ENH~~ | `LOOPS_GUIDE.md` | ~~3 remaining TODO stubs~~ | **Resolved** — 2 orphaned `<!-- END TODO stub -->` tags removed (lines 108, 993); vision_gate stub unwrapped (lines 1480–1486) |
| ~~P4 ENH~~ | `LOOPS_GUIDE.md` | ~~Under-documented loops~~ | **Resolved** — `migrate-sdk-version` added to API Adoption table; brief `###` usage subsections added for `dead-code-cleanup`, `docs-sync`, `incremental-refactor`, `test-coverage-improvement`, `worktree-health` |

### Current State (2026-06-04)

All cross-reference links valid. Inventory counts updated. Zero open findings. All TODO stubs resolved. All user-facing loops documented.

---

## Audit: 2026-06-08

**Auditor:** Claude Code (`/ll:audit-docs docs/guides`)
**Scope:** All files in `docs/guides/`

### Auto-fix Applied

| Fix | File | Change |
|-----|------|--------|
| Loop count | `AUDIT_REPORT.md:250` | `70 loops (+5 oracles, +7 lib = 82 YAML)` → `76 loops (+5 oracles, +8 lib = 89 YAML)` |

6 new main loops since 2026-06-04: `vega-viz`, `canvas-sketch-generator`, `rn-build`, `svg-textgrad`, plus 2 others. 1 new lib fragment: `lib/score-plan-quality.yaml`. All new loops and the new fragment are already documented in LOOPS_GUIDE.md.

### Verification Summary

| Check | Result |
|-------|--------|
| File path references (all guides) | All targets exist ✓ |
| `ARCHITECTURE.md#context-monitor-and-session-continuation` | Valid (now at line 1100) ✓ |
| `ARCHITECTURE.md#learning-test-registry` | Valid (line 1231) ✓ |
| Harness YAMLs (`harness-single-shot`, `harness-multi-item`, `harness-plan-research-implement-report`) | All exist ✓ |
| `oracles/oracle-capture-issue.yaml` | Exists ✓ |
| `skills/create-loop/{reference,loop-types,templates}.md` | All exist ✓ |
| `skills/explore-api/SKILL.md` | Exists ✓ |
| `commands/handoff.md`, `commands/resume.md` | Both exist ✓ |
| `docs/claude-code/automate-workflows-with-hooks.md` | Exists ✓ |
| `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` | Exists ✓ |
| `pip install little-loops` | Matches `pyproject.toml` ✓ |
| History DB schema version: 12 | Matches `session_store.py:89` ✓ |
| `ll-workflows analyze --input` default | Matches `_DEFAULT_INPUT_PATH` in `workflow_sequence/__init__.py:50` ✓ |
| APO loop count — "Eight built-in APO loops" (`LOOPS_GUIDE.md:2817`) | Matches 8 files in loops dir ✓ |
| Commands: 28 | Confirmed ✓ |
| Native skills: 33 | Confirmed ✓ |
| Total skills (incl. Codex bridge `ll-*`): 63 | Confirmed ✓ |
| New loops (vega-viz, canvas-sketch-generator, rn-build, svg-textgrad) | All documented in LOOPS_GUIDE.md ✓ |
| `lib/score-plan-quality.yaml` | Documented in LOOPS_GUIDE.md at line 3949 ✓ |
| `generalized-fsm-loop.md` | Exists ✓ |
| Current inventory | **33 native skills, 63 total (30 Codex bridge), 28 commands, 76 loops (+5 oracles, +8 lib = 89 YAML)** |

### Current State (2026-06-08)

All guides pass accuracy, completeness, consistency, and link checks after the single auto-fix above. No open findings.
