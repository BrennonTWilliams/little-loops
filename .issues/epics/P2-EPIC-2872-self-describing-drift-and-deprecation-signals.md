---
id: 2872
title: Self-describing drift and deprecation signals
type: EPIC
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
discovered_source: https://github.com/pbakaus/impeccable
labels:
- hygiene
- issue-schema
- observability
---

# EPIC-2872: Self-describing drift and deprecation signals

Origin: ll-product #EPIC-072

## Summary

Two failure modes in little-loops' own metadata share a shape: a signal is emitted without encoding what should be done about it, so a human or an agent has to re-derive the action every time — and usually gets it wrong in the cheap direction.

- **Drift findings** from `ll-verify-docs`, `ll-check-links`, and `ll-doctor --full` arrive as an undifferentiated list. Nothing marks which findings are safely auto-fixable, which need a human, and which a specific other command already owns. So `--fix` stays conservative and the remainder becomes noise that gets tuned out wholesale.
- **Retired schema fields** are marked deprecated without a reason. A model told only that a field is deprecated preserves it "just in case" — which is how a retired axis keeps steering current output. `parent_issue` (the deprecated alias for `parent`, `issue_parser.py:1007`) is an existing instance.

Both are fixed by the same move: make the signal carry its own disposition. An action-severity on every drift finding; a mandatory prose reason on every deprecation.

## Children

- Give drift findings an action-severity and a throttle, and forbid opportunistic repair
- Deprecate schema fields with a mandatory prose reason, not just a deprecated flag

Independent of each other; either can ship first.

## Success Metrics

- `ll-doctor --fix` applies only findings marked auto-fixable, and a routed finding names the command that owns its repair.
- Repeat low-value findings are throttled per project rather than re-emitted every run.
- A retired frontmatter key carries a prose reason at the point of validation, and adding a deprecation entry without one fails validation.

## Integration Map

- `ll-verify-docs`, `ll-check-links`, `ll-doctor`
- Issue-frontmatter and loop-YAML schema definitions (`issue_parser.py`)

## Provenance

Both patterns mined from `https://github.com/pbakaus/impeccable` (Apache-2.0), where drift findings carry an action-severity (`auto` / `mention` / `route`) and every retired spec field is paired with a mandatory prose reason. Described and re-implemented, not copied.
