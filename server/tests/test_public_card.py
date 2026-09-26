"""公开卡片接口：给未登录访客和微信搜索爬虫看的基础信息。

结果页被推送/分享出去后，打开它的人（或爬虫）没有登录态，
这时候不能只给一句「请先登录」——页面必须能直接看到内容，才谈得上被收录。
"""

import respx

from app.services import repost_source
from helpers import BVID, mock_bili

UP_MID = "3707052465589015"


def test_public_card_needs_no_token(client):
    """公开接口不能因为"没登录"就拒绝——爬虫和未登录访客都没有 token。"""
    resp = client.get(f"/api/public/cards/{BVID}")
    assert resp.status_code == 404  # 库里还没有这条，但不是 401


@respx.mock
def test_public_card_returns_origin(client, auth_headers):
    mock_bili(bvid=BVID, up_mid=UP_MID)
    parsed = client.post(
        "/api/parse",
        json={"url": f"https://www.bilibili.com/video/{BVID}"},
        headers=auth_headers,
    )
    assert parsed.status_code == 200

    resp = client.get(f"/api/public/cards/{BVID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bvid"] == BVID
    assert data["title"] == "测试标题"
    assert data["up_name"] == "测试UP"
    assert data["cover_url"]
    assert data["source_url"].endswith(BVID)
    # 出处信息也带上：这正是粉丝要的东西
    assert data["origin"] is not None
    assert data["origin"]["account_name"] == "帅哥录屏"
    # 不含任何用户数据
    for leaked in ("id", "user_id", "tags", "stats", "media", "features"):
        assert leaked not in data


def test_public_card_missing_returns_404(client):
    resp = client.get("/api/public/cards/BV1xx411c7mD")
    assert resp.status_code == 404


def test_public_card_rejects_bad_bvid(client):
    resp = client.get("/api/public/cards/not-a-bvid")
    assert resp.status_code == 400
