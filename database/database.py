from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.core.config import get_settings

SQLALCHEMY_DATABASE_URL = get_settings().database_url

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
sync_engine = create_engine(
    SQLALCHEMY_DATABASE_URL.replace("+aiosqlite", ""),
    connect_args=connect_args,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def _async_database_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite:"):
        return url
    if url.startswith("sqlite:"):
        return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    if url.startswith("postgresql+psycopg2:"):
        return url.replace("postgresql+psycopg2:", "postgresql+asyncpg:", 1)
    if url.startswith("postgresql:"):
        return url.replace("postgresql:", "postgresql+asyncpg:", 1)
    return url


async_engine = create_async_engine(
    _async_database_url(SQLALCHEMY_DATABASE_URL),
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create tables and safely upgrade legacy SQLite databases in development."""
    Base.metadata.create_all(bind=sync_engine)
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        _upgrade_legacy_sqlite()


def _upgrade_legacy_sqlite() -> None:
    additions = {
        "users": {
            "role": "VARCHAR(16) NOT NULL DEFAULT 'student'",
            "email": "VARCHAR(254) NULL",
            "background_url": "VARCHAR(512) NOT NULL DEFAULT ''",
            "signature": "VARCHAR(120) NOT NULL DEFAULT ''",
            "updated_at": "DATETIME NULL",
            "token_version": "INTEGER NOT NULL DEFAULT 0",
        },
        "consultations": {
            "memory_summary": "TEXT NOT NULL DEFAULT ''",
            "message_count": "INTEGER NOT NULL DEFAULT 0",
            "risk_level": "VARCHAR(16) NOT NULL DEFAULT 'low'",
            "risk_score": "INTEGER NOT NULL DEFAULT 0",
            "risk_reason": "TEXT NOT NULL DEFAULT ''",
            "intervention_status": "VARCHAR(24) NOT NULL DEFAULT 'none'",
            "last_message_at": "DATETIME NULL",
        },
        "discussions": {
            "like_count": "INTEGER NOT NULL DEFAULT 0",
            "status": "VARCHAR(24) NOT NULL DEFAULT 'published'",
            "moderation_reason": "VARCHAR(256) NOT NULL DEFAULT ''",
            "visibility": "VARCHAR(16) NOT NULL DEFAULT '公开'",
            "image_url": "VARCHAR(512) NOT NULL DEFAULT ''",
            "audio_url": "VARCHAR(512) NOT NULL DEFAULT ''",
        },
        "articles": {
            "source_name": "VARCHAR(128) NOT NULL DEFAULT '平台原创'",
            "source_url": "VARCHAR(1024) NOT NULL DEFAULT ''",
            "published_at": "DATETIME NULL",
        },
        "user_profiles": {
            "recommendation_emotion": "VARCHAR(32) NOT NULL DEFAULT ''",
        },
        "replies": {"status": "VARCHAR(24) NOT NULL DEFAULT 'published'"},
        "risk_events": {
            "event_type": "VARCHAR(24) NOT NULL DEFAULT 'conversation'",
            "model_level": "VARCHAR(16) NOT NULL DEFAULT ''",
            "model_reason": "VARCHAR(512) NOT NULL DEFAULT ''",
            "assigned_to": "INTEGER NULL",
            "due_at": "DATETIME NULL",
            "next_follow_up_at": "DATETIME NULL",
            "version": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    inspector = inspect(sync_engine)
    tables = set(inspector.get_table_names())
    with sync_engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    async with AsyncSessionLocal() as db:
        yield db
