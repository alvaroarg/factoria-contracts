#!/usr/bin/env python3
"""Deterministic, read-only, fail-closed eligibility check for ONE Jira issue.

NO LLM calls, NO Jira state writes. This supplements (does not replace) the
orchestrator's own re-check just before In Progress.

Zero configuration, like the previous pilot (Licitaciones PR #16 / contracts
PR #5): with ``--issue`` it checks exactly that key; with an empty ``--issue``
it selects deterministically (REST/JQL, no LLM) the FIRST eligible issue by
Jira ``Rank ASC`` (Ready/Listo + agent-ready + ONLY engine-opencode, every
blocker Done/Finalizada, no existing ``agent/<key>`` branch/PR). One issue per
run; no eligible issue => ``NO_WORK`` and exit 0 without any LLM call.
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
# "Repository: owner/repo", "Repositorio: owner/repo" or
# "Repositorio destino: owner/repo" (markdown bold/code and a github.com URL
# are tolerated). No declaration => defaults to the current GITHUB_REPOSITORY.
REPO_LINE = re.compile(
    r"(?im)^[\s>*_`-]*(?:Repository|Repositorio(?:\s+destino)?)[*_`\s]*:[*_`\s]*"
    r"(?:https?://github\.com/)?([\w.\-]+(?:/[\w.\-]+)?)"
)
TEXT_BLOCKER = re.compile(
    r"(?i)\b(?:blocked\s+by|is\s+blocked\s+by|depends\s+on|requires|"
    r"bloquead[oa]\s+por|depende\s+de|prerrequisito(?:s)?)\s*\)?\s*[:\-]?\s*"
    r"((?:[A-Z][A-Z0-9_]*-[0-9]+)(?:\s*[,;/y&]\s*"
    r"[A-Z][A-Z0-9_]*-[0-9]+)*)"
)
BLOCKER_WORDS = ("is blocked by", "blocked by", "depends on", "requires", "depende de", "bloqueado por", "bloqueada por")
OUTWARD_DEPENDS = ("depends on", "requires", "depende de")
DEPENDENCY_HEADERS = ("dependencies", "dependencias", "prerequisites", "prerrequisitos", "blocking issues")

# Same rule as the Claude contract (multiprovider/claude/
# 01-jira-three-parallel-STRICT-ROUTING.md, "Localized status names") and the
# Cursor contract (multiprovider/cursor/01-scheduled-implement.md):
#   "Jira may return translated status.name values depending on the account
#    language. Treat Ready and Listo as the same status, and Done and
#    Finalizada as the same status, in every check of this contract (candidate
#    selection, dependency gate and re-checks). Any other name is not
#    Ready/Done."
# Only case/whitespace normalization is permitted. No configuration needed:
# JIRA_READY_STATUS / JIRA_DONE_STATUS are deliberately NOT honoured, so the
# three providers behave identically.
STATUS_EQUIVALENTS = {
    "ready": ("Ready", "Listo"),
    "done": ("Done", "Finalizada"),
}
DEFAULT_HUMAN_REVIEW_STATUS = "Human Review"


def accepted_statuses(env_name, kind):
    """Return the accepted names for ``kind``. ``env_name`` is ignored on purpose."""
    names = STATUS_EQUIVALENTS[kind]
    return {n.casefold() for n in names}, "/".join(names)


def status_is(name, kind):
    return " ".join(str(name or "").split()).casefold() in accepted_statuses(None, kind)[0]


class GateError(Exception):
    pass


class GateInfraError(GateError):
    """Jira/GitHub unreachable or unverifiable: abort the run, never skip silently."""


INLINE_ADF = {"text", "hardBreak", "mention", "emoji", "inlineCard", "date", "status"}


def flatten_adf(content):
    """ADF -> text. Inline runs of a paragraph stay on ONE line (so
    "**Repositorio destino:** `owner/repo`" is one line); blocks and hardBreak
    become newlines."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if content and all(isinstance(x, dict) and x.get("type") in INLINE_ADF for x in content):
            return "".join(flatten_adf(x) for x in content)
        return "\n".join(filter(None, (flatten_adf(x) for x in content)))
    if isinstance(content, dict):
        kind = content.get("type")
        if kind == "hardBreak":
            return "\n"
        if kind == "text":
            return str(content.get("text", ""))
        if kind == "mention":
            return str((content.get("attrs") or {}).get("text", ""))
        if kind == "inlineCard":
            return str((content.get("attrs") or {}).get("url", ""))
        if "content" in content:
            return flatten_adf(content["content"])
        return ""
    return ""


def declared_repositories(description):
    found = []
    for raw in REPO_LINE.findall(description or ""):
        value = raw.strip().rstrip(".,;:")
        if value.lower().endswith(".git"):
            value = value[:-4]
        if value:
            found.append(value)
    return found


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
            raise GateInfraError(f"Cannot read Jira {key}: {type(exc).__name__}") from None
    return get_issue


def jira_search_client():
    """Candidate keys in Jira Rank ASC order (JQL is the INITIAL filter only)."""
    base = os.environ["JIRA_URL"].rstrip("/")
    if not base.startswith("https://"):
        raise GateError("JIRA_URL must use HTTPS")
    creds = base64.b64encode(f"{os.environ['JIRA_USERNAME']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
    headers = {"Authorization": "Basic " + creds, "Accept": "application/json"}

    def search(jql, limit=50):
        params = {"jql": jql, "fields": "summary,status,labels", "maxResults": str(limit)}
        last = None
        # /search/jql is the current Jira Cloud endpoint; /search is the legacy one.
        for path in ("/rest/api/3/search/jql", "/rest/api/3/search"):
            url = base + path + "?" + urllib.parse.urlencode(params)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as reply:
                    data = json.load(reply)
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code in (404, 405, 410):
                    continue
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last = exc
                break
            issues = data.get("issues")
            if not isinstance(issues, list):
                raise GateInfraError("Malformed Jira search response")
            return [i.get("key") for i in issues if isinstance(i, dict) and isinstance(i.get("key"), str)]
        raise GateInfraError(f"Cannot search Jira: {type(last).__name__}")
    return search


def github_existing(issue_key, branch):
    if not os.environ.get("GH_TOKEN"):
        raise GateInfraError("GH_TOKEN absent; cannot check for existing PR")
    p = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--head", branch,
         "--json", "number,headRefName,body,url"],
        capture_output=True, text=True, check=False, timeout=25,
    )
    if p.returncode != 0:
        raise GateInfraError("Could not verify existing open PRs via gh")
    try:
        prs = json.loads(p.stdout)
    except ValueError:
        raise GateInfraError("Malformed GitHub PR list") from None
    if prs:
        raise GateError(f"PR already exists for branch {branch}; do not duplicate or overwrite")
    other = subprocess.run(["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
                           capture_output=True, text=True, check=False, timeout=20)
    if other.returncode != 0:
        raise GateInfraError("Could not check existing remote branches")
    if other.stdout.strip():
        raise GateError(f"Remote branch {branch} already exists; manual recovery required")


def validate(key, mode, get_issue, check_github=True):
    if not KEY.fullmatch(key):
        raise GateError("Invalid issue key")
    project = project_key(key)
    if key.split("-")[0] != project:
        raise GateError("Issue is not in configured JIRA_PROJECT_KEY")
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo):
        raise GateInfraError("GITHUB_REPOSITORY not available")
    item = get_issue(key)
    fields = item.get("fields")
    if not isinstance(fields, dict):
        raise GateError("Incomplete Jira issue response")
    actual_status = str((fields.get("status") or {}).get("name") or "").strip()
    ready_set, ready_label = accepted_statuses("JIRA_READY_STATUS", "ready")
    if not status_is(actual_status, "ready"):
        raise GateError(f"Issue status {actual_status!r}; expected Ready status {ready_label!r} (no automatic status transitions)")
    labels = fields.get("labels")
    if not isinstance(labels, list):
        raise GateError("Cannot inspect Jira labels")
    engines = [l for l in labels if l in ("engine-claude", "engine-cursor", "engine-opencode")]
    if engines != ["engine-opencode"] or "agent-ready" not in labels:
        raise GateError("Issue must have agent-ready and exactly one engine-opencode label")
    description = flatten_adf(fields.get("description"))
    repo_field = os.environ.get("JIRA_REPOSITORY_FIELD_ID", "").strip()
    declared = []
    if repo_field:
        field_value = flatten_adf(fields.get(repo_field)).strip()
        if field_value:
            declared = declared_repositories("Repository: " + field_value) or [field_value]
    if not declared:
        declared = declared_repositories(description)
    # No Repository/Repositorio declaration at all => the repo running the
    # workflow (GITHUB_REPOSITORY). A declaration that names ANOTHER repo fails.
    repo_name = repo.split("/", 1)[1].lower()
    for value in declared:
        matches = value.lower() == repo.lower() if "/" in value else value.lower() == repo_name
        if not matches:
            raise GateError(f"Story Repository {value!r} does not match current GitHub repo {repo!r}")
    repo_source = "story" if declared else "default GITHUB_REPOSITORY"
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
        if not status_is(status, "done"):
            raise GateError(f"Blocker {dependency} is {status!r}, not exact {done_label!r}")
    branch = "agent/" + key.lower()
    if check_github:
        github_existing(key, branch)
    return {"issue": key, "repo": repo, "repo_source": repo_source, "status": actual_status, "blockers": sorted(blockers),
            "branch": branch, "summary": str(fields.get("summary") or "")[:120]}


def project_key(issue_key=""):
    """JIRA_PROJECT_KEY if set; else the prefix of the given key; else KAN."""
    configured = os.environ.get("JIRA_PROJECT_KEY", "").strip().upper()
    if configured:
        return configured
    if issue_key and KEY.fullmatch(issue_key):
        return issue_key.split("-")[0]
    return "KAN"


def candidate_jql(project):
    # Status is NOT put in the JQL (an unknown status name makes Jira reject the
    # whole query); Ready/Listo is checked per issue on the full detail.
    return (f'project = "{project}" AND labels = "agent-ready" AND labels = "engine-opencode" '
            'AND statusCategory != Done ORDER BY Rank ASC')


def select(mode, get_issue, search, check_github=True, limit=50):
    """First eligible issue by Rank ASC, or None. Infra errors abort (fail closed)."""
    project = project_key()
    skipped = []
    for key in search(candidate_jql(project), limit):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            continue
        try:
            result = validate(key, mode, get_issue, check_github)
        except GateInfraError:
            raise
        except GateError as exc:
            skipped.append({"issue": key, "reason": str(exc)})
            continue
        result["selected"] = "auto"
        result["skipped"] = skipped
        return result, skipped
    return None, skipped


def write_outputs(values):
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as out:
            for k, v in values.items():
                out.write(f"{k}={v}\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", default="", help="Exact key; empty = deterministic auto-selection")
    parser.add_argument("--mode", choices=["inspect", "build"], default="inspect")
    args = parser.parse_args(argv)
    requested = (args.issue or "").strip().upper()
    try:
        if requested:
            result = validate(requested, args.mode, jira_client())
            result["selected"] = "requested"
        else:
            result, skipped = select(args.mode, jira_client(), jira_search_client())
            if result is None:
                print("NO_WORK " + json.dumps({"skipped": skipped}, ensure_ascii=False))
                write_outputs({"issue": "", "branch": "", "has_work": "false"})
                return 0
        print("ELIGIBLE " + json.dumps(result, ensure_ascii=False))
        write_outputs({"branch": result["branch"], "issue": result["issue"], "has_work": "true"})
    except (GateError, KeyError) as exc:
        print(f"GATE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
