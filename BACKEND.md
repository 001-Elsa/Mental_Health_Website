# 心理健康AI助手 — 后端 API 文档

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite (文件: `mental_health_v2.db`) |
| 密码加密 | passlib + bcrypt 4.2 |
| 身份认证 | JWT (python-jose) |
| AI 对话 | DeepSeek API (`deepseek-chat`) |

## 项目结构

```
backend/
├── main.py              # FastAPI 入口，注册路由、静态文件
├── auth.py              # JWT 工具 + 密码哈希
├── schemas.py           # Pydantic 请求/响应模型
└── routers/
    ├── auth.py          # 注册 / 登录 / 验证码
    ├── analytics.py     # 数据分析仪表盘
    ├── articles.py      # 知识文章 CRUD + 留言 + 下载
    ├── records.py       # 咨询记录 CRUD + 置顶
    ├── mood.py          # 情绪日志发布 / 搜索 / 收藏
    ├── community.py     # 社区讨论 CRUD + 回复
    └── consult.py       # AI 对话 + 会话管理

database/
├── database.py          # SQLAlchemy 引擎 / 会话 / 建表
└── models.py            # 9 张表的 ORM 模型
```

## 数据库表 (9 张)

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `users` | 用户 | id, nickname, phone, password_hash |
| `mood_logs` | 情绪日志 | user_id, score, trigger, note, visibility, bookmark_count |
| `consultations` | 咨询记录 | user_id, conversation_id, title, summary, emotion_tag, pinned |
| `articles` | 知识文章 | title, author, summary, cover_image, content, category, status, read_count |
| `discussions` | 社区讨论 | user_id, title, content, category, reply_count, view_count |
| `chat_messages` | AI对话消息 | conversation_id, role, content |
| `bookmarks` | 收藏 | user_id, mood_log_id |
| `comments` | 文章评论 | article_id, user_id, content |
| `replies` | 讨论回复 | discussion_id, user_id, content |

---

## API 端点总览

### 🔐 用户认证 `/api/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/send-code` | 发送短信验证码（不向前端返回验证码） |
| POST | `/register` | 注册 (nickname + phone + code + password) |
| POST | `/login` | 登录 (nickname + password → JWT token) |

### 📊 数据分析 `/api/analytics`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/overview` | 四卡片统计 (users / mood_logs / consultations / avg_score) |
| GET | `/mood-trend?days=14` | 每日平均情绪评分 + 记录数 |
| GET | `/consultation-stats?days=14` | 每日咨询数 + 参与用户数 |
| GET | `/user-activity?days=14` | 每日活跃/新增/日记/咨询用户数 |

### 📚 知识文章 `/api/articles`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/categories` | 已有分类列表 |
| GET | `/?title=&category=&status=` | 文章列表（支持搜索筛选） |
| GET | `/{id}` | 文章详情 |
| POST | `/` | 发布文章 |
| PATCH | `/{id}` | 编辑文章 |
| DELETE | `/{id}` | 删除文章 |
| POST | `/{id}/view` | 阅读计数 +1 |
| GET | `/{id}/download` | 下载文章为 .txt |
| GET | `/{id}/comments` | 文章评论列表 |
| POST | `/{id}/comments` | 添加评论 |
| DELETE | `/{id}/comments/{cid}` | 删除评论 |

### 💬 咨询记录 `/api/consultations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/?sid=&title=` | 列表（置顶优先） |
| GET | `/{id}` | 详情 |
| POST | `/` | 创建 |
| PATCH | `/{id}` | 编辑标题 / 切换置顶 |
| DELETE | `/{id}` | 删除 |

### 😊 情绪日志 `/api/mood`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/?user_id=&score=` | 搜索公开日志 |
| GET | `/{id}` | 详情 |
| POST | `/` | 发布日志 (user_id + score + trigger + note + visibility) |
| POST | `/{id}/bookmark?user_id=1` | 切换收藏 |

### 👥 社区讨论 `/api/discussions`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/?title=&category=` | 列表 |
| GET | `/{id}` | 详情 |
| POST | `/` | 发帖 |
| PATCH | `/{id}` | 编辑 |
| DELETE | `/{id}` | 删帖 |
| POST | `/{id}/view` | 阅读计数 +1 |
| GET | `/{id}/replies` | 回复列表 |
| POST | `/{id}/replies` | 添加回复 |
| DELETE | `/{id}/replies/{rid}` | 删除回复 |

### 🤖 AI 咨询 `/api/consult`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 发送消息 (conversation_id + message) |
| GET | `/conversations` | 所有会话列表 |
| GET | `/history/{conversation_id}` | 会话完整历史 |

---

## 关键业务逻辑

### 1. AI 对话记忆机制
- 每条消息存入 `chat_messages` 表（conversation_id + role + content）
- 每次请求将**该会话全部历史**发送给 DeepSeek API（不截断）
- 首次发消息自动创建 `consultations` 记录（title=首条消息, summary=AI首条回复）
- 情绪标签根据消息关键词自动推断

### 2. JWT 认证
- 登录返回 token，有效期默认 1 天，勾选"30天免密"则 30 天
- Token 包含 user_id + nickname
- 前端存储在 localStorage，API 调用时带上 Authorization header

### 3. 短信验证码
- 调用 `/send-code` 后，验证码不会返回给前端，只会通过短信网关发送到用户手机
- 需要配置真实短信服务环境变量，否则接口会返回 `503`

```bash
SMS_WEBHOOK_URL=https://your-sms-gateway.example.com/send-code
SMS_WEBHOOK_TOKEN=your_optional_bearer_token
SMS_SIGN_NAME=心灵伙伴
```

短信网关会收到 JSON：

```json
{
  "phone": "13800000000",
  "code": "1234",
  "sign_name": "心灵伙伴",
  "message": "您的验证码是 1234，5分钟内有效。请勿泄露给他人。"
}
```

### 4. 置顶排序
- 咨询记录按 `pinned DESC, created_at DESC` 排序
- 置顶记录始终排在最前面

## 启动方式

```bash
# 安装依赖
cd environment && python -m venv venv && source venv/Scripts/activate
pip install -r requirements.txt

# 初始化数据
cd .. && python seed.py

# 启动服务
python run.py
# → http://127.0.0.1:8000
# → Swagger 文档: http://127.0.0.1:8000/docs
```

## 测试账号

| 昵称 | 密码 | 手机 |
|------|------|------|
| 测试用户1 | 123456 | 13800000001 |
| 测试用户2 | 123456 | 13800000002 |
