from app.services import config_store


def test_public_help_config_default_empty(client):
    resp = client.get("/api/help/config")
    assert resp.status_code == 200
    assert resp.json() == {"qq_group": ""}


def test_public_help_config_reads_admin_set_value(client, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_help_config(db, "88888888")
    db.close()

    resp = client.get("/api/help/config")
    assert resp.status_code == 200
    assert resp.json() == {"qq_group": "88888888"}


def test_public_config_default_robot_guide_on(client):
    resp = client.get("/api/config/public")
    assert resp.status_code == 200
    assert resp.json() == {"robot_guide": True, "share": True}


def test_public_config_reflects_admin_switch(client, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_robot_guide_enabled(db, False)
    db.close()

    resp = client.get("/api/config/public")
    assert resp.status_code == 200
    assert resp.json() == {"robot_guide": False, "share": True}


def test_public_config_reflects_share_switch(client, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_share_enabled(db, False)
    db.close()

    resp = client.get("/api/config/public")
    assert resp.status_code == 200
    assert resp.json() == {"robot_guide": True, "share": False}
