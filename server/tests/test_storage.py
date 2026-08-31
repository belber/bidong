from app.config import settings
from app.services.storage import LocalStorage


def test_local_storage_writes_and_returns_url(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")

    url = LocalStorage().save_cover("BV1xx411c7mD", b"fake-image", "image/jpeg")

    assert url == "http://testserver/media/covers/BV1xx411c7mD.jpg"
    assert (tmp_path / "BV1xx411c7mD.jpg").read_bytes() == b"fake-image"

