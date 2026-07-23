# 性能验证与复现报告

## 结论

项目保留当前代码生成的逐请求原始样本，并单独保留早期 Docker 故障实验的历史摘要。两者都只用于工程回归，不用于宣称生产容量。

## 当前可审计基线

结果文件：[local-sqlite-current.json](../benchmarks/results/local-sqlite-current.json)。

环境由结果文件自动记录，本轮为 Windows 本地、SQLite、单 API 进程：

| 场景 | 请求/并发 | 成功率 | QPS | P50 | P95 | P99 |
| --- | --- | --- | --- | --- | --- | --- |
| 健康检查 | 400/20 | 100% | 56.33 | 283.94ms | 825.59ms | 1185.81ms |
| 文章列表 | 1000/50 | 100% | 53.57 | 615.53ms | 2606.00ms | 3913.34ms |

该结果暴露出单进程 SQLite 在高并发下的明显排队，因此不把它包装成“高并发能力”。结果文件保留全部 1400 个延迟样本，可重新计算百分位。

## 当前 Docker Redis 故障实验

运行元数据：[00-run-metadata.json](../benchmarks/results/docker-cache-current/00-run-metadata.json)。三份报告分别保留全部 400、1、100 个逐请求延迟样本：

| 场景 | 请求/并发 | 持续时间 | 成功率 | QPS | P50 | P95 | P99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Redis 正常 | 400/20 | 6.566s | 100% | 60.92 | 234.10ms | 801.76ms | 1224.05ms |
| Redis 停机，熔断前首次请求 | 1/1 | 4.044s | 100% | 不作吞吐比较 | 4044.20ms | 4044.20ms | 4044.20ms |
| Redis 停机，5 秒熔断窗口内 | 100/20 | 1.956s | 100% | 51.12 | 334.13ms | 799.48ms | 982.76ms |

环境：Windows Docker Desktop 4.82.0、Docker Engine 29.6.1、PostgreSQL 16、Redis 7、1 个 Uvicorn Worker。为保证归因明确，实验固定单 Worker：第二阶段只发 1 个请求，精确记录关闭状态下的首次 socket 失败；第三阶段在随后 5 秒熔断窗口内完成 100 个请求，不混入下一次 Redis 探测。首次故障延迟为 4044.20ms，熔断窗口 P50 为 334.13ms，下降 91.7%；三个阶段共 501 个请求，全部返回 HTTP 200。最终恢复检查为 `database=ok, cache=redis`。

原始报告：

- [Redis 正常](../benchmarks/results/docker-cache-current/01-redis-healthy.json)
- [首次故障](../benchmarks/results/docker-cache-current/02-outage-first-failure.json)
- [熔断窗口](../benchmarks/results/docker-cache-current/03-circuit-open.json)

这组结果说明熔断避免了每个请求重复承担约 4 秒的 Redis 失败探测，但不能据此推断生产容量；健康与熔断阶段的请求数也不同，只比较逐请求延迟，不把单次首次故障的 `0.25 QPS` 包装成吞吐基线。

## 历史 Redis 故障摘要

历史摘要：[legacy-docker-cache-summary.json](../benchmarks/results/legacy-docker-cache-summary.json)。

环境：Windows Docker Desktop、PostgreSQL 16、Redis 7、4 个 Uvicorn Worker。

| 场景 | 请求/并发 | 成功率 | QPS | P95 |
| --- | --- | --- | --- | --- |
| 文章列表，Redis 正常 | 1000/50 | 100% | 101.95 | 1412ms |
| Redis 停机，首次 socket 失败 | 400/20 | 100% | 7.52 | 4068ms |
| Redis 停机，熔断窗口内 | 400/20 | 100% | 62.69 | 799ms |

旧实验曾显示熔断窗口内吞吐约为首次故障阶段的 8.3 倍、P95 下降约 80%。它没有保留逐请求样本，因此明确标记为 `legacy-summary`，只作为历史线索，不再作为 README 或简历的主数据。

## 一键复现

普通基准：

```powershell
python tests/load/run_suite.py --base-url http://127.0.0.1:8000 --output benchmarks/results/latest.json
```

Redis 故障实验：

```powershell
./scripts/benchmark-cache-failure.ps1
```

故障脚本使用独立 Compose 项目和进程内随机实验密钥，不读取或改写开发者密钥；它在 `try/finally` 中停止并恢复 Redis，依次保存健康、首次故障和熔断窗口三个原始报告，并记录恢复健康状态。Windows 禁止本地脚本执行时可使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/benchmark-cache-failure.ps1
```

单场景：

```powershell
python tests/load/benchmark.py `
  --endpoint '/api/articles/?skip=0&limit=20' `
  --requests 1000 `
  --concurrency 50 `
  --warmup 50 `
  --output benchmarks/results/article-list.json
```

比较两次结果：

```powershell
python tests/load/compare_results.py before.json after.json
```

## 报告字段

每个新报告都包含：

- Git revision；
- 操作系统、Python 版本和处理器信息；
- Base URL、接口、请求数、并发数、预热数和超时；
- 状态码、异常类型、成功率；
- QPS、均值、P50、P95、P99、最大延迟；
- 每个请求的原始延迟样本。

## 后续生产评估要求

生产容量评估还需要固定 Linux 硬件、固定数据量、独立压测机、至少 15 分钟稳态窗口、CPU/内存/数据库连接池曲线，以及 AI 接口单独的供应商延迟目标。
