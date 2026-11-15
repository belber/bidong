import time
import pytest
from sqlalchemy.orm import Session
from app.config import settings


def make_card(client,auth_headers,db_engine):
    from test_transcript import card
    from app.services import config_store,video_download
    key=card(client,auth_headers)
    with Session(db_engine) as db:config_store.set_media_switches(db,True,True,True)
    video_download.announce(db_engine)
    return key


def test_plan_prefers_complete_and_filters_codecs():
    from app.services.video_download import plans_from_data
    dash={'video':[{'qn':80,'codecs':'avc1.640028','url':'https://v.example/v'}], 'audio':[{'qn':30280,'codecs':'mp4a.40.2','url':'https://a.example/a'}]}
    complete={'durl':[{'qn':80,'url':'https://d.example/d.mp4','complete':True,'format':'mp4'}]}
    assert plans_from_data(dash,complete,10)[0]['mode']=='direct'
    assert plans_from_data(dash,{},10)[0]['mode']=='mux'
    assert plans_from_data({'video':[{'qn':80,'codecs':'hev1','url':'x'}],'audio':dash['audio']},{},10)==[]
    assert plans_from_data({'video':dash['video'],'audio':[]},{},10)[0]['has_audio'] is False


def test_submit_read_and_ownership(client,auth_headers,db_engine,monkeypatch):
    from app.services import video_download as service
    from app.models import VideoDownloadJob
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda card,qn=None:[{'qn':64,'label':'720P','mode':'mux','has_audio':True,'estimated_size':100}])
    url=f'/api/cards/{key}/video-download'
    assert client.get(url,headers=auth_headers).json()['status']=='idle'
    a=client.post(url,json={'qn':64},headers=auth_headers);b=client.post(url,json={'qn':64},headers=auth_headers)
    assert a.status_code==b.status_code==202
    assert a.json()['id']==b.json()['id']
    with Session(db_engine) as db:assert db.query(VideoDownloadJob).count()==1
    assert client.get(url).status_code==401
    other=client.post('/api/login',json={'code':'other-video-owner'}).json()['access_token']
    assert client.get(url,headers={'Authorization':'Bearer '+other}).status_code==404


def test_file_expiry_and_reprepare(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.services import video_download as service
    from app.models import VideoDownloadJob
    monkeypatch.setattr(settings,'video_download_cache_dir',str(tmp_path))
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda card,qn=None:[{'qn':64,'label':'720P','mode':'mux','has_audio':True,'estimated_size':100}])
    url=f'/api/cards/{key}/video-download'
    job_id=client.post(url,json={'qn':64},headers=auth_headers).json()['id']
    path=tmp_path/f'{job_id}.mp4';path.write_bytes(b'mp4-test')
    with Session(db_engine) as db:
        job=db.get(VideoDownloadJob,job_id);job.status='ready';job.expires_at=int(time.time())+60;job.size_bytes=8;db.commit()
    data=client.get(url,params={'qn':64},headers=auth_headers).json()
    assert data['status']=='ready' and data['size_bytes']==8
    file=client.get(data['file_url'],headers=auth_headers)
    assert file.status_code==200 and file.content==b'mp4-test'
    assert client.get(data['file_url']).status_code==401
    path.unlink()
    assert client.get(url,params={'qn':64},headers=auth_headers).json()['status']=='expired'
    assert client.post(url,json={'qn':64},headers=auth_headers).status_code==202


def test_clean_switch_enforced(client,auth_headers,db_engine):
    from app.services import config_store
    key=make_card(client,auth_headers,db_engine)
    with Session(db_engine) as db:config_store.set_media_switches(db,True,False,True)
    assert client.post(f'/api/cards/{key}/video-download',json={},headers=auth_headers).status_code==403


def test_direct_download_does_not_need_worker_or_apply_mux_limit(client,auth_headers,db_engine,monkeypatch):
    from test_transcript import card
    from app.services import video_download as service, config_store,media_download
    key=card(client,auth_headers)
    with Session(db_engine) as db:config_store.set_media_switches(db,True,True,True)
    monkeypatch.setattr(service,'resolve_plans',lambda card,qn=None:[{'qn':80,'mode':'direct','has_audio':None,'estimated_size':2**31,'stream':{'url':'https://example.com/v.mp4'}}])
    monkeypatch.setattr(media_download,'build_candidates',lambda *a,**k:[{'url':'https://example.com/v.mp4','configured':True}])
    response=client.post(f'/api/cards/{key}/video-download',json={},headers=auth_headers)
    assert response.status_code==200 and response.json()['mode']=='direct'


def test_limits_failure_retry_and_global_claim(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.services import video_download as service
    from app.models import VideoDownloadJob as Job
    monkeypatch.setattr(settings,'video_download_cache_dir',str(tmp_path))
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda card,qn=None:[{'qn':qn or 64,'mode':'mux','has_audio':True,'estimated_size':100}])
    url=f'/api/cards/{key}/video-download'
    first=client.post(url,json={'qn':64},headers=auth_headers).json()
    assert client.post(url,json={'qn':80},headers=auth_headers).status_code==429
    a=service.claim(db_engine,'first');assert a==first['id']
    assert service.claim(db_engine,'second') is None
    # Audio/network error must fail rather than become a silent success.
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[{'mode':'mux','video':{},'audio':{},'has_audio':True}])
    fetched=[]
    def fetch(stream,target,deadline,budget):
        fetched.append(target.name)
        if target.name=='audio':raise RuntimeError('audio network error')
        target.write_bytes(b'video');return 5
    monkeypatch.setattr(service,'fetch_stream',fetch)
    service.prepare(db_engine,a,'first')
    assert fetched==['video','audio']
    assert client.get(url,headers=auth_headers).json()['status']=='failed'
    assert list((tmp_path/'.tmp').iterdir())==[]
    with Session(db_engine) as db:assert db.get(Job,a).has_audio is True
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[{'qn':64,'mode':'mux','has_audio':True,'estimated_size':100}])
    assert client.post(url,json={},headers=auth_headers).status_code==202


def test_cache_cleanup_and_active_transfer_protection(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.services import video_download as service
    from app.models import VideoDownloadJob as Job
    monkeypatch.setattr(settings,'video_download_cache_dir',str(tmp_path))
    monkeypatch.setattr(settings,'video_download_cache_max_bytes',12)
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[{'qn':64,'mode':'mux','has_audio':True,'estimated_size':8}])
    job_id=client.post(f'/api/cards/{key}/video-download',json={},headers=auth_headers).json()['id']
    file=tmp_path/f'{job_id}.mp4';file.write_bytes(b'12345678')
    from app.errors import AppError
    with Session(db_engine) as db:
        j=db.get(Job,job_id);j.status='ready';j.expires_at=int(time.time())+100;j.serve_until=int(time.time())+100;db.commit()
        service.lock(db)
        with pytest.raises(AppError):service.cleanup(db,8)
        db.rollback();assert file.exists()
        service.lock(db);j=db.get(Job,job_id);j.serve_until=0;j.expires_at=1;service.cleanup(db);db.commit()
        assert j.status=='expired' and not file.exists()


@pytest.mark.parametrize('silent', [False,True])
def test_actual_ffmpeg_mux_keeps_expected_tracks(client,auth_headers,db_engine,monkeypatch,tmp_path,silent):
    """Actual H.264/AAC bytes from supplied media; network boundary only is replaced."""
    import shutil,subprocess
    from pathlib import Path
    from app.services import video_download as service
    from app.models import VideoDownloadJob as Job
    binary=Path('/Users/hol/bidong/server/var/asr/bin/ffmpeg')
    source=Path('/Users/hol/Downloads/mmexport1794222273281.mp4')
    if not binary.exists() or not source.exists():pytest.skip('local acceptance media unavailable')
    monkeypatch.setattr(settings,'video_download_ffmpeg_bin',str(binary))
    cache=tmp_path/'cache';monkeypatch.setattr(settings,'video_download_cache_dir',str(cache))
    video=tmp_path/'video.mp4';audio=tmp_path/'audio.m4a'
    subprocess.run([str(binary),'-v','error','-y','-i',str(source),'-t','2','-an','-c:v','copy',str(video)],check=True)
    subprocess.run([str(binary),'-v','error','-y','-i',str(source),'-t','2','-vn','-c:a','copy',str(audio)],check=True)
    key=make_card(client,auth_headers,db_engine)
    plan={'qn':64,'mode':'mux','has_audio':not silent,'estimated_size':video.stat().st_size+audio.stat().st_size,'video':{'fixture':str(video)},'audio':{'fixture':str(audio)}}
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[plan])
    def fetch(stream,target,deadline,budget):
        shutil.copyfile(stream['fixture'],target);return target.stat().st_size
    monkeypatch.setattr(service,'fetch_stream',fetch)
    url=f'/api/cards/{key}/video-download';job_id=client.post(url,json={},headers=auth_headers).json()['id']
    assert service.claim(db_engine,'test')==job_id
    service.prepare(db_engine,job_id,'test')
    result=client.get(url,headers=auth_headers).json()
    assert result['status']=='ready',result
    assert result['has_audio'] is (not silent)
    path=cache/f'{job_id}.mp4'
    assert result['size_bytes']==path.stat().st_size
    service.validate(path,not silent,time.monotonic()+15)
    # Decode, rather than just trusting MP4 metadata/track names.
    subprocess.run([str(binary),'-v','error','-i',str(path),'-f','null','-'],check=True)
    assert client.get(result['file_url'],headers=auth_headers).content==path.read_bytes()
    assert list((cache/'.tmp').iterdir())==[]


def test_timeout_and_stale_worker_recovery(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.services import video_download as service
    from app.models import VideoDownloadJob as Job,VideoDownloadQueue as Queue
    monkeypatch.setattr(settings,'video_download_cache_dir',str(tmp_path))
    key=make_card(client,auth_headers,db_engine)
    plan={'qn':64,'mode':'mux','has_audio':True,'estimated_size':1,'video':{},'audio':{}}
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[plan])
    url=f'/api/cards/{key}/video-download'
    job_id=client.post(url,json={},headers=auth_headers).json()['id']
    assert service.claim(db_engine,'stale')==job_id
    with Session(db_engine) as db:
        q=db.get(Queue,1);q.lease_until=0;db.commit()
    assert service.claim(db_engine,'replacement')==job_id
    with Session(db_engine) as db:assert db.get(Job,job_id).recoveries==1
    monkeypatch.setattr(service,'fetch_stream',lambda *a: (_ for _ in ()).throw(TimeoutError()))
    service.prepare(db_engine,job_id,'replacement')
    state=client.get(url,headers=auth_headers).json()
    assert state['status']=='failed' and '超时' in state['error']
    assert list((tmp_path/'.tmp').iterdir())==[]


def test_waiting_queue_cap(client,auth_headers,db_engine,monkeypatch):
    from app.services import video_download as service
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[{'qn':64,'mode':'mux','has_audio':False,'estimated_size':1}])
    for i in range(10):
        token=client.post('/api/login',json={'code':f'dev_queue_user_{i}'}).json()['access_token']
        headers={'Authorization':'Bearer '+token}
        other=make_card(client,headers,db_engine)
        assert client.post(f'/api/cards/{other}/video-download',json={},headers=headers).status_code==202
    assert client.post(f'/api/cards/{key}/video-download',json={},headers=auth_headers).status_code==429


def test_incompatible_audio_is_not_a_silent_video():
    from app.services.video_download import plans_from_data
    video={'qn':80,'codecs':'avc1','url':'v'}
    assert plans_from_data({'video':[video],'audio':[{'codecs':'ec-3','url':'a'}]}, {}, 10)==[]
    assert plans_from_data({}, {'durl':[{'qn':80,'complete':False,'format':'mp4','url':'v.mp4'}]},10)==[]


def test_expiry_state_is_checked_under_queue_lock(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.services import video_download as service
    from app.models import VideoDownloadJob as Job
    monkeypatch.setattr(settings,'video_download_cache_dir',str(tmp_path))
    key=make_card(client,auth_headers,db_engine)
    monkeypatch.setattr(service,'resolve_plans',lambda *a:[{'qn':64,'mode':'mux','has_audio':True,'estimated_size':1}])
    url=f'/api/cards/{key}/video-download'
    jid=client.post(url,json={},headers=auth_headers).json()['id']
    with Session(db_engine) as db:
        job=db.get(Job,jid);job.status='ready';job.expires_at=1;db.commit()
    original=service.lock;calls=[]
    def lock(db):calls.append(True);return original(db)
    monkeypatch.setattr(service,'lock',lock)
    assert client.get(url,headers=auth_headers).json()['status']=='expired'
    assert calls, 'expiry must not race a newly requeued task'


@pytest.mark.anyio
async def test_api_logging_does_not_buffer_video_bytes():
    from starlette.requests import Request
    from starlette.responses import StreamingResponse
    from app.main import log_requests
    read=[]
    async def chunks():
        read.append(True);yield b'video-chunk'
    response=StreamingResponse(chunks(),media_type='video/mp4')
    async def next(request):return response
    scope={'type':'http','method':'GET','path':'/api/cards/1/video-download/file','query_string':b'','headers':[]}
    actual=await log_requests(Request(scope),next)
    assert not read, 'middleware must not accumulate a complete video in API memory'
    assert actual is response


def test_direct_plan_keeps_confirmed_silent_source_information():
    from app.services.video_download import plans_from_data
    video={'qn':80,'codecs':'avc1','url':'video'}
    complete={'durl':[{'qn':80,'complete':True,'format':'mp4','url':'full.mp4'}]}
    assert plans_from_data({'video':[video],'audio':[]},complete,10)[0]['has_audio'] is False
