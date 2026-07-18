import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.article_crawler import crawl_articles
from database.database import SyncSessionLocal, init_db


def main() -> None:
    init_db()
    with SyncSessionLocal() as db:
        result = crawl_articles(db)
    print(
        f"采集完成：栏目发现 {result['discovered']}，目标 {result['total_targets']}，"
        f"新增 {result['created']}，更新 {result['updated']}，失败 {len(result['failed'])}"
    )
    for failure in result["failed"]:
        print(f"- {failure['url']}: {failure['error']}")


if __name__ == "__main__":
    main()
