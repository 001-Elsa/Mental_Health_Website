from datetime import datetime

from sqlalchemy.orm import Session

from backend.repositories import articles
from backend.services.cache import cache_service
from database.models import Article


def _serialize(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "author": article.author,
        "summary": article.summary,
        "cover_image": article.cover_image,
        "content": article.content,
        "category": article.category,
        "status": article.status,
        "source_name": article.source_name,
        "source_url": article.source_url,
        "published_at": article.published_at.isoformat() if isinstance(article.published_at, datetime) else None,
        "read_count": article.read_count,
        "created_at": article.created_at.isoformat() if isinstance(article.created_at, datetime) else str(article.created_at),
    }


def list_public(db: Session, *, title: str = "", category: str = "", published_since: datetime | None = None) -> list[dict]:
    since_key = published_since.date().isoformat() if published_since else "all"
    cache_key = f"articles:list:{title}:{category}:{since_key}"
    cached = cache_service.get_json(cache_key)
    if cached is not None:
        return cached
    rows = articles.search_articles(
        db,
        title=title,
        category=category,
        status="已发布",
        published_since=published_since,
    )
    result = [_serialize(row) for row in rows]
    cache_service.set_json(cache_key, result, ttl_seconds=120)
    return result


def get_public(db: Session, article_id: int) -> dict | None:
    cache_key = f"articles:detail:{article_id}"
    cached = cache_service.get_json(cache_key)
    if cached is not None:
        return cached
    article = articles.get_article(db, article_id)
    if not article or article.status != "已发布":
        return None
    result = _serialize(article)
    cache_service.set_json(cache_key, result, ttl_seconds=180)
    return result


def popular(db: Session, limit: int = 10) -> list[dict]:
    cache_key = f"articles:popular:{limit}"
    cached = cache_service.get_json(cache_key)
    if cached is not None:
        return cached
    result = [_serialize(row) for row in articles.popular_articles(db, limit)]
    cache_service.set_json(cache_key, result, ttl_seconds=120)
    return result


def invalidate_articles() -> None:
    cache_service.delete_prefix("articles:")
