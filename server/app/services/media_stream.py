"""Open and validate CDN data before committing a streaming HTTP response."""
import httpx
from ..errors import AppError


def open_stream(urls, headers):
    for url in dict.fromkeys(urls):
        client = httpx.Client(headers=headers, trust_env=False, follow_redirects=True,
                              timeout=httpx.Timeout(connect=15, read=60, write=60, pool=15))
        response = None
        try:
            response = client.send(client.build_request('GET', url), stream=True)
            response.raise_for_status()
            chunks = response.iter_bytes(chunk_size=65536)
            first = next(chunks)
            if not first:
                raise ValueError('empty media')
        except (httpx.HTTPError, StopIteration, ValueError):
            if response is not None:
                response.close()
            client.close()
            continue
        def generate(response=response, client=client, chunks=chunks, first=first):
            try:
                yield first
                yield from chunks
            finally:
                response.close()
                client.close()
        result_headers = {}
        length = response.headers.get('content-length')
        if length and length.isdigit() and not response.headers.get('content-encoding'):
            result_headers['Content-Length'] = length
        return generate(), result_headers
    raise AppError(502, '音频源连接失败，请稍后重试')
