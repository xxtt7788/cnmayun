# 访问统计 ClaudeBot 过滤 — 设计文档

- **日期**: 2026-06-12
- **作者**: Claude (brainstorming skill)
- **状态**: 已批准，待实施

## 背景与目标

`/stats` 仪表盘的"访客明细（最近 50 条，已过滤爬虫）"近期出现大量 `ClaudeBot/1.0` 访问 `/feed` 的记录，本质是 Anthropic 的 AI 训练爬虫把页面当训练语料抓取，不应被当作真实访客计入。

**根因**：`app/normalization.py` 的 `_BOT_SIGNATURES` 元组（`is_bot_user_agent` 的单一来源）当前只包含 14 个签名，**没有** `claudebot` 或任何其他主流 AI 训练爬虫。后果链路：

1. `app/main.py:371` 中间件用 `is_bot_user_agent(ua)` 判断 → False → 不 403 拦截
2. `_record_pv_background`（`app/main.py:196`）写入 `page_views`，`is_bot=False`
3. `get_stats` 读路径（`app/services.py:1383`）用 `is_bot IS NOT TRUE` 过滤 → 该行被算成真实访客
4. 浏览器桶 `_browser_bucket`（`app/stats_aggregator.py:41`）不认识 ClaudeBot 的 UA pattern → 落到 "Other"
5. `/feed` 速率限制只针对 ticker 扫描（`app/main.py:386`），不限 `?ticker=...` 缺省的批量抓取

**本设计目标**：

- 把所有主流 AI 训练 / AI 助手爬虫纳入 `_BOT_SIGNATURES` 单一来源
- 显式保留核心 SEO 爬虫（Googlebot、Bingbot、Baiduspider、Sogou）放行，保留 SEO 价值
- 历史脏数据（`is_bot=FALSE` 但 UA 应判为 bot 的行）通过一次性回填脚本重新分类
- 触发 `recompute_page_view_daily` 刷新聚合表，让 `/stats` 仪表盘立即反映修正

## 设计

### 改动 1：扩展 `_BOT_SIGNATURES` 单一来源

**文件**：`app/normalization.py`
**位置**：约 614–629 行

替换为按子类型分组的签名清单（注释明确"只放行核心 SEO"，避免日后误删）：

```python
# --- Bot detection (shared between middleware write-path and stats read-path) ---
# Substring match (lowercased). We follow a "block by default" stance for
# non-SEO crawlers:
#   - AI training / assistant crawlers: no SEO value, train on user content
#   - SEO link-scrapers: no traffic value
# Core search engine crawlers (Googlebot, Bingbot, Baiduspider, Sogou) are
# intentionally NOT listed to preserve SEO.
_BOT_SIGNATURES: tuple[str, ...] = (
    # AI training / assistant crawlers (low/no SEO value)
    "claudebot",              # Anthropic ClaudeBot
    "anthropic-ai",           # Anthropic assistant fetcher
    "perplexitybot",          # Perplexity AI indexer
    "perplexity-user",        # Perplexity user-triggered fetch
    "chatgpt-user",           # OpenAI ChatGPT user-triggered fetch
    "oai-searchbot",          # OpenAI SearchGPT
    "gptbot",                 # OpenAI GPT training crawler
    "google-extended",        # Google Gemini training (NOT a search crawler)
    "applebot-extended",      # Apple Intelligence training
    "amazonbot",              # Amazon AI / Q
    "meta-externalagent",     # Meta AI training
    "ccbot",                  # Common Crawl (feeds many LLM training pipelines)
    "bytespider",             # ByteDance (TikTok) AI training
    "duckassistbot",          # DuckDuckGo AI assist
    "turnitinbot",            # Turnitin (AI-detection crawler)

    # SEO / link-scraping / monitoring bots (no traffic value)
    "mj12bot",                # Majestic SEO link index scraper
    "googleother",            # Google non-search crawler
    "tlm-audit-scanner",      # Unknown scanner
    "ahrefsbot",              # Ahrefs SEO tool
    "semrushbot",             # SEMrush SEO tool
    "dotbot",                 # Moz SEO tool
    "yandexbot",              # Yandex (low traffic value for China B2B)
    "exabot",                 # Exalead (defunct search engine)
    "facebot",                # Facebook scraper
    "ia_archiver",            # Internet Archive
    "datadog",                # Datadog monitoring crawler
    "uptimerobot",            # Uptime monitoring
    "screaming frog",         # SEO audit tool
)
```

`is_bot_user_agent()` 函数体不变（保持 substring 匹配 + 唯一签名源的不变量）。

**为什么是单一来源**：避免 write path（中间件）和 read path（`get_stats`）两份签名表漂移 — `app/normalization.py:632-642` 现有 docstring 已经把这点写死。

### 改动 2：新增 `reclassify_bot_signatures.py` 回填脚本

**新文件**：`scripts/reclassify_bot_signatures.py`

现有 `scripts/backfill_is_bot.py`（2026-06-10 落地）**只**处理 `is_bot IS NULL` 的行 — 这次 ClaudeBot 留下的脏数据是 `is_bot=FALSE`，原脚本抓不到。需要一个明确"重新评估所有已分类行"的新脚本。

**核心逻辑**：

```python
# 单次 SQL 跑完（避免逐行 round-trip）。pg 用 LOWER + OR-of-LIKE；SQLite 同语法。
signatures = [...]   # 从 app.normalization._BOT_SIGNATURES 导入，单一来源
conditions = " OR ".join([f"LOWER(COALESCE(user_agent, '')) LIKE :p{i}" for i in range(len(signatures))])
params = {f"p{i}": f"%{sig}%" for i, sig in enumerate(signatures)}
sql = f"""
    UPDATE page_views
    SET is_bot = TRUE
    WHERE is_bot = FALSE
      AND ({conditions})
"""
result = db.execute(text(sql), params)
db.commit()
log.info("re-tagged %d rows as bot (FALSE -> TRUE)", result.rowcount)
```

**关键性质**：

- **Idempotent**：只动 `is_bot=FALSE → TRUE`，不碰 `is_bot=NULL`（NULL 由原 `backfill_is_bot.py` 单独处理），不删行
- **批处理不需要**：单条 UPDATE，由 `is_bot` 上的部分索引定位，秒级完成
- **末尾触发 `recompute_page_view_daily(days=14)`**：覆盖 `daily_trend` 面板窗口（`app/templates/stats.html:192`），聚合表立刻反映新分类

**与现有脚本的边界**：

| 脚本 | 处理对象 | 用途 |
|------|---------|------|
| `backfill_is_bot.py` | `is_bot IS NULL` | 部署后首跑，把 schema 迁移前的历史行分类 |
| `reclassify_bot_signatures.py` (新) | `is_bot=FALSE` 且 UA 匹配新签名 | 修"签名不全导致漏判"的脏数据 |

**执行环境**（沿用项目惯例，`app/OPERATIONS.md` 一致）：

```bash
cd /opt/china-succession
source /etc/china-succession/china-succession.env   # 加载 DATABASE_URL
/opt/china-succession/.venv/bin/python -m scripts.reclassify_bot_signatures
```

### 改动 3：单元测试

**文件**：`tests/test_refactor_modules.py`
**类**：`IsBotUserAgentTests`
**位置**：约 186–212 行

新增 4 个 case：

```python
def test_claudebot(self) -> None:
    self.assertTrue(is_bot_user_agent(
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; "
        "compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
    ))

def test_perplexitybot(self) -> None:
    self.assertTrue(is_bot_user_agent("Mozilla/5.0 (compatible; PerplexityBot/1.0)"))

def test_google_extended_is_blocked(self) -> None:
    # google-extended 是 Gemini 训练爬虫（与 Googlebot 搜索爬虫不同），必须判 bot
    self.assertTrue(is_bot_user_agent("Mozilla/5.0 (compatible; Google-Extended/1.0)"))

def test_googlebot_still_allowed(self) -> None:
    # Googlebot 搜索爬虫保留 SEO 价值，签名单不含 "googlebot"
    self.assertFalse(is_bot_user_agent("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"))
```

最后一个 case 替换现有 `test_googlebot_is_not_blocked`（语义不变，强化签名） — 通过 `replace_all=False` 单独处理。

## 显式不做

- **不动 `app/main.py:371` 的 403 拦截**：保持"入库 + is_bot 标记"模型，UA 字符串留作事后模式分析。403 拦截只针对拒绝服务的恶意爬虫，AI 训练爬虫不耗资源到拒绝服务的程度。
- **不动 `/stats` UI**：现有 `is_bot=FALSE` 过滤逻辑（`app/services.py:1383`）已经对，签名扩展后自动正确。
- **不接 `robots.txt` 拦截**：`robots.txt` 协议对 Googlebot/Bingbot 有效，对 ClaudeBot/GPTBot 协议外 AI 爬虫无强制力；接了反而会污染现有 SEO 友好的 robots.txt（`app/static/robots.txt`）。
- **不动 `/feed` 速率限制**：现有 ticker 扫描检测（`app/main.py:386`）针对无 ticker 缺省的爬虫无效，但本设计的目标是"统计干净"，限流是另一回事（且扩到所有 AI 爬虫签名会让放行的 SEO 爬虫被误伤）。

## 部署 & 风险

**部署步骤**（线上 PG，`/opt/china-succession`）：

1. `git pull` 拉代码（新签名 + 新脚本 + 测试）
2. 跑测试：`/opt/china-succession/.venv/bin/python -m pytest tests/test_refactor_modules.py::IsBotUserAgentTests -v`
3. 重启服务（让新签名生效到生产进程）
4. 跑回填：`/opt/china-succession/.venv/bin/python -m scripts.reclassify_bot_signatures`
5. 验证：浏览器打开 `https://cnceo.org/stats`，"访客明细"应不再有 `ClaudeBot/1.0`，"浏览器分布" 的 "Other" 桶应显著下降

**风险**：

- **回滚简单**：新脚本只动 `is_bot` 字段、不删行；签名加回去即恢复
- **30 分钟窗口**：回填后到下一次 `sync-notices` 触发的 `recompute_page_view_daily` 之间，聚合表可能短暂陈旧 — 新脚本末尾主动跑一次 `recompute_page_view_daily(days=14)` 消除这个窗口
- **签名误伤风险**：substring 匹配是"包含"语义，新增签名如果意外匹配真实浏览器 UA（如 `oai-searchbot` 子串可能撞名）会误判。**减风险**：所有新增签名都是公认的、独特的爬虫标识符（来源：`https://darkvisitors.com/` 公开 crawlers 数据库），`tests/test_refactor_modules.py` 的现有 `test_chrome_human` 也会被新签名再次验证

**对其他功能的副作用**：

- `get_token_monitor_stats`（`app/services.py:1594`）不读 `page_views`，无影响
- 缓存：`bump_version("stats")` 由 `_record_pv_background` 在新写入时自动触发（`app/main.py:227`），无需手动 invalidate
- `/api/*` 不读 stats，无影响

## 验收标准

- [ ] 单元测试 `tests/test_refactor_modules.py::IsBotUserAgentTests` 4 个新 case 全过
- [ ] 现有 `test_googlebot_is_not_blocked` 仍过（确认 SEO 爬虫未误伤）
- [ ] `scripts.reclassify_bot_signatures` 在生产 PG 上跑完，输出 `re-tagged N rows`（N > 0 应有大量 ClaudeBot 历史行）
- [ ] `daily_trend` 面板 14 天内数据与回填前相比，bot 桶下降、`Other` 浏览器桶下降
- [ ] `/stats` "访客明细" 手动刷新一次后（绕过 60s TTL 缓存），不再出现 `ClaudeBot/1.0` 字样
- [ ] 新 visit 立即干净（`UA: ... ClaudeBot/1.0 ...` 写入后 5 秒内 `/stats` 不可见）
