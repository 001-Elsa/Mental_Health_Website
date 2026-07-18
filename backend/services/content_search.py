from datetime import datetime, timedelta

from fastapi import HTTPException


PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "365d": 365,
}


def period_start(period: str) -> datetime | None:
    if period == "all":
        return None
    days = PERIOD_DAYS.get(period)
    if days is None:
        raise HTTPException(status_code=422, detail="无效的时间范围")
    return datetime.now() - timedelta(days=days)
