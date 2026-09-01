import httpx
import pytest
import respx

from app.errors import AppError
from app.services.bilibili import BiliClient


@respx.mock
def test_resolve_bv_accepts_url_and_bv():
    client = BiliClient()
    assert client.resolve_bvid("https://www.bilibili.com/video/BV1xx411c7mD") == "BV1xx411c7mD"
    assert client.resolve_bvid("BV1xx411c7mD") == "BV1xx411c7mD"
    client.close()


@respx.mock
def test_resolve_short_link():
    respx.get("https://b23.tv/abcd").mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "https://www.bilibili.com/video/BV1xx411c7mD"},
        )
    )
    client = BiliClient()
    assert client.resolve_bvid("https://b23.tv/abcd") == "BV1xx411c7mD"
    client.close()


@respx.mock
def test_invalid_url_raises():
    client = BiliClient()
    with pytest.raises(AppError):
        client.resolve_bvid("https://example.com/not-bili")
    client.close()


@respx.mock
def test_get_video_maps_fields():
    respx.get("https://api.bilibili.com/x/web-interface/view?bvid=BV1xx411c7mD").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "bvid": "BV1xx411c7mD",
                    "title": "标题",
                    "pic": "//i0.hdslb.com/bfs/archive/a.jpg",
                    "owner": {"name": "UP主"},
                    "tname": "知识",
                    "desc": "简介",
                    "duration": 123,
                    "pubdate": 1700000000,
                    "stat": {
                        "like": 100,
                        "reply": 20,
                        "favorite": 300,
                        "coin": 40,
                        "danmaku": 500,
                    },
                },
            },
        )
    )
    client = BiliClient()
    meta = client.get_video("BV1xx411c7mD")
    assert meta.title == "标题"
    assert meta.cover_url == "https://i0.hdslb.com/bfs/archive/a.jpg"
    assert meta.up_name == "UP主"
    assert meta.partition == "知识"
    assert meta.duration == 123
    assert meta.pubdate == 1700000000
    assert meta.like == 100
    assert meta.reply == 20
    assert meta.favorite == 300
    assert meta.coin == 40
    assert meta.danmaku == 500
    client.close()


@respx.mock
def test_get_tags():
    respx.get("https://api.bilibili.com/x/tag/archive/tags?bvid=BV1xx411c7mD").mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": [{"tag_name": "科幻"}, {"tag_name": "深度"}]},
        )
    )
    client = BiliClient()
    assert client.get_tags("BV1xx411c7mD") == ["科幻", "深度"]
    client.close()


@respx.mock
def test_get_subtitles():
    respx.get("https://api.bilibili.com/x/web-interface/nav").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdef0123456789abcdef.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/fedcba9876543210fedcba9876543210.png",
                    }
                },
            },
        )
    )
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/v2.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "subtitle": {
                        "subtitles": [
                            {
                                "lan": "zh-CN",
                                "subtitle_url": "https://sub.example.com/sub.json",
                            }
                        ]
                    }
                },
            },
        )
    )
    respx.get("https://sub.example.com/sub.json").mock(
        return_value=httpx.Response(
            200,
            json={"body": [{"from": 3.2, "content": "你好"}, {"from": 7.0, "content": "世界"}]},
        )
    )

    client = BiliClient()
    subs = client.get_subtitles("BV1xx411c7mD", 987654)
    assert subs == [{"t": 3, "text": "你好"}, {"t": 7, "text": "世界"}]
    client.close()


@respx.mock
def test_get_playurl_dash_and_durl():
    respx.get("https://api.bilibili.com/x/web-interface/nav").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdef0123456789abcdef.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/fedcba9876543210fedcba9876543210.png",
                    }
                },
            },
        )
    )
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=16.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "dash": {
                        "video": [
                            {
                                "id": 64,
                                "baseUrl": "https://v.example.com/v.m4s",
                                "backupUrl": ["https://v.example.com/v2.m4s"],
                            }
                        ],
                        "audio": [
                            {
                                "id": 30280,
                                "baseUrl": "https://a.example.com/a.m4s",
                                "backupUrl": [],
                            }
                        ],
                    }
                },
            },
        )
    )
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=1(?![0-9]).*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "quality": 32,
                    "durl": [
                        {
                            "url": "https://d.example.com/d.mp4",
                            "backup_url": ["https://d.example.com/d2.mp4"],
                        }
                    ],
                },
            },
        )
    )

    client = BiliClient()
    dash = client.get_playurl("BV1xx411c7mD", 987654, fnval=16)
    assert dash["video"][0]["qn"] == 64
    assert dash["video"][0]["label"] == "720P"
    assert dash["video"][0]["url"] == "https://v.example.com/v.m4s"
    assert dash["audio"][0]["qn"] == 30280

    durl = client.get_playurl("BV1xx411c7mD", 987654, fnval=1)
    assert durl["durl"][0]["qn"] == 32
    assert durl["durl"][0]["url"] == "https://d.example.com/d.mp4"
    client.close()


@respx.mock
def test_get_danmaku():
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(200, text="<i><d p='1,1,25'>哈哈</d></i>")
    )
    client = BiliClient()
    assert client.get_danmaku(987654).startswith("<i>")
    client.close()


@respx.mock
def test_get_danmaku_empty_on_error():
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(404)
    )
    client = BiliClient()
    assert client.get_danmaku(987654) == ""
    client.close()
