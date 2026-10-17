#!/usr/bin/env python3
"""Fail-closed verification of actual published DRAFT PR + review head + Jira state.

Read only.  Confirms evidence markers, NOT that the reviewer model truly ran;
for that inspect task/session events and independent PR diff review evidence.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request


def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=30)
    if p.returncode:
        raise RuntimeError(f"GitHub command failed: gh {' '.join(args[:3])}")
    return json.loads(p.stdout)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--issue", required=True)
    args = p.parse_args()
    key = args.issue.upper()
    branch = "agent/" + key.lower()
    prs = gh("pr", "list", "--state", "open", "--head", branch,
             "--json", "number,isDraft,headRefOid,baseRefName,body,url")
    if len(prs) != 1:
        raise RuntimeError("Exactly ONE actual open PR for feature branch is required")
    pr = prs[0]
    if not pr["isDraft"]:
        raise RuntimeError("PR is not Draft")
    body = pr.get("body") or ""
    if "Factory Engine: opencode" not in body or f"Factory Jira: {key}" not in body:
        raise RuntimeError("Draft PR missing factory origin / Jira markers")
    sha = pr.get("headRefOid") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Could not obtain published PR HEAD commit")
    detail = gh("pr", "view", str(pr["number"]), "--json", "comments")
    comments = [x.get("body") or "" for x in detail.get("comments", [])]
    review_claim = any(
        "Factory Review: PASS" in c and f"Factory Review Head: {sha}" in c
        and "Factory Reviewer: pr-reviewer" in c for c in comments
    )
    if not review_claim:
        raise RuntimeError("No reviewer PASS marker tied to actual published PR HEAD; remain in AI Review")
    root = os.environ["JIRA_URL"].rstrip("/")
    auth = base64.b64encode((os.environ["JIRA_USERNAME"] + ":" + os.environ["JIRA_API_TOKEN"]).encode()).decode()
    req = urllib.request.Request(root + "/rest/api/3/issue/" + key + "?fields=status",
                                 headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as reply:
            status = ((json.load(reply).get("fields") or {}).get("status") or {}).get("name")
    except Exception:
        raise RuntimeError("Cannot verify Jira final status") from None
    expected = os.environ.get("JIRA_HUMAN_REVIEW_STATUS", "Human Review")
    if status != expected:
        raise RuntimeError(f"Jira status {status!r}, expected {expected!r}; do not claim complete")
    print("POSTFLIGHT_OK " + json.dumps({"issue": key, "pr": pr.get("url"), "draft": True,
                                         "review_head": sha, "jira": status}))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError) as exc:
        print("POSTFLIGHT_BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
