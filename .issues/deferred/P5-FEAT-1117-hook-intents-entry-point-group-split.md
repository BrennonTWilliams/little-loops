---
id: FEAT-1117
type: FEAT
priority: P5
status: deferred
discovered_date: 2026-04-15
discovered_by: confidence-check
related: [FEAT-1116, FEAT-917]
---

# FEAT-1117: Evaluate splitting `little_loops.hook_intents` into its own entry-point group

## Summary

Revisit whether hook intent handlers should be discovered through a dedicated `little_loops.hook_intents` entry-point group instead of sharing `little_loops.extensions` with FSM/pub-sub extensions. Deferred from FEAT-1116 Decision 2 — reopen only when a concrete need emerges.

## Deferred Rationale

FEAT-1116 Decision 2 locked in reuse of the `little_loops.extensions` EP group with `LLHookIntentExtension` as a new optional `@runtime_checkable` Protocol detected via `hasattr()`. That choice was deliberately conservative:

- Matches the existing "one discovery path, multiple optional Protocols" pattern (`InterceptorExtension`, `ActionProviderExtension`)
- Avoids churn in `pyproject.toml.tmpl`, `create_extension.py`, `ExtensionLoader`, `config-schema.json`, and extension templates
- Keeps the MVP scoped

A second EP group is *speculatively* useful but has no concrete consumer yet. This issue exists so the question is not forgotten.

## Triggers for Reopening

Open a plan against this issue only when one or more of the following becomes true:

1. **Hook-only host**: A supported host agent can load hook intent handlers but has no path for regular extensions (e.g., a minimal runtime that only implements the hook protocol). Forcing it to enumerate the full `little_loops.extensions` group to filter for hook-capable classes is wasteful and error-prone.
2. **Registry surfacing**: FEAT-917's extension registry needs to list hook intent contributors as a distinct category (separate discovery, separate UI, separate compatibility metadata), and doing so via `hasattr()` filtering at registry-build time becomes awkward.
3. **Version skew**: Hook intent handlers need to evolve their Protocol contract independently of the base `LLExtension` surface (e.g., a major revision of `LLHookEvent` that the base extension API doesn't need to know about).
4. **Performance**: Extension loading at startup scans a large `little_loops.extensions` group and hook intent handlers need a faster discovery path for hot-path hook dispatch.

If none of these is true, leave this issue deferred.

## Scope (When Reopened)

- Add `[project.entry-points."little_loops.hook_intents"]` section to `scripts/pyproject.toml`
- Update `ExtensionLoader` (`scripts/little_loops/extension.py:123`) to load from both EP groups
- Update `wire_extensions()` to dispatch hook-intent extensions from the new group
- Add a `--type {extension,hook-intent}` flag to `ll-create-extension` (`scripts/little_loops/cli/create_extension.py`)
- Branch `templates/extension/pyproject.toml.tmpl` to register under the correct group based on the type flag
- Optionally branch `templates/extension/extension.py.tmpl` if the base class differs
- Update `docs/reference/CONFIGURATION.md` and `docs/reference/API.md` to document the second group

## Non-Goals

- Do not preemptively create the second group while the single-group approach is working
- Do not add discovery-time separation just to "clean up" the Protocol surface — the `hasattr()` detection pattern is idiomatic in this codebase
- Do not treat this as a blocker for FEAT-1116

## References

- FEAT-1116 Design Decision 2 — the current approach and its rationale
- `scripts/little_loops/extension.py:35-98` — current optional-Protocol pattern to replicate or replace
- `scripts/little_loops/extension.py:123` — `ExtensionLoader.from_config` discovery path
- FEAT-917 — extension registry, most likely trigger for reopening
