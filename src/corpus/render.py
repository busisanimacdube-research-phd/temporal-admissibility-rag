from __future__ import annotations
import json, sys, subprocess, os, hashlib, traceback, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
DPI = 150

def filing_dir(f) -> Path:
    return C.FILINGS / f['ticker'] / f['accession']

def _pdf_complete(p: Path) -> bool:
    try:
        if p.stat().st_size < 2000:
            return False
        with p.open('rb') as fh:
            fh.seek(-2048, 2)
            return b'%%EOF' in fh.read()
    except OSError:
        return False

def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    if _pdf_complete(pdf_path):
        return True
    prof = Path(os.environ.get('TMPDIR', '/tmp')) / ('cr_' + hashlib.sha1(str(pdf_path).encode()).hexdigest()[:10])
    cmd = [CHROME, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', f'--user-data-dir={prof}', '--no-pdf-header-footer', f'--print-to-pdf={pdf_path}', html_path.as_uri()]
    dn = subprocess.DEVNULL
    mb = html_path.stat().st_size / 1000000.0
    budget = min(900, max(180, 60 * mb))
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=dn, stdout=dn, stderr=dn, start_new_session=True)
        t0, last_size, stable = (time.time(), -1, 0.0)
        while time.time() - t0 < budget:
            if proc.poll() is not None:
                break
            time.sleep(2)
            sz = pdf_path.stat().st_size if pdf_path.exists() else 0
            if sz > 0 and sz == last_size:
                stable += 2
                if stable >= 8 and _pdf_complete(pdf_path):
                    break
            else:
                stable = 0
            last_size = sz
    except Exception:
        return False
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=20)
            except Exception:
                pass
        subprocess.run(['rm', '-rf', str(prof)], stdout=dn, stderr=dn)
    return _pdf_complete(pdf_path)

def extract_streams(pdf_path: Path, out_dir: Path) -> dict:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    img_dir = out_dir / 'pages'
    img_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for pno in range(doc.page_count):
        page = doc[pno]
        text = page.get_text('text')
        tables = []
        try:
            for t in page.find_tables().tables:
                rows = t.extract()
                if not rows or len(rows) < 2:
                    continue
                tables.append({'bbox': list(t.bbox), 'n_rows': len(rows), 'n_cols': max((len(r) for r in rows)), 'rows': [[('' if c is None else str(c))[:200] for c in r] for r in rows[:60]]})
        except Exception:
            pass
        img_path = img_dir / f'p{pno + 1:04d}.png'
        if not img_path.exists():
            pix = page.get_pixmap(dpi=DPI)
            pix.save(img_path)
        pages.append({'page': pno + 1, 'text': text, 'n_chars': len(text), 'tables': tables, 'image': str(img_path.relative_to(C.FILINGS)), 'width': page.rect.width, 'height': page.rect.height})
    doc.close()
    return {'n_pages': len(pages), 'pages': pages}

def process(f) -> dict | None:
    d = filing_dir(f)
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / 'streams.json'
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text())
            if m.get('n_pages', 0) > 0:
                return m
        except Exception:
            pass
    html_path = d / 'primary.htm'
    if not html_path.exists():
        html_path.write_text(get(f['url']), encoding='utf-8')
    pdf_path = d / 'filing.pdf'
    if not html_to_pdf(html_path, pdf_path):
        return None
    streams = extract_streams(pdf_path, d)
    streams.update({k: f[k] for k in ('ticker', 'cik', 'company', 'form', 'accession', 'filing_date', 'acceptance_datetime', 'report_date', 'url')})
    meta_path.write_text(json.dumps(streams))
    return streams

def main():
    idx = json.loads((C.RAW / 'filing_index.json').read_text())
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        idx = [f for f in idx if f['ticker'] == only]
    ok = fail = pages = tables = 0
    for i, f in enumerate(idx, 1):
        try:
            m = process(f)
        except Exception:
            print(f"  ERR {f['ticker']} {f['accession']}: {traceback.format_exc(limit=1)}", flush=True)
            m = None
        if m:
            ok += 1
            pages += m['n_pages']
            tables += sum((len(p['tables']) for p in m['pages']))
        else:
            fail += 1
        if i % 10 == 0 or i == len(idx):
            print(f'[{i}/{len(idx)}] ok={ok} fail={fail} pages={pages} tables={tables}', flush=True)
    print(f'DONE ok={ok} fail={fail} pages={pages} tables={tables}')
if __name__ == '__main__':
    main()
