---
id: ENH-1639
type: ENH
priority: P4
status: open
captured_at: 2026-05-23T12:00:00Z
discovered_date: 2026-05-23
discovered_by: capture-issue
testable: false
---

# ENH-1639: Document timeout-budget guidance for `prompt` actions doing many MCP tool calls

## Summary

The `harness-exploratory-user-eval`-style template (which imports `lib/common.yaml` from little-loops) ships with `timeout: 720` for prompt actions. When the prompt does ~10 MCP tool calls + synthesis (vision agents, playwright orchestration), 720s is too tight and the action is regularly killed mid-synthesis. Users should budget ≥1500s and consider a streaming agent.

## Current Behavior

- `loops/lib/common.yaml` ships `timeout: 720` as the default for `action_type: prompt` entries that get reused via YAML anchors.
- The `/ll:create-loop` skill's prompt-action template does not call out a higher budget when the suggested prompt includes MCP tool calls.
- `docs/reference/SCHEMA.md` (or the equivalent timeout reference) does not document that prompt + MCP synthesis can run several minutes.
- Result: users authoring loops that perform many MCP tool calls (e.g. semantic-vision checks with ~10 playwright calls + synthesis) hit the 720s timeout mid-synthesis and the action is killed without producing a verdict.

## Expected Behavior

- `loops/lib/common.yaml` includes an inline comment (or accompanying README note) explaining when 720s is too tight and recommending ≥1500s for prompt actions doing multiple MCP tool calls.
- `/ll:create-loop` defaults `timeout: 1500` (with rationale comment) whenever it scaffolds a prompt action expected to perform MCP tool calls.
- `docs/reference/SCHEMA.md` documents the budgeting guidance alongside the `timeout` field so authors discover it before hitting the timeout in practice.

## Motivation

- Repeatedly observed in `harness-exploratory-user-eval` runs: the semantic-vision check timed out at 12m every pass.
- Low-friction fix: a clear note in the README/SKILL for `lib/common.yaml` and the loop wizard's prompt-action template.

## Proposed Solution

Add a short guidance block to:

1. The `lib/common.yaml` doc/comment block (or its accompanying README) explaining the timeout budget for prompt actions.
2. The `/ll:create-loop` skill prompt template — when a `prompt` action is suggested with MCP tool calls, default to `timeout: 1500` and add a comment with the rationale.
3. `docs/reference/SCHEMA.md` (or wherever timeouts are documented) — note that prompt + MCP synthesis can run several minutes and `timeout:` should reflect that.

Suggested text:

> When `action_type: prompt` performs multiple MCP tool calls followed by synthesis (e.g. a vision agent with ~10 tool calls), allow ≥1500s; the default 720s is too tight and will cause timeouts mid-synthesis. Consider a streaming agent if you need progress visibility within the budget.

## Integration Map

### Files to Modify
- `loops/lib/common.yaml` (and any accompanying README at `loops/lib/`)
- `skills/create-loop/SKILL.md`
- `docs/reference/SCHEMA.md` (or equivalent timeout reference)

### Dependent Files (Callers/Importers)
- TBD — grep for loops that import the prompt-action anchor from `lib/common.yaml`: `grep -rE "<<:\s*\*prompt" loops/`

### Similar Patterns
- TBD — search for other timeout defaults in shared loop fragments: `grep -rn "timeout:" loops/lib/`

### Tests
- N/A — documentation-only change; no test coverage required.

### Documentation
- `docs/reference/SCHEMA.md`
- `loops/lib/` README (if present, else add inline YAML comment)

### Configuration
- N/A

## Implementation Steps

1. Add inline guidance comment to `loops/lib/common.yaml` near the prompt-action `timeout:` default.
2. Update `skills/create-loop/SKILL.md` to emit `timeout: 1500` with rationale comment when scaffolding MCP-heavy prompt actions.
3. Add timeout-budget note to `docs/reference/SCHEMA.md` (or equivalent) next to the `timeout` field documentation.
4. Verification: re-read the three touchpoints to confirm guidance is consistent and discoverable.

## Scope Boundaries

- **In scope**: Documentation/comment additions in the three locations above; default-value bump in the create-loop scaffolding template.
- **Out of scope**: Changing the runtime default of 720s in already-published loops; introducing a new streaming-agent action type; adding timeout-budget linting to `ll-loop validate`.

## Impact

- **Priority**: P4 — quality-of-life documentation fix; users can already work around by setting `timeout:` explicitly.
- **Effort**: Small — three doc/comment touchpoints, no code logic.
- **Risk**: Low — documentation-only and a default-value change in a scaffolding template (does not modify existing loops).
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 5). Documentation-only — no code change required.

## Labels

`enhancement`, `documentation`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T19:21:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e2957f37-1ad6-4175-b382-d8060a7c090f.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---
**Status**: Open | Created: 2026-05-23 | Priority: P4
