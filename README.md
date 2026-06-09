# 高管人事动态

**官网**：https://cnceo.org

面向中国 A 股上市公司高管与董事变动追踪的情报工具，为猎头顾问、董事会搜寻顾问和高端人才咨询团队提供每日自动化的公告监控、结构化事件提取和候选名单管理。

## 核心能力

- **每日公告监控**：自动抓取巨潮资讯网，覆盖 A 股 6100 家上市公司
- **结构化变动情报**：董事长、总经理、CFO、董事、独立董事等核心角色的任职变动自动提取
- **人物轨迹查询**：聚合人物的历史任职、教育背景和履历线索
- **公司领导层快照**：实时查看任意上市公司的当前治理层全貌
- **关注与导出**：盯住重点公司和人物，一键导出 CSV 候选名单
- **人工审核队列**：高风险事件保留人工复核，保证情报质量

## 当前数据规模

| 维度 | 数量 |
|------|------|
| 上市公司 | 6,100 |
| 发行人视图（去重） | 5,841 |
| 人物库 | 60,178 |
| 领导层快照 | 54,439 |
| 已发布变动事件 | 133+ |
| 源公告文档 | 930+ |

## 主要页面

**客户前台**（公开访问）：
- `/` — 概览首页，数据规模 + 最新变动 + 快速入口
- `/feed` — 人事动态流，按角色/事件类型/公司筛选
- `/companies` — 公司库，检索与列表
- `/people` — 人物库，履历与任职轨迹
- `/watchlists` — 关注列表，持续监控

**运营后台**（管理员密码保护）：
- `/daily-events` — 每日新增已发布事件记录
- `/review` — 审核台，人工复核待审公告
- `/coverage` — 覆盖台账，数据质量监控
- `/stats` — 访问统计仪表盘（PV/UV/来源/设备）
- `/memory` — 项目记忆库

## 技术栈

- FastAPI + Jinja2 SSR + 自定义 CSS（无前端框架）
- PostgreSQL（生产）/ SQLite（开发）
- SQLAlchemy 2.0 + Alembic
- Caddy 反向代理 + HTTPS（Let's Encrypt）
- systemd 服务与定时任务

## 安全与防护

| 防护措施 | 说明 |
|---------|------|
| 恶意爬虫拦截 | GPTBot、MJ12bot 等 14 种爬虫直接返回 403 |
| CMS 扫描拦截 | WordPress、Joomla 等漏洞扫描路径返回 404，不暴露登录页 |
| 速率限制 | 单 IP 60 次/分钟（普通页面）、30 次/分钟（API），超限返回 429 |
| 防数据遍历 | `/feed?ticker=XXX` 连续扫描 30+ 不同 ticker/分钟返回 429 |
| Admin 密码保护 | 运营后台基于 cookie 鉴权，无密码则 303 重定向登录 |
| 匿名会话隔离 | 关注列表与提醒基于 `visitor_id` cookie，无需注册 |
| Bot 过滤统计 | `/stats` 仪表盘自动过滤爬虫流量，只统计真实用户 |

## 线上环境

- **域名**：https://cnceo.org
- **服务器**：Ubuntu 24.04 LTS，UCloud 香港
- **Web 服务**：`china-succession-web.service`（uvicorn @ 127.0.0.1:8000）
- **数据库**：本机 PostgreSQL
- **反向代理**：Caddy（自动 HTTPS）
- **运行目录**：`/opt/china-succession`

## 本地开发

```bash
# 安装依赖
.venv\Scripts\python.exe -m pip install -e .

# 启动开发服务器
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 运行测试
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 生产部署

1. Windows 本机打包：
```powershell
powershell -ExecutionPolicy Bypass -File deploy\scripts\package_for_server.ps1
```

2. 上传到服务器并执行安装脚本：
```bash
sudo bash deploy/scripts/install_ubuntu_single_node.sh
sudo bash deploy/scripts/init_local_postgres.sh
```

3. 配置环境变量：
```bash
sudo nano /etc/china-succession/china-succession.env
```

4. 配置 Caddy（自动 HTTPS）：
```bash
sudo tee /etc/caddy/Caddyfile <<'EOF'
cnceo.org {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy
```

完整部署步骤参见 `deploy/scripts/` 目录。

## 近期修复

- **2026-05-10** 公开 CSV 导出放行，公开用户最多导出 2000 条，待审数据仅管理员可导出
- **2026-05-10** 修复 favicon.ico 缺失时的边界处理
- **2026-05-10** 统一新的项目文档维护规则
- **2026-05-10** 推广自动化第一轮：上线 `/blog` 指南页、3 篇 SEO 文章公开页、首页内链和 sitemap 更新
- **2026-05-10** 安全加固：速率限制 + 防数据遍历 + CMS 扫描拦截
- **2026-05-10** `/stats` 页面 SQLAlchemy 布尔表达式 500 错误修复
- **2026-05-10** 关注列表与提醒数据隔离修复（防止跨会话泄露）
- **2026-05-10** favicon.ico 与 WordPress 扫描路径处理

## 项目文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目入口说明、运行方式、线上环境和文档索引 |
| `docs/PROJECT_MASTER_PLAN.md` | 项目总体规划与产品路线图 |
| `docs/PROJECT_STATUS.md` | 项目状态总览（每周更新） |
| `docs/promotion/PROMOTION_PLAN.md` | 推广计划 |
| `docs/promotion/PROMOTION_KIT.md` | 推广文案、冷邮件和 FAQ 资源包 |
| `docs/promotion/PLAYBOOK.md` | 推广执行手册 |
| `docs/promotion/AUTOMATED_PROMOTION_20260510.md` | 自动推广执行记录 |
| `runner/OPERATIONS.md` | 数据运维记录 |
| `runner/UI_REDESIGN_V2.md` | UI v2 设计记录 |

## 维护规则

项目文档从现在开始按“入口文档 + 主设计文档 + 状态文档 + 专题文档”维护：

- `README.md`：只放项目入口、核心能力、运行部署、线上环境和文档索引；每次影响用户入口、部署、安全或运行方式的改动必须更新。
- `docs/PROJECT_MASTER_PLAN.md`：唯一的产品与技术顶层设计文档；需求边界、系统架构、阶段路线、上线口径变化必须更新到这里。
- `docs/PROJECT_STATUS.md`：当前上线状态、近期发布、已知限制、技术债务和下一步动作；每周或重要发布后更新。
- `docs/promotion/`：推广计划、推广文案、SEO 内容和执行 SOP；只有营销与获客内容变化时更新。
- `runner/OPERATIONS.md`：数据抓取、补库、迁移、批处理和 Kimi Code 数据作业记录；数据运维动作发生时更新。
- `runner/UI_REDESIGN_V2.md`：UI v2 设计记录；仅在设计系统或大范围视觉重构时更新。

历史文档统一归档在 `docs/archive/`。

## 许可

仅供内部种子运营使用。公开运营前需完成定价模式验证和用户协议。
