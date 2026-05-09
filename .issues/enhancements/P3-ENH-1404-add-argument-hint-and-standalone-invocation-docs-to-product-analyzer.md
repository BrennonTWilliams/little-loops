---
discovered_date: 2026-05-09
discovered_by: audit
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
- Other skills with `argument-hint` frontmatter — grep `skills/*/SKILL.md` for `argument-hint` to see consistent format

### Tests
- N/A — documentation-only change; no behavioral logic modified

### Documentation
- `CLAUDE.md` — already lists `product-analyzer` as user-invocable; no change needed

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
- `/ll:format-issue` - 2026-05-09T21:13:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9656e0a3-1e1c-475f-af39-bb776aea9268.jsonl`
