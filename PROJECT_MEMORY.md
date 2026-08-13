# Project Memory: Shibei Digest

Last updated: 2026-07-17, Asia/Shanghai.

## What This Project Does

This repository powers a personal reading digest for Bohaishibei. It collects new posts from the Bohaishibei digest category, excludes ads/promotions and fiction/serial-story content, creates a phone-friendly HTML page plus Markdown archive, then pushes the digest to both Bark and Feishu.

Production repository:

```text
https://github.com/lxinxin-cloud/shibei-digest
```

Production archive URL:

```text
https://lxinxin-cloud.github.io/shibei-digest/
```

## Current Production Configuration

- Runtime: GitHub Actions.
- Hosting: GitHub Pages, configured for GitHub Actions deployment.
- Schedule: daily cron at UTC 00:00, which is Beijing/Shanghai 08:00.
- Effective cadence: every two days, enforced by `--min-run-interval-hours 36`; the local Codex automation has been disabled, so GitHub Actions is the only production scheduler.
- Notifications: Bark and Feishu.
- Required GitHub Actions secrets:
  - `BARK_DEVICE_KEY`
  - `FEISHU_WEBHOOK_URL`

Secrets are already configured in the GitHub repository as of this handoff, but the actual secret values must never be written into files.

## Important Files

- `scripts/shibei_digest.py`: main automation script.
- `.github/workflows/shibei.yml`: cloud schedule, build, notification, commit, and Pages deploy.
- `public/index.html`: stable history page listing all generated collections.
- `public/latest.html`: backward-compatible latest page, not the canonical notification target.
- `public/latest.md`: backward-compatible latest Markdown output.
- `public/archive/`: canonical timestamped generated outputs.
- `state/seen_articles.json`: dedupe list and `last_checked_at`.
- `scripts/setup_secrets.sh`: helper for local macOS Keychain secrets.
- `README.md`: operator-facing setup and usage.
- `AGENTS.md`: maintainer and coding-agent instructions.

## Current Behavior Details

The script uses `https://www.bohaishibei.com/post/category/digest/` as the crawl source, not the entire homepage. This was chosen because the user wants readable article digests and wants to avoid ad/deal/novel-style content.

The crawler paginates through digest pages using `--max-pages`; production now passes `--max-pages 0`, meaning it continues until every dated article on a page is older than the crawl window.

Production no longer passes a 30-article cap. The default `--limit 0` means no cap; a positive limit is applied only after date filtering, ad/fiction filtering, and seen-URL deduplication. Run JSON reports each stage and `truncated`.

The crawl window starts at the earlier of:

- now minus `--max-age-hours` hours, default 48; and
- `last_checked_at` from `state/seen_articles.json`.

This lets the next successful run backfill if a scheduled run was delayed or failed.

The Bohaishibei listing exposes publication dates but not precise times. The selection logic intentionally compares Beijing dates rather than exact timestamps.

## Notification Semantics

Scheduled runs:

- Send notifications only when new selected articles exist.
- Update state even when there are no new articles.
- Fail if notification was expected and Bark or Feishu did not send, because GitHub Actions passes `--require-delivery`.

Manual workflow dispatch:

- Can force a run even if the 48-hour interval has not elapsed.
- Defaults to sending an empty notification when no new articles are selected, which is useful for testing.

## Known Risks And Maintenance Notes

- Filtering is keyword-based. If long stories or ads slip through, update `EXCLUDE_KEYWORDS` in `scripts/shibei_digest.py`.
- If the site changes HTML structure, inspect `parse_digest_page()` first. It currently relies on `#recent-content .post`, `h2.entry-title a`, `.entry-date`, and `.entry-summary`.
- If the site pagination stops exposing older pages, inspect `fetch_digest_articles()` and the reported `fetched`/`in_window` counts.
- If GitHub Actions is delayed, the date-window logic should still backfill, but very old backfills may include more articles than desired.
- Bark and Feishu open the dated archive page when `PUBLIC_BASE_URL` is set. GitHub Actions sets it to the GitHub Pages base URL.
- Feishu receives structured rich text plus the dated public HTML link.
- GitHub scheduled workflows can run a little late. The important invariant is cloud execution, not exact second-level timing.

## Validation Checklist

Use this before handing the project back after changes:

```bash
python3 -m compileall scripts
python3 scripts/shibei_digest.py --dry-run --include-seen
```

Then check, if touching deployment or notifications:

- GitHub Actions `Shibei Digest` latest run is green.
- GitHub Pages opens at `https://lxinxin-cloud.github.io/shibei-digest/` and lists historical collections.
- Bark notification opens a dated archive page, not `latest.html`.
- Feishu message includes the dated archive page link and article links.
- `state/seen_articles.json` was updated only when intended.

## Local Repository State At Handoff

Before the documentation files were added, local git status already showed:

```text
## main...origin/main [ahead 1, behind 7]
 M .github/workflows/shibei.yml
 M scripts/shibei_digest.py
```

After this handoff documentation, expect additional local changes to `README.md`, `AGENTS.md`, and `PROJECT_MEMORY.md`.

The branch divergence happened because some remote fixes were applied outside a normal local `git push` flow. Treat GitHub as the production source of truth before publishing more local changes. Fetch and inspect carefully; do not run destructive git commands without explicit user approval.

## Recommended Next Improvements

- Add a small fixture-based parser test for `parse_digest_page()`.
- Add a dry-run summary that prints page count and stop reason.
- Consider a simple allow/deny review log for filtered titles if the user wants better quality control.
- Consider content-length or per-article heuristics only if keyword filtering proves insufficient.

## Local Preview Run (Occasional)

Verified 2026-07-17. Use this to preview the current digest locally without touching production state, notifications, or the cloud cadence. Not part of the regular flow — the normal path is GitHub Actions.

Why: the local repo can diverge from origin and local `state/seen_articles.json` can be stale, so the preview uses the cloud state as its starting point.

```bash
cd "<repo root>"
gh api repos/lxinxin-cloud/shibei-digest/contents/state/seen_articles.json --jq '.content' | base64 -d > /tmp/shibei_preview_state.json
python3 scripts/shibei_digest.py --dry-run --state-path /tmp/shibei_preview_state.json --output-dir output
```

Behavior notes:

- `--dry-run` still writes `output/shibei-digest-YYYY-MM-DD-HHMM.{html,md}` but sends no Bark/Feishu notifications and saves no state.
- Window and dedupe match production because the state file comes from the cloud repo via `gh api`.
- Requires `gh` CLI authenticated (confirmed working on this machine 2026-07-17) and local Python deps installed.
- `raw.githubusercontent.com` is unreachable from this network; use `gh api` instead of curl for repo files.
- Latest published collection time is visible at `https://lxinxin-cloud.github.io/shibei-digest/`.
