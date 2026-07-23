"""Keep backend-only test environments independent of browser tooling."""

from importlib.util import find_spec
import os
from pathlib import Path


if not os.environ.get("DATABASE_URL"):
    test_db = Path("test_mental_health.db").absolute()
    if test_db.exists():
        test_db.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-only-secret")
os.environ.setdefault("DEEPSEEK_API_KEY", "")


collect_ignore = ["tests/e2e"] if find_spec("playwright") is None else []
