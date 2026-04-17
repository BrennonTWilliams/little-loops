"""ll-loop testing subcommands: test, simulate."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import load_loop
from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
from little_loops.logger import Logger


def cmd_test(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Run a single test iteration to verify loop configuration.

    Executes the target state's action and evaluation, then reports
    what the loop would do without actually transitioning further.
    """
    from little_loops.fsm.evaluators import EvaluationResult, evaluate, evaluate_exit_code
    from little_loops.fsm.executor import DefaultActionRunner
    from little_loops.fsm.interpolation import InterpolationContext

    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    # Determine target state
    target = args.state if args.state else fsm.initial
    if target not in fsm.states:
        logger.error(f"State '{target}' not found. Available: {', '.join(fsm.states)}")
        return 1
    state_config = fsm.states[target]

    print(f"## Test Iteration: {loop_name}")
    print()
    print(f"State: {target}")

    # If no action, report and exit
    if not state_config.action:
        print(f"State '{target}' has no action to test")
        print()
        print("\u2713 Loop structure is valid (no check action to execute)")
        return 0

    action = state_config.action
    is_slash = action.startswith("/") or state_config.action_type in (
        "prompt",
        "slash_command",
    )

    print(f"Action: {action}")
    print()

    if is_slash:
        from little_loops.fsm.executor import ActionResult, SimulationActionRunner

        exit_code_arg = getattr(args, "exit_code", None)
        if exit_code_arg is not None:
            sim_exit_code = exit_code_arg
            print(f"[SIMULATED] Using --exit-code {sim_exit_code}")
        else:
            sim_runner = SimulationActionRunner()
            sim_result = sim_runner.run(action, timeout=120, is_slash_command=True)
            sim_exit_code = sim_result.exit_code
        print()
        result = ActionResult(
            output=f"[simulated output for: {action}]",
            stderr="",
            exit_code=sim_exit_code,
            duration_ms=0,
        )
    else:
        # Run the action
        runner = DefaultActionRunner()
        timeout = state_config.timeout or 120
        result = runner.run(action, timeout=timeout, is_slash_command=False)

    print(f"Exit code: {result.exit_code}")

    # Truncate output for display
    output_lines = result.output.strip().split("\n")
    if len(output_lines) > 10:
        extra = len(output_lines) - 10
        output_preview = "\n".join(output_lines[:10]) + f"\n... ({extra} more lines)"
    elif len(result.output) > 500:
        output_preview = result.output[:500] + "..."
    else:
        output_preview = result.output.strip() if result.output.strip() else "(empty)"

    print(f"Output:\n{output_preview}")

    if result.stderr:
        stderr_lines = result.stderr.strip().split("\n")
        if len(stderr_lines) > 5:
            extra = len(stderr_lines) - 5
            stderr_preview = "\n".join(stderr_lines[:5]) + f"\n... ({extra} more lines)"
        else:
            stderr_preview = result.stderr.strip()
        print(f"Stderr:\n{stderr_preview}")

    print()

    # Evaluate
    ctx = InterpolationContext()
    eval_result: EvaluationResult

    if state_config.evaluate:
        eval_result = evaluate(
            config=state_config.evaluate,
            output=result.output,
            exit_code=result.exit_code,
            context=ctx,
        )
        evaluator_type: str = state_config.evaluate.type
    else:
        # Default to exit_code evaluation
        eval_result = evaluate_exit_code(result.exit_code)
        evaluator_type = "exit_code (default)"

    print(f"Evaluator: {evaluator_type}")
    print(f"Verdict: {eval_result.verdict.upper()}")

    if eval_result.details:
        for key, value in eval_result.details.items():
            if key != "exit_code" or evaluator_type != "exit_code (default)":
                print(f"  {key}: {value}")

    # Determine next state based on verdict
    verdict = eval_result.verdict
    next_state = None

    if state_config.route:
        routes = state_config.route.routes
        if verdict in routes:
            next_state = routes[verdict]
        elif state_config.route.default:
            next_state = state_config.route.default
    else:
        if verdict == "yes" and state_config.on_yes:
            next_state = state_config.on_yes
        elif verdict == "no" and state_config.on_no:
            next_state = state_config.on_no
        elif verdict == "error" and state_config.on_error:
            next_state = state_config.on_error
        elif verdict in state_config.extra_routes:
            next_state = state_config.extra_routes[verdict]

    print()
    if next_state:
        print(f"Would transition: {target} \u2192 {next_state}")
    else:
        print(f"Would transition: {target} \u2192 (no route for '{verdict}')")

    # Summary
    print()
    has_error = eval_result.verdict == "error" or "error" in eval_result.details
    if has_error:
        print("\u26a0 Loop has issues - review the error details above")
        return 1
    else:
        print("\u2713 Loop appears to be configured correctly")
        return 0


def cmd_simulate(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
    circuit: RateLimitCircuit | None = None,
) -> int:
    """Run interactive simulation of loop execution.

    Traces through loop logic without executing commands, allowing users
    to verify state transitions and understand loop behavior.

    The ``circuit`` kwarg lets tests redirect the shared 429 circuit-breaker
    state file (normally under ``.loops/tmp/``) to a ``tmp_path``; the CLI
    dispatcher does not pass one.
    """
    from little_loops.fsm.executor import FSMExecutor, SimulationActionRunner

    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    # Apply CLI overrides
    if args.max_iterations:
        fsm.max_iterations = args.max_iterations
    else:
        # Limit iterations for simulation safety (cap at 20 unless overridden)
        if fsm.max_iterations > 20:
            logger.info(f"Limiting simulation to 20 iterations (loop config: {fsm.max_iterations})")
            fsm.max_iterations = 20

    # Create simulation runner
    sim_runner = SimulationActionRunner(scenario=args.scenario)

    # Track simulation state
    states_visited: list[str] = []

    def simulation_callback(event: dict) -> None:
        """Display simulation progress."""
        event_type = event.get("event")

        if event_type == "state_enter":
            iteration = event.get("iteration", 0)
            state = event.get("state", "")
            states_visited.append(state)
            print()
            print(f"[{iteration}] State: {state}")

        elif event_type == "action_start":
            action = event.get("action", "")
            action_display = action[:70] + "..." if len(action) > 70 else action
            print(f"    Action: {action_display}")

        elif event_type == "evaluate":
            evaluator = event.get("type", "exit_code")
            verdict = event.get("verdict", "")
            print(f"    Evaluator: {evaluator}")
            print(f"    Result: {verdict.upper()}")

        elif event_type == "route":
            from_state = event.get("from", "")
            to_state = event.get("to", "")
            print(f"    Transition: {from_state} \u2192 {to_state}")

    # Print header
    mode_str = f"scenario={args.scenario}" if args.scenario else "interactive"
    print(f"=== SIMULATION: {fsm.name} ({mode_str}) ===")

    # Run simulation
    executor = FSMExecutor(
        fsm,
        event_callback=simulation_callback,
        action_runner=sim_runner,
        circuit=circuit,
    )
    result = executor.run()

    # Print summary
    print()
    print("=== Summary ===")
    arrow = " \u2192 "
    print(f"States visited: {arrow.join(states_visited)}")
    print(f"Iterations: {result.iterations}")
    print(f"Would have executed {len(sim_runner.calls)} commands")
    print(f"Terminated by: {result.terminated_by}")

    return 0
