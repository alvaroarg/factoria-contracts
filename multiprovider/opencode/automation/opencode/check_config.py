#!/usr/bin/env python3
"""Zero-token static + OpenCode CLI identity check; fail closed on fallback risk."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
# `opencode models` is flaky on a cold runner. Retry the listing only;
# never infer or substitute a model id.
MODEL_LIST_ATTEMPTS = 3
MODEL_LIST_DELAY_SECONDS = 60
AGENTS = {
    "factory-orchestrator": ("primary", "opencode-go/kimi-k3.1-pro", 40),
    # None = no `steps` key: OpenCode then iterates without a step limit
    # (bounded externally by guarded_run.py time/no-edit/token caps).
    "feature-builder": ("subagent", "opencode-go/deepseek-v4.1-flash", None),
    "pr-reviewer": ("subagent", "opencode-go/kimi-k3.1-pro", 15),
}


def frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise ValueError(f"Missing YAML frontmatter: {path}")
    vals = {}
    for key, value in re.findall(r"(?m)^(mode|model|steps|maxSteps):\s*(.+?)\s*$", parts[1]):
        vals[key] = value.strip("'\" ")
    return vals


def run(args, timeout=40):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def require_opencode_go_models(run_cmd=None, sleep=None, attempts=None, delay=None):
    """Run `opencode models opencode-go` up to `attempts` times, waiting `delay` seconds between tries.

    A blocking failure names every required model that is missing or unconfirmed.
    This function never picks a replacement model.
    """
    if run_cmd is None:
        run_cmd = run
    if sleep is None:
        sleep = time.sleep
    if attempts is None:
        attempts = MODEL_LIST_ATTEMPTS
    if delay is None:
        delay = MODEL_LIST_DELAY_SECONDS
    required = sorted({spec[1] for spec in AGENTS.values()})
    missing = list(required)
    saw_listing = False
    for attempt in range(1, attempts + 1):
        models = None
        try:
            models = run_cmd(["opencode", "models", "opencode-go"], timeout=60)
        except subprocess.TimeoutExpired:
            models = None
        if models is not None and models.returncode == 0:
            saw_listing = True
            missing = [model for model in required if model not in models.stdout]
            if not missing:
                return
        if attempt < attempts:
            sleep(delay)
    if saw_listing:
        raise ValueError(
            "Models unavailable: " + ", ".join(missing) + "; do not auto substitute"
        )
    raise ValueError(
        "Could not list OpenCode Go models after "
        + str(attempts)
        + " attempts; unconfirmed: "
        + ", ".join(required)
        + "; do not auto substitute"
    )


def main():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    if config.get("default_agent") != "factory-orchestrator":
        raise ValueError("default_agent must be factory-orchestrator; never allow fallback to build")
    if "jira" not in config.get("mcp", {}):
        raise ValueError("Jira MCP missing")
    for name in AGENTS:
        if "steps" in config.get("agent", {}).get(name, {}) or "maxSteps" in config.get("agent", {}).get(name, {}):
            raise ValueError(f"opencode.json must not override steps for {name}")
    for name, (mode, model, steps) in AGENTS.items():
        path = ROOT / ".opencode" / "agents" / (name + ".md")
        fm = frontmatter(path)
        expected_steps = None if steps is None else str(steps)
        if fm.get("mode") != mode or fm.get("model") != model or fm.get("steps") != expected_steps:
            raise ValueError(f"Wrong agent identity/config for {name}: {fm}")
        if len(path.read_text(encoding="utf-8").splitlines()) < 12:
            raise ValueError(f"Missing contract for {name}")
    agent = run(["opencode", "agent", "list"], timeout=60)
    if agent.returncode != 0:
        raise ValueError("OpenCode cannot list configured agents")
    # CLI output format is presentation text; accept only a distinct, word-boundary name.
    for name in AGENTS:
        if not re.search(r"(?<![A-Za-z0-9-])" + re.escape(name) + r"(?![A-Za-z0-9-])", agent.stdout):
            raise ValueError(f"OpenCode runtime DID NOT LOAD {name}; refuse fallback")
    require_opencode_go_models()
    if not os.environ.get("OPENCODE_GO_API_KEY"):
        raise ValueError("OPENCODE_GO_API_KEY missing")
    print("CONFIG_OK: factory-orchestrator primary Kimi K3.1 Pro (40), feature-builder DeepSeek V4.1 Flash (no step limit), pr-reviewer Kimi K3.1 Pro (15); models listed; no inference call")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as err:
        print("CONFIG_BLOCKED: " + str(err), file=sys.stderr)
        raise SystemExit(2)
