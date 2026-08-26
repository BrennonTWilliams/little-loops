#!/usr/bin/env python3
"""BUG-3208 master-side hang watchdog.

Detects pytest master process hang by monitoring pytest.log for new
verbose-progress lines (`-v` PASSED/collecting markers). On no-progress,
captures /proc/<pid>/stack + /proc/<pid>/fd/ + /proc/<pid>/wchan, then
triggers faulthandler dump via SIGABRT at T+5min.

Two-snapshot protocol (T+2min, T+5min):
  Identical stacks at both snapshots -> hard deadlock
  Different stacks                 -> slow finalization, not dead

Tool choice rationale:
  /proc/<pid>/stack is preferred over py-spy because py-spy requires
  perf_event_open or ptrace that GH-hosted runners don't always grant, and
  silently fails empty when those are missing (no stderr, just empty dump
  that looks like a clean capture). /proc/<pid>/stack needs only PROC_FS
  access and yields a kernel-side stack enough to distinguish file-lock-
  blocked / I/O-blocked / userland-spinning / Python-lock-deadlock.
  faulthandler is engaged inside pytest's own Python interpreter via
  SIGABRT -- Python's faulthandler registers SIGABRT by default since 3.3,
  so sending SIGABRT triggers a Python-level traceback dump to stderr
  before the process aborts. No external dep.

QA-flag: py-spy-silent-fail-on-perf_event_open
"""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def proc_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def snapshot(out, pid, label):
    out.write("\n=== SNAPSHOT " + label + " @ " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")

    out.write("--- /proc/" + str(pid) + "/stack ---\n")
    try:
        with open("/proc/" + str(pid) + "/stack", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- /proc/" + str(pid) + "/status ---\n")
    try:
        with open("/proc/" + str(pid) + "/status", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- /proc/" + str(pid) + "/wchan ---\n")
    try:
        with open("/proc/" + str(pid) + "/wchan", "r") as f:
            out.write(f.read().strip() + "\n")
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- ls -la /proc/" + str(pid) + "/fd/ ---\n")
    try:
        result = subprocess.run(
            ["ls", "-la", "/proc/" + str(pid) + "/fd/"],
            capture_output=True, text=True, timeout=5,
        )
        out.write(result.stdout)
        if result.stderr:
            out.write("(stderr: " + result.stderr + ")\n")
    except (OSError, subprocess.TimeoutExpired) as e:
        out.write("(unavailable: " + str(e) + ")\n")


def main():
    ap = argparse.ArgumentParser(description="BUG-3208 master-side hang watchdog")
    ap.add_argument("--pid", type=int, required=True, help="pytest master PID")
    ap.add_argument("--stdout", required=True, help="pytest stdout log path")
    ap.add_argument("--out", required=True, help="snapshot output path")
    ap.add_argument("--snap1-at", type=int, default=120, help="first snapshot at N seconds no-progress")
    ap.add_argument("--snap2-at", type=int, default=300, help="second snapshot at N seconds no-progress")
    ap.add_argument("--abrt-at", type=int, default=420, help="SIGABRT pytest at N seconds no-progress (forces faulthandler dump)")
    ap.add_argument("--poll-interval", type=int, default=10)
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out = open(out_path, "w", buffering=1)
    out.write("=== BUG-3208 master-watchdog started at " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")
    out.write("   pid=" + str(args.pid) + " stdout=" + args.stdout + " snap1=" + str(args.snap1_at) + "s snap2=" + str(args.snap2_at) + "s abrt=" + str(args.abrt_at) + "s\n\n")

    last_line_count = 0
    last_progress_monotonic = time.monotonic()
    snap1_done = False
    snap2_done = False
    abrt_sent = False
    out.write("[" + time.strftime('%H:%M:%S', time.gmtime()) + "] watchdog alive; watching pid=" + str(args.pid) + "\n")

    while proc_alive(args.pid):
        # Progress signal: stdout line count growth
        try:
            with open(args.stdout, "r", errors="replace") as f:
                lines = f.readlines()
            line_count = len(lines)
        except OSError:
            line_count = 0

        if line_count > last_line_count:
            last_line_count = line_count
            last_progress_monotonic = time.monotonic()
            out.write("[" + time.strftime('%H:%M:%S', time.gmtime()) + "] progress: lines=" + str(line_count) + "\n")

        now = time.monotonic()
        no_progress = now - last_progress_monotonic

        if not snap1_done and no_progress >= args.snap1_at:
            snapshot(out, args.pid, label="1 (T+2min)")
            snap1_done = True

        if snap1_done and not snap2_done and no_progress >= args.snap2_at:
            snapshot(out, args.pid, label="2 (T+5min)")
            out.write("\n=== STACK DELTA snap1 vs snap2 ===\n")
            out.write("Manual diff required. Identical stacks -> hard deadlock.\n")
            out.write("Different stacks -> slow finalization, not dead.\n")
            snap2_done = True

        if snap2_done and not abrt_sent and no_progress >= args.abrt_at:
            out.write("\n=== SIGABRT to pid=" + str(args.pid) + " at T+" + str(int(no_progress)) + "s (forces faulthandler dump) ===\n")
            try:
                os.kill(args.pid, signal.SIGABRT)
                abrt_sent = True
                out.write("SIGABRT sent.\n")
            except OSError as e:
                out.write("SIGABRT failed: " + str(e) + "\n")

        time.sleep(args.poll_interval)

    out.write("\n=== pytest exited at " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")
    out.write("   final no-progress at exit: " + str(int(time.monotonic() - last_progress_monotonic)) + "s\n")
    out.write("   snap1_done=" + str(snap1_done) + " snap2_done=" + str(snap2_done) + " abrt_sent=" + str(abrt_sent) + "\n")
    out.close()


if __name__ == "__main__":
    main()
