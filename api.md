# API

The FastAPI service runs with `make serve` (or `uvicorn vigilix.api.main:app`). Interactive documentation with request and response schemas is served at `/docs`. The in browser engine implements the same contract (`frontend/src/api.ts`).

| Method and path | Body or query | Returns |
| --- | --- | --- |
| `GET /api/health` | | Status, writer engine in use (local model or extractive) and corpus size |
| `GET /api/overview` | | Knowledge base counts, FAERS datasets, evaluation highlights and the top unlabelled signals |
| `POST /api/ask` | `{"question": str, "engine": "auto" or "ollama" or "extractive", "k": int}` | Guard result, query understanding, numbered evidence (including the knowledge graph item), cited answer sentences with verification, confidence and timings |
| `POST /api/ask/stream` | as above | Server sent events: `evidence`, then `token` events from the model, then `final` with verified sentences |
| `POST /api/search` | `{"query": str, "mode": "bm25" or "sif" or "dense" or "hybrid" or "entity" or "full", "k": int}` | Ranked passages with retriever scores (for ablation and debugging) |
| `GET /api/suggest` | `q`, `kind=drug or reaction` | Autocomplete over the dictionaries, including brand names |
| `GET /api/drugs/{name}` | | Dictionary entry, graph profile (labelled reactions by System Organ Class, FAERS signals, case reports, literature, interactions, classes, indications, targets), label sections, FAERS summary and a subgraph |
| `GET /api/reactions/{name}` | | Drugs linked to the reaction with the kinds of evidence, and FAERS rows |
| `GET /api/graph/{name}` | `limit` | A safety prioritised neighbourhood for visualisation |
| `GET /api/signals/datasets` | | The four FAERS extracts with their drugs, periods and fitted gamma priors |
| `GET /api/signals` | `dataset, drug, min_cases, only_signals, unlabelled, hide_clusters, soc, q, sort, limit` | Every measure for each drug and preferred term, label status and cluster flag |
| `POST /api/signals/compute` | `{"a","b","c","d","dataset"}` | PRR, ROR, IC and EBGM with intervals and all screening rules for any table |
| `GET /api/labels` | `region, q` | Label sections |
| `GET /api/labels/{doc_id}` | | Section text with mined term spans, annotated terms, misses, extras, precision, recall and FAERS concordance |
| `POST /api/interactions` | `{"drugs": [str, ...]}` | Pairwise levels with documented sentences, pharmacokinetic mechanisms and shared reaction groups, plus cumulative burden |
| `POST /api/case/intake` | `{"narrative": str}` | Redacted narrative, extracted spans and pairs, seriousness, outcome, onset, dechallenge, rechallenge, ICSR validity and per pair Naranjo and WHO UMC assessments |
| `POST /api/causality/naranjo` | `{"answers": {...}}` | Naranjo score and category |
| `POST /api/causality/who-umc` | structured answers | WHO UMC category with its reason |
| `GET /api/documents/{doc_id}` | | All passages of one source document |
| `GET /api/evaluation` | | The full evaluation summary |
| `GET /api/audit` | `limit` | Recent audit entries and counts |
| `GET /api/figures/{name}` | | Report figures |

## Configuration

Environment variables prefixed `VIGILIX_`: `DATA_DIR`, `LLM_PROVIDER` (auto, ollama or extractive), `LLM_MODEL` (default `llama3.1:8b`), `OLLAMA_URL`, `LLM_TIMEOUT`, `FINAL_K`, `CANDIDATES`, `DENSE`, `ST_MODEL`, `CORS_ORIGINS`, `AUDIT_DB`.
