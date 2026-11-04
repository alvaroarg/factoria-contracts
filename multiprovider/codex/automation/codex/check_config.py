#!/usr/bin/env python3
"""Zero-token checks for the Codex factory. Fail closed. No model calls."""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORCHESTRATOR_MODEL = "gpt-6-astra"
DEFAULT_REVIEWER_MODEL = "gpt-6-astra"
DEFAULT_BUILDER_MODEL = "gpt-6.1-sol"
PINNED_CODEX = "0.166.0"
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,80}")
JIRA_TOOLS = [
    "jira_search",
    "jira_get_issue",
    "jira_get_transitions",
    "jira_transition_issue",
    "jira_add_comment",
]
REQUIRED_DOMAINS = (
    "github.com",
    "api.github.com",
    "api.openai.com",
    "pypi.org",
    "files.pythonhosted.org",
    "atlassian.net",
)
FORBIDDEN = (
    "--yolo",
    "dangerously-bypass-approvals-and-sandbox",
    "danger-full-access",
    "safety-strategy: unsafe",
    "--full-auto",
)
STATUS_RULE = (
    "Treat `Ready` and `Listo` as the same status, and `Done` and `Finalizada` as the same status"
)


def model_from_env(name, default):
    value = (os.environ.get(name) or "").strip() or default
    if not MODEL_ID.fullmatch(value):
        raise ValueError(f"invalid model id for {name}")
    return value


def forbidden_hits(text):
    return [item for item in FORBIDDEN if item in text]


def load_toml(path):
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate_config(config):
    if config.get("approval_policy") != "never":
        raise ValueError("approval_policy must be never")
    if "sandbox_mode" in config or "sandbox_workspace_write" in config:
        raise ValueError("do not combine sandbox_mode with a permission profile")
    if config.get("model_provider") or config.get("model_providers"):
        raise ValueError("model_provider is owned by codex-action's proxy")
    if config.get("web_search") != "disabled":
        raise ValueError("web_search must be disabled so the domain allowlist is not bypassed")
    if config.get("default_permissions") != "factory-build":
        raise ValueError("default_permissions must be factory-build")
    if not (config.get("features") or {}).get("network_proxy"):
        raise ValueError("features.network_proxy must be true or the domain allowlist is not enforced")
    if (config.get("agents") or {}).get("max_concurrent_threads_per_session") != 1:
        raise ValueError("agents.max_concurrent_threads_per_session must be 1; parallelism is the job matrix")
    profile = (config.get("permissions") or {}).get("factory-build") or {}
    if profile.get("extends") != ":workspace":
        raise ValueError("factory-build must extend :workspace")
    git_rule = ((profile.get("filesystem") or {}).get(":workspace_roots") or {}).get(".git")
    if git_rule != "write":
        raise ValueError('.git must be "write" under factory-build :workspace_roots')
    network = profile.get("network") or {}
    if network.get("enabled") is not True:
        raise ValueError("factory-build network.enabled must be true")
    domains = network.get("domains") or {}
    allowed = " ".join(domains)
    missing = [item for item in REQUIRED_DOMAINS if item not in allowed]
    if missing or any(value != "allow" for value in domains.values()):
        raise ValueError("network allowlist incomplete or not allow-only: " + ", ".join(missing))
    review = (config.get("permissions") or {}).get("factory-review") or {}
    if review.get("extends") != ":read-only":
        raise ValueError("factory-review must extend :read-only")
    if (review.get("network") or {}).get("enabled") is not False:
        raise ValueError("factory-review network.enabled must be false")
    jira = (config.get("mcp_servers") or {}).get("jira") or {}
    if jira.get("command") != "uvx" or jira.get("args") != ["mcp-atlassian"]:
        raise ValueError("Jira MCP must be uvx mcp-atlassian")
    if jira.get("required") is not True:
        raise ValueError("Jira MCP required must be true")
    if jira.get("enabled_tools") != JIRA_TOOLS:
        raise ValueError("Jira MCP enabled_tools must be the factory minimum")
    forwarded = set(jira.get("env_vars") or [])
    if not {"JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"} <= forwarded:
        raise ValueError("Jira MCP must forward JIRA_URL, JIRA_USERNAME and JIRA_API_TOKEN")
    if "JIRA_API_TOKEN" in str((jira.get("env") or {})):
        raise ValueError("do not inline the Jira token in config.toml")
    return config


def validate_builder(agent, model):
    if agent.get("name") != "feature-builder":
        raise ValueError("feature-builder name mismatch")
    if not agent.get("description") or not agent.get("developer_instructions"):
        raise ValueError("feature-builder contract is empty")
    if agent.get("model") != model:
        raise ValueError(f"feature-builder model {agent.get('model')!r} != CODEX_BUILDER_MODEL {model!r}; do not auto substitute")
    if (agent.get("features") or {}).get("request_permissions_tool") is not False:
        raise ValueError("feature-builder must disable features.request_permissions_tool")
    for banned in ("--yolo", "danger-full-access", "git push", "gh pr create"):
        if banned in (agent.get("developer_instructions") or "") and banned in ("--yolo", "danger-full-access"):
            raise ValueError(f"feature-builder instructions contain {banned}")


def validate_workflow(text, orchestrator_model, builder_model, reviewer_model, codex_version):
    hits = forbidden_hits(text)
    if hits:
        raise ValueError("workflow contains forbidden Codex flags: " + ", ".join(hits))
    required = (
        "workflow_dispatch:",
        "openai/codex-action@v1",
        "safety-strategy: drop-sudo",
        "permission-profile: factory-build",
        f'CODEX_VERSION: "{codex_version}"',
        "codex-version: ${{ env.CODEX_VERSION }}",
        "--sandbox read-only",
        "--ask-for-approval never",
        "--ignore-user-config",
        "--ephemeral",
        "--output-schema",
        "max-parallel: 3",
        "fail-fast: false",
        'DEFAULT_BRANCH="master"',
        'git fetch origin "$DEFAULT_BRANCH"',
        "codex-factory-diff-${{ matrix.issue }}",
        "codex-factory-summary-${{ matrix.issue }}",
        "contents: write",
        "pull-requests: write",
        f"CODEX_ORCHESTRATOR_MODEL: {orchestrator_model}",
        f"CODEX_BUILDER_MODEL: {builder_model}",
        f"CODEX_REVIEWER_MODEL: {reviewer_model}",
        "--model",
        "postflight.py",
        "jira_gate.py",
        "check_config.py",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError("workflow missing: " + ", ".join(missing))
    if re.search(r"(?m)^[\s]*schedule:\s*$", text) or "cron:" in text:
        raise ValueError("pilot workflow must not define a schedule")
    if re.search(r"(?m)^[\s-]*OPENAI_API_KEY:", text):
        raise ValueError("do not put OPENAI_API_KEY in the job environment; pass it only to the action input and the reviewer step as CODEX_API_KEY")
    if "openai-api-key:" not in text or "CODEX_API_KEY:" not in text:
        raise ValueError("workflow must pass the OpenAI key only as openai-api-key and CODEX_API_KEY")
    select = text.split("\n  factory:", 1)[0]
    if "contents: write" in select.split("jobs:", 1)[-1]:
        raise ValueError("select job must not have contents: write")


def validate_prompts(orchestrator_model, builder_model, reviewer_model):
    orchestrator = (ROOT / "automation" / "codex" / "orchestrator-prompt.md").read_text(encoding="utf-8")
    reviewer = (ROOT / "automation" / "codex" / "reviewer-prompt.md").read_text(encoding="utf-8")
    if STATUS_RULE not in orchestrator:
        raise ValueError("orchestrator prompt is missing the Ready/Listo and Done/Finalizada rule")
    for label in ("engine-claude", "engine-cursor", "engine-opencode", "engine-openai"):
        if label not in orchestrator:
            raise ValueError(f"orchestrator prompt does not name {label}")
    for needle in ("origin/master", "Factory Engine: openai", "feature-builder", "Human Review", "__ISSUE_KEY__", "__BRANCH__"):
        if needle not in orchestrator:
            raise ValueError(f"orchestrator prompt is missing {needle}")
    if "codex exec" not in reviewer or "__HEAD_SHA__" not in reviewer:
        raise ValueError("reviewer prompt is incomplete")
    raw = (ROOT / "automation" / "codex" / "review-schema.json").read_text(encoding="utf-8")
    if '"PASS"' not in raw or '"CHANGES_REQUESTED"' not in raw or '"BLOCKED"' not in raw:
        raise ValueError("review schema is missing verdicts")
    if orchestrator_model not in orchestrator or builder_model not in orchestrator:
        raise ValueError("orchestrator prompt must name the orchestrator and builder models")
    if reviewer_model not in reviewer:
        raise ValueError("reviewer prompt must name the reviewer model")
    hits = forbidden_hits(orchestrator + reviewer)
    if hits:
        raise ValueError("prompts contain forbidden flags: " + ", ".join(hits))


def engines_match_opencode():
    """When the OpenCode gate is installed beside this package, the label set must be identical."""
    candidates = [
        ROOT.parent / "opencode" / "automation" / "opencode" / "jira_gate.py",
        ROOT / "automation" / "opencode" / "jira_gate.py",
    ]
    ours = _load_gate(ROOT / "automation" / "codex" / "jira_gate.py")
    for path in candidates:
        if not path.is_file():
            continue
        other = _load_gate(path)
        if tuple(other.ENGINE_LABELS) != tuple(ours.ENGINE_LABELS):
            raise ValueError(f"ENGINE_LABELS drifted from {path}")
        if other.REQUIRED_ENGINE == ours.REQUIRED_ENGINE:
            raise ValueError(f"{path} must not require the same engine as Codex")


def _load_gate(path):
    spec = importlib.util.spec_from_file_location(path.stem + "_" + str(abs(hash(path))), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_secrets():
    missing = [name for name in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN") if not os.environ.get(name)]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if not os.environ["JIRA_URL"].startswith("https://"):
        raise ValueError("JIRA_URL must use HTTPS")


def require_codex_version(run_cmd=None):
    expected = (os.environ.get("CODEX_VERSION") or PINNED_CODEX).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", expected):
        raise ValueError("CODEX_VERSION must be an exact x.y.z pin")
    if run_cmd is None:
        run_cmd = lambda args: subprocess.run(args, text=True, capture_output=True, timeout=30, check=False)
    try:
        result = run_cmd(["codex", "--version"])
    except subprocess.TimeoutExpired as exc:
        raise ValueError("codex --version timed out") from exc
    output = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")
    if getattr(result, "returncode", 1) != 0 or expected not in output:
        raise ValueError(f"codex --version did not report pinned {expected}")


def validate(require_secret_env=False, require_cli=False, run_cmd=None):
    orchestrator = model_from_env("CODEX_ORCHESTRATOR_MODEL", DEFAULT_ORCHESTRATOR_MODEL)
    builder = model_from_env("CODEX_BUILDER_MODEL", DEFAULT_BUILDER_MODEL)
    reviewer = model_from_env("CODEX_REVIEWER_MODEL", DEFAULT_REVIEWER_MODEL)
    version = (os.environ.get("CODEX_VERSION") or PINNED_CODEX).strip()
    config_path = ROOT / ".codex" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    hits = forbidden_hits(config_text)
    if hits:
        raise ValueError("config.toml contains forbidden flags: " + ", ".join(hits))
    config = load_toml(config_path)
    validate_config(config)
    if config.get("model") != orchestrator:
        raise ValueError(
            f"config model {config.get('model')!r} != CODEX_ORCHESTRATOR_MODEL {orchestrator!r}; do not auto substitute"
        )
    agent = load_toml(ROOT / ".codex" / "agents" / "feature-builder.toml")
    validate_builder(agent, builder)
    workflow = (ROOT / ".github" / "workflows" / "codex-factory.yml").read_text(encoding="utf-8")
    validate_workflow(workflow, orchestrator, builder, reviewer, version)
    validate_prompts(orchestrator, builder, reviewer)
    engines_match_opencode()
    if require_secret_env:
        require_secrets()
    if require_cli:
        require_codex_version(run_cmd)
    return {
        "orchestrator": orchestrator,
        "builder": builder,
        "reviewer": reviewer,
        "codex": version,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-secrets", action="store_true")
    parser.add_argument("--require-cli", action="store_true")
    args = parser.parse_args(argv)
    try:
        found = validate(args.require_secrets, args.require_cli)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired, tomllib.TOMLDecodeError) as err:
        print("CONFIG_BLOCKED: " + str(err), file=sys.stderr)
        return 2
    print(
        "CONFIG_OK: "
        f"orchestrator {found['orchestrator']}, builder {found['builder']}, "
        f"reviewer {found['reviewer']}, codex {found['codex']}; no inference call"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
