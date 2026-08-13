#!/usr/bin/env bash
#
# Qwen Code adapter for the Stop hook — legacy script resolver.
#
# Qwen fires Stop when the assistant finishes responding (every turn in
# interactive mode, once per ``qwen -p`` run). The Claude plugin wires the
# legacy ``hooks/scripts/context-handoff-sentinel.sh`` +
# ``hooks/scripts/session-cleanup.sh`` here; there is no ``stop`` intent in
# the Python dispatch table, so this shim resolves and runs those scripts
# directly when the Claude-plugin root is available (CLAUDE_PLUGIN_ROOT or
# LL_PLUGIN_ROOT). Those scripts are NOT wheel-packaged (EPIC-2279 manifest),
# so pip-installed environments degrade to a no-op — stale-ref cleanup is
# still covered by the session_end intent (interactive) and the next
# session's SessionStart sweep (the Claude workaround posture).
#
# This is a cleanup path: it must NEVER fail and must stay fast.
#
export LL_HOOK_HOST=qwen
INPUT=$(cat)
PAYLOAD_CWD=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then cd "$PAYLOAD_CWD" || true; fi

ROOT="${CLAUDE_PLUGIN_ROOT:-${LL_PLUGIN_ROOT:-}}"
SENTINEL="$ROOT/hooks/scripts/context-handoff-sentinel.sh"
CLEANUP="$ROOT/hooks/scripts/session-cleanup.sh"

if [ -n "$ROOT" ] && [ -f "$SENTINEL" ]; then
    printf '%s' "$INPUT" | bash "$SENTINEL" >/dev/null 2>&1 || true
fi
if [ -n "$ROOT" ] && [ -f "$CLEANUP" ]; then
    printf '%s' "$INPUT" | bash "$CLEANUP" >/dev/null 2>&1 || true
fi
exit 0
