---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# ENH-310: Wire build_cmd into check_code verification

## Summary

`build_cmd` is defined in the config schema and populated by project templates, but no skill or command actually consumes it. Wire it into `/ll:check-code` as an optional build verification step so projects with a build command get build-time error checking alongside lint/format/type checks.

## Context

Identified from conversation analyzing `config-schema.json` and grepping for `build_cmd` usage. The field exists in the schema (line 50), the `ProjectConfig` dataclass (config.py:75), and all project templates (typescript, go, rust, java, etc.) but is never referenced in any skill or command prompt.

## Current Behavior

`/ll:check-code` runs lint, format, and type checking commands. `build_cmd` sits in config unused — it's dead config that was set up during init/configure but never consumed.

## Expected Behavior

`/ll:check-code` should run `build_cmd` (if configured and non-null) as a final verification step after lint/format/type checks, reporting build success or failure alongside the other checks.

## Proposed Solution

Edit `commands/check_code.md` (or the corresponding skill) to:
1. Read `config.project.build_cmd`
2. If non-null, run it as a build verification step
3. Report results in the same format as the other checks

## Current Pain Point

Projects with build steps (TypeScript, Go, Java, Rust) configure `build_cmd` during init but get no value from it. Users expect that configuring a build command means it gets used somewhere in the workflow.

## Scope Boundaries

- Only wire into `check_code` — do not change manage_issue verification (that's ENH-311)
- Do not change the config schema or templates
- Do not add build_cmd to any other workflow

## Impact

- **Priority**: P3
- **Effort**: Small — single file edit to check_code command
- **Risk**: Low — additive change, null build_cmd means no behavior change

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `commands/check_code.md`: Added `build` mode with build_cmd support, updated frontmatter (description, allowed-tools, mode argument), added build_cmd to config section, added build check block after types, updated summary report with Build line and SKIP status, updated arguments and examples sections

### Verification Results
- Tests: N/A (markdown-only change)
- Lint: PASS (pre-existing issues unrelated)
- Types: PASS
- Integration: PASS
