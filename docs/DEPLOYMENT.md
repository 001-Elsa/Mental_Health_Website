# 部署安全与已知限制

## 架构边界

系统是模块化 FastAPI 单体应用：API 进程、独立 SLA worker、PostgreSQL、Redis 和 Prometheus/Grafana 通过 Docker Compose 协作。多个容器和 4 个 Uvicorn worker 不构成微服务或分布式系统；系统没有服务发现、分布式事务或跨服务调用链治理。

## 上公网前的必做项

1. 复制 `.env.example` 为 `.env`，用强随机值替换 `SECRET_KEY`、`POSTGRES_PASSWORD`、`GRAFANA_ADMIN_PASSWORD`，并按需修改管理员用户名。
2. 通过反向代理启用 HTTPS，限制 `CORS_ORIGINS` 为实际前端域名，且不要公开 PostgreSQL、Redis、Prometheus 的端口。
3. 在受控密钥服务或部署平台的 Secret 中保存 DeepSeek 与通知 Webhook 密钥，禁止提交 `.env`。
4. 配置数据库备份、日志保留和 Grafana 管理员轮换；默认演示密码不得用于公网。

## CI 与测试边界

GitHub Actions 启动 PostgreSQL 16 与 Redis 7，并先执行 `alembic upgrade head`，随后运行 API 测试。测试覆盖 PostgreSQL 下的并发风险案例领取、Redis 正常缓存路径，以及 Redis 故障熔断和恢复的故障注入路径。

CI 还会运行不调用外部模型的 AI/RAG 离线质量门槛、Vitest 前端单元测试、生产构建，以及使用 Chromium 的 Playwright 登录与会话恢复链路。

这不是生产认证：CI 不会启动 4 worker 的 Docker API 容器，不会调用真实 AI 提供商，也不替代长时间负载测试、外部网络故障演练或安全渗透测试。自动化测试已覆盖无密钥降级以及上游超时、429 和异常响应的 Mock 故障注入；真实供应商和真实密钥仍只应在受控环境验证。

## 性能边界

当前压测可用于比较缓存与故障熔断策略，不用于承诺容量。Windows Docker Desktop 的当前故障注入中，首次 Redis 失败请求耗时 4044ms；随后 5 秒熔断窗口内 100 个请求的 P50 为 334ms、P95 为 799ms，全部成功，最终恢复检查确认 Redis 与数据库正常。详细条件和逐请求数据见 [PERFORMANCE.md](PERFORMANCE.md)。
