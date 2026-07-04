---
name: ll-loop-suggester
description: |
  Analyze user message history to suggest FSM loop configurations automatically. Uses ll-messages output to identify repeated workflows and generate ready-to-use loop YAML. Also supports --from-commands mode to suggest loops from the available command/skill catalog without requiring message history, and --from-sequences mode to suggest loops from ll-logs sequences n-gram output.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow", "create loop from messages", "analyze messages for loops", "ll-messages loop", "suggest automation", "detect patterns for loops", "suggest loops from commands", "loop from catalog", "from-commands", "suggest loops from sequences", "from-sequences", "loop from ll-logs"
argument-hint: "[messages.jsonl|--from-commands|--from-sequences]"
disable-model-invocation: true
metadata:
  short-description: Suggest FSM loops from message history, command catalog, or sequences.
---

# Loop Suggester

Bridged from `commands/loop-suggester.md` for Codex Skills API discovery.
See the source command file for the full prompt body.
