import respx

from helpers import BVID, mock_bili


def test_create_and_list_tags(client, auth_headers):
    first = client.post("/api/tags", json={"name": "学习"}, headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["name"] == "学习"

    duplicate = client.post("/api/tags", json={"name": "学习"}, headers=auth_headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]

    tags = client.get("/api/tags", headers=auth_headers).json()
    assert tags == ["学习"]


@respx.mock
def test_add_tags_to_card(client, auth_headers):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    card_id = resp.json()["id"]

    updated = client.post(
        f"/api/cards/{card_id}/tags",
        json={"tags": ["收藏", "学习"]},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert set(updated.json()["tags"]) == {"科幻", "深度", "收藏", "学习"}

    tags = client.get("/api/tags", headers=auth_headers).json()
    assert "收藏" in tags

