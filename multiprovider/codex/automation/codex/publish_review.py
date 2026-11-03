#!/usr/bin/env python3
"""Apply the isolated reviewer's JSON verdict. The reviewer process cannot write.

PASS on the current PR HEAD posts the factory markers and moves Jira to Human
Review. Any other verdict is recorded and does not move Jira.
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
from safety import REVIEW_PASS, REVIEWER_MARKER, secret_categories


class ReviewError(RuntimeError):
    pass


def load_verdict(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewError("Reviewer output is not JSON") from exc
    if not isinstance(data, dict):
        raise ReviewError("Reviewer output is not a JSON object")
    verdict = data.get("verdict")
    if verdict not in ("PASS", "CHANGES_REQUESTED", "BLOCKED"):
        raise ReviewError("Reviewer verdict missing or unknown")
    return data


def classify(verdict, issue, head):
    """Return 'pass' or 'stop'. Never treats a mismatched HEAD as PASS."""
    if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
        raise ReviewError("Published PR HEAD is not a full sha")
    if str(verdict.get("jira_key") or "").upper() != issue.upper():
        raise ReviewError("Reviewer jira_key does not match this story")
    if verdict.get("verdict") != "PASS":
        return "stop"
    if verdict.get("head_sha") != head:
        raise ReviewError("Reviewer PASS is not for the current PR HEAD")
    return "pass"


def safe_summary(summary, secrets):
    text = str(summary or "").strip()
    if secret_categories(text, secrets):
        return "[redacted: reviewer summary contained secret material]"
    return text[:2000]


def pass_comment(head, summary):
    return "\n".join([
        REVIEW_PASS,
        f"Factory Review Head: {head}",
        REVIEWER_MARKER,
        "",
        summary,
    ])


def stop_comment(verdict, summary):
    # Must not contain the PASS marker. postflight treats that marker as success.
    return "\n".join([
        f"Factory Review: {verdict}",
        REVIEWER_MARKER,
        "",
        summary,
        "",
        "Jira was not moved to Human Review.",
    ])


def write_summary(payload):
    path = os.environ.get("CODEX_SUMMARY_PATH")
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _auth_header():
    token = base64.b64encode((os.environ["JIRA_USERNAME"] + ":" + os.environ["JIRA_API_TOKEN"]).encode()).decode()
    return {"Authorization": "Basic " + token, "Accept": "application/json", "Content-Type": "application/json"}


def transition_to(issue, expected_status):
    root = os.environ["JIRA_URL"].rstrip("/")
    if not root.startswith("https://"):
        raise ReviewError("JIRA_URL must use HTTPS")
    headers = _auth_header()
    listed = urllib.request.Request(root + f"/rest/api/3/issue/{issue}/transitions", headers=headers)
    try:
        with urllib.request.urlopen(listed, timeout=20) as reply:
            transitions = json.load(reply).get("transitions") or []
    except Exception as exc:
        raise ReviewError("Cannot list Jira transitions") from exc
    target = " ".join(expected_status.split()).casefold()
    chosen = None
    for item in transitions:
        name = " ".join(str(((item.get("to") or {}).get("name") or "")).split()).casefold()
        if name == target:
            chosen = str(item.get("id"))
            break
    if not chosen:
        raise ReviewError(f"No Jira transition to {expected_status!r}")
    body = json.dumps({"transition": {"id": chosen}}).encode()
    request = urllib.request.Request(
        root + f"/rest/api/3/issue/{issue}/transitions",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as reply:
            if reply.status not in (200, 204):
                raise ReviewError(f"Jira transition returned HTTP {reply.status}")
    except ReviewError:
        raise
    except Exception as exc:
        raise ReviewError("Jira transition failed") from exc


def gh_json(*args):
    completed = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode:
        raise ReviewError("GitHub command failed: gh " + " ".join(args[:3]))
    return json.loads(completed.stdout)


def post_comment(number, body, directory):
    path = Path(directory) / "review-comment.md"
    path.write_text(body, encoding="utf-8")
    completed = subprocess.run(
        ["gh", "pr", "comment", str(number), "--body-file", str(path)],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if completed.returncode:
        raise ReviewError("Could not comment on the Draft PR")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--verdict", required=True)
    args = parser.parse_args(argv)
    key = args.issue.upper()
    branch = "codex/" + key.lower()
    expected = (os.environ.get("JIRA_HUMAN_REVIEW_STATUS") or "").strip() or "Human Review"
    secrets = {}
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "JIRA_API_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name) or ""
        if len(value) >= 8:
            secrets[name] = value
    try:
        verdict = load_verdict(args.verdict)
        prs = gh_json(
            "pr", "list", "--state", "open", "--head", branch,
            "--json", "number,isDraft,headRefOid,url",
        )
        if len(prs) != 1 or not prs[0].get("isDraft"):
            raise ReviewError("Exactly one open Draft PR is required before publishing the review")
        pr = prs[0]
        head = pr.get("headRefOid") or ""
        action = classify(verdict, key, head)
        summary = safe_summary(verdict.get("summary"), secrets)
        if action == "pass":
            post_comment(pr["number"], pass_comment(head, summary), Path(args.verdict).parent)
            transition_to(key, expected)
            write_summary({"issue": key, "verdict": "PASS", "pr": pr.get("url"), "review_head": head})
            print(json.dumps({"issue": key, "verdict": "PASS", "pr": pr.get("url"), "head": head}))
            return 0
        post_comment(pr["number"], stop_comment(verdict["verdict"], summary), Path(args.verdict).parent)
        write_summary({"issue": key, "verdict": verdict["verdict"], "pr": pr.get("url")})
        raise ReviewError(f"Reviewer verdict {verdict['verdict']}; Jira left unchanged")
    except (ReviewError, KeyError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        write_summary({"issue": key, "publish_review": "blocked"})
        print("REVIEW_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
