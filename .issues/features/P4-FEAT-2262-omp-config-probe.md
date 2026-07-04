---
id: FEAT-2262
title: omp config probe — oh-my-pi config candidate in _config_candidates()
type: feature
status: done
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

## Implementation Notes (2026-07-03)

oh-my-pi's config directory confirmed as `.omp/` by the FEAT-1850 headless
audit (`thoughts/research/omp-headless-flags.md` — upstream repo carries a
project-level `.omp/`; user root is `~/.omp/`, `PI_CONFIG_DIR` overrides).
Added `OMP_CONFIG_DIR = ".omp"` and a `host == "omp" or state_dir ==
OMP_CONFIG_DIR` branch to `_config_candidates()` in
`scripts/little_loops/config/core.py`, prepending `.omp/ll-config.json` ahead
of `.ll/` and root candidates — mirroring the `.codex` handling. Tests: four
omp probe tests in `scripts/tests/test_config.py::TestResolveConfigPath`
(host precedence, `LL_STATE_DIR=.omp` trigger, ignored without trigger,
fallthrough). `HOST_COMPATIBILITY.md` config-probe table updated.

## Status

**Done** | Created: 2026-06-24 | Completed: 2026-07-03 | Priority: P4
