#!/usr/bin/env python3
"""AutoFigure wrapper for the adversarial-redesign loop.

Optional dependency: AutoFigure (https://github.com/ResearAI/AutoFigure)
Install: pip install -e ./AutoFigure && playwright install chromium
API key: set OPENROUTER_API_KEY (or AUTOFIGURE_API_KEY) in env.

Emits JSON to stdout: {"svg_path": "...", "final_score": 8.5, "iteration": 1}
The final_score is AutoFigure's quality metric on a 1–10 scale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--concept", required=True, help="Natural-language description of the figure")
    p.add_argument("--output", required=True, help="Path for the generated SVG file")
    p.add_argument(
        "--critique-file", help="JSON file with complaints from the previous critic round"
    )
    p.add_argument(
        "--result-file", help="Also write result JSON to this path (stdout is always written)"
    )
    p.add_argument(
        "--iteration", type=int, default=1, help="Iteration number embedded in result JSON"
    )
    return p.parse_args()


def build_description(concept: str, critique_file: str | None) -> str:
    """Append critique constraints to the concept description when a critique file is provided."""
    if not critique_file:
        return concept
    path = Path(critique_file)
    if not path.exists():
        return concept
    critique = json.loads(path.read_text())
    complaints = critique.get("complaints", [])
    if not complaints:
        return concept
    constraints = "\n".join(f"- {c}" for c in complaints)
    return f"{concept}\n\nAddress these specific issues in the new diagram:\n{constraints}"


def generate_figure(description: str, output_path: Path) -> float:
    """Call AutoFigure to generate an SVG and return its quality score (1–10).

    Raises ImportError if AutoFigure is not installed; the caller prints a
    friendly message before propagating.
    """
    try:
        from autofigure import AutoFigureAgent  # type: ignore[import]
    except ImportError as exc:
        print(
            "ERROR: AutoFigure is not installed.\n"
            "Install it with: pip install -e ./AutoFigure && playwright install chromium\n"
            "Then set OPENROUTER_API_KEY in your environment.",
            file=sys.stderr,
        )
        raise exc

    agent = AutoFigureAgent()
    result = agent.generate(description=description, output_path=str(output_path))

    # AutoFigure result attribute names vary by version; try each in order.
    for attr in ("final_score", "score", "quality_score"):
        val = getattr(result, attr, None)
        if val is not None:
            return float(val)
    return 5.0  # fallback if the attribute isn't found


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    description = build_description(args.concept, args.critique_file)
    final_score = generate_figure(description, output_path)

    result = {
        "svg_path": str(output_path.resolve()),
        "final_score": final_score,
        "iteration": args.iteration,
    }
    result_json = json.dumps(result)
    print(result_json)
    if args.result_file:
        Path(args.result_file).write_text(result_json)


if __name__ == "__main__":
    main()
