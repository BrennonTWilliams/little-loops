---
id: ENH-2028
title: "session_digest.enabled defaults off \u2014 ambient history context never fires"
type: ENH
priority: P4
status: open
captured_at: '2026-06-08T22:17:25Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- ENH-1907
- EPIC-1707
confidence_score: 84
outcome_confidence: 74
score_complexity: 20
score_test_coverage: 19
score_ambiguity: 14
score_change_surface: 21
decision_needed: true
---

# ENH-2028: session_digest.enabled defaults off — ambient history context never fires

## Summary

ENH-1907 implemented the project-context snapshot (ambient `<project_context>` block injected at session start via `session_start.py`), but `SessionDigestConfig.enabled` defaults to `False` and the little-loops project itself has no `history:` block in `.ll/ll-config.json`. As a result, the most frictionless form of history injection silently never fires on any install, including the one where it was built. The feature is effectively invisible post-install.

## Motivation

The EPIC-1707 vision is "prior corrections, file edits, and tool-use patterns inform agent outputs without the user manually surfacing context." The ambient session-start digest is the only mechanism that achieves this for *every* skill and conversation without requiring per-skill `ll-history-context` calls. Keeping it opt-in means users never discover it; the value proposition depends on it being always-on with a cap, not on users knowing to configure it.

## Current Behavior

`SessionDigestConfig.enabled` defaults to `False` (`scripts/little_loops/config/features.py:658`). `session_start.py` gates the entire digest path on `feature_enabled(merged_config, "history.session_digest.enabled")`. With no `history:` block in the project config, `enabled` is never set to `True`, so the block is never generated and the hook exits without injecting anything.

## Expected Behavior

One of:
1. **(Preferred)** Change `SessionDigestConfig.enabled` default to `True` with a conservative `char_cap` (e.g. 800 chars) — opt-out rather than opt-in. Projects that don't want it can set `history.session_digest.enabled: false`.
2. **(Lighter)** Keep the global default as `False` but enable it in this project's `.ll/ll-config.json` so at minimum little-loops itself dogfoods the feature.
3. Wire `/ll:init` and `/ll:configure` to prompt about enabling session_digest during setup.

Option 1 is the right long-term default; option 2 is a quick fix for this project.

## Scope Boundaries

- **In scope**: Changing `SessionDigestConfig.enabled` default to `True` (option 1), adding a `history.session_digest` block to `.ll/ll-config.json` (option 2), or wiring a session_digest prompt into `/ll:init`/`/ll:configure` (option 3).
- **In scope**: Updating `config-schema.json`, `docs/reference/API.md`, `CHANGELOG.md`, and tests to reflect the chosen default.
- **Out of scope**: Changing the content format or algorithm of the session digest itself (ENH-1907).
- **Out of scope**: Adding new history data sources beyond what ENH-1907 already captures.
- **Out of scope**: Modifying per-skill explicit `ll-history-context` call behavior.
- **Out of scope**: Changing the cap algorithm or stale-filtering decay logic.

## Implementation Steps

### Option 1: Change default to True

1. In `scripts/little_loops/config/features.py`, change `SessionDigestConfig.enabled: bool = False` to `True`.
2. Update `SessionDigestConfig.from_dict` to default `enabled` to `True`.
3. Update `config-schema.json` and `docs/reference/API.md` to reflect the new default.
4. Add a migration note to `CHANGELOG.md` (behavior change — previously silent, now injects a capped digest).
5. Add/update tests in `scripts/tests/test_session_start.py` to assert the digest fires when no config is present.

### Option 2: Enable in project config (quick fix)

Add to `.ll/ll-config.json`:
```json
"history": {
  "session_digest": {
    "enabled": true,
    "days": 7,
    "char_cap": 1200
  }
}
```

### Option 3: Wire into init/configure

Update `skills/init/SKILL.md` Phase 3 and `skills/configure/SKILL.md` to include a `session_digest` prompt block.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py` — change `SessionDigestConfig.enabled` default (option 1)
- `config-schema.json` — update default annotation for `history.session_digest.enabled`
- `.ll/ll-config.json` — add `history.session_digest` block (option 2)
- `skills/init/SKILL.md` — add session_digest prompt to Phase 3 (option 3)
- `skills/configure/SKILL.md` — add session_digest prompt block (option 3)
- `CHANGELOG.md` — behavior-change migration note (option 1)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/session_start.py` — reads `history.session_digest.enabled` via `feature_enabled()`; primary consumer of the config change
- TBD — `grep -r "session_digest" scripts/little_loops/` to find other references

### Similar Patterns
- TBD — `grep -r "SessionDigestConfig\|session_digest" scripts/little_loops/config/` for other feature-flag defaults to keep consistent

### Tests
- `scripts/tests/test_session_start.py` — assert digest fires with default config (option 1)
- `scripts/tests/test_config_features.py` — verify `SessionDigestConfig()` default matches intended behavior

### Documentation
- `docs/reference/API.md` — update `SessionDigestConfig` default annotation

### Configuration
- `config-schema.json` — `history.session_digest.enabled` default value change

## API / Interface Changes

- `SessionDigestConfig.enabled` default value changes (if option 1).
- `config-schema.json` default annotation for `history.session_digest.enabled`.
- No CLI surface changes.

## Tests

- `scripts/tests/test_session_start.py` — assert digest fires with default config (option 1), or assert it fires when config sets `enabled: true` (option 2).
- `scripts/tests/test_config_features.py` — verify `SessionDigestConfig()` default matches intended behavior.

## Impact

- **Priority**: P4 — Feature is fully implemented but invisible post-install; no user is blocked.
- **Effort**: Small — Option 1 is a one-line default change plus doc/test updates. Option 2 is a config file edit only.
- **Risk**: Low — Option 1 changes observable behavior (adds a capped context block at session start) but the conservative `char_cap` limits injection size; opt-out available via `history.session_digest.enabled: false`.
- **Breaking Change**: Yes (option 1) — Sessions that previously injected nothing will now inject a capped digest block. Not an API break, but an observable behavior change requiring a CHANGELOG entry.

## Labels

`history`, `session-digest`, `config-defaults`, `dx`, `discoverability`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-08_

**Readiness Score**: 84/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Unresolved decision between Option 1, 2, and 3** — "Option 1 is the right long-term default" is stated but not formally decided. This is an open decision that must be resolved before implementation starts; implementing the wrong option produces a qualitatively different outcome.
- **Two TBD items in Integration Map** (lines 85 and 88) — full list of `session_digest` references and feature-flag defaults to keep consistent have not been verified. Quick greps resolve these (7 references found; only `session_start.py` is a behavioral consumer), but should be confirmed before finalizing scope.

## Session Log
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `ad2e03f6-8c83-42d6-b37c-d90baffcb383.jsonl`
- `/ll:format-issue` - 2026-06-09T01:44:50 - `69b33e41-c63d-4418-8c47-2b1a6287ce4b.jsonl`
- `/ll:capture-issue` - 2026-06-08T22:17:25Z - `a20cfa81-f228-4cd0-9501-12f64feb6d30.jsonl`

---

**Open** | Created: 2026-06-08 | Priority: P4
