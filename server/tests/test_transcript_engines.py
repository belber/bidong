from pathlib import Path
from types import SimpleNamespace
import pytest
from app.config import settings
from app.services import transcript,transcript_audio


def test_cache_changes_with_engine_model_and_chunk_settings(monkeypatch):
    card=SimpleNamespace(platform='douyin',bvid='sample',cid=0)
    monkeypatch.setattr(settings,'transcript_engine','whisper')
    first=transcript.key_for(card)
    monkeypatch.setattr(settings,'transcript_engine','sensevoice')
    second=transcript.key_for(card)
    monkeypatch.setattr(settings,'transcript_sensevoice_model_path','/models/new-model.int8.onnx')
    third=transcript.key_for(card)
    assert len({first,second,third})==3


def test_sensevoice_segments_use_ctc_timestamps():
    from app.services.sensevoice import timed_segments
    result=timed_segments(['你','好','，','世','界','。'],[0.2,0.4,0.6,0.8,1.0,1.2],1.4)
    assert ''.join(s['text'] for s in result)=='你好，世界。'
    assert result[0]['start']==pytest.approx(.2)
    assert result[0]['end']==pytest.approx(.8)
    assert result[-1]['end']==pytest.approx(1.4)


def test_missing_ctc_timestamps_fail_instead_of_inventing_time():
    from app.services.sensevoice import timed_segments
    with pytest.raises(ValueError):timed_segments(['你','好'],[],2.)


def test_sensevoice_dispatch_after_vad(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'transcript_asr_enabled',True)
    monkeypatch.setattr(settings,'transcript_engine','sensevoice')
    monkeypatch.setattr(settings,'transcript_temp_dir',str(tmp_path))
    for name in ['transcript_vad_path','transcript_sensevoice_model_path','transcript_sensevoice_tokens_path']:
        monkeypatch.setattr(settings,name,__file__)
    monkeypatch.setattr(transcript_audio,'download_audio',lambda data,d:d/'audio.wav')
    monkeypatch.setattr(transcript_audio,'normalize_audio',lambda path,d:path)
    monkeypatch.setattr(transcript_audio,'detect_speech',lambda path:[(0.,1.)])
    monkeypatch.setattr(transcript_audio,'run_whisper',lambda *a:pytest.fail('wrong engine'))
    expected=[{'start':0.1,'end':1.,'text':'你好'}]
    monkeypatch.setattr(transcript_audio,'run_sensevoice',lambda *args:expected)
    assert transcript_audio.recognize({'duration':1})==expected
    assert list(tmp_path.iterdir())==[]


def test_chunk_windows_are_bounded_and_cover_audio():
    from app.services.sensevoice import windows
    data=list(windows(35,[(0,35)],12,1))
    assert data[0][0]==0
    assert data[-1][1]==35
    assert all(end-start<=14 for _,_,start,end in data)
    assert [(a,b) for a,b,_,_ in data]==[(0,12),(12,24),(24,35)]
    assert list(windows(35,[(25,30)],12,1))==[(24,35,23,35)]


def test_vad_runs_in_subprocess_to_release_memory(monkeypatch,tmp_path):
    calls=[]
    monkeypatch.setattr(transcript_audio,'process',lambda args,timeout:calls.append(args) or b'[[0.1,1.2]]')
    assert transcript_audio.detect_speech(tmp_path/'audio.wav')==[[.1,1.2]]
    assert '--vad-audio' in calls[0]


def test_model_mount_location_does_not_change_cache(monkeypatch):
    card=SimpleNamespace(platform='douyin',bvid='sample',cid=0)
    monkeypatch.setattr(settings,'transcript_sensevoice_model_path','./var/models/sensevoice/model.int8.onnx')
    first=transcript.key_for(card)
    monkeypatch.setattr(settings,'transcript_sensevoice_model_path','/models/sensevoice/model.int8.onnx')
    assert transcript.key_for(card)==first


def test_queued_old_engine_job_is_not_processed_with_new_engine(client,auth_headers,db_engine,monkeypatch):
    from test_transcript import card
    key=card(client,auth_headers)
    client.post(f'/api/cards/{key}/transcript',headers=auth_headers)
    monkeypatch.setattr(settings,'transcript_cache_version','new-model-configuration')
    monkeypatch.setattr(transcript,'platform_subtitles',lambda data:pytest.fail('old config must be rejected first'))
    assert transcript.work_once(db_engine)
    from sqlalchemy.orm import Session
    from app.models import TranscriptJob
    with Session(db_engine) as db:
        job=db.query(TranscriptJob).one()
        assert job.status=='failed'
        assert '配置' in job.error
