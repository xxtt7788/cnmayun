# 自动推广执行记录

> 日期：2026-05-18
> 目标：基于项目内现有文档、公开页面配置和本地统计数据，生成本周可直接使用但未对外发布的推广素材包。

---

## 一、本周核对范围

已核对的真实来源：

- 项目入口与状态文档：`README.md`、`docs/PROJECT_STATUS.md`
- 推广文档：`docs/promotion/PROMOTION_KIT.md`、`docs/promotion/PROMOTION_PLAN.md`
- 官网公开入口定义：`app/static/sitemap.xml`
- 官网公开页面模板：首页、`/blog`、`/stats`
- 本地 SQLite 数据：`data/china_succession.db`

本次未执行的动作：

- 未向微信、脉脉、LinkedIn、邮件系统或任何外部平台发布
- 未伪造搜索引擎收录、社媒互动或邮件发送结果

本次环境限制：

- 当前工作环境内 `cnceo.org` DNS 解析正常，但直接 HTTP/HTTPS 请求失败，无法在本机完成稳定的线上页面可达性核验
- 因此本周链接清单基于仓库内 sitemap、模板和历史记录整理，不把“已在线访问成功”写成结论

---

## 二、本周可分享的官网链接清单

优先分发链接：

1. 首页：
   `https://cnceo.org/`
   用途：第一次介绍产品、冷启动分享、让对方快速理解覆盖范围与核心能力

2. 人事动态流：
   `https://cnceo.org/feed`
   用途：强调“可直接看近期高管/董事变动”

3. 指南列表页：
   `https://cnceo.org/blog`
   用途：非硬广分发、朋友圈/脉脉/LinkedIn 承接页

4. 文章 1：
   `https://cnceo.org/blog/article-01-track-cfo-chairperson`
   主题：如何高效跟踪 CFO 和董事长变动

5. 文章 2：
   `https://cnceo.org/blog/article-02-search-window`
   主题：董事长离任后的 search window

6. 文章 3：
   `https://cnceo.org/blog/article-03-guide`
   主题：从公告到候选名单的完整工作流

可备选链接：

- 公司库：`https://cnceo.org/companies`
- 人物库：`https://cnceo.org/people`
- sitemap：`https://cnceo.org/sitemap.xml`

链接优先级依据：

- `app/static/sitemap.xml` 已包含以上公开入口
- 本地 `page_views` 数据中，2026-05-10 记录到的热门页面是 `/blog` 和 3 篇文章页，各 2 PV；首页 1 PV；来源全部为 direct

---

## 三、本周分发文案

### 1. 朋友圈版

这两周把 `cnceo.org` 的公开承接页补齐了。

现在不是单纯“抓公告”，而是把 A 股上市公司董事长、总经理、CFO、董事等人事变动整理成可筛选、可追踪、可导出的结构化情报。

如果你做高管搜寻、董事会搜寻，比较麻烦的一步往往不是找人，而是太晚知道谁刚刚变动。这个工具的价值就是把“翻公告”压缩成几分钟。

可先看这几个入口：
官网：`https://cnceo.org/`
动态流：`https://cnceo.org/feed`
指南页：`https://cnceo.org/blog`

### 2. 脉脉版

做 A 股高管搜寻时，很多人真正浪费时间的环节不是沟通客户，而是每天手工翻公告、判断哪些是有效人事信号。

我们把这件事做成了一个窄而深的工具：`cnceo.org`

它现在能做的事情比较直接：
- 追踪 A 股上市公司核心高管和董事变动
- 把公告里的变动事件结构化
- 支持按角色、事件类型、公司筛选
- 可以顺着人物和公司继续做候选名单整理

这周如果你只想看一篇说明，建议先看：
`https://cnceo.org/blog/article-03-guide`

如果你更关心 search window，直接看：
`https://cnceo.org/blog/article-02-search-window`

### 3. LinkedIn 版

We are building `cnceo.org`, a focused intelligence product for tracking leadership and board changes across China A-share listed companies.

Instead of manually scanning hundreds of announcements, the product turns public disclosure into structured, filterable signals for chairperson, CEO-equivalent, CFO-equivalent, director, and independent director changes.

Useful entry points:
- Home: `https://cnceo.org/`
- Event feed: `https://cnceo.org/feed`
- Guide hub: `https://cnceo.org/blog`

Three public articles are already prepared for sharing:
- CFO / Chairperson tracking
- Search window after chairperson departure
- Workflow from announcement to candidate list

### 4. 冷邮件版

主题：把 A 股高管变动从“翻公告”变成可跟进名单

[姓名] 您好，

我们最近把一个面向高管搜寻场景的小工具整理成了公开可查看的承接页：`cnceo.org`

它的目标很简单：把 A 股上市公司公告里的董事长、总经理、CFO、董事等人事变动，变成可筛选、可追踪、可导出的结构化信息，减少手工翻公告的时间。

如果您想先快速了解，建议从这几个入口看起：

- 产品首页：`https://cnceo.org/`
- 人事动态流：`https://cnceo.org/feed`
- 使用指南：`https://cnceo.org/blog/article-03-guide`

如果您更关心机会窗口判断，也可以直接看这篇：
`https://cnceo.org/blog/article-02-search-window`

这封邮件只是发送一份可评估的公开入口，不涉及任何账号开通或强推销。若您愿意，我可以继续按角色或行业整理更贴近 search 场景的观察素材。

---

## 四、本周可用于周报的高管人事动态素材

说明：

- 以 `data/china_succession.db` 内已发布事件为准
- 当前库内没有 2026-05-12 至 2026-05-18 的新增已发布事件
- 因此以下列出的是库内最近可确认的 5 条公开事件，日期集中在 2026-04-18 与 2026-04-10

1. 2026-04-18，四川路桥建设集团股份有限公司（600039）
   孙立成被选举为董事长。
   公告链接：`https://static.cninfo.com.cn/finalpage/2026-04-18/1225118542.PDF`

2. 2026-04-18，四川路桥建设集团股份有限公司（600039）
   羊勇被聘任为总经理。
   公告链接：`https://static.cninfo.com.cn/finalpage/2026-04-18/1225118542.PDF`

3. 2026-04-18，四川路桥建设集团股份有限公司（600039）
   郭人荣被聘任为财务总监，并兼任总法律顾问、首席合规官等职责。
   公告链接：`https://static.cninfo.com.cn/finalpage/2026-04-18/1225118542.PDF`

4. 2026-04-10，创业慧康科技股份有限公司（300451）
   张吕峥被选举为董事长。
   公告链接：`https://static.cninfo.com.cn/finalpage/2026-04-10/1225094714.PDF`

5. 2026-04-10，创业慧康科技股份有限公司（300451）
   马文浩被聘任为财务总监。
   公告链接：`https://static.cninfo.com.cn/finalpage/2026-04-10/1225094714.PDF`

可直接改写为周报口径：

- 近期可确认的人事变动仍以董事长、总经理、财务负责人任命类事件为主
- 单家公司多岗位同步调整，仍然是值得优先关注的高价值线索
- 四川路桥在 2026-04-18 同一批公告内出现董事长、总经理、财务负责人三项关键岗位变动，适合做“单家公司集中调整”案例
- 创业慧康在 2026-04-10 同时出现董事长与财务负责人任命，适合做“治理层与财务层同步变更”案例

---

## 五、本周数据备注

本地统计快照：

- `companies`: 6100
- `persons`: 60181
- `executive_snapshots`: 54508
- `events`: 133
- `page_views`: 11

近 14 天内本地可见访问记录：

- 只有 2026-05-10 有访问记录，PV 11，UV 11
- 来源全部为 direct
- 热门路径为 `/blog` 与 3 篇文章页，各 2 PV

解释口径：

- 样本非常小，只能证明“公开文章页已经进入真实访问记录”
- 目前不适合把这些数字包装成增长结论，更适合作为“优先继续分发 blog 入口”的依据

---

## 六、下周建议动作

1. 继续优先分发 `https://cnceo.org/blog` 和 3 篇文章，而不是只发首页
2. 如果下周事件库仍无 7 日内新发布事件，周报应明确标注“本周无新增已发布案例”，不要硬凑时效
3. 下次自动化应优先补一篇新的“周观察”公开文章，再同步更新 sitemap
4. 如果能恢复线上可达性核验，补一次首页、`/feed`、`/blog` 的真实 200/标题/截图记录
