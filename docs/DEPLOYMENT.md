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

这不是生产认证：CI 不会启动 4 worker 的 Docker API 容器，不会调用真实 AI 提供商，也不替代长时间负载测试、外部网络故障演练或安全渗透测试。AI 目前覆盖无密钥的安全降级；针对上游超时、限流与异常响应的系统化 Mock/故障注入仍是后续工作，真实密钥只应在受控环境使用。

## 性能边界

当前压测可用于比较缓存与故障熔断策略，不用于承诺容量。Windows Docker Desktop 基线中，文章列表在并发 50、1000 次请求下为 101.95 QPS、P95 1412ms；Redis 故障熔断后为 62.69 QPS，熔断前为 7.52 QPS。详细条件与数据见 [PERFORMANCE.md](PERFORMANCE.md)。
