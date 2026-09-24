---
id: 3540
title: Treat agent-authored content in artifacts as untrusted input and escape it at render
type: ENH
priority: P1
status: open
discovered_date: '2026-09-23'
labels:
- security
- artifacts
---

# Treat agent-authored content in artifacts as untrusted input and escape it at render

## Summary

The single-file artifact work embeds filtered `history.db` content — model
output and tool output — into a page an operator then opens in a browser. That
content was produced by a session with internet access and a tool loop, which
makes it untrusted input in the ordinary security sense: a page the agent
visited can influence what the agent said, and rendering that text as markup
converts a prompt injection into stored XSS against whoever reads the
transcript. The artifact is also the one output designed to be shared, so the
reader is frequently not the person who ran the session.

Escape all agent-authored and tool-authored strings at the render boundary
rather than trusting the store, and pin the rule with tests that feed
known-hostile payloads through the export path. Decide explicitly which
fields, if any, are allowed to carry markup, and make that an allowlist rather
than a default.

The companion rule is smaller and worth fixing at the same time: any write
into a directory the agent controls must unlink the destination first, or the
write follows a symlink the agent was persuaded to plant.

## Background

Sandboxed-agent-harness research states the principle directly: model output
stored in session transcripts is **durable untrusted content** from a sandbox
that browses the open internet — "a page the agent visits can tell it what to
say" — so rendering it as markup turns prompt injection into stored XSS
against the operator reading the transcript. The existing principle that our
own append-only logs are untrusted input applies with higher stakes here:
on the rendering surface the consequence is code execution in a reader's
browser rather than a corrupted metric. Sibling boundaries govern what data
may be embedded (the SQL exposure boundary; the embedding allowlist) — this
issue governs what happens to the data once it is embedded.

## Scope

1. Audit the artifact export/render path for every site where transcript
   strings (model output, tool output, metadata derived from them) are
   interpolated into the emitted HTML, and escape at the render boundary.
2. Build a markup allowlist: enumerate the fields, if any, permitted to carry
   markup; everything not on the allowlist is escaped. The allowlist is
   explicit data, not an implicit default.
3. Pin the rule with deterministic tests feeding known-hostile payloads
   (script tags, event-handler attributes, javascript: URLs, crafted
   metadata) through the export path and asserting on the emitted artifact.
4. Apply the unlink-before-write rule to any code path that writes into a
   directory an agent can influence: unlink the destination first so a
   planted symlink is followed never.

## Acceptance Criteria

- [ ] Every transcript-derived string in the exported artifact is escaped at
      render unless it is on an explicit markup allowlist.
- [ ] Hostile-payload tests cover the export path (script injection,
      attribute injection, URL schemes, metadata-sourced payloads) and gate
      in the deterministic test tier.
- [ ] Writes into agent-controlled directories unlink the destination first;
      a test demonstrates the planted-symlink case is refused.
- [ ] The markup allowlist is documented in the artifact module (which
      fields carry markup and why).
