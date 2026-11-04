#!/usr/bin/env python3
"""Fail-closed check of the Draft PR, the reviewer marker, touched files, and secrets.

Read only. Does not move Jira and does not push.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety import ENGINE_MARKER, REVIEW_PASS, REVIEWER_MARKER, protected_paths, secret_categories, status_paths


def gh_json(*args):
    completed = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode:
        raise RuntimeError("GitHub command failed: gh " + " ".join(args[:3]))
    return json.loads(completed.stdout)


def gh_text(*args):
    completed = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=40)
    if completed.returncode:
        raise RuntimeError("GitHub command failed: gh " + " ".join(args[:3]))
    return completed.stdout


def git_text(*args):
    completed = subprocess.run(["git", *args], capture_output=True, text=True, check=False, timeout=20)
    if completed.returncode:
        raise RuntimeError("git " + " ".join(args[:2]) + " failed")
    return completed.stdout


def collect_secrets():
    found = {}
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "JIRA_API_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name) or ""
        if len(value) >= 8:
            found[name] = value
    return found


def write_summary(payload):
    path = os.environ.get("CODEX_SUMMARY_PATH")
    if not path:
        return
    previous = {}
    if os.path.exists(path):
        try:
            previous = json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError:
            previous = {}
    if not isinstance(previous, dict):
        previous = {}
    previous.update(payload)
    encoded = json.dumps(previous)
    if secret_categories(encoded, collect_secrets()):
        previous = {"issue": payload.get("issue"), "secrets_ok": False}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(previous, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate(*, issue, pr, comments, jira_status, paths, blobs, secrets, expected_status):
    key = issue.upper()
    if not isinstance(pr, dict) or not pr.get("isDraft"):
        raise RuntimeError("Exactly one actual open Draft PR is required")
    body = pr.get("body") or ""
    if ENGINE_MARKER not in body or f"Factory Jira: {key}" not in body:
        raise RuntimeError("Draft PR missing factory origin / Jira markers")
    if pr.get("baseRefName") != "master":
        raise RuntimeError("Draft PR base is not master")
    sha = pr.get("headRefOid") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Could not obtain published PR HEAD commit")
    review_claim = any(
        REVIEW_PASS in comment and f"Factory Review Head: {sha}" in comment and REVIEWER_MARKER in comment
        for comment in comments
    )
    if not review_claim:
        raise RuntimeError("No reviewer PASS marker tied to actual published PR HEAD; remain out of Human Review")
    expected = (expected_status or "").strip() or "Human Review"
    actual = " ".join(str(jira_status or "").split())
    if actual.casefold() != expected.casefold():
        raise RuntimeError(f"Jira status {actual!r}, expected {expected!r}; do not claim complete")
    blocked = protected_paths(paths)
    if blocked:
        raise RuntimeError("Protected paths touched: " + ", ".join(blocked))
    hits = []
    for blob in blobs:
        hits.extend(secret_categories(blob, secrets))
    if hits:
        raise RuntimeError("Secret material in published text: " + ", ".join(sorted(set(hits))))
    return {"issue": key, "pr": pr.get("url"), "draft": True, "review_head": sha, "jira": actual, "secrets_ok": True}


def jira_status(key):
    root = os.environ["JIRA_URL"].rstrip("/")
    auth = base64.b64encode((os.environ["JIRA_USERNAME"] + ":" + os.environ["JIRA_API_TOKEN"]).encode()).decode()
    request = urllib.request.Request(
        root + "/rest/api/3/issue/" + key + "?fields=status",
        headers={"Authorization": "Basic " + auth, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as reply:
            return ((json.load(reply).get("fields") or {}).get("status") or {}).get("name")
    except Exception:
        raise RuntimeError("Cannot verify Jira final status") from None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    args = parser.parse_args(argv)
    key = args.issue.upper()
    branch = "codex/" + key.lower()
    try:
        prs = gh_json(
            "pr", "list", "--state", "open", "--head", branch,
            "--json", "number,isDraft,headRefOid,baseRefName,body,url",
        )
        if len(prs) != 1:
            raise RuntimeError("Exactly ONE actual open PR for the feature branch is required")
        pr = prs[0]
        detail = gh_json("pr", "view", str(pr["number"]), "--json", "comments,body")
        comments = [item.get("body") or "" for item in detail.get("comments", [])]
        diff = gh_text("pr", "diff", str(pr["number"]))
        names = [line.strip() for line in gh_text("pr", "diff", str(pr["number"]), "--name-only").splitlines() if line.strip()]
        names.extend(status_paths(git_text("status", "--porcelain")))
        result = evaluate(
            issue=key,
            pr=pr,
            comments=comments,
            jira_status=jira_status(key),
            paths=names,
            blobs=[pr.get("body") or "", detail.get("body") or "", diff, *comments],
            secrets=collect_secrets(),
            expected_status=os.environ.get("JIRA_HUMAN_REVIEW_STATUS"),
        )
    except (RuntimeError, KeyError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        write_summary({"issue": key, "postflight": "blocked"})
        print("POSTFLIGHT_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    write_summary({"issue": key, "pr": result.get("pr"), "review_head": result.get("review_head"), "jira": result.get("jira"), "secrets_ok": True, "protected_ok": True})
    print("POSTFLIGHT_OK " + json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
