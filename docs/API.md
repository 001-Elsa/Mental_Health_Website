# API 使用说明

启动后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 交互文档，访问 `/openapi.json` 获取机器可读契约。

## 认证与权限

登录成功后在请求头携带：

```http
Authorization: Bearer <access_token>
```

角色分为 `student` 与 `admin`。学生可维护自己的情绪记录、AI 会话和社区内容；`/api/admin/*`、文章发布和知识文档写入仅管理员可用。

## 核心接口

| 模块 | 方法与路径 | 说明 |
| --- | --- | --- |
| 认证 | `POST /api/auth/login` | 密码登录并签发 JWT |
| 情绪 | `POST /api/mood/` | 记录 1-10 分情绪 |
| 情绪风险 | `GET /api/mood/risk-status` | 返回当前待处理风险与支持行动 |
| 趋势 | `GET /api/analytics/mood-forecast` | 返回未来 7 天基线预测 |
| AI 倾听 | `POST /api/consult/chat` | 支持 `request_key` 幂等、多轮回复、摘要、标签和风险结果 |
| 推荐状态 | `PUT /api/recommendations/preference` | 保存用户手动选择的推荐状态，后续文章与练习推荐持续使用该状态 |
| 支持画像 | `GET /api/users/me/profile` | 返回主要情绪、压力源和支持偏好 |
| RAG | `POST /api/knowledge/ask` | 知识库问答与引用来源 |
| 推荐 | `GET /api/recommendations/articles` | 返回文章及推荐理由 |
| 练习推荐 | `GET /api/recommendations/exercises` | 按画像和情绪推荐短时练习 |
| 社区可见性 | `GET /api/discussions/mine` | 查看自己的公开、私人和待审核内容 |
| 社区 | `POST /api/discussions/{id}/reports` | 举报不安全内容 |
| 风险后台 | `GET /api/admin/risk-events` | 管理员风险处置队列 |
| 风险流转 | `PATCH /api/admin/risk-events/{id}` | 分派、联系、随访、结案与乐观锁版本校验 |
| 处置轨迹 | `GET /api/admin/risk-events/{id}/timeline` | 返回案例完整处置时间线 |
| 站内通知 | `GET /api/users/me/notifications` | 返回支持进展和未读数量 |
| 审计日志 | `GET /api/admin/audit-logs` | 查询管理员关键操作与请求追踪号 |
| 运营趋势 | `GET /api/admin/trends` | 返回情绪、咨询和风险的逐日趋势 |
| 运营管理 | `GET /api/admin/users` | 管理用户角色、文章状态与敏感词规则 |

## 统一错误

```json
{
  "code": "HTTP_403",
  "detail": "需要管理员权限",
  "request_id": "request-trace-id"
}
```

所有响应包含 `X-Request-ID`。参数错误额外返回 `errors` 字段；未处理异常不会向客户端泄露堆栈。
