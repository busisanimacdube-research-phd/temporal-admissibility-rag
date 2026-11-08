import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
RAW = DATA / 'raw'
FILINGS = DATA / 'filings'
PAGES = DATA / 'pages'
XBRL = DATA / 'xbrl'
KG = DATA / 'kg'
BENCH = DATA / 'questions'
RESULTS = ROOT / 'results'
FIGURES = ROOT / 'figures'
CACHE = ROOT / 'cache'
for _p in (RAW, FILINGS, PAGES, XBRL, KG, BENCH, RESULTS, FIGURES, CACHE):
    _p.mkdir(parents=True, exist_ok=True)
SEC_UA = os.environ.get('SEC_USER_AGENT', 'research-project contact@example.org')
SEC_RATE_DELAY = 0.12
TICKERS = ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'TSLA', 'JPM', 'BAC', 'WMT', 'XOM', 'JNJ', 'PG', 'KO', 'PFE', 'INTC', 'CSCO', 'DIS', 'VZ', 'CVX']
CIK_OVERRIDE = {'XOM': '0000034088', 'ATVI': '0000718877', 'FL': '0000850209'}
FORMS = ('10-K', '10-Q')
YEAR_MIN, YEAR_MAX = (2019, 2025)
OLLAMA = 'http://127.0.0.1:11434'
READER_VL = 'qwen2.5vl:7b'
READER_TEXT = READER_VL
EMBED = 'bge-m3:latest'
NUM_CTX = 8192
TOP_K = 5
N_IMAGES = 1
UNIT_CHARS = 900
MAX_UNITS = TOP_K + 2
CANDIDATE_POOL = 50
CHUNK_TOKENS = 512
CHUNK_OVERLAP = 64
SEED = 20260909
NEAR_DAYS = 45

def _load_frozen():
    import json
    global TOP_K, NEAR_DAYS, MAX_UNITS
    fp = RESULTS / 'frozen_config.json'
    if not fp.exists():
        return None
    try:
        d = json.loads(fp.read_text())
    except Exception:
        return None
    TOP_K = int(d.get('TOP_K', TOP_K))
    NEAR_DAYS = int(d.get('NEAR_DAYS', NEAR_DAYS))
    MAX_UNITS = TOP_K + 2
    return d
FROZEN = _load_frozen()
FB_TICKERS = ['PEP', 'AMCR', 'MMM', 'AMD', 'BBY', 'BA', 'AXP', 'MGM', 'ULTA', 'ADBE', 'GLW', 'CVS', 'GIS', 'NKE', 'AES', 'AWK', 'XYZ', 'LMT', 'ATVI', 'FL', 'NFLX', 'COST', 'KHC', 'PYPL']
FB_YEAR_MIN, FB_YEAR_MAX = (2015, 2023)
FB_NAME_TO_TICKER = {'pepsico': 'PEP', 'amcor': 'AMCR', '3m': 'MMM', 'amd': 'AMD', 'best buy': 'BBY', 'boeing': 'BA', 'american express': 'AXP', 'mgm resorts': 'MGM', 'ulta beauty': 'ULTA', 'adobe': 'ADBE', 'corning': 'GLW', 'cvs health': 'CVS', 'general mills': 'GIS', 'nike': 'NKE', 'aes corporation': 'AES', 'american water works': 'AWK', 'block': 'XYZ', 'lockheed martin': 'LMT', 'activision blizzard': 'ATVI', 'foot locker': 'FL', 'netflix': 'NFLX', 'costco': 'COST', 'kraft heinz': 'KHC', 'paypal': 'PYPL'}
