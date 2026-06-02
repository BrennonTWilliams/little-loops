---
discovered_date: 2026-05-09
discovered_by: audit
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-05-11T09:59:22Z
status: done
---

# ENH-1404: Add argument-hint and standalone invocation docs to product-analyzer

## Summary

`product-analyzer` is listed in `CLAUDE.md` as a directly user-invocable skill, but its frontmatter has no `argument-hint`, `arguments`, or examples. When invoked standalone (not via `scan-product`), users get no guidance on what inputs are accepted or what the output is used for. This is especially important since the skill produces raw YAML — users invoking it directly should know they'll get structured output, not issue files.

## Current Behavior

`skills/product-analyzer/SKILL.md` frontmatter has no `argument-hint`, `arguments`, or Examples section. When invoked standalone (`/ll:product-analyzer`), users receive raw YAML output with no guidance on accepted inputs, available focus-area filters, or the difference between this skill and `/ll:scan-product`.

## Expected Behavior

`product-analyzer` frontmatter includes `argument-hint: "[focus-area]"` and an `arguments` block documenting the optional focus-area parameter. An Examples section at the bottom of the skill explains raw YAML output and directs users to `/ll:scan-product` for full workflow. The trigger description distinguishes the skill from the command.

## Motivation

This enhancement would:
- Expose the `focus-area` filter capability that currently exists but is undiscoverable
- Prevent user confusion between raw YAML skill output vs issue file creation via `scan-product`
- Align `product-analyzer` with other user-invocable skills that document their argument contracts

## Implementation Steps

### `skills/product-analyzer/SKILL.md` frontmatter

Add:
```yaml
argument-hint: "[focus-area]"
arguments:
  - name: focus-area
    description: "Optional: limit analysis to a specific goal ID, persona, or 'gaps|ux|opportunities'"
    required: false
```

### Add Examples section at the bottom of the skill

```markdown
## Examples

# Full product analysis (used by /ll:scan-product internally)
/ll:product-analyzer

# Focus on a specific strategic priority
/ll:product-analyzer gaps

# Focus on persona UX issues only
/ll:product-analyzer ux

# Focus on business value opportunities
/ll:product-analyzer opportunities

**Note**: This skill returns raw YAML findings. To create issue files from these findings, use `/ll:scan-product` instead.
```

### Update trigger description

Current: "Use when asked to analyze product goals, check feature gaps, or evaluate business value."

Improved: "Use when asked to analyze product goals, check feature gaps, or evaluate business value. Returns raw YAML findings. For full scan with issue file creation, use `/ll:scan-product`."

This makes the skill-vs-command distinction visible at the point of invocation, preventing user confusion about why no issue files are created.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/reference/COMMANDS.md` — add `**Arguments:**` block to the `### /ll:product-analyzer` section documenting the optional `[focus-area]` parameter; follow the pattern from the `align-issues` and `tradeoff-review-issues` entries added in ENH-1362/1363
5. Update `commands/help.md` — add or update the product-analyzer entry to surface standalone invocation with `[focus-area]`; check whether a dedicated `/ll:product-analyzer [focus-area]` block is needed or if the existing `Skills: product-analyzer` subordinate note under `/ll:scan-product` is sufficient per the help file convention
6. Create `scripts/tests/test_enh1404_doc_wiring.py` — wiring test asserting all acceptance criteria: `argument-hint`, `arguments:` block, `name: focus-area`, `## Examples` section, and updated description; use `_frontmatter()` and `_section()` helpers from `test_enh1402_doc_wiring.py` as the model

## Acceptance Criteria

- `argument-hint` is present in frontmatter
- `arguments` section documents the optional focus-area parameter
- Examples section clarifies raw YAML output and points to scan-product for full workflow
- Description distinguishes skill from command

## Scope Boundaries

- **In scope**: `argument-hint`/`arguments` frontmatter fields; Examples section; trigger description update in SKILL.md
- **Out of scope**: Implementing focus-area filtering logic (separate concern); changes to `scan-product` command behavior

## Integration Map

### Files to Modify
- `skills/product-analyzer/SKILL.md` — frontmatter (`argument-hint`, `arguments`), trigger description, add Examples section

### Dependent Files (Callers/Importers)
- `commands/scan-product.md` — invokes the skill; no changes needed here

### Similar Patterns
- `skills/configure/SKILL.md` — closest match: `argument-hint: "[area]"` with pipe-separated valid values in the `arguments[].description` field; same single-optional-positional structure
- `skills/capture-issue/SKILL.md` — `argument-hint: "[description]"` with two `required: false` arguments including a `flags` entry; shows the two-argument (value + flags) frontmatter pattern
- `skills/audit-docs/SKILL.md` — `argument-hint: "[scope]"` with `scope: "full|readme|file:<path>"` description format; shows how to enumerate valid choices in the description field

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`$ARGUMENTS` substitution**: The skills platform uses `$ARGUMENTS` as the body substitution variable. Adding `argument-hint` to the frontmatter is a discoverability/autocomplete hint only — it does NOT wire the argument into the skill body. If focus-area filtering is ever implemented (separate issue, out of scope here), the skill body would need to reference `$ARGUMENTS` explicitly. For this issue (documentation-only), no body changes are needed.
- **Current state confirmed**: `skills/product-analyzer/SKILL.md` has no `argument-hint`, no `arguments:` block, and no `## Examples` section. Frontmatter has exactly 3 fields: `description`, `model`, `allowed-tools`.
- **`scan-product` invocation**: `commands/scan-product.md` calls `skill="product-analyzer"` with a freeform injected prompt (no named arguments). No changes needed there.
- **Examples section placement**: End of file after `## REMEMBER: You are a product analyst, not a code reviewer` (line 288) — consistent with how `manage-issue`, `capture-issue`, and `init` place their Examples sections after all behavioral content.

### Tests

- N/A — documentation-only change; no behavioral logic modified

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1404_doc_wiring.py` — new test file needed; assert `argument-hint: "[focus-area]"` in frontmatter, `arguments:` block present, `name: focus-area` present, `## Examples` section present, description updated to mention `scan-product`; follow pattern from `test_enh1402_doc_wiring.py` (same `SKILL_FILE` target) and `test_enh1362_doc_wiring.py` / `test_enh1363_doc_wiring.py` (argument-hint + Examples assertions) [Agent 3 finding]

### Documentation
- `CLAUDE.md` — already lists `product-analyzer` as user-invocable; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:product-analyzer` section has no `**Arguments:**` block today; ENH-1362/1363 pattern requires adding one to match the `argument-hint` + `arguments:` frontmatter being added [Agent 2 finding]
- `commands/help.md` — no standalone `/ll:product-analyzer [focus-area]` entry exists; only appears as `Skills: product-analyzer` under `/ll:scan-product`; ENH-1362/1363 convention required help.md updates when argument-hint was added to similar skills [Agent 2 finding]

### Configuration
- N/A

## Evidence

- `skills/product-analyzer/SKILL.md:1-8` — frontmatter missing argument-hint/arguments
- Audit finding: "No examples in the skill frontmatter" (Major)
- `CLAUDE.md` — lists product-analyzer as user-invocable but no usage docs

## Impact

- **Priority**: P3 — Usability improvement; affects discoverability, not correctness
- **Effort**: Small — Documentation-only changes to one skill file
- **Risk**: Low — No behavioral changes; additive frontmatter and docs only
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `captured`

## Status

**Open** | Created: 2026-05-09 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-05-11T09:59:22 - `80ede08a-b81f-4ed8-ad7a-920cca3e6f43.jsonl`
- `/ll:ready-issue` - 2026-05-11T09:55:23 - `a677c3fc-a84a-438e-9ee0-21b7099435b2.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `efdd1801-4c77-4a8b-89f5-8b4d20701ec6.jsonl`
- `/ll:wire-issue` - 2026-05-11T09:51:33 - `c4e46643-020f-41ca-b8fa-383620609fa1.jsonl`
- `/ll:refine-issue` - 2026-05-11T09:47:00 - `52eefc9d-6742-4ead-9d63-13b45961b866.jsonl`
- `/ll:format-issue` - 2026-05-09T21:13:57 - `9656e0a3-1e1c-475f-af39-bb776aea9268.jsonl`
