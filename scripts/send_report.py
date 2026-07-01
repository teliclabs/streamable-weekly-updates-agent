#!/usr/bin/env python3
"""Send a weekly Streamable update draft by email using Resend's HTTP API."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
PAYLOAD_DIR = ROOT / "output" / "email-payloads"


def main() -> int:
    parser = argparse.ArgumentParser(description="Email a Streamable weekly update markdown report.")
    parser.add_argument("--report", required=True, help="Markdown Discord report path.")
    parser.add_argument("--linkedin-report", help="Optional Markdown LinkedIn post draft path.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--send", action="store_true", help="Send the email.")
    mode.add_argument("--dry-run", action="store_true", help="Write payload and do not send.")
    parser.add_argument("--subject", help="Override email subject.")
    args = parser.parse_args()

    config = load_config()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    if not report_path.exists():
        raise SystemExit(f"Missing report file: {report_path}")

    markdown = read_markdown_report(report_path, "Report")
    if not markdown:
        raise SystemExit(f"Report file is empty: {report_path}")

    linkedin_markdown = None
    if args.linkedin_report:
        linkedin_path = Path(args.linkedin_report)
        if not linkedin_path.is_absolute():
            linkedin_path = ROOT / linkedin_path
        linkedin_markdown = read_markdown_report(linkedin_path, "LinkedIn report")

    load_env(config)
    payload = build_payload(config, markdown, args.subject, linkedin_markdown)
    save_payload(payload)

    if not args.send:
        print("Dry run only. Payload saved.")
        print(json.dumps({k: v for k, v in payload.items() if k != "html"}, indent=2, ensure_ascii=False))
        return 0

    api_key_env = config["email"].get("apiKeyEnv", "RESEND_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise SystemExit(f"Missing {api_key_env}. Configure .env before sending.")

    result = send_resend(config["email"]["apiUrl"], api_key, payload)
    print(json.dumps({"sent": True, "result": result}, indent=2, ensure_ascii=False))
    return 0


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def read_markdown_report(path: Path, label: str) -> str:
    if not path.exists():
        raise SystemExit(f"Missing {label.lower()} file: {path}")
    markdown = path.read_text().strip()
    if not markdown:
        raise SystemExit(f"{label} file is empty: {path}")
    return markdown


def load_env(config: dict[str, Any]) -> None:
    for key in ("envPath", "fallbackEnvPath"):
        value = config["email"].get(key)
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            apply_dotenv(path)


def apply_dotenv(path: Path) -> None:
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_payload(
    config: dict[str, Any],
    markdown: str,
    subject: str | None,
    linkedin_markdown: str | None = None,
) -> dict[str, Any]:
    report_config = config["report"]
    tz = ZoneInfo(report_config.get("timezone", "America/Los_Angeles"))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    email_subject = subject or f"{report_config['subjectPrefix']} - {today}"
    intro = "Here is this week's Discord-ready Streamable update draft in Markdown."
    combined_markdown = markdown
    if linkedin_markdown:
        intro = "Here are this week's Discord and LinkedIn-ready Streamable update drafts."
        combined_markdown = (
            "## Discord draft\n\n"
            f"{markdown}\n\n"
            "## LinkedIn post draft\n\n"
            f"{linkedin_markdown}"
        )
    if "backfill" in markdown.lower():
        intro = "Here is the Streamable updates backfill draft."
    wrapped_text = (
        f"{intro}\n\n"
        "Review before posting or sending to the wider email list.\n\n"
        "-----\n\n"
        f"{combined_markdown}\n"
    )
    wrapped_html = render_html(combined_markdown, intro)
    payload = {
        "from": report_config["from"],
        "to": [report_config["recipient"]],
        "subject": email_subject,
        "text": wrapped_text,
        "html": wrapped_html,
        "reply_to": report_config.get("replyTo"),
    }
    return {key: value for key, value in payload.items() if value}


def render_html(markdown: str, intro: str) -> str:
    parts = [
        "<html><body style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.45; color: #111827;\">",
        f"<p>{html.escape(intro)}</p>",
        "<p><strong>Review before posting or sending to the wider email list.</strong></p>",
        "<hr>",
    ]
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{inline_markdown(line[2:].strip())}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{inline_markdown(line)}</p>")
    if in_list:
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    return escaped.replace("**", "")


def save_payload(payload: dict[str, Any]) -> Path:
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = PAYLOAD_DIR / f"{stamp}-payload.json"
    path.write_text(json.dumps(redact_payload(payload), indent=2, ensure_ascii=False) + "\n")
    return path


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload)


def send_resend(api_url: str, api_key: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "streamable-weekly-updates-agent/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {"status": response.status}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {exc.code}: {body}") from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"send_report.py failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
