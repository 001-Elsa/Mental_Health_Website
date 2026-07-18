# 简单压测报告

测试日期：2026-07-17

## 环境

- Windows 本地开发机
- Uvicorn 单进程
- SQLite 演示数据库
- Redis 未启动，缓存自动降级为进程内存
- 接口：`GET /api/analytics/overview`
- 400 次请求，并发 20

## 结果

| 指标 | 结果 |
| --- | ---: |
| 成功率 | 100% |
| 吞吐量 | 72.45 req/s |
| 平均延迟 | 262.78 ms |
| P50 | 210.87 ms |
| P95 | 652.67 ms |
| 最大延迟 | 1052.73 ms |

运行命令：

```bash
set REQUESTS=400
set CONCURRENCY=20
environment\venv\Scripts\python.exe tests\load\benchmark.py
```

## 结论

当前结果适合作为开发环境基线，不能代表生产容量。主要限制是 Windows 本地调度、单 Uvicorn 进程和 SQLite；生产评估应使用 Docker Compose 的 PostgreSQL + Redis，并增加 4 个 API worker，再分别测试读接口、登录和 AI 对话。AI/RAG 接口受模型供应商网络时延影响，不应与本地数据接口使用同一性能目标。
