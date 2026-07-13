"""SessionStart hook handler: load config + apply ``.ll/ll.local.md`` overrides.

Python port of ``hooks/scripts/session-start.sh`` (FEAT-1450). The ``handle``
function is invoked by the dispatcher in
``little_loops.hooks.__init__::main_hooks`` after the Claude Code adapter
(``hooks/adapters/claude-code/session-start.sh``) reads the host's stdin
payload.

Observable side-effects preserved from the bash version:

1. Removes ``.ll/ll-context-state.json`` from the prior session (best-effort).
2. Resolves the project config via :func:`little_loops.config.core.resolve_config_path`.
3. If ``.ll/ll.local.md`` exists, parses its YAML frontmatter with
   ``yaml.safe_load`` and deep-merges it into the base config — arrays
   replace, explicit ``None`` removes keys.
4. Emits the rendered config JSON via ``LLHookResult.stdout`` so Claude Code
   ingests it as session context.
5. Composes stderr feedback covering the ``Config loaded`` line, the optional
   ``Local overrides applied`` line, a ``Warning: Large config`` line when the
   rendered config exceeds 5000 chars, the ``Warning: No config found`` line
   when neither candidate exists, and feature-flag validation warnings for
   ``sync.enabled`` / ``documents.enabled``.

The bash version had a stdout/stderr inconsistency for the no-config warning;
this port chooses stderr in both branches (per the issue's Step-resolved
decision).
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from little_loops.config.core import deep_merge, resolve_config_path
from little_loops.hooks.types import LLHookEvent, LLHookResult

logger = logging.getLogger(__name__)

_LOCAL_OVERRIDE_FILE = Path(".ll/ll.local.md")
_PRIOR_SESSION_STATE = Path(".ll/ll-context-state.json")
_LARGE_CONFIG_THRESHOLD = 5000


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter (arbitrary nested shapes) from a markdown doc.

    Mirrors the bash version's behaviour: returns ``{}`` for any malformed or
    missing frontmatter, and uses ``yaml.safe_load`` so nested dicts / lists /
    explicit nulls survive. Not interchangeable with
    ``little_loops.frontmatter.parse_frontmatter`` (which is a key:value subset
    parser) — local-override frontmatter needs full YAML.
    """
    if not content or not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    text = parts[1].strip()
    if not text:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def handle(event: LLHookEvent) -> LLHookResult:
    """Build the merged session-start config and validate feature flags.

    Returns ``LLHookResult(exit_code=0, feedback=<stderr>, stdout=<config-json>)``.
    """
    # ENH-1945: _run_backfill() consumes transcript_path from the payload for
    # non-Claude-Code hosts (Codex, OpenCode). The event object must be preserved
    # so the backfill daemon thread can read it.

    cwd = Path.cwd()
    feedback_lines: list[str] = []

    # 1. Clean up prior-session state (best-effort, suppress all errors).
    with contextlib.suppress(OSError):
        _PRIOR_SESSION_STATE.unlink()

    # 2. Resolve base config.
    config_path = resolve_config_path(cwd)
    base_config: dict[str, Any] = {}
    if config_path is not None:
        try:
            base_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base_config = {}

    # 3. Apply local overrides if present.
    local_file = cwd / _LOCAL_OVERRIDE_FILE
    overrides_applied = False
    merged_config: dict[str, Any] = base_config
    if local_file.is_file():
        try:
            override_text = local_file.read_text(encoding="utf-8")
        except OSError:
            override_text = ""
        local_overrides = _parse_frontmatter(override_text)
        if local_overrides:
            merged_config = deep_merge(base_config, local_overrides)
            overrides_applied = True

    # 3b. Bootstrap the unified session store (FEAT-1112). Best-effort and only
    # for initialized projects — uninitialized projects (no config) are a no-op
    # so the hook never creates a stray .ll/ directory.
    _project_context_block = ""
    if config_path is not None:
        with contextlib.suppress(Exception):
            from little_loops.session_store import ensure_db, resolve_history_db

            ensure_db(resolve_history_db(cwd / ".ll" / "history.db"))

        # ENH-1830 / BUG-1882: trigger incremental JSONL backfill in a detached
        # subprocess so it outlives the short-lived hook process. A daemon thread
        # is killed when the hook subprocess exits (typically in <0.5s), so it
        # never commits. Path discovery runs synchronously here (fast) to produce
        # the concrete path arg passed to the worker.
        import os as _os

        _db_path = (
            Path(_os.environ["LL_HISTORY_DB"])
            if _os.environ.get("LL_HISTORY_DB")
            else cwd / ".ll" / "history.db"
        )

        with contextlib.suppress(Exception):
            from little_loops.user_messages import get_project_folder

            # ENH-1945: consume transcript_path from hook payload when available.
            payload = event.payload or {}
            _transcript = (payload.get("transcript_path") or "").strip()
            if _transcript and Path(_transcript).is_file():
                _backfill_path: str | None = _transcript
            else:
                _pf = get_project_folder(cwd)
                _backfill_path = str(_pf) if _pf is not None else None

            if _backfill_path is not None and not _os.environ.get("LL_NON_INTERACTIVE"):
                # ENH-2581: pass --rebuild only when SCHEMA_VERSION has advanced past
                # the last rebuild() run, so the (expensive) cache-table rebuild is
                # opt-in-on-migration rather than run on every session start.
                _worker_argv = [
                    sys.executable,
                    "-m",
                    "little_loops.cli.backfill_worker",
                    str(_db_path),
                    _backfill_path,
                ]
                with contextlib.suppress(Exception):
                    from little_loops.session_store import SCHEMA_VERSION, connect

                    _rebuild_conn = connect(_db_path)
                    try:
                        _row = _rebuild_conn.execute(
                            "SELECT value FROM meta WHERE key = 'last_rebuild_version'"
                        ).fetchone()
                    finally:
                        _rebuild_conn.close()
                    _last_rebuild_version = int(_row[0]) if (_row and _row[0]) else 0
                    if _last_rebuild_version < SCHEMA_VERSION:
                        _worker_argv.append("--rebuild")

                subprocess.Popen(
                    _worker_argv,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(cwd),
                )

        # ENH-1907: Inject project-context digest (best-effort, opt-in).
        # Runs after the backfill thread launches so the digest reflects only
        # already-persisted rows from prior sessions, not this session's backfill.
        # ENH-2040: Gate reads the dataclass attribute so the default (True) is
        # respected when no history block is present in the merged config dict.
        with contextlib.suppress(Exception):
            from little_loops.config.features import HistoryConfig

            _hist = HistoryConfig.from_dict(merged_config.get("history", {}))
            _sd = _hist.session_digest
            if _sd.enabled:
                from little_loops.history_reader import project_digest, render_project_context

                # An empty sections list (the config default) renders all providers;
                # a non-empty list restricts/orders the output (see project_digest).
                _digest = project_digest(_db_path, days=_sd.days, sections=_sd.sections)
                _project_context_block = render_project_context(
                    _digest, char_cap=_sd.char_cap, days=_sd.days
                )

    # 4. Compose the rendered stdout payload.
    if config_path is not None and not overrides_applied:
        # Match bash: preserve original on-disk formatting when no overrides.
        try:
            stdout_payload: str | None = config_path.read_text(encoding="utf-8")
        except OSError:
            stdout_payload = json.dumps(merged_config, indent=2)
    elif config_path is not None or overrides_applied:
        stdout_payload = json.dumps(merged_config, indent=2)
    else:
        stdout_payload = None

    # Append project-context block (ENH-1907) if populated.
    if _project_context_block:
        if stdout_payload is not None:
            stdout_payload = stdout_payload + "\n\n" + _project_context_block
        else:
            stdout_payload = _project_context_block

    # 5. Compose feedback (stderr).
    if config_path is not None:
        # Match bash output format: print() uses a space separator, not a colon-space.
        feedback_lines.append(f"[little-loops] Config loaded: {config_path}")
        if overrides_applied:
            feedback_lines.append(f"[little-loops] Local overrides applied from: {local_file}")
        if stdout_payload is not None and len(stdout_payload) > _LARGE_CONFIG_THRESHOLD:
            feedback_lines.append(
                f"[little-loops] Warning: Large config ({len(stdout_payload)} chars)"
            )
    else:
        feedback_lines.append("[little-loops] Warning: No config found. Run ll-init to create one.")

    # 6. Feature-flag validation warnings.
    feedback_lines.extend(_validate_features(merged_config))

    feedback = "\n".join(feedback_lines) if feedback_lines else None
    return LLHookResult(exit_code=0, feedback=feedback, stdout=stdout_payload)


def _validate_features(config: dict[str, Any]) -> list[str]:
    """Return stderr warning lines for misconfigured enabled features.

    Mirrors ``validate_enabled_features`` in the bash version exactly:

    - ``sync.enabled: true`` with empty ``sync.github`` → warn.
    - ``documents.enabled: true`` with empty ``documents.categories`` → warn.

    Other ``*.enabled`` flags (e.g. ``product.enabled``) are intentionally not
    validated — the existing ``TestSessionStartValidation`` test fixture
    enables ``product`` and asserts no ``Warning:`` substring appears.
    """
    warnings_out: list[str] = []
    sync = config.get("sync") if isinstance(config.get("sync"), dict) else {}
    if isinstance(sync, dict) and sync.get("enabled") is True:
        github = sync.get("github")
        if not isinstance(github, dict) or not github:
            warnings_out.append(
                "[little-loops] Warning: sync.enabled is true but sync.github is not configured"
            )
    documents = config.get("documents") if isinstance(config.get("documents"), dict) else {}
    if isinstance(documents, dict) and documents.get("enabled") is True:
        categories = documents.get("categories")
        if not isinstance(categories, dict) or not categories:
            warnings_out.append(
                "[little-loops] Warning: documents.enabled is true but no document categories"
                " configured"
            )
    design_tokens = (
        config.get("design_tokens") if isinstance(config.get("design_tokens"), dict) else {}
    )
    if isinstance(design_tokens, dict) and design_tokens.get("enabled") is True:
        from pathlib import Path

        token_path = Path(design_tokens.get("path", ".ll/design-tokens"))
        if not token_path.exists():
            warnings_out.append(
                "[little-loops] Warning: design_tokens.enabled is true but path"
                f" '{token_path}' does not exist"
            )
        else:
            # ENH-1768: warn when active profile is configured but missing.
            profiles_dir = design_tokens.get("profiles_dir") or "profiles"
            active = design_tokens.get("active", "default")
            profiles_root = token_path / profiles_dir
            if profiles_root.is_dir() and not (profiles_root / active).is_dir():
                warnings_out.append(
                    "[little-loops] Warning: design_tokens.active="
                    f"'{active}' but '{profiles_root / active}' does not exist"
                )
    return warnings_out
