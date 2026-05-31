---
id: FEAT-917
title: Extension Registry with Discovery and Compatibility Checking
type: FEAT
priority: P5
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# FEAT-917: Extension Registry with Discovery and Compatibility Checking

## Summary

Implement extension discovery beyond `importlib.metadata.entry_points`: a naming convention for PyPI packages (`little-loops-ext-*`), extension manifests declaring capabilities and version compatibility, and `ll extensions` CLI commands for searching, inspecting, and validating installed extensions.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." FEAT-911 uses `entry_points` for extension loading, but there's no way to discover available extensions, check compatibility, or understand what an extension does before installing it.

## Current Behavior

No extension system exists yet (FEAT-911 pending). Once shipped, extensions are loaded via `entry_points` but there's no discovery, inspection, or compatibility mechanism.

## Expected Behavior

- PyPI naming convention: `little-loops-ext-*` packages are auto-discoverable
- Extension manifest (in `pyproject.toml` metadata or dedicated file) declares:
  - Events consumed
  - Hooks intercepted (if using FEAT-915 bidirectional hooks)
  - Actions/evaluators contributed
  - Compatible ll version range
- CLI commands:
  - `ll extensions list` — show installed extensions and their status
  - `ll extensions info <name>` — show manifest details
  - `ll extensions check` — validate all installed extensions against current ll version
  - `ll extensions search <query>` — search PyPI for `little-loops-ext-*` packages

## Motivation

Extension ecosystems need discoverability. Without a registry or manifest system, users can't find extensions, and version mismatches cause silent failures. This is the infrastructure that makes "protocol, not product" viable at scale.

## Proposed Solution

1. Define extension manifest schema (embedded in `pyproject.toml` under `[tool.little-loops.extension]` or as `ll-extension.json`)
2. Add `ll extensions` CLI command group with `list`, `info`, `check`, and `search` subcommands
3. `search` queries PyPI API for packages matching `little-loops-ext-*` pattern
4. `check` loads all installed extensions and validates version ranges against current ll version
5. Optionally maintain a curated `awesome-ll-extensions` list or index file

## API/Interface

```toml
# In extension's pyproject.toml
[tool.little-loops.extension]
name = "grafana-dashboard"
description = "Real-time loop monitoring in Grafana"
events = ["loop_start", "loop_complete", "route", "evaluate"]
ll_version = ">=1.60,<2.0"
```

```bash
$ ll extensions list
NAME                STATUS    VERSION  COMPAT
grafana-dashboard   loaded    0.3.1    ✓
slack-notify        loaded    1.0.0    ✓
old-extension       error     0.1.0    ✗ (requires ll<1.50)

$ ll extensions check
2 extensions OK, 1 incompatible
```

## Use Case

A team evaluating ll wants to see what extensions are available. They run `ll extensions search dashboard`, find `little-loops-ext-grafana`, install it, run `ll extensions check` to confirm compatibility, and see it appear in `ll extensions list`.

## Acceptance Criteria

- [ ] Extension manifest schema defined and documented
- [ ] Manifest schema includes a `transports` capability key alongside `events`, `hooks`, and `actions/evaluators` so transports introduced by FEAT-918 are first-class in `ll extensions list`/`info`
- [ ] `ll extensions list` shows installed extensions with status and compatibility
- [ ] `ll extensions check` validates version compatibility for all installed extensions
- [ ] `ll extensions info <name>` displays manifest details
- [ ] Naming convention `little-loops-ext-*` documented for PyPI discoverability

## Impact

- **Priority**: P5 - Ecosystem infrastructure; premature until multiple extensions exist
- **Effort**: Medium - CLI commands are straightforward; manifest schema needs design iteration
- **Risk**: Low - Additive tooling with no core execution path impact
- **Breaking Change**: No
- **Depends On**: FEAT-911, optionally FEAT-915

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Extension Protocol and entry point configuration |
| guidelines | CONTRIBUTING.md | CLI command patterns to follow |

## Labels

`feat`, `extension-api`, `ecosystem`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- FEAT-911 is COMPLETED — entry point group `little_loops.extensions` confirmed in `extension.py:25` ✓
- No `ll extensions` CLI command group (list/info/check/search) exists ✓
- No extension manifest schema defined in `pyproject.toml` or dedicated file ✓
- `ExtensionLoader.from_config()` loads by dotted path; no PyPI discovery mechanism ✓

---

## Status

**Open** | Created: 2026-04-02 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:40:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): This issue covers **Extensions only** — third-party PyPI packages following the `little-loops-ext-*` naming convention that declare `[tool.little-loops.extension]` manifests and are discoverable via `ll extensions search/list/check`. Host-integration adapters (Codex CLI via FEAT-957, Pi Coding Agent via FEAT-992) are **NOT extensions** in this sense: they have no PyPI presence, no extension manifest, and are NOT included in the `ll extensions` registry or discovery commands. Do not design the manifest schema or CLI commands to accommodate host adapters. These are orthogonal systems — use "Extensions" (PyPI ecosystem) vs "Host Adapters" or "Host Plugins" as the canonical naming split.
