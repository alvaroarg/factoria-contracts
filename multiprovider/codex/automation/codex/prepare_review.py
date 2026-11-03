#!/usr/bin/env python3
"""Write the published diff and the Jira spec where a read-only reviewer can read them.

The reviewer runs with --sandbox read-only and does not get Jira or GitHub
credentials in its prompt. This script fetches both before that process starts.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def load_gate():
    path = Path(__file__).resolve().parent / "jira_gate.py"
    spec = importlib.util.spec_from_file_location("codex_jira_gate_prepare", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_context(*, issue, repo, pr_url, head, base, description):
    return (
        f"Jira key: {issue}\n"
        f"Repository: {repo}\n"
        f"PR: {pr_url}\n"
        f"HEAD: {head}\n"
        f"Base branch: {base}\n\n"
        "The published diff is the file .review/pr.diff in this checkout. "
        "That file, not the builder's report, is the review evidence.\n\n"
        "## Approved Jira description\n\n"
        f"{description.rstrip()}\n"
    )


def gh_json(*args):
    completed = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode:
        raise RuntimeError("GitHub command failed: gh " + " ".join(args[:3]))
    return json.loads(completed.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--out-dir", default=".review")
    args = parser.parse_args(argv)
    key = args.issue.upper()
    branch = "codex/" + key.lower()
    try:
        prs = gh_json(
            "pr", "list", "--state", "open", "--head", branch,
            "--json", "number,isDraft,headRefOid,baseRefName,url",
        )
        if len(prs) != 1 or not prs[0].get("isDraft"):
            raise RuntimeError("Exactly one open Draft PR is required before review")
        pr = prs[0]
        if pr.get("baseRefName") != "master":
            raise RuntimeError("Draft PR base is not master")
        diff = subprocess.run(
            ["gh", "pr", "diff", str(pr["number"])],
            capture_output=True, text=True, check=False, timeout=40,
        )
        if diff.returncode or not diff.stdout.strip():
            raise RuntimeError("Could not read the published PR diff")
        gate = load_gate()
        fields = (gate.jira_client()(key).get("fields") or {})
        description = gate.flatten_adf(fields.get("description"))
        if len(description.strip()) < 60:
            raise RuntimeError("Jira description unavailable for the reviewer")
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "pr.diff").write_text(diff.stdout, encoding="utf-8")
        (out / "context.md").write_text(build_context(
            issue=key,
            repo=args.repo,
            pr_url=pr.get("url") or "",
            head=pr.get("headRefOid") or "",
            base=pr.get("baseRefName") or "",
            description=description,
        ), encoding="utf-8")
    except (RuntimeError, KeyError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print("REVIEW_INPUT_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "issue": key,
        "pr": pr.get("url"),
        "head": pr.get("headRefOid"),
        "context": str(out / "context.md"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
