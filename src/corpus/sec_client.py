from __future__ import annotations
import json, time, hashlib, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
_SESSION = requests.Session()
_SESSION.headers.update({'User-Agent': C.SEC_UA, 'Accept-Encoding': 'gzip, deflate'})
_LAST = [0.0]

def _throttle():
    dt = time.time() - _LAST[0]
    if dt < C.SEC_RATE_DELAY:
        time.sleep(C.SEC_RATE_DELAY - dt)
    _LAST[0] = time.time()

def get(url: str, cache_dir: Path | None=None, binary: bool=False, retries: int=4):
    cache_dir = cache_dir or C.CACHE / 'sec'
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    path = cache_dir / (key + ('.bin' if binary else '.txt'))
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes() if binary else path.read_text(encoding='utf-8', errors='ignore')
    last_err = None
    for attempt in range(retries):
        try:
            _throttle()
            r = _SESSION.get(url, timeout=(15, 45), stream=True)
            if r.status_code == 200:
                deadline = time.time() + 150
                buf = bytearray()
                for chunk in r.iter_content(65536):
                    buf.extend(chunk)
                    if time.time() > deadline:
                        raise requests.RequestException('transfer deadline exceeded')
                r.close()
                path.write_bytes(bytes(buf))
                return bytes(buf) if binary else bytes(buf).decode('utf-8', errors='ignore')
            if r.status_code in (403, 429, 500, 502, 503):
                time.sleep(2 ** attempt)
                last_err = f'HTTP {r.status_code}'
                continue
            raise RuntimeError(f'{url} -> HTTP {r.status_code}')
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f'failed {url}: {last_err}')

def get_json(url: str):
    return json.loads(get(url))

def ticker_to_cik() -> dict[str, str]:
    d = get_json('https://www.sec.gov/files/company_tickers.json')
    return {v['ticker'].upper(): f"{int(v['cik_str']):010d}" for v in d.values()}
