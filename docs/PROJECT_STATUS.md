# 项目状态总览

> **产品**：高管人事动态（https://cnceo.org）
> **最后更新**：2026-06-12

---

## 一、里程碑时间线

| 日期 | 里程碑 | 状态 |
|------|--------|------|
| 2026-04-18 | 项目启动，核心数据模型与公告抓取完成 | ✅ |
| 2026-04-25 | 审核台聚合修复 + AI 自动审核闭环 | ✅ |
| 2026-04-26 | 前端列表分页 + 人物信息优化 | ✅ |
| 2026-04-28 | R1-R5 数据增强全部完成（股东、股价、财报等） | ✅ |
| 2026-04-29 | 数据运维记录归档，基线数据就绪 | ✅ |
| 2026-05-03 | UI v2 重构上线，客户首页改版，品牌名统一 | ✅ |
| 2026-05-03 | PostgreSQL 兼容性修复（GROUP BY ORDER BY） | ✅ |
| 2026-05-03 | 运营导航条件渲染（仅登录后显示） | ✅ |
| 2026-05-07 | 品牌名从"高管异动雷达"改为"高管人事动态" | ✅ |
| 2026-05-07 | 域名接入 + HTTPS 配置（cnceo.org） | ✅ |
| 2026-05-07 | SEO 基础设施（robots.txt、sitemap.xml、OG 标签） | ✅ |
| 2026-05-07 | 推广计划制定 + 推广资产创建 | ✅ |
| 2026-05-07 | 访问统计系统（page_views + /stats 页面） | ✅ |
| 2026-05-07 | 关注列表匿名会话隔离（visitor_id cookie） | ✅ |
| 2026-05-10 | `/stats` 500 错误修复 + 统计导航链接 | ✅ |
| 2026-05-10 | 数据隔离漏洞修复（alert/watchlist 跨会话泄露） | ✅ |
| 2026-05-10 | favicon.ico 支持 + 模板声明 | ✅ |
| 2026-05-10 | 安全加固：恶意爬虫拦截 + CMS 扫描 404 | ✅ |
| 2026-05-10 | 安全加固：速率限制（429）+ 防 ticker 数据遍历 | ✅ |
| 2026-05-10 | 公开 CSV 导出放行，公开用户上限 2000 条，待审数据仅管理员可导出 | ✅ |
| 2026-05-10 | 修复 favicon.ico 缺失时的 404 边界处理 | ✅ |
| 2026-05-10 | 统一新的文档维护规则 | ✅ |
| 2026-05-10 | 推广自动化第一轮：官网 `/blog` 上线、3 篇 SEO 文章公开、sitemap 更新 | ✅ |
| 2026-06-09 | AI 抽取 token 优化：8 层降本（系统/用户拆分、prompt 压缩、prefilter、smart-skip、rule-only fast path、token 预算、缓存、输出上限） | ✅ |
| 2026-06-09 | `/token-monitor` 仪表盘：按小时趋势、预算状态、节省估算、成本预测 | ✅ |
| 2026-06-10 | `/stats` 重构：page_view_daily 预聚合（hourly + hour=-1 日级 rollup），读路径从 170s 降至亚秒 | ✅ |
| 2026-06-10 | 进程内缓存层 `services_base.cached_call`：6 个热读路径（overview / recent_companies / coverage / launch / churn / stats）加 TTL+version 失效 | ✅ |
| 2026-06-10 | 机器人检测重构：`page_views.is_bot` 列 + `is_bot_user_agent` 单一来源；bot 写入而非丢弃，统计走 `is_bot = FALSE` 部分索引 | ✅ |
| 2026-06-10 | `/review` 分页 + `/api/review/queue\|groups` 增 `offset` 查询参数 | ✅ |
| 2026-06-10 | 请求超时守护：30s `asyncio.wait_for` 包裹所有 handler，Cloudflare 524 之前先返 503 | ✅ |
| 2026-06-10 | 速率限制放宽（API 60/min、浏览 120/min、ticker 扫描 60/min）匹配合法客户端行为 | ✅ |
| 2026-06-10 | Schema 迁移重写：DDL 各自短事务 + PG `CREATE INDEX CONCURRENTLY`，不再与 sync-notices 死锁 | ✅ |
| 2026-06-10 | 回填脚本：`scripts/backfill_is_bot.py`（pre-deploy 行的 is_bot）+ `scripts/backfill_page_view_daily.py` | ✅ |
| 2026-06-10 | 重构模块单测：`tests/test_refactor_modules.py` 32 个 case（cache、aggregator、bot detection、API offset、bump-skip） | ✅ |
| 2026-06-11 | AI 提取器人名修复：议案标题句不再生成低信号 hint；AI 与规则路径共用同一套人名校验，杜绝"经公"类假人名。spec 见 `docs/superpowers/specs/2026-06-11-ai-extractor-person-name-fixes-design.md` | ✅ |
| 2026-06-12 | 访问统计 bot 过滤加固：`_BOT_SIGNATURES` 新增 15 个 AI 训练爬虫签名（含 ClaudeBot/PerplexityBot/Google-Extended），核心 SEO 爬虫保留放行；`scripts/reclassify_bot_signatures.py` 一键回填历史 `is_bot=FALSE` 误判行 + 触发 14 天 rollup 刷新 | ✅ |
| 2026-06-12 | `data/` 清理：删除 35+ untracked 一次性 debug 脚本，git rm 22 个 sqlite/log 文件（保留在磁盘），`.gitignore` 加固；**安全修复** `data/deployment_credentials.txt`（含服务器 SSH 密码 + admin 密码）从仓库移除（仍在 git 历史，密码需轮换）；线上已部署新代码并 reclassify 370,571 行 + 重算 14 天 rollup 131,589 行 | ✅ |

---

## 二、当前产品状态

### 2.1 已上线功能

**客户前台（公开访问）**：
- ✅ 概览首页：数据规模、最新变动、快速搜索、使用场景
- ✅ 人事动态流：按角色/事件类型/公司筛选，CSV 导出
- ✅ 公司库：公司检索、领导层快照、近期变动
- ✅ 人物库：人物检索、任职轨迹、履历摘要
- ✅ 关注列表：公司/人物/角色维度监控

**运营后台（管理员密码保护）**：
- ✅ 新增记录：每日已发布事件归档
- ✅ 审核台：按公告聚合的批量审核（HTML + API 双分页）
- ✅ 覆盖台账：数据质量与同步任务监控
- ✅ 访问统计仪表盘：从 `page_view_daily` 预聚合读，bot 走 `is_bot = FALSE` 部分索引
- ✅ Token 监控仪表盘：AI 抽取成本、按小时趋势、预算状态
- ✅ 项目记忆库：系统运行状态与项目定义

**基础设施**：
- ✅ HTTPS（Let's Encrypt）
- ✅ SEO（robots.txt、sitemap.xml、OG 标签）
- ✅ 访问统计（page_views 表 + `/stats` 仪表盘，bot 过滤）
- ✅ 进程内缓存（`services_base.cached_call`）：TTL+version 失效，6 个热读路径覆盖
- ✅ 预聚合层（`page_view_daily`）：hourly + day-rollup，sync 末尾自动 refresh
- ✅ 恶意爬虫拦截（14 种爬虫返回 403）
- ✅ CMS 漏洞扫描拦截（WordPress 等返回 404）
- ✅ 速率限制（单 IP API 60/浏览 120/分钟，超限 429）
- ✅ 防数据遍历（ticker 连续扫描 60+/分钟返回 429）
- ✅ 请求超时守护（30s 超时返 503，避免 Cloudflare 524）
- ✅ 公告同步定时任务（每 30 分钟）
- ✅ 数据库备份定时任务
- ✅ 零快照修复定时任务

### 2.2 已知限制

| 限制 | 说明 | 优先级 |
|------|------|--------|
| 零快照公司 317 家 | 部分公司暂无高管快照数据 | 中 |
| 已发布事件 133 条 | 历史事件底座偏薄，需持续运营 | 高 |
| 待审核 110 条 | 审核队列需持续消化 | 高 |
| 无 SMTP/ webhook | 站外提醒通道未配置 | 低 |
| 无 Google Analytics | 流量追踪未接入（已自研 /stats 替代） | 低 |

---

## 三、技术债务

| 债务 | 说明 | 影响 |
|------|------|------|
| ~~SQLite/PG 兼容~~ | ~~已修复 ORDER BY + GROUP BY 问题~~ | ✅ 已解决 |
| ~~数据隔离~~ | ~~alert/watchlist 跨会话泄露~~ | ✅ 已解决 |
| ~~无单元测试覆盖抽取逻辑~~ | 2026-06-10 起 `tests/test_refactor_modules.py` 32 个 case 覆盖缓存、聚合、bot、API offset | ✅ 部分解决（cninfo 抓取与人物去重仍待补） |
| 本地开发仍用 SQLite | 与生产环境不一致 | 低 |
| 部署脚本依赖 sudo | 文件权限管理不够精细 | 低 |
| `data/` 下临时 debug 脚本未清理 | 35+ 个一次性脚本、deploy zip、sqlite db 仍 untracked | 低（建议补 .gitignore 后清理） |

---

## 四、推广状态

### 4.1 已完成的推广资产

- 推广计划文档（PROMOTION_PLAN.md）
- 推广资源包（PROMOTION_KIT.md）
- 执行手册（PLAYBOOK.md）
- 3 篇 SEO 文章
- 官网公开指南页 `/blog`
- 3 篇 SEO 文章公开页面
- 朋友圈/LinkedIn/脉脉文案
- 冷邮件模板 3 封
- 产品截图说明

### 4.2 待执行的推广动作

- [ ] 朋友圈发布
- [ ] LinkedIn 发布
- [ ] 猎头群分享
- [ ] 冷邮件第一轮（20 封）
- [ ] 注册公众号并发文
- [ ] 搜索引擎注册（Google/Bing/百度）— 需账号验证

---

## 五、文档索引

| 文档 | 路径 | 维护频率 |
|------|------|----------|
| 项目入口 | `README.md` | 运行方式、线上环境、部署、安全或文档索引变化时更新 |
| 顶层设计 | `docs/PROJECT_MASTER_PLAN.md` | 产品定义、需求边界、系统架构、阶段路线变化时更新 |
| 当前状态 | `docs/PROJECT_STATUS.md` | 每周或重要发布后更新 |
| 推广计划 | `docs/promotion/PROMOTION_PLAN.md` | 推广策略变化时更新 |
| 推广资源包 | `docs/promotion/PROMOTION_KIT.md` | 对外文案、冷邮件、FAQ 变化时更新 |
| 推广手册 | `docs/promotion/PLAYBOOK.md` | 推广执行 SOP 变化时更新 |
| 数据运维记录 | `runner/OPERATIONS.md` | 数据抓取、补库、迁移、批处理发生时更新 |
| UI 设计记录 | `runner/UI_REDESIGN_V2.md` | 设计系统或大范围视觉重构时更新 |

### 5.1 文档维护规则

项目文档不再按“只维护两份主文档”执行，而是按职责分层维护：

- `README.md` 是入口文档，不承载长篇设计细节。
- `docs/PROJECT_MASTER_PLAN.md` 是唯一的产品与技术顶层设计文档。
- `docs/PROJECT_STATUS.md` 是当前上线状态和近期动作记录。
- `docs/promotion/` 只记录推广、获客、文案和内容营销。
- `runner/` 只记录数据运维、Kimi Code 数据作业、UI 重构交接等专题执行记录。
- 历史失效文档统一进入 `docs/archive/`，避免根目录和 docs 目录继续扩散零散文档。

---

## 六、下一步（建议）

### 本周（2026-05-10 ~ 05-17）

1. **推广启动**：朋友圈 + LinkedIn + 猎头群分享产品上线
2. **搜索引擎**：完成 Google/Bing/百度站长平台注册和验证
3. **冷邮件**：发送第一轮 20 封定向邮件
4. **数据运营**：消化待审核队列，目标从 110 条压到 80 条以下
5. **安全监控**：观察速率限制和防遍历的效果，调整阈值

### 本月（2026-05）

1. **内容营销**：注册公众号，发布第一篇 SEO 文章
2. **产品迭代**：根据种子用户反馈优化首页和人事动态流
3. **定价探索**：收集 10+ 位种子用户的付费意愿反馈

---

*维护人：创始人 + Kimi Code CLI Agent*
