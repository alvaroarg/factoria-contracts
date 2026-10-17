#!/usr/bin/env python3
"""External execution watchdog for a single OpenCode invocation.

Hard controls: no second attempt, time cap, initial SOURCE/TEST diff deadline.
OpenCode agent `steps` is additionally capped in each agent definition.  The
10-step-without-edit rule is a prompt rule; its step count is not independently
provable from every OpenCode JSON emitter.  The time-based kill IS enforceable.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

PROTECTED_PREFIXES = (
    ".git/", ".github/", ".opencode/", ".claude/", ".cursor/",
    "automation/opencode/", ".venv/", "venv/", "node_modules/", ".pytest_cache/",
    "__pycache__/", ".mypy_cache/", ".ruff_cache/", "dist/", "build/",
)
PROTECTED_NAMES = ("opencode.json", "AGENTS.md", "CLAUDE.md", ".env", "README.md")


def source_paths(base):
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", base, "HEAD"],
        ["git", "diff", "--name-only", "--diff-filter=ACMRT"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths = set()
    for cmd in commands:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=7, check=False)
            if p.returncode:
                return set()
        except (OSError, subprocess.TimeoutExpired):
            return set()
        for raw in p.stdout.splitlines():
            s = raw.strip().replace("\\", "/")
            if s and not s.startswith(PROTECTED_PREFIXES) and s.split("/")[-1] not in PROTECTED_NAMES:
                paths.add(s)
    return paths


def stop_tree(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def collect(stream, q):
    for line in iter(stream.readline, ""):
        q.put(line)
    q.put(None)


def event_detail(line, metrics):
    try:
        ev = json.loads(line)
    except (TypeError, ValueError):
        if re.search(r"429|rate.limit|quota.exceeded", line, flags=re.I):
            metrics["quota_error_observed"] = True
        return
    t = str(ev.get("type") or "")
    error_info = ev.get("error") or {}
    if t in ("error", "session.error", "message.error") and re.search(r"\b429\b|rate.limit|quota.exceeded", json.dumps(error_info), flags=re.I):
        metrics["quota_error_observed"] = True
    part = ev.get("part") or {}
    if not isinstance(part, dict):
        part = {}
    if t:
        metrics["event_types"][t] = metrics["event_types"].get(t, 0) + 1
    tool = str(part.get("tool") or ev.get("tool") or "")
    if tool:
        metrics["tools"][tool] = metrics["tools"].get(tool, 0) + 1
        if tool == "task":
            state = part.get("state")
            if not isinstance(state, dict):
                state = {}
            task_input = state.get("input") or part.get("input") or {}
            # Evidence hint only; exact JSON structure may change by release.
            if isinstance(task_input, dict):
                agent = str(task_input.get("subagent_type") or task_input.get("agent") or "")
                if agent:
                    metrics["task_agents"].append(agent[:70])
    if t in ("step_start", "step_finish", "step-start", "step-finish"):
        who = str(ev.get("agent") or part.get("agent") or "")
        if who == "build":
            metrics["unexpected_agent_observed"] = True
    if t in ("step_finish", "step-finish") or part.get("type") == "step-finish":
        metrics["step_events"] += 1
        # Aggregate only when OpenCode provided token usage; never invent values.
        tokens = part.get("tokens")
        if isinstance(tokens, dict):
            for k in ("input", "output", "reasoning"):
                if isinstance(tokens.get(k), (int, float)):
                    metrics["reported_tokens"][k] += int(tokens[k])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--issue", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--no-edit-seconds", type=int, default=360)
    p.add_argument("--total-seconds", type=int, default=1800)
    p.add_argument("--max-reported-input-tokens", type=int, default=800000)
    args = p.parse_args()
    issue = args.issue.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", issue):
        raise SystemExit("Invalid Jira issue key")
    branch = "agent/" + issue.lower()
    now_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip()
    if now_branch != branch:
        raise SystemExit("CONFIG_BLOCKED: wrong git branch before model launch")

    prompt_file = Path("automation/opencode/pilot-prompt.md")
    prompt = prompt_file.read_text(encoding="utf-8").replace("__ISSUE_KEY__", issue)
    prompt = prompt.replace("__GITHUB_REPOSITORY__", os.environ["GITHUB_REPOSITORY"])
    metrics = {"issue": issue, "agent": "factory-orchestrator", "builder_model": "opencode-go/deepseek-v4-pro",
               "reviewer_model": "opencode-go/kimi-k3", "initial_change_seen": False,
               "changed_paths": [], "stop_reason": "", "exit_code": None, "seconds": 0,
               "event_types": {}, "tools": {}, "task_agents": [], "step_events": 0,
               "reported_tokens": {"input": 0, "output": 0, "reasoning": 0},
               "quota_error_observed": False, "unexpected_agent_observed": False}
    cmd = ["opencode", "run", "--agent", "factory-orchestrator", "--model",
           "opencode-go/kimi-k3", "--format", "json", prompt]
    print("LAUNCH: factory-orchestrator / Kimi K3; builder DeepSeek V4 Pro; ONE invocation; no automatic retry", flush=True)
    q = queue.Queue()
    temp_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    raw_file = temp_dir / ("opencode-" + issue.lower() + "-events.jsonl")
    # Raw events often contain code and Jira spec. NEVER upload raw event file.
    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    thread = threading.Thread(target=collect, args=(proc.stdout, q), daemon=True)
    thread.start()
    exhausted = False
    with raw_file.open("w", encoding="utf-8") as raw:
        while True:
            elapsed = time.monotonic() - start
            changed = source_paths(args.base)
            if changed:
                metrics["initial_change_seen"] = True
                metrics["changed_paths"] = sorted(changed)[:100]
            if not metrics["initial_change_seen"] and elapsed > args.no_edit_seconds:
                metrics["stop_reason"] = "BLOCKED_NO_PROGRESS_TIMEBOUND"
                stop_tree(proc)
            elif elapsed > args.total_seconds:
                metrics["stop_reason"] = "BLOCKED_TOTAL_TIMEBOUND"
                stop_tree(proc)
            try:
                line = q.get(timeout=3)
            except queue.Empty:
                if proc.poll() is not None and not thread.is_alive():
                    break
                continue
            if line is None:
                if proc.poll() is not None:
                    break
                continue
            raw.write(line)
            event_detail(line, metrics)
            if metrics["quota_error_observed"]:
                metrics["stop_reason"] = "BLOCKED_QUOTA_429"
                stop_tree(proc)
            elif metrics["unexpected_agent_observed"]:
                metrics["stop_reason"] = "BLOCKED_UNEXPECTED_BUILTIN_BUILD_AGENT"
                stop_tree(proc)
            elif metrics["reported_tokens"]["input"] >= args.max_reported_input_tokens:
                metrics["stop_reason"] = "BLOCKED_REPORTED_INPUT_TOKEN_CAP"
                stop_tree(proc)
            if proc.poll() is not None and q.empty() and not thread.is_alive():
                break

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        stop_tree(proc)
    metrics["exit_code"] = proc.returncode
    metrics["seconds"] = round(time.monotonic() - start, 1)
    if not metrics["initial_change_seen"] and not metrics["stop_reason"]:
        metrics["stop_reason"] = "BLOCKED_ZERO_DIFF"
    elif proc.returncode and not metrics["stop_reason"]:
        metrics["stop_reason"] = "BLOCKED_CLI_ERROR"
    elif not metrics["stop_reason"]:
        metrics["stop_reason"] = "CLI_COMPLETED_VERIFY_PR_AND_REVIEW"

    report = temp_dir / "opencode-factory-summary.json"
    report.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RUNTIME_SUMMARY: " + json.dumps({k: metrics[k] for k in
          ("stop_reason", "seconds", "initial_change_seen", "changed_paths", "step_events", "task_agents", "reported_tokens", "quota_error_observed", "unexpected_agent_observed")}, ensure_ascii=False), flush=True)
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a", encoding="utf-8") as summary:
        summary.write("## OpenCode factory guarded run\n")
        summary.write(f"- Jira: `{issue}`\n- Reason: `{metrics['stop_reason']}`\n")
        summary.write(f"- Initial source/test diff: `{metrics['initial_change_seen']}`\n")
        summary.write(f"- Runtime: `{metrics['seconds']} s`\n")
    if metrics["stop_reason"] != "CLI_COMPLETED_VERIFY_PR_AND_REVIEW":
        return 33
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
