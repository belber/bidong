"""Opt-in integration: actual FFmpeg + VAD + Whisper; only media source is local.
ASR_TEST_AUDIO=/absolute/chinese.wav pytest tests/test_transcript_audio_real.py -q
"""
import json
import os
from pathlib import Path
import shutil
import pytest

pytestmark=pytest.mark.skipif(not os.environ.get('ASR_TEST_AUDIO'),reason='requires initialized real ASR models and local speech fixture')


def test_actual_audio_to_queue_and_exports(client,auth_headers,db_engine,monkeypatch,tmp_path):
    from app.config import settings
    from app.services import transcript,transcript_audio
    from test_transcript import card
    monkeypatch.setattr(settings,'transcript_asr_enabled',True)
    monkeypatch.setattr(settings,'transcript_temp_dir',str(tmp_path/'jobs'))
    monkeypatch.setattr(transcript,'platform_subtitles',lambda data:[])
    def source(data,directory):
        dest=directory/'fixture.media'
        shutil.copyfile(os.environ['ASR_TEST_AUDIO'],dest)
        return dest
    monkeypatch.setattr(transcript_audio,'download_audio',source)
    key=card(client,auth_headers)
    url=f'/api/cards/{key}/transcript'
    assert client.post(url,headers=auth_headers).status_code==202
    assert transcript.work_once(db_engine)
    result=client.get(url,headers=auth_headers).json()
    assert result['status']=='completed',result
    assert result['source']=='asr'
    assert any('文案' in s['text'] for s in result['segments'])
    txt=client.get(url+'/export?format=txt',headers=auth_headers)
    srt=client.get(url+'/export?format=srt',headers=auth_headers)
    assert txt.status_code==srt.status_code==200
    assert '文案' in txt.text and '-->' in srt.text
    assert list((tmp_path/'jobs').iterdir())==[]
    output=os.environ.get('ASR_TEST_OUTPUT')
    if output:
        root=Path(output);root.mkdir(parents=True,exist_ok=True)
        (root/'transcript.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        (root/'transcript.txt').write_text(txt.text)
        (root/'transcript.srt').write_text(srt.text)


def test_actual_silence_never_loads_whisper(monkeypatch,tmp_path):
    import wave
    from app.config import settings
    from app.services import transcript_audio
    source_path=tmp_path/'silence.wav'
    with wave.open(str(source_path),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(b'\0\0'*16000*5)
    def source(data,directory):
        dest=directory/'silence.wav';shutil.copyfile(source_path,dest);return dest
    monkeypatch.setattr(settings,'transcript_asr_enabled',True)
    monkeypatch.setattr(settings,'transcript_temp_dir',str(tmp_path/'jobs'))
    monkeypatch.setattr(transcript_audio,'download_audio',source)
    monkeypatch.setattr(transcript_audio,'run_whisper',lambda *a:pytest.fail('silence must not load model'))
    assert transcript_audio.recognize({'duration':5})==[]
    assert list((tmp_path/'jobs').iterdir())==[]
