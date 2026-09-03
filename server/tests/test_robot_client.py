import httpx
import respx

from app.errors import AppError
from app.services.bilibili_robot import BiliRobotClient


def _client():
    return BiliRobotClient(
        {"SESSDATA": "s", "bili_jct": "csrf-token", "DedeUserID": "100"},
        robot_uid="100",
    )


@respx.mock
def test_get_followers():
    respx.get(url__regex=r"https://api\.bilibili\.com/x/relation/followers.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"list": [{"mid": 111, "uname": "用户A", "mtime": 1700000000}]},
            },
        )
    )
    client = _client()
    items = client.get_followers()
    client.close()
    assert items == [{"mid": "111", "uname": "用户A", "mtime": 1700000000}]


@respx.mock
def test_get_at_notifications_extracts_bvid():
    respx.get("https://api.bilibili.com/x/msgfeed/at").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "cursor": {"id": 8, "time": 1700000001, "is_end": True},
                    "items": [
                        {
                            "id": 8,
                            "at_time": 1700000001,
                            "user": {"mid": 222, "nickname": "用户B"},
                            "item": {
                                "type": "reply",
                                "business": "评论",
                                "uri": "https://www.bilibili.com/video/BV1xx411c7mD",
                                "source_content": "@壁咚收藏夹",
                            },
                        }
                    ]
                },
            },
        )
    )
    client = _client()
    items = client.get_at_notifications()
    client.close()
    assert items == [
        {
            "id": "8",
            "time": 1700000001,
            "mid": "222",
            "uname": "用户B",
            "bvid": "BV1xx411c7mD",
        }
    ]


@respx.mock
def test_send_msg_posts_csrf_and_sender_uid():
    route = respx.post("https://api.vc.bilibili.com/web_im/v1/web_im/send_msg").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    client = _client()
    client.send_msg("333", "壁咚激活码：ABC123")
    client.close()
    assert route.called
    assert route.calls[0].request.headers.get("cookie", "").find("bili_jct=csrf-token") != -1
