#!/usr/bin/env python3
"""Zero-token static + OpenCode CLI identity check; fail closed on fallback risk."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
AGENTS = {
    "factory-orchestrator": ("primary", "opencode-go/kimi-k3", 40),
    "feature-builder": ("subagent", "opencode-go/deepseek-v4-pro", 80),
    "pr-reviewer": ("subagent", "opencode-go/kimi-k3", 15),
}


def frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise ValueError(f"Missing YAML frontmatter: {path}")
    vals = {}
    for key, value in re.findall(r"(?m)^(mode|model|steps):\s*(.+?)\s*$", parts[1]):
        vals[key] = value.strip("'\" ")
    return vals


def run(args, timeout=40):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def main():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    if config.get("default_agent") != "factory-orchestrator":
        raise ValueError("default_agent must be factory-orchestrator; never allow fallback to build")
    if "jira" not in config.get("mcp", {}):
        raise ValueError("Jira MCP missing")
    for name, (mode, model, steps) in AGENTS.items():
        path = ROOT / ".opencode" / "agents" / (name + ".md")
        fm = frontmatter(path)
        if fm.get("mode") != mode or fm.get("model") != model or fm.get("steps") != str(steps):
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
    models = run(["opencode", "models", "opencode-go"], timeout=60)
    if models.returncode != 0:
        raise ValueError("Could not list OpenCode Go models")
    for model in set(x[1] for x in AGENTS.values()):
        if model not in models.stdout:
            raise ValueError(f"Model {model} unavailable; do not auto substitute")
    if not os.environ.get("OPENCODE_GO_API_KEY"):
        raise ValueError("OPENCODE_GO_API_KEY missing")
    print("CONFIG_OK: factory-orchestrator primary Kimi K3 (40), feature-builder DeepSeek V4 Pro (80), pr-reviewer Kimi K3 (15); models listed; no inference call")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as err:
        print("CONFIG_BLOCKED: " + str(err), file=sys.stderr)
        raise SystemExit(2)
