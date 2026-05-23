/**
 * OpenCode adapter for little-loops hook intents.
 *
 * Mirrors the shape of hooks/adapters/claude-code/{session-start,precompact}.sh:
 * spawn `python -m little_loops.hooks <intent>`, pipe the host event payload as
 * JSON to stdin, propagate stdout/stderr/exit-code back to OpenCode. No logic
 * lives here; the adapter is purely a transport. Host identity is conveyed via
 * the LL_HOOK_HOST environment variable so the Python dispatcher constructs
 * LLHookEvent with host="opencode".
 *
 * MVP scope: session.created → session_start, session.compacted → pre_compact.
 * tool.execute.after → post_tool_use is wired as fire-and-forget (no `await`
 * on spawnIntent) per FEAT-1489 — zero user-visible latency cost.
 * tool.execute.before is still deferred (blocking pre-tool requires a
 * cold-start budget that has not yet been measured; see README.md).
 */
import type { Plugin } from "@opencode-ai/plugin";

type Intent = "session_start" | "pre_compact" | "post_tool_use";

interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

const spawnIntent = async (
  intent: Intent,
  payload: unknown,
  cwd: string,
): Promise<SpawnResult> => {
  const proc = Bun.spawn(["python", "-m", "little_loops.hooks", intent], {
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
      ctx.cwd,
    );
    if (stderr) console.error(stderr);
    if (exitCode === 2) {
      // session_start blocking is not the documented success path, but mirror
      // the dispatcher contract: exit_code=2 means "block + inject feedback".
      throw new Error(stderr || "session_start blocked");
    }
    return stdout ? JSON.parse(stdout) : undefined;
  },
  "session.compacted": async (input: unknown) => {
    const { stderr, exitCode } = await spawnIntent("pre_compact", input, ctx.cwd);
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
    // byte metrics to .ll/session.db when ``analytics.enabled`` is set, so
    // OpenCode never blocks on a SQLite write. Consumers of the data layer
    // must tolerate observational-only semantics.
    void spawnIntent("post_tool_use", input, ctx.cwd);
  },
});

export default plugin;
