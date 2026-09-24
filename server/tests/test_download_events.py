import httpx
import respx

from app.services.media_download import is_allowed_url
from helpers import BVID, mock_bili


def _make_card(client, auth_headers):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


def _mark_configured(db_engine, host):
    from sqlalchemy.orm import sessionmaker

    from app.models import BiliCdnDomain

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    row = db.query(BiliCdnDomain).filter_by(host=host).first()
    if row is None:
        row = BiliCdnDomain(host=host)
    row.is_configured = True
    db.add(row)
    db.commit()
    db.close()


def _mock_watermarked_playurl():
    respx.get(
        url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=1.*"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "quality": 16,
                    "durl": [
                        {
                            "url": "https://upos-sz-mirrorcoso1.bilivideo.com/a.mp4?deadline=1789752728",
                            "backup_url": [
                                "https://upos-sz-estgcos.bilivideo.com/b.mp4?deadline=1789752728"
                            ],
                        }
                    ],
                    "dash": {"video": [], "audio": []},
                },
            },
        )
    )


def _mock_audio_playurl():
    respx.get(
        url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=16.*"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "dash": {
                        "video": [],
                        "audio": [
                            {
                                "id": 30280,
                                "baseUrl": "https://upos-sz-mirrorcos.bilivideo.com/a.m4s?deadline=1789752728",
                                "backupUrl": [
                                    "https://upos-sz-estgcos.bilivideo.com/a.m4s?deadline=1789752728"
                                ],
                            }
                        ],
                    },
                    "durl": [],
                },
            },
        )
    )


def test_is_allowed_url_skips_dynamic_pcdn_and_ports():
    assert is_allowed_url("https://upos-sz-mirrorcoso1.bilivideo.com/a.mp4") is True
    assert is_allowed_url("https://xy116x196x156x56xy.mcdn.bilivideo.cn:8082/a.m4s") is False
    assert is_allowed_url("https://example.com:8080/a.mp4") is False
    assert is_allowed_url("") is False


@respx.mock
def test_download_url_returns_all_candidates_with_configured_flags(
    client, auth_headers, db_engine, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    _mock_watermarked_playurl()
    card = _make_card(client, auth_headers)
    _mark_configured(db_engine, "upos-sz-estgcos.bilivideo.com")

    resp = client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "watermarked"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "watermarked"
    assert data["qn"] == 16
    assert data["expires_at"] == 1789752728
    assert [c["host"] for c in data["candidates"]] == [
        "upos-sz-mirrorcoso1.bilivideo.com",
        "upos-sz-estgcos.bilivideo.com",
    ]
    assert [c["configured"] for c in data["candidates"]] == [False, True]


@respx.mock
def test_download_url_returns_all_unconfigured_candidates_without_error(
    client, auth_headers, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    _mock_watermarked_playurl()
    card = _make_card(client, auth_headers)

    resp = client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "watermarked"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert [c["host"] for c in data["candidates"]] == [
        "upos-sz-mirrorcoso1.bilivideo.com",
        "upos-sz-estgcos.bilivideo.com",
    ]
    assert [c["configured"] for c in data["candidates"]] == [False, False]
    assert "error_type" not in data


@respx.mock
def test_download_url_debug_fail_returns_failing_candidate(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    monkeypatch.setattr(settings, "download_debug_fail", True)
    _mock_watermarked_playurl()
    card = _make_card(client, auth_headers)

    resp = client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "watermarked"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"] == [{
        "url": "https://debug.invalid/download-debug-fail",
        "host": "debug.invalid",
        "configured": False,
    }]


@respx.mock
def test_download_url_audio_uses_normal_dash(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_audio", True)
    _mock_audio_playurl()
    card = _make_card(client, auth_headers)

    resp = client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "audio"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "audio"
    assert data["qn"] == 30280
    candidate = data["candidates"][0]
    assert candidate["host"] == "testserver"
    assert candidate["configured"] is True
    assert candidate["url"] == f"http://testserver/api/cards/{card['id']}/download?kind=audio&qn=30280"


@respx.mock
def test_report_download_event_and_domain_counters(
    client, auth_headers, db_engine, monkeypatch
):
    from app.config import settings
    from sqlalchemy.orm import sessionmaker

    from app.models import BiliCdnDomain, DownloadEvent

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    _mock_watermarked_playurl()
    card = _make_card(client, auth_headers)
    _mark_configured(db_engine, "upos-sz-mirrorcoso1.bilivideo.com")
    client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "watermarked"},
        headers=auth_headers,
    )

    payload = {
        "card_id": card["id"],
        "bvid": card["bvid"],
        "kind": "watermarked",
        "qn": 16,
        "host": "upos-sz-mirrorcoso1.bilivideo.com",
        "candidate_index": 0,
        "stage": "download",
        "status": "fail",
        "error_type": "domain_not_configured",
        "error_message": "url not in domain list",
        "http_status": None,
        "wx_err_msg": "downloadFile:fail url not in domain list",
    }
    resp = client.post("/api/download-events", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "fail"

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    event = db.query(DownloadEvent).first()
    assert event is not None
    assert event.error_type == "domain_not_configured"
    domain = db.query(BiliCdnDomain).filter_by(host="upos-sz-mirrorcoso1.bilivideo.com").first()
    assert domain is not None
    assert domain.download_failure_count == 1
    db.close()


def test_unconfigured_domain_alert_dedup(db_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.services import notify

    calls = []
    monkeypatch.setattr(
        notify,
        "send_notification",
        lambda db, subject, body, kind="": calls.append(subject)
        or {"email": True, "serverchan": False},
    )
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    assert notify.send_unconfigured_domain_alert(db, "a.example.com", "BV1") is True
    assert notify.send_unconfigured_domain_alert(db, "a.example.com", "BV1") is False
    assert len(calls) == 1
    db.close()


@respx.mock
def test_download_url_triggers_unconfigured_domain_alert(
    client, auth_headers, db_engine, monkeypatch
):
    from app.config import settings
    from app.services import notify

    monkeypatch.setattr(settings, "enable_watermarked_video", True)
    calls = []
    monkeypatch.setattr(
        notify,
        "send_unconfigured_domain_alert",
        lambda db, host, bvid="": calls.append(host) or True,
    )
    _mock_watermarked_playurl()
    card = _make_card(client, auth_headers)
    _mark_configured(db_engine, "upos-sz-mirrorcoso1.bilivideo.com")

    resp = client.get(
        f"/api/cards/{card['id']}/download-url",
        params={"kind": "watermarked"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "upos-sz-mirrorcoso1.bilivideo.com" not in calls
    assert "upos-sz-estgcos.bilivideo.com" in calls


@respx.mock
def test_download_event_fills_video_title_and_link_from_own_card(
    client, auth_headers, db_engine
):
    """后端从该用户自己的卡片回填标题与 B站链接，客户端传值不作数。"""
    from sqlalchemy.orm import sessionmaker

    from app.models import DownloadEvent

    card = _make_card(client, auth_headers)
    payload = {
        "card_id": card["id"],
        "bvid": card["bvid"],
        "kind": "watermarked",
        "qn": 16,
        "host": "upos-sz-mirrorcoso1.bilivideo.com",
        "stage": "download",
        "status": "success",
        "video_title": "伪造标题",
        "source_url": "https://evil.example/x",
    }
    resp = client.post("/api/download-events", json=payload, headers=auth_headers)
    assert resp.status_code == 200

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    event = db.query(DownloadEvent).first()
    assert event is not None
    assert event.video_title == card["title"] == "测试标题"
    assert event.source_url == card["source_url"]
    assert "evil.example" not in event.source_url
    db.close()
