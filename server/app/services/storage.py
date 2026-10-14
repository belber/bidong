from pathlib import Path

from ..config import settings


def _ext_for(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")


def media_url(value: str) -> str:
    """把媒体地址补成绝对地址。

    本地存储后端存的是相对路径（/media/covers/x.jpg），管理端页面、微信搜索爬虫
    这类「自己直接消费 URL」的地方拿到相对路径会 404，所以由后端在序列化时补全；
    COS 存的本来就是绝对地址，原样返回（生产行为不变）。
    """
    if not value or not isinstance(value, str):
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return settings.public_base_url.rstrip("/") + "/" + value.lstrip("/")


class LocalStorage:
    def save_cover(self, bvid: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        key = f"{bvid}{_ext_for(content_type)}"
        path = Path(settings.local_storage_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        # 存相对路径：换 IP 不用改库，小程序端用 apiBase 拼（见 spec §4）
        return f"/media/covers/{key}"


class CosStorage:
    def save_cover(self, bvid: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        from qcloud_cos import CosConfig, CosS3Client

        key = f"covers/{bvid}{_ext_for(content_type)}"
        config = CosConfig(
            Region=settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key,
        )
        client = CosS3Client(config)
        client.put_object(
            Bucket=settings.cos_bucket,
            Body=image_bytes,
            Key=key,
            ContentType=content_type,
        )
        return f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com/{key}"


def get_storage():
    if settings.storage_backend == "cos":
        return CosStorage()
    return LocalStorage()

