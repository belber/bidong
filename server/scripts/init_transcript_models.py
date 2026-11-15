#!/usr/bin/env python3
"""Explicit, verified model initialization; never invoked by API startup."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

VAD = ('silero_vad.onnx',
       'https://raw.githubusercontent.com/snakers4/silero-vad/6478567951ae5c9979ad7b234185b5515f4be7a1/src/silero_vad/data/silero_vad.onnx',
       '2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f')
SENSE_REPO = 'https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/2365baeacb507f821a0c8120fcee3d484dba7a07/'
MODELS = {
    'sensevoice': [
        ('sensevoice/model.int8.onnx', SENSE_REPO+'model.int8.onnx', 'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51'),
        ('sensevoice/tokens.txt', SENSE_REPO+'tokens.txt', 'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc'),
        VAD,
    ],
    'whisper': [
        ('ggml-base-q5_1.bin', 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base-q5_1.bin',
         '422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898'),
        VAD,
    ],
}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory',default='./var/models')
    parser.add_argument('--engine',choices=sorted(MODELS),default='sensevoice')
    parser.add_argument('--mirror',action='store_true',help='Use hf-mirror.com; same SHA256 verification')
    args = parser.parse_args()
    root = Path(args.directory)
    for filename,url,sha in MODELS[args.engine]:
        dest = root/filename
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and digest(dest)==sha:
            print(filename+': verified');continue
        if args.mirror:
            url = url.replace('huggingface.co','hf-mirror.com')
        temp = dest.with_suffix(dest.suffix+'.part')
        try:
            request = urllib.request.Request(url,headers={'User-Agent':'bidong-model-init/2'})
            with urllib.request.urlopen(request,timeout=60) as response,temp.open('wb') as output:
                while chunk:=response.read(1024*1024):
                    output.write(chunk)
            if digest(temp)!=sha:
                raise RuntimeError(filename+': checksum mismatch')
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
        print(filename+': initialized')


if __name__ == '__main__':
    main()
