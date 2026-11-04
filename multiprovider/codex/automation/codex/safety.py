"""Pure checks shared by publish and postflight. No network."""
import re

ENGINE_MARKER = "Factory Engine: openai"
REVIEW_PASS = "Factory Review: PASS"
REVIEWER_MARKER = "Factory Reviewer: pr-reviewer"
PROTECTED_PREFIXES = (
    ".github/",
    ".claude/",
    ".cursor/",
    ".opencode/",
    ".codex/",
    ".review/",
    "automation/opencode/",
    "automation/codex/",
)
_OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9]{20,}")
_GITHUB_TOKEN = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")


def normalize_path(path):
    text = str(path or "").replace("\\", "/").strip()
    if text.startswith("./"):
        text = text[2:]
    if " -> " in text:
        text = text.split(" -> ", 1)[1].strip()
    return text


def is_protected(path):
    norm = normalize_path(path)
    if not norm or norm.endswith("/"):
        return False
    base = norm.rsplit("/", 1)[-1]
    if base == "CLAUDE.md" or base == ".env" or base.startswith(".env."):
        return True
    return any(norm == prefix.rstrip("/") or norm.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def protected_paths(paths):
    return [normalize_path(path) for path in paths if is_protected(path)]


def secret_categories(text, secrets):
    """Return category names, never the secret values."""
    found = []
    blob = text or ""
    for name, value in (secrets or {}).items():
        if isinstance(value, str) and len(value) >= 8 and value in blob:
            found.append(name)
    if _OPENAI_KEY.search(blob):
        found.append("openai-key-pattern")
    if _GITHUB_TOKEN.search(blob):
        found.append("github-token-pattern")
    return found


def status_paths(porcelain):
    paths = []
    for line in (porcelain or "").splitlines():
        if len(line) < 4:
            continue
        paths.append(normalize_path(line[3:]))
    return paths
