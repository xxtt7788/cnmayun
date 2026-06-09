# 运行手册与当前状态

## 1. 这份文档回答什么问题

这份文档专门回答 3 类问题：

- 系统怎么启动
- 数据怎么初始化和同步
- 当前本地这份工程到底处于什么状态

## 2. 当前运行环境

当前项目运行环境：

- 操作系统：Windows
- Python：3.11+
- Web 框架：FastAPI
- ORM：SQLAlchemy
- 模板：Jinja2
- 数据库：SQLite
- 外部主数据源：巨潮官方公开接口

## 3. 启动方式

安装依赖：

```powershell
.venv\Scripts\python -m pip install -e .
```

启动服务：

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问地址：

```text
http://127.0.0.1:8000/
```

如需调整巨潮请求容错参数，可使用这些环境变量：

```text
CNINFO_REQUEST_TIMEOUT
CNINFO_REQUEST_RETRIES
CNINFO_RETRY_BACKOFF_SECONDS
```

## 4. 当前主要页面

当前可以直接访问的页面：

- `/`：概览页
- `/coverage`：覆盖台账
- `/companies`：公司库
- `/people`：人物库
- `/companies/{ticker}`：公司详情页
- `/people/{person_id}`：人物详情页

## 5. 当前主要 API

当前对外可用的 API：

- `/api/overview`
- `/api/baseline/summary`
- `/api/coverage`
- `/api/companies`
- `/api/companies/{ticker}`
- `/api/people`
- `/api/people/{person_id}`
- `/api/events`
- `/api/rankings/churn`

其中最适合快速看系统状态的是：

- `/api/baseline/summary`
- `/api/coverage`
- `/api/companies?limit=5`
- `/api/people?limit=5`

## 6. 数据文件与目录

### 数据库文件

默认数据库文件：

```text
data/china_succession.db
```

### 日志文件

当前本地服务日志位置：

```text
data/server.out.log
data/server.err.log
```

如果继续跑长时间同步任务，建议额外查看：

```text
data/sync_remaining.out.log
data/sync_remaining.err.log
```

### 研究与抓取样本

`data/` 目录里还保留了一些开发期抓下来的页面、脚本和接口样本。  
这些不是运行必需，但对理解巨潮接口和排查问题有帮助。

## 7. 命令行任务

### 7.1 初始化公司全集

```powershell
.venv\Scripts\python -m app.tasks init-universe
```

用途：

- 从巨潮证券清单初始化 `companies`

适用场景：

- 第一次建库
- 重建数据库后重新初始化

### 7.2 同步当前高管基线

```powershell
.venv\Scripts\python -m app.tasks sync-baseline --limit 200 --workers 6
```

用途：

- 批量同步公司简介和当前高管快照
- 落库人物、快照、任职区间、同步记录

参数说明：

- `--limit`：本次最多同步多少家公司
- `--workers`：并发抓取线程数

### 7.3 重建数据库并重新同步

```powershell
.venv\Scripts\python -m app.tasks sync-baseline --reset-db --limit 200
```

用途：

- 删除 SQLite 数据库文件
- 重新建表
- 重新初始化公司全集
- 重新跑基线同步

注意：

- 这是重建型操作
- 会清空当前本地数据库内容

## 8. 当前本地系统状态

当前这份工作区已经验证到的本地状态如下：

- 公司总数：6099
- 活跃公司：5952
- 已同步公司：5031
- 未同步公司：921
- 当前快照条数：50105
- 核心角色快照条数：50105
- 人物总数：54512
- 累计同步任务记录数：52
- 当前服务地址：`http://127.0.0.1:8000/`

这意味着：

- 系统已经可运行
- 数据不是空壳
- 但当前仍然只是部分覆盖，不是全量生产级

## 9. 当前已经验收通过的页面和接口

我已经实际验证通过的路径包括：

- `/`
- `/coverage`
- `/companies?q=茅台`
- `/people?limit=5`
- `/api/coverage`
- `/api/companies?limit=3`
- `/api/people?limit=3`

说明：

- 页面可以正常打开
- 覆盖台账和检索接口已经接入真实数据
- 公司库和人物库不再是占位页

## 10. 推荐的人工核验对象

如果你要自己手动验证系统，优先看下面这些对象。

### 公司：`600519`

原因：

- 页面最完整
- 高管结构清晰
- 适合检查董事长、总经理、财务负责人、董事、独立董事是否归一正确

### 公司：`300750`

原因：

- 创业板样本
- 适合核验非主板映射

### 公司：`688981`

原因：

- 科创板样本
- 适合检查板块识别是否正常

## 11. 已知限制

### 11.1 覆盖率还不够高

当前只同步了 5031 家公司。  
这不是功能失效，而是当前还没有把全量基线跑完。

### 11.2 失败公司仍然存在

当前已经有一部分公司状态为 `failed`。  
目前系统的处理方式是：

- 将公司标记为 `failed`
- 将失败信息写进 `baseline_runs.notes`
- 网络类失败会先经过请求重试与退避，再最终落成失败

还没有做：

- 失败原因分类
- 死信队列
- 专门的失败审核台

### 11.3 指标层仍基本为空

虽然已经有：

- `company_metrics_daily`
- `/api/rankings/churn`

但这层还没有正式回填逻辑。  
所以当前排行榜和稳定度信息不应视为产品真值。

### 11.4 事件层还没有进入生产状态

虽然：

- ORM 里已经有 `events`
- 页面和 API 也有承载位置

但真正的公告抓取、分类、抽取、去重还没接进来。  
当前系统重点仍然是“当前快照”，不是“历史事件流”。

### 11.5 PowerShell 里可能看到中文乱码

浏览器页面和接口响应本身是 UTF-8 正常中文。  
如果 PowerShell 里显示乱码，通常是控制台编码问题，不代表文件损坏。

## 12. 维护顺序建议

后续维护时，推荐顺序如下：

1. 先维持当前基线同步能力稳定
2. 扩大基线覆盖率
3. 增加失败分类和专项重试
4. 再接公告抓取和事件分类
5. 再做任职区间闭合
6. 最后做指标和图谱

不要反过来做。  
如果在覆盖率和数据质量还不稳的时候就去做图谱和复杂分析，最后只会把脏数据放大。

## 13. 排错建议

如果页面打不开，优先排：

- 服务是否启动
- 端口是否被占用
- `data/server.err.log` 是否有异常

如果覆盖台账不对，优先排：

- `baseline_runs` 是否有最近记录
- `executive_snapshots` 是否有数据
- `companies.baseline_status` 是否正常

如果公司页为空，优先排：

- 公司是否已标记为 `synced`
- 是否存在对应 `executive_snapshots`

如果人物库结果太少，优先排：

- 是否只筛选了当前活跃任职
- 角色筛选是否过窄

如果同步效果异常，优先排：

- `normalization.extract_canonical_roles`
- 巨潮接口响应是否变更
- `baseline_runs.notes`

## 14. 一句话总结

当前系统已经具备：

- 可启动
- 可建库
- 可同步
- 可检索
- 可展示

但它当前的重点仍然是：

**把“当前高管基线层”做稳、做清楚、做可管理。**
