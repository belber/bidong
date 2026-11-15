"""Isolated CPU SenseVoice process with bounded audio windows and CTC timing.

Heavy imports occur only in main(), never in the API or idle worker.
"""
import argparse
import json
import math
from pathlib import Path
import re
import wave


def windows(duration, spans, seconds=12, context=1):
    if seconds <= 0 or seconds > 30 or context < 0 or context > 2:
        raise ValueError('invalid bounded audio window')
    start = 0.
    while start < duration:
        end = min(duration, start + seconds)
        if any(a < end and b > start for a, b in spans):
            yield start, end, max(0, start-context), min(duration, end+context)
        start = end


def timed_segments(tokens, timestamps, duration):
    if len(tokens) != len(timestamps) or (tokens and not timestamps):
        raise ValueError('model did not return aligned token timestamps')
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid audio duration')
    points = []
    previous = -1.
    for token, timestamp in zip(tokens, timestamps):
        t = float(timestamp)
        if not math.isfinite(t) or t < previous or t < 0:
            raise ValueError('invalid token timestamp')
        previous = t
        text = str(token).replace('▁', ' ')
        if t >= duration or re.fullmatch(r'<\|.*\|>', text):
            continue
        if text:
            points.append((text,t))
    output, text, start = [], '', None
    for i, (token,t) in enumerate(points):
        if start is None:
            start = t
        text += token
        next_time = points[i+1][1] if i+1 < len(points) else duration
        if re.search(r'[，。！？；,.!?;]$',token) or len(text) >= 24 or next_time-t >= .7 or i+1 == len(points):
            end = min(duration, next_time)
            if text.strip() and end > start:
                output.append({'start':round(start,3),'end':round(end,3),'text':text.strip()})
            text, start = '', None
    return output


def main():
    parser = argparse.ArgumentParser()
    for key in ('audio','output','spans','model','tokens'):
        parser.add_argument('--'+key,required=True)
    parser.add_argument('--language',default='zh')
    parser.add_argument('--chunk-seconds',type=int,default=12)
    parser.add_argument('--context-seconds',type=float,default=1.)
    args = parser.parse_args()
    import numpy as np
    import sherpa_onnx
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=args.model, tokens=args.tokens, language='' if args.language == 'auto' else args.language,
        num_threads=1, use_itn=True, provider='cpu', debug=False)
    spans = json.loads(Path(args.spans).read_text())
    tokens, timestamps = [], []
    with wave.open(args.audio,'rb') as audio:
        if audio.getframerate() != 16000 or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError('expected mono 16kHz PCM16 WAV')
        rate = audio.getframerate()
        duration = audio.getnframes()/rate
        for core_start,core_end,start,end in windows(duration,spans,args.chunk_seconds,args.context_seconds):
            audio.setpos(int(start*rate))
            raw = audio.readframes(math.ceil((end-start)*rate))
            samples = np.frombuffer(raw,dtype=np.int16).astype(np.float32)/32768
            stream = recognizer.create_stream()
            stream.accept_waveform(rate,samples)
            recognizer.decode_stream(stream)
            result = stream.result
            if len(result.tokens) != len(result.timestamps):
                raise ValueError('SenseVoice CTC timing is missing')
            for token,relative in zip(result.tokens,result.timestamps):
                absolute = start+float(relative)
                # Keep only each window's owned core; overlap gives context without duplicate text.
                if core_start <= absolute < core_end:
                    tokens.append(token);timestamps.append(absolute)
            del result,stream,samples,raw
    segments = timed_segments(tokens,timestamps,duration)
    Path(args.output).write_text(json.dumps(segments,ensure_ascii=False))


if __name__ == '__main__':
    main()
