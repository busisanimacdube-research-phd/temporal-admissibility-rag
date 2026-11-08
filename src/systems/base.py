from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from systems.llm import generate
from systems.answer import parse_output
from systems.units import build_units
from systems.index import UnitIndex
SCHEMA = 'Reply with a single JSON object and nothing else:\n{"answer": <the direct answer, a number without units where numeric, or the string "UNANSWERABLE">, "citations": [<ids of the evidence items you used>], "abstain": <true only if the evidence available at the as-of date is insufficient>}'
ROLE = 'You are a financial analyst answering questions about SEC filings. Answer strictly from the evidence provided.'
PIT_RULE = 'Point-in-time rule: answer only from disclosures that were public on or before the as-of date; nothing filed later is available to you. Where the same fiscal period was reported more than once, use the most recently reported value that was public by the as-of date.\nAnswer only about the exact fiscal period the question names. The evidence will usually contain figures for other periods; those are not an answer. If no disclosure available by the as-of date reports the period asked about, the figure was not yet public and you must abstain.'
CALC_NOTE = "Where a 'Structured calculation' block appears below, its inputs were selected from the evidence and its arithmetic has already been carried out."
RESOLUTION_NOTE = "Where a 'Point-in-time resolution' block appears below, the figure it gives is the one in force at the as-of date and it supersedes any earlier figure for the same period that also appears in the evidence."

def render_evidence(units: list[dict], with_time: bool=True, limit_chars: int | None=None) -> str:
    limit_chars = limit_chars or C.UNIT_CHARS
    lines = []
    for i, u in enumerate(units, 1):
        tag = f'E{i}'
        loc = f"{u.get('accession')} p.{u.get('page')}" if u.get('accession') else '-'
        t = f" filed {str(u.get('asserted_at'))[:10]}" if with_time and u.get('asserted_at') else ''
        lines.append(f"[{tag}] ({u['kind']}, {loc}{t})\n{u['text'][:limit_chars]}")
    return '\n\n'.join(lines)

class CompanyContext:

    def __init__(self, graph, company: str, dense: bool=True):
        self.company = company
        self.g = graph
        self.units = build_units(graph, company)
        cache = C.CACHE / 'emb' / f'{company}.npy'
        self.index = UnitIndex(self.units, dense=dense, cache=cache)
        self.uid_pos = {u['uid']: i for i, u in enumerate(self.units)}

class System:
    name = 'base'
    uses_time = False
    uses_vision = False
    uses_graph = False
    restrict_families = None

    def answer(self, item: dict, ctx: CompanyContext) -> dict:
        raise NotImplementedError

    def _gen(self, prompt: str, **kw) -> dict:
        t = time.time()
        raw = generate(prompt, **kw)
        out = parse_output(raw)
        out['latency'] = time.time() - t
        return out

    def _pack(self, item, units, extra_rule: str='', with_time: bool=True) -> str:
        return f"{ROLE}\n\n{extra_rule}\n\nAs-of date: {item['as_of'][:10]}\nCompany: {item['company']}\n\nEvidence:\n{render_evidence(units, with_time)}\n\nQuestion: {item['question']}\n\n{SCHEMA}".strip()
