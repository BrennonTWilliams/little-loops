---
description: |
  Capture issues from conversation context or natural language descriptions. Supports duplicate detection, reopening completed issues, and batch capture from conversation analysis.

  Trigger keywords: "capture issue", "create issue", "log issue", "record bug", "save this as issue", "capture this bug", "track this problem", "note this enhancement", "add to issues"
---

# Capture Issue Skill

This skill detects when users want to capture issues and invokes the `/ll:capture_issue` command.

## When to Activate

Proactively offer or invoke this skill when the user:
- Mentions bugs, problems, or issues they want to track
- Says things like "we should add..." or "it would be better if..."
- Identifies something that needs to be fixed or improved
- Wants to record a feature idea or enhancement
- Asks to "capture this", "log this", or "save this as an issue"

## How to Use

When this skill activates, invoke the command:

```
/ll:capture_issue [description]
```

### With a Description

If the user provides a clear description of the issue, pass it as an argument:

```
/ll:capture_issue "The login button doesn't respond on mobile Safari"
```

### Without a Description (Conversation Mode)

If the user wants to capture issues from the conversation, invoke without arguments:

```
/ll:capture_issue
```

This analyzes the conversation to identify potential issues and presents them for selection.

## Examples

| User Says | Action |
|-----------|--------|
| "This button is broken, let's track it" | `/ll:capture_issue "Button is broken"` |
| "We should add dark mode" | `/ll:capture_issue "Add dark mode support"` |
| "Can you capture the issues we discussed?" | `/ll:capture_issue` |
| "Log this as a bug" | `/ll:capture_issue "[context from conversation]"` |

## Integration

After capturing issues:
- Review with `cat [issue-path]`
- Validate with `/ll:ready_issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage_issue`
