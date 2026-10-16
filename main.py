"""FastAPI service for Vigilix Meridian.

Run with ``uvicorn vigilix.api.main:app`` (``make serve``). Interactive API
documentation is served at ``/docs``; the React interface at ``/``.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from vigilix.api.audit import AuditLog
from vigilix.config import ROOT, SETTINGS

app = FastAPI(
    title="Vigilix Meridian API",
    version="1.0.0",
    description="Evidence grounded pharmacovigilance: verified retrieval augmented answers, FAERS disproportionality, label mining, interaction screening and case causality.",
)
app.add_middleware(CORSMiddleware, allow_origins=list(SETTINGS.cors_origins), allow_methods=["*"], allow_headers=["*"])


@lru_cache(maxsize=1)
def services():
    from vigilix.api.services import Services

    return Services()


@lru_cache(maxsize=1)
def audit() -> AuditLog:
    return AuditLog()


# ---------------------------------------------------------------- schemas
class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, examples=["Does clarithromycin increase the risk of rhabdomyolysis with simvastatin?"])
    engine: str | None = Field(None, description="auto, ollama or extractive")
    k: int | None = Field(None, ge=3, le=15)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    mode: str = Field("full", description="bm25, sif, dense, hybrid, entity or full")
    k: int = Field(10, ge=1, le=50)


class TableRequest(BaseModel):
    a: int = Field(..., ge=0)
    b: int = Field(..., ge=0)
    c: int = Field(..., ge=0)
    d: int = Field(..., ge=0)
    dataset: str | None = None


class DrugsRequest(BaseModel):
    drugs: list[str] = Field(..., min_length=2, max_length=15)


class CaseRequest(BaseModel):
    narrative: str = Field(..., min_length=20, max_length=8000)


class NaranjoRequest(BaseModel):
    answers: dict[str, str]


class WhoUmcRequest(BaseModel):
    time_plausible: str = "unknown"
    other_explanation: str = "unknown"
    dechallenge: str = "unknown"
    rechallenge: str = "unknown"
    known_reaction: str = "unknown"
    sufficient_information: bool = True


# ----------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    s = services()
    choice = s.pipeline.engine()
    return {"status": "ok", "engine": choice.name, "engine_reason": choice.reason, "passages": len(s.retriever.store), "version": app.version}


@app.get("/api/overview")
def overview() -> dict:
    return services().overview()


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    t0 = time.time()
    res = services().pipeline.answer(req.question, engine=req.engine, k=req.k)
    audit().record("/api/ask", req.question, res, latency_ms=round(1000 * (time.time() - t0), 1))
    return res


@app.post("/api/ask/stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    pipe = services().pipeline

    def gen():
        final = None
        for ev in pipe.stream(req.question, engine=req.engine):
            if ev["event"] == "final":
                final = ev["data"]
            yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"
        if final is not None:
            audit().record("/api/ask/stream", req.question, final)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/search")
def search(req: SearchRequest) -> dict:
    r = services().retriever
    q, res = r.search(req.query, k=req.k, mode=req.mode)
    return {"query": q.to_dict(), "results": [r.result_dict(c, i + 1) for i, c in enumerate(res)]}


@app.get("/api/suggest")
def suggest(q: str = Query(..., min_length=2), kind: str = "drug", limit: int = 12) -> list[dict]:
    return services().suggest(q, kind, limit)


@app.get("/api/drugs/{name}")
def drug(name: str) -> dict:
    res = services().drug(name)
    if not res["profile"].get("found") and not res["entry"]:
        raise HTTPException(404, f"unknown drug {name}")
    return res


@app.get("/api/reactions/{name}")
def reaction(name: str) -> dict:
    return services().reaction(name)


@app.get("/api/graph/{name}")
def graph(name: str, limit: int = 40) -> dict:
    s = services()
    return s.graph.subgraph(s.drug(name)["drug"], limit)


@app.get("/api/signals/datasets")
def datasets() -> list[dict]:
    return services().datasets()


@app.get("/api/signals")
def signals(
    dataset: str | None = None,
    drug: str | None = None,
    min_cases: int = 0,
    only_signals: bool = False,
    unlabelled: bool = False,
    hide_clusters: bool = False,
    soc: str | None = None,
    q: str | None = None,
    sort: str = "eb05",
    limit: int = Query(500, le=5000),
) -> dict:
    return services().signals(dataset, drug, min_cases, only_signals, unlabelled, hide_clusters, soc, q, sort, limit)


@app.post("/api/signals/compute")
def compute(req: TableRequest) -> dict:
    return services().compute(req.a, req.b, req.c, req.d, req.dataset)


@app.get("/api/labels")
def labels(region: str | None = None, q: str | None = None) -> list[dict]:
    return services().label_list(region, q)


@app.get("/api/labels/{doc_id:path}")
def label(doc_id: str) -> dict:
    s = services()
    if doc_id not in s.labels_by_id:
        raise HTTPException(404, "unknown label section")
    return s.label(doc_id)


@app.post("/api/interactions")
def interactions(req: DrugsRequest) -> dict:
    res = services().interactions(req.drugs)
    audit().record("/api/interactions", ",".join(req.drugs), {}, drugs=res["drugs"])
    return res


@app.post("/api/case/intake")
def case_intake(req: CaseRequest) -> dict:
    t0 = time.time()
    res = services().case_intake(req.narrative)
    audit().record("/api/case/intake", req.narrative, {}, latency_ms=round(1000 * (time.time() - t0), 1), redacted=res["redacted_narrative"][:500], redactions=res["redactions"], drugs=res["suspect_drugs"], reactions=res["events"])
    return res


@app.post("/api/causality/naranjo")
def naranjo(req: NaranjoRequest) -> dict:
    from vigilix.causality.assess import naranjo as score

    return score(req.answers)


@app.post("/api/causality/who-umc")
def who_umc(req: WhoUmcRequest) -> dict:
    from vigilix.causality.assess import who_umc as cat

    return cat(req.time_plausible, req.other_explanation, req.dechallenge, req.rechallenge, req.known_reaction, req.sufficient_information)


@app.get("/api/documents/{doc_id:path}")
def documents(doc_id: str) -> dict:
    return services().documents(doc_id)


@app.get("/api/evaluation")
def evaluation() -> dict:
    return services().evaluation


@app.get("/api/audit")
def audit_log(limit: int = 100) -> dict:
    return {"stats": audit().stats(), "entries": audit().recent(limit)}


@app.get("/api/figures/{name}")
def figure(name: str):
    p = SETTINGS.paths.figures / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


# ------------------------------------------------------------ frontend
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    if (DIST / "data").exists():
        app.mount("/data", StaticFiles(directory=DIST / "data"), name="data")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
