---
discovered_commit: 90b70c6
discovered_branch: main
discovered_date: 2026-02-15T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-437: README understates template coverage

## Summary

The README "What's Included" section (line 88) lists templates for "Python, Node.js, Go, Rust, Java, and .NET" but the actual `templates/` directory contains 9 templates including separate TypeScript and generic entries.

## Current Behavior

README says:
> Configuration system with project-type templates for Python, Node.js, Go, Rust, Java, and .NET

## Expected Behavior

Should accurately reflect all available templates: Python, JavaScript, TypeScript, Go, Rust, Java (Maven & Gradle), .NET, and a generic fallback.

## Files Involved

- `README.md:88` — "What's Included" bullet
- `templates/` — 9 template files: `python-generic.json`, `javascript.json`, `typescript.json`, `go.json`, `rust.json`, `java-maven.json`, `java-gradle.json`, `dotnet.json`, `generic.json`

## Proposed Solution

Update the wording to mention TypeScript separately and note the generic fallback, e.g.:
> Configuration system with project-type templates for Python, JavaScript, TypeScript, Go, Rust, Java (Maven/Gradle), .NET, and a generic fallback

## Scope Boundaries

- Only update the "What's Included" bullet on line 88 of README.md
- Do not restructure or reorganize the templates directory
- Do not modify template file contents

## Impact

- **Priority**: P4 - Documentation accuracy, cosmetic only
- **Effort**: Small - Single line change in README
- **Risk**: Low - No code changes, documentation only
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `good-first-issue`

## Resolution

**Fixed** on 2026-02-15. Updated README.md line 88 to accurately list all 9 project-type templates: Python, JavaScript, TypeScript, Go, Rust, Java (Maven/Gradle), .NET, and generic fallback.

### Changes Made
- `README.md:88` — Updated "What's Included" template list

## Status

**Completed** | Created: 2026-02-15 | Resolved: 2026-02-15 | Priority: P4
