---
id: BUG-3402
type: BUG
title: gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T00:36:57Z'
parent: EPIC-3212
---

# BUG-3402: gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain

## Summary

On keychain-backed macOS `gh`, `gh auth token` still succeeds and prints the operator's token (exit 0) even when `GH_CONFIG_DIR` is redirected to a freshly-created empty directory and `GH_TOKEN`/`GITHUB_TOKEN` are unset. `gh` stores the OAuth token in the login Keychain under a fixed service name (`gh:github.com`), keyed by hostname only — not gated by `GH_CONFIG_DIR`/`hosts.yml` the way `gh auth status`/`gh api` are.

## Current Behavior

The `GH_CONFIG_DIR`-redirect-based non-escalation guarantee that ENH-3205's Decision Rules promise ("an inner github state spawned under an outer non-github declaring state... `gh auth token` fails against the inherited empty config dir") does NOT hold on keychain-backed macOS `gh`. A nested or sibling github-scoped spawn can still mint a valid token via `gh auth token` regardless of an inherited/redirected empty `GH_CONFIG_DIR`, because the probe reads Keychain directly rather than the config dir.

This is already recorded as a failing assertion in the learning-test registry: `ll-learning-tests check gh` reports 1 failing claim dated 2026-09-07, tagged "ENH-3205 gap", stored in `.ll/learning-tests/gh.md` / `.ll/learning-tests/raw/gh.txt` (overall status=proven, but this specific assertion result=fail).

Surfaced during `/ll:wire-issue BUG-3400 --auto` (2026-09-08): BUG-3400 fixes the CMD/queue runner path to call `gh_scope_extra()` (mirroring the FSM path's existing `GH_CONFIG_DIR`-redirect approach), but BUG-3400's acceptance criteria only assert `gh auth status` inside the scoped child does not see the operator login — they do not test `gh auth token`. So BUG-3400's fix will satisfy its own acceptance criteria while this deeper isolation gap remains live on macOS: `gh_scope_extra()`'s own probe (and any child's own `gh auth token` call) can still mint the operator's real token via Keychain regardless of the `GH_CONFIG_DIR` redirect.

## Expected Behavior

Either:
(a) find/add a Keychain-defeating mechanism — e.g. force `GH_TOKEN` to an explicit empty/invalid sentinel value in the scoped child's env when `github` is not declared, since env `GH_TOKEN`/`GITHUB_TOKEN` do take precedence over Keychain per the registry's own passing assertions; or
(b) explicitly document this as an accepted platform limitation of the credential-scoping feature on macOS and narrow the isolation claim in ENH-3205/`docs/ARCHITECTURE.md`/`docs/guides/LOOPS_GUIDE.md` accordingly.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2 — a security-isolation gap in a feature already merged to `main` (EPIC-3212), silent (no error, just a token that shouldn't be mintable), and platform-specific (macOS Keychain) so may not reproduce in CI.
- **Breaking Change**: No

## Relates To

- ENH-3205 (gh isolation design — this is a gap in that design's own guarantee)
- BUG-3400 (the fix being wired assumes `GH_CONFIG_DIR` redirection is sufficient isolation for both `gh auth status` and `gh auth token`; it is not, for `gh auth token` on keychain-backed macOS `gh`)
- Found via `/ll:wire-issue BUG-3400 --auto` on 2026-09-08, cross-checking the `gh` learning-test registry.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-08T00:37:04 - `818ac84c-8dd8-46bc-9d1e-d582e9b2e72e.jsonl`
