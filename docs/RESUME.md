# 简历项目描述与面试证据

## 推荐项目名称

**心晴 Campus｜高校 AI 心理支持与风险干预平台**

技术栈：React、TypeScript、FastAPI、PostgreSQL、Redis、Docker Compose、Prometheus、Playwright。

## 简历版描述

- 针对长对话上下文膨胀和网络重试重复写入问题，设计“最近消息 + 长期摘要 + 用户画像”的分层记忆，并以数据库唯一幂等键持久化 AI 响应，保证客户端重试不会重复调用模型、写消息或创建风险案例。
- 针对 RAG 幻觉和心理数据隐私问题，仅允许审核知识进入引用，私人历史与匿名公开经历只作归纳上下文，证据不足直接拒答；建立 11 条离线回归集，覆盖召回、未审核资料隔离、风险识别和联系方式脱敏，当前质量门槛全部通过。
- 针对多管理员并发处置覆盖问题，实现 30 分钟跨会话案例合并、风险升级、SLA、严格状态机和 `version` 条件更新；并发测试中 20 个领取请求仅 1 个成功，所有处置写入只追加时间线、审计日志和用户通知。
- 针对 Redis 故障导致请求反复等待 socket 超时的问题，实现负缓存、随机 TTL、本地单飞、Redis 短锁和 5 秒熔断；当前 Docker 故障注入中 501/501 请求成功，首次故障延迟 4044ms，熔断窗口 P50 为 334ms（下降 91.7%），并保留环境指纹和全部逐请求样本。

建议简历只保留其中 3 条，并确保面试时可以打开对应代码、测试和结果文件。

## 数字证据映射

| 简历数字 | 证据 | 复现命令 |
| --- | --- | --- |
| 离线评测 11/11 | `evals/cases.json`、`evals/results/latest.json` | `python evals/run_evals.py` |
| 20 个领取请求仅 1 个成功 | `test_twenty_concurrent_claims_have_exactly_one_winner` | `pytest tests/test_api.py -k twenty_concurrent -q` |
| Redis 故障逐请求数据与恢复状态 | `benchmarks/results/docker-cache-current/` | `scripts/benchmark-cache-failure.ps1` |
| 前后端与浏览器回归 | pytest、Vitest、Playwright | 见 README“验证与复现” |

## 面试时必须主动说明的边界

- Docker 性能数据来自个人开发机，不代表生产容量；当前报告保留逐请求样本，旧摘要仅作历史线索。
- RAG 当前是可解释的词法基线，不是向量数据库方案。
- 离线 Eval 验证工程安全边界，不构成医疗有效性证明。
- 项目是模块化单体加独立 SLA Worker，不包装成微服务。
