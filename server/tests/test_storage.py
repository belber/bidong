import sys
import types

from app.config import settings
from app.services.storage import LocalStorage, media_url


def test_local_storage_writes_file_and_returns_relative_path(tmp_path, monkeypatch):
    """本地后端存相对路径：换 IP 不用改库，前端用 apiBase 拼。"""
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")

    url = LocalStorage().save_cover("BV1xx411c7mD", b"fake-image", "image/jpeg")

    assert url == "/media/covers/BV1xx411c7mD.jpg"
    assert (tmp_path / "BV1xx411c7mD.jpg").read_bytes() == b"fake-image"


def test_cos_storage_still_returns_absolute_url(monkeypatch):
    """生产走 COS：必须仍然是绝对地址，不能被相对路径改动波及。"""
    calls = {}

    class FakeClient:
        def __init__(self, config):
            calls["config"] = config

        def put_object(self, **kwargs):
            calls["kwargs"] = kwargs
            return {"ETag": "x"}

    fake_module = types.ModuleType("qcloud_cos")
    fake_module.CosConfig = lambda **kwargs: kwargs
    fake_module.CosS3Client = FakeClient
    monkeypatch.setitem(sys.modules, "qcloud_cos", fake_module)

    monkeypatch.setattr(settings, "storage_backend", "cos")
    monkeypatch.setattr(settings, "cos_region", "ap-shanghai")
    monkeypatch.setattr(settings, "cos_secret_id", "id")
    monkeypatch.setattr(settings, "cos_secret_key", "key")
    monkeypatch.setattr(settings, "cos_bucket", "bidong-1300000000")
    # 故意设一个本地地址：COS 分支不允许再用它
    monkeypatch.setattr(settings, "public_base_url", "http://192.168.31.179:8000")

    from app.services.storage import CosStorage

    url = CosStorage().save_cover("BV1xx411c7mD", b"fake-image", "image/webp")

    assert url == "https://bidong-1300000000.cos.ap-shanghai.myqcloud.com/covers/BV1xx411c7mD.webp"
    assert calls["kwargs"]["Key"] == "covers/BV1xx411c7mD.webp"
    assert calls["kwargs"]["ContentType"] == "image/webp"


class TestMediaUrl:
    """给管理端 / 爬虫这类「自己直接消费 URL」的地方补绝对地址。"""

    def test_relative_path_becomes_absolute(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "http://192.168.31.179:8000")
        assert media_url("/media/covers/a.jpg") == "http://192.168.31.179:8000/media/covers/a.jpg"

    def test_absolute_url_untouched(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "http://192.168.31.179:8000")
        cos = "https://bucket.cos.ap-shanghai.myqcloud.com/covers/a.jpg"
        assert media_url(cos) == cos
        assert media_url("http://192.168.31.179:8000/media/covers/a.jpg") == "http://192.168.31.179:8000/media/covers/a.jpg"

    def test_empty_value_stays_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "http://192.168.31.179:8000")
        assert media_url("") == ""
        assert media_url(None) is None

    def test_base_url_trailing_slash_does_not_double_up(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "http://192.168.31.179:8000/")
        assert media_url("/media/covers/a.jpg") == "http://192.168.31.179:8000/media/covers/a.jpg"
        assert media_url("media/covers/a.jpg") == "http://192.168.31.179:8000/media/covers/a.jpg"

