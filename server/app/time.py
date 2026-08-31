from datetime import datetime, timedelta, timezone

SHANGHAI_OFFSET = timedelta(hours=8)


def utcnow_naive() -> datetime:
    """返回 naive UTC 时间，避免 SQLite/Postgres 时区差异带来的麻烦。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def month_of(dt: datetime) -> str:
    """naive UTC -> 北京时间下的 'YYYY-MM'，与收藏月份分组保持一致。"""
    return (dt + SHANGHAI_OFFSET).strftime("%Y-%m")


def to_unix(dt: datetime) -> int:
    """naive UTC -> unix 秒，供前端沿用现有数字时间戳。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

