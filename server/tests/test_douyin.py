"""抖音解析：链接归一化 + 字段映射。

字段映射用真机抓下来的响应做夹具（tests/fixtures/douyin_detail_video.json），
这样测试不需要任何网络和登录态。
"""

import json
from pathlib import Path

import pytest

from app.errors import AppError
from app.services import config_store, douyin, link_platform

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"


def fixture_detail() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["aweme_detail"]


class TestDetectPlatform:
    def test_recognizes_bilibili_links(self):
        assert link_platform.detect_platform("https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili"
        assert link_platform.detect_platform("https://b23.tv/2g9l5YF") == "bilibili"
        assert link_platform.detect_platform("看看这个 BV1xx411c7mD") == "bilibili"

    def test_recognizes_douyin_links(self):
        assert link_platform.detect_platform("https://v.douyin.com/iRNBho6/") == "douyin"
        assert link_platform.detect_platform("https://www.douyin.com/video/7685688911658323392") == "douyin"
        assert link_platform.detect_platform("https://www.douyin.com/note/7300000000000000000") == "douyin"
        assert link_platform.detect_platform("7.43 复制打开抖音 https://v.douyin.com/iRNBho6/") == "douyin"

    def test_returns_none_for_other_text(self):
        assert link_platform.detect_platform("https://www.youtube.com/watch?v=xxx") is None
        assert link_platform.detect_platform("") is None
        assert link_platform.detect_platform(None) is None


class TestExtractAwemeId:
    def test_extracts_from_share_text(self):
        text = "7.43 复制打开抖音，看看【木鱼水心】的作品 https://v.douyin.com/iRNBho6/"
        assert douyin.extract_aweme_id(text) is None  # 短链要联网才知道 ID

    def test_extracts_from_full_url(self):
        assert douyin.extract_aweme_id("https://www.douyin.com/video/7685688911658323392") == "7685688911658323392"
        assert douyin.extract_aweme_id("https://www.douyin.com/note/7300000000000000000?x=1") == "7300000000000000000"

    def test_extracts_from_slides_share_page(self):
        # 图文短链会跳到 /share/slides/<id>，漏了这条就解析不出图文
        assert douyin.extract_aweme_id("https://www.iesdouyin.com/share/slides/7300000000000000000/") == "7300000000000000000"

    def test_ignores_non_douyin(self):
        assert douyin.extract_aweme_id("https://www.bilibili.com/video/BV1xx411c7mD") is None


class TestMetaFromDetail:
    def test_maps_core_fields(self):
        meta = douyin.meta_from_detail(fixture_detail())
        assert meta.aweme_id == "7685688911658323392"
        assert meta.kind == "video"
        assert meta.title == "给我39个粉丝更新一下#萌妹子 #男高"
        assert meta.author_name == "Dustinsuperstar"
        assert meta.author_unique_id == "74305918298"
        assert meta.author_sec_uid.startswith("MS4wLjABAAAA")
        assert meta.duration == 13
        assert meta.created_at == 1789463897

    def test_collects_media_urls(self):
        meta = douyin.meta_from_detail(fixture_detail())
        assert len(meta.video_urls) == 4
        assert all(u.startswith("http") for u in meta.video_urls)
        assert len(meta.audio_urls) == 2
        assert meta.cover_url.startswith("http")

    def test_extracts_hashtags_as_tags(self):
        meta = douyin.meta_from_detail(fixture_detail())
        assert meta.tags == ["萌妹子", "男高"]

    def test_maps_stats_to_bilibili_slots(self):
        meta = douyin.meta_from_detail(fixture_detail())
        assert meta.stats == {
            "like": 15931,
            "reply": 1553,
            "favorite": 1521,
            "share": 2887,
        }

    def test_marks_note_when_images_present(self):
        detail = fixture_detail()
        detail["images"] = [{"url_list": ["https://p26-sign.douyinpic.com/a.jpeg"]}]
        meta = douyin.meta_from_detail(detail)
        assert meta.kind == "note"
        assert meta.image_urls == ["https://p26-sign.douyinpic.com/a.jpeg"]

    def test_raises_when_detail_empty(self):
        with pytest.raises(AppError):
            douyin.meta_from_detail({})


class TestSourceUrl:
    def test_video_source_url(self):
        assert douyin.source_url("7685688911658323392", "video") == (
            "https://www.douyin.com/video/7685688911658323392"
        )

    def test_note_source_url(self):
        assert douyin.source_url("7300000000000000000", "note") == (
            "https://www.douyin.com/note/7300000000000000000"
        )


class TestCookieStore:
    """Cookie 归一化与存取：用户从浏览器粘出来的格式很杂，先压平再落库。"""

    def test_normalize_drops_bare_domain_token(self):
        # Netscape 导出会混进 `douyin.com` 这种没有 = 的片段
        raw = "sessionid=abc; douyin.com; sid_tt=abc\nuid_tt=abc;"
        assert config_store.normalize_cookie(raw) == "sessionid=abc; sid_tt=abc; uid_tt=abc"

    def test_normalize_handles_multiline(self):
        raw = "a=1;\nb=2\r\nc=3"
        assert config_store.normalize_cookie(raw) == "a=1; b=2; c=3"

    def test_roundtrip_and_configured_check(self, db_engine):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        db = Session()
        assert config_store.douyin_cookie_configured(db) is False

        config_store.set_douyin_cookie(db, "sessionid=x; sid_tt=x; uid_tt=x;")
        db.commit()
        assert config_store.douyin_cookie(db) == "sessionid=x; sid_tt=x; uid_tt=x"
        assert config_store.douyin_cookie_configured(db) is True

        config_store.set_douyin_cookie(db, "sessionid=x")
        db.commit()
        assert config_store.douyin_cookie_configured(db) is False
        db.close()

    def test_parse_node_defaults_and_roundtrip(self, db_engine):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        db = Session()
        assert config_store.douyin_parse_node(db) == "tencent"
        config_store.set_douyin_parse_node(db, "home")
        db.commit()
        assert config_store.douyin_parse_node(db) == "home"
        config_store.set_douyin_parse_node(db, "")
        db.commit()
        assert config_store.douyin_parse_node(db) == "tencent"
        db.close()
