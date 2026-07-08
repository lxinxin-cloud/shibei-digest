# WebNews Rules

This repository maintains the Bohaishibei digest automation.

Goal: collect new digest articles, filter ads/promotions and fiction/serial content, render a mobile-friendly digest, and send it to Bark and Feishu.

Never commit Bark keys, Feishu webhooks, GitHub tokens, or other secrets.

Preserve generated archives unless explicitly asked to delete them.

Treat `state/seen_articles.json` as production state for deduplication and cadence.

Production uses GitHub Actions and GitHub Pages at `https://lxinxin-cloud.github.io/shibei-digest/`.

The daily cron is UTC 00:00, equal to 08:00 Asia/Shanghai. The script uses `--min-run-interval-hours 36`, creating an effective every-two-days cadence.

Main code is `scripts/shibei_digest.py`. `public/index.html` is the history entry page. `public/archive/` contains canonical dated collection files. `public/latest.html` and `public/latest.md` are backward-compatible latest files only.

Bark and Feishu notification links should point to the dated archive file returned by `write_outputs()`, not to `latest.html`.

Keep iPhone-sized reading experience readable when changing generated pages.

Validate behavior changes with:

```bash
python3 -m compileall scripts
python3 scripts/shibei_digest.py --dry-run --include-seen --max-pages 8 --limit 80
```

Check local and remote git state before publishing. Do not use destructive cleanup commands unless explicitly approved.
