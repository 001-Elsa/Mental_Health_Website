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

## 2026-07-20 Docker 基线

环境：Windows Docker Desktop、PostgreSQL 16、Redis 7、4 个 Uvicorn worker、Prometheus/Grafana 同机运行。每轮使用 `tests/load/benchmark.py`，不包含真实 DeepSeek 网络时间。

| 场景 | 请求 / 并发 | 成功率 | QPS | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 健康检查（PG+Redis） | 1000 / 50 | 100% | 83.41 | 382ms | 1743ms | 2784ms |
| 文章列表（Redis 正常） | 1000 / 50 | 100% | 101.95 | 333ms | 1412ms | 2228ms |
| Redis 停机，熔断前 | 400 / 20 | 100% | 7.52 | 1951ms | 4068ms | 5929ms |
| Redis 停机，5 秒熔断后 | 400 / 20 | 100% | 62.69 | 138ms | 799ms | 4166ms |

熔断后 Redis 故障场景吞吐提高约 8.3 倍，P95 降低约 80%。P99 仍受首次 socket 失败和 Windows/Docker 调度影响，因此不能宣称“高并发生产容量”；下一轮应在固定硬件的 Linux 环境、预置数据量和更长稳态窗口下复测。

可复现命令：

```powershell
$env:BASE_URL='http://127.0.0.1:8000'
$env:REQUESTS='1000'
$env:CONCURRENCY='50'
$env:ENDPOINT='/api/articles/'
environment\venv\Scripts\python.exe tests\load\benchmark.py
```
