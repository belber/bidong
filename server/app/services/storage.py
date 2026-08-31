from pathlib import Path

from ..config import settings


def _ext_for(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")


class LocalStorage:
    def save_cover(self, bvid: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        key = f"{bvid}{_ext_for(content_type)}"
        path = Path(settings.local_storage_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        return f"{settings.public_base_url}/media/covers/{key}"


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

