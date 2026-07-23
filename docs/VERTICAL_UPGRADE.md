# 项目纵向深化说明

## 1. AI 调用链路

非流式接口和 RAG 均改用共享 `httpx.AsyncClient`。连接、读取、写入、连接池分别设置超时；供应商 429、408、425、5xx、连接失败和读取超时才会重试，最多 2 次并加入指数退避与抖动。API Key 无效、响应格式错误等不可恢复错误不会盲目重试。

`POST /api/consult/chat/stream` 使用 SSE 输出：

```text
meta -> token... -> done
```

请求断开时取消上游流；完整回复结束后再异步持久化消息、摘要和画像。该路径使用 `AsyncSession + asyncpg/aiosqlite`，模型等待期间事件循环可以处理其他请求。

## 2. Redis 缓存策略

| Key | 数据 | 基础 TTL | 失效方式 |
| --- | --- | ---: | --- |
| `articles:detail:{id}` | 已发布文章详情或空值标记 | 180s / 空值 20s | 文章写操作删除 `articles:*` |
| `articles:list:{query}:{category}:{date}` | 文章列表 | 120s | 文章写操作删除前缀 |
| `analytics:overview:user:{id}` | 用户概览 | 按业务设置 | 情绪/会话写入后删除 |
| `rate_limit:ai:{id}` | AI 分钟窗口计数 | 60s | 自动过期 |
| `verification:sms:{phone}` | 注册验证码 | 300s | 使用后删除 |

文章详情使用 Cache Aside。不存在 ID 会写入短期空值，阻断穿透；TTL 加随机值避免雪崩；进程锁和 Redis 短锁只允许一个请求回源。Redis 失败后开启 5 秒熔断窗口，期间直接走内存/数据库，避免每个请求反复等待 socket 超时。

## 3. 风险案例状态机

新状态主线：

```text
pending -> claimed -> processing -> waiting -> processing
                          |-> transferred -> claimed
                          |-> resolved -> closed
```

旧版 `assigned/contacted/follow_up/false_positive` 暂时保留兼容，但同样经过服务端状态校验。`POST /api/admin/risk-events/{id}/claim?expected_version=N` 使用单条条件 UPDATE；20 个并发领取者只有一个能更新版本并成功。

同一用户、同一事件类型在 30 分钟内出现未关闭风险时合并到已有案例并提升分数/级别。高风险和严重风险 5 分钟、中风险 30 分钟、低风险 24 小时。独立 `sla-worker` 每 30 秒扫描一次，追加 `sla_escalated` 轨迹与通知，不在 4 个 API worker 中重复调度。

时间线记录操作者、原/新状态、原因、request_id 和 IP，只提供追加与查询操作，不提供修改/删除接口。

## 4. 安全与隐私

- Access Token 默认 15 分钟；Refresh Token 默认 30 天。
- 刷新时旧 Refresh Token 立即撤销并指向替代令牌，重复使用返回 401。
- 退出登录撤销 Refresh Token；修改密码增加 `token_version` 并撤销该用户全部刷新令牌。
- 登录连续失败 5 次后锁定 15 分钟。
- 私人会话、情绪记录和风险案例继续执行对象级权限检查；客户端传入的 user_id 不作为授权依据。
- 上传继续执行大小、MIME、魔数、随机文件名和受管路径校验。

## 5. 可观测与部署

Compose 运行 4 个 Uvicorn worker，Prometheus 使用 multiprocess collector 汇总 Counter/Histogram/Gauge。监控覆盖 API QPS/错误率/P50/P95/P99、AI 成功/超时/429/TTFT/降级、缓存结果/错误、开放风险案例/SLA、PostgreSQL 和 Redis。

告警规则：API 5xx > 5%、AI 超时 > 20%、存在 SLA 超时、Redis 不可用、PostgreSQL 连接使用率 > 80%。Grafana 仪表盘由 provisioning 自动加载。

端口为避免与本机其他 Docker 项目冲突采用：前端 8088、API 8000、PostgreSQL 5433、Redis 6380、Prometheus 9091、Grafana 3001。

## 6. 验证

```powershell
environment\venv\Scripts\python.exe -m pytest tests\test_api.py -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
docker compose up -d --build
docker compose ps
```

当前自动化包含后端业务/安全/并发测试、AI 供应商故障注入、5 项前端单元测试、2 条 Playwright 核心链路，以及 11 条离线 AI/RAG 评测案例。覆盖并发领取、HttpOnly Refresh Cookie 轮换、SSE 持久化、缓存负值、指标暴露、RAG 拒答和隐私脱敏。

## 7. 当前边界

- DeepSeek 指标只有配置真实 API Key 并产生请求后才有样本；无 Key 时走明确降级回复。
- 当前压测是 Windows + Docker Desktop 单机结果，不等同于生产容量承诺。
- 后续性能结论必须同时记录数据量、硬件、worker 数、数据库执行计划和测试脚本参数。
