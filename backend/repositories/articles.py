from datetime import datetime

from sqlalchemy import case
from sqlalchemy.orm import Session

from database.models import Article


def get_article(db: Session, article_id: int) -> Article | None:
    return db.query(Article).filter(Article.id == article_id).first()


def search_articles(
    db: Session,
    *,
    title: str = "",
    category: str = "",
    status: str = "",
    published_since: datetime | None = None,
) -> list[Article]:
    query = db.query(Article)
    if title:
        query = query.filter(Article.title.contains(title))
    if category:
        query = query.filter(Article.category == category)
    if status:
        query = query.filter(Article.status == status)
    publication_time = case(
        (Article.source_url != "", Article.published_at),
        else_=Article.created_at,
    )
    if published_since is not None:
        query = query.filter(publication_time >= published_since)
    return query.order_by(publication_time.desc()).all()


def popular_articles(db: Session, limit: int = 10) -> list[Article]:
    return db.query(Article).filter(
        Article.status == "已发布"
    ).order_by(Article.read_count.desc(), Article.created_at.desc()).limit(limit).all()
