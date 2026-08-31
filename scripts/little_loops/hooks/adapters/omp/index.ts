/**
 * oh-my-pi (omp) adapter for little-loops hook intents.
 *
 * omp hooks are native Bun/TS modules loaded via `HookAPI.on()` registration
 * (`export default function(pi: HookAPI) { pi.on(...) }`) — see
 * thoughts/research/omp-hook-event-parity.md (FEAT-2263). This makes the
 * shape closer to hooks/adapters/opencode/index.ts's `spawnIntent()`
 * transport pattern than to the Bash-shim hosts (codex/kimi/qwen). No logic
 * lives here; the adapter is purely a transport. Host identity is conveyed
 * via LL_HOOK_HOST so the Python dispatcher builds LLHookEvent(host="omp").
 *
 * MVP scope (FEAT-2261 acceptance criteria): session_start -> session_start,
 * tool_result -> post_tool_use (fire-and-forget, matching the FEAT-1489
 * fire-and-forget precedent used for Codex/OpenCode's post_tool_use). Richer
 * mappings the FEAT-2263 audit identified (pre_tool_use via `tool_call`,
 * pre_compact via `session_before_compact`, user_prompt_submit via
 * `before_agent_start`, session_end via `session_shutdown`) are documented in
 * README.md as deferred — not wired here to keep this issue's change surface
 * to the stated ACs.
 */
// Imported from the "./extensibility/hooks" subpath, not the package root:
// the root package's published dist/types/index.d.ts does not re-export
// HookAPI/HookContext even though in-repo hook examples import them from the
// root (that resolves against source, not the published .d.ts this adapter's
// tsc --noEmit gate checks against).
import type {
  HookAPI,
  HookContext,
  SessionStartEvent,
  ToolResultEvent,
} from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

type Intent = "session_start" | "post_tool_use";

interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

// Interpreter resolution (BUG-2921): mirror the shell adapters' and the
// OpenCode adapter's LL_PYTHON -> python3 -> python chain. Bun.which returns
// null (never throws) when a name is not on PATH.
const PY =
  process.env.LL_PYTHON ?? Bun.which("python3") ?? Bun.which("python") ?? "python";

const spawnIntent = async (
  intent: Intent,
  payload: unknown,
  cwd: string,
): Promise<SpawnResult> => {
  const proc = Bun.spawn([PY, "-m", "little_loops.hooks", intent], {
    cwd,
    env: { ...process.env, LL_HOOK_HOST: "omp" },
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });
  proc.stdin.write(JSON.stringify(payload ?? {}));
  proc.stdin.end();
  const [stdout, stderr] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
  ]);
  const exitCode = await proc.exited;
  return { stdout, stderr, exitCode };
};

export default function registerHooks(pi: HookAPI): void {
  // Advisory only: HookHandler<SessionStartEvent> returns void, so there is
  // no cancel/result path to honor here (unlike Codex/OpenCode's
  // session_start, which can block via exit_code=2).
  pi.on("session_start", async (event: SessionStartEvent, ctx: HookContext) => {
    const { stderr } = await spawnIntent("session_start", event, ctx.cwd);
    if (stderr) console.error(stderr);
  });

  // Fire-and-forget per FEAT-1489 precedent: tool_result fires after the
  // tool has already executed, so post_tool_use's analytics write must never
  // add latency to the omp tool-result path. Stderr/exit code are dropped,
  // matching hooks/adapters/opencode/index.ts's tool.execute.after handler.
  pi.on("tool_result", (event: ToolResultEvent, ctx: HookContext) => {
    void spawnIntent("post_tool_use", event, ctx.cwd);
  });
}
