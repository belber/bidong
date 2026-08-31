import httpx
import respx

BVID = "BV1xx411c7mD"


def mock_bili(bvid=BVID):
    respx.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "bvid": bvid,
                    "title": "测试标题",
                    "pic": "//i0.hdslb.com/bfs/archive/a.jpg",
                    "owner": {"name": "测试UP"},
                    "tname": "知识",
                    "desc": "测试简介",
                    "duration": 123,
                    "pubdate": 1700000000,
                    "cid": 987654,
                },
            },
        )
    )
    respx.get(f"https://api.bilibili.com/x/tag/archive/tags?bvid={bvid}").mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": [{"tag_name": "科幻"}, {"tag_name": "深度"}]},
        )
    )
    respx.get("https://i0.hdslb.com/bfs/archive/a.jpg").mock(
        return_value=httpx.Response(
            200,
            content=b"fake-image",
            headers={"content-type": "image/jpeg"},
        )
    )
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
            json={"body": [{"from": 5.0, "content": "第一句"}, {"from": 9.0, "content": "第二句"}]},
        )
    )
