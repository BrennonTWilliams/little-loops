---
id: BUG-2310
title: "ll-init re-init clobbers unmodeled config keys despite \"Merging\" message"
type: BUG
status: open
priority: P1
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- config
- data-loss
relates_to:
- ENH-2240
- BUG-2042
---

# BUG-2310: ll-init re-init clobbers unmodeled config keys despite "Merging" message

## Summary

Re-running `ll-init` on a project that already has `.ll/ll-config.json` **silently
destroys** every config key that `build_config()` does not model. The headless
path prints `"Merging with existing configuration."` but performs no merge — it
rebuilds a fixed subset of keys and overwrites the file wholesale. A
`deep_merge()` with the correct semantics already exists in `config/core.py:44`
but neither init path uses it.

## Current Behavior

`_run_yes` (`scripts/little_loops/init/cli.py:303-315`):
1. Loads existing config and pre-populates a **fixed subset** of keys into `choices`.
2. Calls `build_config()`, which only emits keys it knows about.
3. Calls `write_config()`, which does `atomic_write_json` — a full overwrite.

The TUI path (`scripts/little_loops/init/tui.py:628,839`) has the same shape
(pre-populates more keys, but still overwrites wholesale).

Empirically, re-running `ll-init --yes` against this very repo would **delete**:

```
commands.confidence_gate.{enabled,readiness_threshold}
commands.tdd_mode
context_monitor.auto_handoff_threshold = 50
design_tokens.{active,active_theme}
documents.*            (entire section)
history.compaction.*   (entire section)
history.session_digest.char_cap = 1200
scratch_pad.*          (entire detailed section)
sprints.default_max_workers = 2
```

The `"Merging with existing configuration."` message (`cli.py:174`) makes this
worse: the user is told their data is preserved while it is being clobbered.

Note `--force` does **not** gate this: `write_config` runs regardless of `--force`
(it only flips a print message and the codex-adapter overwrite). The advertised
exit code `1 - Error (config exists...)` in the `--help` epilog has no
corresponding code path.

## Expected Behavior

Re-running `ll-init` preserves any config keys the user set that `build_config`
does not model. The "Merging" message should reflect a real merge.

## Root Cause

`scripts/little_loops/init/cli.py` `_run_yes()` and
`scripts/little_loops/init/tui.py` write path both compute
`config = build_config(template, choices)` and pass it straight to
`write_config()`. `build_config()` (`scripts/little_loops/init/core.py:21`) emits
only `$schema, project, issues, scan, learning_tests, analytics, context_monitor
(enabled only), product, [decisions/scratch_pad/session_capture/prompt_optimization],
history.session_digest, loops.run_defaults`. Everything else in an existing file
is dropped. `deep_merge()` (`scripts/little_loops/config/core.py:44`) — built
precisely for config overlays — is never invoked by init.

## Proposed Fix

In both `_run_yes` and the TUI write path, layer the rebuilt config over the
existing one before writing:

```python
from little_loops.config.core import deep_merge
config = deep_merge(existing_config, build_config(template, choices))
write_config(config, ll_dir)
```

Caveat: `deep_merge` treats a `None` value in the override as a key-removal
sentinel — coordinate with BUG-2311 (null leaves) so `build_config` does not emit
`None` leaves that would delete user keys (e.g. `loops.run_defaults.mode`) on
merge. Either strip `None` leaves in `build_config` or merge on a None-stripped
copy.

## Impact

Any user who re-runs `ll-init` (e.g. to pick up a new feature toggle, or after a
plugin upgrade) loses hand-tuned settings — sprints, confidence gate, documents,
scratch_pad, history compaction, context-monitor threshold. High blast radius and
silent.

## Labels

- init, config, data-loss

## Session Log
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P1
