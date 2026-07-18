import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from backend.services import article_service
from database.models import Article


@dataclass(frozen=True)
class CrawlTarget:
    url: str
    category: str


@dataclass(frozen=True)
class CrawlSource:
    url: str
    category: str
    include_pattern: str
    limit: int = 50


DEFAULT_TARGETS = (
    CrawlTarget("https://www.zhihu.com/question/58915510/answer/3045876619", "焦虑缓解"),
    CrawlTarget("https://www.zhihu.com/question/504516772/answer/1967165396151928234", "心理科普"),
    CrawlTarget("https://zhuanlan.zhihu.com/p/1981329512047321929", "睡眠与精力"),
    CrawlTarget("https://www.zhihu.com/question/650416617/answer/122857212755", "求职压力"),
    CrawlTarget("https://www.uwh.edu.cn/xljk/detail/1140/18395.html", "学业压力"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/260526/2034423.shtml", "毕业适应"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/250319/1984335.shtml", "正念练习"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyz_xlzs/231221/1863570.shtml", "焦虑缓解"),
    CrawlTarget("https://www.fjwzy.cn/xinli/info/1062/2835.htm", "学业压力"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyz_sdhy/230407/1832518.shtml", "焦虑缓解"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyz_xlzs/231225/1871573.shtml", "学业压力"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyz_xlzs/221220/1819128.shtml", "心理科普"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyz_xlzs/240621/1889637.shtml", "自我关怀"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/fdy_bjtj_yrjy/210524/1694565.shtml", "毕业适应"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/240223/1860956.shtml", "成长适应"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/230905/1858318.shtml", "心理科普"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/230418/1834625.shtml", "情绪调节"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/230823/1856705.shtml", "新生适应"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/240401/1881630.shtml", "心理科普"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/230906/1843817.shtml", "学业压力"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/240628/1888799.shtml", "心理科普"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/240712/1885530.shtml", "心理科普"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/250709/2012409.shtml", "情绪调节"),
    CrawlTarget("https://dxs.moe.gov.cn/zx/a/xl_xlyr_xlyral/260611/2004527.shtml", "成长适应"),
    CrawlTarget("https://xxgk.huayu.edu.cn/info/1002/1175.htm", "新生适应"),
    CrawlTarget("https://xljk.zut.edu.cn/info/1085/1287.htm", "心理科普"),
)

DEFAULT_SOURCES = (
    CrawlSource("https://www.uwh.edu.cn/xljk/article/1139.html", "心理科普", r"/xljk/detail/1139/\d+\.html$"),
    CrawlSource("https://www.uwh.edu.cn/xljk/article/1140.html", "心理科普", r"/xljk/detail/1140/\d+\.html$"),
    CrawlSource("https://www.uwh.edu.cn/xljk/article/1140.html?page=2", "心理科普", r"/xljk/detail/1140/\d+\.html$"),
    CrawlSource("https://www.hnpi.edu.cn/xljk/993/list.htm", "心理科普", r"/xljk/\d{4}/\d{4}/c993a\d+/page\.htm$"),
    CrawlSource("https://xinli.univs.cn/pbjy/", "心理科普", r"/a/pbjy_[^/]+/\d+/\d+\.shtml$"),
)

SOURCE_NAMES = {
    "zhihu.com": "知乎",
    "uwh.edu.cn": "芜湖学院心理健康教育服务中心",
    "dxs.moe.gov.cn": "中国大学生在线",
    "fjwzy.cn": "福建卫生职业技术学院心理健康教育中心",
    "hnpi.edu.cn": "湖南汽车工程职业大学心理健康教育中心",
    "xinli.univs.cn": "中国大学生在线·阳光心理",
    "zut.edu.cn": "中原工学院大学生心理健康中心",
    "huayu.edu.cn": "山东华宇工学院心理健康教育中心",
}

CATEGORY_KEYWORDS = (
    ("睡眠与精力", ("睡眠", "失眠", "早起", "疲惫", "精力")),
    ("焦虑缓解", ("焦虑", "紧张", "恐慌")),
    ("学业压力", ("考试", "学习", "学业", "拖延", "考研")),
    ("人际关系", ("人际", "宿舍", "沟通", "社交", "边界", "拒绝")),
    ("情绪调节", ("情绪", "抑郁", "内耗", "反刍", "烦躁", "低落")),
    ("新生适应", ("新生", "适应", "开学")),
    ("毕业适应", ("毕业", "就业", "求职", "未来")),
    ("自我关怀", ("自我", "悦己", "关怀", "接纳", "成长")),
)


def _clean(value: str, limit: int = 512) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _meta(soup: BeautifulSoup, *selectors: tuple[str, str]) -> str:
    for attribute, value in selectors:
        tag = soup.find("meta", attrs={attribute: value})
        if tag and tag.get("content"):
            return _clean(str(tag["content"]), 1024)
    return ""


def _json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        values = value if isinstance(value, list) else [value]
        rows.extend(item for item in values if isinstance(item, dict))
    return rows


def _parse_datetime(value: str) -> datetime | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        match = re.search(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", clean)
        if match:
            return datetime(*(int(part) for part in match.groups()))
    return None


def _source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, name in SOURCE_NAMES.items():
        if host == domain or host.endswith(f".{domain}"):
            return name
    return host or "公开网络来源"


def _canonical_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "", ""))


def _category_for_title(title: str, fallback: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in title for keyword in keywords):
            return category
    return fallback


def discover_targets_from_html(source: CrawlSource, html: str, *, base_url: str | None = None) -> list[CrawlTarget]:
    soup = BeautifulSoup(html, "html.parser")
    source_host = urlparse(source.url).netloc.lower()
    discovered: list[CrawlTarget] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        url = _canonical_url(urljoin(base_url or source.url, str(link["href"])))
        if url in seen or urlparse(url).netloc.lower() != source_host:
            continue
        if not re.search(source.include_pattern, urlparse(url).path):
            continue
        title = _clean(link.get_text(" "), 160)
        seen.add(url)
        discovered.append(CrawlTarget(url, _category_for_title(title, source.category)))
        if len(discovered) >= source.limit:
            break
    return discovered


def discover_targets(http_client: httpx.Client, sources: Iterable[CrawlSource]) -> tuple[list[CrawlTarget], list[dict[str, str]]]:
    targets: list[CrawlTarget] = []
    failures: list[dict[str, str]] = []
    for source in sources:
        try:
            response = http_client.get(source.url)
            response.raise_for_status()
            targets.extend(discover_targets_from_html(source, response.text, base_url=str(response.url)))
        except Exception as exc:
            failures.append({"url": source.url, "error": _clean(f"栏目发现失败：{exc}", 180)})
    return targets, failures


def parse_article_html(target: CrawlTarget, html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    structured = _json_ld(soup)
    title = _meta(soup, ("property", "og:title"), ("name", "twitter:title"))
    if not title and soup.title:
        title = _clean(soup.title.get_text(" "), 256)
    if not title:
        heading = soup.find("h1")
        title = _clean(heading.get_text(" ") if heading else "", 256)

    summary = _meta(soup, ("property", "og:description"), ("name", "description"), ("name", "twitter:description"))
    if not summary:
        paragraph = next((p for p in soup.find_all("p") if len(_clean(p.get_text(" "))) >= 40), None)
        summary = _clean(paragraph.get_text(" ") if paragraph else "")

    author = _meta(soup, ("name", "author"), ("property", "article:author"))
    published_value = _meta(soup, ("property", "article:published_time"), ("name", "publishdate"))
    cover_image = _meta(soup, ("property", "og:image"), ("name", "twitter:image"))
    for row in structured:
        if not author:
            raw_author = row.get("author")
            if isinstance(raw_author, dict):
                author = _clean(str(raw_author.get("name", "")), 64)
            elif isinstance(raw_author, list) and raw_author and isinstance(raw_author[0], dict):
                author = _clean(str(raw_author[0].get("name", "")), 64)
        if not published_value and row.get("datePublished"):
            published_value = str(row["datePublished"])
        if not summary and row.get("description"):
            summary = _clean(str(row["description"]))

    if not published_value:
        date_tag = soup.find(attrs={"itemprop": "datePublished"}) or soup.find("time", attrs={"datetime": True})
        if date_tag:
            published_value = str(date_tag.get("content") or date_tag.get("datetime") or date_tag.get_text(" "))
    if not published_value:
        published_value = soup.get_text(" ", strip=True)[:12000]

    return {
        "title": title or "未命名心理文章",
        "author": author,
        "summary": summary,
        "cover_image": cover_image,
        "content": "",
        "category": target.category,
        "status": "已发布",
        "source_name": _source_name(target.url),
        "source_url": target.url,
        "published_at": _parse_datetime(published_value),
    }


def crawl_articles(
    db: Session,
    targets: Iterable[CrawlTarget] = DEFAULT_TARGETS,
    *,
    sources: Iterable[CrawlSource] = DEFAULT_SOURCES,
    delay_seconds: float = 0.35,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owned_client = client is None
    http_client = client or httpx.Client(
        trust_env=False,
        follow_redirects=True,
        timeout=20,
        headers={
            "User-Agent": "CampusMentalHealthBot/1.0 (+educational metadata index; contact: campus-admin)",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    created = 0
    updated = 0
    failures: list[dict[str, str]] = []
    seed_targets = list(targets)
    discovered_targets, discovery_failures = discover_targets(http_client, sources)
    failures.extend(discovery_failures)
    target_by_url: dict[str, CrawlTarget] = {}
    for target in (*seed_targets, *discovered_targets):
        canonical = _canonical_url(target.url)
        target_by_url.setdefault(canonical, CrawlTarget(canonical, target.category))
    target_list = list(target_by_url.values())
    try:
        for index, target in enumerate(target_list):
            try:
                response = http_client.get(target.url)
                response.raise_for_status()
                values = parse_article_html(target, response.text)
                article = db.query(Article).filter(Article.source_url == target.url).first()
                if article is None:
                    article = Article(**values)
                    db.add(article)
                    created += 1
                else:
                    for field, value in values.items():
                        setattr(article, field, value)
                    updated += 1
                db.commit()
            except Exception as exc:  # Continue crawling other independent sources.
                db.rollback()
                failures.append({"url": target.url, "error": _clean(str(exc), 180)})
            if delay_seconds and index < len(target_list) - 1:
                time.sleep(delay_seconds)
    finally:
        if owned_client:
            http_client.close()
    article_service.invalidate_articles()
    return {
        "created": created,
        "updated": updated,
        "discovered": len(discovered_targets),
        "total_targets": len(target_list),
        "failed": failures,
    }
