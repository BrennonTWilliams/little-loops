---
id: BUG-3490
parent: EPIC-3493
epic: EPIC-3493
type: BUG
title: Policy builder skill catalog is empty in consumer projects (single-root plugin
  discovery)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:14:21Z'
labels:
- policy-builder
relates_to:
- BUG-3486
- BUG-3489
- FEAT-3474
---

# BUG-3490: Policy builder skill catalog is empty in consumer projects (single-root plugin discovery)

## Summary

The policy builder scans the consuming project's root-level `skills/` and `commands/`, instead of the installed little-loops content. A normal consumer therefore gets an empty menu. The related `_find_plugin_root()` fallback assumes a source checkout and cannot locate the skills already shipped inside the Python wheel; commands are not packaged yet.

Fix this with a filesystem-only, read-only resolver that selects one authoritative plugin content root, package commands alongside skills, and explicitly migrate catalog and skill-resolution consumers. Do not change the legacy root lookup used by mutation commands or merge multiple installations.

Split from BUG-3486 (whole-builder review, defect h). The design below incorporates the pre-implementation reasoning review and replaces the earlier multi-root/project-shadowing and persisted marketplace-path proposal.

## Current Behavior and Root Cause

- `cli/artifact/policy_builder.py::_load_skill_catalog(project_root)` directly scans `project_root/skills` and `project_root/commands`. It does not resolve installed content.
- `skill_expander.py::_find_plugin_root()` returns `CLAUDE_PLUGIN_ROOT` when set, otherwise three parents above its own file. The latter is the repository root in an editable checkout but is not a plugin content root in a wheel installation.
- `hatch_build.py::SkillsForceIncludeHook` ships `skills/` into `little_loops/skills`, but does not ship `commands/`.
- `mcp_server/server.py::_resolve_skills_root()` already has a packaged-content fallback and a dedicated `LL_MCP_SKILLS_ROOT` override. This is a useful read-only precedent, not evidence that all root consumers can safely change together.
- `_find_plugin_root()` is also used by commands that write skill files or generate adapters. Redirecting that API to site-packages would silently change their editing target.
- The builder template constructs `/ll:<name>` for menu values and its known-skill validation set. Project-local skills cannot be added correctly merely by adding their basenames to the current `{name, description}` catalog.

## Expected Behavior

The builder, `ll-help`, and `ll-action list` can discover installed little-loops skills and commands in supported editable and wheel layouts without consumer root-level catalog directories. An explicit valid plugin environment root takes precedence. Selection and skill content lookup agree on the same installation, and no lower-precedence installation contributes additional names.

Project-local skills remain outside this catalog. Existing mutation commands keep their current root-selection behavior. Discovery does not run a host CLI, consult `install_source`, or persist machine-specific installation paths.

## Proposed Solution

### Select one read-only content root

Add `resolve_plugin_content_root() -> Path | None` in `skill_expander.py`, separate from the existing `_find_plugin_root()` API. Check candidates in this order:

1. `CLAUDE_PLUGIN_ROOT`, when set and containing a `skills/` or `commands/` directory.
2. The source checkout root derived from this module, when it contains either directory.
3. The installed package directory obtained through `importlib.resources.files("little_loops")`, when it contains either directory.

Return the first valid root, or `None` when none exists. Invalid or unavailable candidates contribute nothing. Note that `mcp_server/server.py::_resolve_skills_root` orders packaged before checkout; the two orders are equivalent in practice because, under one interpreter, only one of those candidates ever has a `skills/` directory (editable: the package dir has none; wheel: the derived checkout root is a site-packages parent). Document that equivalence next to the resolver so the codebase does not carry two apparent contracts.

Expose the candidate walk as a module-level `_content_root_candidates() -> list[Path]` (env, checkout, packaged, in that order, unvalidated) that tests monkeypatch. This is the isolation seam Implementation Step 1 relies on: packaged-layout fixtures replace the list rather than relying on path tricks to hide the real checkout. A commands-only root is valid. Selection is by directory availability, not by whether a particular requested name exists: never fall through to another installation for a missing skill or command. An empty but valid selected catalog stays empty rather than borrowing another version's content.

Use filesystem paths for normal unpacked wheel/editable installations. Do not claim support for non-filesystem resource loaders through `Path(str(traversable))`; unsupported resource representations should be skipped without fabricating a path. Archive-backed resource support is outside this fix.

Do not cache this inexpensive lookup initially. This avoids stale environment/config state and cache invalidation requirements in long-lived processes and tests. No subprocess probing occurs, including when every candidate is missing. Marketplace-only discovery outside a host session is deferred; a marketplace installation exposed through a valid environment root is supported.

### Preserve editing targets and align read consumers

Keep `_find_plugin_root()` unchanged for mutation/development commands. Explicitly migrate the read paths required for catalog-to-execution consistency:

- policy-builder catalog generation;
- `cli/help.py::main_help` default lookup, preserving explicit `-C` behavior;
- `cli/action.py::_load_skills`;
- `skill_expander.py::expand_skill`;
- `cli/queue.py::_classify_action` skill lookup;
- `mcp_server/tools.py::_tool_skills_list`, preserving its agreement with queue classification;
- `cli/harness.py::_resolve_skill_target_path`, which hashes skill content for cell keys through `_find_plugin_root()` + `_resolve_content_path` and is read-only; on a wheel it currently resolves nothing and must agree with the root queue classification uses.

Missing content produces an empty catalog, `None` from expansion, or the existing queue classification fallback, as appropriate. Do not pass `None` into existing path-based collectors.

Keep `assemble_tool_catalog(root)` an explicit-root scanner; its callers do not inherit a resolver change automatically. This issue changes the MCP skills-list caller, not all tool catalogs or doctor behavior. The MCP prompt index's dedicated `LL_MCP_SKILLS_ROOT` override and existing lookup policy remain outside this change; do not silently remove that override.

### Reuse enumeration and define callable identity

Make the builder a projection over `collect_entries(selected_root)`, preserving its public `{name, description}` shape. Do not add `CatalogRoot`, `collect_entries_multi`, or project inclusion flags.

For the builder, deduplicate by callable identity, currently `/ll:<name>`, rather than `(kind, name)`. If a command and skill share a name, prefer the skill entry when both survive collection, matching `_resolve_content_path()`'s skill-first lookup. Preserve the collector's existing suppression of disabled model-invocation bridge stubs with a matching command; such stubs do not introduce an extra callable. Sort the final builder catalog deterministically by name.

Keep `collect_entries()` and the existing help/action output contracts unchanged. The deduplication is a builder projection rule, not a global redefinition of help entry identity. Test ordinary cross-kind collisions and bridge-stub pairs separately.

Project-local invocation namespaces require a separate design: explicit invocation identity, host-supported naming, selection/validation/emission changes, and runtime lookup parity. Same-basename project and plugin entries must not be assumed to shadow each other.

### Package commands

Extend the existing conditional build hook to include `commands/` as `little_loops/commands` for checkout wheel and sdist builds. Preserve the unpacked-sdist path, where content is already under `little_loops/` and is covered by `little_loops/**`. Do not add redundant package include entries solely because commands are a new directory; change `pyproject.toml` only if build validation demonstrates a need. Update the package-data comments to describe both content directories. `commands/` stays out of `PACKAGE_DATA_ASSETS`, for the same reason `skills/` is excluded (`package_data.py` BUG-3177 note): force-included content is proven by the wheel-smoke integration test, not the importlib manifest.

### Follow-up (out of scope)

Once the resolver exists, `mcp_server/server.py::_resolve_skills_root` duplicates its candidate walk (plus the `LL_MCP_SKILLS_ROOT` override and stderr warning). Fold it onto the shared resolver in a separate issue; this issue leaves it untouched.

## Implementation Steps

1. Add isolated resolver fixtures for environment, editable, packaged, commands-only, invalid, and absent roots. Monkeypatch `_content_root_candidates()` so packaged tests cannot pass accidentally against repository content.
2. Implement the read-only single-root resolver while retaining `_find_plugin_root()` behavior for editing/development consumers.
3. Migrate the listed read consumers together. Add parity tests for catalog entries, content expansion, MCP skills listing, and queue skill classification, including coexistence of different installation versions.
4. Replace the builder's direct project scan with the collector projection and explicit invocation deduplication. Verify the generated HTML catalog and `/ll:` selections.
5. Extend packaging for commands and validate both direct wheel and sdist-to-wheel artifacts.
6. Update relevant API/CLI and package-data documentation to distinguish installed content discovery from editing-root lookup. Run the full local test suite.

## Integration Map

### Files to Modify

- `scripts/little_loops/skill_expander.py`: new read-only resolver and expansion lookup; retain legacy `_find_plugin_root`.
- `scripts/little_loops/cli/artifact/policy_builder.py`: installed-content lookup and deterministic, deduplicated collector projection.
- `scripts/little_loops/cli/help.py`: default root selection only; preserve explicit root override and collector behavior.
- `scripts/little_loops/cli/action.py`: read-only root selection for skill listing.
- `scripts/little_loops/cli/queue.py`: matching read-only root selection for skill classification.
- `scripts/little_loops/mcp_server/tools.py`: skills-list root selection and explanatory parity documentation.
- `scripts/little_loops/cli/harness.py`: `_resolve_skill_target_path` switches to the read-only resolver (returns `None` when no root resolves).
- `scripts/hatch_build.py`, `scripts/little_loops/package_data.py`: command packaging and documentation.
- `docs/reference/API.md`, `docs/reference/CLI.md`: resolver contract, consumers, and supported discovery layouts.

### Boundaries to Preserve

- `cli/adapt.py`, `cli/generate_skill_descriptions.py`, `cli/adapt_agents_for_codex.py`, and `cli/adapt_skills_for_codex.py`: no implicit redirection to packaged content through the new resolver.
- `cli/verify_host_map.py` and `cli/verify_cli_allowlist.py`: source-repo verification CLIs that read checkout docs (`HOST_COMPATIBILITY.md`, `skills/configure/areas.md`) via `_find_plugin_root()`; keep the legacy root.
- `tool_catalog.py::assemble_tool_catalog`: explicit-root API stays intact; `cli/doctor.py` is not implicitly fixed by this work.
- `mcp_server/server.py::_resolve_skills_root`: preserve the existing dedicated MCP override and behavior.
- `init/install_check.py`, init configuration writers, and `config-schema.json`: no persisted `install_path` or install-source branching in this issue.

### Tests

- Resolver/expansion tests in `scripts/tests/test_skill_expander.py`.
- Existing help and action contracts in `scripts/tests/test_help.py` and `scripts/tests/test_action.py`.
- Builder generation coverage in `scripts/tests/test_policy_builder_emit.py` and `scripts/tests/test_enh3035_artifact_template_kit.py`.
- MCP and queue parity coverage, including `scripts/tests/test_enh_3444_mcp_skills_list.py` and the existing queue classification tests.
- Packaging: `scripts/tests/test_wheel_smoke.py::TestWheelSmoke::test_skills_force_include_accessible` (integration-marked, local-only) gains a commands twin, covering direct wheel and unpacked-sdist wheel contents.
- Harness: `_resolve_skill_target_path` resolves the same path as queue classification for a packaged-only root and returns `None` when no root resolves.
- Regression coverage proving editing commands still use the legacy root lookup.

## Acceptance Criteria

- [ ] A consumer without root `skills/` or `commands/` gets known lifecycle catalog entries from valid environment, editable, and packaged content roots.
- [ ] Environment > checkout > packaged precedence is deterministic. With different names/content in coexisting installations, only the selected root contributes entries; expansion does not fall through for a missing name.
- [ ] Commands-only roots work; invalid/missing candidates do not raise; an empty selected root does not cause version mixing.
- [ ] On a packaged layout, `ll-help` and `ll-action list` are non-empty, while explicit `ll-help -C` retains its existing semantics.
- [ ] Every advertised builder invocation resolves to content in the selected installation. Queue classification and MCP skills listing use the same root and preserve their existing parity contract.
- [ ] The generated builder catalog is deterministic and contains one entry per `/ll:<name>`, including cross-kind collisions and bridge-stub pairs. Project `.claude/skills` and `.claude/commands` are excluded.
- [ ] Existing source-checkout help/action output contracts remain unchanged. Mutation/development commands retain their legacy root-selection behavior rather than being redirected to site-packages.
- [ ] Resolver calls spawn no subprocess, even with no valid content roots, and require no new configuration fields or cache state.
- [ ] Built wheels contain both `little_loops/skills` and `little_loops/commands`, from both direct-checkout and unpacked-sdist builds; packaged catalog tests cannot accidentally resolve the real checkout.
- [ ] Documentation describes the supported layouts and deferred marketplace/project-skill cases; full local suite passes.

## Scope Boundaries

Includes installed little-loops content discovery for the listed read consumers, builder invocation deduplication, and command packaging. Excludes multi-installation merging, project-local skills, persisted marketplace discovery, archive-backed resource loaders, editing-target redesign, packaging agents, and general doctor/tool-catalog discovery changes. Browser/core defects remain in BUG-3486 and router runtime defects in BUG-3489.

Marketplace discovery was removed from this implementation because `detect_installation()` returns early for pip installs, no-project callers have no defined project config source, cached paths can become stale, and process-local memoization does not avoid a probe on each fresh CLI invocation. A future marketplace discovery feature needs explicit host support, context, stale-path handling, and invalidation semantics.

## Impact

- **Priority**: P2 — installed content is unavailable in the builder for normal consumer layouts.
- **Effort**: Medium — coordinated read-consumer migration and distribution validation.
- **Risk**: Medium — mitigate catalog/execution divergence with parity tests and preserve mutation-root semantics.
- **Configuration changes**: None.

## Steps to Reproduce

Call `_load_skill_catalog` with a temporary consumer root lacking root-level `skills/` and `commands/`; observe an empty catalog despite installed little-loops content. In a wheel installation without `CLAUDE_PLUGIN_ROOT`, run `ll-help` and observe that its legacy fallback does not locate the packaged skills.

## Status

**Open** | Created: 2026-09-16 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-09-17T03:10:39 - `62feba6c-702f-4140-917b-5a2b05ea6c40.jsonl`
- `/ll:wire-issue` - 2026-09-17T01:06:16 - `9edbdbb5-9660-42b5-a715-69e61709aaa6.jsonl`
- `/ll:refine-issue` - 2026-09-16T22:24:05 - `c7278f1b-df03-4464-a3c5-e94aa066b201.jsonl`

- 2026-09-16 pre-implementation review: added `cli/harness.py::_resolve_skill_target_path` as a read consumer, listed verify CLIs as boundaries, named the `_content_root_candidates()` test seam, noted precedence equivalence with `server.py`, cited the wheel-smoke test, and recorded the server.py follow-up.
- Design review incorporated: select one read-only installation, preserve mutation roots, define invocation deduplication and parity tests, defer project-skill merging and persisted marketplace discovery.
