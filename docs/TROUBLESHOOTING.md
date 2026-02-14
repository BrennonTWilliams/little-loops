# Troubleshooting Guide

Common issues and solutions for little-loops.

## Quick Reference

- [Configuration Issues](#configuration-issues)
- [Git Worktree Problems](#git-worktree-problems)
- [Claude CLI Issues](#claude-cli-issues)
- [State Management](#state-management)
- [Session Handoff](#session-handoff)
- [Priority and Filtering](#priority-and-filtering)
- [Merge Conflicts](#merge-conflicts)
- [Slash Command Issues](#slash-command-issues)
- [Hook Debugging](#hook-debugging)
- [Diagnostic Commands](#diagnostic-commands)

---

## Configuration Issues

### Config file not found

**Symptom**: Commands use default values instead of project config

**Cause**: Missing or mislocated `.claude/ll-config.json`

**Solution**:
1. Run `/ll:init` to create config
2. Verify path is `.claude/ll-config.json` (not project root)
3. Check file permissions

```bash
# Verify config exists
ls -la .claude/ll-config.json
```

### Invalid JSON in config

**Symptom**: `JSONDecodeError` on startup

**Cause**: Malformed JSON syntax

**Solution**:
1. Validate JSON syntax:
   ```bash
   python -m json.tool .claude/ll-config.json
   ```
2. Common fixes:
   - Remove trailing commas after last items
   - Ensure all strings use double quotes
   - Check for missing closing braces

### Type commands not running

**Symptom**: `type_cmd` ignored or errors

**Cause**: Tool not installed or set to wrong value

**Solution**:
1. Install the type checker:
   ```bash
   pip install mypy  # For Python
   npm install -g typescript  # For TypeScript
   ```
2. Set `"type_cmd": null` to disable type checking
3. Verify command works standalone:
   ```bash
   mypy src/
   ```

### Config values not substituting

**Symptom**: `{{config.project.src_dir}}` appears literally in output

**Cause**: Variable path doesn't match config structure

**Solution**:
1. Check available paths with:
   ```python
   from little_loops.config import BRConfig
   from pathlib import Path
   c = BRConfig(Path.cwd())
   print(c.to_dict())
   ```
2. Use correct path (e.g., `config.project.src_dir` not `config.src_dir`)

---

## Git Worktree Problems

### Worktree creation fails

**Symptom**: "Failed to create worktree" or "fatal: ... already exists" in ll-parallel

**Cause**: Branch already exists, or worktree directory locked

**Solution**:
1. Clean up stale worktrees:
   ```bash
   ll-parallel --cleanup
   ```
2. Delete orphaned branches:
   ```bash
   git branch -D $(git branch | grep 'parallel/')
   ```
3. Remove leftover directories:
   ```bash
   rm -rf .worktrees/
   git worktree prune
   ```

### Worktree permission denied

**Symptom**: Cannot write to worktree directory

**Cause**: Previous process left locks or wrong permissions

**Solution**:
```bash
# Remove worktrees directory
rm -rf .worktrees/

# Prune git's worktree tracking
git worktree prune

# Verify cleanup
git worktree list
```

### Worktree not inheriting settings

**Symptom**: Claude uses wrong model or settings in worktree

**Cause**: `.claude/settings.local.json` not present or not copied

**Solution**:
1. Ensure main repo has `.claude/settings.local.json`
2. The worktree should inherit this automatically
3. Check worktree has access:
   ```bash
   cat .worktrees/worker-1/.claude/settings.local.json
   ```

### Too many worktrees

**Symptom**: Disk space issues or "too many open files"

**Cause**: Worktrees not cleaned up after runs

**Solution**:
```bash
# List all worktrees
git worktree list

# Clean up all worktrees
ll-parallel --cleanup

# Or manually
git worktree remove .worktrees/worker-1 --force
git worktree prune
```

---

## Claude CLI Issues

### Command not found: claude

**Symptom**: `FileNotFoundError` or "claude: command not found"

**Cause**: Claude CLI not installed or not in PATH

**Solution**:
1. Install Claude CLI:
   ```bash
   npm install -g @anthropic-ai/claude-cli
   ```
2. Verify installation:
   ```bash
   which claude
   claude --version
   ```
3. Check PATH includes npm global bin directory

### Claude exits with returncode 1

**Symptom**: Commands fail but no clear error message

**Cause**: Various - permission, timeout, API issues

**Solution**:
1. Run command manually to see full output:
   ```bash
   claude -p "/ll:ready-issue BUG-001"
   ```
2. Check if `--dangerously-skip-permissions` is working
3. Verify API key/authentication status:
   ```bash
   claude --auth-status
   ```

### Timeout during issue processing

**Symptom**: Issue processing stops after timeout_seconds

**Cause**: Complex issues or slow API responses

**Solution**:
1. Increase timeout in config:
   ```json
   {
     "automation": {
       "timeout_seconds": 7200
     }
   }
   ```
2. For parallel mode:
   ```json
   {
     "parallel": {
       "timeout_per_issue": 7200
     }
   }
   ```
3. Use CLI flag: `ll-auto --timeout 7200`

### Permission denied errors

**Symptom**: Claude refuses to execute commands

**Cause**: Missing `--dangerously-skip-permissions` or permission not granted

**Solution**:
1. The CLI tools add this flag automatically
2. For manual runs, add the flag explicitly
3. Check Claude Code permissions in your IDE settings

---

## State Management

### State file corruption

**Symptom**: `JSONDecodeError` when resuming

**Cause**: Interrupted during state save (power loss, kill -9, etc.)

**Solution**:
1. Delete the corrupted state file:
   ```bash
   # For sequential mode
   rm .auto-manage-state.json

   # For parallel mode
   rm .parallel-manage-state.json
   ```
2. Restart without `--resume`

### Resume not working

**Symptom**: Reprocesses already-completed issues

**Cause**: State file deleted, wrong path, or different mode

**Solution**:
1. Check `automation.state_file` in config
2. Verify file exists before using `--resume`:
   ```bash
   ls -la .auto-manage-state.json
   ```
3. Ensure you're using the same mode (sequential vs parallel)

### Issues stuck in "attempted" state

**Symptom**: Issues skipped on future runs but not in completed

**Cause**: Issue failed but not recorded in failed_issues

**Solution**:
1. View current state:
   ```bash
   cat .auto-manage-state.json | python -m json.tool
   ```
2. Edit state file to remove from `attempted_issues`:
   ```bash
   # Or just delete and restart
   rm .auto-manage-state.json
   ```

### State file location confusion

**Symptom**: Can't find state file or using wrong one

**Cause**: Different state files for different modes

**Solution**:
| Mode | Default State File |
|------|-------------------|
| Sequential (ll-auto) | `.auto-manage-state.json` |
| Parallel (ll-parallel) | `.parallel-manage-state.json` |

Check your config for custom paths:
```bash
grep state_file .claude/ll-config.json
```

---

## Session Handoff

### Context monitor not triggering

**Symptom**: No warnings appear when context fills up

**Cause**: Context monitoring is disabled by default

**Solution**:
1. Enable in `.claude/ll-config.json`:
   ```json
   {
     "context_monitor": {
       "enabled": true,
       "auto_handoff_threshold": 80
     }
   }
   ```
2. Verify `jq` is installed (required for the hook):
   ```bash
   which jq
   ```
3. Check state file is being updated:
   ```bash
   cat .claude/ll-context-state.json
   ```

### Reminders keep appearing after handoff

**Symptom**: "[ll] Context ~X% used" keeps showing after running `/ll:handoff`

**Cause**: Handoff file modification time not detected correctly

**Solution**:
1. Verify the file was created/modified:
   ```bash
   ls -la .claude/ll-continue-prompt.md
   ```
2. Check `handoff_complete` in state file:
   ```bash
   cat .claude/ll-context-state.json | jq '.handoff_complete'
   ```
3. Manually mark complete if needed:
   ```bash
   # Edit .claude/ll-context-state.json and set "handoff_complete": true
   ```

### Resume shows stale prompt

**Symptom**: Warning about prompt being N hours old

**Cause**: Continuation prompt older than `prompt_expiry_hours` (default: 24)

**Solution**:
1. Generate fresh prompt: `/ll:handoff`
2. Increase expiry in config:
   ```json
   {
     "continuation": {
       "prompt_expiry_hours": 72
     }
   }
   ```
3. Stale prompts are still usable - the warning is informational

### No continuation prompt found

**Symptom**: `/ll:resume` says "No continuation state found"

**Cause**: Handoff was never run or file deleted

**Solution**:
1. Run `/ll:handoff` to create the prompt
2. Check file location:
   ```bash
   ls -la .claude/ll-continue-prompt.md
   ```
3. Check session state file:
   ```bash
   cat .claude/ll-session-state.json 2>/dev/null || echo "No session state"
   ```

### Automation not detecting handoff signal

**Symptom**: `ll-auto` or `ll-parallel` not spawning continuation sessions

**Cause**: Signal not in expected format or detection pattern mismatch

**Solution**:
1. Verify `/ll:handoff` outputs the signal:
   ```
   CONTEXT_HANDOFF: Ready for fresh session
   ```
2. Check logs for detection:
   ```bash
   # Look for "Detected CONTEXT_HANDOFF signal" in output
   ```
3. Verify continuation prompt exists in worktree:
   ```bash
   cat .worktrees/worker-1/.claude/ll-continue-prompt.md
   ```

### Max continuations reached

**Symptom**: "Reached max continuations (3), stopping"

**Cause**: Issue required more than 3 session restarts

**Solution**:
1. Increase limit in config:
   ```json
   {
     "continuation": {
       "max_continuations": 5
     }
   }
   ```
2. Consider splitting the issue into smaller tasks
3. Check if issue is stuck in a loop (repeated handoffs without progress)

### Claude not seeing context warnings in non-interactive mode

**Symptom**: ll-auto or ll-parallel exhausts context without triggering handoff

**Cause**: The context-monitor.sh hook must use exit code 2 with stderr to send feedback to Claude in non-interactive mode

**Verification**:
1. Check the hook uses `exit 2` and `>&2`:
   ```bash
   grep -A2 "exit 2" hooks/scripts/context-monitor.sh
   ```
2. Look for hook output in Claude logs showing the warning was received

**Reference**: GitHub issue #11224 documents PostToolUse hook behavior - exit code 2 with stderr is required for feedback to reach Claude

### Token estimation seems wrong

**Symptom**: Threshold triggers too early or too late

**Cause**: Default weights may not match your usage patterns

**Solution**:
1. Adjust estimation weights:
   ```json
   {
     "context_monitor": {
       "estimate_weights": {
         "read_per_line": 10,
         "tool_call_base": 100,
         "bash_output_per_char": 0.3
       },
       "context_limit_estimate": 150000
     }
   }
   ```

2. **Tool-specific costs** (hardcoded in `hooks/scripts/context-monitor.sh`):

   | Tool | Cost | Formula |
   |------|------|---------|
   | `Read` | 10 per line | `lines × read_per_line` |
   | `Grep` | 5 per line | `output_lines × 5` |
   | `Glob` | 20 per file | `file_count × 20` |
   | `Bash` | 0.3 per char | `chars × bash_output_per_char` |
   | `Write`/`Edit` | 300 | `tool_call_base × 3` |
   | `Task` | 2000 | Fixed overhead |
   | `WebFetch` | 1500 | Fixed overhead |
   | `WebSearch` | 1000 | Fixed overhead |

3. Increase threshold for later warnings: `"auto_handoff_threshold": 85`
4. Check token breakdown in state file:
   ```bash
   cat .claude/ll-context-state.json | jq '.breakdown'
   ```
5. For custom tuning, edit `hooks/scripts/context-monitor.sh` lines 56-118

For comprehensive documentation, see [Session Handoff Guide](SESSION_HANDOFF.md).

---

## Priority and Filtering

### Priority filter not working

**Symptom**: Wrong priority issues processed or issues skipped

**Cause**: Filename doesn't match pattern `P[0-5]-*`

**Solution**:
1. Verify filename format: `P1-BUG-001-description.md`
2. Priority must be at the start of filename
3. Check `issues.priorities` in config matches your prefixes:
   ```json
   {
     "issues": {
       "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"]
     }
   }
   ```

### Category filtering wrong

**Symptom**: `--category` flag processes wrong issue type

**Cause**: Category name mismatch with config

**Solution**:
1. Use category keys from config: `"bugs"`, `"features"`, `"enhancements"`
2. Not the directory name or prefix
3. Check available categories:
   ```python
   from little_loops.config import BRConfig
   from pathlib import Path
   print(BRConfig(Path.cwd()).issue_categories)
   ```

### No issues found

**Symptom**: "No issues to process" but issues exist

**Cause**: Wrong base_dir, category config, or file extension

**Solution**:
1. Check issue directory exists:
   ```bash
   ls -la .issues/bugs/
   ```
2. Verify files have `.md` extension
3. Check config `issues.base_dir` matches actual location
4. Run diagnostic:
   ```python
   from little_loops.issue_parser import find_issues
   from little_loops.config import BRConfig
   from pathlib import Path
   issues = find_issues(BRConfig(Path.cwd()))
   print(f"Found {len(issues)} issues")
   for i in issues[:5]:
       print(f"  {i.issue_id}: {i.title}")
   ```

---

## Merge Conflicts

### Merge fails repeatedly

**Symptom**: "Merge conflict after N retries"

**Cause**: Parallel workers modified same files

**Solution**:
1. Reduce workers temporarily:
   ```bash
   ll-parallel --workers 1
   ```
2. Prioritize issues to avoid overlapping changes
3. Increase retry limit:
   ```json
   {
     "parallel": {
       "max_merge_retries": 5
     }
   }
   ```

### Local changes blocking merge

**Symptom**: "Your local changes would be overwritten"

**Cause**: Uncommitted changes in main repo

**Solution**:
1. Commit or stash changes before running:
   ```bash
   git stash
   ll-parallel
   git stash pop
   ```
2. Recent versions auto-stash, but verify:
   ```bash
   git stash list
   ```

### Branch not found after merge

**Symptom**: Cleanup errors for already-deleted branch

**Cause**: Branch already deleted by previous cleanup

**Solution**:
- Safe to ignore - cleanup is idempotent
- Verify branches:
  ```bash
  git branch -a | grep parallel/
  ```

### Rebase conflicts during merge

**Symptom**: Merge coordinator reports rebase failure

**Cause**: Conflicting changes between workers

**Solution**:
1. The coordinator will retry automatically
2. If persists, check which files conflict:
   ```bash
   git diff --name-only HEAD...parallel/BUG-001-branch
   ```
3. Consider processing conflicting issues sequentially

---

## Slash Command Issues

### Command not found

**Symptom**: `/ll:command_name` not recognized

**Cause**: Plugin not installed or wrong prefix

**Solution**:
1. Verify plugin is installed:
   ```bash
   cat .claude/settings.local.json | grep enabledPlugins
   ```
2. Check prefix is `ll:` not `br:` (old prefix)
3. Run `/ll:help` to see available commands

### Command uses wrong config values

**Symptom**: Command runs with default instead of project values

**Cause**: Config not loaded or variable path wrong

**Solution**:
1. Check config file exists and is valid JSON
2. Verify variable paths in command templates
3. Test config loading:
   ```python
   from little_loops.config import BRConfig
   from pathlib import Path
   c = BRConfig(Path.cwd())
   print(c.project.test_cmd)  # Should show your config value
   ```

### ready-issue always returns NOT_READY

**Symptom**: All issues fail validation

**Cause**: Issue file format doesn't match expected structure

**Solution**:
1. Check issue file has required sections
2. Verify title format: `# ISSUE-ID: Title`
3. Ensure issue describes a concrete, actionable task
4. Run manually to see full output:
   ```bash
   claude -p "/ll:ready-issue BUG-001"
   ```

### manage-issue completes but no changes

**Symptom**: Issue marked complete but code unchanged

**Cause**: Issue was deemed already fixed or invalid

**Solution**:
1. Check issue moved to `completed/` directory
2. Look for closure notes in the file
3. Review git log for any commits
4. Run with verbose output to see reasoning

---

## Hook Debugging

### Hook not executing

**Symptom**: Expected hook behavior not occurring (context warnings, duplicate checks, etc.)

**Cause**: Hook disabled, missing dependencies, or execution errors

**Solution**:
1. Check hooks are registered in `hooks/hooks.json`
2. Verify hook script is executable:
   ```bash
   chmod +x hooks/scripts/context-monitor.sh
   chmod +x hooks/scripts/check-duplicate-issue-id.sh
   chmod +x hooks/scripts/user-prompt-check.sh
   chmod +x hooks/scripts/precompact-state.sh
   ```
3. Check `jq` is installed (required by most hooks):
   ```bash
   which jq || brew install jq  # macOS
   which jq || apt install jq   # Linux
   ```

### Hook timeout errors

**Symptom**: "Hook exceeded timeout" or hook execution aborted

**Cause**: Lock acquisition timeout or slow file operations

**Solution**:
1. Check for stale lock files:
   ```bash
   find .claude -name "*.lock" -o -name "*.lock.lock"
   rm -rf .claude/*.lock .claude/*.lock.lock
   ```
2. Verify hooks complete quickly (should be <1s normally):
   ```bash
   time bash hooks/scripts/context-monitor.sh < test-input.json
   ```
3. Check hook timeout settings in `hooks/hooks.json`

### State file corruption

**Symptom**: Hook crashes with JSON parse errors

**Cause**: Interrupted write operation or concurrent access bug

**Solution**:
1. Check state file is valid JSON:
   ```bash
   jq empty .claude/ll-context-state.json 2>&1
   jq empty .claude/ll-precompact-state.json 2>&1
   ```
2. Delete corrupted state files (they'll be recreated):
   ```bash
   rm .claude/ll-context-state.json
   rm .claude/ll-precompact-state.json
   ```
3. Verify `atomic_write_json` is being used (check hook scripts source `lib/common.sh`)

### Lock files not cleaned up

**Symptom**: Stale `.lock` files preventing hook execution

**Cause**: Hook process killed before cleanup or trap failure

**Solution**:
1. Remove all lock files:
   ```bash
   # Clean up hook lock files
   rm -rf .claude/.*.lock
   rm -rf .claude/.*.lock.lock
   rm -rf .issues/.*.lock
   rm -rf .issues/.*.lock.lock
   ```
2. Check for hung processes:
   ```bash
   ps aux | grep -E '(context-monitor|check-duplicate|user-prompt-check|precompact)'
   ```
3. Lock files should auto-expire (4s timeout for most hooks)

### Duplicate issue ID not detected

**Symptom**: Multiple issues created with same ID despite hook

**Cause**: Race condition or hook not running on Write tool

**Solution**:
1. Verify hook is registered for PreToolUse:
   ```bash
   grep -A5 "check-duplicate-issue-id" hooks/hooks.json
   ```
2. Test hook manually:
   ```bash
   echo '{"tool_name":"Write","tool_input":{"file_path":".issues/bugs/P2-BUG-001-test.md"}}' | \
     bash hooks/scripts/check-duplicate-issue-id.sh
   ```
3. Check if lock acquisition is timing out (reduce concurrent writes)

### Context monitor not updating

**Symptom**: Token counts not increasing or warnings not appearing

**Cause**: Hook not running, state file issues, or disabled

**Solution**:
1. Enable context monitoring in config:
   ```json
   {
     "context_monitor": {
       "enabled": true
     }
   }
   ```
2. Check state file is updating:
   ```bash
   watch -n 1 'cat .claude/ll-context-state.json | jq .estimated_tokens'
   ```
3. Verify PostToolUse hook is running:
   ```bash
   # Add this to context-monitor.sh temporarily for debugging
   echo "Hook triggered at $(date)" >> /tmp/hook-debug.log
   ```
4. Test hook manually:
   ```bash
   echo '{"tool_name":"Read","tool_response":{"content":"test\n"}}' | \
     bash hooks/scripts/context-monitor.sh
   ```

### User prompt optimization not working

**Symptom**: Prompts not being optimized despite enabled setting

**Cause**: Bypass patterns matching or template file missing

**Solution**:
1. Check prompt doesn't start with bypass prefix (default: `*`):
   ```json
   {
     "prompt_optimization": {
       "bypass_prefix": "*"
     }
   }
   ```
2. Verify template file exists:
   ```bash
   ls -la hooks/prompts/optimize-prompt-hook.md
   ```
3. Test hook with a sample prompt:
   ```bash
   echo '{"prompt":"implement user authentication system"}' | \
     bash hooks/scripts/user-prompt-check.sh
   ```

### Testing individual hooks

**Manual hook testing**:

```bash
# Test context-monitor.sh
echo '{
  "tool_name": "Read",
  "tool_response": {"content": "line1\nline2\nline3\n"}
}' | bash hooks/scripts/context-monitor.sh

# Test check-duplicate-issue-id.sh
echo '{
  "tool_name": "Write",
  "tool_input": {"file_path": ".issues/bugs/P2-BUG-999-test.md"}
}' | bash hooks/scripts/check-duplicate-issue-id.sh

# Test user-prompt-check.sh
echo '{
  "prompt": "add authentication to the app"
}' | bash hooks/scripts/user-prompt-check.sh

# Test precompact-state.sh
echo '{
  "transcript_path": "/tmp/test.jsonl"
}' | bash hooks/scripts/precompact-state.sh
```

### Hook integration tests

Run the full integration test suite:

```bash
# Run all hook integration tests
python -m pytest scripts/tests/test_hooks_integration.py -v

# Run specific test class
python -m pytest scripts/tests/test_hooks_integration.py::TestContextMonitor -v

# Run with detailed output
python -m pytest scripts/tests/test_hooks_integration.py -v -s
```

### Common lock issues

**Symptom**: "Failed to acquire lock" or timeout errors

**Debugging**:
1. Check if `flock` is available:
   ```bash
   which flock || echo "Using mkdir-based fallback locks"
   ```
2. Verify lock timeout settings (in hook scripts):
   - context-monitor.sh: 4s timeout
   - check-duplicate-issue-id.sh: 3s timeout
   - precompact-state.sh: 3s timeout
3. Monitor lock files during operation:
   ```bash
   watch -n 0.1 'find .claude .issues -name "*.lock*" 2>/dev/null'
   ```

### Special character handling

**Symptom**: Prompts with special characters cause errors or injection

**Verification**:
1. Test with special characters:
   ```bash
   echo '{"prompt":"test with $VAR and $(cmd) and & chars"}' | \
     bash hooks/scripts/user-prompt-check.sh
   ```
2. Check for sed usage (should use bash parameter expansion instead):
   ```bash
   grep -n "sed" hooks/scripts/*.sh
   # Should only appear in comments, not active code
   ```
3. Run integration tests:
   ```bash
   python -m pytest scripts/tests/test_hooks_integration.py::TestUserPromptCheck -v
   ```

---

## Diagnostic Commands

These commands use the Python API directly. See [API Reference](API.md) for full documentation.

### Check configuration

Uses [`BRConfig`](API.md#brconfig) to load and display resolved configuration:

```bash
# View resolved config
python -c "
from little_loops.config import BRConfig
from pathlib import Path
import json
c = BRConfig(Path.cwd())
print(json.dumps(c.to_dict(), indent=2))
"
```

### Check issue discovery

Uses [`find_issues()`](API.md#find_issues) to list all discovered issues:

```bash
# List all discovered issues
python -c "
from little_loops.issue_parser import find_issues
from little_loops.config import BRConfig
from pathlib import Path
issues = find_issues(BRConfig(Path.cwd()))
for i in issues:
    print(f'{i.priority} {i.issue_id}: {i.title}')
"
```

### Check worktree status

```bash
# List all worktrees
git worktree list

# List parallel branches
git branch -a | grep parallel/

# Check worktree directory
ls -la .worktrees/
```

### Check state files

```bash
# Sequential state
cat .auto-manage-state.json 2>/dev/null | python -m json.tool || echo "No sequential state"

# Parallel state
cat .parallel-manage-state.json 2>/dev/null | python -m json.tool || echo "No parallel state"
```

### Verify Python package

```bash
# Check installation
pip show little-loops 2>/dev/null || pip show -e . 2>/dev/null

# Check CLI tools
which ll-auto
which ll-parallel

# Check version
python -c "import little_loops; print(little_loops.__file__)"
```

---

## Getting Help

If you're still stuck:

1. Check the [README](../README.md) for basic setup
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for system understanding
3. Check [API.md](API.md) for module details

For persistent issues, create a bug report with:
- Config file (sanitized - remove any secrets)
- Command run and full output
- Git status output
- Python and Claude CLI versions
