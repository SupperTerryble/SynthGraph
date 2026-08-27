<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/🇫🇷_Français-lightgrey?style=flat-square" alt="Français"></a>
  <img src="https://img.shields.io/badge/🇬🇧_English-blue?style=flat-square" alt="English">
</p>

# SynthGraph — verifiable synthesis-route extraction through constrained tool-calling

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Qwen3--8B%20(local%2C%20GGUF)-6E40C9)
![Neo4j](https://img.shields.io/badge/Neo4j-Knowledge%20Graph-008CC1?logo=neo4j&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
[![tests](https://github.com/SupperTerryble/SynthGraph/actions/workflows/tests.yml/badge.svg)](https://github.com/SupperTerryble/SynthGraph/actions/workflows/tests.yml)

A scientific PDF goes in, a **verifiable** synthesis route comes out.

**The project's non-negotiable rule: the system invents NOTHING.** Every value enters
the graph through a tool call that **rejects** it if the supplied quotation does not
contain it. A parameter absent from the paper is never guessed — it becomes a declared
gap (`MissingParameter`).

---

## The architecture

<p align="center">
  <img src="docs/architecture.svg" alt="SynthGraph architecture: a PDF goes through text extraction and RAG focusing, then enters an agentic loop where the LLM never writes to the graph directly — it calls three tools whose every argument is checked against the attached quotation, a rejection sending the model back to its work. A deterministic validator recomputes the elemental balance and holds veto power. Output: a traced route into Neo4j, and gaps explicitly declared." width="900">
</p>

Three ideas carry the whole system:

1. **The model does not write to the graph** — it calls three tools
   (`add_precursor`, `add_operation`, `finalize_route`) that reject any argument not
   proven by the attached quotation, and hand it back an *actionable* refusal:
   quote it, or declare the gap.
2. **A deterministic validator holds veto power** — the elemental balance, recomputed
   outside the LLM, rejects a chemically impossible extraction whatever the model said.
3. **A gap is data** — absence is declared (`MissingParameter`), never filled in with a
   plausible value.

## The result in one table

Same model (Qwen3-8B quantized Q4_K_M, running locally), two architectures:

| Paper | Precursors | Temperatures | Traceability | Reproducible |
|---|---|---|---|---|
| *single-shot* (baseline) | — | 37.5 % | **22.6 %** | 1 route / 3 |
| crystal (tool-calling) | 100 % | **100 %** | 95.4 % (108 values) | almost |
| physrev (tool-calling) | 100 % | 100 % | **100 %** | **yes** |
| prepara — 1957 OCR (tool-calling) | **100 %** | 100 % | **100 %** | **yes** |

The gain comes from the **architecture** (constrained tools + deterministic validation
with veto power), not from a bigger model: a 35B-A3B MoE performs **worse**
(33 % of precursors).

Extended corpus: **8 papers, 6 synthesis families** (flux, ceramic, hydrothermal,
sol-gel, auto-combustion, chemical bath, chemical reduction). Hand-annotated gold set:
89 checks, 0 errors.

## Tests

```bash
pip install -r requirements-tests.txt          # lightweight: no torch, no GPU
python tests/regression/run_all.py
```

**56 suites, 835 assertions**, offline, in about thirty seconds.
Three further suites check the gold set against the *source texts* of the papers:
those texts are copyrighted articles and are not versioned, so these suites only run
locally and are excluded by name in CI — `run_all.py` announces them in its summary,
so that a green run cannot lie about what actually ran.

## Installation

```bash
git clone https://github.com/SupperTerryble/SynthGraph.git
cd SynthGraph
pip install -r requirements.txt
export MODELS_DIR=/path/to/your/gguf/models
export NEO4J_PASSWORD=...          # optional: graph export to Neo4j
```

> Source PDFs and GGUF models are not versioned (copyright / size).
> The gold annotations, however, live in `data/gold/`.

---

## Getting started

```bash
# Extract and compare against the gold set — the 3 iridates
python tools/compare_tc_gold.py --model Qwen3-8B-Q4_K_M.gguf

# The 5 non-iridate papers
python tools/compare_tc_gold.py --model Qwen3-8B-Q4_K_M.gguf \
    --papers hydro_czts,solgel_cuo,combu_ferrite,cbd_mnse,reduc_cu \
    --gold data/gold/gold_corpus5.json

# "Can I actually redo this synthesis in the lab?" — the chemist's question
python tools/audit_reproductibilite.py

# Regression suite (offline, no GPU, ~3 min)
python tests/regression/run_all.py
```

> On Windows, remember to set `PYTHONIOENCODING=utf-8`.

---

## How to read this repository

| Looking for… | Go to |
|---|---|
| the full history and lessons learned | `README_AUTONOME.md` |
| the mandate and decisions already settled | `MANDAT.md` |
| working instructions | `CLAUDE.md` |
| what the pipeline extracted, route by route, with evidence | `VOIES_DE_SYNTHESE.md` |

### The code

| Role | File |
|---|---|
| **The 3 tools exposed to the model** (add_precursor, add_operation, finalize_route) and ALL the guardrails | `synthgraph/extraction/graph_tools.py` |
| The agentic loop (call formats, `<think>` mode, history pruning) | `synthgraph/agents/extractor_toolcalling.py` |
| The contract for each operation type (required columns, declared gaps) | `synthgraph/schemas/step_schema.py` |
| The deterministic elemental balance — **it holds veto power** | `synthgraph/validation/deterministic.py` |
| Full pipeline (single-shot, QA, Cypher) | `synthgraph/pipeline/runner.py` |

### The tools

| Tool | What it does |
|---|---|
| `compare_tc_gold.py` | extracts, then compares against the hand-annotated gold set |
| `audit_reproductibilite.py` | is the synthesis **actually redoable**? (reagents, proportions, sequence, atmosphere, vessel, work-up) |
| `make_voies_doc.py` | produces `VOIES_DE_SYNTHESE.md`: one section per route, every value with its quotation |
| `build_text_cache.py` | pre-extracts PDF text (slow, cached) |
| `recompute_corpus5.py` | recomputes metrics without spinning up the GPU |
| `triage_corpus.py` | failure classes over a batch |

### The data

- `data/gold/` — the **hand-annotated** references, checked against source texts
  (89 checks, 0 errors on corpus5).
- `data/bench_night/`, `data/corpus5/` — the PDFs.
- `logs/odl_*.txt` — extracted-text cache.
- `logs/pathways_Qwen3_*.json` — latest extractions.
- `logs/chroma_db_bible/` — **do not delete**, persistent vector store.
- `logs/archives_runs/` — campaign history.

---

## The regression tests

`tests/regression/` keeps one test per shipped fix, and **one test per trap encountered
on real data**:

- a prompt-example leak (`equipment='bécher'` copied from a French prompt into an
  English paper);
- a negated atmosphere ("without inert gas protection");
- a **storage** vial mistaken for a reactor;
- a branded sonicator ("VialTweeter") mistaken for a vessel;
- a hydrate `Fe(NO3)2.9H2O` read as a decimal, corrupting the elemental balance — and
  therefore triggering the **veto**;
- a "2" found inside `2H2O` and taken for a quantity.

These suites lived in a temporary session folder until 20 Aug: a cleanup would have
erased them.

---

## What the pipeline can do, and what it cannot

Across 8 papers from 6 synthesis families (flux, ceramic, hydrothermal, sol-gel,
auto-combustion, chemical bath, chemical reduction) it extracts: precursors, ratios,
thermal sequences, atmosphere, per-operation vessel, work-up steps — **every value
backed by its quotation**.

It does not guess. When a paper names no vessel, no proportion or no atmosphere, the
pipeline abstains and declares the gap. Several apparent "failures" reflect that limit
of the **sources**, not of the system.
