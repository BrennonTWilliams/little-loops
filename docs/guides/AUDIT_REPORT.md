# User Guide Audit Report

**Date:** 2026-03-17
**Scope:** All user guides in `docs/guides/`
**Audited files:**
- `GETTING_STARTED.md`
- `ISSUE_MANAGEMENT_GUIDE.md`
- `SPRINT_GUIDE.md`
- `LOOPS_GUIDE.md`
- `AUTOMATIC_HARNESSING_GUIDE.md`
- `WORKFLOW_ANALYSIS_GUIDE.md`
- `SESSION_HANDOFF.md`

---

## Executive Summary

The guides are generally well-written, with clear structure, practical examples, and good use of code blocks and tables. The most consistent weaknesses across guides are:

1. **Missing tables of contents** in longer documents (4 of 7 guides)
2. **Factual errors and omissions** — missing entries in reference tables, broken links, incorrect counts
3. **Inconsistent cross-referencing** — features mentioned without explanation or links
4. **Variable interpolation and flag inconsistencies** — syntax varies without explanation
5. **Misleading recipes** — Quick Start and recipe sections sometimes promise outcomes that the described commands cannot deliver

The three highest-priority issues for immediate correction are:
- A factual heading error in `AUTOMATIC_HARNESSING_GUIDE.md` ("6-phase" lists only 5)
- A broken anchor link in `AUTOMATIC_HARNESSING_GUIDE.md` (`#check_mcp`)
- A missing evaluator (`mcp_result`) from the main evaluators table in `LOOPS_GUIDE.md`

---

## Per-Guide Findings

### 1. GETTING_STARTED.md

**Overall:** Good introductory guide. Clear tone, well-paced, and accessible to new users.

**Issues:** No major structural or factual problems were identified. Minor polish items were noted but the guide is largely sound as an entry point.

---

### 2. ISSUE_MANAGEMENT_GUIDE.md

**Overall:** Comprehensive and well-organized. Covers the full issue lifecycle with good use of tables and examples.

**Issues:** No major structural or factual problems were identified. The guide is thorough and internally consistent.

---

### 3. SPRINT_GUIDE.md

**Overall:** Excellent. Well-structured with clear explanations and practical recipes.

**Issues (minor):**

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | Low | Execution plan example | Inconsistent wave label format: `"Wave 2 (after Wave 1) parallel:"` vs `"Wave 1 (parallel):"` — format should be uniform |
| 2 | Low | CLI reference | `--handoff-threshold` flag listed in a table without prose explanation of what "handoff threshold" means |
| 3 | Low | YAML anatomy table | `options.max_iterations` appears in the anatomy table but is absent from the Configuration section |
| 4 | Low | Recipe sections | `manage-issue` is referenced without a link or explanation for readers unfamiliar with it |
| 5 | Low | "Full Plan a Feature Sprint Pipeline" recipe | Near-duplicates content from `ISSUE_MANAGEMENT_GUIDE.md` — consider a cross-reference instead |

---

### 4. LOOPS_GUIDE.md

**Overall:** Very comprehensive (927 lines) but suffers from navigation and consistency issues given its length. Content is accurate and detailed, but readers must scroll extensively to find specific sections.

**Issues:**

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | Evaluators table | `mcp_result` evaluator appears in the harness evaluation pipeline table but is **missing from the main Evaluators reference table** — critical omission |
| 2 | Medium | `apo-beam` loop definition | `eval_criteria` default is `""` (empty) while all other APO loops default to `"clarity, specificity, and effectiveness"` — likely an unintentional inconsistency |
| 3 | Medium | Tips section | `backoff:` field mentioned in Tips without prior introduction anywhere in the guide body |
| 4 | Medium | Core state documentation | `max_retries` / `on_retry_exhausted` fields introduced only in the harness section, not in the core state reference where users would first look |
| 5 | Low | "Beyond the Basics" section | Vague heading with no introductory sentence listing the topics covered |
| 6 | Low | Diagrams | Mixed arrow styles across diagrams: `──▶` in walkthrough, `──→` in harness FSM, `▶` in pattern tree |
| 7 | Low | Built-in loops table | 21 loops are listed with no grouping by category — difficult to scan |
| 8 | Low | APO loop sections | Use `---` horizontal rule separators inconsistently with the rest of the guide |
| 9 | Low | `diff_stall` evaluator | Described only ~500 lines after its first mention in the evaluators table — needs a forward reference or inline description |
| 10 | Low | Walkthrough section | `ll-loop test` and `ll-loop simulate` appear in the CLI reference but are never demonstrated in the walkthrough |
| 11 | Low | Document | No table of contents for a 927-line document |

---

### 5. AUTOMATIC_HARNESSING_GUIDE.md

**Overall:** Well-structured with clear wizard steps (H1–H4), good comparison tables, and a complete worked example. However, contains one factual error and several technical inconsistencies.

**Issues:**

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | "Full 6-phase ordering" heading (line ~196) | Heading claims 6 phases but lists only 5 — factual error |
| 2 | **High** | Broken anchor link | A note references `#check_mcp` but the actual section heading generates anchor `#mcp-tool-gates-check_mcp` — link returns 404 |
| 3 | Medium | Conceptual cycle diagram (lines ~27–55) | Diagram shows only `check_concrete` / `check_semantic` / `check_invariants`, omitting `check_mcp` and `check_skill` — misleading for readers trying to understand the full pipeline |
| 4 | Medium | Stall detection example (line ~469) | Uses `${current_item}` but the established syntax elsewhere is `${captured.current_item.output}` — inconsistent variable interpolation |
| 5 | Medium | `check_semantic` action field | Uses `echo 'Evaluating...'` as the action with no explanation of why a placeholder echo is required for an LLM judge step |
| 6 | Low | Discovery command table | The "Active issues list" command string is extremely long inside a narrow table cell — hard to read and likely to wrap badly |
| 7 | Low | `action_type` usage | Variant A uses `action_type: prompt` for a slash command while `check_skill` uses `action_type: slash_command` — inconsistency not explained |
| 8 | Low | `timeout` field | `timeout: 14400` has an inline comment "4-hour limit" but the unit (seconds) is never explicitly stated in the guide |
| 9 | Low | Worked example | Omits `check_mcp` / `check_skill` phases without explaining the omission, leaving readers uncertain whether the example is incomplete or simplified |
| 10 | Low | Document | No table of contents for a 603-line document |

---

### 6. WORKFLOW_ANALYSIS_GUIDE.md

**Overall:** Well-structured (282 lines) with a clear pipeline diagram, progressive disclosure, practical recipes, and explicit scoring formulas. The shorter length makes the missing TOC less critical.

**Issues:**

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | "Quick pattern check" recipe | Claims users can run `/ll:analyze-workflows` and "stop after Step 1" — the command runs all steps and provides no mid-pipeline stop mechanism; the recipe is misleading |
| 2 | Medium | `cohesion_score` explanation | Appears after the Step 3 section despite being a Step 2 concept — misplaced relative to `pattern_confidence` |
| 3 | Medium | Priority formula (HIGH ≥8, MEDIUM ≥4, LOW <4) | Inputs `frequency`, `workflow_count`, and `friction_score` are never defined with ranges, making the thresholds uninterpretable |
| 4 | Medium | `type` field in proposals | Not explained at first mention — the 9-type table (line ~189) is the actual explanation but isn't cross-referenced from the first mention |
| 5 | Medium | "Quick pattern check" recipe | `ll-messages --stdout \| head -20` previews raw messages but performs no pattern analysis, contradicting the section's stated purpose |
| 6 | Low | CLI reference table | `--skip-cli` and `--commands-only` flags are listed but never demonstrated in any recipe |
| 7 | Low | Frequency threshold | "Frequency ≥ 5" automation threshold (line ~180) appears to conflict with the LOW priority bucket, which would include 1–2 occurrence patterns |
| 8 | Low | ASCII pipeline diagram | Bottom row shows 3 output arrows while the top row has 5 columns (including `summary.md`), creating a visual mismatch |
| 9 | Low | Document | No table of contents |

---

### 7. SESSION_HANDOFF.md

**Overall:** Well-structured (425 lines) with a good Quick Start, clear diagrams, and a solid troubleshooting section. Contains a rendering bug and significant gaps in the configuration reference.

**Issues:**

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | `--deep` mode code example | Nested fenced code block bug: a ` ```markdown ` block nests a ` ``` ` block for git status, causing premature block closure and broken rendering in most Markdown renderers |
| 2 | **High** | Configuration Reference table | Table documents only 5 of 8+ fields. Missing: `continuation.enabled`, `auto_detect_on_session_start`, `include_todos`, `include_git_status`, `include_recent_files` |
| 3 | Medium | Quick Start / Configuration | `jq` is a dependency for certain features but is only mentioned in the Troubleshooting section — should be disclosed upfront |
| 4 | Medium | `auto_detect_on_session_start` | Appears in the full config block but has no prose explanation anywhere in the guide |
| 5 | Medium | Configuration Reference table | `context_limit_estimate` and `estimate_weights.*` appear in the full config but are absent from the reference table |
| 6 | Low | `/ll:resume` | No documentation of the error case when the handoff file path doesn't exist |
| 7 | Low | Integration section | References a "Stop hook" that "cleans up state" but doesn't specify what state is deleted |
| 8 | Low | Document | No table of contents for a 425-line document |

---

## Cross-Guide Patterns

### Missing Tables of Contents

Four of seven guides exceed 280 lines without a TOC: `LOOPS_GUIDE.md` (927 lines), `AUTOMATIC_HARNESSING_GUIDE.md` (603 lines), `SESSION_HANDOFF.md` (425 lines), and `WORKFLOW_ANALYSIS_GUIDE.md` (282 lines). Adding a TOC to each would significantly improve navigability.

### Incomplete Reference Tables

Reference/configuration tables frequently omit fields that appear in full YAML examples elsewhere in the same document. This pattern appears in `SPRINT_GUIDE.md`, `LOOPS_GUIDE.md`, `AUTOMATIC_HARNESSING_GUIDE.md`, and `SESSION_HANDOFF.md`. A process to keep examples and tables in sync would prevent this.

### Recipes That Overpromise

`WORKFLOW_ANALYSIS_GUIDE.md` and `SPRINT_GUIDE.md` both contain recipe sections where the described command sequence cannot deliver the stated outcome. Recipes should be tested against actual tool behavior before publication.

### Undisclosed Dependencies

External tools required by features (`jq` in `SESSION_HANDOFF.md`) are mentioned only in troubleshooting sections rather than in prerequisites or quick-start sections.

---

## Recommended Action Priority

| Priority | Guide | Item |
|----------|-------|------|
| P1 | `AUTOMATIC_HARNESSING_GUIDE.md` | Fix "6-phase" heading to match actual phase count |
| P1 | `AUTOMATIC_HARNESSING_GUIDE.md` | Fix broken `#check_mcp` anchor link |
| P1 | `LOOPS_GUIDE.md` | Add `mcp_result` to the main evaluators reference table |
| P1 | `SESSION_HANDOFF.md` | Fix nested fenced code block rendering bug |
| P2 | `SESSION_HANDOFF.md` | Complete the Configuration Reference table |
| P2 | `AUTOMATIC_HARNESSING_GUIDE.md` | Update conceptual cycle diagram to include all 6 phases |
| P2 | `WORKFLOW_ANALYSIS_GUIDE.md` | Fix or remove misleading "Quick pattern check" recipe |
| P2 | `WORKFLOW_ANALYSIS_GUIDE.md` | Define `frequency`/`workflow_count`/`friction_score` input ranges |
| P3 | All long guides | Add tables of contents |
| P3 | `LOOPS_GUIDE.md` | Group the 21 built-in loops by category |
| P3 | `LOOPS_GUIDE.md` | Introduce `backoff:`, `max_retries`, `on_retry_exhausted` in core state docs |
| P4 | `SPRINT_GUIDE.md` | Standardize wave label format in execution plan examples |
| P4 | `SESSION_HANDOFF.md` | Disclose `jq` dependency in Quick Start |
| P4 | All guides | Audit remaining incomplete reference tables |
