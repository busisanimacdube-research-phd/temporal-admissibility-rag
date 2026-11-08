# Temporal Admissibility of Evidence in Retrieval-Augmented Generation

Retrieval-augmented generation (RAG) is often asked about the past: what had been reported at a given date. Such an **as-of question** should be answered only from documents that existed at that date. We call this property **temporal admissibility**. Retrieval corpora violate it by construction: they are assembled later, they contain the documents published after the as-of date, including revisions of earlier ones, and retrievers rank evidence by relevance rather than by publication time.

This repository contains the code, data and per-question results of a study that measures this **temporal leakage** in RAG pipelines at three levels:

- **Evidence leakage**: retrieved units published after the as-of date.
- **Answer leakage**: answers that give a value revised after the as-of date.
- **Premature answering**: answers to questions that no admissible document could answer yet.

## What is evaluated

- Seven retrieval pipelines (BM25, dense, hybrid, two graph-based and two page-image pipelines inspired by LightRAG, HippoRAG, VisRAG and M3DocRAG) sharing one evidence store and one reader.
- The same hybrid pipeline with an as-of filter, with the evidence dates and an instruction in the prompt, with both, with a soft date-aware reranking, and with other readers.
- A TempFinRAG reimplementation with and without its availability filter.

The testbed is an evolving corpus of 559 periodic reports of 20 companies filed with the SEC (2019 to 2025), in which every unit carries its EDGAR acceptance timestamp and revisions are recorded in machine-readable form. The 612 test questions (6 held-out companies) are generated from fixed templates; gold answers and their revision histories come from SEC XBRL data, with no model-written content.

## Layout

| Path | Contents |
|---|---|
| `src/corpus` | download of the filings from SEC EDGAR, rendering, inline-XBRL extraction |
| `src/kg` | evidence store and graph with publication times |
| `src/bench` | question generation (templates, revision detection, as-of dating) |
| `src/systems` | the retrieval pipelines and the reader interface (Ollama) |
| `src/eval` | scoring and the experiment runner |
| `analysis` | leakage, base-rate, variant and error analyses, statistics and figures |
| `data/questions/questions.jsonl` | development, validation and test questions with as-of dates, gold answers and revision fields |
| `data/graph` | graph nodes with publication times, one file per company |
| `results/pipelines` | per-question outputs of every pipeline on the test set |
| `results/variants` | per-question outputs of the controlled variants, with cited units |
| `results/frozen_config.json` | retrieval depth selected on the validation companies |

## Reproducing the analyses

```bash
pip install -r requirements.txt
python analysis/analyse_leakage.py
python analysis/base_rate.py
python analysis/analyse_variants.py
python analysis/error_analysis.py
python analysis/make_figs.py
```

The analyses run from the stored per-question results and need no model. `base_rate.py` also needs the evidence store, which is rebuilt from public SEC sources.

## Rebuilding the corpus and rerunning the pipelines

The filings themselves (about 42 GB with page images) are public and are not redistributed here. Rendering filings to pages uses headless Google Chrome (path set in `src/corpus/render.py`).

```bash
export SEC_USER_AGENT="your-name your-email"
python src/corpus/build_index.py
python src/corpus/fetch_all.py
python src/corpus/render_all.py
python src/corpus/xbrl_facts.py
python src/bench/build_bench.py
python src/eval/run.py --split test --systems main
python analysis/run_variants.py hybrid timefiltered hybrid_instr filter_only soft_rerank hybrid_14b hybrid_llama8 tempfinrag tempfinrag_nofilter
```

The pipelines use local models served by Ollama: `qwen2.5vl:7b` (reader), `bge-m3` (embeddings), and `qwen2.5:14b`, `qwen2.5:7b` and `llama3.1:8b` for the reader variants. Generation is greedy (temperature 0).
