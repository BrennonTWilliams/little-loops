# Show Output Formats

This document defines the display format for `--show` mode for each configuration area.

## project --show

```
Project Configuration
---------------------
  name:       {{config.project.name}}
  src_dir:    {{config.project.src_dir}}       (default: src/)
  test_dir:   {{config.project.test_dir}}      (default: tests)
  test_cmd:   {{config.project.test_cmd}}      (default: pytest)
  lint_cmd:   {{config.project.lint_cmd}}      (default: ruff check .)
  type_cmd:   {{config.project.type_cmd}}      (default: mypy)
  format_cmd: {{config.project.format_cmd}}    (default: ruff format .)
  build_cmd:  {{config.project.build_cmd}}     (default: none)
  run_cmd:    {{config.project.run_cmd}}      (default: none)

Edit: /ll:configure project
```

## issues --show

```
Issues Configuration
--------------------
  base_dir:         {{config.issues.base_dir}}          (default: .issues)
  completed_dir:    {{config.issues.completed_dir}}     (default: completed)
  capture_template: {{config.issues.capture_template}}  (default: full)
  templates_dir:    {{config.issues.templates_dir}}     (default: none)
  priorities:       {{config.issues.priorities}}        (default: P0-P5)
  categories:       [bugs, features, enhancements]      (+ any custom)

Edit: /ll:configure issues
```

## parallel --show

```
Parallel Processing Configuration (ll-parallel)
-----------------------------------------------
  max_workers:             {{config.parallel.max_workers}}              (default: 2)
  p0_sequential:           {{config.parallel.p0_sequential}}            (default: true)
  worktree_base:           {{config.parallel.worktree_base}}            (default: .worktrees)
  timeout_per_issue:       {{config.parallel.timeout_per_issue}}        (default: 7200s)
  max_merge_retries:       {{config.parallel.max_merge_retries}}        (default: 2)
  stream_subprocess_output: {{config.parallel.stream_subprocess_output}} (default: false)
  worktree_copy_files:     {{config.parallel.worktree_copy_files}}      (default: [.env])

Edit: /ll:configure parallel
```

## automation --show

```
Sequential Automation Configuration (ll-auto)
---------------------------------------------
  timeout_seconds: {{config.automation.timeout_seconds}} (default: 3600)
  max_workers:     {{config.automation.max_workers}}     (default: 2)
  stream_output:   {{config.automation.stream_output}}   (default: true)
  state_file:      {{config.automation.state_file}}      (default: .auto-manage-state.json)
  worktree_base:   {{config.automation.worktree_base}}   (default: .worktrees)

Edit: /ll:configure automation
```

## documents --show

```
Documents Configuration
-----------------------
  enabled:    {{config.documents.enabled}}    (default: false)
  categories:
{{#each config.documents.categories}}
    {{@key}}:
      description: {{this.description}}
      files: {{this.files}}
{{/each}}

Edit: /ll:configure documents
```

## continuation --show

```
Continuation Configuration
--------------------------
  enabled:                     {{config.continuation.enabled}}                      (default: true)
  auto_detect_on_session_start: {{config.continuation.auto_detect_on_session_start}} (default: true)
  include_todos:               {{config.continuation.include_todos}}                (default: true)
  include_git_status:          {{config.continuation.include_git_status}}           (default: true)
  include_recent_files:        {{config.continuation.include_recent_files}}         (default: true)
  max_continuations:           {{config.continuation.max_continuations}}            (default: 3)
  prompt_expiry_hours:         {{config.continuation.prompt_expiry_hours}}          (default: 24)

Edit: /ll:configure continuation
```

## context --show

```
Context Monitor Configuration
-----------------------------
  enabled:                {{config.context_monitor.enabled}}                 (default: false)
  auto_handoff_threshold: {{config.context_monitor.auto_handoff_threshold}}  (default: 80%)
  context_limit_estimate: {{config.context_monitor.context_limit_estimate}}  (default: 150000)
  state_file:             {{config.context_monitor.state_file}}              (default: .claude/ll-context-state.json)

Edit: /ll:configure context
```

## prompt --show

```
Prompt Optimization Configuration
---------------------------------
  enabled:           {{config.prompt_optimization.enabled}}            (default: true)
  mode:              {{config.prompt_optimization.mode}}               (default: quick)
  confirm:           {{config.prompt_optimization.confirm}}            (default: true)
  bypass_prefix:     {{config.prompt_optimization.bypass_prefix}}      (default: *)
  clarity_threshold: {{config.prompt_optimization.clarity_threshold}}  (default: 6)

Edit: /ll:configure prompt
Toggle: /ll:toggle-autoprompt [enabled|mode|confirm]
```

## scan --show

```
Scan Configuration
------------------
  focus_dirs:       {{config.scan.focus_dirs}}       (default: [src/, tests/])
  exclude_patterns: {{config.scan.exclude_patterns}} (default: [node_modules, __pycache__, .git])
  custom_agents:    {{config.scan.custom_agents}}    (default: [])

Edit: /ll:configure scan
```

## sync --show

```
Sync Configuration
------------------
  enabled:          {{config.sync.enabled}}                       (default: false)
  provider:         {{config.sync.provider}}                      (default: github)
  GitHub:
    repo:           {{config.sync.github.repo}}                   (default: auto-detect)
    label_mapping:  {{config.sync.github.label_mapping}}          (default: BUG→bug, FEAT→enhancement, ENH→enhancement)
    priority_labels: {{config.sync.github.priority_labels}}       (default: true)
    sync_completed: {{config.sync.github.sync_completed}}         (default: false)

Edit: /ll:configure sync
```
