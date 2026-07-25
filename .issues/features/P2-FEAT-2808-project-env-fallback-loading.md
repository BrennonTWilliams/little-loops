---
id: FEAT-2808
title: "Project .env fallback loading at every CLI entry point"
type: FEAT
priority: P2
status: done
captured_at: '2026-07-25T18:25:08Z'
completed_at: '2026-07-25T18:25:08Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
relates_to:
- BUG-2807
- ENH-2737
labels:
- config
- cli
- credentials
---

# FEAT-2808: Project .env fallback loading at every CLI entry point

## Summary

New `scripts/little_loops/env_file.py` (`parse_env_file` +
`load_env_fallback`) loads a gitignored `<project_root>/.env` into
`os.environ`, wired into `BRConfig.__init__` so every CLI entry point
(`ll-auto`, `ll-loop`, `ll-parallel`, `ll-sprint`, ...) and the FSM
executor's SDK credential probe pick it up uniformly; child host-CLI
processes inherit the values.

## Motivation

`claude setup-token` tells subscription users to set
`CLAUDE_CODE_OAUTH_TOKEN`; the conventional home is a project `.env` —
which nothing in little-loops read, leaving the BUG-2807 credential probe
to downgrade `request_path: sdk` to the CLI path even after the token was
minted and stored.

## Design Decisions

- **Real environment always wins**: only keys absent from `os.environ` are
  set, and a set-but-empty env var counts as present (an explicit `FOO=` in
  the shell is a deliberate signal, not an invitation to backfill). A stale
  `.env` value can never shadow a deliberately exported one.
- **All keys loaded** (standard `.env` semantics), not an allowlist — the
  never-override rule is the safety valve.
- **Stdlib-only parser** per the minimize-dependencies policy (no
  `python-dotenv`): comments, blank lines, optional `export ` prefix,
  single/double-quoted values; malformed lines skipped silently (a parse
  hard-fail would break every CLI entry point). No interpolation or
  multiline values.
- Loaded in `BRConfig.__init__` before `_load_config()`, so it precedes any
  environment read (host selection, credential probes). Idempotent.

## Verification

- 10 tests in `scripts/tests/test_env_file.py` (parser edge cases,
  precedence, set-but-empty, BRConfig wiring end-to-end).
- Live: constructing `BRConfig` in this repo makes the `.env`-stored
  `CLAUDE_CODE_OAUTH_TOKEN` visible to the process.
- Documented in `docs/reference/CONFIGURATION.md`; mypy/ruff clean;
  `ll-verify-docs` passes.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-25T18:25:46 - `2b65dece-bf36-4022-a4e8-1a1ea6eed801.jsonl`
- `/ll:capture-issue` - 2026-07-25T18:25:08Z

---

## Status
- Status: done
