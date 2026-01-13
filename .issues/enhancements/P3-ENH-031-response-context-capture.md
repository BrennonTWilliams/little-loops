---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T12:00:00Z
---

# ENH-031: Response Context Capture

## Summary

Enhance `ll-messages` extraction to capture response metadata from assistant turns, enabling file-based workflow tracking, completion detection, and tool usage analysis.

## Motivation

Current message extraction (FEAT-011) captures only user messages. The assistant's responses contain critical workflow information:

- **Files actually modified**: Track which files were edited, not just mentioned
- **Tools used**: Understand tool usage patterns
- **Completion status**: Detect success vs failure vs abandonment
- **Follow-up suggestions**: What did the assistant recommend next?

Without this data, workflow analysis cannot:
- Cluster messages by files they affected (not just mentioned)
- Detect workflow completion vs abandonment
- Analyze error recovery patterns
- Track implicit workflow linking via shared file modifications

## Proposed Implementation

### 1. Enhanced JSONL Schema

Add `response_metadata` field to extracted messages:

```json
{
  "content": "Remove all references to champion-insights.md",
  "timestamp": "2026-01-12T07:13:56.678Z",
  "session_id": "abc-123",
  "uuid": "msg-007",
  "cwd": "/Users/brennon/project",
  "git_branch": "main",
  "is_sidechain": false,
  "entities": ["champion-insights.md"],

  "response_metadata": {
    "tools_used": [
      {"tool": "Grep", "count": 1},
      {"tool": "Edit", "count": 4}
    ],
    "files_read": [
      "README.md",
      "config.json"
    ],
    "files_modified": [
      "src/auth.py",
      "src/login.py",
      "tests/test_auth.py"
    ],
    "completion_status": "success",
    "error_message": null,
    "follow_up_suggested": "commit changes"
  }
}
```

### 2. Response Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `tools_used` | `list[{tool, count}]` | Tools invoked in response |
| `files_read` | `list[str]` | Files read via Read tool |
| `files_modified` | `list[str]` | Files modified via Edit/Write |
| `completion_status` | `string` | "success", "failure", "partial" |
| `error_message` | `string?` | Error text if failed |
| `follow_up_suggested` | `string?` | Detected next action suggestion |

### 3. Parsing Requirements

Modify `scripts/little_loops/messages.py` to:

1. **Parse full conversation turns**:
   ```python
   def extract_messages_with_responses(
       project_folder: Path,
       include_response_context: bool = False,
   ) -> list[UserMessage]:
       """Extract user messages with optional response metadata."""

       for entry in parse_jsonl(session_file):
           if entry["type"] == "user":
               msg = parse_user_message(entry)

               if include_response_context:
                   # Find the corresponding assistant response
                   response = find_assistant_response(entry["uuid"], session_data)
                   if response:
                       msg.response_metadata = extract_response_metadata(response)

               yield msg
   ```

2. **Extract tool usage from assistant responses**:
   ```python
   def extract_response_metadata(response: dict) -> ResponseMetadata:
       """Extract metadata from assistant response."""

       tools_used = []
       files_read = []
       files_modified = []

       # Parse tool_use blocks in response content
       for block in response.get("message", {}).get("content", []):
           if block.get("type") == "tool_use":
               tool_name = block.get("name")
               tools_used.append(tool_name)

               # Extract file paths from tool inputs
               if tool_name == "Read":
                   files_read.append(block["input"]["file_path"])
               elif tool_name in ("Edit", "Write"):
                   files_modified.append(block["input"]["file_path"])

       return ResponseMetadata(
           tools_used=Counter(tools_used),
           files_read=files_read,
           files_modified=files_modified,
           completion_status=detect_completion_status(response),
           error_message=detect_error(response),
           follow_up_suggested=detect_follow_up(response),
       )
   ```

3. **Detect completion status**:
   ```python
   def detect_completion_status(response: dict) -> str:
       """Detect if the request was completed successfully."""

       content = response.get("message", {}).get("content", "")
       text = extract_text_content(content)

       # Check for error indicators
       if any(err in text.lower() for err in ["error", "failed", "couldn't", "unable to"]):
           return "failure"

       # Check for partial completion
       if any(partial in text.lower() for partial in ["partially", "some of", "not all"]):
           return "partial"

       return "success"
   ```

### 4. CLI Enhancement

Add `--include-response-context` flag:

```bash
# Extract with response context (slower, more data)
ll-messages extract --include-response-context

# Default: user messages only (faster)
ll-messages extract
```

### 5. Benefits for Workflow Analysis

| Analysis Capability | Enabled By |
|---------------------|------------|
| File-based workflow clustering | `files_modified` field |
| Workflow completion detection | `completion_status` field |
| Tool usage patterns | `tools_used` field |
| Error recovery workflows | `error_message` + subsequent messages |
| Implicit workflow linking | Same files modified across sessions |

### 6. File-Based Clustering Example

With response context, FEAT-013 can cluster by files modified:

```yaml
file_workflows:
  - file: "src/auth.py"
    modifications:
      - msg_uuid: "msg-007"
        action: "Add error handling"
        timestamp: "2026-01-12T07:13:56Z"
        tools: ["Edit"]
      - msg_uuid: "msg-015"
        action: "Fix null check"
        timestamp: "2026-01-12T08:45:12Z"
        tools: ["Edit"]
      - msg_uuid: "msg-023"
        action: "Add type hints"
        timestamp: "2026-01-12T09:30:00Z"
        tools: ["Edit"]
    total_modifications: 3
    workflow_inference: "auth.py refactoring"
```

### 7. Privacy Considerations

- File paths may contain sensitive information
- Consider path normalization (relative paths only)
- Add `--redact-paths` option to mask full paths
- Default to user messages only; response context is opt-in

## Location

| Component | Path |
|-----------|------|
| Module | `scripts/little_loops/messages.py` (enhance) |
| CLI | `scripts/little_loops/messages_cli.py` (add flag) |
| Tests | `scripts/tests/test_messages.py` (add response tests) |

## Current Behavior

`ll-messages extract` captures only user messages. No response context is captured.

## Expected Behavior

```bash
# Extract with response context
$ ll-messages extract --include-response-context -n 50
Extracted 50 messages with response context to .claude/user-messages-20260112.jsonl

# View response metadata
$ head -1 .claude/user-messages-20260112.jsonl | jq .response_metadata
{
  "tools_used": [{"tool": "Edit", "count": 3}],
  "files_modified": ["src/auth.py", "src/login.py"],
  "completion_status": "success"
}
```

## Impact

- **Severity**: Medium - Enables file-based workflow tracking
- **Effort**: Medium - Requires parsing assistant responses
- **Risk**: Low - Read-only, opt-in feature

## Dependencies

Requires access to Claude Code conversation logs that include assistant responses.

## Blocked By

- FEAT-011: User Message History Extraction (base extraction)
- FEAT-029: `/ll:analyze-workflows` Command (implement base pipeline first)

## Blocks

None. This is an enhancement to improve analysis accuracy.

## Labels

`enhancement`, `cli-tool`, `workflow-analysis`, `response-parsing`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P3
