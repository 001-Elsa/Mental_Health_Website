import os
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from uuid import uuid4

test_db = Path("test_mental_health.db").absolute()
if test_db.exists():
    test_db.unlink()

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEEPSEEK_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from database.database import init_db  # noqa: E402
from database.database import SyncSessionLocal  # noqa: E402
from database.models import (  # noqa: E402
    AdminAuditLog,
    Article,
    ChatMessage,
    Consultation,
    Exercise,
    KnowledgeDocument,
    RiskAction,
    RiskEvent,
    User,
    UserNotification,
    UserProfile,
)
from backend.services.conversation_memory import compress_history  # noqa: E402
from backend.services.article_crawler import CrawlSource, CrawlTarget, discover_targets_from_html, parse_article_html  # noqa: E402
from backend.services import article_service  # noqa: E402
from backend.services.rag import retrieve_conversation_context  # noqa: E402


init_db()
client = TestClient(app)
user_counter = count(1)


def auth_headers() -> dict[str, str]:
    suffix = next(user_counter)
    phone = f"1390000{suffix:04d}"
    nickname = f"测试鉴权用户{suffix}"
    code_res = client.post("/api/auth/send-code", json={"phone": phone})
    code = code_res.json()["dev_code"]
    client.post(
        "/api/auth/register",
        json={"nickname": nickname, "phone": phone, "code": code, "password": "123456"},
    )
    login = client.post("/api/auth/login", json={"nickname": nickname, "password": "123456"})
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def admin_headers() -> dict[str, str]:
    headers = auth_headers()
    user_id = client.get("/api/users/me", headers=headers).json()["id"]
    with SyncSessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        user.role = "admin"
        db.commit()
    return headers


def test_protected_write_requires_token():
    res = client.post("/api/articles/", json={"title": "no auth", "category": "test", "content": "x"})
    assert res.status_code == 401


def test_current_user_endpoint_and_spoofed_user_id_ignored():
    headers = auth_headers()
    me = client.get("/api/users/me", headers=headers)
    assert me.status_code == 200
    user_id = me.json()["id"]

    res = client.post(
        "/api/mood/",
        json={"user_id": 9999, "score": 8, "trigger": "pytest", "note": "测试", "visibility": "公开"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["user_id"] == user_id


def test_mood_trend_switches_between_current_user_and_all_users():
    mine_headers = auth_headers()
    other_headers = auth_headers()
    client.post(
        "/api/mood/",
        json={"score": 2, "trigger": "个人趋势", "note": "仅属于当前用户", "visibility": "私人"},
        headers=mine_headers,
    )
    client.post(
        "/api/mood/",
        json={"score": 10, "trigger": "平台趋势", "note": "另一个用户的数据", "visibility": "私人"},
        headers=other_headers,
    )

    unauthorized = client.get("/api/analytics/mood-trend?days=14&scope=mine")
    mine = client.get("/api/analytics/mood-trend?days=14&scope=mine", headers=mine_headers)
    all_users = client.get("/api/analytics/mood-trend?days=14&scope=all")

    assert unauthorized.status_code == 401
    assert mine.status_code == 200
    assert all_users.status_code == 200
    mine_points = [point for point in mine.json() if point["count"] > 0]
    all_points = [point for point in all_users.json() if point["count"] > 0]
    assert mine_points[-1]["avg_score"] == 2.0
    assert mine_points[-1]["count"] == 1
    assert all_points[-1]["count"] >= 2


def test_ai_chat_has_safe_fallback_without_provider_key():
    headers = auth_headers()
    res = client.post(
        "/api/consult/chat",
        json={"conversation_id": "pytest-conv", "message": "我最近压力很大", "visibility": "私人"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "reply" in res.json()


def test_conversation_search_matches_message_content_and_isolates_users():
    owner_headers = auth_headers()
    other_headers = auth_headers()
    conversation_id = f"search-{uuid4().hex[:12]}"
    client.post(
        "/api/consult/chat",
        json={"conversation_id": conversation_id, "message": "第一次普通问候", "visibility": "私人"},
        headers=owner_headers,
    )
    client.post(
        "/api/consult/chat",
        json={"conversation_id": conversation_id, "message": "我想继续讨论星河睡眠计划", "visibility": "私人"},
        headers=owner_headers,
    )

    owner_result = client.get("/api/consult/conversations?q=星河睡眠计划", headers=owner_headers)
    other_result = client.get("/api/consult/conversations?q=星河睡眠计划", headers=other_headers)

    assert owner_result.status_code == 200
    assert [item["conversation_id"] for item in owner_result.json()] == [conversation_id]
    assert other_result.status_code == 200
    assert other_result.json() == []


def test_conversation_owner_can_rename_pin_and_delete():
    owner_headers = auth_headers()
    other_headers = auth_headers()
    conversation_id = f"manage-{uuid4().hex[:12]}"
    client.post(
        "/api/consult/chat",
        json={"conversation_id": conversation_id, "message": "需要管理的会话", "visibility": "私人"},
        headers=owner_headers,
    )

    forbidden_update = client.patch(
        f"/api/consult/conversations/{conversation_id}",
        json={"title": "越权修改", "pinned": True},
        headers=other_headers,
    )
    updated = client.patch(
        f"/api/consult/conversations/{conversation_id}",
        json={"title": "我的置顶会话", "pinned": True},
        headers=owner_headers,
    )
    conversations = client.get("/api/consult/conversations", headers=owner_headers).json()

    assert forbidden_update.status_code == 404
    assert updated.status_code == 200
    assert updated.json()["title"] == "我的置顶会话"
    assert updated.json()["pinned"] is True
    assert conversations[0]["conversation_id"] == conversation_id
    assert conversations[0]["pinned"] is True

    forbidden_visibility = client.patch(
        f"/api/consult/conversations/{conversation_id}/visibility?visibility=公开",
        headers=other_headers,
    )
    made_public = client.patch(
        f"/api/consult/conversations/{conversation_id}/visibility?visibility=公开",
        headers=owner_headers,
    )
    public_results = client.get(
        "/api/content/public-conversations",
        params={"keyword": "我的置顶会话", "period": "all"},
    ).json()

    assert forbidden_visibility.status_code == 404
    assert made_public.status_code == 200
    assert made_public.json()["visibility"] == "公开"
    assert [item["title"] for item in public_results] == ["我的置顶会话"]

    made_private = client.patch(
        f"/api/consult/conversations/{conversation_id}/visibility?visibility=私人",
        headers=owner_headers,
    )
    private_results = client.get(
        "/api/content/public-conversations",
        params={"keyword": "我的置顶会话", "period": "all"},
    ).json()

    assert made_private.status_code == 200
    assert made_private.json()["visibility"] == "私人"
    assert private_results == []

    forbidden_delete = client.delete(f"/api/consult/conversations/{conversation_id}", headers=other_headers)
    deleted = client.delete(f"/api/consult/conversations/{conversation_id}", headers=owner_headers)
    remaining_ids = {
        item["conversation_id"]
        for item in client.get("/api/consult/conversations", headers=owner_headers).json()
    }
    assert forbidden_delete.status_code == 404
    assert deleted.status_code == 200
    assert conversation_id not in remaining_ids


def test_content_search_excludes_private_conversations_and_filters_time():
    now = datetime.now()
    with SyncSessionLocal() as db:
        db.add_all([
            Consultation(user_id=1, conversation_id="public-recent", title="exam pressure public", summary="recent", visibility="公开", created_at=now),
            Consultation(user_id=1, conversation_id="public-old", title="exam pressure old", summary="old", visibility="公开", created_at=now - timedelta(days=120)),
            Consultation(user_id=1, conversation_id="private-recent", title="exam pressure private", summary="private", visibility="私人", created_at=now),
        ])
        db.commit()

    recent = client.get("/api/content/public-conversations?keyword=exam%20pressure&period=30d")
    all_time = client.get("/api/content/public-conversations?keyword=exam%20pressure&period=all")

    assert recent.status_code == 200
    assert [item["title"] for item in recent.json()] == ["exam pressure public"]
    assert {item["title"] for item in all_time.json()} == {"exam pressure public", "exam pressure old"}
    assert all("user_id" not in item and "conversation_id" not in item for item in all_time.json())


def test_article_search_filters_by_original_publication_time():
    now = datetime.now()
    with SyncSessionLocal() as db:
        db.add_all([
            Article(title="campus sleep recent", summary="recent", category="sleep", status="已发布", source_name="知乎", source_url="https://example.com/recent", published_at=now - timedelta(days=10)),
            Article(title="campus sleep old", summary="old", category="sleep", status="已发布", source_name="高校心理中心", source_url="https://example.com/old", published_at=now - timedelta(days=400)),
        ])
        db.commit()
    article_service.invalidate_articles()

    response = client.get("/api/articles/?title=campus%20sleep&period=30d")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["campus sleep recent"]
    assert response.json()[0]["source_name"] == "知乎"


def test_article_crawler_parses_metadata_without_copying_full_text():
    html = """
    <html><head>
      <meta property="og:title" content="大学生睡眠与压力" />
      <meta property="og:description" content="一篇面向高校学生的心理健康摘要。" />
      <meta property="article:published_time" content="2026-06-10T08:00:00+08:00" />
      <meta name="author" content="心理中心" />
    </head><body><p>这里是不会入库的完整正文。</p></body></html>
    """
    values = parse_article_html(CrawlTarget("https://zhuanlan.zhihu.com/p/example", "睡眠与精力"), html)

    assert values["title"] == "大学生睡眠与压力"
    assert values["source_name"] == "知乎"
    assert values["published_at"] == datetime(2026, 6, 10, 8, 0)
    assert values["content"] == ""


def test_article_crawler_discovers_allowlisted_links_and_infers_category():
    source = CrawlSource(
        "https://school.example.edu/psych/list.htm",
        "心理科普",
        r"/psych/article/\d+\.html$",
    )
    html = """
    <a href="/psych/article/101.html">考试焦虑怎么缓解</a>
    <a href="/psych/article/101.html?from=home">重复链接</a>
    <a href="/psych/article/102.html">改善睡眠的五个方法</a>
    <a href="https://other.example.com/psych/article/103.html">站外文章</a>
    <a href="/news/104.html">不匹配栏目</a>
    """

    targets = discover_targets_from_html(source, html)

    assert [(target.url, target.category) for target in targets] == [
        ("https://school.example.edu/psych/article/101.html", "焦虑缓解"),
        ("https://school.example.edu/psych/article/102.html", "睡眠与精力"),
    ]


def test_high_risk_chat_creates_review_event():
    headers = auth_headers()
    conversation_id = f"risk-{uuid4().hex[:12]}"
    res = client.post(
        "/api/consult/chat",
        json={"conversation_id": conversation_id, "message": "我已经准备今晚就自杀", "visibility": "私人"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["risk"]["level"] == "critical"
    assert res.json()["risk"]["requires_intervention"] is True
    with SyncSessionLocal() as db:
        event = db.query(RiskEvent).filter(RiskEvent.conversation_id == conversation_id).first()
        assert event is not None
        assert event.status == "pending"


def test_admin_routes_enforce_role_and_allow_admin():
    headers = auth_headers()
    forbidden = client.get("/api/admin/overview", headers=headers)
    assert forbidden.status_code == 403
    user_id = client.get("/api/users/me", headers=headers).json()["id"]
    with SyncSessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        user.role = "admin"
        db.commit()
    allowed = client.get("/api/admin/overview", headers=headers)
    assert allowed.status_code == 200
    assert "pending_risks" in allowed.json()


def test_community_sensitive_content_enters_review_queue():
    headers = auth_headers()
    created = client.post(
        "/api/discussions/",
        json={"title": "想找同学聊一聊", "category": "经验分享", "content": "可以加微信继续联系吗"},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["status"] == "pending_review"
    public_rows = client.get("/api/discussions/").json()
    assert all(row["id"] != created.json()["id"] for row in public_rows)


def test_rag_returns_grounded_citation_without_provider_key():
    with SyncSessionLocal() as db:
        db.add(KnowledgeDocument(
            title="考试焦虑应对",
            source="测试心理中心",
            category="焦虑缓解",
            content="考试焦虑时先进行缓慢呼吸，再把复习任务拆成十分钟可以完成的一步。",
        ))
        db.commit()
    res = client.post("/api/knowledge/ask", json={"question": "考试焦虑时应该怎么办"})
    assert res.status_code == 200
    assert res.json()["citations"]
    assert "考试焦虑" in res.json()["citations"][0]["title"]


def test_personalized_rag_uses_owner_and_public_conversations_only():
    owner_headers = auth_headers()
    other_headers = auth_headers()
    owner_id = client.get("/api/users/me", headers=owner_headers).json()["id"]
    other_id = client.get("/api/users/me", headers=other_headers).json()["id"]
    marker = f"aurora{uuid4().hex[:10]}"
    rows = [
        Consultation(user_id=owner_id, conversation_id=f"{marker}-own", title=f"{marker} sleep", visibility="私人"),
        Consultation(user_id=other_id, conversation_id=f"{marker}-public", title=f"{marker} sleep", visibility="公开"),
        Consultation(user_id=other_id, conversation_id=f"{marker}-private", title=f"{marker} sleep", visibility="私人"),
    ]
    with SyncSessionLocal() as db:
        db.add_all(rows)
        db.add_all([
            ChatMessage(conversation_id=f"{marker}-own", role="user", content=f"{marker} OWN_DETAIL"),
            ChatMessage(conversation_id=f"{marker}-own", role="assistant", content=f"{marker} OWN_AI_REPLY"),
            ChatMessage(conversation_id=f"{marker}-public", role="user", content=f"{marker} PUBLIC_DETAIL"),
            ChatMessage(conversation_id=f"{marker}-public", role="assistant", content=f"{marker} PUBLIC_AI_REPLY"),
            ChatMessage(conversation_id=f"{marker}-private", role="user", content=f"{marker} HIDDEN_OTHER_PRIVATE"),
            ChatMessage(conversation_id=f"{marker}-private", role="assistant", content=f"{marker} HIDDEN_AI_REPLY"),
        ])
        db.commit()
        chunks = retrieve_conversation_context(db, marker, user_id=owner_id)

    combined = "\n".join(chunk.content for chunk in chunks)
    assert {chunk.kind for chunk in chunks} == {"own_conversation", "public_conversation"}
    assert "OWN_AI_REPLY" in combined
    assert "PUBLIC_AI_REPLY" in combined
    assert "HIDDEN_OTHER_PRIVATE" not in combined
    assert "HIDDEN_AI_REPLY" not in combined

    response = client.post("/api/knowledge/ask", json={"question": marker}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["personalization"] == {"own_history": 1, "public_conversations": 1}


def test_mood_forecast_is_bounded_and_explained():
    headers = auth_headers()
    for score in (4, 5, 6, 7):
        client.post(
            "/api/mood/",
            json={"score": score, "trigger": "pytest", "note": "趋势测试", "visibility": "私人"},
            headers=headers,
        )
    res = client.get("/api/analytics/mood-forecast?days=7", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "linear_regression_baseline"
    assert len(body["points"]) == 7
    assert all(1 <= point["predicted_score"] <= 10 for point in body["points"])


def test_conversation_history_compression_keeps_user_context():
    summary = compress_history([
        {"role": "user", "content": "最近因为考试很焦虑"},
        {"role": "assistant", "content": "我们先拆分任务"},
        {"role": "user", "content": "昨晚也没有睡好"},
    ])
    assert "焦虑" in summary
    assert "考试" in summary
    assert len(summary) <= 700


def test_private_discussion_is_owner_only_and_like_is_reversible():
    owner = auth_headers()
    stranger = auth_headers()
    created = client.post(
        "/api/discussions/",
        json={"title": "只对自己可见的记录", "category": "成长记录", "content": "这是私人内容", "visibility": "私人"},
        headers=owner,
    )
    assert created.status_code == 200
    discussion_id = created.json()["id"]
    assert client.get(f"/api/discussions/{discussion_id}", headers=owner).status_code == 200
    assert client.get(f"/api/discussions/{discussion_id}", headers=stranger).status_code == 404
    assert client.post(f"/api/discussions/{discussion_id}/like", headers=stranger).status_code == 404

    first = client.post(f"/api/discussions/{discussion_id}/like", headers=owner)
    second = client.post(f"/api/discussions/{discussion_id}/like", headers=owner)
    assert first.json() == {"liked": True, "like_count": 1}
    assert second.json() == {"liked": False, "like_count": 0}


def test_declining_mood_creates_trend_risk_event():
    headers = auth_headers()
    user_id = client.get("/api/users/me", headers=headers).json()["id"]
    last = None
    for score in (6, 4, 2):
        last = client.post(
            "/api/mood/",
            json={"score": score, "trigger": "连续压力", "note": "趋势测试", "visibility": "私人"},
            headers=headers,
        )
        assert last.status_code == 200
    assert last is not None
    assert last.json()["risk"]["level"] == "medium"
    with SyncSessionLocal() as db:
        event = db.query(RiskEvent).filter(
            RiskEvent.user_id == user_id,
            RiskEvent.event_type == "mood_trend",
        ).first()
        assert event is not None
        assert event.consultation_id is not None


def test_consultation_updates_profile_and_recommends_exercise():
    with SyncSessionLocal() as db:
        db.add(Exercise(
            title="三分钟呼吸练习",
            category="焦虑缓解",
            description="用稳定呼吸降低紧张感",
            steps="吸气四秒，停两秒，呼气六秒",
            duration_minutes=3,
        ))
        db.commit()
    headers = auth_headers()
    user_id = client.get("/api/users/me", headers=headers).json()["id"]
    response = client.post(
        "/api/consult/chat",
        json={"conversation_id": f"profile-{uuid4().hex[:10]}", "message": "我最近考试压力很大，也有点焦虑", "visibility": "私人"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["profile_summary"]
    assert response.json()["recommended_exercises"]
    profile = client.get("/api/users/me/profile", headers=headers)
    assert profile.status_code == 200
    assert "学习与考试" in profile.json()["stressors"]
    with SyncSessionLocal() as db:
        assert db.query(UserProfile).filter(UserProfile.user_id == user_id).first() is not None


def test_manual_recommendation_emotion_persists_and_controls_ranking():
    headers = auth_headers()
    user_id = client.get("/api/users/me", headers=headers).json()["id"]
    with SyncSessionLocal() as db:
        matching = Article(
            title=f"焦虑匹配文章-{uuid4().hex[:8]}",
            category="焦虑缓解",
            status="已发布",
            read_count=1,
        )
        popular_unmatched = Article(
            title=f"高热度非匹配文章-{uuid4().hex[:8]}",
            category="心理科普",
            status="已发布",
            read_count=999999,
        )
        db.add_all([
            Consultation(
                user_id=user_id,
                conversation_id=f"recommend-{uuid4().hex[:10]}",
                title="最近很开心",
                emotion_tag="愉悦",
                visibility="私人",
            ),
            matching,
            popular_unmatched,
        ])
        db.commit()
        matching_id = matching.id
        popular_unmatched_id = popular_unmatched.id

    invalid = client.put("/api/recommendations/preference", json={"emotion": "随便"}, headers=headers)
    saved = client.put("/api/recommendations/preference", json={"emotion": "焦虑"}, headers=headers)
    first = client.get("/api/recommendations/articles", headers=headers)
    second = client.get("/api/recommendations/articles", headers=headers)

    assert invalid.status_code == 422
    assert saved.status_code == 200
    assert saved.json() == {"emotion": "焦虑", "is_manual": True}
    assert first.status_code == 200
    assert first.json()["profile"]["emotion"] == "焦虑"
    assert first.json()["profile"]["is_manual"] is True
    assert second.json()["profile"]["emotion"] == "焦虑"
    ranked_ids = [item["article"]["id"] for item in first.json()["items"]]
    assert ranked_ids.index(matching_id) < ranked_ids.index(popular_unmatched_id)
    with SyncSessionLocal() as db:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        assert profile.recommendation_emotion == "焦虑"


def test_article_cache_invalidates_when_admin_unpublishes():
    headers = admin_headers()
    created = client.post(
        "/api/articles/",
        json={"title": "缓存失效测试文章", "author": "", "summary": "测试", "content": "用于验证文章缓存", "category": "工程测试", "status": "已发布"},
        headers=headers,
    )
    assert created.status_code == 200
    article_id = created.json()["id"]
    assert client.get(f"/api/articles/{article_id}").status_code == 200
    changed = client.patch(
        f"/api/admin/articles/{article_id}/status",
        json={"status": "草稿"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert client.get(f"/api/articles/{article_id}").status_code == 404


def test_chat_idempotency_returns_same_result_without_duplicate_messages():
    headers = auth_headers()
    conversation_id = f"idem-{uuid4().hex[:12]}"
    payload = {
        "conversation_id": conversation_id,
        "request_key": f"req-{uuid4().hex}",
        "message": "我最近考试压力很大，有点焦虑",
        "visibility": "私人",
    }
    first = client.post("/api/consult/chat", json=payload, headers=headers)
    second = client.post("/api/consult/chat", json=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    with SyncSessionLocal() as db:
        assert db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).count() == 2


def test_repeated_high_risk_messages_escalate_one_open_case():
    headers = auth_headers()
    conversation_id = f"case-{uuid4().hex[:12]}"
    for index in range(2):
        response = client.post(
            "/api/consult/chat",
            json={
                "conversation_id": conversation_id,
                "request_key": f"risk-{index}-{uuid4().hex}",
                "message": "我已经准备今晚就自杀",
                "visibility": "私人",
            },
            headers=headers,
        )
        assert response.status_code == 200
    with SyncSessionLocal() as db:
        events = db.query(RiskEvent).filter(RiskEvent.conversation_id == conversation_id).all()
        assert len(events) == 1
        assert events[0].due_at is not None
        actions = db.query(RiskAction).filter(RiskAction.risk_event_id == events[0].id).all()
        assert {action.action for action in actions} >= {"created", "signal_updated"}


def test_risk_case_workflow_has_optimistic_lock_audit_timeline_and_notification():
    student_headers = auth_headers()
    conversation_id = f"workflow-{uuid4().hex[:10]}"
    created = client.post(
        "/api/consult/chat",
        json={
            "conversation_id": conversation_id,
            "request_key": f"workflow-{uuid4().hex}",
            "message": "我已经准备今晚就自杀",
            "visibility": "私人",
        },
        headers=student_headers,
    )
    assert created.status_code == 200
    admin = admin_headers()
    event = next(item for item in client.get("/api/admin/risk-events?status=open", headers=admin).json() if item["conversation_id"] == conversation_id)

    assigned = client.patch(
        f"/api/admin/risk-events/{event['id']}",
        json={"status": "assigned", "expected_version": event["version"]},
        headers=admin,
    )
    assert assigned.status_code == 200
    stale = client.patch(
        f"/api/admin/risk-events/{event['id']}",
        json={"status": "contacted", "expected_version": event["version"]},
        headers=admin,
    )
    assert stale.status_code == 409

    refreshed = next(item for item in client.get("/api/admin/risk-events?status=open", headers=admin).json() if item["id"] == event["id"])
    contacted = client.patch(
        f"/api/admin/risk-events/{event['id']}",
        json={"status": "contacted", "expected_version": refreshed["version"], "note": "已完成首次支持联系"},
        headers=admin,
    )
    assert contacted.status_code == 200
    timeline = client.get(f"/api/admin/risk-events/{event['id']}/timeline", headers=admin)
    assert [item["action"] for item in timeline.json()] == ["created", "assigned", "contacted"]
    logs = client.get("/api/admin/audit-logs", headers=admin).json()
    assert any(item["action"] == "risk.contacted" and item["request_id"] for item in logs)
    notifications = client.get("/api/users/me/notifications", headers=student_headers).json()
    assert notifications["unread_count"] == 1
    notification_id = notifications["items"][0]["id"]
    assert client.patch(f"/api/users/me/notifications/{notification_id}/read", headers=student_headers).status_code == 200


def test_risk_case_rejects_invalid_state_jump():
    student_headers = auth_headers()
    conversation_id = f"invalid-{uuid4().hex[:10]}"
    client.post(
        "/api/consult/chat",
        json={"conversation_id": conversation_id, "message": "我已经准备今晚就自杀", "visibility": "私人"},
        headers=student_headers,
    )
    admin = admin_headers()
    event = next(item for item in client.get("/api/admin/risk-events?status=open", headers=admin).json() if item["conversation_id"] == conversation_id)
    with SyncSessionLocal() as db:
        audit_count_before = db.query(AdminAuditLog).filter(
            AdminAuditLog.target_id == str(event["id"]),
        ).count()
    response = client.patch(
        f"/api/admin/risk-events/{event['id']}",
        json={"status": "follow_up", "expected_version": event["version"], "next_follow_up_at": "2099-01-01T00:00:00"},
        headers=admin,
    )
    assert response.status_code == 422
    with SyncSessionLocal() as db:
        audit_count_after = db.query(AdminAuditLog).filter(
            AdminAuditLog.target_id == str(event["id"]),
        ).count()
        assert audit_count_after == audit_count_before
        assert db.query(UserNotification).filter(UserNotification.user_id == event["user_id"]).count() == 0


def test_community_media_upload_and_media_only_share():
    headers = auth_headers()
    rejected = client.post(
        "/api/discussions/media",
        files={"file": ("unsafe.txt", b"not media", "text/plain")},
        headers=headers,
    )
    assert rejected.status_code == 415

    uploaded = client.post(
        "/api/discussions/media",
        files={"file": ("moment.png", b"\x89PNG\r\n\x1a\ncommunity", "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    media = uploaded.json()
    assert media["media_type"] == "image"
    assert media["url"].startswith("/uploads/community/")

    created = client.post(
        "/api/discussions/",
        json={"title": "今天的一张照片", "category": "经验分享", "content": "", "visibility": "公开", "image_url": media["url"]},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["image_url"] == media["url"]
    assert client.get(media["url"]).status_code == 200

    upload_path = Path(media["url"].lstrip("/"))
    if upload_path.exists():
        upload_path.unlink()


def test_realtime_plaza_persists_messages_and_requires_login():
    payload = {"content": "刚刚完成了一次深呼吸，感觉平静了一点。"}
    assert client.post("/api/discussions/plaza", json=payload).status_code == 401

    created = client.post("/api/discussions/plaza", json=payload, headers=auth_headers())
    assert created.status_code == 200
    message = created.json()
    assert message["status"] == "published"
    assert message["author_name"].startswith("测试鉴权用户")
    assert message["created_at"]

    public_messages = client.get("/api/discussions/plaza").json()
    assert any(item["id"] == message["id"] and item["content"] == payload["content"] for item in public_messages)


def test_community_rejects_unmanaged_media_urls():
    response = client.post(
        "/api/discussions/plaza",
        json={"content": "外部媒体地址校验", "image_url": "https://example.com/image.png"},
        headers=auth_headers(),
    )
    assert response.status_code == 422


def test_profile_center_updates_media_contacts_and_password():
    headers = auth_headers()
    original = client.get("/api/users/me", headers=headers)
    assert original.status_code == 200
    assert {"email", "background_url", "signature"} <= set(original.json())

    nickname = f"资料用户{uuid4().hex[:6]}"
    updated = client.patch(
        "/api/users/me",
        json={"nickname": nickname, "signature": "认真生活，也允许自己偶尔休息。"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["nickname"] == nickname
    assert updated.json()["signature"].startswith("认真生活")

    fake_image = client.post(
        "/api/users/me/media?kind=avatar",
        files={"file": ("fake.png", b"not-a-real-image", "image/png")},
        headers=headers,
    )
    assert fake_image.status_code == 422
    avatar = client.post(
        "/api/users/me/media?kind=avatar",
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\nprofile-image", "image/png")},
        headers=headers,
    )
    assert avatar.status_code == 200
    avatar_url = avatar.json()["url"]
    assert avatar_url.startswith("/uploads/profile/")
    assert client.get(avatar_url).status_code == 200

    new_phone = f"138{uuid4().int % 100_000_000:08d}"
    sms = client.post("/api/auth/send-code", json={"phone": new_phone})
    assert sms.status_code == 200
    wrong_phone_password = client.post(
        "/api/users/me/phone",
        json={"new_phone": new_phone, "code": sms.json()["dev_code"], "current_password": "wrong-password"},
        headers=headers,
    )
    assert wrong_phone_password.status_code == 400
    changed_phone = client.post(
        "/api/users/me/phone",
        json={"new_phone": new_phone, "code": sms.json()["dev_code"], "current_password": "123456"},
        headers=headers,
    )
    assert changed_phone.status_code == 200
    assert changed_phone.json()["phone"] == new_phone

    email = f"student-{uuid4().hex[:8]}@example.com"
    email_code = client.post(
        "/api/users/me/email-code",
        json={"email": email, "current_password": "123456"},
        headers=headers,
    )
    assert email_code.status_code == 200
    bound_email = client.post(
        "/api/users/me/email",
        json={"email": email, "code": email_code.json()["dev_code"], "current_password": "123456"},
        headers=headers,
    )
    assert bound_email.status_code == 200
    assert bound_email.json()["email"] == email

    wrong_password = client.post(
        "/api/users/me/password",
        json={"current_password": "bad-password", "new_password": "87654321"},
        headers=headers,
    )
    assert wrong_password.status_code == 400
    changed_password = client.post(
        "/api/users/me/password",
        json={"current_password": "123456", "new_password": "87654321"},
        headers=headers,
    )
    assert changed_password.status_code == 200
    relogin = client.post("/api/auth/login", json={"nickname": nickname, "password": "87654321"})
    assert relogin.status_code == 200

    avatar_path = Path(avatar_url.lstrip("/"))
    if avatar_path.exists():
        avatar_path.unlink()
