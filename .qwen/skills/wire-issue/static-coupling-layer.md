# Wire-Issue: Static Coupling Layer (Phase 3.5)

Loaded by `/ll:wire-issue` Phase 3.5. Added by FEAT-1736.

## Overview

Query the decisions log for `coupling` entries before spawning agents. Matching entries inject `then_check` targets as `MUST_AUDIT` into Phase 4 agent prompts, shifting known coupling patterns from per-run re-discovery to a project-maintained knowledge base. The log is hybrid storage (a legacy `.ll/decisions.yaml` flat file and/or `.ll/decisions.d/*.json` fragments); querying via `ll-issues decisions list` reads both tiers, so no file-presence gate is needed here.

## Procedure

```bash
# Load all coupling entries
COUPLING_JSON=$(ll-issues decisions list --type=coupling --format=json 2>/dev/null)

# If empty or the decisions log is absent, skip to Phase 4 (no error)
[ -z "$COUPLING_JSON" ] || [ "$COUPLING_JSON" = "[]" ] && proceed_to_phase_4

# Infer archetype from issue title (add-cli-command, add-config-key, add-event-type, ...)
# Load matching bundle and merge (deduplicate by id)
ARCHETYPE_JSON=$(ll-issues decisions list --type=coupling --archetype="${INFERRED_ARCHETYPE}" --format=json 2>/dev/null)

# For each entry: fnmatch(changed_file, entry.if_changed) → collect then_check into MUST_AUDIT
```

## Tier handling

| Tier | Where injected |
|------|---------------|
| `hard` | Phase 4 agent prompts + Implementation Steps (blocking) |
| `soft` | Phase 4 agent prompts (advisory) |
| `fyi` | Report only — not injected into agent prompts |

## Agent prompt injection

Prepend to each Phase 4 agent prompt when MUST_AUDIT is non-empty:

```
STATIC LAYER — MUST_AUDIT (from coupling rules in the decisions log):
  HARD (blocking — must change together):
    - <path1>
  SOFT (should update):
    - <path2>

Cross-check these targets before searching for additional wiring gaps.
```

## Adding coupling entries

```bash
ll-issues decisions add \
  --type=coupling \
  --category=wiring \
  --if-changed="commands/*.md" \
  --then-check=".claude-plugin/plugin.json,.claude/CLAUDE.md" \
  --tier=hard \
  --archetype=add-cli-command \
  --rationale="New CLI commands must be registered in plugin.json"
```
