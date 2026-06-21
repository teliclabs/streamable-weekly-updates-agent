# Streamable Weekly Updates Agent

This workspace is the OpenClaw agent for weekly Streamable product updates.

It tracks:

- Product repo: `https://github.com/teliclabs/streamable`
- Primary focus: web app and user-facing server behavior
- Recipient: `nathanang2000@gmail.com`
- Output: a concise Discord-ready weekly update draft for streamers, plus a public `/updates` page entry

## Weekly Flow

1. `scripts/collect_changes.py` fetches the Streamable repo and writes a source briefing from the last 7 days of commits.
2. The OpenClaw agent reads the source briefing and drafts 4-6 user-facing bullets.
3. The agent writes the final Discord-ready copy to `output/outbox/YYYY-MM-DD-streamable-weekly.md`.
4. `scripts/send_report.py --send --report <file>` emails the draft to Nathan.
5. The agent updates `repo/streamable/webapp/content/product-updates.ts` so `https://streamable.run/updates` includes the new public highlights.
6. The agent runs `npm run build` from `repo/streamable/webapp`.
7. If the build passes, the agent commits and pushes the Streamable product repo changes to `origin main`.

The script does not post to Discord or send to the email list. Nathan reviews and posts/sends manually.

The agent must not push `/updates` changes unless `npm run build` passes.

## Manual Run

From this workspace:

```bash
python3 scripts/collect_changes.py --days 7
```

Then ask the `streamable-weekly-updates` OpenClaw agent to draft and send the report, or create a markdown file manually and run:

```bash
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --dry-run
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --send
```

For the public page update, edit the cloned product repo in `repo/streamable`, then run:

```bash
cd repo/streamable/webapp
npm run build
```

Only commit and push the product repo after the build succeeds.

## GitHub Persistence

This workspace is stored at:

`https://github.com/teliclabs/streamable-weekly-updates-agent.git`

Do not commit cloned product code, generated reports, or credentials.
