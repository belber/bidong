import httpx
import pytest
from app.errors import AppError
from app.services.media_stream import open_stream

def test_backup_after_connection_failure_and_no_proxy(monkeypatch):
    real = httpx.Client
    def handle(req):
        if req.url.host == 'bad.example': raise httpx.ConnectError('failed')
        return httpx.Response(200, content=b'audio')
    def client(**kw):
        assert kw['trust_env'] is False
        return real(transport=httpx.MockTransport(handle), **kw)
    monkeypatch.setattr(httpx, 'Client', client)
    iterator, headers = open_stream(['https://bad.example/a','https://good.example/a'], {})
    assert b''.join(iterator) == b'audio'

def test_empty_upstream_never_succeeds(monkeypatch):
    real=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'')),**kw))
    with pytest.raises(AppError): open_stream(['https://good.example/a'],{})
