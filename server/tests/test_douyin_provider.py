"""抖音取数 provider：网络层用 respx 打桩，不碰真实接口。"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.errors import AppError
from app.services.douyin_provider import DETAIL_API, DouyinProvider

FIXTURE = Path(__file__).parent / "fixtures" / "douyin_detail_video.json"
AWEME_ID = "7685688911658323392"


def fixture_body() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def provider():
    p = DouyinProvider(cookie="sessionid=abc; sid_tt=abc; uid_tt=abc")
    yield p
    p.close()


class TestResolveAwemeId:
    def test_full_url_needs_no_network(self, provider):
        assert provider.resolve_aweme_id(f"https://www.douyin.com/video/{AWEME_ID}") == AWEME_ID

    @respx.mock
    def test_short_link_follows_redirect(self, provider):
        respx.get("https://v.douyin.com/iRNBho6/").mock(
            return_value=httpx.Response(
                302, headers={"location": f"https://www.iesdouyin.com/share/video/{AWEME_ID}/"}
            )
        )
        respx.get(f"https://www.iesdouyin.com/share/video/{AWEME_ID}/").mock(
            return_value=httpx.Response(200, text="<html></html>")
        )
        assert provider.resolve_aweme_id("7.43 复制打开抖音 https://v.douyin.com/iRNBho6/") == AWEME_ID

    @respx.mock
    def test_short_link_without_id_raises(self, provider):
        respx.get("https://v.douyin.com/dead/").mock(
            return_value=httpx.Response(200, text="<html>直播中</html>")
        )
        with pytest.raises(AppError) as exc:
            provider.resolve_aweme_id("https://v.douyin.com/dead/")
        assert exc.value.status_code == 400

    def test_garbage_raises(self, provider):
        with pytest.raises(AppError):
            provider.resolve_aweme_id("这不是抖音链接")


class TestFetchDetail:
    @respx.mock
    def test_returns_detail_on_success(self, provider):
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=fixture_body()))
        detail = provider.fetch_detail(AWEME_ID)
        assert detail["aweme_id"] == AWEME_ID

    @respx.mock
    def test_empty_body_means_session_dead(self, provider):
        # 身份失效时抖音回的是 200 + 0 字节，不能只看状态码
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(AppError) as exc:
            provider.fetch_detail(AWEME_ID)
        assert "会话" in exc.value.message

    @respx.mock
    def test_non_json_body_raises(self, provider):
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b"<html>403</html>"))
        with pytest.raises(AppError):
            provider.fetch_detail(AWEME_ID)

    @respx.mock
    def test_network_error_becomes_502(self, provider):
        respx.get(DETAIL_API).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(AppError) as exc:
            provider.fetch_detail(AWEME_ID)
        assert exc.value.status_code == 502


class TestResolve:
    @respx.mock
    def test_end_to_end_meta(self, provider):
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=fixture_body()))
        meta = provider.resolve(f"https://www.douyin.com/video/{AWEME_ID}")
        assert meta.aweme_id == AWEME_ID
        assert meta.kind == "video"
        assert meta.stats["like"] == 15931


class TestProbe:
    @respx.mock
    def test_probe_reports_body_size(self, provider):
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=fixture_body()))
        result = provider.probe(AWEME_ID)
        assert result["ok"] is True
        assert result["bytes"] == len(fixture_body())

    @respx.mock
    def test_probe_flags_empty_body(self, provider):
        respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b""))
        result = provider.probe(AWEME_ID)
        assert result["ok"] is False
        assert result["bytes"] == 0
