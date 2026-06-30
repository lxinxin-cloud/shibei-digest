#!/usr/bin/env python3
"""Build a mobile-friendly digest for new Bohaishibei articles."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.bohaishibei.com"
DIGEST_URL = f"{BASE_URL}/post/category/digest/"
STATE_PATH = Path("state/seen_articles.json")
OUTPUT_DIR = Path("output")
PUBLIC_DIR = Path("public")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)

EXCLUDE_KEYWORDS = (
    "广告",
    "优惠",
    "折扣",
    "包邮",
    "券",
    "领券",
    "天猫",
    "淘宝",
    "京东",
    "小说",
    "连载",
    "番外",
    "章节",
    "赞助",
    "推广",
)


def secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value

    service = f"shibei_digest_{name}"
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


@dataclasses.dataclass(frozen=True)
class Article:
    title: str
    url: str
    published: dt.datetime | None
    summary: str
    category: str


def fetch(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_chinese_date(value: str) -> dt.datetime | None:
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", value or "")
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return dt.datetime(year, month, day, tzinfo=dt.timezone(dt.timedelta(hours=8)))


def parse_digest_page(page_html: str) -> list[Article]:
    soup = BeautifulSoup(page_html, "html.parser")
    articles: list[Article] = []
    seen_urls: set[str] = set()

    for node in soup.select("#recent-content .post"):
        title_link = node.select_one("h2.entry-title a")
        if not title_link:
            continue
        url = title_link.get("href", "").strip()
        title = clean_text(title_link.get_text(" "))
        if not url or not title or url in seen_urls:
            continue

        date_node = node.select_one(".entry-date")
        summary_node = node.select_one(".entry-summary")
        published = parse_chinese_date(date_node.get_text(" ") if date_node else "")
        summary = clean_text(summary_node.get_text(" ") if summary_node else "")
        articles.append(
            Article(
                title=title,
                url=url,
                published=published,
                summary=summary,
                category=classify(title, summary),
            )
        )
        seen_urls.add(url)

    return articles


def classify(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    rules = [
        ("科技", ("AI", "芯片", "手机", "互联网", "平台", "算法", "应用", "数据")),
        ("商业", ("公司", "价格", "裁员", "发财", "投资", "股票", "市场", "消费")),
        ("社会", ("社会", "婚姻", "相亲", "教育", "学校", "医院", "案件", "城市")),
        ("生活", ("生活", "家庭", "孩子", "父母", "旅行", "吃", "天气", "高温")),
        ("观点", ("为什么", "怎么看", "锐评", "讨论", "反思", "价值")),
    ]
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "其他"


def should_exclude(article: Article) -> bool:
    text = f"{article.title} {article.summary}"
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return set(data.get("seen_urls", []))


def save_seen(path: Path, seen_urls: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "seen_urls": sorted(set(seen_urls)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_new_articles(
    articles: list[Article],
    seen_urls: set[str],
    max_age_hours: int,
    include_seen: bool,
) -> list[Article]:
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    earliest = now - dt.timedelta(hours=max_age_hours)
    selected: list[Article] = []

    for article in articles:
        if not include_seen and article.url in seen_urls:
            continue
        if article.published and article.published < earliest:
            continue
        if should_exclude(article):
            continue
        selected.append(article)

    return selected


def short_summary(article: Article, limit: int = 160) -> str:
    summary = article.summary or "暂无摘要。"
    if len(summary) <= limit:
        return summary
    return summary[: limit - 1].rstrip() + "..."


def group_articles(articles: list[Article]) -> dict[str, list[Article]]:
    groups: dict[str, list[Article]] = {}
    for article in articles:
        groups.setdefault(article.category, []).append(article)
    return groups


def render_markdown(articles: list[Article], generated_at: dt.datetime) -> str:
    lines = [
        f"# 拾贝文章汇总 {generated_at:%Y-%m-%d %H:%M}",
        "",
        f"本次共 {len(articles)} 篇。已过滤广告、优惠、推广、小说/连载类内容。",
        "",
    ]
    if not articles:
        lines.extend(["过去周期内没有发现新的合适文章。", ""])
        return "\n".join(lines)

    for category, items in group_articles(articles).items():
        lines.extend([f"## {category}", ""])
        for article in items:
            date_text = article.published.strftime("%Y-%m-%d") if article.published else "日期未知"
            lines.extend(
                [
                    f"### [{article.title}]({article.url})",
                    f"- 日期：{date_text}",
                    f"- 摘要：{short_summary(article)}",
                    f"- 阅读建议：{reading_hint(article)}",
                    "",
                ]
            )
    return "\n".join(lines)


def reading_hint(article: Article) -> str:
    if article.category in {"科技", "商业"}:
        return "适合优先读，信息密度较高。"
    if article.category == "社会":
        return "适合通勤阅读，容易引发讨论。"
    if article.category == "生活":
        return "轻松阅读，适合休息时看。"
    return "看标题兴趣决定。"


def render_html(articles: list[Article], generated_at: dt.datetime) -> str:
    title = f"拾贝文章汇总 {generated_at:%Y-%m-%d}"
    cards: list[str] = []
    for category, items in group_articles(articles).items():
        cards.append(f"<section><h2>{html.escape(category)}</h2>")
        for article in items:
            date_text = article.published.strftime("%Y-%m-%d") if article.published else "日期未知"
            cards.append(
                f"""
<article class="card">
  <div class="meta">{html.escape(date_text)} · {html.escape(article.category)}</div>
  <h3>{html.escape(article.title)}</h3>
  <p>{html.escape(short_summary(article))}</p>
  <p class="hint">{html.escape(reading_hint(article))}</p>
  <a class="button" href="{html.escape(article.url)}">打开原文</a>
</article>
"""
            )
        cards.append("</section>")

    if not cards:
        cards.append('<p class="empty">过去周期内没有发现新的合适文章。</p>')

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f4ef;
      --fg: #1f2328;
      --muted: #667085;
      --card: #fffdf8;
      --line: #e4ddd2;
      --accent: #0f766e;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #171717;
        --fg: #efefef;
        --muted: #a3a3a3;
        --card: #222;
        --line: #383838;
        --accent: #5eead4;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      line-height: 1.75;
    }}
    main {{
      width: min(760px, 100%);
      margin: 0 auto;
      padding: 28px 16px 48px;
    }}
    header {{
      padding: 8px 0 18px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 22px;
    }}
    h1 {{
      font-size: 30px;
      line-height: 1.2;
      margin: 0 0 10px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 20px;
      margin: 28px 0 12px;
      letter-spacing: 0;
    }}
    h3 {{
      font-size: 19px;
      line-height: 1.35;
      margin: 6px 0 10px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 12px; }}
    .sub, .meta, .hint {{
      color: var(--muted);
      font-size: 14px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin: 12px 0;
    }}
    .button {{
      display: inline-block;
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
      padding: 4px 0;
    }}
    .empty {{
      padding: 24px 0;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title)}</h1>
      <p class="sub">生成时间：{generated_at:%Y-%m-%d %H:%M} · 共 {len(articles)} 篇 · 已过滤广告/优惠/推广/小说</p>
    </header>
    {''.join(cards)}
  </main>
</body>
</html>
"""


def write_outputs(
    articles: list[Article],
    output_dir: Path,
    public_dir: Path | None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    stamp = generated_at.strftime("%Y-%m-%d-%H%M")
    html_content = render_html(articles, generated_at)
    markdown_content = render_markdown(articles, generated_at)

    html_path = output_dir / f"shibei-digest-{stamp}.html"
    md_path = output_dir / f"shibei-digest-{stamp}.md"
    html_path.write_text(html_content, encoding="utf-8")
    md_path.write_text(markdown_content, encoding="utf-8")

    if not public_dir:
        return html_path, md_path

    public_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = public_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    latest_html = public_dir / "latest.html"
    latest_md = public_dir / "latest.md"
    archive_html = archive_dir / f"shibei-digest-{stamp}.html"
    archive_md = archive_dir / f"shibei-digest-{stamp}.md"

    latest_html.write_text(html_content, encoding="utf-8")
    latest_md.write_text(markdown_content, encoding="utf-8")
    archive_html.write_text(html_content, encoding="utf-8")
    archive_md.write_text(markdown_content, encoding="utf-8")
    return latest_html, latest_md


def public_url_for(path: Path) -> str | None:
    base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return None
    return f"{base_url}/{path.name}"


def send_bark(articles: list[Article], html_path: Path) -> bool:
    key = secret("BARK_DEVICE_KEY")
    if not key:
        return False
    server = os.getenv("BARK_SERVER", "https://api.day.app").strip().rstrip("/")
    title = f"拾贝新文 {len(articles)} 篇"
    body = "本次没有新的合适文章。" if not articles else "\n".join(
        f"{idx}. {article.title}" for idx, article in enumerate(articles[:8], 1)
    )
    payload = {
        "title": title,
        "body": body,
        "group": "拾贝文章汇总",
    }
    url = public_url_for(html_path)
    if url:
        payload["url"] = url
    payload["device_key"] = key
    response = requests.post(f"{server}/push", json=payload, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code} {response.text[:500]}")
    return True


def feishu_blocks(articles: list[Article], html_path: Path) -> list[list[dict[str, str]]]:
    lines: list[list[dict[str, str]]] = []
    url = public_url_for(html_path)
    if url:
        lines.append([{"tag": "a", "text": "打开手机优化 HTML", "href": url}])
        lines.append([{"tag": "text", "text": ""}])

    if not articles:
        lines.append([{"tag": "text", "text": "过去周期内没有发现新的合适文章。"}])
        return lines

    for category, items in group_articles(articles).items():
        lines.append([{"tag": "text", "text": f"【{category}】"}])
        for index, article in enumerate(items, 1):
            text = f"{index}. {article.title}\n{short_summary(article, 120)}\n"
            lines.append(
                [
                    {"tag": "text", "text": text},
                    {"tag": "a", "text": "原文", "href": article.url},
                ]
            )
        lines.append([{"tag": "text", "text": ""}])
    return lines


def send_feishu(articles: list[Article], html_path: Path) -> bool:
    webhook = secret("FEISHU_WEBHOOK_URL")
    if not webhook:
        return False
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"拾贝文章汇总：{len(articles)} 篇新文",
                    "content": feishu_blocks(articles, html_path),
                }
            }
        },
    }
    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    if data.get("code") not in (0, None):
        raise RuntimeError(f"Feishu webhook rejected message: {data}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send Bohaishibei digest.")
    parser.add_argument("--max-age-hours", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true", help="Do not send notifications or update state.")
    parser.add_argument("--include-seen", action="store_true", help="Include URLs already in state.")
    parser.add_argument("--state-path", type=Path, default=STATE_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--public-dir",
        type=Path,
        default=None,
        help="Also write latest.html/latest.md and archive files for static hosting.",
    )
    parser.add_argument(
        "--save-without-delivery",
        action="store_true",
        help="Update state even if Bark and Feishu are not configured or fail to send.",
    )
    parser.add_argument(
        "--notify-empty",
        action="store_true",
        help="Send Bark and Feishu notifications even when no new articles are selected.",
    )
    parser.add_argument("--limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_text = fetch(DIGEST_URL)
    articles = parse_digest_page(html_text)[: args.limit]
    seen_urls = load_seen(args.state_path)
    selected = select_new_articles(
        articles,
        seen_urls=seen_urls,
        max_age_hours=args.max_age_hours,
        include_seen=args.include_seen,
    )
    html_path, md_path = write_outputs(selected, args.output_dir, args.public_dir)

    bark_sent = False
    feishu_sent = False
    errors: list[str] = []
    if not args.dry_run:
        should_notify = bool(selected) or args.notify_empty
        if should_notify:
            try:
                bark_sent = send_bark(selected, html_path)
            except Exception as exc:
                errors.append(f"Bark: {exc}")

            try:
                feishu_sent = send_feishu(selected, html_path)
            except Exception as exc:
                errors.append(f"Feishu: {exc}")

        if bark_sent or feishu_sent or args.save_without_delivery or not should_notify:
            save_seen(args.state_path, seen_urls | {article.url for article in selected})

    print(json.dumps(
        {
            "found": len(articles),
            "selected": len(selected),
            "html": str(html_path),
            "markdown": str(md_path),
            "bark_sent": bark_sent,
            "feishu_sent": feishu_sent,
            "dry_run": args.dry_run,
            "errors": errors,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 1 if errors and not (bark_sent or feishu_sent) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
