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
  categories:       [bugs, features, enhancements, epics]      (+ any custom)

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
  use_feature_branches:         {{config.parallel.use_feature_branches}}         (default: false)
  push_feature_branches:        {{config.parallel.push_feature_branches}}        (default: false)
  open_pr_for_feature_branches: {{config.parallel.open_pr_for_feature_branches}} (default: false)
  base_branch:                  {{config.parallel.base_branch}}                  (default: main)
  epic_branches.enabled:        {{config.parallel.epic_branches.enabled}}        (default: false)
  epic_branches.prefix:         {{config.parallel.epic_branches.prefix}}         (default: epic/)
  epic_branches.merge_to_base_on_complete: {{config.parallel.epic_branches.merge_to_base_on_complete}} (default: true)
  epic_branches.open_pr:        {{config.parallel.epic_branches.open_pr}}        (default: false)

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

## commands --show

```
Commands Configuration
----------------------
  pre_implement:    {{config.commands.pre_implement}}              (default: none)
  post_implement:   {{config.commands.post_implement}}             (default: none)
  confidence_gate:
    enabled:              {{config.commands.confidence_gate.enabled}}              (default: false)
    readiness_threshold:  {{config.commands.confidence_gate.readiness_threshold}}  (default: 85)
    outcome_threshold:    {{config.commands.confidence_gate.outcome_threshold}}    (default: 70)
  tdd_mode:         {{config.commands.tdd_mode}}                   (default: false)
  max_refine_count: {{config.commands.max_refine_count}}           (default: 5)
  rate_limits:
    max_wait_seconds:        {{config.commands.rate_limits.max_wait_seconds}}        (default: 21600)
    long_wait_ladder:        {{config.commands.rate_limits.long_wait_ladder}}        (default: [300, 900, 1800, 3600])
    circuit_breaker_enabled: {{config.commands.rate_limits.circuit_breaker_enabled}} (default: true)
    circuit_breaker_path:    {{config.commands.rate_limits.circuit_breaker_path}}    (default: .loops/tmp/rate-limit-circuit.json)

Edit: /ll:configure commands
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
  context_limit_estimate: {{config.context_monitor.context_limit_estimate}}  (default: 0, auto-detect)
  state_file:             {{config.context_monitor.state_file}}              (default: .ll/ll-context-state.json)

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
    label_mapping:  {{config.sync.github.label_mapping}}          (default: BUG→bug, FEAT→enhancement, ENH→enhancement, EPIC→epic)
    priority_labels: {{config.sync.github.priority_labels}}       (default: true)
    sync_completed: {{config.sync.github.sync_completed}}         (default: false)

Edit: /ll:configure sync
```

## design_tokens --show

```
Design Tokens Configuration
----------------------------
  enabled:         {{config.design_tokens.enabled}}         (default: true)
  path:            {{config.design_tokens.path}}            (default: .ll/design-tokens)
  active:          {{config.design_tokens.active}}          (default: default)
  profiles_dir:    {{config.design_tokens.profiles_dir}}    (default: null → "profiles")
  primitives_file: {{config.design_tokens.primitives_file}} (default: primitives.json)
  semantic_file:   {{config.design_tokens.semantic_file}}   (default: semantic.json)
  themes_dir:      {{config.design_tokens.themes_dir}}      (default: themes)
  active_theme:    {{config.design_tokens.active_theme}}    (default: light)
  installed:       {{enumerate <path>/<profiles_dir or "profiles">/ subdirectories}}

Edit: /ll:configure design-tokens
```

## learning_tests --show

Learning Tests Configuration
------------------------------
  enabled:               {{config.learning_tests.enabled}}               (default: false)
  stale_after_days:      {{config.learning_tests.stale_after_days}}      (default: 30)
  discoverability.mode:  {{config.learning_tests.discoverability.mode}}  (default: warn)

Edit: /ll:configure learning-tests
```

## decisions --show

```
Decisions Configuration
-----------------------
  enabled:       {{config.decisions.enabled}}       (default: false)
  log_path:      {{config.decisions.log_path}}      (default: .ll/decisions.yaml)
  auto_generate: {{config.decisions.auto_generate}} (default: [])

Edit: /ll:configure decisions
```

## analytics --show

```
Analytics Configuration
-----------------------
  enabled:              {{config.analytics.enabled}}              (default: false)
  capture.skills:       {{config.analytics.capture.skills}}       (default: ["*"])
  capture.cli_commands: {{config.analytics.capture.cli_commands}} (default: ["*"])
  capture.corrections:        {{config.analytics.capture.corrections}}         (default: true)
  capture.file_events:        {{config.analytics.capture.file_events}}         (default: true)
  capture.correction_patterns: {{config.analytics.capture.correction_patterns}} (default: [])

Edit: /ll:configure analytics
```

## history --show

```
History Configuration
---------------------
  velocity_window:                       {{config.history.velocity_window}}                       (default: 10)
  effort_fields:                         {{config.history.effort_fields}}                         (default: ["session_count", "cycle_time_days"])
  max_age_days:                          {{config.history.max_age_days}}                          (default: null)
  planning_skills:                       {{config.history.planning_skills}}                       (default: ["create-sprint", "scope-epic", "manage-issue", "review-epic"])
  session_digest.enabled:                {{config.history.session_digest.enabled}}                (default: false)
  session_digest.days:                   {{config.history.session_digest.days}}                   (default: 7)
  session_digest.char_cap:               {{config.history.session_digest.char_cap}}               (default: 1200)
  session_digest.sections:               {{config.history.session_digest.sections}}               (default: [])
  evolution.feedback_min_recurrence:     {{config.history.evolution.feedback_min_recurrence}}     (default: 2)
  evolution.bypass_min_count:            {{config.history.evolution.bypass_min_count}}            (default: 2)
  go_no_go.correction_penalty:           {{config.history.go_no_go.correction_penalty}}           (default: -0.2)
  capture_issue.dup_overlap_threshold:   {{config.history.capture_issue.dup_overlap_threshold}}   (default: 0.7)

Edit: /ll:configure history
```

## loops.run_defaults --show

```
Loop Run Defaults
-----------------
  clear:         {{config.loops.run_defaults.clear}}         (default: false)
  show_diagrams: {{config.loops.run_defaults.show_diagrams}} (default: null)
  mode:          {{config.loops.run_defaults.mode}}          (default: null)
  delay:         {{config.loops.run_defaults.delay}}         (default: null)

Valid show_diagrams values:
  Topologies: layered, neighborhood, inline
  Presets:    detailed, summary, clean, local, slim, oneline
  Sentinel:   default

Edit: /ll:configure loops.run_defaults
```
