import respx
from sqlalchemy.orm import sessionmaker

from app.models import DownloadEvent
from app.time import utcnow_naive

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


@respx.mock
def test_delete_card_clears_download_event_reference(client, auth_headers, db_engine):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    card = resp.json()
    card_id = card["id"]

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    event = DownloadEvent(
        card_id=card_id,
        bvid=card["bvid"],
        kind="watermarked",
        qn=16,
        host="upos-sz-mirrorcoso1.bilivideo.com",
        candidate_index=0,
        stage="download",
        status="fail",
        error_type="domain_not_configured",
        error_message="url not in domain list",
        wx_err_msg="downloadFile:fail url not in domain list",
        created_at=utcnow_naive(),
    )
    db.add(event)
    db.commit()
    event_id = event.id
    db.close()

    deleted = client.delete(f"/api/cards/{card_id}", headers=auth_headers)
    assert deleted.status_code == 204

    db = Session()
    assert db.query(DownloadEvent).get(event_id).card_id is None
    assert db.query(DownloadEvent).count() == 1
    db.close()

