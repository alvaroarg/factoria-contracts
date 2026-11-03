#!/usr/bin/env python3
"""Copy the trusted Codex profile to a codex-home outside the checkout.

openai/codex-action merges its Responses proxy into this config.toml and
preserves unrelated tables. The template must not already set model_provider.
The workspace is marked trusted so project AGENTS.md and .codex/agents load.
"""
import argparse
import shutil
import sys
from pathlib import Path


def prepare(config_path, agents_dir, dest_home, workspace):
    workspace = str(workspace)
    if (not workspace.startswith("/")) or ('"' in workspace) or ("\n" in workspace):
        raise ValueError("workspace path cannot be embedded in TOML")
    source = Path(config_path).read_text(encoding="utf-8")
    if "model_provider" in source:
        raise ValueError("config.toml must not set model_provider; the action writes the proxy")
    if "[projects." in source:
        raise ValueError("config template must not contain a projects table")
    dest = Path(dest_home)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    trust = f'\n[projects."{workspace}"]\ntrust_level = "trusted"\n'
    (dest / "config.toml").write_text(source.rstrip() + "\n" + trust, encoding="utf-8")
    agent_dest = dest / "agents"
    agent_dest.mkdir()
    copied = 0
    for path in sorted(Path(agents_dir).glob("*.toml")):
        shutil.copyfile(path, agent_dest / path.name)
        copied += 1
    if copied < 1:
        raise ValueError("no Codex agent files to copy")
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--agents", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    try:
        dest = prepare(args.config, args.agents, args.dest, args.workspace)
    except (OSError, ValueError) as exc:
        print(f"CODEX_HOME_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"CODEX_HOME_OK {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
