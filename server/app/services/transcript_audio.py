"""Bounded temporary audio pipeline. Heavy dependencies are imported only by worker."""
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import sys
import time
from urllib.parse import urlparse
import wave
import httpx
from ..config import settings
from ..errors import AppError


def process(args, timeout):
    env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, env=env)
    try:
        out, err = child.communicate(timeout=timeout)
        if child.returncode:
            raise AppError(502, '音频处理未完成，请稍后重试')
        return out
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
        raise


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
        raise AppError(502, '媒体地址不可用')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise AppError(502, '媒体地址不可用')
    return url


def media_candidates(data):
    if data['platform'] == 'douyin':
        from ..db import SessionLocal
        from .douyin_provider import build_douyin_provider
        from .douyin import meta_from_detail
        with SessionLocal() as db:
            provider = build_douyin_provider(db)
            try:
                meta = meta_from_detail(provider.fetch_detail(data['bvid']))
            finally:
                provider.close()
        if meta.kind == 'note':
            raise AppError(422, '图文作品暂不支持文案提取')
        if meta.duration > settings.transcript_max_seconds:
            raise AppError(422, '语音识别仅支持30分钟以内的视频')
        # music.play_url is BGM, NOT the video's spoken audio. Always use video here.
        return meta.video_urls, {'User-Agent':'Mozilla/5.0', 'Referer':'https://www.douyin.com/'}
    from .bilibili import BiliClient, UA
    c = BiliClient()
    try:
        play = c.get_playurl(data['bvid'], data['cid'])
        streams = sorted(play.get('audio', []), key=lambda s: s.get('qn',0))
        if not streams:
            streams = c.get_durl(data['bvid'], data['cid'])
        urls = [url for s in streams for url in [s.get('url'), *s.get('backup_urls', [])] if url]
    finally:
        c.close()
    return urls, {'User-Agent':UA, 'Referer':'https://www.bilibili.com/'}


def download_audio(data, directory):
    urls, headers = media_candidates(data)
    path = directory/'source.media'
    deadline = time.monotonic()+300
    for initial in urls[:4]:
        try:
            url = initial
            with httpx.Client(timeout=20, headers=headers, follow_redirects=False, trust_env=False) as client:
                for _ in range(6):
                    try:
                        public_url(url)
                    except AppError:
                        # Reject this candidate without skipping safe backup URLs.
                        break
                    with client.stream('GET', url) as response:
                        if response.is_redirect:
                            url = str(response.url.join(response.headers['location']))
                            continue
                        response.raise_for_status()
                        if int(response.headers.get('content-length',0)) > settings.transcript_max_bytes:
                            raise AppError(422, '音视频文件过大，暂不支持提取')
                        total = 0
                        with path.open('wb') as f:
                            for chunk in response.iter_bytes(65536):
                                total += len(chunk)
                                if total > settings.transcript_max_bytes:
                                    raise AppError(422, '音视频文件过大，暂不支持提取')
                                if time.monotonic() > deadline:
                                    raise AppError(504, '音轨获取超时，请重试')
                                f.write(chunk)
                        if total:
                            return path
                        break
        except AppError:
            raise
        except (httpx.HTTPError, OSError, ValueError):
            continue
    raise AppError(502, '暂时无法获取视频音轨，请稍后重试')


def normalize_audio(path, directory):
    target = directory/'audio.wav'
    process([settings.transcript_ffmpeg_bin, '-nostdin', '-v','error', '-y',
             '-protocol_whitelist','file,pipe', '-i',str(path), '-vn', '-ac','1', '-ar','16000',
             '-t',str(settings.transcript_max_seconds+1), '-c:a','pcm_s16le',str(target)], 300)
    with wave.open(str(target),'rb') as audio:
        duration = audio.getnframes()/audio.getframerate()
    if duration > settings.transcript_max_seconds:
        raise AppError(422, '语音识别仅支持30分钟以内的视频')
    return target


def detect_speech(path):
    # Run VAD separately so ORT/NumPy allocations are gone before loading the ASR model.
    output = process([sys.executable, '-m', 'app.services.transcript_audio',
                      '--vad-audio', str(path), '--vad-model', settings.transcript_vad_path], 300)
    return json.loads(output)


def _detect_speech_in_process(path):
    import numpy as np
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1; options.inter_op_num_threads = 1
    session = ort.InferenceSession(settings.transcript_vad_path, sess_options=options, providers=['CPUExecutionProvider'])
    state = np.zeros((2,1,128),dtype=np.float32)
    context = np.zeros((1,64),dtype=np.float32)
    spans, start, end, frame = [], None, 0., 0
    with wave.open(str(path),'rb') as audio:
        while raw := audio.readframes(512):
            chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32)/32768
            if chunk.size < 512:
                chunk = np.pad(chunk,(0,512-chunk.size))
            chunk = chunk.reshape(1,512)
            probability, state = session.run(None, {'input':np.concatenate([context,chunk],axis=1), 'state':state, 'sr':np.array(16000,dtype=np.int64)})
            context = chunk[:,-64:]
            t = frame/16000
            if float(probability[0,0]) >= .5:
                if start is None: start = t
                end = t+.032
            elif start is not None and t-end >= .35:
                if end-start >= .25: spans.append((max(0,start-.2),end+.2))
                start = None
            frame += 512
    if start is not None and end-start >= .25:
        spans.append((max(0,start-.2),end+.2))
    return spans


def run_whisper(path, directory, timeout):
    output = directory/'transcript'
    process([settings.transcript_whisper_bin, '-m',settings.transcript_model_path, '-f',str(path),
             '-l',settings.transcript_language, '-t','1', '-ng', '-oj', '-of',str(output)], timeout)
    payload = json.loads(output.with_suffix('.json').read_text())
    segments = []
    for entry in payload.get('transcription',[]):
        offsets = entry.get('offsets',{})
        text = entry.get('text','').strip()
        start, end = float(offsets.get('from',0))/1000, float(offsets.get('to',0))/1000
        if text and not re.fullmatch(r'[\[（(【].*[\]）)】]',text) and end > start:
            segments.append({'start':start,'end':end,'text':text})
    return segments


def recognize(data):
    if not settings.transcript_asr_enabled:
        raise AppError(503, '暂无平台字幕，语音识别服务暂未开放')
    root = Path(settings.transcript_temp_dir)
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < 512*1024*1024:
        raise AppError(503, '文案服务暂时繁忙，请稍后再试')
    if not Path(settings.transcript_vad_path).is_file():
        raise AppError(503, '语音检测模型尚未就绪')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='job-', dir=root) as temp:
        directory = Path(temp)
        path = normalize_audio(download_audio(data,directory),directory)
        spans = detect_speech(path)
        if not spans:
            return []
        remaining = max(1, settings.transcript_timeout_seconds-(time.monotonic()-started))
        if settings.transcript_engine == 'sensevoice':
            if not all(Path(p).is_file() for p in (settings.transcript_sensevoice_model_path, settings.transcript_sensevoice_tokens_path)):
                raise AppError(503, '语音识别模型尚未就绪')
            segments = run_sensevoice(path, directory, remaining, spans)
        else:
            if not Path(settings.transcript_model_path).is_file():
                raise AppError(503, '语音识别模型尚未就绪')
            segments = run_whisper(path, directory, remaining)
        # Discard any recognition outside VAD speech spans (music/silence hallucination guard).
        return [s for s in segments if any(s['start'] < end and s['end'] > start for start,end in spans)]


def run_sensevoice(path, directory, timeout, spans):
    output = directory / 'sensevoice.json'
    span_file = directory / 'speech-spans.json'
    span_file.write_text(json.dumps(spans))
    process([sys.executable, '-m', 'app.services.sensevoice',
             '--audio', str(path), '--output', str(output), '--spans', str(span_file),
             '--model', settings.transcript_sensevoice_model_path,
             '--tokens', settings.transcript_sensevoice_tokens_path,
             '--language', settings.transcript_language,
             '--chunk-seconds', str(settings.transcript_chunk_seconds),
             '--context-seconds', str(settings.transcript_chunk_context_seconds)], timeout)
    return json.loads(output.read_text())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--vad-audio', required=True)
    parser.add_argument('--vad-model', required=True)
    args = parser.parse_args()
    settings.transcript_vad_path = args.vad_model
    print(json.dumps(_detect_speech_in_process(Path(args.vad_audio))))
