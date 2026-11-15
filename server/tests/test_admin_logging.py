import logging


def test_admin_logs_never_include_credentials(admin_client, monkeypatch, caplog):
    monkeypatch.setattr('app.routers.admin_douyin._health', lambda db: {'ok': True, 'bytes': 4096})
    with caplog.at_level(logging.INFO, logger='bidong'):
        login=admin_client.post('/api/admin/login',json={'password':'admin-dev-password'})
        token=login.json()['token']
        response=admin_client.post('/api/admin/douyin/cookie',
            json={'cookie':'sessionid=private-cookie-test-value; sid_tt=test; uid_tt=test'},
            headers={'Authorization':'Bearer '+token})
    assert response.status_code==200
    assert 'private-cookie-test-value' not in caplog.text
    assert 'admin-dev-password' not in caplog.text
    assert token not in caplog.text
    assert '/api/admin/douyin/cookie' in caplog.text
