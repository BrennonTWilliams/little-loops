#!/usr/bin/env bash
#
# check-private-refs.sh — Claude Code PreToolUse hook for private-codebase
# references.
#
# Validates the candidate content of a Write/Edit operation against
# ll-verify-private-refs BEFORE Claude mutates disk. This repo is public, and
# the most common way a private path lands in it is an agent pasting a run
# trace or an absolute path into an issue file. Catching it at the host layer
# complements the pre-commit gate (staged files) and the pytest gate
# (full-repo, baselined).
#
# gitleaks, already in .pre-commit-config.yaml, does not cover this: the leak is
# machine paths and project names, not credentials.
#
# Exit semantics (Claude Code PreToolUse contract — see
# hooks/adapters/claude-code/pre-tool-use.sh:7-13):
#   0 = allow (irrelevant tool/path, missing tools, or clean candidate)
#   2 = block (validator reported a private reference; message on stderr)
#
# Reads tool input from stdin (Claude Code native transport) or
# $CLAUDE_TOOL_INPUT as a fallback, stages the candidate content under a
# temporary root that mirrors the file's repo-relative path, and runs the
# validator against the staged copy. Validating the candidate rather than the
# current file is the whole point — it catches the reference before it is
# written, which the git and pytest belts cannot do.

set -euo pipefail

# ---------------------------------------------------------------------------
# Read tool input (stdin, with $CLAUDE_TOOL_INPUT fallback)
# ---------------------------------------------------------------------------

INPUT="${CLAUDE_TOOL_INPUT:-}"
if [[ -z "$INPUT" ]]; then
    INPUT=$(cat)
fi

if [[ -z "$INPUT" ]]; then
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "[little-loops] check-private-refs: python3 not on PATH; skipping host-side gate" >&2
    exit 0
fi

if ! command -v ll-verify-private-refs >/dev/null 2>&1; then
    echo "[little-loops] check-private-refs: ll-verify-private-refs not on PATH; skipping host-side gate (pre-commit and pytest gates still enforce)" >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Stage candidate content in a temporary root
# ---------------------------------------------------------------------------
#
# Status line on stdout:
#   "ok:<relpath>"  → staged candidate ready under $WORK_DIR/<relpath>
#   "skip:msg"      → irrelevant tool/path, allow silently
#   "error:msg"     → malformed input, allow silently with a stderr note
WORK_DIR=$(mktemp -d -t check-private-refs-XXXXXX 2>/dev/null || mktemp -d)
trap 'rm -rf "$WORK_DIR" 2>/dev/null || true' EXIT INT TERM

# NOTE: heredoc deliberately NOT wrapped in $(...) — macOS bash 3.2 mis-parses
# a heredoc inside command substitution (see check-decisions-yaml.sh:64-70).
INPUT="$INPUT" WORK_DIR="$WORK_DIR" python3 <<'PY' >"$WORK_DIR/.ll-status" 2>/dev/null || true
import json
import os
import sys

try:
    payload = json.loads(os.environ['INPUT'])
except Exception as exc:
    print(f"error:malformed-json ({exc})")
    sys.exit(0)

tool_name = payload.get('tool_name') or ''
tool_input = payload.get('tool_input') or {}
file_path = tool_input.get('file_path') or ''

if tool_name not in ('Write', 'Edit'):
    print('skip:not-write-or-edit')
    sys.exit(0)

if not file_path:
    print('skip:no-file-path')
    sys.exit(0)

cwd = os.getcwd()
abs_path = file_path if os.path.isabs(file_path) else os.path.join(cwd, file_path)
try:
    rel = os.path.relpath(abs_path, cwd)
except ValueError:
    print('skip:unrelated-path')
    sys.exit(0)

# Outside the repo, or inside a directory the checker excludes anyway.
if rel.startswith('..'):
    print('skip:outside-repo')
    sys.exit(0)

first = rel.replace('\\', '/').split('/')[0]
if first in ('postmortems', '.loops', 'thoughts', 'logs', '.git'):
    print(f'skip:excluded-dir ({first})')
    sys.exit(0)

if rel.replace('\\', '/') in ('.ll/ll-continue-prompt.md', '.ll/private-refs.local.txt'):
    print(f'skip:excluded-file ({rel})')
    sys.exit(0)

# Binary-ish targets are not worth staging.
if os.path.splitext(rel)[1].lower() in ('.png', '.jpg', '.jpeg', '.gif', '.pdf',
                                        '.zip', '.db', '.sqlite', '.pyc'):
    print('skip:binary-target')
    sys.exit(0)

work_dir = os.environ['WORK_DIR']
staged = os.path.join(work_dir, rel)
os.makedirs(os.path.dirname(staged) or work_dir, exist_ok=True)

if tool_name == 'Write':
    content = tool_input.get('content') or ''
    with open(staged, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print(f'ok:{rel}')
    sys.exit(0)

# tool_name == 'Edit' — reconstruct the post-Edit result from the current file
if not os.path.isfile(abs_path):
    print('skip:edit-target-missing')
    sys.exit(0)

with open(abs_path, 'rb') as fh:
    current = fh.read()

old_string = tool_input.get('old_string') or ''
new_string = tool_input.get('new_string')
if new_string is None:
    new_string = ''
replace_all = bool(tool_input.get('replace_all', False))

old_bytes = old_string.encode('utf-8')
new_bytes = new_string.encode('utf-8')

if not old_string or current.count(old_bytes) == 0:
    # Can't reconstruct. Do NOT fall back to validating the current file: the
    # existing corpus is grandfathered by the baseline, so a pre-existing
    # reference would block an unrelated edit. Allow and let the pre-commit and
    # pytest gates cover it.
    print('skip:edit-not-reconstructible')
    sys.exit(0)

if replace_all:
    result = current.replace(old_bytes, new_bytes)
else:
    result = current.replace(old_bytes, new_bytes, 1)

# Only the added text is the agent's contribution. Staging the whole file would
# re-report grandfathered references elsewhere in it and block the edit for a
# line the agent never touched.
with open(staged, 'wb') as fh:
    fh.write(new_bytes)
print(f'ok:{rel}')
PY
STATUS="$(cat "$WORK_DIR/.ll-status" 2>/dev/null || true)"

case "$STATUS" in
    skip:*)
        echo "[little-loops] check-private-refs: ${STATUS#skip:}" >&2
        exit 0
        ;;
    error:*)
        echo "[little-loops] check-private-refs: ${STATUS#error:}" >&2
        exit 0
        ;;
    ok:*)
        REL="${STATUS#ok:}"
        ;;
    *)
        echo "[little-loops] check-private-refs: unexpected status '$STATUS'" >&2
        exit 0
        ;;
esac

# ---------------------------------------------------------------------------
# Run the validator against the staged candidate
# ---------------------------------------------------------------------------
#
# -C "$WORK_DIR" so relative-path resolution and exclusion checks see the
# mirrored layout. The local patterns file lives in the real repo, so point the
# staged root at it by copying when present.
if [[ -f ".ll/private-refs.local.txt" ]]; then
    mkdir -p "$WORK_DIR/.ll"
    cp ".ll/private-refs.local.txt" "$WORK_DIR/.ll/private-refs.local.txt" 2>/dev/null || true
fi

set +e
VALIDATION_OUTPUT="$(ll-verify-private-refs -C "$WORK_DIR" "$REL" 2>&1)"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
    while IFS= read -r line; do
        echo "[little-loops] private-refs gate: ${line}" >&2
    done <<<"$VALIDATION_OUTPUT"

    # Redirect, don't dead-end. Without this the block only says "use a
    # repo-relative path", so the likely response is to strip the path and write
    # to the repo root anyway — satisfying the checker while defeating the
    # convention that put run forensics in postmortems/.
    #
    # Gated on `git check-ignore` rather than a repo name: hooks/ ships with the
    # plugin, and suggesting postmortems/ inside a consuming project — where it
    # is not ignored — would get the file committed, reintroducing the very leak
    # the convention prevents. Checking the ignore rule means the hint appears
    # only where the convention actually exists, including for anyone who adopts
    # it downstream.
    #
    # No filename globs (audit-loop-run-*, *-findings*): guessing future filename
    # shapes is brittle. "Root-level markdown that isn't a standard root doc" is
    # a stabler discriminator, and since this only prints inside an
    # already-triggered block, a false positive costs one hedged line.
    if [[ "$REL" != */* && "$REL" == *.md ]]; then
        case "$REL" in
            README.md|CHANGELOG.md|CONTRIBUTING.md|AGENTS.md)
                : # a real root doc — the fix is to remove the path, not move the file
                ;;
            *)
                if git check-ignore -q postmortems 2>/dev/null; then
                    echo "[little-loops] private-refs gate: If this is a loop-run postmortem, write it to" >&2
                    echo "[little-loops] private-refs gate: postmortems/ instead — gitignored, source-repo-only." >&2
                fi
                ;;
        esac
    fi

    exit 2
fi

exit 0
