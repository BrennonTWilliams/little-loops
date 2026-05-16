---
discovered_date: 2026-02-10
discovered_by: manual_review
---

# BUG-312: Commands crash on null project commands (lint_cmd, type_cmd, format_cmd, test_cmd)

## Summary

`check_code` and `manage_issue` blindly interpolate nullable project commands (`lint_cmd`, `type_cmd`, `format_cmd`, `test_cmd`, `build_cmd`) without null guards. When any of these are `null` — which is the configured default for many project types — the commands attempt to execute invalid bash, causing failures.

## Context

The config schema defines `type_cmd`, `format_cmd`, and `build_cmd` as `["string", "null"]` (explicitly nullable). `lint_cmd` and `test_cmd` are typed as `"string"` in the schema, but templates still set them to `null`. Several project templates set these to `null`:

- **Java**: `type_cmd: null`, `format_cmd: null` (lint_cmd has values: `mvn checkstyle:check` / `./gradlew checkstyleMain`)
- **Go/Rust/Node.js/.NET**: `type_cmd: null`
- **General fallback**: `test_cmd: null`, `lint_cmd: null`, `type_cmd: null`, `format_cmd: null`

ENH-310 added a null guard for `build_cmd` in `check_code` ("Run build verification if `build_cmd` is configured (non-null). Skip silently if not configured.") but no other command block received the same treatment.

## Steps to Reproduce

1. Configure a project using a template with null commands (e.g., `generic.json` sets `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd` all to `null`)
2. Run `/ll:check-code` (or `/ll:manage-issue bug fix` which hits Phase 4 verification)
3. Observe that the null command is interpolated into bash, producing an invalid command execution

## Actual Behavior

When a nullable command (e.g., `type_cmd: null`) is interpolated into a bash block like `{{config.project.type_cmd}} {{config.project.src_dir}}`, the resulting command is invalid and causes the check to fail rather than being skipped gracefully.

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

A Go project running `/ll:check-code` will fail on the types block. A Java project will fail on lint, format, and types. A general-fallback project will fail on nearly everything.

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

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `commands/check_code.md`: Added null-guard instructions to lint, format, and types blocks matching existing build_cmd pattern. Added guards to fix mode for lint_cmd and format_cmd. Updated summary report to show SKIP status for all checks.
- `commands/manage_issue.md`: Added null-guard instructions to Phase 4 for test_cmd, lint_cmd, type_cmd. Added build_cmd verification step (previously missing). Updated instruction text to clarify skip behavior.

### Verification Results
- Tests: PASS (2660 passed)
- Lint: PASS (no new issues)
- Types: PASS
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P2

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID (after update)
- Fixed Java template claim: Java has `lint_cmd` values (`mvn checkstyle:check` / `./gradlew checkstyleMain`), not null. Only the generic template has `lint_cmd: null`.
- Confirmed: check_code lint/format/types blocks have no null guards. build_cmd has documented guard (ENH-310).
- Confirmed: manage_issue Phase 4 lacks null guards for test_cmd, lint_cmd; type_cmd has comment only. build_cmd missing entirely.

### Ready Issue Validation (2026-02-10)

- Corrected Context section: `lint_cmd` and `test_cmd` are `"string"` in schema (not nullable), though templates still set null values
- Added missing BUG-required sections: Steps to Reproduce, Actual Behavior
- All file references verified: `commands/check_code.md`, `commands/manage_issue.md` exist and confirm claims
- ENH-310 completed issue confirms build_cmd guard was intentionally scoped to check_code only
