/**
 * OpenCode adapter for little-loops hook intents.
 *
 * Mirrors the shape of hooks/adapters/claude-code/{session-start,precompact}.sh:
 * spawn `$PY -m little_loops.hooks <intent>`, pipe the host event payload as
 * JSON to stdin, propagate stdout/stderr/exit-code back to OpenCode. No logic
 * lives here; the adapter is purely a transport. Host identity is conveyed via
 * the LL_HOOK_HOST environment variable so the Python dispatcher constructs
 * LLHookEvent with host="opencode".
 *
 * MVP scope: session.created → session_start (then drift_check, ENH-2888),
 * session.compacted → pre_compact.
 * tool.execute.after → post_tool_use is wired as fire-and-forget (no `await`
 * on spawnIntent) per FEAT-1489 — zero user-visible latency cost.
 * tool.execute.before is still deferred (blocking pre-tool requires a
 * cold-start budget that has not yet been measured; see README.md).
 */
import type { Plugin } from "@opencode-ai/plugin";

type Intent = "session_start" | "drift_check" | "pre_compact" | "post_tool_use";

interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

// Interpreter resolution (BUG-2921): a bare `python` fails silently (fail-open,
// exit 127) under a minimal hook-process PATH. Mirror the shell adapters'
// LL_PYTHON → python3 → python chain. Bun.which returns null (never throws) when
// a name is not on PATH, so the final literal preserves the prior behavior.
// Resolved once at module scope — the plugin factory is long-lived, so there is
// no reason to re-probe PATH on every hook event.
const PY =
  process.env.LL_PYTHON ?? Bun.which("python3") ?? Bun.which("python") ?? "python";

const spawnIntent = async (
  intent: Intent,
  payload: unknown,
  cwd: string,
): Promise<SpawnResult> => {
  const proc = Bun.spawn([PY, "-m", "little_loops.hooks", intent], {
    cwd,
    env: { ...process.env, LL_HOOK_HOST: "opencode" },
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

const plugin: Plugin = async (ctx) => ({
  "session.created": async (input: unknown) => {
    const { stdout, stderr, exitCode } = await spawnIntent(
      "session_start",
      input,
      ctx.directory,
    );
    if (stderr) console.error(stderr);
    if (exitCode === 2) {
      // session_start blocking is not the documented success path, but mirror
      // the dispatcher contract: exit_code=2 means "block + inject feedback".
      throw new Error(stderr || "session_start blocked");
    }
    // Second sequential dispatch (ENH-2888): drift_check is advisory-only and
    // always exits 0, so its stdout/stderr are surfaced but never block or
    // override session_start's return value.
    const driftResult = await spawnIntent("drift_check", input, ctx.directory);
    if (driftResult.stderr) console.error(driftResult.stderr);
    return stdout ? JSON.parse(stdout) : undefined;
  },
  "session.compacted": async (input: unknown) => {
    const { stderr, exitCode } = await spawnIntent("pre_compact", input, ctx.directory);
    if (stderr) console.error(stderr);
    // pre_compact's success path is exit_code=2 with feedback-only; no return
    // value is consumed by OpenCode for this event.
    if (exitCode !== 0 && exitCode !== 2) {
      throw new Error(stderr || `pre_compact failed with exit ${exitCode}`);
    }
  },
  "tool.execute.after": async (input: unknown) => {
    // Fire-and-forget: do NOT await the spawned Promise. Stderr / exit code
    // are intentionally dropped — the handler (FEAT-1623) persists per-tool
    // byte metrics to .ll/history.db when ``analytics.enabled`` is set, so
    // OpenCode never blocks on a SQLite write. Consumers of the data layer
    // must tolerate observational-only semantics.
    void spawnIntent("post_tool_use", input, ctx.directory);
  },
});

export default plugin;
