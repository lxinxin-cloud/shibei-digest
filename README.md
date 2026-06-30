# 拾贝文章汇总

每 48 小时抓取博海拾贝“文摘”分类的新文章，过滤广告、优惠、推广、小说/连载类内容，生成手机友好的 HTML 和 Markdown 归档，并推送到 Bark 与飞书。

## 本地运行

```bash
python3 -m pip install -r requirements.txt
python3 scripts/shibei_digest.py --dry-run
```

输出文件会写到 `output/`，已推送文章记录在 `state/seen_articles.json`。

## 推送配置

不要把 token 或 webhook 写进代码。最简单的是运行前设置环境变量：

```bash
export BARK_DEVICE_KEY="你的 Bark device key"
export FEISHU_WEBHOOK_URL="你的飞书机器人 webhook"
python3 scripts/shibei_digest.py
```

更适合定时自动化的是存到 macOS Keychain。脚本会自动读取下面两个 service：

```bash
chmod +x scripts/setup_secrets.sh
scripts/setup_secrets.sh
```

也可以手动写入：

```bash
security add-generic-password -a "$USER" -s shibei_digest_BARK_DEVICE_KEY -w "你的 Bark device key" -U
security add-generic-password -a "$USER" -s shibei_digest_FEISHU_WEBHOOK_URL -w "你的飞书机器人 webhook" -U
```

可选配置：

```bash
export PUBLIC_BASE_URL="https://你的公开目录"
export BARK_SERVER="https://api.day.app"
```

Bark 需要的是 Bark App 首页里显示的推送链接设备码，通常来自类似 `https://api.day.app/设备码/标题/内容` 的链接；不要使用 iOS 系统的 device token。

如果设置了 `PUBLIC_BASE_URL`，Bark 通知会打开对应的 HTML 汇总链接；否则 Bark 只发送提醒和标题列表，完整摘要会发到飞书。

## 定时运行

Codex 自动化或系统计划任务每 48 小时运行：

```bash
cd "/Users/flxx/Desktop/XX Zone/8. My AI_Prod/WebNews"
python3 scripts/shibei_digest.py
```

第一次正式运行会推送最近 48 小时内符合条件的文章，之后通过 `state/seen_articles.json` 去重。

如果 Bark 和飞书都没有配置，脚本仍会生成 HTML/Markdown，但不会更新去重状态，避免自动化空跑后错过文章。

## GitHub Actions + Pages 公网运行

这个仓库已经包含 `.github/workflows/shibei.yml`，可在 GitHub 云端每两天自动运行并发布页面。

### 1. 配置仓库 Secrets

进入 GitHub 仓库：

`Settings -> Secrets and variables -> Actions -> New repository secret`

添加两个 secret：

- `BARK_DEVICE_KEY`
- `FEISHU_WEBHOOK_URL`

### 2. 开启 GitHub Pages

进入：

`Settings -> Pages`

把 `Build and deployment` 的 Source 设为 `GitHub Actions`。

### 3. 手动触发第一次运行

进入：

`Actions -> Shibei Digest -> Run workflow`

运行成功后，最新页面会发布到：

```text
https://lxinxin-cloud.github.io/shibei-digest/latest.html
```

之后 workflow 会在每天 UTC 00:00 检查一次，也就是北京时间早晨 8:00。脚本只有在距离上次完整检查足够久后才真正抓取和推送，所以实际节奏是每两天早晨 8:00 运行一次。抓取会按发布时间向后翻多页，直到越过上次成功检查/最近 48 小时的窗口；这样文章多于第一页时也不会漏。没有新文章时不会推送空通知；有新文章时会推送 Bark 和飞书。
