"""Minimal OpenAI-compatible chat-completions client for ``OpenAIGenericRunner``.

Invoked as a subprocess by ``OpenAIGenericRunner.build_blocking_json`` with
``argv = [base_url, model, prompt]`` and the API key in the ``OPENAI_API_KEY``
environment variable. Prints a single ``{"result": ...}`` JSON envelope on
stdout that :func:`little_loops.host_runner.run_blocking_json` parses; writes
errors to stderr and exits non-zero so the caller surfaces them as
``BlockingJsonError(api_error=True)``.

stdlib only (``urllib.request``) — no third-party import in the child process,
so the interpreter that runs the host already satisfies it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_DEFAULT_TIMEOUT = 180


def _strip_fences(text: str) -> str:
    """Remove a single ```json / ``` fenced block if the model wrapped one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_verdict(content: str):
    """Best-effort: a dict when the model returned JSON, else the raw text."""
    text = _strip_fences(content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return parsed if isinstance(parsed, dict) else text


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: _openai_compat_client BASE_URL MODEL PROMPT", file=sys.stderr)
        return 2

    base_url, model, prompt = argv[1], argv[2], argv[3]
    api_key = os.environ.get("OPENAI_API_KEY", "")

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        print(f"upstream HTTP {exc.code}: {detail}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"upstream connection error: {exc.reason}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surface any transport failure
        print(f"client error: {exc}", file=sys.stderr)
        return 2

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("unexpected upstream response shape", file=sys.stderr)
        return 2

    print(json.dumps({"result": _extract_verdict(content)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
