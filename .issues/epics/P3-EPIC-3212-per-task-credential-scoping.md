---
id: EPIC-3212
title: Per-Task Credential Scoping
type: EPIC
priority: P3
status: open
captured_at: "2026-08-16T16:53:55Z"
discovered_date: 2026-08-16
discovered_by: link-epics
relates_to: []
---

# EPIC-3212: Per-Task Credential Scoping

## Summary

Group of 3 related issues: Declare and enforce per-task credential scope via deny-by-default env projection, Record the credential scope a run was granted for after-the-fact audit, Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation.

## Goal

A task (loop-YAML state or `ActionSpec`) declares the credential scopes it needs; every env-borne credential it did not declare is absent from its child process; gh is genuinely isolated from the operator's keyring login; and what each dispatch was granted is recorded by name for after-the-fact audit. Undeclared tasks stay exactly as they are today.

## Scope

**In**: `project_child_env()` deny mode + scope registry (ENH-3233); loop-YAML `scopes:` (ENH-3235); `ActionSpec.scopes` (ENH-3234); gh `GH_TOKEN`/`GH_CONFIG_DIR` pairing on the FSM shell path (ENH-3205); `credential_scope_events` audit table (ENH-3204).

**Out** (per the children's Scope Boundaries): token minting / GitHub App tokens; Keychain-backed host-CLI OAuth; SSH-agent git; `HOME` redirection; `sync.py`; MCP server credentials; retrofitting declarations onto this repo's existing loops; CLI `--scope` flags; audit-record retention or query UI.

## Children

- **ENH-3203** — Declare and enforce per-task credential scope via deny-by-default env projection (done — decomposed into ENH-3233/3234/3235)
  - **ENH-3233** — Deny-by-default env projection core: chokepoint, credential-scope registry, and baseline (done 2026-09-07)
  - **ENH-3234** — ActionSpec credential scope declaration and runner_spec.py wiring (done 2026-09-07 — gh isolation + audit write missing, see BUG-3400)
  - **ENH-3235** — FSM StateConfig credential scope declaration and fsm/runners.py wiring (done 2026-09-07)
- **ENH-3204** — Record the credential scope a run was granted for after-the-fact audit (done 2026-09-07 — queue path not wired, see BUG-3400)
- **ENH-3205** — Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation (done 2026-09-07 — gh probe unguarded, see BUG-3400)
- **BUG-3400** — Credential scoping: unguarded gh probe, scopes [] bypasses validation, queue path not gh-isolated or audited (open, P1 — post-merge review 2026-09-07; last blocker to closing this epic)
- **BUG-3402** — gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain (open)
- **ENH-3403** — ActionSpec.scopes silently ignored by skill/prompt/mcp runners (open)



## Implementation Order

1. **ENH-3233** — chokepoint. Everything else consumes its `env_allow` kwarg and scope registry.
2. **ENH-3235** — loop-YAML `scopes:` surface. Primary consumer; unblocks the three below.
3. **ENH-3234**, **ENH-3205**, **ENH-3204** — independent of each other once 1–2 land; can run in parallel (e.g. one sprint, `max_workers: 2`).

## Acceptance (epic-level)

- A loop-YAML state can declare `scopes: [github]`; its `bash -c` child sees `GH_TOKEN` + a per-spawn `GH_CONFIG_DIR`, and no other registry credential; `gh auth status` inside it does not see the operator's keyring login.
- A state with no `scopes:` is byte-for-byte full-inherit (all existing `loops/*.yaml` unchanged and green).
- `ll-loop validate` rejects an unknown scope name before the loop starts.
- Every declaring dispatch leaves a `credential_scope_events` row (names only) keyed by `run_id`.
- Documented plainly: env projection scopes env-borne credentials only — Keychain-backed host-CLI OAuth and SSH-agent git are not constrained.

## Impact

- **Priority**: P3 — security hardening with no runtime behaviour change for undeclared tasks; value is bounded by projection-only (no narrowing of the operator's own token).
- **Effort**: Medium overall — ENH-3233 and ENH-3235 are Medium each; ENH-3234/3205/3204 are Small–Medium and parallelizable.
- **Risk**: Medium — concentrated in ENH-3233's baseline (a missing entry breaks declaring shell actions on unrelated-looking errors) and ENH-3205's fail-closed token path. Both have explicit mitigations in their issues.
- **Breaking Change**: No — every surface is opt-in per task.

## Status

**Open** | Created: 2026-08-16 | Priority: P3

2026-09-07: All five original children merged to `main` via the `epic/EPIC-3212` integration branch (57c0a3af1; `verify_before_merge: false`, so no automated gate ran). Post-merge `/code-review high` of the branch diff (db393717e..1927af68d) found three defects that break the epic-level acceptance criteria (`gh` isolation and the "every declaring dispatch leaves an audit row" guarantee are both missing on the `ActionSpec`/queue path). Filed as BUG-3400 and wired as a child; the epic stays open until it lands. An unrelated suite flake surfaced during verification (stale `.ll/events-*.sock` files) is tracked separately as BUG-3401.

## Review Notes (2026-09-04)

Pre-implementation review of all five open children applied: ENH-3233 gained caller-key pass-through, prefix baseline, enumerated registry, and Keychain caveat; ENH-3234 gained the `queue_store` round-trip gap and resolve-time decision; ENH-3235 pinned `scopes` and validate-time rejection; ENH-3204 resolved all three decisions (executor write site) and dropped ENH-3234 from `blocked_by`; ENH-3205 ran its gh learning test, fixed the token source, dropped `sync.py`, and resolved both decisions.