import httpx
from app.services import transcript_audio as audio
from app.errors import AppError

def test_rejected_candidate_uses_safe_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, 'media_candidates', lambda data: (['https://bad.example:8082/a', 'https://good.example/a'], {}))
    def validate(url):
        if ':8082' in url:
            raise AppError(502, '媒体地址不可用')
        return url
    monkeypatch.setattr(audio, 'public_url', validate)
    real = httpx.Client
    requested = []
    def handle(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b'audio')
    monkeypatch.setattr(audio.httpx, 'Client', lambda **kwargs: real(transport=httpx.MockTransport(handle), **kwargs))
    assert audio.download_audio({}, tmp_path).read_bytes() == b'audio'
    assert requested == ['https://good.example/a']
