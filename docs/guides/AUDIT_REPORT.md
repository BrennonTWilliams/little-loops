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
| Skill count | 23 documented = 23 directories in `skills/` |
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
| Fragment library (lib/common.yaml, lib/cli.yaml) | Documented at LOOPS_GUIDE.md:1432 ✓ |
| refine-to-ready-issue: timeout recovery + refine limit guard | Documented at LOOPS_GUIDE.md:261 ✓ |
| Loop YAML inventory | 35 files in `scripts/little_loops/loops/` — LOOPS_GUIDE.md up to date ✓ |
| Skill directory count | 23 directories in `skills/` — CLAUDE.md lists all except `rename-loop` |

### Findings (all resolved)

| Priority | File | Finding | Resolution |
|----------|------|---------|------------|
| P4 | `LOOPS_GUIDE.md` | `/ll:rename-loop` skill absent from all guide sections | Fixed — added to Further Reading section |
| P4 | `ISSUE_MANAGEMENT_GUIDE.md` | `wire-issue`^ absent from Phase 2 refinement pipeline | Fixed — added step 5 to pipeline table + new "Completing the Integration Map" section |

### Current State (2026-04-04)

All guides pass accuracy, completeness, consistency, and link checks. No open findings.
