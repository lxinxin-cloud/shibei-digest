# 拾贝文章汇总

自动抓取博海拾贝“文摘”分类的新文章，过滤广告、优惠、推广、小说/连载类内容，生成适合手机阅读的 HTML 和 Markdown，并推送到 Bark 与飞书。

当前公网归档入口：

```text
https://lxinxin-cloud.github.io/shibei-digest/
```

## 运行方式

推荐生产方式是 GitHub Actions + GitHub Pages。仓库里的 `.github/workflows/shibei.yml` 会每天 UTC 00:00 触发一次，也就是北京时间早晨 8:00；脚本使用 `--min-run-interval-hours 36` 做间隔门禁，所以实际每两天推送一次。当前本地 Codex 自动化已停用，GitHub Actions 是唯一生产调度器。

手动触发：

```text
GitHub -> Actions -> Shibei Digest -> Run workflow
```

手动触发默认带 `--force-run --notify-empty`，适合测试 Bark、飞书和 Pages 发布链路。

## 本地开发

```bash
python3 -m pip install -r requirements.txt
python3 scripts/shibei_digest.py --dry-run --include-seen
```

本地输出默认写到 `output/`。正式静态页面写到 `public/archive/shibei-digest-YYYY-MM-DD-HHMMSS.html` 和对应 Markdown；重复运行即使发生在同一秒也会自动追加碰撞编号。`public/index.html` 会列出所有历史集合。`public/latest.html` 和 `public/latest.md` 仍会写入，但只作为旧链接兼容入口，不再作为推送里的主链接。去重和上次检查时间记录在 `state/seen_articles.json`。

推送保护：飞书消息使用紧凑 UTF-8 JSON，并在接近自定义机器人 20 KB 上限前拆分消息；每个拆分消息都保留文章原文链接。Bark 使用 Markdown 将每篇标题显示为可点击链接，同时保留整期归档入口。共享同一状态文件的进程会通过锁串行执行，避免重复启动时互相覆盖归档或重复推送。生产默认不限制文章数量；如需临时限制，可使用 `--limit N`，限制发生在过滤广告和去重之后。

## 推送配置

不要把 token、device key 或 webhook 写进代码或文档。

GitHub Actions 需要两个 repository secrets：

- `BARK_DEVICE_KEY`
- `FEISHU_WEBHOOK_URL`

本地运行可以用环境变量：

```bash
export BARK_DEVICE_KEY="你的 Bark device key"
export FEISHU_WEBHOOK_URL="你的飞书机器人 webhook"
export PUBLIC_BASE_URL="https://lxinxin-cloud.github.io/shibei-digest"
python3 scripts/shibei_digest.py --public-dir public
```

也可以写入 macOS Keychain：

```bash
chmod +x scripts/setup_secrets.sh
scripts/setup_secrets.sh
```

Bark 需要的是 Bark App 首页里推送 URL 的设备码，通常来自 `https://api.day.app/设备码/...`，不是 iOS 系统 device token。

## 抓取逻辑

入口是：

```text
https://www.bohaishibei.com/post/category/digest/
```

脚本会从第一页开始按页抓取，默认持续抓取到窗口覆盖完成（`--max-pages 0`）；每页解析文章标题、URL、发布日期和摘要，并按发布时间判断是否进入本次窗口。窗口起点取“最近 `--max-age-hours` 小时”和 `state/seen_articles.json` 中 `last_checked_at` 的更早值，这样如果某次 GitHub Actions 延迟或失败，下一次可以回补。运行 JSON 会同时报告 `fetched`、`in_window`、`excluded`、`already_seen`、`selected_before_limit`、`selected` 和 `truncated`，用于核对是否存在截断。

由于站点列表只有日期、没有精确时间，选择文章时按北京时间的日期比较。多页抓取会在整页文章日期都早于窗口起始日期时停止。

过滤规则在 `scripts/shibei_digest.py` 的 `EXCLUDE_KEYWORDS`，目前覆盖广告、优惠、推广、小说、连载、番外、章节等关键词。如果后续发现误收或误杀，优先改这里并用 dry run 验证。

## 验证

常用检查：

```bash
python3 -m compileall scripts
python3 scripts/shibei_digest.py --dry-run --include-seen
```

GitHub 侧需要确认：

- Actions 最近一次 `Shibei Digest` 运行成功。
- GitHub Pages Source 是 `GitHub Actions`。
- Secrets 中存在 `BARK_DEVICE_KEY` 和 `FEISHU_WEBHOOK_URL`。
- 手机可打开 `https://lxinxin-cloud.github.io/shibei-digest/` 并回看历史集合。

## 交接资料

接手开发前请先读：

- `AGENTS.md`：给后续 coding agent/维护者的项目规则。
- `PROJECT_MEMORY.md`：当前配置、线上状态、已知风险和下一步建议。
