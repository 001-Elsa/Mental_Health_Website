from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database.database import get_sync_db
from database.models import Article, Comment, User
from backend.auth import get_current_user, require_admin
from backend.services import article_service
from backend.services.content_search import period_start
from backend.services.audit import record_audit
from backend.services.cache import cache_service
from backend.schemas import (
    ArticleCreate, ArticleOut,
    CommentCreate, CommentOut,
    DownloadOut,
)

router = APIRouter(prefix="/api/articles", tags=["知识文章"])


# ==================== 分类 ====================
@router.get("/categories")
def list_categories(db: Session = Depends(get_sync_db)):
    cached = cache_service.get_json("articles:categories")
    if cached is not None:
        return cached
    rows = db.query(Article.category).filter(
        Article.status == "已发布"
    ).distinct().order_by(Article.category).all()
    result = [r[0] for r in rows if r[0]]
    cache_service.set_json("articles:categories", result, 300)
    return result


# ==================== 文章 CRUD ====================
@router.get("/", response_model=list[ArticleOut])
def list_articles(
    title: str = Query(default=""),
    category: str = Query(default=""),
    period: str = Query(default="all"),
    status: str = Query(default=""),
    db: Session = Depends(get_sync_db),
):
    return article_service.list_public(
        db,
        title=title.strip(),
        category=category,
        published_since=period_start(period),
    )


@router.get("/popular", response_model=list[ArticleOut])
def list_popular_articles(
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_sync_db),
):
    return article_service.popular(db, limit)


@router.get("/{aid}", response_model=ArticleOut)
def get_article(aid: int, db: Session = Depends(get_sync_db)):
    obj = article_service.get_public(db, aid)
    if not obj:
        raise HTTPException(status_code=404, detail="文章不存在")
    return obj


@router.post("/", response_model=ArticleOut)
def create_article(
    payload: ArticleCreate,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    data = payload.model_dump()
    data["author"] = data.get("author") or current_user.nickname
    article = Article(**data)
    db.add(article)
    db.flush()
    record_audit(
        db,
        actor_id=current_user.id,
        action="article.create",
        target_type="article",
        target_id=article.id,
        detail={"title": article.title, "status": article.status},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    db.refresh(article)
    article_service.invalidate_articles()
    return article


@router.patch("/{aid}", response_model=ArticleOut)
def update_article(
    aid: int,
    payload: ArticleCreate,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    obj = db.query(Article).filter(Article.id == aid).first()
    if not obj:
        raise HTTPException(status_code=404, detail="文章不存在")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    record_audit(
        db,
        actor_id=current_user.id,
        action="article.update",
        target_type="article",
        target_id=aid,
        detail={"title": obj.title, "status": obj.status},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    db.refresh(obj)
    article_service.invalidate_articles()
    return obj


@router.delete("/{aid}")
def delete_article(
    aid: int,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    obj = db.query(Article).filter(Article.id == aid).first()
    if not obj:
        raise HTTPException(status_code=404, detail="文章不存在")
    detail = {"title": obj.title, "status": obj.status}
    db.delete(obj)
    record_audit(
        db,
        actor_id=current_user.id,
        action="article.delete",
        target_type="article",
        target_id=aid,
        detail=detail,
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    article_service.invalidate_articles()
    return {"ok": True}


# ==================== 阅读计数 ====================
@router.post("/{aid}/view")
def increment_view(aid: int, db: Session = Depends(get_sync_db)):
    obj = db.query(Article).filter(Article.id == aid, Article.status == "已发布").first()
    if not obj:
        raise HTTPException(status_code=404, detail="文章不存在")
    obj.read_count = (obj.read_count or 0) + 1
    db.commit()
    article_service.invalidate_articles()
    return {"read_count": obj.read_count}


# ==================== 下载 ====================
@router.get("/{aid}/download")
def download_article(aid: int, db: Session = Depends(get_sync_db)):
    obj = db.query(Article).filter(Article.id == aid, Article.status == "已发布").first()
    if not obj:
        raise HTTPException(status_code=404, detail="文章不存在")
    text = f"{obj.title}\n作者: {obj.author}\n分类: {obj.category}\n\n{obj.content}"
    return PlainTextResponse(content=text, headers={
        "Content-Disposition": f"attachment; filename={obj.title}.txt"
    })


# ==================== 留言 ====================
@router.get("/{aid}/comments", response_model=list[CommentOut])
def list_comments(aid: int, db: Session = Depends(get_sync_db)):
    if not db.query(Article.id).filter(Article.id == aid, Article.status == "已发布").first():
        raise HTTPException(status_code=404, detail="文章不存在")
    return db.query(Comment).filter(Comment.article_id == aid).order_by(Comment.created_at.desc()).all()


@router.post("/{aid}/comments", response_model=CommentOut)
def add_comment(
    aid: int,
    payload: CommentCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    if not db.query(Article.id).filter(Article.id == aid, Article.status == "已发布").first():
        raise HTTPException(status_code=404, detail="文章不存在")
    comment = Comment(article_id=aid, user_id=current_user.id, content=payload.content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{aid}/comments/{cid}")
def delete_comment(
    aid: int,
    cid: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(Comment).filter(Comment.id == cid, Comment.article_id == aid).first()
    if not obj:
        raise HTTPException(status_code=404, detail="评论不存在")
    if obj.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除该评论")
    db.delete(obj)
    db.commit()
    return {"ok": True}
