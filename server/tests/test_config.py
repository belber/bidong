from app.config import Settings


def test_media_switches_default_off(monkeypatch):
    for key in ("ENABLE_WATERMARKED_VIDEO", "ENABLE_CLEAN_VIDEO", "ENABLE_AUDIO"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.enable_watermarked_video is False
    assert s.enable_clean_video is False
    assert s.enable_audio is False
