"""插入测试数据"""

from datetime import datetime, timedelta
from database.database import init_db, SyncSessionLocal
from database.models import (
    User, MoodLog, Consultation, Article, Discussion, Bookmark, ChatMessage,
    Comment, Reply, Report, RiskEvent, SensitiveWord, KnowledgeDocument,
    AdminAuditLog, DiscussionLike, Exercise, IdempotencyRecord, RiskAction,
    UserNotification, UserProfile,
)
from backend.auth import hash_password

init_db()
db = SyncSessionLocal()

# 清空旧数据
db.query(Bookmark).delete()
db.query(Report).delete()
db.query(RiskAction).delete()
db.query(RiskEvent).delete()
db.query(AdminAuditLog).delete()
db.query(IdempotencyRecord).delete()
db.query(UserNotification).delete()
db.query(SensitiveWord).delete()
db.query(KnowledgeDocument).delete()
db.query(DiscussionLike).delete()
db.query(Exercise).delete()
db.query(UserProfile).delete()
db.query(Comment).delete()
db.query(Reply).delete()
db.query(ChatMessage).delete()
db.query(Discussion).delete()
db.query(MoodLog).delete()
db.query(Consultation).delete()
db.query(Article).delete()
db.query(User).delete()
db.commit()

today = datetime.utcnow().date()

# ====== 用户（密码统一为 123456） ======
users = [
    User(username="user1", nickname="测试用户1", phone="13800000001", password_hash=hash_password("123456"), created_at=datetime(today.year, today.month, today.day, 10, 0, 0)),
    User(username="user2", nickname="测试用户2", phone="13800000002", password_hash=hash_password("123456"), created_at=datetime(today.year, today.month, today.day, 10, 0, 0)),
    User(username="admin", nickname="平台管理员", phone="13800000000", password_hash=hash_password("admin123"), role="admin", created_at=datetime(today.year, today.month, today.day, 9, 0, 0)),
]
db.add_all(users)
db.flush()
db.add(UserProfile(
    user_id=users[0].id,
    summary="近期主要情绪为焦虑；压力来源集中在学习与考试、睡眠；更容易接受任务拆分类支持。",
    dominant_emotions="焦虑、平静",
    stressors="学习与考试、睡眠",
    coping_preferences="任务拆分",
))

# ====== 情绪日志（分散在10天，供图表展示） ======
mood_data = [
    (8.5, "工作完成", "今天顺利完成了项目，心情很好。", "公开"),
    (7.0, "运动放松", "跑完步感觉很舒服，情绪平稳。", "公开"),
    (6.5, "人际矛盾", "和朋友发生了争执，有些难过。", "私人"),
    (9.0, "收到礼物", "朋友寄来了生日礼物，非常开心！", "公开"),
    (5.5, "睡眠不足", "昨晚失眠，一整天提不起精神。", "公开"),
    (7.5, "天气晴朗", "阳光很好，中午出去散了步。", "公开"),
    (6.0, "工作压力", "项目截止日期临近，有些焦虑。", "公开"),
    (8.0, "家庭聚会", "和家人一起吃饭，感觉很温暖。", "私人"),
    (7.8, "阅读放松", "读了本好书，心情平静了许多。", "公开"),
    (6.8, "意外事件", "电脑突然坏了，有点烦躁。", "公开"),
]
mood_logs = []
for i, (score, trigger, note, vis) in enumerate(mood_data):
    d = today - timedelta(days=9 - i)
    mood_logs.append(
        MoodLog(
            user_id=users[i % 2].id,
            score=score,
            trigger=trigger,
            note=note,
            visibility=vis,
            bookmark_count=(i * 3) % 10,
            created_at=datetime(d.year, d.month, d.day, 10 + i, 0, 0),
        )
    )
db.add_all(mood_logs)

# ====== 咨询记录（分散在几天） ======
d1, d2 = today - timedelta(days=3), today - timedelta(days=7)
consultations = [
    Consultation(user_id=users[0].id, conversation_id="demo-safe-chat", title="期末周压力", summary="讨论了期末复习和睡眠安排。", emotion_tag="焦虑", pinned=True, risk_level="medium", risk_score=30, created_at=datetime(today.year, today.month, today.day, 10, 0, 0)),
    Consultation(user_id=users[1].id, conversation_id="demo-risk-chat", title="持续低落与失眠", summary="用户表达了强烈绝望感，需要人工跟进。", emotion_tag="低落", pinned=False, risk_level="high", risk_score=65, intervention_status="pending", risk_reason="强烈绝望感、持续低落", created_at=datetime(d1.year, d1.month, d1.day, 11, 0, 0)),
    Consultation(user_id=users[0].id, title="人际关系复盘", summary="梳理了室友沟通中的边界问题。", emotion_tag="烦躁", pinned=False, created_at=datetime(d2.year, d2.month, d2.day, 15, 0, 0)),
]
db.add_all(consultations)
db.flush()
demo_risk = RiskEvent(
    user_id=users[1].id,
    consultation_id=consultations[1].id,
    conversation_id="demo-risk-chat",
    level="high",
    score=65,
    signals="强烈绝望感、持续低落",
    excerpt="最近每天都很痛苦，感觉没有希望，也不知道该找谁说。",
    due_at=datetime.utcnow() + timedelta(hours=2),
)
db.add(demo_risk)
db.flush()
db.add(RiskAction(
    risk_event_id=demo_risk.id,
    action="created",
    from_status="",
    to_status="pending",
    note="强烈绝望感、持续低落",
))
db.add(UserNotification(
    user_id=users[0].id,
    notification_type="support",
    title="欢迎使用心晴 Campus",
    content="你可以从情绪记录开始，也可以随时进入 AI 倾听。平台不会用这些信息提供医疗诊断。",
    link="/dashboard",
))

# ====== 知识文章 ======
articles = [
    Article(title="期末周焦虑：把失控感拆成三个可行动步骤", author="校心理中心", summary="从任务拆分、身体放松和求助计划入手，降低期末周的持续紧绷。", content="当事情同时涌来时，大脑会把它们理解成一个无法解决的整体。先写下今天必须完成的一件事，再给自己安排十分钟的身体活动，最后确定一个可以联系的人。小而具体的行动会重新建立掌控感。", category="焦虑缓解", status="已发布", read_count=426),
    Article(title="睡不着时，先别急着强迫自己入睡", author="睡眠健康研究组", summary="理解睡眠压力如何形成，并用更温和的方法打断越想睡越清醒的循环。", content="如果躺下二十分钟仍然清醒，可以离开床铺，到光线较暗的地方做安静、重复的事情。困意出现后再回到床上。固定起床时间比提前上床更能帮助生物钟稳定。", category="睡眠", status="已发布", read_count=681),
    Article(title="和室友谈边界，不必等到忍无可忍", author="朋辈辅导中心", summary="用事实、感受和具体请求组织一次不攻击对方的沟通。", content="选择双方情绪平稳的时间，描述可观察到的事实，再说它对你的影响，最后提出一个可以执行的请求。边界不是控制别人，而是说明你愿意如何参与一段关系。", category="人际关系", status="已发布", read_count=318),
    Article(title="心理危机支持资源清单", author="平台运营组", summary="整理校内外求助渠道与紧急情况下的行动顺序。", content="紧急情况下，请优先联系身边可信任的人陪伴，并拨打 120 或 110。非紧急但持续困扰时，可以预约学校心理中心或所在地正规医疗机构。", category="心理科普", status="草稿", read_count=50),
]
db.add_all(articles)

# ====== 社区讨论 ======
discussions = [
    Discussion(user_id=users[0].id, title="期末周如何让自己按时吃饭？", content="忙起来就会忘记吃饭，最近尝试和室友约固定饭点，感觉比单独设闹钟有效。大家还有什么办法？", category="学习压力", reply_count=0, view_count=108, like_count=16),
    Discussion(user_id=users[1].id, title="第一次预约学校心理中心的经历", content="流程比想象中简单，老师先听我讲最近的状态，没有急着给结论。把这段经历分享给还在犹豫的同学。", category="经验分享", reply_count=0, view_count=246, like_count=38),
]
db.add_all(discussions)

db.add_all([
    SensitiveWord(word="加微信", category="privacy"),
    SensitiveWord(word="代考", category="illegal"),
])

db.add_all([
    Exercise(
        title="5-4-3-2-1 感官定位",
        category="焦虑缓解",
        description="把注意力带回当下，适合焦虑明显或脑中反复预演时。",
        steps="依次说出看到的5样东西、触碰到的4样东西、听到的3种声音、闻到的2种气味和感受到的1种味道。",
        duration_minutes=5,
    ),
    Exercise(
        title="十分钟任务启动",
        category="行为激活",
        description="把困难任务缩小到十分钟可以完成的一步。",
        steps="选择一件最小任务，设置10分钟计时，只承诺做到计时结束，再决定是否继续。",
        duration_minutes=10,
    ),
    Exercise(
        title="方形呼吸",
        category="正念",
        description="用稳定节奏帮助身体从紧绷状态慢下来。",
        steps="吸气4秒、停4秒、呼气4秒、停4秒，重复4轮；头晕时恢复自然呼吸。",
        duration_minutes=3,
    ),
    Exercise(
        title="给朋友的一封短信",
        category="自我关怀",
        description="用对待朋友的语气回应自己的低落和自责。",
        steps="写下发生了什么、你此刻的感受，以及如果朋友经历同样事情你会对他说什么。",
        duration_minutes=8,
    ),
])

db.add_all([
    KnowledgeDocument(
        title="高校学生心理危机识别与转介要点",
        source="高校心理中心内部科普资料",
        category="危机支持",
        content="当学生明确表达自伤或自杀意图、具体方式、时间计划时，应优先确认其当下安全，联系可信任的陪伴者，并尽快转介学校心理中心、正规医疗机构或紧急服务。不要承诺保密，也不要仅依赖线上聊天。",
    ),
    KnowledgeDocument(
        title="焦虑状态下的短时稳定技巧",
        source="校心理中心学生手册",
        category="焦虑缓解",
        content="焦虑强烈时，可以先做缓慢呼吸和感官定位：说出看到的五样东西、触碰到的四样东西、听到的三种声音。随后把任务缩小到十分钟内可以完成的一步。若焦虑持续影响学习和睡眠，建议预约专业咨询。",
    ),
    KnowledgeDocument(
        title="大学生睡眠自助建议",
        source="睡眠健康教育资料",
        category="睡眠",
        content="保持固定起床时间，减少睡前长时间刷屏和咖啡因摄入。躺下较长时间仍清醒时，可暂时离床做安静活动，困倦后再回床。若失眠持续数周并显著影响日间功能，应寻求正规医疗评估。",
    ),
])

db.commit()
db.close()

print("测试数据插入完成！")
print(f"  用户: {len(users)} 条")
print(f"  情绪日志: {len(mood_logs)} 条")
print(f"  咨询记录: {len(consultations)} 条")
print(f"  知识文章: {len(articles)} 条")
print(f"  社区讨论: {len(discussions)} 条")
