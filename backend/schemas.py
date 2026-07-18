from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ====== User ======
class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    phone: str
    email: str = ""
    avatar_url: str
    background_url: str = ""
    signature: str = ""
    role: str = "student"
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== MoodLog ======
class MoodLogCreate(BaseModel):
    user_id: int = 1
    score: float = Field(ge=1, le=10)
    trigger: str = ""
    note: str = ""
    visibility: str = "公开"


class MoodLogOut(BaseModel):
    id: int
    user_id: int
    score: float
    trigger: str
    note: str
    visibility: str
    bookmark_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== Consultation ======
class PublicConversationOut(BaseModel):
    id: int
    title: str
    summary: str
    emotion_tag: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== Article ======
class ArticleCreate(BaseModel):
    title: str
    author: str = ""
    summary: str = ""
    cover_image: str = ""
    content: str = ""
    category: str = ""
    status: str = "已发布"
    source_name: str = "平台原创"
    source_url: str = ""
    published_at: datetime | None = None


class ArticleOut(BaseModel):
    id: int
    title: str
    author: str
    summary: str
    cover_image: str
    content: str
    category: str
    status: str
    source_name: str
    source_url: str
    published_at: datetime | None
    read_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== 数据分析 ======
class AnalyticsOverview(BaseModel):
    total_users: int
    total_mood_logs: int
    total_consultations: int
    avg_mood_score: float


class TrendPoint(BaseModel):
    date: str  # "YYYY-MM-DD"
    avg_score: Optional[float] = None
    count: int = 0
    user_count: int = 0


class ActivityPoint(BaseModel):
    date: str  # "YYYY-MM-DD"
    active_users: int = 0
    new_users: int = 0
    diary_users: int = 0
    consultation_users: int = 0


# ====== Discussion ======
class DiscussionCreate(BaseModel):
    title: str = Field(min_length=4, max_length=80)
    content: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=512)
    audio_url: str = Field(default="", max_length=512)
    category: str = Field(default="", max_length=64)
    visibility: str = Field(default="公开", pattern=r"^(公开|私人)$")
    user_id: int = 1

    @model_validator(mode="after")
    def require_content_or_media(self):
        if not self.content.strip() and not self.image_url and not self.audio_url:
            raise ValueError("正文、图片或语音至少填写一项")
        return self


class DiscussionOut(BaseModel):
    id: int
    user_id: int
    title: str
    content: str
    image_url: str = ""
    audio_url: str = ""
    category: str
    reply_count: int
    view_count: int
    like_count: int = 0
    status: str = "published"
    moderation_reason: str = ""
    visibility: str = "公开"
    created_at: datetime

    model_config = {"from_attributes": True}


class PlazaMessageCreate(BaseModel):
    content: str = Field(default="", max_length=1000)
    image_url: str = Field(default="", max_length=512)
    audio_url: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def require_content_or_media(self):
        if not self.content.strip() and not self.image_url and not self.audio_url:
            raise ValueError("文字、图片或语音至少发送一项")
        return self


class PlazaMessageOut(BaseModel):
    id: int
    user_id: int
    author_name: str
    content: str
    image_url: str = ""
    audio_url: str = ""
    status: str
    created_at: datetime


# ====== Comment ======
class CommentCreate(BaseModel):
    article_id: int
    content: str
    user_id: int = 1


class CommentOut(BaseModel):
    id: int
    article_id: int
    user_id: int
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== Reply ======
class ReplyCreate(BaseModel):
    discussion_id: int
    content: str
    user_id: int = 1


class ReplyOut(BaseModel):
    id: int
    discussion_id: int
    user_id: int
    content: str
    status: str = "published"
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== Download ======
class DownloadOut(BaseModel):
    title: str
    content: str
