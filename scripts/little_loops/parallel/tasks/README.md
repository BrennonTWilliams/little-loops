# Parallel Task Definitions

This directory contains example task definitions for the parallel processing system.

## Task Definition Schema

Each task file follows a consistent YAML schema:

```yaml
name: task-name
description: |
  Multi-line description of what this task does.

version: "1.0"

workers:
  count: 4                  # Number of parallel workers
  timeout: 300              # Per-worker timeout (seconds)
  retry:
    enabled: true
    max_attempts: 2
    delay: 5

inputs:
  option_name:
    type: string|boolean|array
    default: value
    description: What this option does

subtasks:
  - id: subtask-id
    name: Human-readable Name
    description: What this subtask does
    priority: 1             # Lower = runs first
    command: |
      shell commands here
    on_failure: continue    # continue | stop_all
```

## Available Tasks

| Task | Description | Workers |
|------|-------------|---------|
| `lint-all` | Parallel linting (Python, TS/JS, CSS) | 3 |
| `test-suite` | Parallel test execution by module | 4 |
| `build-assets` | Parallel asset compilation | 4 |
| `health-check` | Parallel service health checks | 8 |

## Usage Examples

```bash
# Run a task with defaults
br-task run lint-all

# Run with options
br-task run test-suite --coverage --workers 6

# Dry run (preview only)
br-task run build-assets --dry-run

# Run specific subtasks
br-task run lint-all --only "python-lint,typescript-lint"
```

## Configuration Reference

### Worker Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `count` | int | 2 | Number of parallel workers |
| `timeout` | int | 300 | Per-worker timeout (seconds) |
| `isolation` | string | process | process, thread, or worktree |
| `memory_limit` | string | - | Memory limit per worker |

### Retry Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | false | Enable retry on failure |
| `max_attempts` | int | 2 | Maximum retry attempts |
| `delay` | int | 5 | Delay between retries (seconds) |
| `backoff` | string | linear | linear or exponential |

### Subtask Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique subtask identifier |
| `name` | string | yes | Human-readable name |
| `command` | string | yes | Shell command to execute |
| `priority` | int | no | Execution priority (lower first) |
| `on_failure` | string | no | continue or stop_all |
| `file_patterns` | array | no | Glob patterns for file matching |
| `outputs` | array | no | Expected output files |
| `environment` | object | no | Environment variables |

## Template Syntax

Task definitions support Handlebars-style templating:

```yaml
# Conditionals
{{#if inputs.verbose}}-v{{/if}}

# Comparisons
{{#if (eq inputs.mode "production")}}--minify{{/if}}

# Array joining
{{inputs.paths | join " "}}

# Variable substitution
{{environments[inputs.environment].base_url}}
```

## Creating Custom Tasks

1. Create a new `.yaml` file in this directory
2. Follow the schema shown above
3. Test with `br-task run your-task --dry-run`
4. Add to version control

See the example tasks for comprehensive patterns and best practices.
