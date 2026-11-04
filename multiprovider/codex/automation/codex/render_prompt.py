#!/usr/bin/env python3
"""Substitute __PLACEHOLDER__ tokens in a Codex prompt. Fail if any remain."""
import argparse
import re
import sys
from pathlib import Path

TOKEN = re.compile(r"__[A-Z0-9_]+__")


def render(template, **values):
    text = template
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z0-9_]+", key):
            raise ValueError(f"invalid placeholder name {key}")
        text = text.replace(f"__{key}__", "" if value is None else str(value))
    leftover = sorted(set(TOKEN.findall(text)))
    if leftover:
        raise ValueError("unresolved placeholders: " + ", ".join(leftover))
    return text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--pr-url", default="")
    parser.add_argument("--head", default="")
    args = parser.parse_args(argv)
    values = {
        "ISSUE_KEY": args.issue,
        "GITHUB_REPOSITORY": args.repo,
        "BASE_SHA": args.base,
        "BRANCH": args.branch,
        "PR_URL": args.pr_url,
        "HEAD_SHA": args.head,
    }
    try:
        rendered = render(Path(args.template).read_text(encoding="utf-8"), **{k: v for k, v in values.items() if v})
    except (OSError, ValueError) as exc:
        print(f"PROMPT_BLOCKED: {exc}", file=sys.stderr)
        return 2
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    print(f"PROMPT_OK {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
