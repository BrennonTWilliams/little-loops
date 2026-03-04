---
id: ENH-562
type: ENH
priority: P3
title: "Add dual confidence thresholds (readiness + outcome) to config"
status: completed
created: 2026-03-03
completed: 2026-03-03
confidence_score: 95
outcome_confidence: 90
related_issues: []
---

# ENH-562: Add dual confidence thresholds (readiness + outcome) to config

## Problem

The `/ll:confidence-check` skill produces two distinct scores per issue — `confidence_score` (readiness, 0-100) and `outcome_confidence` (0-100) — but `ll-config.json` only had a single `commands.confidence_gate.threshold` field. There was no way to independently tune the gate for each score, and the field name gave no indication of which score it applied to.

## Solution

Replaced the single `threshold` field with two named thresholds in `commands.confidence_gate`:

- `readiness_threshold` (default: 85) — gates on `confidence_score`
- `outcome_threshold` (default: 70) — gates on `outcome_confidence`

Plumbed both thresholds through config schema, project config, `/ll:configure`, and `/ll:init`.

## Changes

| File | Change |
|------|--------|
| `config-schema.json` | Removed `threshold`; added `readiness_threshold` (default 85) and `outcome_threshold` (default 70) in `commands.confidence_gate` |
| `.claude/ll-config.json` | Added `commands.confidence_gate` with `enabled: false`, `readiness_threshold: 85`, `outcome_threshold: 70` |
| `skills/configure/areas.md` | Split single threshold question into two questions (readiness + outcome) |
| `skills/configure/show-output.md` | Added `## commands --show` section displaying both thresholds |
| `skills/init/interactive.md` | Updated Round 5 ACTIVE count (+2 for confidence gate), renamed `gate_threshold` → `gate_readiness` + `gate_outcome` (items 9–10), renumbered 11–12, added two-question prompts in 5b/5c, updated config output and notes |

## Verification

- `ll-config.json` validates cleanly against updated `config-schema.json`
- Both threshold fields visible in `/ll:configure --show commands`
- `/ll:init` Round 5 asks for readiness threshold and outcome threshold separately when "Confidence gate" is selected
