export const meta = {
  name: 'feat-1680',
  description: 'Implement FEAT-1680: session-end hook sweeping stale cross-issue status refs',
  phases: [
    { title: 'Core Files', detail: 'Create handler, adapter, update dispatch/config' },
    { title: 'Tests', detail: 'Create unit tests and update existing test files' },
    { title: 'Docs', detail: 'Update documentation files' },
    { title: 'Verify', detail: 'Run test suite' },
  ],
}

const P = '/Users/brennon/AIProjects/brenentech/little-loops'

phase('Core Files')
await parallel([
  () => agent(
    'Create the session-end hook handler and adapter in ' + P + '. ' +
    'File 1: ' + P + '/scripts/little_loops/hooks/sweep_stale_refs.py — ' +
    'write the implementation described in .issues/features/P3-FEAT-1680-session-end-hook-sweep-stale-cross-issue-status-refs.md ' +
    'Implementation Steps section. Key requirements: ' +
    '(a) import _CODE_FENCE from little_loops.text_utils, ' +
    '(b) import find_issues from little_loops.issue_parser, ' +
    '(c) import atomic_write from little_loops.file_utils, ' +
    '(d) import BRConfig, resolve_config_path from little_loops.config.core, ' +
    '(e) public handle(event: LLHookEvent) -> LLHookResult function, ' +
    '(f) wrap entire body in try/except Exception: return LLHookResult(exit_code=0), ' +
    '(g) load config via resolve_config_path(cwd) + json.loads to get raw_hooks dict, ' +
    '(h) read fix_mode = raw_hooks.get("stale_ref_fix", "report"), ' +
    '(i) use BRConfig(project_root=cwd) to get config for find_issues(), ' +
    '(j) done_issues = find_issues(config, status_filter={"done"}), ' +
    '(k) open_issues = find_issues(config) (default call skips done/cancelled/deferred), ' +
    '(l) if fix_mode == "auto", call _auto_fix_file() on each open issue, ' +
    '(m) scan each open issue file with _scan_file() for stale refs, ' +
    '(n) stale refs are lines containing a done issue ID AND matching "is (still )?(open|in_progress|active)" or "blocked by", ' +
    '(o) skip lines inside code fences (use _CODE_FENCE spans), ' +
    '(p) _auto_fix_file rewrites stale status phrases using _STALE_STATUS_RE.sub("is done", line), ' +
    '(q) always return LLHookResult(exit_code=0), ' +
    '(r) report findings via feedback string format: "[ll] N stale cross-issue reference(s) found:\n  path:lineno: [ID] snippet", ' +
    'File 2: ' + P + '/hooks/adapters/claude-code/session-end.sh — ' +
    'exact 3-line content: #!/usr/bin/env bash, then INPUT=$(cat), then echo "$INPUT" | python -m little_loops.hooks session_end, then exit $? — ' +
    'then run: chmod +x ' + P + '/hooks/adapters/claude-code/session-end.sh',
    {label: 'create-handler', phase: 'Core Files'}
  ),

  () => agent(
    'Update three existing files in ' + P + ' for FEAT-1680. ' +
    'EDIT 1: scripts/little_loops/hooks/__init__.py — ' +
    '(a) in _USAGE string, append ", session_end" to the available intents list, ' +
    '(b) in module docstring bullet list, add a bullet "- ``session_end`` -> :mod:`little_loops.hooks.sweep_stale_refs`" after the pre_tool_use bullet, ' +
    '(c) in _dispatch_table(), add "sweep_stale_refs" to the lazy imports list (alphabetical: after session_start, before user_prompt_submit), ' +
    '(d) add "session_end": sweep_stale_refs.handle to the built_ins dict. ' +
    'EDIT 2: hooks/hooks.json — ' +
    'In the "Stop" array, add a new object AFTER the session-cleanup.sh entry but BEFORE the closing bracket of the Stop array. ' +
    'The new entry has no "matcher" field (Stop entries omit matcher). ' +
    'Use command "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh", timeout 15, ' +
    'statusMessage "Sweeping stale cross-issue status references...". ' +
    'EDIT 3: config-schema.json — ' +
    'In the "hooks" properties object (around line 1132), add a "stale_ref_fix" property alongside "host": ' +
    'type "string", enum ["report", "auto"], default "report", ' +
    'description "Session-end stale-ref sweep mode (FEAT-1680). report prints findings to stderr; auto also rewrites them in-place."',
    {label: 'update-config', phase: 'Core Files'}
  ),
])

phase('Tests')
await parallel([
  () => agent(
    'Create ' + P + '/scripts/tests/test_sweep_stale_refs.py for FEAT-1680. ' +
    'Model after scripts/tests/test_hook_session_start.py and test_hook_post_tool_use.py. ' +
    'Key patterns to follow: ' +
    '(1) _event() factory: LLHookEvent(host="claude-code", intent="session_end", payload={}, cwd=str(cwd)), ' +
    '(2) _write_config(tmp_path, stale_ref_fix="report") helper writes .ll/ll-config.json with {"hooks": {"stale_ref_fix": value}}, ' +
    '(3) in_tmp fixture using monkeypatch.chdir(tmp_path), ' +
    '(4) _write_issues helper creates .issues/{features,enhancements,bugs}/ dirs and writes minimal issue files with YAML frontmatter (id, status fields), ' +
    'Test classes: ' +
    'TestSweepStaleRefsBaseline — test_no_config_exits_zero, test_no_issues_dir_exits_zero, test_no_done_issues_exits_zero (all assert exit_code==0, feedback is None), ' +
    'TestSweepStaleRefsDetection — test_detects_is_open_phrase, test_detects_is_still_open, test_detects_blocked_by, test_no_false_positive_when_id_not_done, test_multiple_files_multiple_findings, test_report_includes_line_number (assert ":N:" in feedback), test_skips_code_fence_region (ID inside triple-backtick block should NOT be flagged), ' +
    'TestSweepStaleRefsAutoFix — test_auto_fix_rewrites_is_open (verify file content changed to "is done"), test_auto_fix_no_remaining_findings (after auto-fix, feedback is None since no stale refs remain), ' +
    'TestSweepStaleRefsGracefulDegradation — test_exits_zero_with_no_cwd, test_exits_zero_with_broken_config, ' +
    'TestScanFile — unit tests for _scan_file helper, import it directly, ' +
    'TestAutoFixFile — unit tests for _auto_fix_file helper, import it directly. ' +
    'Import from little_loops.hooks.sweep_stale_refs: handle, _scan_file, _auto_fix_file. ' +
    'All tests must assert exit_code == 0 for every path through handle().',
    {label: 'create-tests', phase: 'Tests'}
  ),

  () => agent(
    'Update two existing test files in ' + P + ' for FEAT-1680. ' +
    'EDIT 1: scripts/tests/test_hook_intents.py — ' +
    'In test_dispatch_table_merges_hook_intent_registry, after "assert \\"pre_compact\\" in table" add "assert \\"session_end\\" in table". ' +
    'Then add test_dispatch_session_end_happy_path to TestHooksMainModule class (after test_dispatch_pre_tool_use_happy_path). ' +
    'It runs subprocess [sys.executable, "-m", "little_loops.hooks", "session_end"] with input=json.dumps({}), cwd=str(tmp_path). ' +
    'Asserts returncode==0, stdout=="", stderr=="" (no config in tmp_path -> short-circuit before any output). ' +
    'EDIT 2: scripts/tests/test_config_schema.py — ' +
    'Read the file first. Add test_stale_ref_fix_in_schema following the test_analytics_in_schema or test_hooks_in_schema pattern. ' +
    'Assert stale_ref_fix in schema["properties"]["hooks"]["properties"], ' +
    'assert schema["properties"]["hooks"]["properties"]["stale_ref_fix"]["type"] == "string", ' +
    'assert schema["properties"]["hooks"]["properties"]["stale_ref_fix"]["enum"] == ["report", "auto"], ' +
    'assert schema["properties"]["hooks"].get("additionalProperties") is False.',
    {label: 'update-tests', phase: 'Tests'}
  ),

  () => agent(
    'Update the integration test file ' + P + '/scripts/tests/test_hooks_integration.py for FEAT-1680. ' +
    'Read the file first to find the TestContextHandoffSentinel class (or TestSessionStartValidation) as a pattern. ' +
    'Add a new TestSessionEndSweep class near the end of the file. ' +
    'It should have a test_adapter_exits_zero method that: ' +
    '(1) finds the session-end.sh adapter path relative to __file__ or via a known path, ' +
    '(2) runs it via subprocess with input="{}", capture_output=True, ' +
    '(3) uses cwd=str(tmp_path) so no project config is found, ' +
    '(4) asserts returncode==0. ' +
    'Follow the EXACT same pattern as the existing Stop-hook tests (TestContextHandoffSentinel) for finding the adapter path.',
    {label: 'update-integration-tests', phase: 'Tests'}
  ),
])

phase('Docs')
await parallel([
  () => agent(
    'Update three doc files in ' + P + ' for FEAT-1680. Read each file first. ' +
    'FILE 1: docs/reference/API.md — find "LLHookIntentExtension" section listing built-in intents, add session_end. Also find "main_hooks" section listing adapter files, add session-end.sh. ' +
    'FILE 2: docs/reference/HOST_COMPATIBILITY.md — find hook intents parity matrix, update the "stop" row to note session_end as the Python dispatch intent for Claude Code Stop event. ' +
    'FILE 3: docs/reference/EVENT-SCHEMA.md — find "Per-intent payload notes" section, add session_end bullet: handler reads done IDs via find_issues(status_filter={"done"}) and hooks.stale_ref_fix from raw config; outputs findings in result.feedback; always exits 0.',
    {label: 'docs-api-compat-schema', phase: 'Docs'}
  ),

  () => agent(
    'Update three doc files in ' + P + ' for FEAT-1680. Read each file first. ' +
    'FILE 1: docs/ARCHITECTURE.md — find directory structure tree listing hooks/adapters/claude-code/ files, add session-end.sh alongside precompact.sh and session-start.sh. ' +
    'FILE 2: docs/development/TROUBLESHOOTING.md — find "Hook not executing" chmod block, add chmod +x hooks/adapters/claude-code/session-end.sh. ' +
    'FILE 3: docs/claude-code/write-a-hook.md — find "Adapter flow" section listing adapter files, add session-end.sh.',
    {label: 'docs-arch-trouble-guide', phase: 'Docs'}
  ),
])

phase('Verify')
const testResult = await agent(
  'Run tests for FEAT-1680 in ' + P + '. ' +
  'Run: cd ' + P + ' && python -m pytest scripts/tests/test_sweep_stale_refs.py scripts/tests/test_hook_intents.py::TestHooksMainModule::test_dispatch_session_end_happy_path scripts/tests/test_config_schema.py -v -k "sweep or session_end or stale" 2>&1 | tail -50. ' +
  'If any tests fail (not skip), report the exact error and what file/line needs fixing. ' +
  'If all pass, report "ALL TESTS PASSED".',
  {label: 'run-tests', phase: 'Verify'}
)

return { testResult }
