---
name: compact-session
description: Use when asked to manually compact a session's memory, trigger session summarization, or reduce a long session's context footprint.
disable-model-invocation: true
allowed-tools:
  - Bash(ll-compact-session:*)
  - Read
metadata:
  short-description: Use when asked to manually compact a session's memory or trigger session summ
---

# Compact Session Skill

Manually triggers session-memory compaction for one session — the same LCM
compaction path (`session_store.compact_session`) that fires automatically in
the background once a session crosses the soft token threshold (FEAT-2598).
Produces leaf/condensed `summary_nodes` rows and prints the resulting
`CompactResult` (summary text, covered message count, token estimate).

This is the LCM/semantic-summarization axis — distinct from `ll-session
compact`, which sweeps the separate *retention* axis (`kind='retention'`
`raw_events` summarization, ENH-1906/ENH-2581). Do not confuse the two.

## When to Activate

Proactively offer or invoke this skill when the user:

- Asks to compact, summarize, or condense a session manually
- Wants to reduce a long-running session's context footprint before continuing
- Asks whether a session has been compacted yet, or wants to see its summary
- Mentions the session is approaching a context limit and wants to trigger
  summarization early rather than waiting for the automatic soft-threshold trigger

## Arguments

$ARGUMENTS

- **session_id** (required) — the session to compact. If the user doesn't name
  one, use the current session's ID (available from the host CLI's session
  context) or ask which session they mean.
- `--db PATH` (optional) — session database path (default: `.ll/history.db`)
- `--json` (optional) — machine-readable output

## How to Use

Run the `ll-compact-session` CLI command:

```bash
ll-compact-session SESSION_ID
```

For programmatic access (e.g. from another skill or loop evaluator):

```bash
ll-compact-session SESSION_ID --json
```

The JSON payload includes `new_leaves` (leaf nodes created this run),
`summary_text` (the condensed summary, `null` if the session has fewer than
two leaf blocks), `compacted_messages` (covered `message_events` ids), and
`context_token_estimate`.

Compaction is idempotent — repeated calls do not create duplicate nodes.
Note that `history.compaction.enabled` (default `false` in
`.ll/ll-config.json`) gates whether an LLM summary is produced at all; when
disabled, `ll-compact-session` still runs but the leaf/condensed summaries
fall back to deterministic truncation (no LLM cost) per the existing LCM
three-level escalation in `session_store._summarize_block`.

## Examples

| User says | Action |
|-----------|--------|
| "Compact this session before we keep going" | `ll-compact-session <current-session-id>` |
| "Has session abc123 been summarized?" | `ll-compact-session abc123 --json`, report `summary_text` |
| "This loop's session is getting huge, trigger compaction now" | `ll-compact-session <session-id>` |
