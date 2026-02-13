# ENH-371: Add description and statusMessage fields to hooks.json - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P5-ENH-371-add-description-and-statusmessage-to-hooks-json.md`
- **Type**: enhancement
- **Priority**: P5
- **Action**: improve

## Current State Analysis

`hooks/hooks.json` defines 6 hook events with only the required fields (`type`, `command`, `timeout`) and optional `matcher`. The hooks reference documents three optional metadata fields that are not present:

1. **Top-level `description`** — shown in `/hooks` menu to identify the plugin (ref: `hooks-reference.md:310-311`)
2. **Per-handler `statusMessage`** — custom spinner text while hook runs (ref: `hooks-reference.md:256`)
3. **Per-handler `once`** — runs only once per session, skills only (ref: `hooks-reference.md:257`)

### Key Discoveries
- `hooks/hooks.json:1-74` — 6 hooks, no metadata fields
- `hooks-reference.md:310-332` — canonical example with top-level `description`
- `hooks-reference.md:249-257` — `statusMessage` and `once` documented as common handler fields
- Issue ENH-371 provides suggested `statusMessage` values for all 6 hooks

## Desired End State

`hooks/hooks.json` includes:
1. A top-level `"description"` field as a sibling to `"hooks"`
2. A `"statusMessage"` field on each of the 6 hook handlers
3. `"once"` field evaluated and skipped (not applicable — all hooks are per-event)

### How to Verify
- JSON is valid (parse with `python -c "import json; json.load(open('hooks/hooks.json'))"`)
- Top-level `description` field present
- All 6 handlers have `statusMessage`
- No behavioral changes to hook execution

## What We're NOT Doing

- Not changing hook behavior or scripts
- Not adding new hooks or modifying existing matchers/commands/timeouts
- Not adding `once: true` to any hook (none are one-time initialization)
- Not restructuring hooks.json format

## Solution Approach

Single-file edit to `hooks/hooks.json`:
1. Add `"description": "little-loops development workflow hooks"` as the first field
2. Add `"statusMessage"` to each handler using the values from the issue

## Implementation Phases

### Phase 1: Update hooks.json

#### Overview
Add the `description` and `statusMessage` fields to hooks.json.

#### Changes Required

**File**: `hooks/hooks.json`

The updated file should be:

```json
{
  "description": "little-loops development workflow hooks",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-start.sh",
            "timeout": 5,
            "statusMessage": "Loading ll config..."
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh",
            "timeout": 3,
            "statusMessage": "Checking prompt..."
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-duplicate-issue-id.sh",
            "timeout": 5,
            "statusMessage": "Checking for duplicate issue IDs..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-monitor.sh",
            "timeout": 5,
            "statusMessage": "Monitoring context usage..."
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-cleanup.sh",
            "timeout": 15,
            "statusMessage": "Cleaning up session..."
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/precompact-state.sh",
            "timeout": 5,
            "statusMessage": "Preserving task state..."
          }
        ]
      }
    ]
  }
}
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON is valid: `python -c "import json; json.load(open('hooks/hooks.json'))"`
- [ ] Top-level `description` field present: `python -c "import json; d=json.load(open('hooks/hooks.json')); assert 'description' in d"`
- [ ] All 6 handlers have `statusMessage`: `python -c "import json; d=json.load(open('hooks/hooks.json')); [assert any('statusMessage' in h for h in mg['hooks']) for event in d['hooks'].values() for mg in event]"`

## Testing Strategy

- JSON validation (automated)
- Field presence checks (automated)
- No unit tests needed — metadata-only change with no behavioral impact

## `once` Field Evaluation

All 6 current hooks fire on every occurrence of their event:
- **SessionStart**: Runs on every session start (startup, resume, clear, compact)
- **UserPromptSubmit**: Runs on every user prompt
- **PreToolUse**: Runs on every Write/Edit tool use
- **PostToolUse**: Runs on every tool completion
- **Stop**: Runs on every session stop
- **PreCompact**: Runs on every compaction

None are one-time initialization hooks. Additionally, `once` is documented as "Skills only, not agents" and these are plugin hooks. Therefore, `once` is not applicable to any current hook.

## References

- Issue: `.issues/enhancements/P5-ENH-371-add-description-and-statusmessage-to-hooks-json.md`
- Hooks reference: `docs/claude-code/hooks-reference.md:249-257, 310-332`
- Current hooks: `hooks/hooks.json:1-74`
