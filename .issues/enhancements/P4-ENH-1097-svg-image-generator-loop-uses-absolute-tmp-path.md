---
discovered_date: 2026-04-13
discovered_by: capture-issue
---

# ENH-1097: svg-image-generator loop uses absolute /tmp/ path instead of .loops/tmp/

## Summary

The `svg-image-generator` loop hardcodes `output_dir: "/tmp/ll-svg-generator"` as an absolute
system path. All other built-in FSM loops write temporary files to `.loops/tmp/` (relative to the
project root), keeping loop artefacts scoped to the project. `svg-image-generator` should follow
the same convention.

## Current Behavior

`scripts/little_loops/loops/svg-image-generator.yaml` defaults `output_dir` to
`"/tmp/ll-svg-generator"` — an absolute path that writes outside the project tree and ignores
`.gitignore` coverage for loop artefacts.

## Expected Behavior

`output_dir` defaults to `".loops/tmp/ll-svg-generator"`, consistent with every other built-in
loop that uses temporary files (e.g. `harness-multi-item`, `sprint-refine-and-implement`,
`test-coverage-improvement`).

## Motivation

Consistency: all other loops already use `.loops/tmp/` so artefacts stay within the project
directory, are covered by `.gitignore`, and are visible alongside the loop that created them.
Using `/tmp/` is a one-off divergence with no benefit — it pollutes the system temp directory and
makes it harder to inspect or clean up generated SVG artefacts alongside the loop run.

## Proposed Solution

Change the `output_dir` default in `svg-image-generator.yaml`:

```yaml
# Before
context:
  output_dir: "/tmp/ll-svg-generator"

# After
context:
  output_dir: ".loops/tmp/ll-svg-generator"
```

No other logic needs to change — the prompt states already contain `mkdir -p` semantics via the
plan state's "Create directory … if it does not already exist" instruction.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-image-generator.yaml` — change `output_dir` default value

### Dependent Files (Callers/Importers)
- N/A — `output_dir` is a user-overridable context variable; callers that already pass a custom
  `output_dir` are unaffected

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — uses `.loops/tmp/`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — uses `.loops/tmp/`
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — uses `.loops/tmp/`

### Tests
- N/A — no tests exercise the default `output_dir` value directly

### Documentation
- `docs/` loop guides that reference the svg-image-generator example path (if any)

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/svg-image-generator.yaml`
2. Change `output_dir: "/tmp/ll-svg-generator"` → `output_dir: ".loops/tmp/ll-svg-generator"`
3. Verify no docs hardcode the old absolute path; update if found
4. Run a quick smoke test (or note untestable inline) and commit

## Impact

- **Priority**: P4 — Justification: cosmetic consistency fix; no functional breakage
- **Effort**: Small — single-line change
- **Risk**: Low — `output_dir` is user-overridable; default only affects fresh runs with no
  override
- **Breaking Change**: No — users who relied on `/tmp/ll-svg-generator` will get output in
  `.loops/tmp/ll-svg-generator` instead, but that is a better default

## Scope Boundaries

- Only the default `output_dir` value changes; the context variable itself and all prompt
  references remain intact
- Does not enforce `.loops/tmp/` for user-supplied overrides (users may still pass any path)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `consistency`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-13T10:52:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ecde5189-5435-44c0-b1ce-c8b3a48ba967.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P4
