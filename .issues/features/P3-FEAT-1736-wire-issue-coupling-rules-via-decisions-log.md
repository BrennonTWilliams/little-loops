---
id: FEAT-1736
title: Wire-Issue Coupling Rules via Decisions Log
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-27
discovered_by: capture-issue
captured_at: '2026-05-27T04:46:43Z'
completed_at: '2026-06-06T06:29:42Z'
depends_on:
- FEAT-1712
parent: EPIC-1707
confidence_score: 92
outcome_confidence: 77
score_complexity: 19
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 22
---

# FEAT-1736: Wire-Issue Coupling Rules via Decisions Log

## Summary

Extend `decisions.yaml` with a `coupling` entry type that serves as wire-issue's static layer. Archetype template bundles — named sets of coupling entries — replace the need for a separate `coupling-rules.yaml` file. Wire-issue's Phase 3 loads active coupling entries and injects them as a pre-populated must-check list before spawning discovery agents, shifting coupling discovery from pure agent inference to a queryable, project-maintained knowledge base.

## Current Behavior

Wire-issue discovers integration points through 3 agent passes starting from scratch on every run. There is no persistent record of project-specific coupling patterns. Change archetypes (e.g., "adding a CLI command always requires updating plugin.json, CLAUDE.md, and commands/") must be re-discovered by agents on every run, leading to inconsistent coverage and missed wiring on repeated issue types.

## Expected Behavior

`decisions.yaml` (introduced by FEAT-948) gains a `coupling` entry type alongside the existing `rule`, `decision`, and `exception` types. A coupling entry adds:
- `if_changed` — glob pattern matching files being modified
- `then_check` — list of files/patterns to audit for wiring gaps
- `tier` — `hard` (must change together) | `soft` (should update) | `fyi` (informational)
- `archetype` — optional named bundle label (e.g., `add-cli-command`) grouping related coupling rules

Wire-issue Phase 3 queries active coupling entries matching the issue's planned changes and injects them as a pre-populated must-check list before spawning agents. Agent passes then validate and classify what the static layer surfaces rather than discovering from scratch.

Archetype templates are implemented as sets of coupling entries sharing an `archetype:` label, queryable as a group.

**Fallback**: `decisions.yaml` is always the source of truth. When SQLite (FEAT-1112) is available, coupling entries are queried via FTS5 index for speed. When no DB exists, the full YAML is loaded and filtered in Python — no error, no degraded behavior.

## Motivation

The wire-issue improvements analysis (`docs/research/wire-issue-improvements.md`) identifies two root causes for missed wiring: thin symbol extraction and no persistent coupling knowledge. This issue addresses the latter. Known coupling patterns (e.g., any change to `config-schema.json` requires updating `docs/reference/API.md`) are expressed once as coupling entries and applied automatically on every wire-issue run for matching issues, eliminating repeated agent re-discovery of the same patterns.

Coupling rules live in decisions.yaml rather than a separate file because the schema already provides stable IDs, enforcement tiers, `supersedes` for rule evolution, and `labels[]` for archetype grouping — all the structure needed for coupling rules without a second file to maintain.

## Proposed Solution

**Schema extension** — add `coupling` as a fourth entry type in decisions.yaml with fields `if_changed`, `then_check`, `tier`, `archetype`. Reuse existing `id`, `category`, `labels`, `rationale`, `enforcement`, and `supersedes` fields unchanged.

**Archetype bundles** — a named archetype (e.g., `add-cli-command`) is a set of coupling entries sharing `archetype: add-cli-command` in their labels. Wire-issue infers the archetype from the issue title + implementation plan via a lightweight prompt, then loads the matching bundle as a pre-populated must-check list.

**Wire-issue Phase 3 integration** — after extracting key symbols, query coupling entries where `if_changed` globs match the planned change files. Inject matched `then_check` targets directly into agent prompts as an explicit must-audit list. Hard-tier entries are added to Implementation Steps as blocking; soft-tier entries appear in the Integration Map with a warning; fyi-tier entries are mentioned in the report only.

**Query path** (with fallback):
```python
def load_coupling_entries(config, changed_globs):
    db_path = config.session_db  # from FEAT-1112
    if db_path and db_path.exists():
        return query_coupling_via_sqlite(db_path, changed_globs)
    # fallback: load YAML directly
    decisions = yaml.safe_load(open(config.decisions.log_path))
    return [e for e in decisions if e["type"] == "coupling"
            and any(fnmatch(g, e["if_changed"]) for g in changed_globs)]
```

**Graceful degradation** — if `decisions.yaml` does not exist, wire-issue skips the static layer entirely and proceeds with pure agent discovery (current behavior). Absence of the file is not an error.

## API/Interface

```yaml
# .ll/decisions.yaml — coupling entry examples

- id: "COUPLING-001"
  type: coupling
  timestamp: "2026-05-27T00:00:00Z"
  category: wiring
  labels: [wire-issue, archetype:add-cli-command]
  archetype: add-cli-command
  if_changed: "commands/*.md"
  then_check:
    - ".claude-plugin/plugin.json"
    - ".claude/CLAUDE.md"
    - "skills/*/SKILL.md"
    - "docs/reference/API.md"
  tier: hard
  rationale: "New CLI commands must be registered in plugin.json and listed in CLAUDE.md or they are invisible to users."
  enforcement: required

- id: "COUPLING-002"
  type: coupling
  timestamp: "2026-05-27T00:00:00Z"
  category: wiring
  labels: [wire-issue, archetype:add-config-key]
  archetype: add-config-key
  if_changed: "config-schema.json"
  then_check:
    - "docs/reference/API.md"
    - ".claude/CLAUDE.md"
  tier: hard
  rationale: "Config schema changes must be reflected in the API reference and CLAUDE.md project config section."
  enforcement: required

- id: "COUPLING-003"
  type: coupling
  timestamp: "2026-05-27T00:00:00Z"
  category: wiring
  labels: [wire-issue]
  if_changed: "scripts/little_loops/events/**"
  then_check:
    - "docs/reference/schemas/"
    - "scripts/little_loops/cli/ll_generate_schemas.py"
  tier: hard
  rationale: "New LLEvent subtypes require schema regeneration and schema directory update."
  enforcement: required
```

```bash
# CLI — adding coupling entries via existing decisions subcommand
ll-issues decisions add \
  --type=coupling \
  --category=wiring \
  --if-changed="commands/*.md" \
  --then-check=".claude-plugin/plugin.json,.claude/CLAUDE.md" \
  --tier=hard \
  --archetype=add-cli-command \
  --rationale="New commands must be registered in plugin.json"

ll-issues decisions list --type=coupling --archetype=add-cli-command
```

## Integration Map

### Files to Modify

**Schema:**
- `scripts/little_loops/decisions.py` — add `CouplingEntry` dataclass alongside `RuleEntry`, `DecisionEntry`, `ExceptionEntry`; add `if_changed`, `then_check`, `tier`, `archetype` fields; extend `add_entry()` and `list_entries()` dispatch to handle `type=coupling`
- `config-schema.json` — no new top-level key; coupling entries live in decisions.yaml under existing `decisions` schema block; update entry type enum to include `coupling`

**Wire-issue static layer:**
- `skills/wire-issue/SKILL.md` — Phase 3: after symbol extraction, call `ll-issues decisions list --type=coupling` and filter by `if_changed` glob match against planned change files; inject matched `then_check` targets into agent prompts as `MUST_AUDIT` list; annotate by tier in output

**CLI extension:**
- `scripts/little_loops/cli/issues/decisions.py` — extend `add` subcommand to accept `--if-changed`, `--then-check`, `--tier`, `--archetype` flags when `--type=coupling`; extend `list` to support `--archetype` filter

### Dependent Files (Callers/Importers)
- `skills/wire-issue/SKILL.md` — Phase 3 invokes `ll-issues decisions list` (subprocess call); imports `load_coupling_entries()` indirectly via CLI
- No existing Python callers — `load_coupling_entries` and `CouplingEntry` are new symbols; only consumer at runtime is `skills/wire-issue/SKILL.md` Phase 3 via CLI subprocess (`ll-issues decisions list --type=coupling`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — imports `cmd_decisions`, `add_decisions_parser`; may need `CouplingEntry` added to its import block if used at the dispatch layer [Agent 1 finding]
- `scripts/little_loops/decisions_sync.py` — imports `list_entries`, `resolve_active`; calls `list_entries(path, type="rule")` so coupling entries are naturally excluded — no changes required [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/decisions.py` — add `CouplingEntry` following `RuleEntry` / `DecisionEntry` pattern from FEAT-948
- `fnmatch` (stdlib) — glob matching for `if_changed` patterns against planned change file paths
- `skills/wire-issue/SKILL.md` Phase 3 — injection point for must-audit list (same location as FEAT-948's symbol extraction fix, option 3 from wire-issue-improvements.md)

### Tests
- `scripts/tests/test_decisions.py` — extend with: load coupling entries, filter by archetype, `if_changed` glob matching, tier classification, graceful skip when no `decisions.yaml`
- `scripts/tests/test_cli_decisions.py` — extend with: coupling-specific `--if-changed`, `--then-check`, `--tier`, `--archetype` flag validation in `add`; `--archetype` post-filter in `list`; ID prefix `"COUPLING"` auto-generation in `_cmd_add()`
- `scripts/tests/test_wire_issue_static_layer.py` — new: coupling entry injection into wire-issue Phase 3, fallback when no DB, fallback when no decisions.yaml

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — conditional: `test_decisions_in_schema` currently asserts `additionalProperties: false` on the `decisions` block; if a new field is added to `config-schema.json` for coupling support, this test needs a corresponding assertion [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — asserts `ll-issues decisions` appears in `docs/reference/CLI.md`; extend with parametrized assertions for new flags (`--archetype`, `--if-changed`, `--then-check`, `--tier`) once CLI.md is updated [Agent 1 finding]

### Documentation
- `docs/research/wire-issue-improvements.md` — add note that Dimensions 3 and 4 are addressed by this issue (coupling entries + archetype bundles replace separate `coupling-rules.yaml`)
- `docs/reference/API.md` — document `CouplingEntry` dataclass and `load_coupling_entries()` helper
- `docs/reference/CLI.md` — document coupling-specific flags (`--if-changed`, `--then-check`, `--tier`, `--archetype`) for `ll-issues decisions add` and `--archetype` for `ll-issues decisions list`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — add `coupling` row to the "Decisions Log" entry-type table (currently lists `rule`, `decision`, `exception`); add `wire-issue` to the Key consumers line [Agent 2 finding]

### Configuration
- `config-schema.json` — entry type enum updated to include `coupling` (tracked under Files to Modify above)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`config-schema.json` has no entry-type enum**: The `decisions` section of `config-schema.json` only has `enabled`, `log_path`, `auto_generate` keys — no `entries[].type` enum. The actual type enum lives in two Python locations: `_ENTRY_REGISTRY` dict keys in `scripts/little_loops/decisions.py` and `choices=["rule","decision","exception"]` in `scripts/little_loops/cli/issues/decisions.py`. Both need `"coupling"` added; `config-schema.json` does not.

- **`config.session_db` property does not exist on `BRConfig`**: The pseudocode in Proposed Solution uses `config.session_db` which is not a real attribute. The correct pattern (matching `generate_from_completed()` in `decisions.py`) is `db_path = project_root / ".ll" / "history.db"`. Alternatively use `Path(config.decisions.log_path).parent / "history.db"` for path-relative resolution. Update `load_coupling_entries()` to use one of these.

- **SQLite `query_coupling_via_sqlite()` requires a new DB migration**: The session store is at schema v12 (`SCHEMA_VERSION = 12` in `session_store.py`) and has no coupling table or FTS5 index for coupling entries. Implementing the SQLite fast-path requires adding a migration in `session_store._MIGRATIONS`. Consider deferring the SQLite path to a follow-on; the YAML fallback is robust for all current use cases.

- **`_cmd_add()` ID auto-generation prefix dict needs updating**: In `scripts/little_loops/cli/issues/decisions.py`, `_cmd_add()` generates entry IDs from a hardcoded prefix dict `{"rule": "RULE", "decision": "DEC", "exception": "EXC"}`. Adding `"coupling": "COUPLING"` to this dict is required alongside the `--type choices` update.

- **`issue_history/coupling.py` is an unrelated module**: `scripts/little_loops/issue_history/coupling.py` exists but computes Jaccard file co-occurrence from completed issue history — a different concept from `CouplingEntry` in decisions.yaml. No changes needed to this file; naming does not conflict since they are in separate packages.

- **`decisions_sync.py` is not affected**: `decisions_sync.py` syncs only `type="rule"` entries with `enforcement="required"` to `ll.local.md`. Coupling entries will not be auto-synced, which is correct behavior — coupling entries drive wire-issue, not the Active Rules block.

## Implementation Steps

1. **Schema + dataclass** — add `CouplingEntry` to `scripts/little_loops/decisions.py` with `if_changed`, `then_check`, `tier`, `archetype` fields; extend `add_entry()` / `list_entries()` / `resolve_active()` to dispatch on `type=coupling`
2. **CLI extension** — extend `decisions add` in `scripts/little_loops/cli/issues/decisions.py` to accept coupling-specific flags; extend `list` to support `--archetype` filter
3. **Query helper** — implement `load_coupling_entries(config, changed_globs: list[str]) -> list[CouplingEntry]` in `decisions.py`: SQLite path when DB available, YAML fallback otherwise; graceful return of `[]` when `decisions.yaml` absent
4. **Wire-issue integration** — update `skills/wire-issue/SKILL.md` Phase 3 to call `ll-issues decisions list --type=coupling`, match `if_changed` globs against planned change files, and inject matched `then_check` targets as `MUST_AUDIT` list in agent prompts; annotate hard/soft/fyi tier in output
5. **Archetype inference** — add lightweight prompt in wire-issue Phase 3 to infer archetype label from issue title + implementation plan; use inferred label to pre-load matching bundle via `--archetype` filter
6. **Tests** — extend `test_decisions.py`; create `test_wire_issue_static_layer.py`
7. **Docs** — update `docs/research/wire-issue-improvements.md` and `docs/reference/API.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/ARCHITECTURE.md` — add `coupling` row to the "Decisions Log" entry-type table; add `wire-issue` to the Key consumers line alongside the existing consumers
9. Update `_print_entry()` in `scripts/little_loops/cli/issues/decisions.py` — add `elif isinstance(entry, CouplingEntry):` branch to display `if_changed`, `then_check`, and `tier` fields; without this branch, `ll-issues decisions list --type=coupling` shows only the header, silently omitting all coupling-specific content
10. Extend `test_wiring_cli_registry.py` — add parametrized assertions for the new coupling flags in `docs/reference/CLI.md` once the CLI docs are updated (step 7)

## Use Case

**Static layer hit**: A user runs `/ll:wire-issue` on a FEAT that adds a new CLI command. Phase 3 matches `commands/*.md` against `COUPLING-001`, loads `then_check` targets, and injects `.claude-plugin/plugin.json`, `.claude/CLAUDE.md`, and `docs/reference/API.md` as `MUST_AUDIT` into agent prompts. Agent 2 confirms which of these need updates — no re-discovery needed.

**Archetype inference**: The issue title is "Add `ll-issues audit` subcommand". Phase 3 infers archetype `add-cli-command`, loads the full bundle (COUPLING-001 and any other entries with that archetype label), and pre-populates the must-check list before agents run.

**Fallback**: A new project has no `decisions.yaml`. Wire-issue skips the static layer silently and proceeds with pure agent discovery — existing behavior, no error.

## Acceptance Criteria

- [ ] `decisions.yaml` supports a `coupling` entry type with `if_changed`, `then_check`, `tier`, and `archetype` fields
- [ ] `ll-issues decisions add --type=coupling` accepts and validates coupling-specific fields
- [ ] `ll-issues decisions list --type=coupling [--archetype=X]` filters and returns coupling entries
- [ ] Wire-issue Phase 3 loads matching coupling entries and injects `then_check` targets as `MUST_AUDIT` into agent prompts
- [ ] Hard-tier entries appear in Implementation Steps; soft-tier in Integration Map; fyi-tier in report only
- [ ] Archetype inference in Phase 3 identifies the change archetype from issue title + plan and loads matching bundle
- [ ] SQLite query path used when DB available (FEAT-1112); YAML + Python fallback otherwise
- [ ] Graceful skip (no error, no behavior change) when `decisions.yaml` does not exist
- [ ] Tests cover: coupling entry CRUD, archetype filtering, glob matching, tier classification, DB fallback, no-file fallback
- [ ] `docs/research/wire-issue-improvements.md` notes Dimensions 3 and 4 are addressed here

## Impact

- **Priority**: P3 — Quality-of-life improvement for wire-issue; not blocking current workflows
- **Effort**: Medium — Additive extension to FEAT-948's schema and CLI; wire-issue integration is the main new surface
- **Risk**: Low — Fully additive; graceful degradation means no existing behavior changes when feature is absent
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/wire-issue-improvements.md` | Source analysis; Dimensions 3 and 4 are addressed here |
| `.issues/features/P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md` | Prerequisite: establishes decisions.yaml schema and CLI |
| `docs/reference/API.md` | Document new `CouplingEntry` and query helper |

## Labels

`feature`, `wire-issue`, `decisions-log`, `coupling`, `static-analysis`, `captured`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:ready-issue` - 2026-06-06T06:13:24 - `bc0c9814-4d3f-43c0-80b0-7d94bf761d3d.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `b0de6839-9d9c-48cb-9f15-2f1d336ec2d8.jsonl`
- `/ll:wire-issue` - 2026-06-06T06:03:38 - `8ed7b083-50b7-47e3-a7f2-7a091b7ac0ec.jsonl`
- `/ll:refine-issue` - 2026-06-06T05:56:16 - `5f49fd53-56c3-4860-b0f4-ca309ceb1668.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `9029be6c-8329-49c0-9735-9a01010bd610.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-04T22:14:35 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-27T04:51:42 - `b23d6a24-9de3-4d03-ac3b-2a54631906b4.jsonl`
- `/ll:capture-issue` - 2026-05-27T04:46:43Z - `b79fe46a-2b76-4bd7-97a6-bcd0936e48b5.jsonl`
