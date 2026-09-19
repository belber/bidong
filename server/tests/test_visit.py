from sqlalchemy.orm import sessionmaker

from app.models import VisitEvent


def test_report_visit_requires_auth(client):
    resp = client.post("/api/visit-events", json={"path": "pages/home/home"})
    assert resp.status_code == 401


def test_report_visit_records_row(client, auth_headers, db_engine):
    resp = client.post(
        "/api/visit-events",
        json={"path": "pages/home/home"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    event = db.query(VisitEvent).first()
    assert event is not None
    assert event.path == "pages/home/home"
    db.close()
