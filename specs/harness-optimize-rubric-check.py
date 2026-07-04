#!/usr/bin/env python3
"""Mechanical checker for specs/harness-optimize-rubric.md.

Scores the harness-optimize loop on every rubric dimension (A1..H4) plus the
premise-validity sentinel (S1..S4), from external signals only: exit codes,
floats, JSONL artifacts, and git objects. No LLM self-grades.

Output contract (final lines, rubric-router compatible):
    DIMENSION: <id> <name>: <STATUS> (w=<n>) -- <evidence>
    SENTINEL: <STATE> -- <triggers>
    PREMISE: delta=.. tokens_ratio=.. n=.. age_days=..
    COVERAGE: <int>%
    AGGREGATE: <int 0-100>

Exit codes: 0 pass | 1 gating failure | 3 sentinel BREAKING/BROKEN.

Stdlib-only. `pyyaml` is used opportunistically for graph checks (E1) and
degrades to a regex scan when absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASS, PARTIAL, FAIL, SKIP, NA = "PASS", "PARTIAL", "FAIL", "SKIP", "NA"
SCORE = {PASS: 1.0, PARTIAL: 0.5, FAIL: 0.0}

YES_VERDICTS = {"yes", "target", "progress", "true", "pass"}


@dataclass
class Dim:
    id: str
    name: str
    weight: int
    status: str
    evidence: str
    gating: bool = False

    @property
    def evaluated(self) -> bool:
        return self.status in SCORE

    @property
    def score(self) -> float:
        return SCORE.get(self.status, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "weight": self.weight,
            "status": self.status, "score": self.score if self.evaluated else None,
            "gating": self.gating, "evidence": self.evidence,
        }


@dataclass
class Ctx:
    """Shared parsed telemetry."""
    args: argparse.Namespace
    repo: Path
    traj_files: list[Path] = field(default_factory=list)
    traj_lines: list[tuple[Path, dict]] = field(default_factory=list)  # valid lines
    traj_invalid: int = 0
    traj_total: int = 0
    runs: list[dict] = field(default_factory=list)  # per history run: {name, verdicts:{state:[bool]}, first_gate}
    ab: list[dict] = field(default_factory=list)    # sorted oldest->newest: {path, mtime, summary, n, host}
    accepted: list[dict] = field(default_factory=list)  # accepted traj lines with resolvable order
    loop_yaml_text: str = ""
    loop_yaml: Any = None  # parsed dict or None


# ---------------------------------------------------------------- helpers

def run(cmd: list[str] | str, cwd: Path, timeout: int = 120,
        use_shell: bool = False) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), shell=use_shell, timeout=timeout,
            capture_output=True, text=True,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "<timeout>"
    except OSError as e:
        return 127, f"<oserror: {e}>"


def git(ctx: Ctx, *args: str, timeout: int = 60) -> tuple[int, str]:
    return run(["git", "-C", str(ctx.repo), *args], ctx.repo, timeout)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return ((c - m) / d, (c + m) / d)


def fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- loaders

TRAJ_GLOBS = [
    ".ll/runs/*/states/*/trajectory.jsonl",
    ".ll/runs/*/trajectory.jsonl",
    ".loops/runs/*/states/*/trajectory.jsonl",
    ".loops/runs/*/*/states/*/trajectory.jsonl",
]
REQ_KEYS = {"iter": int, "score": (int, float), "accepted": bool, "commit_sha": str}


def load_trajectories(ctx: Ctx) -> None:
    seen: set[Path] = set()
    for pat in TRAJ_GLOBS:
        for f in ctx.repo.glob(pat):
            if f in seen or not f.is_file():
                continue
            seen.add(f)
    ctx.traj_files = sorted(seen, key=lambda f: f.stat().st_mtime)
    for f in ctx.traj_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            ctx.traj_total += 1
            try:
                d = json.loads(line)
                ok = isinstance(d, dict) and all(
                    isinstance(d.get(k), t) and not (k != "iter" and isinstance(d.get(k), bool) and t is not bool)
                    for k, t in REQ_KEYS.items()
                )
                # bool is an int subclass; require iter to be a real int, not bool
                if ok and isinstance(d.get("iter"), bool):
                    ok = False
                if ok:
                    ctx.traj_lines.append((f, d))
                else:
                    ctx.traj_invalid += 1
            except (json.JSONDecodeError, TypeError):
                ctx.traj_invalid += 1
    ctx.accepted = [d for _, d in ctx.traj_lines if d["accepted"] and d["commit_sha"]]


def load_events(ctx: Ctx) -> None:
    hist = ctx.repo / ".loops" / ".history"
    if not hist.is_dir():
        return
    suffix = f"-{ctx.args.loop}"
    for run_dir in sorted(d for d in hist.iterdir() if d.is_dir() and d.name.endswith(suffix)):
        ef = run_dir / "events.jsonl"
        if not ef.is_file():
            continue
        verdicts: dict[str, list[bool]] = {}
        raw_verdicts: dict[str, list[str]] = {}
        cur: str | None = None
        first_gate: str | None = None
        try:
            lines = ef.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "state_enter":
                cur = ev.get("state")
            elif ev.get("event") == "evaluate" and cur:
                v = str(ev.get("verdict", "")).lower()
                verdicts.setdefault(cur, []).append(v in YES_VERDICTS)
                raw_verdicts.setdefault(cur, []).append(v)
                if cur == ctx.args.gate_state and first_gate is None:
                    first_gate = v
        ctx.runs.append({"name": run_dir.name, "verdicts": verdicts,
                         "raw": raw_verdicts, "first_gate": first_gate})


def load_ab(ctx: Ctx) -> None:
    found: dict[Path, float] = {}
    for root in (ctx.repo / ".loops", ctx.repo / ".ll"):
        if root.is_dir():
            for f in root.rglob("ab.json"):
                try:
                    found[f] = f.stat().st_mtime
                except OSError:
                    continue
    for f, mtime in sorted(found.items(), key=lambda kv: kv[1]):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = data.get("summary", data if "delta" in data else {})
        if "delta" not in summary:
            continue
        ctx.ab.append({
            "path": f, "mtime": mtime, "summary": summary,
            "n": len(data.get("items", [])),
            "host": data.get("host") or summary.get("host"),
        })


def load_loop_yaml(ctx: Ctx) -> None:
    p = Path(ctx.args.loop_yaml)
    if not p.is_absolute():
        p = ctx.repo / p
    if p.is_file():
        ctx.loop_yaml_text = p.read_text(encoding="utf-8", errors="replace")
        try:
            import yaml  # type: ignore
            ctx.loop_yaml = yaml.safe_load(ctx.loop_yaml_text)
        except Exception:
            ctx.loop_yaml = None


def pooled_variance(ctx: Ctx, state: str) -> tuple[int, int]:
    """Return (pass_count, total) pooled across runs for a state."""
    k = t = 0
    for r in ctx.runs:
        vs = r["verdicts"].get(state, [])
        k += sum(vs)
        t += len(vs)
    return k, t


# ---------------------------------------------------------------- A: scorer

def scorer_cmd(ctx: Ctx) -> str | None:
    if not ctx.args.scorer:
        return None
    return f"{ctx.args.scorer} {ctx.args.tasks_dir or ''}".strip()


def run_scorer_once(ctx: Ctx, tasks_dir: str | None = None) -> tuple[int, float | None, str]:
    cmd = f"{ctx.args.scorer} {tasks_dir if tasks_dir is not None else (ctx.args.tasks_dir or '')}".strip()
    rc, out = run(cmd, ctx.repo, timeout=ctx.args.scorer_timeout, use_shell=True)
    val: float | None = None
    tail = out.strip().splitlines()[-1].strip() if out.strip() else ""
    try:
        val = float(tail)
    except ValueError:
        val = None
    return rc, val, tail


def dim_a1(ctx: Ctx) -> Dim:
    if not scorer_cmd(ctx):
        return Dim("A1", "scorer contract", 5, SKIP, "no --scorer supplied", gating=True)
    rc, val, tail = run_scorer_once(ctx)
    if rc == 0 and val is not None:
        return Dim("A1", "scorer contract", 5, PASS, f"exit 0, float {fmt(val)}", gating=True)
    return Dim("A1", "scorer contract", 5, FAIL,
               f"exit {rc}, last stdout line {tail!r} (need exit 0 + bare float)", gating=True)


def dim_a2(ctx: Ctx, a1: Dim) -> Dim:
    if a1.status == SKIP:
        return Dim("A2", "scorer noise floor", 6, SKIP, "no --scorer supplied", gating=True)
    if a1.status == FAIL:
        return Dim("A2", "scorer noise floor", 6, FAIL, "blocked by A1 contract failure", gating=True)
    vals: list[float] = []
    for _ in range(ctx.args.noise_k):
        rc, val, _ = run_scorer_once(ctx)
        if rc == 0 and val is not None:
            vals.append(val)
    if len(vals) < 2:
        return Dim("A2", "scorer noise floor", 6, FAIL, f"only {len(vals)}/{ctx.args.noise_k} valid samples", gating=True)
    sigma = statistics.stdev(vals)
    tol = ctx.args.tolerance
    ev = f"sigma={fmt(sigma)} over k={len(vals)} (floor={fmt(tol / 2)}, tolerance={fmt(tol)})"
    if sigma <= tol / 2:
        return Dim("A2", "scorer noise floor", 6, PASS, ev, gating=True)
    if sigma <= tol:
        return Dim("A2", "scorer noise floor", 6, PARTIAL, ev, gating=True)
    return Dim("A2", "scorer noise floor", 6, FAIL, ev + " — gate promotes noise", gating=True)


def dim_a3(ctx: Ctx) -> Dim:
    scores = [d["score"] for _, d in ctx.traj_lines]
    if len(scores) < 10:
        return Dim("A3", "scorer dynamic range", 4, SKIP, f"{len(scores)} trajectory lines (<10)")
    distinct = len({fmt(float(s)) for s in scores})
    ev = f"{distinct} distinct score values over {len(scores)} lines"
    return Dim("A3", "scorer dynamic range", 4, PASS if distinct >= 2 else FAIL, ev)


def dim_a4(ctx: Ctx) -> Dim:
    heldout = ctx.args.heldout_dir
    if not heldout and ctx.args.tasks_dir:
        cand = Path(str(ctx.args.tasks_dir).rstrip("/") + ".heldout")
        if not cand.is_absolute():
            cand = ctx.repo / cand
        heldout = str(cand) if cand.is_dir() else None
    if not heldout:
        return Dim("A4", "held-out separation", 5, FAIL,
                   "no held-out task set (--heldout-dir or <tasks_dir>.heldout) — hardcoding is undetectable")
    if not ctx.args.scorer:
        return Dim("A4", "held-out separation", 5, PARTIAL, f"held-out exists at {heldout}; unmeasured (no --scorer)")
    rc_t, v_t, _ = run_scorer_once(ctx)
    rc_h, v_h, _ = run_scorer_once(ctx, tasks_dir=heldout)
    if rc_t != 0 or v_t is None or rc_h != 0 or v_h is None:
        return Dim("A4", "held-out separation", 5, FAIL, "scorer failed on tuning or held-out set")
    gap = v_t - v_h
    ev = f"tuning={fmt(v_t)} heldout={fmt(v_h)} gap={fmt(gap)} (cap={fmt(ctx.args.heldout_gap)})"
    return Dim("A4", "held-out separation", 5, PASS if gap <= ctx.args.heldout_gap else FAIL, ev)


# ---------------------------------------------------------------- B: gate

def dim_b1_b2(ctx: Ctx) -> tuple[Dim, Dim]:
    if not shutil.which("ll-loop"):
        return (Dim("B1", "validator clean of ERRORs", 6, SKIP, "ll-loop not on PATH", gating=True),
                Dim("B2", "warnings clean or justified", 2, SKIP, "ll-loop not on PATH"))
    rc, out = run(["ll-loop", "validate", ctx.args.loop, "--json"], ctx.repo, timeout=180)
    b1 = Dim("B1", "validator clean of ERRORs", 6, PASS if rc == 0 else FAIL,
             f"ll-loop validate exit {rc} (ERRORs force exit 1)", gating=True)
    warn_count: int | None = None
    try:
        payload = json.loads(out[out.index("{"):] if "{" in out else out)
        items = payload if isinstance(payload, list) else (
            payload.get("findings") or payload.get("warnings") or payload.get("results") or [])
        if isinstance(items, list):
            warn_count = sum(1 for i in items
                             if isinstance(i, dict) and "warn" in str(i.get("severity", i.get("level", ""))).lower())
    except (ValueError, json.JSONDecodeError, AttributeError):
        warn_count = None
    if warn_count is None:
        warn_count = len(re.findall(r"\bWARN(?:ING)?\b", out))
        src = "text scan"
    else:
        src = "json"
    ev = f"{warn_count} warnings ({src})"
    status = PASS if warn_count == 0 else (PARTIAL if warn_count <= 2 else FAIL)
    return b1, Dim("B2", "warnings clean or justified", 2, status, ev)


def dim_b3(ctx: Ctx) -> Dim:
    k, t = pooled_variance(ctx, ctx.args.gate_state)
    if t < 10:
        return Dim("B3", "gate discrimination", 6, SKIP,
                   f"{t} gate verdicts (<10) across {len(ctx.runs)} runs")
    p = k / t
    var = p * (1 - p)
    lo, hi = wilson_ci(k, t)
    ev = f"pass_rate={fmt(p)} variance={fmt(var)} n={t} CI=[{fmt(lo)},{fmt(hi)}] (floor=0.05)"
    return Dim("B3", "gate discrimination", 6, PASS if var >= 0.05 else FAIL, ev)


def dim_b4(ctx: Ctx) -> Dim:
    recent_files = ctx.traj_files[-10:]
    lines = [d for f, d in ctx.traj_lines if f in set(recent_files)]
    if len(lines) < 10:
        return Dim("B4", "acceptance-rate band", 4, SKIP, f"{len(lines)} lines in trailing window (<10)")
    a = sum(1 for d in lines if d["accepted"]) / len(lines)
    ev = f"acceptance={fmt(a)} over {len(lines)} lines (band [0.15,0.85]; P1 predicts ~0.5)"
    return Dim("B4", "acceptance-rate band", 4, PASS if 0.15 <= a <= 0.85 else FAIL, ev)


def dim_b5(ctx: Ctx) -> Dim:
    if not ctx.traj_lines:
        return Dim("B5", "revert/commit integrity", 5, SKIP, "no trajectory lines", gating=True)
    bad: list[str] = []
    checked = 0
    for _, d in ctx.traj_lines:
        if d["accepted"]:
            sha = d["commit_sha"]
            if not sha:
                bad.append(f"iter {d['iter']}: accepted with empty sha")
                continue
            if checked < 50:
                checked += 1
                rc, _ = git(ctx, "cat-file", "-e", f"{sha}^{{commit}}")
                if rc != 0:
                    bad.append(f"iter {d['iter']}: sha {sha[:12]} unresolvable")
                    continue
                rc, subj = git(ctx, "log", "-1", "--format=%s", sha)
                if rc == 0 and "harness-optimize" not in subj:
                    bad.append(f"iter {d['iter']}: subject {subj.strip()!r}")
        elif d["commit_sha"]:
            bad.append(f"iter {d['iter']}: rejected but sha non-empty")
    if bad:
        return Dim("B5", "revert/commit integrity", 5, FAIL,
                   f"{len(bad)} violations, e.g. {bad[0]}", gating=True)
    return Dim("B5", "revert/commit integrity", 5, PASS,
               f"{len(ctx.traj_lines)} lines conform ({checked} shas resolved)", gating=True)


def dim_b6(ctx: Ctx) -> Dim:
    tol = ctx.args.tolerance
    drops: list[str] = []
    files_with_chain = 0
    per_file: dict[Path, list[float]] = {}
    for f, d in ctx.traj_lines:
        if d["accepted"]:
            per_file.setdefault(f, []).append(float(d["score"]))
    for f, chain in per_file.items():
        if len(chain) < 2:
            continue
        files_with_chain += 1
        for prev, curr in zip(chain, chain[1:]):
            if curr < prev - tol:
                drops.append(f"{f.name}: {fmt(prev)}→{fmt(curr)}")
    if files_with_chain == 0:
        return Dim("B6", "accepted-chain monotonicity", 3, SKIP, "no file with ≥2 accepted lines")
    if drops:
        return Dim("B6", "accepted-chain monotonicity", 3, FAIL, f"{len(drops)} drops, e.g. {drops[0]}")
    return Dim("B6", "accepted-chain monotonicity", 3, PASS, f"{files_with_chain} chains non-decreasing (tol={fmt(tol)})")


# ---------------------------------------------------------------- C: trajectory

def dim_c1(ctx: Ctx) -> Dim:
    if ctx.traj_total == 0:
        return Dim("C1", "trajectory schema validity", 3, SKIP, "no trajectory files")
    valid = ctx.traj_total - ctx.traj_invalid
    rate = valid / ctx.traj_total
    ev = f"{valid}/{ctx.traj_total} lines valid ({fmt(rate * 100)}%)"
    return Dim("C1", "trajectory schema validity", 3, PASS if rate >= 0.99 else FAIL, ev)


def _propose_action_text(ctx: Ctx) -> str:
    if isinstance(ctx.loop_yaml, dict):
        st = (ctx.loop_yaml.get("states") or {}).get("propose") or {}
        return str(st.get("action", ""))
    m = re.search(r"^  propose:\n(.*?)(?=^  \w|\Z)", ctx.loop_yaml_text, re.M | re.S)
    return m.group(1) if m else ""


def dim_c2(ctx: Ctx) -> Dim:
    if not ctx.loop_yaml_text:
        return Dim("C2", "cumulative feed-forward ledger", 4, SKIP, "loop YAML not found")
    text = _propose_action_text(ctx)
    hits = [w for w in ("trajectory", "rejected", "ledger", "tried") if w in text.lower()]
    if hits:
        return Dim("C2", "cumulative feed-forward ledger", 4, PASS, f"propose references {hits}")
    return Dim("C2", "cumulative feed-forward ledger", 4, FAIL,
               "propose receives only baseline/last-score — no rejected-edit ledger (guide § feed the trajectory forward)")


def dim_c3(ctx: Ctx) -> Dim:
    snaps: list[Path] = []
    for root in (ctx.repo / ".ll" / "runs", ctx.repo / ".loops" / "runs"):
        if root.is_dir():
            snaps.extend(root.rglob("candidates/iter-*.txt"))
    if not snaps:
        return Dim("C3", "duplicate re-proposal rate", 3, SKIP,
                   "no candidate snapshots (unlocked by C2 remediation)")
    # map iter -> accepted per run dir
    rejected_hashes: list[str] = []
    for s in snaps:
        m = re.search(r"iter-(\d+)", s.name)
        if not m:
            continue
        it = int(m.group(1))
        run_root = s.parent.parent
        accepted = None
        for f, d in ctx.traj_lines:
            if run_root in f.parents and d["iter"] == it:
                accepted = d["accepted"]
                break
        if accepted is False:
            norm = re.sub(r"\s+", " ", s.read_text(encoding="utf-8", errors="replace")).strip()
            rejected_hashes.append(hashlib.sha256(norm.encode()).hexdigest())
    if not rejected_hashes:
        return Dim("C3", "duplicate re-proposal rate", 3, SKIP, "no snapshots mappable to rejected iterations")
    dups = len(rejected_hashes) - len(set(rejected_hashes))
    rate = dups / len(rejected_hashes)
    ev = f"dup-rate={fmt(rate)} over {len(rejected_hashes)} rejected candidates (cap={fmt(ctx.args.dup_rate)})"
    return Dim("C3", "duplicate re-proposal rate", 3, PASS if rate <= ctx.args.dup_rate else FAIL, ev)


# ---------------------------------------------------------------- D: proposal

def accepted_shas(ctx: Ctx, limit: int = 50) -> list[str]:
    shas: list[str] = []
    for _, d in ctx.traj_lines:
        if d["accepted"] and d["commit_sha"] and d["commit_sha"] not in shas:
            shas.append(d["commit_sha"])
    return shas[-limit:]


def commit_files(ctx: Ctx, sha: str) -> list[str]:
    rc, out = git(ctx, "show", "--name-only", "--format=", sha)
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def dim_d1(ctx: Ctx) -> Dim:
    shas = accepted_shas(ctx)
    if not shas:
        return Dim("D1", "blast radius", 3, SKIP, "no accepted commits")
    declared = set(shlex.split(ctx.args.targets)) if ctx.args.targets else None
    baseline_set: set[str] | None = declared
    leaks: list[str] = []
    for sha in shas:
        files = set(commit_files(ctx, sha))
        if not files:
            continue
        if baseline_set is None:
            baseline_set = files
            continue
        extra = files - baseline_set
        if extra:
            leaks.append(f"{sha[:10]}: +{sorted(extra)[:3]}")
    mode = "declared --targets" if declared else "first-commit heuristic"
    if leaks:
        return Dim("D1", "blast radius", 3, FAIL, f"{len(leaks)} leaks ({mode}), e.g. {leaks[0]}")
    return Dim("D1", "blast radius", 3, PASS, f"{len(shas)} commits within {mode}")


def dim_d2(ctx: Ctx) -> Dim:
    shas = accepted_shas(ctx, limit=30)
    if not shas:
        return Dim("D2", "diff economy", 2, SKIP, "no accepted commits")
    added: list[int] = []
    for sha in shas:
        rc, out = git(ctx, "show", "--numstat", "--format=", sha)
        if rc != 0:
            continue
        total = 0
        for ln in out.splitlines():
            parts = ln.split("\t")
            if len(parts) >= 2 and parts[0].isdigit():
                total += int(parts[0])
        added.append(total)
    if not added:
        return Dim("D2", "diff economy", 2, SKIP, "numstat unavailable")
    med, mx = statistics.median(added), max(added)
    ev = f"median_added={med} max={mx} over {len(added)} commits (caps {ctx.args.diff_median}/{ctx.args.diff_max})"
    if med <= ctx.args.diff_median and mx <= ctx.args.diff_max:
        return Dim("D2", "diff economy", 2, PASS, ev)
    if med <= ctx.args.diff_median:
        return Dim("D2", "diff economy", 2, PARTIAL, ev)
    return Dim("D2", "diff economy", 2, FAIL, ev)


PATH_RE = re.compile(r"`([\w][\w./-]*\.(?:py|md|yaml|yml|json|sh|toml))`")
CLI_RE = re.compile(r"\b(ll-[a-z][a-z0-9-]+)\b")


def dim_d3(ctx: Ctx) -> Dim:
    shas = accepted_shas(ctx, limit=20)
    if not shas:
        return Dim("D3", "dangling-reference rate", 3, SKIP, "no accepted commits")
    known_cli: set[str] = set()
    pj = ctx.repo / "scripts" / "pyproject.toml"
    if pj.is_file():
        known_cli = set(re.findall(r"^(ll-[a-z0-9-]+)\s*=", pj.read_text(encoding="utf-8"), re.M))
    dangling: list[str] = []
    for sha in shas:
        rc, out = git(ctx, "show", "-U0", "--format=", sha)
        if rc != 0:
            continue
        for ln in out.splitlines():
            if not ln.startswith("+") or ln.startswith("+++"):
                continue
            for path in PATH_RE.findall(ln):
                rc2, _ = git(ctx, "cat-file", "-e", f"HEAD:{path}")
                if rc2 != 0 and not (ctx.repo / path).exists():
                    dangling.append(f"{sha[:10]}: `{path}`")
            for cli in CLI_RE.findall(ln):
                if known_cli and cli not in known_cli:
                    dangling.append(f"{sha[:10]}: {cli}")
    if dangling:
        return Dim("D3", "dangling-reference rate", 3, FAIL,
                   f"{len(dangling)} dangling refs, e.g. {dangling[0]}")
    return Dim("D3", "dangling-reference rate", 3, PASS, f"0 dangling refs across {len(shas)} commits")


GUARD_RE = re.compile(r"^-\s*(max_steps|max_iterations|timeout|target_score|tolerance)\s*:", re.M)
GUARD_ADD_RE = re.compile(r"^\+\s*(max_steps|max_iterations|timeout|target_score|tolerance)\s*:", re.M)


def dim_d4(ctx: Ctx) -> Dim:
    shas = accepted_shas(ctx, limit=30)
    if not shas:
        return Dim("D4", "guardrail preservation", 3, SKIP, "no accepted commits")
    yaml_touched = False
    stripped: list[str] = []
    for sha in shas:
        rc, out = git(ctx, "show", "-U0", "--format=", sha, "--", "*.yaml", "*.yml")
        if rc != 0 or not out.strip():
            continue
        yaml_touched = True
        removed = set(GUARD_RE.findall(out))
        added = set(GUARD_ADD_RE.findall(out))
        for key in removed - added:
            stripped.append(f"{sha[:10]}: removed {key}")
    if not yaml_touched:
        return Dim("D4", "guardrail preservation", 3, NA, "no loop-YAML targets among accepted commits")
    if stripped:
        return Dim("D4", "guardrail preservation", 3, FAIL, f"{len(stripped)} strips, e.g. {stripped[0]}")
    return Dim("D4", "guardrail preservation", 3, PASS, "no guardrail keys removed")


# ---------------------------------------------------------------- E: diagnosis

EDGE_KEYS = ("next", "on_yes", "on_no", "on_error", "on_partial", "on_blocked", "on_rate_limit_exhausted")


def dim_e1(ctx: Ctx) -> Dim:
    if not ctx.loop_yaml_text:
        return Dim("E1", "diagnose state on cycle", 4, SKIP, "loop YAML not found")
    if not isinstance(ctx.loop_yaml, dict):
        has = "COMPONENT=" in ctx.loop_yaml_text or re.search(r"diagnos", ctx.loop_yaml_text, re.I)
        return Dim("E1", "diagnose state on cycle", 4, PARTIAL if has else FAIL,
                   "yaml lib unavailable — regex scan " + ("found" if has else "found no") + " diagnose contract")
    states: dict = ctx.loop_yaml.get("states") or {}
    diag = {n for n, s in states.items()
            if re.search(r"diagnos", n, re.I) or "COMPONENT=" in str((s or {}).get("action", ""))}
    if not diag:
        return Dim("E1", "diagnose state on cycle", 4, FAIL,
                   "no diagnose state; propose self-selects its target (canonical shape: diagnose is initial + loopback)")
    def edges(name: str) -> list[str]:
        s = states.get(name) or {}
        out = [str(s[k]) for k in EDGE_KEYS if isinstance(s.get(k), str)]
        route = s.get("route")
        if isinstance(route, dict):
            out += [str(v) for v in route.values() if isinstance(v, str)]
        return [e for e in out if e in states]
    commit_states = [n for n, s in states.items()
                     if "git commit" in str((s or {}).get("action", "")) or re.search(r"commit", n, re.I)]
    off_cycle = []
    for cs in commit_states:
        # flag if propose is reachable from the commit loopback while avoiding all diagnose states
        seen: set[str] = set()
        frontier = edges(cs)
        while frontier:
            nxt = frontier.pop()
            if nxt in seen:
                continue
            seen.add(nxt)
            if nxt in diag:
                continue  # path passes through diagnose — good; don't expand past it
            if nxt == "propose":
                off_cycle.append(cs)
                break
            frontier.extend(edges(nxt))
    if off_cycle:
        return Dim("E1", "diagnose state on cycle", 4, PARTIAL,
                   f"diagnose exists ({sorted(diag)}) but loopback from {off_cycle} reaches propose without it")
    return Dim("E1", "diagnose state on cycle", 4, PASS, f"diagnose states {sorted(diag)} on every commit loopback")


def _diagnosis_snaps(ctx: Ctx) -> list[Path]:
    out: list[Path] = []
    for root in (ctx.repo / ".ll" / "runs", ctx.repo / ".loops" / "runs"):
        if root.is_dir():
            out.extend(root.rglob("diagnosis/iter-*.txt"))
    return sorted(out, key=lambda p: p.stat().st_mtime)


COMPONENT_RE = re.compile(r"^COMPONENT=(prompt|tool|memory|workflow)\s*$", re.M)


def dim_e2(ctx: Ctx) -> tuple[Dim, list[str]]:
    snaps = _diagnosis_snaps(ctx)
    if not snaps:
        return Dim("E2", "diagnosis commitment contract", 3, SKIP,
                   "no diagnosis snapshots (unlocked by E1 remediation)"), []
    comps: list[str] = []
    misses = 0
    for s in snaps:
        text = s.read_text(encoding="utf-8", errors="replace")
        m = COMPONENT_RE.search(text)
        if m:
            comps.append(m.group(1))
        else:
            misses += 1
    ev = f"{len(comps)}/{len(snaps)} snapshots match ^COMPONENT=(prompt|tool|memory|workflow)$"
    return Dim("E2", "diagnosis commitment contract", 3, PASS if misses == 0 else FAIL, ev), comps


def dim_e3(ctx: Ctx, e2: Dim, comps: list[str]) -> Dim:
    if e2.status == SKIP:
        return Dim("E3", "component-coverage entropy", 1, SKIP, "E2 skipped")
    tail = comps[-10:]
    distinct = len(set(tail))
    ev = f"{distinct} distinct components in trailing {len(tail)} diagnoses"
    return Dim("E3", "component-coverage entropy", 1, PASS if distinct >= 2 else FAIL, ev)


# ---------------------------------------------------------------- F: budget

def dim_f1(ctx: Ctx) -> Dim:
    flat: list[str] = []
    any_measured = False
    for state in sorted({s for r in ctx.runs for s in r["verdicts"]}):
        k, t = pooled_variance(ctx, state)
        if t < 10:
            continue
        any_measured = True
        p = k / t
        if p * (1 - p) < 0.05:
            flat.append(f"{state} (p={fmt(p)}, n={t})")
    if not any_measured:
        return Dim("F1", "evaluator-wide discrimination", 3, SKIP, "no evaluator state with ≥10 verdicts")
    if flat:
        return Dim("F1", "evaluator-wide discrimination", 3, FAIL, f"toothless: {', '.join(flat)}")
    return Dim("F1", "evaluator-wide discrimination", 3, PASS, "all measured evaluator states variance ≥ 0.05")


def dim_f2(ctx: Ctx) -> Dim:
    per_file_max: list[int] = []
    per_file: dict[Path, int] = {}
    for f, d in ctx.traj_lines:
        if d["accepted"]:
            per_file[f] = max(per_file.get(f, 0), int(d["iter"]))
    per_file_max = sorted(per_file.values())
    if len(per_file_max) < 5:
        return Dim("F2", "budget vs yield curve", 2, SKIP, f"{len(per_file_max)} runs with acceptances (<5)")
    p90 = per_file_max[min(len(per_file_max) - 1, math_ceil(0.9 * len(per_file_max)) - 1)]
    max_iter = ctx.args.max_iterations
    if max_iter is None:
        max_iter = 30
        if isinstance(ctx.loop_yaml, dict):
            try:
                max_iter = int((ctx.loop_yaml.get("context") or {}).get("max_iterations", 30))
            except (TypeError, ValueError):
                pass
    cap = math_ceil(ctx.args.budget_factor * p90)
    ev = f"p90(last accepted iter)={p90}, max_iterations={max_iter}, cap={ctx.args.budget_factor}×p90={cap}"
    return Dim("F2", "budget vs yield curve", 2, PASS if max_iter <= cap else FAIL, ev)


def math_ceil(x: float) -> int:
    return int(-(-x // 1))


def dim_f3(ctx: Ctx) -> Dim:
    cutoff = time.time() - ctx.args.cost_max_age * 86400
    for ab in reversed(ctx.ab):
        if ab["mtime"] >= cutoff and ab["summary"].get("median_tokens_harness", 0) > 0:
            age = (time.time() - ab["mtime"]) / 86400
            return Dim("F3", "cost telemetry present", 2, PASS,
                       f"ab.json {age:.0f}d old, median_tokens_harness={ab['summary']['median_tokens_harness']}")
    return Dim("F3", "cost telemetry present", 2, FAIL,
               f"no ab.json ≤{ctx.args.cost_max_age}d with token counts — H3 and sentinel S4 are blind")


# ---------------------------------------------------------------- G: isolation

def dim_g1(ctx: Ctx) -> Dim:
    if not ctx.traj_files:
        return Dim("G1", "no cross-run trajectory append", 2, SKIP, "no trajectory files")
    collisions: list[str] = []
    per_file: dict[Path, list[int]] = {}
    for f, d in ctx.traj_lines:
        per_file.setdefault(f, []).append(int(d["iter"]))
    for f, iters in per_file.items():
        for prev, curr in zip(iters, iters[1:]):
            if curr < prev:
                collisions.append(f"{f.name}: iter {prev}→{curr}")
                break
    if collisions:
        return Dim("G1", "no cross-run trajectory append", 2, FAIL,
                   f"{len(collisions)} files with restarting iter (cross-run append), e.g. {collisions[0]}")
    return Dim("G1", "no cross-run trajectory append", 2, PASS, f"{len(per_file)} files monotonic")


def dim_g2(ctx: Ctx) -> Dim:
    shas = accepted_shas(ctx)
    if not shas:
        return Dim("G2", "resume continuity", 3, SKIP, "no accepted commits")
    # newest accepted commit = topological tip of the accepted set (clock-independent);
    # merge-base --independent returns commits not reachable from any other candidate
    cand = shas[-20:]
    rc, out = git(ctx, "merge-base", "--independent", *cand)
    tips = out.split()

    def ctime(sha: str) -> int:
        rc2, o = git(ctx, "show", "-s", "--format=%ct", sha)
        return int(o.strip()) if rc2 == 0 and o.strip().isdigit() else -1

    if rc == 0 and tips:
        last = tips[0] if len(tips) == 1 else max(tips, key=ctime)
    else:
        last = max(cand, key=ctime)
    drift: list[str] = []
    for path in commit_files(ctx, last):
        rc, blob = git(ctx, "rev-parse", f"{last}:{path}")
        if rc != 0:
            continue
        wt = ctx.repo / path
        if not wt.is_file():
            drift.append(f"{path} missing from worktree")
            continue
        rc2, cur = git(ctx, "hash-object", "--", path)
        if rc2 == 0 and cur.strip() != blob.strip():
            drift.append(f"{path} drifted from {last[:10]}")
    if drift:
        return Dim("G2", "resume continuity", 3, FAIL, f"{len(drift)} files, e.g. {drift[0]}")
    return Dim("G2", "resume continuity", 3, PASS, f"worktree matches last accepted commit {last[:10]}")


def dim_g3(ctx: Ctx) -> Dim:
    targets: list[str] = shlex.split(ctx.args.targets) if ctx.args.targets else []
    if not targets:
        union: set[str] = set()
        for sha in accepted_shas(ctx, limit=10):
            union.update(commit_files(ctx, sha))
        targets = sorted(union)
    if not targets:
        return Dim("G3", "clean-tree invariant", 1, SKIP, "targets unknown (no --targets, no accepted commits)")
    rc, out = git(ctx, "status", "--porcelain", "--", *targets)
    dirty = [ln for ln in out.splitlines() if ln.strip()]
    if rc != 0:
        return Dim("G3", "clean-tree invariant", 1, SKIP, "git status failed")
    if dirty:
        return Dim("G3", "clean-tree invariant", 1, FAIL, f"{len(dirty)} dirty target paths, e.g. {dirty[0].strip()}")
    return Dim("G3", "clean-tree invariant", 1, PASS, f"{len(targets)} target paths clean")


# ---------------------------------------------------------------- H: transfer

def dim_h1(ctx: Ctx) -> Dim:
    if not ctx.ab:
        return Dim("H1", "fresh baseline A/B", 3, FAIL,
                   "no ab.json anywhere — premise accounting has no data (run: ll-loop run "
                   f"{ctx.args.loop} --baseline)", gating=True)
    age = (time.time() - ctx.ab[-1]["mtime"]) / 86400
    ev = f"latest ab.json {age:.0f}d old (max {ctx.args.ab_max_age}d): {ctx.ab[-1]['path'].name}"
    return Dim("H1", "fresh baseline A/B", 3, PASS if age <= ctx.args.ab_max_age else FAIL, ev, gating=True)


def dim_h2(ctx: Ctx) -> Dim:
    if not ctx.ab:
        return Dim("H2", "harness lift", 4, SKIP, "no ab.json (H1 already failing)")
    ab = ctx.ab[-1]
    delta, n = ab["summary"]["delta"], ab["n"]
    ev = (f"delta={fmt(delta)} n={n} harness={fmt(ab['summary'].get('harness_pass_rate', -1))} "
          f"baseline={fmt(ab['summary'].get('baseline_pass_rate', -1))}")
    if delta >= ctx.args.lift and n >= 10:
        return Dim("H2", "harness lift", 4, PASS, ev)
    if delta > ctx.args.tolerance:
        return Dim("H2", "harness lift", 4, PARTIAL, ev + f" (need delta≥{fmt(ctx.args.lift)} at n≥10)")
    return Dim("H2", "harness lift", 4, FAIL,
               ev + f" — delta ≤ tolerance {fmt(ctx.args.tolerance)}: indistinguishable from noise")


def dim_h3(ctx: Ctx) -> Dim:
    if not ctx.ab:
        return Dim("H3", "cost-adjusted lift", 3, SKIP, "no ab.json")
    s = ctx.ab[-1]["summary"]
    mt_h, mt_b, delta = s.get("median_tokens_harness", 0), s.get("median_tokens_baseline", 0), s["delta"]
    if mt_b <= 0:
        return Dim("H3", "cost-adjusted lift", 3, SKIP, "baseline token count missing/zero")
    ratio = mt_h / mt_b
    ev = f"token_ratio={fmt(ratio)} delta={fmt(delta)} (caps: ratio≤{fmt(ctx.args.token_ratio)} or delta≥{fmt(ctx.args.strong_lift)})"
    if ratio <= ctx.args.token_ratio or delta >= ctx.args.strong_lift:
        return Dim("H3", "cost-adjusted lift", 3, PASS, ev)
    if ratio <= ctx.args.token_ratio_hard:
        return Dim("H3", "cost-adjusted lift", 3, PARTIAL, ev)
    return Dim("H3", "cost-adjusted lift", 3, FAIL, ev + " — harness is overhead-dominant")


def dim_h4(ctx: Ctx) -> Dim:
    hosted = [ab for ab in ctx.ab if ab.get("host")]
    hosts = {ab["host"] for ab in hosted}
    if len(hosts) < 2:
        return Dim("H4", "cross-host stability", 2, NA,
                   "fewer than 2 hosts in ab.json history (single-host install or host field absent)")
    latest_by_host = {}
    for ab in hosted:
        latest_by_host[ab["host"]] = ab["summary"]["delta"]
    signs = {h: (d > 0) for h, d in latest_by_host.items()}
    if len(set(signs.values())) > 1:
        return Dim("H4", "cross-host stability", 2, FAIL,
                   f"ordering reversal: {latest_by_host} — improvement is host-specific")
    return Dim("H4", "cross-host stability", 2, PASS, f"delta sign agrees across {sorted(hosts)}")


# ---------------------------------------------------------------- sentinel

@dataclass
class Sentinel:
    state: str
    triggers: list[str]
    signals: dict[str, Any]


def compute_sentinel(ctx: Ctx, dims: dict[str, Dim]) -> Sentinel:
    sig: dict[str, Any] = {}
    trig: list[str] = []

    # S1: first-iteration saturation over trailing W runs with gate activity
    runs_with_gate = [r for r in ctx.runs if r["first_gate"] is not None][-ctx.args.window:]
    if runs_with_gate:
        sat = sum(1 for r in runs_with_gate if r["first_gate"] == "target") / len(runs_with_gate)
        sig["S1_saturation_rate"] = round(sat, 3)
        sig["S1_n_runs"] = len(runs_with_gate)
    else:
        sat = None
        sig["S1_saturation_rate"] = None

    # S2: gate collapse toward always-accept
    k, t = pooled_variance(ctx, ctx.args.gate_state)
    s2 = False
    if t >= 10:
        p = k / t
        s2 = p >= 0.95 and p * (1 - p) < 0.05
        sig["S2_gate_pass_rate"] = round(p, 3)
        sig["S2_n"] = t
    sig["S2_collapse"] = s2

    # S3: consecutive A/B parity probes (n>=10 each)
    s3k = 0
    for ab in reversed(ctx.ab):
        if ab["n"] >= 10 and (ab["summary"]["delta"] <= ctx.args.tolerance or ab["summary"]["delta"] < 0):
            s3k += 1
        else:
            break
    sig["S3_parity_streak"] = s3k

    # S4: fleet delta decay
    probes = ctx.ab[-5:]
    s4 = False
    if len(probes) >= 3:
        xs = list(range(len(probes)))
        ys = [p["summary"]["delta"] for p in probes]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
        s4 = slope < 0 and ys[-1] < 0.10
        sig["S4_slope"] = round(slope, 4)
        sig["S4_latest_delta"] = round(ys[-1], 3)
    sig["S4_decay"] = s4

    s1_hi = sat is not None and sat >= 0.8
    s1_mid = sat is not None and sat >= 0.5
    if s1_mid:
        trig.append(f"S1 saturation={fmt(sat)} (n={sig['S1_n_runs']})")
    if s2:
        trig.append(f"S2 gate collapse (p={sig.get('S2_gate_pass_rate')}, n={sig.get('S2_n')})")
    if s3k:
        trig.append(f"S3 parity streak={s3k} (delta≤{fmt(ctx.args.tolerance)} at n≥10)")
    if s4:
        trig.append(f"S4 delta decay (slope={sig.get('S4_slope')}, latest={sig.get('S4_latest_delta')})")

    # instrument health: FAIL (not SKIP) on A2/A3/B1 is evidence of breakage
    unhealthy = any(dims[i].status == FAIL for i in ("A2", "A3", "B1") if i in dims)

    if len(ctx.runs) < 5 and not ctx.ab:
        return Sentinel("INSUFFICIENT_DATA", [f"{len(ctx.runs)} runs, 0 ab.json probes"], sig)
    if (s1_mid or s2) and unhealthy:
        bad = [i for i in ("A2", "A3", "B1") if dims.get(i) and dims[i].status == FAIL]
        return Sentinel("INSTRUMENT_FAILURE", trig + [f"instruments failing: {bad} — premise inference suspended"], sig)
    if s3k >= 2 and (s1_hi or s2):
        return Sentinel("BROKEN", trig, sig)
    if s3k >= 2 or (s3k == 1 and (s1_mid or s2 or s4)):
        return Sentinel("BREAKING", trig, sig)
    if s1_mid or s2 or s3k == 1 or s4:
        return Sentinel("WATCH", trig, sig)
    return Sentinel("HEALTHY", trig or ["no premise-decay signals"], sig)


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", help="repo root")
    p.add_argument("--loop", default="harness-optimize")
    p.add_argument("--loop-yaml", default="scripts/little_loops/loops/harness-optimize.yaml")
    p.add_argument("--gate-state", default="gate")
    p.add_argument("--scorer", default=None, help="scorer command (enables A1/A2/A4 live probes)")
    p.add_argument("--tasks-dir", default=None)
    p.add_argument("--heldout-dir", default=None)
    p.add_argument("--targets", default=None, help="space-separated declared target files")
    p.add_argument("--json", dest="json_out", default=None, help="write scorecard JSON here")
    # thresholds (see spec § 8)
    p.add_argument("--tolerance", type=float, default=0.02)
    p.add_argument("--noise-k", type=int, default=5)
    p.add_argument("--scorer-timeout", type=int, default=600)
    p.add_argument("--heldout-gap", type=float, default=0.15)
    p.add_argument("--diff-median", type=int, default=120)
    p.add_argument("--diff-max", type=int, default=400)
    p.add_argument("--dup-rate", type=float, default=0.20)
    p.add_argument("--budget-factor", type=float, default=1.5)
    p.add_argument("--max-iterations", type=int, default=None)
    p.add_argument("--ab-max-age", type=int, default=30)
    p.add_argument("--cost-max-age", type=int, default=90)
    p.add_argument("--lift", type=float, default=0.05)
    p.add_argument("--strong-lift", type=float, default=0.15)
    p.add_argument("--token-ratio", type=float, default=3.0)
    p.add_argument("--token-ratio-hard", type=float, default=5.0)
    p.add_argument("--window", type=int, default=10)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repo root", file=sys.stderr)
        return 2
    ctx = Ctx(args=args, repo=repo)
    load_trajectories(ctx)
    load_events(ctx)
    load_ab(ctx)
    load_loop_yaml(ctx)

    dims: list[Dim] = []
    a1 = dim_a1(ctx); dims.append(a1)
    dims.append(dim_a2(ctx, a1))
    dims.append(dim_a3(ctx))
    dims.append(dim_a4(ctx))
    b1, b2 = dim_b1_b2(ctx); dims += [b1, b2]
    dims += [dim_b3(ctx), dim_b4(ctx), dim_b5(ctx), dim_b6(ctx)]
    dims += [dim_c1(ctx), dim_c2(ctx), dim_c3(ctx)]
    dims += [dim_d1(ctx), dim_d2(ctx), dim_d3(ctx), dim_d4(ctx)]
    dims.append(dim_e1(ctx))
    e2, comps = dim_e2(ctx); dims.append(e2)
    dims.append(dim_e3(ctx, e2, comps))
    dims += [dim_f1(ctx), dim_f2(ctx), dim_f3(ctx)]
    dims += [dim_g1(ctx), dim_g2(ctx), dim_g3(ctx)]
    dims += [dim_h1(ctx), dim_h2(ctx), dim_h3(ctx), dim_h4(ctx)]

    by_id = {d.id: d for d in dims}
    sentinel = compute_sentinel(ctx, by_id)

    evaluated = [d for d in dims if d.evaluated]
    total_w = sum(d.weight for d in dims)
    eval_w = sum(d.weight for d in evaluated)
    aggregate = round(100 * sum(d.weight * d.score for d in evaluated) / eval_w) if eval_w else 0
    gating_fails = [d for d in dims if d.gating and d.status == FAIL]
    if gating_fails:
        aggregate = min(aggregate, 49)
    coverage = round(100 * eval_w / total_w)

    for d in dims:
        gate_tag = " [GATING]" if d.gating else ""
        print(f"DIMENSION: {d.id} {d.name}: {d.status} (w={d.weight}){gate_tag} — {d.evidence}")
    print(f"SENTINEL: {sentinel.state} — {'; '.join(sentinel.triggers)}")
    if ctx.ab:
        s = ctx.ab[-1]["summary"]
        ratio = (s.get("median_tokens_harness", 0) / s["median_tokens_baseline"]
                 if s.get("median_tokens_baseline") else None)
        age = (time.time() - ctx.ab[-1]["mtime"]) / 86400
        print(f"PREMISE: delta={fmt(s['delta'])} tokens_ratio={fmt(ratio) if ratio else 'n/a'} "
              f"n={ctx.ab[-1]['n']} age_days={age:.0f}")
    else:
        print("PREMISE: no ab.json — unmeasured")
    print(f"COVERAGE: {coverage}%")
    print(f"AGGREGATE: {aggregate}")

    if args.json_out:
        scorecard = {
            "loop": args.loop, "aggregate": aggregate, "coverage": coverage,
            "gating_failures": [d.id for d in gating_fails],
            "sentinel": {"state": sentinel.state, "triggers": sentinel.triggers,
                         "signals": sentinel.signals},
            "dimensions": [d.to_dict() for d in dims],
            "telemetry": {"trajectory_lines": ctx.traj_total, "runs": len(ctx.runs),
                          "ab_probes": len(ctx.ab)},
        }
        out = Path(args.json_out)
        if not out.is_absolute():
            out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")

    if gating_fails:
        return 1
    if sentinel.state in ("BREAKING", "BROKEN"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
