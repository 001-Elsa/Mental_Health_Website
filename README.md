# 心晴 Campus

面向高校学生的心理健康支持平台，提供情绪记录、AI 倾听、风险识别、心理知识库问答、内容推荐、社区互助和运营分析能力。

> 本项目用于心理支持与资源导航，不提供医疗诊断。高风险场景优先引导用户联系现实支持者、学校心理中心或紧急服务。

## 项目亮点

- DeepSeek 多轮倾听：保存对话上下文，自动生成情绪标签、结构化摘要和长期记忆压缩。
- 可解释风险识别：结合自伤风险文本信号与近期情绪下降趋势，生成等级、分数、依据和干预任务。
- RAG 心理知识库：检索审核文档与已发布文章，回答携带引用来源，资料不足时明确拒答。
- 运营治理闭环：管理员处理风险事件、社区举报、待审内容和敏感词；普通学生无法访问后台。
- 多媒体同伴社区：长分享使用独立编辑页，支持文字、图片和语音；实时交流广场使用 WebSocket 通知和持久化消息。
- 完整个人中心：头像、背景和签名资料，社区发布历史，以及手机、邮箱、密码安全设置。
- 可解释推荐与预测：按近期情绪匹配内容类别并返回推荐原因；线性基线预测未来 7 天趋势。
- 工程化：JWT/RBAC、Redis 缓存与限流、Alembic、请求幂等、乐观锁、审计日志、统一错误、请求追踪、Docker Compose、CI 和 17 项后端测试。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、TanStack Query、Zustand、ECharts、React Hook Form、Zod |
| 后端 | FastAPI、SQLAlchemy 2、Pydantic 2、JWT、Alembic |
| 数据 | PostgreSQL、Redis；本地开发支持 SQLite 和内存缓存降级 |
| AI | DeepSeek Chat、轻量中文检索、可解释风险规则、线性回归趋势基线 |
| 工程 | Docker Compose、Nginx、pytest、Vitest、GitHub Actions、HTTP 压测脚本 |

## 四个版本目标

- V1：认证、AI 咨询、情绪可视化、文章与社区、Docker 一键启动。
- V2：管理后台、风险干预、社区审核、用户分析、AI 摘要和标签。
- V3：Redis、RBAC、日志与统一异常、CI、OpenAPI 文档和压测报告。
- V4：RAG、历史摘要压缩、趋势预测、推荐系统和内容安全审核。

完整设计见 [系统架构](docs/ARCHITECTURE.md) 与 [真实业务闭环和系统设计](docs/SYSTEM_DESIGN.md)，逐项完成情况见 [功能验收矩阵](docs/FEATURE_AUDIT.md)，接口说明见 [API 文档](docs/API.md)，实测结果见 [压测报告](docs/PERFORMANCE.md)。

第一次接手或准备面试时，建议从 [项目全景学习手册](docs/PROJECT_GUIDE.md) 开始，它按技术栈、功能代码映射、核心调用链、数据模型和面试问答完整讲解了项目。

## 一键启动

```bash
copy .env.example .env
docker compose up --build
```

- Web：`http://127.0.0.1:8080`
- OpenAPI：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

在 `.env` 中填写 `DEEPSEEK_API_KEY` 后启用真实 AI 回复。未配置时风险识别、历史保存和知识检索仍可运行，回复使用安全降级。

## 本地开发

```bash
environment\venv\Scripts\pip.exe install -r environment\requirements.txt
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

| 角色 | 昵称 | 密码 |
| --- | --- | --- |
| 学生 | 测试用户1 | `123456` |
| 管理员 | 平台管理员 | `admin123` |

## 质量验证

```bash
environment\venv\Scripts\pytest.exe -q
cd frontend
npm test
npm run build
```

启动 API 后运行简单压测：

```bash
environment\venv\Scripts\python.exe tests\load\benchmark.py
```

测试覆盖鉴权防伪造、风险事件、管理员 RBAC、社区审核、RAG 引用、趋势预测和历史压缩。CI 配置位于 `.github/workflows/ci.yml`。

## 环境变量

关键配置见 `.env.example`：

- `SECRET_KEY`：生产环境 JWT 密钥。
- `DATABASE_URL`：PostgreSQL 或 SQLite 连接。
- `REDIS_URL`：缓存、验证码和 AI 接口限流。
- `DEEPSEEK_API_KEY` / `DEEPSEEK_URL`：DeepSeek 服务。
- `SMS_WEBHOOK_URL`：短信网关；本地未配置时返回开发验证码。
- `EMAIL_WEBHOOK_URL`：邮箱验证码 Webhook；本地未配置时返回开发验证码。
- `CORS_ORIGINS`：允许访问 API 的前端来源。
