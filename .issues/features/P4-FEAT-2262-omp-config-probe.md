---
id: FEAT-2262
title: omp config probe — oh-my-pi config candidate in _config_candidates()
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2258
depends_on: [FEAT-1850]
labels: [host-compat, omp, config]
---

# FEAT-2262: omp config probe — _config_candidates()

## Summary

Add oh-my-pi's config-directory probe path to `_config_candidates()` in
`scripts/little_loops/config/core.py`, so an omp user's project config
(`.omp/ll-config.json` or oh-my-pi's actual config dir — confirmed during the
FEAT-1850 headless audit) is discovered the same way `.codex` is today.

## Acceptance Criteria

- `_config_candidates()` includes the omp config-dir candidate, special-cased
  alongside the existing `.codex` handling.
- An omp project with config in that dir resolves correctly via `resolve_host()`.
- Tests in `test_config*.py` cover the new candidate.

## Reference

- `scripts/little_loops/config/core.py` `_config_candidates()` — only `.codex`
  special-cased today.
- FEAT-1850 — confirms omp's actual config directory name during the headless audit.

## Impact

- **Effort**: XS–S.
- **Risk**: Low — additive.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
