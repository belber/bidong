import json
import pytest
from app.models import VideoCard
from app.time import utcnow_naive


def card(client, auth_headers):
    # Use actual API ownership setup without calling upstream media platforms.
    from app.deps import get_current_user
    from app.db import get_db
    from app.main import app
    from app.security import decode_user_id
    user_id = decode_user_id(auth_headers['Authorization'].split()[1])
    db = next(app.dependency_overrides[get_db]())
    from app.services.transcript import announce
    announce(db.bind)
    row = VideoCard(user_id=user_id, bvid='BV1xx411c7mD', platform='bilibili',
                    title='口播测试', up_name='作者', cover_url='', source_url='https://www.bilibili.com/video/BV1xx411c7mD',
                    duration=30, cid=99, month='2026-11', collected_at=utcnow_naive())
    db.add(row); db.commit(); db.refresh(row)
    key = row.id
    db.close()
    return key


def test_read_is_idle_and_does_not_enqueue(client, auth_headers, db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob
    key = card(client, auth_headers)
    r = client.get(f'/api/cards/{key}/transcript', headers=auth_headers)
    assert r.status_code == 200
    assert r.json()['status'] == 'idle'
    with Session(db_engine) as db:
        assert db.query(TranscriptJob).count() == 0


def test_submit_idempotent_and_owned(client, auth_headers, db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob
    key = card(client, auth_headers)
    path = f'/api/cards/{key}/transcript'
    a = client.post(path, headers=auth_headers)
    b = client.post(path, headers=auth_headers)
    assert a.status_code == b.status_code == 202
    assert a.json()['id'] == b.json()['id']
    assert client.get(path).status_code == 401
    other = client.post('/api/login', json={'code': 'another-person'}).json()['access_token']
    assert client.get(path, headers={'Authorization': 'Bearer '+other}).status_code == 404
    with Session(db_engine) as db:
        assert db.query(TranscriptJob).count() == 1


def test_completed_exports_use_real_timestamps(client, auth_headers, db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob
    key = card(client, auth_headers)
    path = f'/api/cards/{key}/transcript'
    client.post(path, headers=auth_headers)
    with Session(db_engine) as db:
        job = db.query(TranscriptJob).one()
        job.status = 'completed'
        job.segments_json = json.dumps([{'start': 1.25, 'end': 3.7, 'text': '你好，世界。'}])
        db.commit()
    txt = client.get(path+'/export?format=txt', headers=auth_headers)
    srt = client.get(path+'/export?format=srt', headers=auth_headers)
    assert txt.status_code == srt.status_code == 200
    assert txt.text == '你好，世界。'
    assert '00:00:01,250 --> 00:00:03,700' in srt.text
    assert client.get(path+'/export?format=exe', headers=auth_headers).status_code == 422


def test_worker_platform_subtitles_without_asr(client, auth_headers, db_engine, monkeypatch):
    from app.services import transcript
    key = card(client, auth_headers)
    client.post(f'/api/cards/{key}/transcript', headers=auth_headers)
    monkeypatch.setattr(transcript, 'platform_subtitles', lambda data: [{'start': i, 'end': i+0.5, 'text': str(i)} for i in range(601)])
    monkeypatch.setattr(transcript, 'recognize', lambda *a: pytest.fail('ASR must not run'))
    assert transcript.work_once(db_engine)
    r = client.get(f'/api/cards/{key}/transcript', headers=auth_headers).json()
    assert r['status'] == 'completed'
    assert r['source'] == 'platform'
    assert len(r['segments']) == 601


def test_silence_skips_whisper(tmp_path, monkeypatch):
    from app.services import transcript_audio as audio
    from app.config import settings
    monkeypatch.setattr(settings, 'transcript_asr_enabled', True)
    monkeypatch.setattr(settings, 'transcript_vad_path', __file__)
    monkeypatch.setattr(audio, 'download_audio', lambda data, directory: directory/'audio.wav')
    monkeypatch.setattr(audio, 'normalize_audio', lambda path, directory: path)
    monkeypatch.setattr(audio, 'detect_speech', lambda path: [])
    monkeypatch.setattr(audio, 'run_whisper', lambda *args: pytest.fail('silence must skip ASR'))
    monkeypatch.setattr(settings, 'transcript_temp_dir', str(tmp_path))
    assert audio.recognize({'duration': 10}) == []
    assert list(tmp_path.iterdir()) == []


def test_missing_worker_is_explicit(client, auth_headers, db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptQueue
    key=card(client,auth_headers)
    with Session(db_engine) as db:
        db.get(TranscriptQueue,1).heartbeat_at=0;db.commit()
    r=client.post(f'/api/cards/{key}/transcript',headers=auth_headers)
    assert r.status_code==503
    assert r.json()['error_type']=='transcript_worker_unavailable'


def test_worker_no_speech_is_cached(client,auth_headers,db_engine,monkeypatch):
    from app.services import transcript
    key=card(client,auth_headers)
    monkeypatch.setattr(transcript,'platform_subtitles',lambda data:[])
    calls=[]
    monkeypatch.setattr(transcript,'recognize',lambda data:calls.append(data) or [])
    path=f'/api/cards/{key}/transcript'
    client.post(path,headers=auth_headers);assert transcript.work_once(db_engine)
    assert client.get(path,headers=auth_headers).json()['status']=='no_speech'
    assert client.post(path,headers=auth_headers).status_code==200
    assert not transcript.work_once(db_engine)
    assert len(calls)==1


@pytest.mark.parametrize('has_subtitles',[True,False])
def test_long_video_uses_subtitles_but_never_asr(client,auth_headers,db_engine,monkeypatch,has_subtitles):
    from sqlalchemy.orm import Session
    from app.services import transcript
    key=card(client,auth_headers)
    with Session(db_engine) as db:
        db.get(VideoCard,key).duration=4000;db.commit()
    monkeypatch.setattr(transcript,'platform_subtitles',lambda data:[{'start':3000,'end':3002,'text':'长视频字幕'}] if has_subtitles else [])
    monkeypatch.setattr(transcript,'recognize',lambda data:pytest.fail('no ASR on long video'))
    path=f'/api/cards/{key}/transcript'
    client.post(path,headers=auth_headers);transcript.work_once(db_engine)
    result=client.get(path,headers=auth_headers).json()
    assert result['status']==('completed' if has_subtitles else 'failed')
    if not has_subtitles:assert '30分钟' in result['error']


def test_queue_and_per_user_limits(client,auth_headers,db_engine,monkeypatch):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob, User
    from app.services import transcript
    from app.errors import AppError
    from app.config import settings
    key=card(client,auth_headers)
    with Session(db_engine,expire_on_commit=False) as db:
        first=db.get(VideoCard,key);user=db.get(User,first.user_id)
        transcript.submit(db,user,first)
        other=VideoCard(user_id=user.id,bvid='different',platform='bilibili',title='另一条',up_name='',cover_url='',source_url='',month='2026-11')
        db.add(other);db.commit()
        with pytest.raises(AppError,match='已有文案'):transcript.submit(db,user,other)
        db.rollback()
        another=User(openid='queue-limit-person');db.add(another);db.commit()
        monkeypatch.setattr(settings,'transcript_queue_limit',1)
        with pytest.raises(AppError,match='任务较多'):transcript.submit(db,another,other)
        db.rollback();assert db.query(TranscriptJob).count()==1


def test_crashed_job_recovers_once(client,auth_headers,db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob,TranscriptQueue
    from app.services import transcript
    key=card(client,auth_headers)
    client.post(f'/api/cards/{key}/transcript',headers=auth_headers)
    with Session(db_engine) as db:
        job=db.query(TranscriptJob).one();job.status='processing';job.recoveries=1
        queue=db.get(TranscriptQueue,1);queue.worker_token='dead';queue.lease_until=0;db.commit()
    assert not transcript.work_once(db_engine)
    result=client.get(f'/api/cards/{key}/transcript',headers=auth_headers).json()
    assert result['status']=='failed' and '中断' in result['error']


def test_active_lease_prevents_another_worker(client,auth_headers,db_engine):
    import time
    from sqlalchemy.orm import Session
    from app.models import TranscriptQueue
    from app.services import transcript
    key=card(client,auth_headers)
    client.post(f'/api/cards/{key}/transcript',headers=auth_headers)
    with Session(db_engine) as db:
        queue=db.get(TranscriptQueue,1);queue.worker_token='live';queue.lease_until=int(time.time())+100;db.commit()
    assert not transcript.work_once(db_engine)
    assert client.get(f'/api/cards/{key}/transcript',headers=auth_headers).json()['status']=='queued'


def test_failed_audio_pipeline_cleans_temporary_files(tmp_path,monkeypatch):
    from app.services import transcript_audio as audio
    from app.config import settings
    monkeypatch.setattr(settings,'transcript_asr_enabled',True)
    monkeypatch.setattr(settings,'transcript_vad_path',__file__)
    monkeypatch.setattr(settings,'transcript_temp_dir',str(tmp_path))
    def download(data,directory):
        path=directory/'audio.media';path.write_bytes(b'fixture');return path
    monkeypatch.setattr(audio,'download_audio',download)
    monkeypatch.setattr(audio,'normalize_audio',lambda *a:(_ for _ in ()).throw(RuntimeError('conversion failed')))
    with pytest.raises(RuntimeError):audio.recognize({'duration':10})
    assert list(tmp_path.iterdir())==[]


def test_douyin_transcript_uses_video_not_bgm(monkeypatch):
    from types import SimpleNamespace
    from app.services import transcript_audio as audio,douyin_provider,douyin
    from app import db
    class Provider:
        def fetch_detail(self,key):return {'id':key}
        def close(self):pass
    class DummySession:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(db,'SessionLocal',DummySession)
    monkeypatch.setattr(douyin_provider,'build_douyin_provider',lambda db:Provider())
    monkeypatch.setattr(douyin,'meta_from_detail',lambda data:SimpleNamespace(kind='video',duration=10,video_urls=['https://video.example/original'],audio_urls=['https://music.example/bgm']))
    urls,headers=audio.media_candidates({'platform':'douyin','bvid':'test'})
    assert urls==['https://video.example/original']


def test_export_not_ready_never_creates_task(client,auth_headers,db_engine):
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob
    key=card(client,auth_headers)
    assert client.get(f'/api/cards/{key}/transcript/export?format=srt',headers=auth_headers).status_code==409
    with Session(db_engine) as db:assert db.query(TranscriptJob).count()==0
