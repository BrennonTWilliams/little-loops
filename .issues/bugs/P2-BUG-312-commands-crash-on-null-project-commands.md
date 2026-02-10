---
discovered_date: 2026-02-10
discovered_by: manual_review
---

# BUG-312: Commands crash on null project commands (lint_cmd, type_cmd, format_cmd, test_cmd)

## Summary

`check_code` and `manage_issue` blindly interpolate nullable project commands (`lint_cmd`, `type_cmd`, `format_cmd`, `test_cmd`, `build_cmd`) without null guards. When any of these are `null` — which is the configured default for many project types — the commands attempt to execute invalid bash, causing failures.

## Context

The config schema defines `lint_cmd`, `type_cmd`, `format_cmd`, and `build_cmd` as `["string", "null"]`. Several project templates set these to `null`:

- **Java**: `type_cmd: null`, `format_cmd: null` (lint_cmd has values: `mvn checkstyle:check` / `./gradlew checkstyleMain`)
- **Go/Rust/Node.js/.NET**: `type_cmd: null`
- **General fallback**: `test_cmd: null`, `lint_cmd: null`, `type_cmd: null`, `format_cmd: null`

ENH-310 added a null guard for `build_cmd` in `check_code` ("Run build verification if `build_cmd` is configured (non-null). Skip silently if not configured.") but no other command block received the same treatment.

## Current Behavior

`check_code` lint/format/types blocks and `manage_issue` Phase 4 blindly interpolate commands:

```bash
# check_code - no null guards
{{config.project.lint_cmd}} {{config.project.src_dir}}
{{config.project.format_cmd}} --check {{config.project.src_dir}}
{{config.project.type_cmd}} {{config.project.src_dir}} --ignore-missing-imports

# manage_issue Phase 4 - no null guards
{{config.project.test_cmd}} tests/ -v
{{config.project.lint_cmd}} {{config.project.src_dir}}
{{config.project.type_cmd}} {{config.project.src_dir}}
```

A Go project running `/ll:check_code` will fail on the types block. A Java project will fail on lint, format, and types. A general-fallback project will fail on nearly everything.

## Expected Behavior

Each command block should check whether the command is configured (non-null) before executing. If null, skip silently and report `SKIP` status in the summary. This matches the pattern already established for `build_cmd` in `check_code`.

## Proposed Solution

### `commands/check_code.md`

Add null-guard instructions to the lint, format, and types blocks, matching the build block pattern:

- **Lint block**: "Run linting if `lint_cmd` is configured (non-null). Skip silently if not configured."
- **Format block**: "Run format check if `format_cmd` is configured (non-null). Skip silently if not configured."
- **Types block**: "Run type checking if `type_cmd` is configured (non-null). Skip silently if not configured."

Update the summary report to show `SKIP` for any unconfigured commands (currently only build has SKIP status).

### `commands/manage_issue.md` — Phase 4

Add null-guard instructions to each verification step:

- Skip `test_cmd` if null
- Skip `lint_cmd` if null
- Skip `type_cmd` if null
- Add `build_cmd` step (missing entirely — ENH-310 only wired it into `check_code`)

Report skipped checks in the verification output rather than failing silently.

## Affected Commands

| Command | `lint_cmd=null` | `type_cmd=null` | `format_cmd=null` | `test_cmd=null` | `build_cmd` |
|---------|----------------|-----------------|-------------------|-----------------|-------------|
| `check_code` | **No guard** | **No guard** | **No guard** | N/A | Guarded (ENH-310) |
| `manage_issue` | **No guard** | Comment only | N/A | **No guard** | **Not wired in** |

## Impact

- **Priority**: P2 — affects any non-Python project type out of the box
- **Effort**: Small — add consistent null-guard instructions to two command files
- **Risk**: Low — additive change, Python projects (where all commands have defaults) see no behavior change

## Labels

`bug`, `captured`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID (after update)
- Fixed Java template claim: Java has `lint_cmd` values (`mvn checkstyle:check` / `./gradlew checkstyleMain`), not null. Only the generic template has `lint_cmd: null`.
- Confirmed: check_code lint/format/types blocks have no null guards. build_cmd has documented guard (ENH-310).
- Confirmed: manage_issue Phase 4 lacks null guards for test_cmd, lint_cmd; type_cmd has comment only. build_cmd missing entirely.
