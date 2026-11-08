from __future__ import annotations
import json, sys, time, hashlib, base64, threading, io
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
_S = requests.Session()
_LOCK = threading.Lock()
CACHE_DIR = C.CACHE / 'llm'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _ck(kind: str, payload: dict) -> Path:
    h = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return CACHE_DIR / f'{kind}-{h}.json'

def embed(texts: list[str], model: str=C.EMBED, use_cache: bool=True) -> list[list[float]]:
    out = []
    for t in texts:
        p = _ck('emb', {'m': model, 't': t})
        if use_cache and p.exists():
            out.append(json.loads(p.read_text())['e'])
            continue
        for attempt in range(4):
            try:
                r = _S.post(f'{C.OLLAMA}/api/embed', json={'model': model, 'input': t}, timeout=180)
                r.raise_for_status()
                e = r.json()['embeddings'][0]
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        if use_cache:
            p.write_text(json.dumps({'e': e}))
        out.append(e)
    return out
VISION_MAX_PX = 768
_IMG_CACHE = C.CACHE / 'img'
_IMG_CACHE.mkdir(parents=True, exist_ok=True)

def _prepare_image(path: str) -> str:
    p = Path(path)
    key = hashlib.sha1(f'{p}|{VISION_MAX_PX}'.encode()).hexdigest()[:20]
    cp = _IMG_CACHE / f'{key}.b64'
    if cp.exists():
        return cp.read_text()
    from PIL import Image
    im = Image.open(p)
    if max(im.size) > VISION_MAX_PX:
        im = im.convert('RGB')
        im.thumbnail((VISION_MAX_PX, VISION_MAX_PX * 2), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=88, optimize=True)
        data = buf.getvalue()
    else:
        data = p.read_bytes()
    b64 = base64.b64encode(data).decode()
    cp.write_text(b64)
    return b64

def generate(prompt: str, model: str=C.READER_TEXT, images: list[str] | None=None, temperature: float=0.0, num_ctx: int=C.NUM_CTX, max_tokens: int=512, use_cache: bool=True) -> str:
    imgs_b64 = [_prepare_image(ip) for ip in images or []]
    key = {'m': model, 'p': prompt, 't': temperature, 'c': num_ctx, 'n': max_tokens, 'i': [hashlib.sha1(x.encode()).hexdigest()[:16] for x in imgs_b64]}
    p = _ck('gen', key)
    if use_cache and p.exists():
        return json.loads(p.read_text())['r']
    body = {'model': model, 'prompt': prompt, 'stream': False, 'options': {'temperature': temperature, 'num_ctx': num_ctx, 'num_predict': max_tokens, 'seed': C.SEED}}
    if imgs_b64:
        body['images'] = imgs_b64
    for attempt in range(4):
        try:
            r = _S.post(f'{C.OLLAMA}/api/generate', json=body, timeout=1200)
            r.raise_for_status()
            txt = r.json().get('response', '')
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    if use_cache:
        p.write_text(json.dumps({'r': txt}))
    return txt

def warm(models=(C.READER_TEXT, C.EMBED, C.READER_VL)):
    for m in models:
        try:
            _S.post(f'{C.OLLAMA}/api/generate', json={'model': m, 'prompt': 'ok', 'stream': False, 'options': {'num_predict': 1, 'num_ctx': C.NUM_CTX}}, timeout=600)
        except Exception as e:
            print(f'  warm {m}: {e}')
