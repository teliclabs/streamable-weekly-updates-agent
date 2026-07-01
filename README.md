# Streamable Weekly Updates Agent

This workspace is the OpenClaw agent for weekly Streamable product updates.

It tracks:

- Product repo: `https://github.com/teliclabs/streamable`
- Primary focus: web app and user-facing server behavior
- Recipient: `nathanang2000@gmail.com`
- Output: a public `/updates` page entry, plus concise Markdown Discord-ready and LinkedIn-ready weekly drafts for Nathan

## Weekly Flow

1. `scripts/collect_changes.py` fetches the Streamable repo and writes a source briefing from the last 7 days of commits.
2. The OpenClaw agent reads the source briefing and drafts 4-6 user-facing Discord paragraphs.
3. The agent writes the final Discord-ready copy to `output/outbox/YYYY-MM-DD-streamable-weekly.md`.
4. The agent writes a LinkedIn-ready post to `output/outbox/YYYY-MM-DD-streamable-linkedin.md`.
5. The agent updates `repo/streamable/webapp/content/product-updates.ts` so `https://streamable.run/updates` includes the new public weekly highlights.
6. The agent runs `npm run build` from `repo/streamable/webapp`.
7. If the build passes, the agent commits and pushes the Streamable product repo changes to `origin main`.
8. After the product repo push succeeds, `scripts/send_report.py --send --report <discord-file> --linkedin-report <linkedin-file> --linkedin-image assets/linkedin/streamable-linkedin-update-frame-1410143399.jpg` emails both drafts and the LinkedIn image asset to Nathan.

The script does not post to Discord, post to LinkedIn, or send to the email list. Nathan reviews and posts/sends manually. The LinkedIn image asset is stored at `assets/linkedin/streamable-linkedin-update-frame-1410143399.jpg`.

The agent must not push `/updates` changes unless `npm run build` passes, and it must not email Nathan until the product repo push succeeds.

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
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --linkedin-report output/outbox/YYYY-MM-DD-streamable-linkedin.md --linkedin-image assets/linkedin/streamable-linkedin-update-frame-1410143399.jpg --dry-run
python3 scripts/send_report.py --report output/outbox/YYYY-MM-DD-streamable-weekly.md --linkedin-report output/outbox/YYYY-MM-DD-streamable-linkedin.md --linkedin-image assets/linkedin/streamable-linkedin-update-frame-1410143399.jpg --send
```

## GitHub Persistence

This workspace is stored at:

`https://github.com/teliclabs/streamable-weekly-updates-agent.git`

Do not commit cloned product code, generated reports, or credentials.
