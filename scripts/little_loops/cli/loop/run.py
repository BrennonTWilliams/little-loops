"""ll-loop run subcommand."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from little_loops.cli.loop._helpers import (
    _is_earliest_waiter,
    _make_instance_id,
    get_builtin_loops_dir,
    print_execution_plan,
    register_loop_signal_handlers,
    resolve_loop_path,
    run_background,
    run_foreground,
    with_diagram_color,
)
from little_loops.logger import Logger


def _parse_program_md(path: Path) -> dict[str, str]:
    """Parse .ll/program.md heading sections into context key-value pairs.

    Sections mapped:
      ## Directive  → directive (prose)
      ## Targets    → targets (space-joined list items)
      ## Benchmark  → each key: value pair injected directly
      ## Budget     → budget (prose)
      ## Constraints → constraints (prose)
    """
    if not path.exists():
        return {}
    try:
        content = path.read_text()
    except OSError:
        return {}

    def _extract(heading: str) -> str:
        m = re.search(rf"^##\s+{re.escape(heading)}\s*$", content, re.MULTILINE | re.IGNORECASE)
        if not m:
            return ""
        start = m.end()
        nxt = re.search(r"^##\s", content[start:], re.MULTILINE)
        return content[start : start + nxt.start()].strip() if nxt else content[start:].strip()

    result: dict[str, str] = {}

    directive = _extract("Directive")
    if directive:
        result["directive"] = directive

    targets_text = _extract("Targets")
    if targets_text:
        items = [
            line.lstrip("-* \t").strip()
            for line in targets_text.splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        result["targets"] = " ".join(items) if items else targets_text

    benchmark_text = _extract("Benchmark")
    if benchmark_text:
        for line in benchmark_text.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip()
                if k and v:
                    result[k] = v

    budget = _extract("Budget")
    if budget:
        result["budget"] = budget

    constraints = _extract("Constraints")
    if constraints:
        result["constraints"] = constraints

    return result


def cmd_run(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Run a loop."""
    # Resolve to absolute so tracking files always land in the main repo,
    # regardless of any subsequent os.chdir (e.g. the --worktree path, BUG-2386).
    loops_dir = loops_dir.resolve()

    from little_loops.fsm.concurrency import LockManager, resolve_scope
    from little_loops.fsm.persistence import PersistentExecutor, _reconcile_stale_runs
    from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
    from little_loops.fsm.validation import load_and_validate

    try:
        if getattr(args, "builtin", False):
            path = get_builtin_loops_dir() / f"{loop_name}.yaml"
            if not path.exists():
                logger.error(f"Built-in loop not found: {loop_name!r}")
                return 1
        else:
            path = resolve_loop_path(loop_name, loops_dir)
        fsm, _ = load_and_validate(path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    # Apply overrides
    if getattr(args, "max_steps", None):
        fsm.max_steps = args.max_steps
    if getattr(args, "max_iterations", None):
        fsm.max_iterations = args.max_iterations
    if args.delay is not None:
        fsm.backoff = args.delay
    if args.no_llm:
        fsm.llm.enabled = False
    if getattr(args, "no_host_guard", False):
        fsm.host_guard.enabled = False
    if getattr(args, "host_guard_budget_mb", None) is not None:
        fsm.host_guard.max_cumulative_subproc_mb = args.host_guard_budget_mb
    if getattr(args, "no_prompt_size_guard", False):
        fsm.prompt_size_guard.enabled = False
    if getattr(args, "prompt_size_warn_chars", None) is not None:
        fsm.prompt_size_guard.warn_chars = args.prompt_size_warn_chars
    if args.llm_model:
        fsm.llm.model = args.llm_model
    # Inject positional input arg before --context so --context can override
    if getattr(args, "input", None) is not None:
        raw = args.input
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                matched = {k: v for k, v in parsed.items() if k in fsm.context}
                if matched:
                    fsm.context.update(matched)
                else:
                    fsm.context[fsm.input_key] = raw
            else:
                fsm.context[fsm.input_key] = raw
        except (json.JSONDecodeError, ValueError):
            fsm.context[fsm.input_key] = raw
    # Inject program.md fields before --context so --context can override
    program_md_arg = getattr(args, "program_md", None)
    program_md_path = (
        program_md_arg if program_md_arg is not None else Path.cwd() / ".ll" / "program.md"
    )
    for key, value in _parse_program_md(program_md_path).items():
        fsm.context[key] = value
    for kv in getattr(args, "context", None) or []:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        fsm.context[key.strip()] = value.strip()

    # Generate instance_id early so run_dir can be derived before the validation scan
    if getattr(args, "foreground_internal", False):
        _pre_instance_id: str | None = getattr(args, "instance_id", None)
    else:
        _pre_instance_id = _make_instance_id(loop_name)

    # Inject run_dir into context before validation so ${context.run_dir} resolves.
    # --context run_dir=VALUE (already applied above) takes precedence.
    if "run_dir" not in fsm.context:
        fsm.context["run_dir"] = str(loops_dir / "runs" / (_pre_instance_id or loop_name)) + "/"

    # Inject input hash for checkpoint fingerprinting.
    # --context input_hash=VALUE (already applied above) takes precedence.
    if "input_hash" not in fsm.context and isinstance(fsm.context.get("input"), str):
        fsm.context["input_hash"] = hashlib.sha256(fsm.context["input"].encode()).hexdigest()[:12]

    # Inject loop metadata into context so templates can reference
    # ${context.max_steps} in state actions and evaluator prompts.
    # --context max_steps=VALUE (already applied above) takes precedence.
    # Must run after the --max-steps CLI override so the context value reflects
    # any CLI-supplied override.
    if "max_steps" not in fsm.context:
        fsm.context["max_steps"] = fsm.max_steps
    if fsm.max_iterations is not None and "max_iterations" not in fsm.context:
        fsm.context["max_iterations"] = fsm.max_iterations

    # Apply YAML loop config env-var overrides (CLI flags below overwrite these)
    if fsm.config is not None and isinstance(fsm.config.handoff_threshold, int):
        os.environ["LL_HANDOFF_THRESHOLD"] = str(fsm.config.handoff_threshold)

    if getattr(args, "handoff_threshold", None) is not None:
        if not (1 <= args.handoff_threshold <= 100):
            raise SystemExit("--handoff-threshold must be between 1 and 100")
        os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)

    if getattr(args, "context_limit", None) is not None:
        os.environ["LL_CONTEXT_LIMIT"] = str(args.context_limit)

    from little_loops.config import BRConfig
    from little_loops.design_tokens import load_design_tokens, render_as_prompt_context

    _config = BRConfig(Path.cwd())

    # Inject include allowlist from config default.
    # --context include=VALUE (already applied above) takes precedence.
    if "include" not in fsm.context and _config.loops.run_defaults.include:
        fsm.context["include"] = _config.loops.run_defaults.include

    if not fsm.context.get("design_tokens_context"):
        _tokens = load_design_tokens(_config)
        fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""

    _edge_label_colors = _config.cli.colors.fsm_edge_labels.to_dict()
    _highlight_color = _config.cli.colors.fsm_active_state
    _badges = _config.loops.glyphs.to_dict()

    # Dry run
    if args.dry_run:
        from little_loops.cli.loop.diagram_modes import resolve_facets
        from little_loops.cli.loop.layout import _render_fsm_diagram
        from little_loops.cli.output import terminal_width

        facets = resolve_facets(args)
        if facets is not None:
            tw = terminal_width()
            header_text = f"== loop: {fsm.name} "
            print(header_text + "=" * max(0, tw - len(header_text)))
            with with_diagram_color(facets is not None):
                diagram = _render_fsm_diagram(
                    fsm,
                    highlight_color=_highlight_color,
                    edge_label_colors=_edge_label_colors,
                    badges=_badges,
                    mode=facets.scope,
                    suppress_labels=not facets.edge_labels,
                    title_only=facets.state_detail == "title",
                )
            print(diagram)
            print()
        print_execution_plan(fsm, edge_label_colors=_edge_label_colors)
        return 0

    # Pre-run validation: check required context variables are present
    _ctx_var_re = re.compile(r"\$\{context\.([^}.]+)")
    missing_keys: set[str] = set()
    for state in fsm.states.values():
        templates = [state.action] if state.action else []
        if state.evaluate and state.evaluate.prompt:
            templates.append(state.evaluate.prompt)
        for template in templates:
            for m in _ctx_var_re.finditer(template):
                key = m.group(1)
                if key not in fsm.context:
                    missing_keys.add(key)
    if missing_keys:
        for key in sorted(missing_keys):
            logger.error(
                f"Missing required context variable: '{key}'. "
                f"Run with: ll-loop run {loop_name} --context {key}=VALUE"
            )
        return 1

    # Pre-run validation: check required_inputs are present and non-empty
    for key in fsm.required_inputs:
        if not fsm.context.get(key, ""):
            logger.error(
                f"loop '{loop_name}' requires input '{key}' but none was provided. "
                f"Pass it via: ll-loop run {loop_name} <value>"
            )
            return 1

    # Baseline mode: apply to context before background gate so flags forward correctly
    baseline_enabled = getattr(args, "baseline", False)
    if baseline_enabled:
        if getattr(args, "worktree", False):
            raise SystemExit("--baseline and --worktree cannot be combined")
        fsm.context["_baseline"] = {
            "enabled": True,
            "skill": getattr(args, "baseline_skill", None),
            "items": getattr(args, "items", None),
            "cross_host": getattr(args, "cross_host", False),
        }

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        if getattr(args, "worktree", False):
            raise SystemExit("--worktree and --background cannot be combined")
        if getattr(args, "follow", False):
            raise SystemExit(
                "--follow and --background cannot be combined; use 'll-logs tail' to watch a background loop"
            )
        return run_background(loop_name, args, loops_dir)

    # Register PID file for all foreground runs so cmd_stop can send SIGTERM (BUG-639).
    # Background-spawned processes (foreground_internal=True) have their PID written by the
    # parent in run_background(); plain foreground runs must write their own PID here.
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)
    _reconcile_stale_runs(loops_dir)
    instance_id = _pre_instance_id
    pid_file = running_dir / f"{instance_id or loop_name}.pid"
    foreground_pid_file: Path | None = pid_file

    if not getattr(args, "foreground_internal", False):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

    def _cleanup_pid() -> None:
        pid_file.unlink(missing_ok=True)

    atexit.register(_cleanup_pid)

    # Scope-based locking
    lock_manager = LockManager(loops_dir)
    scope = resolve_scope(fsm.scope or ["."], fsm.context)
    _queue_entry_file: Path | None = None

    def _cleanup_queue_entry() -> None:
        if _queue_entry_file is not None:
            _queue_entry_file.unlink(missing_ok=True)

    if not getattr(args, "no_lock", False):
        if not lock_manager.acquire(fsm.name, scope, instance_id=instance_id, singleton=fsm.singleton):
            conflict = lock_manager.find_conflict(
                scope, caller_loop_name=fsm.name, caller_singleton=fsm.singleton
            )
            if conflict and getattr(args, "queue", False):
                # Write queue entry so dashboard shows the waiting loop
                queue_dir = loops_dir / ".queue"
                queue_dir.mkdir(parents=True, exist_ok=True)
                entry_id = str(uuid.uuid4())
                entry = {
                    "id": entry_id,
                    "loopName": loop_name,
                    "enqueuedAt": datetime.now(UTC).isoformat(),
                    "context": {
                        "waitingFor": conflict.loop_name,
                        "scope": conflict.scope,
                        "pid": os.getpid(),
                    },
                }
                _queue_entry_file = queue_dir / f"{entry_id}.json"
                _queue_entry_file.write_text(json.dumps(entry, indent=2))
                atexit.register(_cleanup_queue_entry)

                logger.info(f"Waiting for conflicting loop '{conflict.loop_name}' to finish...")
                # Retry loop: when N waiters are released simultaneously, only one wins
                # acquire(); losers loop back and wait again rather than exiting (BUG-1281).
                acquired = False
                _wait_start = time.time()
                _budget = _config.loops.queue_wait_timeout_seconds
                while time.time() - _wait_start < _budget:
                    _remaining = _budget - (time.time() - _wait_start)
                    if not lock_manager.wait_for_scope(
                        scope,
                        timeout=int(_remaining),
                        loop_name=fsm.name,
                        singleton=fsm.singleton,
                    ):
                        _cleanup_queue_entry()
                        logger.error("Timeout waiting for scope to become available")
                        return 1
                    if not _is_earliest_waiter(entry_id, queue_dir):
                        time.sleep(1)
                        continue
                    if lock_manager.acquire(
                        fsm.name, scope, instance_id=instance_id, singleton=fsm.singleton
                    ):
                        acquired = True
                        break
                if not acquired:
                    _cleanup_queue_entry()
                    logger.error("Failed to acquire lock after waiting")
                    return 1
                # Lock acquired - no longer queued
                _cleanup_queue_entry()
            elif conflict:
                logger.error(f"Scope conflict with running loop: {conflict.loop_name}")
                logger.info(f"  Conflicting scope: {conflict.scope}")
                logger.info("  Use --queue to wait for it to finish")
                return 1
            else:
                # Unexpected: find_conflict returned None but acquire failed
                logger.error("Failed to acquire scope lock (unknown reason)")
                return 1

    executor: PersistentExecutor | None = None
    try:
        # Worktree isolation: create branch + directory before anything reads Path.cwd()
        if getattr(args, "worktree", False):
            from little_loops.config import BRConfig as _MainBRConfig
            from little_loops.parallel.git_lock import GitLock
            from little_loops.worktree_utils import cleanup_worktree, setup_worktree

            _main_config = _MainBRConfig(Path.cwd())
            _worktree_base = _main_config.get_worktree_base()
            _copy_files = _main_config.parallel.worktree_copy_files
            _repo_path = Path.cwd()

            _timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            _safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)
            _branch_name = f"{_timestamp}-{_safe_name}"
            _worktree_path = _worktree_base / _branch_name

            _worktree_base.mkdir(parents=True, exist_ok=True)
            _git_lock = GitLock(logger)

            # Capture main-repo HEAD before creating the worktree so the
            # cleanup closure can detect commits added during the run (BUG-2386).
            _base_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=_repo_path,
                capture_output=True,
                text=True,
            )
            _base_commit: str | None = (
                _base_result.stdout.strip()
                if _base_result.returncode == 0 and _base_result.stdout.strip()
                else None
            )

            setup_worktree(
                repo_path=_repo_path,
                worktree_path=_worktree_path,
                branch_name=_branch_name,
                copy_files=_copy_files,
                logger=logger,
                git_lock=_git_lock,
            )

            logger.info(f"Worktree: {_worktree_path}")
            logger.info(f"Branch:   {_branch_name}")

            def _cleanup_worktree_on_exit() -> None:
                _delete_branch = True
                if _worktree_path.exists() and _base_commit:
                    _status = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=_worktree_path,
                        capture_output=True,
                        text=True,
                    )
                    _has_dirty = bool(_status.returncode == 0 and _status.stdout.strip())

                    _revcount = subprocess.run(
                        ["git", "rev-list", "--count", f"{_base_commit}..HEAD"],
                        cwd=_worktree_path,
                        capture_output=True,
                        text=True,
                    )
                    _ahead_str = _revcount.stdout.strip()
                    _commits_ahead = (
                        int(_ahead_str) if _revcount.returncode == 0 and _ahead_str.isdigit() else 0
                    )

                    if _has_dirty or _commits_ahead > 0:
                        _delete_branch = False
                        logger.warning(
                            f"Worktree has pending work — branch '{_branch_name}' was NOT deleted."
                        )
                        if _commits_ahead:
                            logger.warning(f"  {_commits_ahead} commit(s) ahead of base.")
                        if _has_dirty:
                            logger.warning("  Uncommitted changes detected.")
                        logger.warning(f"  To recover: git checkout {_branch_name}")

                cleanup_worktree(
                    worktree_path=_worktree_path,
                    repo_path=_repo_path,
                    logger=logger,
                    git_lock=_git_lock,
                    delete_branch=_delete_branch,
                )

            atexit.register(_cleanup_worktree_on_exit)

            os.environ["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
            os.chdir(_worktree_path)

        circuit = (
            RateLimitCircuit(Path(_config.commands.rate_limits.circuit_breaker_path))
            if _config.commands.rate_limits.circuit_breaker_enabled
            else None
        )
        Path(fsm.context["run_dir"]).mkdir(parents=True, exist_ok=True)
        executor = PersistentExecutor(
            fsm,
            loops_dir=loops_dir,
            circuit=circuit,
            instance_id=instance_id,
            pid=os.getpid(),
            run_model=getattr(args, "run_model", None) or None,
        )

        # Register signal handlers for graceful shutdown
        register_loop_signal_handlers(executor, pid_file=foreground_pid_file)

        from little_loops.extension import wire_extensions
        from little_loops.transport import wire_transports

        wire_extensions(executor.event_bus, _config.extensions, executor=executor)
        wire_transports(executor.event_bus, _config.events)
        return run_foreground(
            executor,
            fsm,
            args,
            highlight_color=_highlight_color,
            edge_label_colors=_edge_label_colors,
            badges=_badges,
            instance_id=instance_id,
            loop_path=path,
            running_dir=running_dir,
            model=fsm.llm.model,
            cost_output_json=getattr(args, "cost_output_json", None),
        )
    finally:
        if executor is not None:
            executor.close_transports()
        if not getattr(args, "no_lock", False):
            lock_manager.release(fsm.name, instance_id=instance_id)
