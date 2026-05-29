---
id: ENH-1804
type: ENH
priority: P3
status: open
captured_at: "2026-05-29T21:57:08Z"
discovered_date: 2026-05-29
discovered_by: capture-issue
---

# ENH-1804: Extract hitl-md 16KB generate prompt to shared file fragment

## Summary

The `generate` state action in `loops/hitl-md.yaml` is 16,272 characters — by far the largest action in any built-in loop. Extract the design specification portion (HTML/CSS/JS requirements for the interactive review page) to a shared prompt file under `prompts/` or a loop fragment. This reduces FSM definition size, makes the prompt independently iterable, and aligns with the fragment-extraction direction in ENH-1775.

## Current Behavior

The `generate` state inlines the entire design specification (document rendering rules, inline segment markers, saliency highlighting, popover affordances, all 6 ENH-1770 sensemaking features, cross-feature requirements) as a single 16KB YAML string. This makes the loop YAML unreadable and increases the probability of template interpolation errors or token-limit failures.

## Expected Behavior

The generate state references a shared prompt file:

```yaml
generate:
  action: |
    Read ${captured.run_dir.output}/segments.json for the ordered segment list.
    If ${captured.run_dir.output}/critique.md exists, read it and address all issues.
    ${context.design_tokens_context}
    Read prompts/hitl-md-generate.md for the full design specification.
    Write a single self-contained HTML file to ${captured.run_dir.output}/index.html
    following every requirement in the design specification.
  action_type: prompt
  next: evaluate
  on_error: failed
```

The design spec lives in `prompts/hitl-md-generate.md` and can be iterated independently.

## Motivation

The 16KB action size likely contributed to the `2026-05-29T213409` run failure (terminated with error at generate state entry). Extracting the prompt reduces FSM definition bloat, improves debuggability, and creates a reusable fragment that other HITL loops (hitl-compare, html-anything) could reference. This also enables independent prompt iteration without touching the loop YAML.

## Proposed Solution

1. Move the design specification portion of the generate action to `prompts/hitl-md-generate.md`
2. Replace the inlined spec in the generate action with a reference to read the file
3. The loop YAML keeps only the file-path references and context wiring

## Integration Map

### Files to Modify
- `loops/hitl-md.yaml` — replace inlined 16KB action with file reference
- `prompts/hitl-md-generate.md` (new) — extracted design specification

### Dependent Files (Callers/Importers)
- `loops/hitl-compare.yaml` — may benefit from shared fragment
- `loops/html-anything.yaml` — may benefit from shared fragment

### Similar Patterns
- ENH-1775 (Wave 2) — extracting generator-evaluator sub-loop and `parse_tagged_json` fragment
- ENH-1774 (Wave 1) — adding `ll-commit` and Playwright screenshot as shared fragments

### Tests
- Re-run `ll-loop run hitl-md --input "PRD-Hermes-Integration-v3.md"` to verify no regression
- Verify the generate prompt reads the external file correctly via template resolution

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Create `prompts/hitl-md-generate.md` with the extracted design specification
2. Update `loops/hitl-md.yaml` generate state to reference the file
3. Add `on_error: failed` to generate state (see BUG-1803)
4. Validate: `ll-loop validate hitl-md`
5. Re-run the failing invocation to confirm fix

## Impact

- **Priority**: P3 — Reduces fragility and improves maintainability; not blocking
- **Effort**: Medium — Requires careful extraction to preserve all design spec details
- **Risk**: Low — The generate action is self-contained; extraction doesn't change behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loop-fragment`, `captured`

## Session Log

- `/ll:capture-issue` — 2026-05-29T21:57:08Z — `64ba091c-1c65-464a-81b6-237b5a702007.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
