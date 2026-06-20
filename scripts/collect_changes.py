#!/usr/bin/env python3
"""Collect weekly Streamable repo changes for the OpenClaw editor agent."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
SOURCE_DIR = ROOT / "output" / "source"


@dataclass
class GitResult:
    stdout: str
    stderr: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect weekly product changes from git.")
    parser.add_argument("--days", type=int, default=None, help="Lookback window in days.")
    parser.add_argument("--since", help="Explicit ISO/date git --since value.")
    parser.add_argument("--until", help="Explicit ISO/date git --until value.")
    parser.add_argument("--no-fetch", action="store_true", help="Skip network fetch.")
    parser.add_argument("--print-json", action="store_true", help="Print the JSON report.")
    args = parser.parse_args()

    config = load_config()
    tz = ZoneInfo(config["report"].get("timezone", "America/Los_Angeles"))
    now_utc = datetime.now(timezone.utc)
    until = parse_dt(args.until, tz) if args.until else now_utc
    days = args.days if args.days is not None else int(config["report"].get("lookbackDays", 7))
    since = parse_dt(args.since, tz) if args.since else until - timedelta(days=days)

    repo_dir = ensure_repo(config, fetch=not args.no_fetch)
    ref = resolve_ref(repo_dir, config["product"].get("branch", "main"))
    commits = collect_commits(repo_dir, ref, since, until, config)
    summary = summarize(repo_dir, ref, since, until, commits, config, tz)

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz).strftime("%Y-%m-%d")
    json_path = SOURCE_DIR / f"{stamp}-streamable-source.json"
    md_path = SOURCE_DIR / f"{stamp}-streamable-source.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(render_markdown(summary) + "\n")

    if args.print_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Commits collected: {len(commits)}")
    return 0


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def parse_dt(value: str, tz: ZoneInfo) -> datetime:
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> GitResult:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    return GitResult(proc.stdout, proc.stderr)


def ensure_repo(config: dict[str, Any], fetch: bool) -> Path:
    repo_rel = Path(config["product"]["localRepoDir"])
    repo_dir = ROOT / repo_rel
    repo_url = config["product"]["repoUrl"]
    branch = config["product"].get("branch", "main")
    if not (repo_dir / ".git").exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        clone = ["git", "clone", "--branch", branch, repo_url, str(repo_dir)]
        result = run(clone, check=False)
        if result.stderr and result.stdout:
            pass
        if not (repo_dir / ".git").exists():
            run(["git", "clone", repo_url, str(repo_dir)])
    elif fetch:
        run(["git", "fetch", "--prune", "origin"], cwd=repo_dir)
    return repo_dir


def resolve_ref(repo_dir: Path, branch: str) -> str:
    remote_ref = f"origin/{branch}"
    if run(["git", "rev-parse", "--verify", remote_ref], cwd=repo_dir, check=False).stdout.strip():
        return remote_ref
    if run(["git", "rev-parse", "--verify", branch], cwd=repo_dir, check=False).stdout.strip():
        return branch
    return "HEAD"


def collect_commits(
    repo_dir: Path,
    ref: str,
    since: datetime,
    until: datetime,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    pretty = "%H%x1f%ad%x1f%an%x1f%s"
    log = run(
        [
            "git",
            "log",
            ref,
            f"--since={since.isoformat()}",
            f"--until={until.isoformat()}",
            "--date=iso-strict",
            f"--pretty=format:{pretty}",
        ],
        cwd=repo_dir,
    ).stdout
    commits: list[dict[str, Any]] = []
    for line in log.splitlines():
        parts = line.split("\x1f", 3)
        if len(parts) != 4:
            continue
        sha, date, author, subject = parts
        files = commit_files(repo_dir, sha)
        commits.append(
            {
                "sha": sha,
                "shortSha": sha[:10],
                "date": date,
                "author": author,
                "subject": subject,
                "files": files,
                "categories": categorize(files, subject, config),
                "sensitive": is_sensitive(subject, files, config),
            }
        )
    return commits


def commit_files(repo_dir: Path, sha: str) -> list[dict[str, str]]:
    output = run(["git", "show", "--name-status", "--format=", sha], cwd=repo_dir).stdout
    files: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1] if len(parts) > 1 else ""
        old_path = parts[1] if status.startswith("R") and len(parts) > 2 else ""
        files.append({"status": status, "path": path, "oldPath": old_path})
    return files


def categorize(files: list[dict[str, str]], subject: str, config: dict[str, Any]) -> list[str]:
    paths = [item["path"].lower() for item in files]
    subject_l = subject.lower()
    focus = config["focus"]
    categories: set[str] = set()
    if any(matches_hint(path, focus["webappPathHints"]) for path in paths):
        categories.add("webapp")
    if any(matches_hint(path, focus["serverUserFacingHints"]) for path in paths):
        categories.add("server-user-facing")
    if any(matches_hint(path, focus["internalOnlyHints"]) for path in paths):
        categories.add("internal")
    if any(path.endswith((".md", ".mdx", ".rst")) or "docs/" in path for path in paths):
        categories.add("docs")
    if any(term in subject_l for term in ["upload", "uploads", "clip", "clips", "recording", "recordings", "media"]):
        categories.add("upload-corner")
    if not categories:
        categories.add("uncategorized")
    return sorted(categories)


def matches_hint(path: str, hints: list[str]) -> bool:
    for hint in hints:
        h = hint.lower()
        if h.endswith("/") and path.startswith(h):
            return True
        if h in path:
            return True
    return False


def is_sensitive(subject: str, files: list[dict[str, str]], config: dict[str, Any]) -> bool:
    terms = [term.lower() for term in config["focus"]["sensitiveTerms"]]
    haystack = subject.lower() + " " + " ".join(item["path"].lower() for item in files)
    return any(term in haystack for term in terms)


def summarize(
    repo_dir: Path,
    ref: str,
    since: datetime,
    until: datetime,
    commits: list[dict[str, Any]],
    config: dict[str, Any],
    tz: ZoneInfo,
) -> dict[str, Any]:
    file_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    authors: Counter[str] = Counter()
    public_candidates = 0
    sensitive_count = 0

    for commit in commits:
        authors[commit["author"]] += 1
        if commit["sensitive"] or "internal" in commit["categories"]:
            sensitive_count += 1
        else:
            public_candidates += 1
        for category in commit["categories"]:
            category_counter[category] += 1
        for item in commit["files"]:
            file_counter[item["path"]] += 1
            status_counter[item["status"][0]] += 1

    base = run(
        ["git", "rev-list", "-1", f"--before={since.isoformat()}", ref],
        cwd=repo_dir,
        check=False,
    ).stdout.strip()
    diffstat = ""
    full_diffstat = ""
    if base:
        diff_args = ["git", "diff", "--stat", f"{base}..{ref}"]
        pathspecs = config["focus"].get("diffPathspecs", ["webapp"])
        diffstat = run(diff_args + ["--", *pathspecs], cwd=repo_dir, check=False).stdout.strip()
        full_diffstat = run(diff_args, cwd=repo_dir, check=False).stdout.strip()

    return {
        "product": config["product"],
        "window": {
            "sinceUtc": since.isoformat(),
            "untilUtc": until.isoformat(),
            "sinceLocal": since.astimezone(tz).isoformat(),
            "untilLocal": until.astimezone(tz).isoformat(),
            "timezone": str(tz),
        },
        "repo": {
            "path": str(repo_dir),
            "ref": ref,
            "head": run(["git", "rev-parse", ref], cwd=repo_dir).stdout.strip(),
        },
        "counts": {
            "commits": len(commits),
            "publicCandidateCommits": public_candidates,
            "sensitiveOrInternalCommits": sensitive_count,
            "changedFiles": len(file_counter),
        },
        "categories": dict(category_counter.most_common()),
        "fileStatus": dict(status_counter.most_common()),
        "topFiles": file_counter.most_common(30),
        "authors": authors.most_common(),
        "diffstat": diffstat,
        "fullDiffstatLineCount": len(full_diffstat.splitlines()) if full_diffstat else 0,
        "commits": commits,
        "editorRules": [
            "Write for streamers, not developers.",
            "Use 4-6 concise bullets on average.",
            "Mention Upload Corner only when upload/media changes are materially relevant.",
            "Never mention secrets, keys, tokens, credential work, security internals, CI-only chores, migrations, or private infrastructure.",
            "Do not invent changes. If evidence is unclear, omit it.",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    product = summary["product"]
    window = summary["window"]
    counts = summary["counts"]
    lines.append("# Streamable Weekly Source Briefing")
    lines.append("")
    lines.append(f"- Product repo: `{product['repoUrl']}`")
    lines.append(f"- Focus: `{product.get('site', 'streamable.run')}` web app and user-facing product behavior")
    lines.append(f"- Window: {window['sinceLocal']} to {window['untilLocal']} ({window['timezone']})")
    lines.append(f"- Commits collected: {counts['commits']}")
    lines.append(f"- Public-candidate commits: {counts['publicCandidateCommits']}")
    lines.append(f"- Sensitive/internal commits to avoid mentioning directly: {counts['sensitiveOrInternalCommits']}")
    lines.append("")
    lines.append("## Category Counts")
    for category, count in summary["categories"].items():
        lines.append(f"- {category}: {count}")
    lines.append("")
    lines.append("## Focus Diffstat")
    lines.append("```")
    lines.append(summary["diffstat"] or "No diffstat available for this window.")
    lines.append("```")
    if summary.get("fullDiffstatLineCount"):
        lines.append("")
        lines.append(f"Full repo diffstat line count: {summary['fullDiffstatLineCount']} (omitted here to keep webapp changes prominent).")
    lines.append("")
    lines.append("## Top Changed Files")
    for path, count in summary["topFiles"][:20]:
        lines.append(f"- `{path}` ({count})")
    lines.append("")
    lines.append("## Commit Inventory")
    for commit in summary["commits"]:
        if commit["sensitive"]:
            flag = "omit-sensitive"
        elif "internal" in commit["categories"]:
            flag = "omit-internal"
        else:
            flag = "public-candidate"
        categories = ", ".join(commit["categories"])
        lines.append(f"- `{commit['shortSha']}` {commit['date']} [{flag}; {categories}] {commit['subject']}")
        shown = 0
        for item in commit["files"]:
            if shown >= 8:
                remaining = len(commit["files"]) - shown
                lines.append(f"  - ... {remaining} more files")
                break
            lines.append(f"  - {item['status']}: `{item['path']}`")
            shown += 1
    lines.append("")
    lines.append("## Editor Rules")
    for rule in summary["editorRules"]:
        lines.append(f"- {rule}")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"collect_changes.py failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
