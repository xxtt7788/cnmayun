# 自动推广执行记录

> 日期：2026-05-10
> 目标：把已有推广资产从“文档”推进成“可被搜索、可被分享、可被投放”的公开入口。

---

## 一、已自动完成

### 1. 官网公开内容页

已把 `docs/promotion/content/` 下的 3 篇 SEO 文章接入官网：

- https://cnceo.org/blog
- https://cnceo.org/blog/article-01-track-cfo-chairperson
- https://cnceo.org/blog/article-02-search-window
- https://cnceo.org/blog/article-03-guide

这些页面用于承接：

- 搜索引擎长尾关键词
- 朋友圈、脉脉、LinkedIn 分享
- 冷邮件中的“非硬广”内容入口
- 后续公众号/知乎文章的官网原文链接

### 2. 首页内链

首页新增“高管搜寻指南”模块，直接链接 3 篇文章。

作用：

- 提升搜索引擎发现文章的概率。
- 让首次访问用户不只看到工具，也看到方法论。
- 让产品从“数据工具”更像“懂高管搜寻场景的专业产品”。

### 3. sitemap 更新

`app/static/sitemap.xml` 已加入：

- `/blog`
- `/blog/article-01-track-cfo-chairperson`
- `/blog/article-02-search-window`
- `/blog/article-03-guide`

当前 sitemap 地址：

- https://cnceo.org/sitemap.xml

### 4. 导航入口

顶部公开导航已新增“指南”，方便用户和搜索引擎从全站入口进入内容页。

---

## 二、当前可直接投放的链接

### 痛点型分享

链接：

- https://cnceo.org/blog/article-01-track-cfo-chairperson

适合场景：

- 朋友圈
- 猎头群
- 脉脉
- 冷邮件首封

推荐标题：

> 猎头如何高效追踪上市公司 CFO 和董事长变动

### 机会窗口型分享

链接：

- https://cnceo.org/blog/article-02-search-window

适合场景：

- 猎头合伙人私聊
- 董事会搜寻顾问
- LinkedIn 长文引用

推荐标题：

> 董事长离任后，搜寻窗口期有多长？

### 使用指南型分享

链接：

- https://cnceo.org/blog/article-03-guide

适合场景：

- 新用户 onboarding
- 试用邀请
- 冷邮件跟进

推荐标题：

> 从公告到候选名单：高管搜寻顾问的完整工作流

---

## 三、搜索收录动作

已完成：

- 官网 sitemap 已包含新文章。
- `robots.txt` 已声明 sitemap 地址。
- 官网首页已加入文章内链。

需要账号执行：

- Google Search Console：提交 `https://cnceo.org/sitemap.xml`。
- Bing Webmaster Tools：提交 `https://cnceo.org/sitemap.xml`。
- 百度搜索资源平台：提交 `https://cnceo.org/sitemap.xml`，并把 3 篇文章 URL 加入链接提交。

说明：

这些动作需要站点所有权验证或平台账号，AI 不能替你伪造账号登录状态。当前已经把可提交的技术入口准备好。

---

## 四、下一轮可自动化动作

下一轮不应该再写泛泛的推广计划，而应该继续产出可上线资产：

1. 每周生成一篇“本周 A 股高管人事动态观察”官网文章。
2. 从 `/feed` 中选 5 条高价值事件，生成周报草稿。
3. 为每篇文章生成朋友圈、脉脉、LinkedIn、冷邮件 4 种分发文案。
4. 每周更新 sitemap。
5. 每周查看 `/stats`，记录来源、热门页面、跳出率和导出次数。

---

## 五、边界

AI 已完成可自动完成的官网承接层。

仍然必须由你或你授权的账号执行：

- 微信朋友圈发布。
- 微信群分享。
- 脉脉、LinkedIn、知乎、小红书发布。
- 搜索资源平台账号验证。
- 冷邮件真实发送。

这些动作涉及账号身份、社交关系、平台风控和合规，不能在没有账号授权的情况下假装完成。
