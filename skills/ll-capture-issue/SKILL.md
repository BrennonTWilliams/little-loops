---
name: ll-capture-issue
description: Use when asked to capture or create an issue from conversation or natural language.
args: "[description] [--quick] [--parent EPIC-NNN]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ll-issues:*, git:*)
  - Bash(ll-session:*)
metadata:
  short-description: Use when asked to capture or create an issue from conversation or natural langua
---

# Capture Issue

Bridged from `skills/capture-issue/SKILL.md` for Codex Skills API discovery.
See the source skill file for the full prompt body.
