#!/usr/bin/env python3
"""Deterministic, read-only, fail-closed eligibility check for ONE Jira issue.

NO LLM calls, NO Jira state writes. This supplements (does not replace) the
orchestrator's own re-check just before In Progress.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

KEY = re.compile(r"^[A-Z][A-Z0-9_]*-[1-9][0-9]*$")
REPO_LINE = re.compile(r"(?im)^\s*Repository\s*:\s*([\w.\-]+/[\w.\-]+)\s*$")
TEXT_BLOCKER = re.compile(
    r"(?i)\b(?:blocked\s+by|is\s+blocked\s+by|depends\s+on|requires|"
    r"bloquead[oa]\s+por|depende\s+de|prerrequisito(?:s)?)\s*[:\-]?\s*"
    r"((?:[A-Z][A-Z0-9_]*-[0-9]+)(?:\s*[,;/y&]\s*"
    r"[A-Z][A-Z0-9_]*-[0-9]+)*)"
)
BLOCKER_WORDS = ("is blocked by", "blocked by", "depends on", "requires", "depende de", "bloqueado por", "bloqueada por")
OUTWARD_DEPENDS = ("depends on", "requires", "depende de")
DEPENDENCY_HEADERS = ("dependencies", "dependencias", "prerequisites", "prerrequisitos", "blocking issues")

# Álvaro's KAN board is in Spanish: the "Ready" transition lands in status
# "Listo" and "Done" lands in "Finalizada". Both names of each pair are always
# accepted as equivalent. JIRA_READY_STATUS / JIRA_DONE_STATUS may add more
# literal names (comma-separated); comparison ignores case and surrounding spaces.
STATUS_EQUIVALENTS = {
    "ready": ("Ready", "Listo"),
    "done": ("Done", "Finalizada"),
}


def accepted_statuses(env_name, kind):
    configured = [s.strip() for s in os.environ.get(env_name, "").split(",") if s.strip()]
    names = list(STATUS_EQUIVALENTS[kind]) + configured
    return {n.casefold() for n in names}, "/".join(dict.fromkeys(STATUS_EQUIVALENTS[kind] + tuple(configured)))


class GateError(Exception):
    pass


def flatten_adf(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (flatten_adf(x) for x in content)))
    if isinstance(content, dict):
        out = []
        if content.get("type") == "text" and "text" in content:
            out.append(str(content["text"]))
        if "content" in content:
            out.append(flatten_adf(content["content"]))
        return " ".join(x for x in out if x)
    return ""


def extract_text_blockers(text):
    blockers = set()
    for m in TEXT_BLOCKER.finditer(text):
        blockers.update(re.findall(r"[A-Z][A-Z0-9_]*-\d+", m.group(1)))
    # Support explicit '## Dependencies' sections when an item is just an issue key.
    lines = text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip().lstrip("# ").strip().lower()
        if line.lstrip().startswith("#"):
            in_section = any(stripped.startswith(h) for h in DEPENDENCY_HEADERS)
            continue
        if in_section and (line.strip() == "" or line.lstrip().startswith(("-", "*"))):
            if any(word in stripped for word in ("none", "ninguna", "ninguno")):
                continue
            blockers.update(re.findall(r"\b[A-Z][A-Z0-9_]*-\d+\b", line))
        elif in_section and line.strip() and not line.lstrip().startswith(("-", "*")):
            # A section with unclear prose: leave interpretation to orchestrator;
            # a documented ambiguity would be safer than trusting a clean gate.
            if any(x in stripped for x in ("pending", "pendiente", "blocked", "bloquead")) and not re.search(r"[A-Z][A-Z0-9_]*-\d+", line):
                raise GateError("Ambiguous textual dependency without Jira key")
    return blockers


def blocking_links(links):
    if not isinstance(links, list):
        raise GateError("Jira issue links missing/invalid")
    found = set()
    for link in links:
        if not isinstance(link, dict):
            raise GateError("Malformed Jira issue link")
        relation = link.get("type") or {}
        if not isinstance(relation, dict):
            raise GateError("Malformed Jira link type")
        inward = (relation.get("inward") or "").lower().strip()
        outward = (relation.get("outward") or "").lower().strip()
        name = (relation.get("name") or "").lower().strip()
        for direction, label in (("inwardIssue", inward), ("outwardIssue", outward)):
            linked = link.get(direction)
            if linked is None:
                continue
            key = linked.get("key") if isinstance(linked, dict) else None
            if not isinstance(key, str) or not KEY.fullmatch(key):
                raise GateError("Malformed linked Jira issue key")
            if any(s in label for s in BLOCKER_WORDS) or (direction == "outwardIssue" and any(s in label for s in OUTWARD_DEPENDS)):
                found.add(key)
            elif ("block" in name or "depend" in name or "bloque" in name) and not label:
                raise GateError("Ambiguous dependency direction in Jira issue link")
    return found


def jira_client():
    base = os.environ["JIRA_URL"].rstrip("/")
    user = os.environ["JIRA_USERNAME"]
    token = os.environ["JIRA_API_TOKEN"]
    creds = base64.b64encode(f"{user}:{token}".encode()).decode()
    if not base.startswith("https://"):
        raise GateError("JIRA_URL must use HTTPS")

    def get_issue(key):
        if not KEY.fullmatch(key):
            raise GateError("Invalid Jira key")
        selected = ["summary", "status", "labels", "description", "issuelinks"]
        for config_name in ("JIRA_REPOSITORY_FIELD_ID", "JIRA_DEPENDENCIES_FIELD_ID"):
            if os.environ.get(config_name):
                selected.append(os.environ[config_name])
        fields = ",".join(selected)
        url = f"{base}/rest/api/3/issue/{urllib.parse.quote(key)}?fields={fields}"
        req = urllib.request.Request(url, headers={"Authorization": "Basic " + creds, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as reply:
                return json.load(reply)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise GateError(f"Cannot read Jira {key}: {type(exc).__name__}") from None
    return get_issue


def github_existing(issue_key, branch):
    if not os.environ.get("GH_TOKEN"):
        raise GateError("GH_TOKEN absent; cannot check for existing PR")
    p = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--head", branch,
         "--json", "number,headRefName,body,url"],
        capture_output=True, text=True, check=False, timeout=25,
    )
    if p.returncode != 0:
        raise GateError("Could not verify existing open PRs via gh")
    try:
        prs = json.loads(p.stdout)
    except ValueError:
        raise GateError("Malformed GitHub PR list") from None
    if prs:
        raise GateError(f"PR already exists for branch {branch}; do not duplicate or overwrite")
    other = subprocess.run(["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
                           capture_output=True, text=True, check=False, timeout=20)
    if other.returncode != 0:
        raise GateError("Could not check existing remote branches")
    if other.stdout.strip():
        raise GateError(f"Remote branch {branch} already exists; manual recovery required")


def validate(key, mode, get_issue, check_github=True):
    if not KEY.fullmatch(key):
        raise GateError("Invalid issue key")
    project = os.environ["JIRA_PROJECT_KEY"].strip().upper()
    if key.split("-")[0] != project:
        raise GateError("Issue is not in configured JIRA_PROJECT_KEY")
    repo = os.environ["GITHUB_REPOSITORY"].strip()
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo):
        raise GateError("GITHUB_REPOSITORY not available")
    item = get_issue(key)
    fields = item.get("fields")
    if not isinstance(fields, dict):
        raise GateError("Incomplete Jira issue response")
    actual_status = str((fields.get("status") or {}).get("name") or "").strip()
    ready_set, ready_label = accepted_statuses("JIRA_READY_STATUS", "ready")
    if actual_status.casefold() not in ready_set:
        raise GateError(f"Issue status {actual_status!r}; expected Ready status {ready_label!r} (no automatic status transitions)")
    labels = fields.get("labels")
    if not isinstance(labels, list):
        raise GateError("Cannot inspect Jira labels")
    engines = [l for l in labels if l in ("engine-claude", "engine-cursor", "engine-opencode")]
    if engines != ["engine-opencode"] or "agent-ready" not in labels:
        raise GateError("Issue must have agent-ready and exactly one engine-opencode label")
    description = flatten_adf(fields.get("description"))
    repo_field = os.environ.get("JIRA_REPOSITORY_FIELD_ID", "").strip()
    declared_repo = flatten_adf(fields.get(repo_field)).strip() if repo_field else ""
    if not declared_repo:
        repo_match = REPO_LINE.search(description)
        declared_repo = repo_match.group(1) if repo_match else ""
    if declared_repo.lower() != repo.lower():
        raise GateError("No exact Repository owner/repo matching current GitHub repo (field or description)")
    if not description.strip() or len(description) < 60:
        raise GateError("Jira issue description too short to provide approved technical spec")
    additional = ""
    deps_field = os.environ.get("JIRA_DEPENDENCIES_FIELD_ID", "").strip()
    if deps_field:
        additional = flatten_adf(fields.get(deps_field))
    blockers = blocking_links(fields.get("issuelinks")) | extract_text_blockers(description + "\n" + additional)
    blockers.discard(key)
    done_set, done_label = accepted_statuses("JIRA_DONE_STATUS", "done")
    for dependency in sorted(blockers):
        dep = get_issue(dependency)
        status = str(((dep.get("fields") or {}).get("status") or {}).get("name") or "").strip()
        if status.casefold() not in done_set:
            raise GateError(f"Blocker {dependency} is {status!r}, not exact {done_label!r}")
    branch = "agent/" + key.lower()
    if check_github:
        github_existing(key, branch)
    return {"issue": key, "repo": repo, "status": actual_status, "blockers": sorted(blockers),
            "branch": branch, "summary": str(fields.get("summary") or "")[:120]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--mode", choices=["inspect", "build"], default="inspect")
    args = parser.parse_args(argv)
    try:
        result = validate(args.issue.strip().upper(), args.mode, jira_client())
        print("ELIGIBLE " + json.dumps(result, ensure_ascii=False))
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as out:
                out.write(f"branch={result['branch']}\nissue={result['issue']}\n")
    except (GateError, KeyError) as exc:
        print(f"GATE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
