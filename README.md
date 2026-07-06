# Streamable Weekly Updates Agent

This workspace is the OpenClaw agent for weekly Streamable product updates.

It tracks:

- Product repo: `https://github.com/teliclabs/streamable`
- Primary focus: web app and user-facing server behavior
- Recipient: `nathanang2000@gmail.com`
- Output: a public `/updates` page entry, plus concise Markdown Discord-ready, LinkedIn-ready, and X-ready weekly drafts for Nathan

## Weekly Flow

1. The agent creates a status artifact at `output/status/YYYY-MM-DD/YYYY-MM-DDTHHMMSS-weekly-status.md` and sends a short start checkpoint.
2. `scripts/collect_changes.py` fetches the Streamable repo and writes a source briefing from the last 7 days of commits.
3. The agent checkpoints after collection, reads the source briefing, and drafts 4-6 user-facing Discord paragraphs.
4. The agent writes the final Discord-ready copy to `output/outbox/YYYY-MM-DD-streamable-weekly.md`.
5. The agent writes a LinkedIn-ready post with the FAQ section to `output/outbox/YYYY-MM-DD-streamable-linkedin.md`.
6. The agent writes an X-ready post without the FAQ section and without a `/updates` link to `output/outbox/YYYY-MM-DD-streamable-x.md`.
7. The agent checkpoints after all drafts are written.
8. The agent updates `repo/streamable/webapp/content/product-updates.ts` so `https://streamable.run/updates` includes the new public weekly highlights.
9. The agent checkpoints before the webapp build, then runs `npm run build` from `repo/streamable/webapp`.
10. The agent checkpoints after the build result.
11. If the build passes, the agent commits and pushes the Streamable product repo changes to `origin main`, then checkpoints the commit hash and push result.
12. After the product repo push succeeds, `scripts/send_report.py --send --report <discord-file> --linkedin-report <linkedin-file> --x-report <x-file>` emails all drafts and approval commands to Nathan.
13. The agent checkpoints the email recipient, send result, and Resend id if available.
14. The weekly run stops there. LinkedIn and X are posted only after Nathan explicitly approves each draft.

The script does not post to Discord, post to LinkedIn, post to X, or send to the email list. LinkedIn and X posting are done only by browser automation after explicit approval. The current social posting mode is text-only; do not attach image assets unless Nathan explicitly asks for media again.

The agent must not push `/updates` changes unless `npm run build` passes, and it must not email Nathan until the product repo push succeeds. The agent must never post from Nathan's personal LinkedIn profile.

## Run Status

Weekly runs should keep a lightweight generated status file in `output/status/` using the local `America/Los_Angeles` date and timestamp:

```text
output/status/YYYY-MM-DD/YYYY-MM-DDTHHMMSS-weekly-status.md
```

Update the file, and send a concise manager checkpoint, when the run starts, after change collection, after drafts are written, before and after the webapp build, after commit/push, after email send, and on any blocker.

The status file should include phase, files touched, build result, commit hash, push result, email recipient/result/Resend id, social posting status, blockers, and next action. Generated status files are operational artifacts; do not commit them.

## LinkedIn Approval

Weekly email approval commands:

```text
APPROVE LINKEDIN YYYY-MM-DD
APPROVE X YYYY-MM-DD
```

For now, Nathan should send that command in OpenClaw/Telegram after reviewing the email. Plain email replies are not automatic until Gmail Pub/Sub webhook approval is configured with `openclaw webhooks gmail setup` and `gog`/`gogcli`.

## Manual Run

From this workspace:

```bash
python3 scripts/collect_changes.py --days 7
```

Then ask the `streamable-weekly-updates` OpenClaw agent to draft the report and update the public page, or create a markdown file manually.

For the public page update, edit the cloned product repo in `repo/streamable`, then run:

```bash
cd repo/streamable/webapp
npm run build
```

Only commit and push the product repo after the build succeeds.

After the product repo push succeeds, email Nathan the Markdown report:

```bash
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --linkedin-report output/outbox/YYYY-MM-DD-streamable-linkedin.md --x-report output/outbox/YYYY-MM-DD-streamable-x.md --dry-run
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --linkedin-report output/outbox/YYYY-MM-DD-streamable-linkedin.md --x-report output/outbox/YYYY-MM-DD-streamable-x.md --send
```

After approval, use browser profile `streamable-linkedin-weekly` and start from:

`https://www.linkedin.com/company/110907670/admin/`

Only publish if the composer is clearly posting as Streamable.

The OpenClaw profile path is `/Users/streamable/.openclaw/browser/streamable-linkedin-weekly/user-data`, copied from the logged-in profile at `/Users/streamable/.openclaw/browser-profiles/streamable-linkedin-weekly`.

Known-good LinkedIn path saved from the successful 2026-06-30 run:

- Start from `https://www.linkedin.com/company/110907670/admin/`.
- Use the Create button on that company admin page.
- Paste the text-only LinkedIn draft with the FAQ section.
- Remove any automatic link preview when running text-only.
- Verify the composer is posting as Streamable.
- Publish and capture the post URL.

Successful reference post: `https://www.linkedin.com/feed/update/urn:li:share:7477884120233033728?actorCompanyId=110907670`

For X posting, use browser profile `streamable-x-weekly` and start from:

`https://x.com/home`

Only publish if the browser is clearly logged into the intended StreamableRun account. The X draft should mirror LinkedIn but omit the FAQ section and the `/updates` link.

Known-good X path saved from the successful 2026-06-30 run:

- Use browser profile `streamable-x-weekly`.
- Prefer `https://x.com/intent/post?text=<url-encoded-approved-draft>` so the full text renders visibly in the composer.
- Verify the composer text is visible, logged in as `@streamablerun`, no FAQ is present, and no `/updates` link is present.
- Click the enabled `Post` button once, then verify the new post on `https://x.com/streamablerun`.

## GitHub Persistence

This workspace is stored at:

`https://github.com/teliclabs/streamable-weekly-updates-agent.git`

Do not commit cloned product code, generated reports, or credentials.
