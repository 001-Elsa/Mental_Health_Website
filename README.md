# 心晴 Campus

面向高校学生的心理健康支持平台，提供用户模式和后台管理员模式两套体验。

用户模式只展示当前用户自己的情绪记录、AI 倾听、心理画像、支持进展和个性化推荐。后台管理员模式用于查看全站运营指标、风险干预队列、内容审核、用户管理和审计记录。

> 本项目用于心理支持与资源导航，不提供医疗诊断或治疗结论。高风险场景会优先引导用户联系现实支持者、学校心理中心或紧急服务。

## 核心亮点

- 双模式权限边界：普通用户只能查看自己的记录；管理员才能查看全站风险、内容和运营数据。
- AI 倾听闭环：多轮对话、长期摘要、用户画像、风险识别、支持练习推荐和安全降级。
- 可信 RAG 问答：区分审核知识库、我的历史倾听、匿名公开经验；回答展示引用来源，资料不足时明确拒答。
- 心理画像推荐：显性展示情绪主线、压力来源、支持偏好，并解释每条文章或练习为什么被推荐。
- 风险干预工作台：管理员可处理风险案例、SLA、处置时间线、通知和审计日志。
- 工程化能力：FastAPI、React、TypeScript、SQLAlchemy、Alembic、Redis 降级、Docker Compose、CI、自动化测试和压测脚本。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、TanStack Query、Zustand、ECharts、React Hook Form、Zod |
| 后端 | FastAPI、SQLAlchemy 2、Pydantic 2、JWT、RBAC、Alembic |
| 数据 | PostgreSQL / SQLite、Redis / 内存降级缓存 |
| AI | DeepSeek Chat、轻量中文检索、可解释风险规则、线性趋势预测 |
| 工程 | Docker Compose、Nginx、pytest、Vitest、GitHub Actions、压测脚本 |

## 本地启动

```bash
copy .env.example .env
docker compose up --build
```

- Web: `http://127.0.0.1:8088`
- OpenAPI: `http://127.0.0.1:8000/docs`
- 健康检查: `http://127.0.0.1:8000/api/health`
- Prometheus: `http://127.0.0.1:9091`
- Grafana: `http://127.0.0.1:3001`（默认 `admin / mental-health-admin`，首次部署后请修改）

## 纵向深化能力

- AI：`httpx.AsyncClient` 连接池、并发信号量、分级超时、最多 2 次可恢复错误重试、安全降级，以及 `POST /api/consult/chat/stream` SSE 流式输出。
- 数据库：流式会话使用 SQLAlchemy `AsyncSession` 与 `asyncpg`，Alembic 迁移增加热路径复合索引。
- Redis：Cache Aside、空值短缓存、随机 TTL、单飞回源、5 秒故障熔断及内存降级。
- 风险案例：30 分钟跨会话合并、原子领取、严格状态机、乐观锁、对象级处理权限、独立 SLA worker 与只追加审计时间线。
- 安全：15 分钟 Access Token、Refresh Token 轮换/撤销、改密后旧令牌失效、登录失败限流。
- 可观测性：4 Uvicorn worker 多进程指标、Prometheus、Grafana、PostgreSQL/Redis exporters 和 5 条告警规则。

详细实现、验证方式和已知边界见 [纵向深化说明](docs/VERTICAL_UPGRADE.md) 与 [Docker 性能报告](docs/PERFORMANCE.md)。

本地开发也可以分别启动后端和前端：

```bash
environment\venv\Scripts\python.exe run.py
```

```bash
cd frontend
npm install
npm run dev
```

插入演示数据：

```bash
environment\venv\Scripts\python.exe seed.py
```

## 验证

```bash
$env:PYTHONPATH='.'
environment\venv\Scripts\pytest.exe tests\test_api.py -q
```

```bash
cd frontend
npm.cmd run build
```

## 默认能力边界

- 用户默认进入用户模式，只能看到自己的情绪、会话、通知和推荐。
- 管理员登录后额外出现后台管理入口，可以查看全站聚合数据和风险队列。
- 私密会话不会进入公开搜索；公开分享会经过安全规则和审核治理。
- RAG 回答只引用审核资料；历史倾听和匿名公开经验仅用于归纳上下文，不直接暴露身份信息。
