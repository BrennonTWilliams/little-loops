# User Guide Audit Report

**Date:** 2026-03-22
**Scope:** All user guides in `docs/guides/`
**Audited files:**
- `GETTING_STARTED.md`
- `ISSUE_MANAGEMENT_GUIDE.md`
- `SPRINT_GUIDE.md`
- `LOOPS_GUIDE.md`
- `AUTOMATIC_HARNESSING_GUIDE.md`
- `WORKFLOW_ANALYSIS_GUIDE.md`
- `SESSION_HANDOFF.md`
- `EXAMPLES_MINING_GUIDE.md` *(added since prior audit)*

---

## Executive Summary

All 18 findings from the prior audit (2026-03-17) have been resolved. The guides are accurate, complete, internally consistent, and have valid cross-references. No new issues were found, including in `EXAMPLES_MINING_GUIDE.md` which was added since the prior audit.

**Verdict: Clean.**

---

## Prior Audit Resolution (2026-03-17 → 2026-03-22)

### P1 — Critical (4/4 resolved)

| Issue | Resolution |
|-------|------------|
| `AUTOMATIC_HARNESSING_GUIDE.md` "6-phase" heading listed only 5 phases | Fixed — heading now reads "5-phase" |
| `AUTOMATIC_HARNESSING_GUIDE.md` broken `#check_mcp` anchor | Fixed — all references use correct `#mcp-tool-gates-check_mcp` |
| `LOOPS_GUIDE.md` `mcp_result` missing from main evaluators table | Fixed — added with full verdict documentation |
| `SESSION_HANDOFF.md` nested fenced code block rendering bug | Fixed — outer block now uses `~~~markdown` delimiter |

### P2 — High (4/4 resolved)

| Issue | Resolution |
|-------|------------|
| `SESSION_HANDOFF.md` incomplete Configuration Reference table (5 of 13 fields) | Fixed — all 13 fields documented |
| `AUTOMATIC_HARNESSING_GUIDE.md` conceptual cycle diagram omitted `check_mcp` and `check_skill` | Fixed — all 5 evaluation phases shown |
| `WORKFLOW_ANALYSIS_GUIDE.md` "Quick pattern check" recipe incorrectly described `/ll:analyze-workflows` as stoppable mid-pipeline | Fixed — recipe now directs users to spawn `workflow-pattern-analyzer` agent directly |
| `WORKFLOW_ANALYSIS_GUIDE.md` `frequency`/`workflow_count`/`friction_score` ranges undefined | Fixed — Variable Definitions table added with ranges |

### P3/P4 — Medium/Low (10/10 resolved)

| Issue | Resolution |
|-------|------------|
| Four long guides missing tables of contents | Fixed — TOCs added to all four |
| `LOOPS_GUIDE.md` built-in loops table not grouped | Fixed — grouped by category (Issue Management, Code Quality, RL, APO, Harness) |
| `LOOPS_GUIDE.md` `backoff:`, `max_retries`, `on_retry_exhausted` undocumented in core state reference | Fixed — Retry and Timing Fields section added under Beyond the Basics |
| `SPRINT_GUIDE.md` `max_iterations` absent from Configuration section | Fixed — added to configuration table |
| `SPRINT_GUIDE.md` inconsistent wave label format in execution plan examples | Fixed — format unified |
| `SPRINT_GUIDE.md` `--handoff-threshold` flag without prose explanation | Fixed — paragraph explanation added after run flags table |
| `SESSION_HANDOFF.md` `jq` dependency undisclosed in Quick Start | Fixed — Prerequisites section added to Quick Start |
| `LOOPS_GUIDE.md` `apo-beam` `eval_criteria` default was empty while all other APO loops used a non-empty default | Fixed — default is now consistent across all APO loops |
| `AUTOMATIC_HARNESSING_GUIDE.md` `action_type: prompt` vs `action_type: slash_command` difference unexplained | Fixed — comparison table added |
| `WORKFLOW_ANALYSIS_GUIDE.md` multiple clarity fixes (cohesion_score placement, type field cross-reference, --skip-cli recipes, ASCII diagram arrow count, frequency/LOW priority note) | Fixed — all addressed |

---

## New Guide: `EXAMPLES_MINING_GUIDE.md`

Added since the prior audit. No issues found:

- All 8 file references verified to exist (`loops/examples-miner.yaml`, `loops/oracles/oracle-capture-issue.yaml`, `loops/apo-textgrad.yaml`, `LOOPS_GUIDE.md`, `AUTOMATIC_HARNESSING_GUIDE.md`, `docs/generalized-fsm-loop.md`, and others)
- `--skill` and `--examples-format` CLI flags verified in `scripts/little_loops/cli/messages.py`
- Content is technically accurate; FSM flow diagram matches documented behavior; all cross-references are valid

---

## Current State

All guides pass accuracy, completeness, consistency, and link checks. No open findings.
