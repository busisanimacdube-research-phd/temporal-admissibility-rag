from __future__ import annotations
import json, sys, traceback, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get
from corpus.render import html_to_pdf, filing_dir
from corpus.ixbrl import extract
from corpus.anchor import assign_pages, repair_fact_pages, _norm
DPI = 150

def page_streams(pdf_path: Path, out_dir: Path, write_images: bool=True):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    img_dir = out_dir / 'pages'
    if write_images:
        img_dir.mkdir(parents=True, exist_ok=True)
    texts, meta = ([], [])
    for pno in range(doc.page_count):
        page = doc[pno]
        t = page.get_text('text')
        texts.append(t)
        img_rel = None
        if write_images:
            ip = img_dir / f'p{pno + 1:04d}.png'
            if not ip.exists():
                page.get_pixmap(dpi=DPI).save(ip)
            img_rel = str(ip.relative_to(C.FILINGS))
        meta.append({'page': pno + 1, 'n_chars': len(t), 'image': img_rel, 'width': page.rect.width, 'height': page.rect.height})
    doc.close()
    return (texts, meta)

def process(f: dict, write_images: bool=True) -> dict | None:
    d = filing_dir(f)
    d.mkdir(parents=True, exist_ok=True)
    (d / 'streams.json').unlink(missing_ok=True)
    bundle_path = d / 'bundle.json'
    if bundle_path.exists():
        try:
            b = json.loads(bundle_path.read_text())
            if b.get('n_pages', 0) > 0:
                return b
        except Exception:
            pass
    html_path = d / 'primary.htm'
    if not html_path.exists():
        html_path.write_text(get(f['url']), encoding='utf-8')
    raw = html_path.read_bytes()
    pdf_path = d / 'filing.pdf'
    if not html_to_pdf(html_path, pdf_path):
        pdf_path.unlink(missing_ok=True)
        time.sleep(3)
        if not html_to_pdf(html_path, pdf_path):
            return None
    texts, pmeta = page_streams(pdf_path, d, write_images)
    ix = extract(raw)
    if texts:
        ix = repair_fact_pages(assign_pages(ix, texts), texts)
    npages = [_norm(t) for t in texts]
    hit = tot = 0
    for fa in ix['facts']:
        v = _norm(fa.get('raw_text') or '')
        if len(v) < 3:
            continue
        tot += 1
        hit += v in npages[fa['page'] - 1] if 1 <= fa['page'] <= len(npages) else 0
    bundle = {**{k: f[k] for k in ('ticker', 'cik', 'company', 'form', 'accession', 'filing_date', 'acceptance_datetime', 'report_date', 'url')}, 'n_pages': len(texts), 'pages': [{**m, 'text': t} for m, t in zip(pmeta, texts)], 'tables': ix['tables'], 'blocks': ix['blocks'], 'facts': ix['facts'], 'has_ixbrl': ix['has_ixbrl'], 'n_page_repairs': ix.get('n_page_repairs', 0), 'anchor_checked': tot, 'anchor_hits': hit}
    bundle_path.write_text(json.dumps(bundle))
    return bundle

def main():
    idx = json.loads((C.RAW / 'filing_index.json').read_text())
    tickers = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] != 'ALL' else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if tickers:
        idx = [f for f in idx if f['ticker'] in tickers]
    if limit:
        idx = idx[:limit]
    t0 = time.time()
    ok = fail = 0
    npages = nfacts = ntables = nblocks = ahit = achk = nixbrl = 0
    for i, f in enumerate(idx, 1):
        try:
            b = process(f)
        except Exception:
            print(f"  ERR {f['ticker']} {f['accession']}: {traceback.format_exc(limit=2)}", flush=True)
            b = None
        if b:
            ok += 1
            npages += b['n_pages']
            nfacts += len(b['facts'])
            ntables += len(b['tables'])
            nblocks += len(b['blocks'])
            ahit += b['anchor_hits']
            achk += b['anchor_checked']
            nixbrl += bool(b['has_ixbrl'])
        else:
            fail += 1
        if i % 5 == 0 or i == len(idx):
            el = time.time() - t0
            print(f'[{i}/{len(idx)}] ok={ok} fail={fail} pages={npages} tables={ntables} facts={nfacts} ixbrl={nixbrl} anchor={100 * ahit / max(1, achk):.1f}% {el:.0f}s ({el / i:.1f}s/filing)', flush=True)
    print(f'DONE ok={ok} fail={fail} pages={npages} tables={ntables} blocks={nblocks} facts={nfacts} ixbrl_filings={nixbrl} anchor_acc={100 * ahit / max(1, achk):.2f}%')
if __name__ == '__main__':
    main()
