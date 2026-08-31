import respx

from helpers import BVID, mock_bili


@respx.mock
def test_list_filter_get_delete(client, auth_headers):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    card = resp.json()
    card_id = card["id"]
    month = card["month"]

    cards = client.get("/api/cards", headers=auth_headers).json()
    assert len(cards) == 1
    assert cards[0]["id"] == card_id

    by_tag = client.get("/api/cards", params={"tag": "科幻"}, headers=auth_headers).json()
    assert len(by_tag) == 1
    missing = client.get("/api/cards", params={"tag": "不存在"}, headers=auth_headers).json()
    assert missing == []

    by_month = client.get("/api/cards", params={"month": month}, headers=auth_headers).json()
    assert len(by_month) == 1

    one = client.get(f"/api/cards/{card_id}", headers=auth_headers)
    assert one.status_code == 200
    assert one.json()["id"] == card_id

    deleted = client.delete(f"/api/cards/{card_id}", headers=auth_headers)
    assert deleted.status_code == 204
    gone = client.get(f"/api/cards/{card_id}", headers=auth_headers)
    assert gone.status_code == 404

