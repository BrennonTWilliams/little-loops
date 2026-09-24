---
id: EPIC-3556
type: EPIC
title: Treat agent-authored artifact content as untrusted input
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
supersedes:
- ENH-3540
---

# EPIC-3556: Treat agent-authored artifact content as untrusted input

## Summary

`ll-artifact` emits single-file HTML pages that embed agent-influenced strings (model/tool output, skill catalog text, loop/branch/model names). Rendering them as markup turns prompt injection into stored XSS against whoever opens the artifact. Make escaping the default at every render boundary, pin it with hostile-payload tests, and route artifact writes through the symlink-safe atomic writer. Supersedes ENH-3540, split into four independently shippable children.

## Motivation

A shared artifact is opened by people other than the one who ran the session, so an injected payload executes against a different victim. Today's dashboard is safe by construction of one page, not by a rule.

## Integration Map

### Files to Modify
- `scripts/little_loops/artifact_templates.py` — `script_json` (ENH-3557); `escape_data`, schema annotations (ENH-3558)
- `scripts/little_loops/cli/artifact/policy_builder.py` — ENH-3557, ENH-3559
- `scripts/little_loops/cli/artifact/dashboard.py` — ENH-3557, ENH-3558, ENH-3559
- `scripts/little_loops/cli/artifact/extract.py` — ENH-3558, ENH-3559
- `scripts/little_loops/cli/artifact/{render,design_md,templatize}.py`, `scripts/little_loops/file_utils.py` — ENH-3559
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — ENH-3560

### Dependent Files (Callers/Importers)
- `cli/artifact/serve.py` re-serves the policy-builder and dashboard pages verbatim and inherits every fix.
- `render_template` callers (`render.py`, `dashboard.py`, `templatize.py` round-trip oracle, `fsm/persistence.py`) stay unchanged.
- ~80 `atomic_write` callers inherit ENH-3559's mode change.

### Tests
- Python: `test_policy_builder_emit.py`, `test_feat3304_artifact_dashboard.py`, `test_feat3036_artifact_templates.py`, `test_feat3310_artifact_extract.py`, `test_file_utils.py`, new `test_enh3559_artifact_symlink_safe_writes.py`; `test_artifact_templatize.py` must pass unchanged.
- Node: new `scripts/tests/js/policy_builder_dom_sinks.test.mjs`, enforced via `test_policy_builder_node_gate.py`.

### Documentation
- Allowlist docs in `artifact_templates.py`; `docs/reference/CLI.md` (`extract` / `refresh` / `render`); `refresh` help text (ENH-3558).

## Sequencing

ENH-3557 → ENH-3558 → ENH-3559, serialized by `blocked_by`. ENH-3558 needs `script_json` for its allowlisted `_js` keys, and all three edit `dashboard.py`; ENH-3558 and ENH-3559 both edit `extract.py`. ENH-3560 touches only the builder template and can run in parallel with any of them. ENH-3554 (templatize region-context tagging) follows ENH-3558 and is outside this epic.

## Impact

- **Priority**: P1 — prompt injection becomes stored XSS against whoever opens a shared artifact, often not the person who ran the session.
- **Effort**: Medium — four small-to-medium children, ~18 change sites.
- **Risk**: Medium — a wrong escape boundary breaks FEAT-3308 round trips; the global `atomic_write` mode change reaches ~80 callers.
- **Breaking Change**: Minor, behavioral (see Success Metrics).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P1

## Goal

Every `ll-artifact` generator treats agent-influenced strings as untrusted where they enter emitted HTML; `render_template` bytes stay unchanged (FEAT-3308 round trips).

## Scope

In: script-context JSON, single-pass placeholders, `escape_data` ingest escaping, atomic symlink-safe writes, builder DOM sinks. Out: templatize region-context tagging (ENH-3554), changing the frozen render env. Cancelled ENH-3540 holds the original spec and research trail; its Scope, decisions, and ACs have been carried into each child.

## Children
- **ENH-3557** — Script-context-safe JSON and single-pass placeholder substitution (open)
- **ENH-3558** — Escape-by-default ingest for template data and extract output (open)
- **ENH-3559** — Symlink-safe artifact writes and umask-preserving atomic_write (open)
- **ENH-3560** — Remove interpolated innerHTML sinks from policy builder (open)





## Success Metrics

- [ ] All four children `done`; the full `python -m pytest scripts/tests/` passes, including the Node gate.
- [ ] Hostile-payload tests (`</script>`, `onerror=`, `javascript:`, placeholder tokens, `<img onerror>` project names) exist for every export path: dashboard (shareable, `--local`, SSE fragments), `extract`/`refresh`, `policy-builder` (server splices and client DOM).
- [ ] `test_artifact_templatize.py` round-trip tests pass unchanged.
- [ ] CHANGELOG entries (release prep) for the three behavioral changes: `extract`/`refresh` `data.json` holds entity-encoded text; markup-spanning regions render as escaped text on `refresh` until ENH-3554; files written by `atomic_write` change from `0600` to umask-derived modes.

## Session Log
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
