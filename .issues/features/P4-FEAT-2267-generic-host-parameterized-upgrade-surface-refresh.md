---
id: FEAT-2267
title: Generic host-parameterized ll-init --upgrade surface refresh
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
blocked_by: [BUG-2266]
relates_to: [ENH-2256, FEAT-2260]
labels: [host-compat, portfolio, init, upgrade]
---

# FEAT-2267: Generic host-parameterized ll-init --upgrade surface refresh

## Summary

Generalize `ll-init --upgrade` from a Claude-plugin-only flow into a **single
host-parameterized surface-refresh dispatcher** that keeps *every* active
host's integration surface current after a package upgrade. Per
ARCHITECTURE-049, this is built **once** taking a host argument, not as N
bespoke per-host upgrade paths.

ENH-2256 (`a16d8f7d`) shipped `--upgrade` for the **pip package** plus a
warn/advise path for the **Claude marketplace plugin**, but:

1. The headless `--upgrade` only acts on the package; the Claude plugin update
   is never run, even with `--upgrade`.
2. There is **no surface at all** for non-Claude hosts. Their integration
   surface is **generated adapter files** in the target project
   (`.codex/hooks.json`, codex skill frontmatter / `.codex/agents/*.toml` from
   the `ll-adapt-*` CLIs, opencode/omp adapters) — not a marketplace plugin.
   `fetch_latest_plugin()` correctly returns `None` for these hosts, so they
   currently get **zero** upgrade signal.

## The two surface flavors

| Host | Surface | "Update" means | Staleness signal |
|------|---------|----------------|------------------|
| claude-code | versioned marketplace plugin | `<host> plugin update ll@little-loops` (scope-aware) | marketplace version query |
| codex / gemini / omp | generated adapter files in the project | **regenerate** against the new `plugin_root` | stamped gen-version vs installed package |

## Why non-Claude is more fragile

`install_codex_adapter()` (`writers.py:343-385`) renders the adapter by
substituting `{{LL_PLUGIN_ROOT}}` with an **absolute** `plugin_root` path
(`writers.py:374`). For a Claude plugin install that path is version-stamped
(`…/cache/…/ll/<version>/…`), so a package/plugin upgrade can leave
`.codex/hooks.json` pointing at an **old or deleted** version dir. And the
writer **skips existing files without `--force`** (`writers.py:371`), so a
plain re-run will not refresh a stale adapter.

## Acceptance Criteria

- `--upgrade` runs a **host-parameterized** surface-refresh after the package
  upgrade, dispatching per active host (driven by selected hosts /
  `resolve_host()`), built once — no per-host bespoke branches beyond the
  surface-flavor split.
- **claude-code branch**: scope-aware plugin update — auto-update when the
  install is **project-scoped**; **advise only** (or require explicit opt-in)
  when **user-scoped**, to avoid mutating shared global state from a
  project-scoped command. (Depends on BUG-2266 for scope.)
- **adapter-host branch**: force-regenerate each active host's adapters against
  the upgraded `plugin_root` (re-substitute the path so a dangling version
  stamp is corrected).
- **Staleness stamping**: generated adapters embed the package version they
  were generated from (mirror the existing `.claude/ll-update-docs.watermark`
  pattern). Warn-only mode compares stamp vs installed version and prints a
  concrete hint (`generated against X, package is now Y — re-run --upgrade`).
- All host CLI calls go through `resolve_host()` — never a hardcoded `"claude"`
  (per CLAUDE.md host-abstraction rule); best-effort (`check=False`) so a
  missing/unauthenticated host never aborts the init or config write.
- TUI Screen-1 per-surface checks (`tui.py:175-224`) extended to show
  adapter-staleness rows for non-Claude hosts, symmetric with the existing
  package/plugin rows.

## Open design questions (keep explicit; do not pre-decide)

- User-scoped Claude plugin: auto-update gated on `scope == project` only, vs.
  a separate `--upgrade-global` opt-in, vs. always advise. (Scope philosophy:
  should a project-scoped command ever mutate global state?)
- Where the adapter gen-version stamp lives (inside each adapter file as a
  comment/field, vs. a sidecar watermark per host).

## Reference

- `scripts/little_loops/init/cli.py:159-236` — current package/plugin upgrade block.
- `scripts/little_loops/init/install_check.py:105-146` — `fetch_latest_plugin`.
- `scripts/little_loops/init/writers.py:343-385` — `install_codex_adapter` (skip-without-force + plugin_root substitution).
- `scripts/little_loops/init/cli.py:57-80` — `_dispatch_host_adapters`.
- ENH-2256 — originating work. FEAT-2260 — generic skill/command adapter (sibling shared-infra child).

## Impact

- **Effort**: Medium. **Risk**: Medium — touches global plugin state (gated) and
  regenerates project files (force). **Breaking change**: No (additive flag behavior).

## Status

**Open** | Created: 2026-06-24 | Priority: P4
