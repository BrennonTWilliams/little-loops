---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-339: CLI hardcodes .loops directory path

## Summary

`cli.py` hardcodes `.loops` in 4+ places with no corresponding config key in the schema or `ll-config.json`. Users cannot customize the loops directory location.

## Context

Identified during a config consistency audit. The `.loops` directory is the only major directory path without a config schema entry.

## Affected Files

- `scripts/little_loops/cli.py` (lines ~659, 664, 927, 979): hardcoded `.loops` path
- `config-schema.json`: missing `loops.loops_dir` config key
- `scripts/little_loops/config.py`: no `LoopsConfig` dataclass

## Proposed Fix

1. Add `loops` section to `config-schema.json`:
   ```json
   "loops": {
     "type": "object",
     "properties": {
       "loops_dir": { "type": "string", "default": ".loops" }
     }
   }
   ```
2. Add `LoopsConfig` dataclass in `config.py` and wire into `BRConfig`
3. Replace all hardcoded `.loops` references in `cli.py` with `config.loops.loops_dir`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Config system design |

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
