"""End to end question answering: guard, understand, retrieve, ground, write, verify."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator

from vigilix.config import SETTINGS
from vigilix.rag import guard as G
from vigilix.rag.composer import compose, graph_evidence_text
from vigilix.rag.llm import OllamaClient, build_messages, parse_cited_sentences
from vigilix.rag.retriever import Retriever
from vigilix.rag.verifier import Verifier


@dataclass
class EngineChoice:
    name: str
    reason: str


class Pipeline:
    def __init__(self, retriever: Retriever | None = None, verifier: Verifier | None = None, llm: OllamaClient | None = None):
        self.retriever = retriever or Retriever.load()
        self.verifier = verifier or Verifier.load()
        self.llm = llm or OllamaClient()
        self._llm_ok: bool | None = None
        self._llm_checked = 0.0

    # ------------------------------------------------------------------
    def engine(self, requested: str | None = None) -> EngineChoice:
        provider = (requested or SETTINGS.llm.provider).lower()
        if provider == "extractive":
            return EngineChoice("extractive", "extractive composer requested")
        now = time.time()
        if self._llm_ok is None or now - self._llm_checked > 30:
            self._llm_ok = self.llm.available()
            self._llm_checked = now
        if self._llm_ok:
            return EngineChoice("llm", f"local model {self.llm.model} via Ollama")
        if provider == "ollama":
            return EngineChoice("extractive", f"Ollama model {self.llm.model} not reachable, fell back to extractive composer")
        return EngineChoice("extractive", "no local model available, extractive composer used")

    def evidence(self, question: str, k: int | None = None) -> tuple[G.GuardResult, object, list[dict], dict]:
        pre = self.retriever.understand(question)
        g = G.check(question, has_entities=bool(pre.drugs or pre.reactions))
        q = self.retriever.understand(g.text)
        _, results = self.retriever.search(q, k=k or SETTINGS.retrieval.final_k)
        items = []
        injected = 0
        for n, c in enumerate(results, start=1):
            r = self.retriever.result_dict(c, n)
            r["text"], flagged = G.neutralise(r["text"])
            injected += int(flagged)
            r["n"] = n
            items.append(r)
        summary = self.retriever.graph.evidence_summary(q.drugs, q.reactions) if (q.drugs and (q.reactions or len(q.drugs) > 1)) else {"pairs": [], "interactions": [], "flags": {}}
        gtext = graph_evidence_text(summary, self.retriever.graph)
        if gtext:
            items.append(
                {
                    "n": len(items) + 1,
                    "rank": len(items) + 1,
                    "pid": "graph",
                    "doc_id": "graph",
                    "source_type": "graph",
                    "evidence_level": 3,
                    "evidence_label": "Knowledge graph",
                    "title": "Knowledge graph evidence",
                    "section": "Graph",
                    "text": gtext,
                    "url": "",
                    "drugs": q.drugs,
                    "reactions": q.reactions,
                    "score": 0.0,
                }
            )
        summary["injection_neutralised"] = injected
        return g, q, items, summary

    def _verify(self, sents: list[dict], items: list[dict]) -> list[dict]:
        by_n = {it["n"]: it for it in items}
        out = []
        for s in sents:
            cited = [by_n[c]["text"] for c in s["citations"] if c in by_n]
            valid = bool(s["citations"]) and all(c in by_n for c in s["citations"])
            v = self.verifier.verify(s["text"], cited, self.retriever.drugs, self.retriever.reactions, valid=valid)
            out.append({**s, "verification": v})
        return out

    @staticmethod
    def confidence(items: list[dict], sents: list[dict], q) -> dict:
        if not sents:
            return {"level": "low", "score": 0.0, "reasons": ["no answer sentences"]}
        sup = sum(1 for s in sents if s["verification"]["status"] == "supported") / len(sents)
        unsup = sum(1 for s in sents if s["verification"]["status"] == "unsupported")
        top_level = min((it["evidence_level"] for it in items if it["source_type"] != "graph"), default=4)
        strong = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4}[top_level]
        entity_hit = 1.0
        if q.drugs:
            entity_hit = sum(1 for it in items[:5] if set(q.drugs) & set(it.get("drugs", [])) or any(d in it["title"].lower() for d in q.drugs)) / max(min(5, len(items)), 1)
        score = 0.5 * sup + 0.3 * strong + 0.2 * entity_hit - 0.15 * unsup
        reasons = [f"{round(sup * 100)} percent of sentences fully supported", f"strongest evidence: level {top_level}"]
        if q.drugs:
            reasons.append(f"{round(entity_hit * 100)} percent of top evidence mentions the queried drug")
        level = "high" if score >= 0.75 else "moderate" if score >= 0.5 else "low"
        return {"level": level, "score": round(score, 3), "reasons": reasons}

    # ------------------------------------------------------------------
    def answer(self, question: str, engine: str | None = None, k: int | None = None) -> dict:
        t0 = time.time()
        g, q, items, summary = self.evidence(question, k)
        timings = {"retrieval_ms": round(1000 * (time.time() - t0), 1)}
        base = {"question": question, "guard": g.to_dict(), "query": q.to_dict(), "evidence": items, "graph": summary}
        if g.crisis:
            return base | {"engine": "guard", "answer": [{"text": G.CRISIS_MESSAGE, "citations": [], "verification": {"status": "not_applicable"}}], "confidence": {"level": "not_applicable"}, "timings": timings, "notices": ["crisis"]}
        if g.out_of_scope:
            return base | {"engine": "guard", "answer": [{"text": G.SCOPE_MESSAGE, "citations": [], "verification": {"status": "not_applicable"}}], "confidence": {"level": "not_applicable"}, "timings": timings, "notices": ["out_of_scope"], "evidence": []}
        choice = self.engine(engine)
        notes = []
        notices = []
        if g.dosing_request:
            notes.append("Do not give an individual dose.")
            notices.append("dosing")
        t1 = time.time()
        sents: list[dict] = []
        if choice.name == "llm":
            try:
                text = self.llm.chat(build_messages(g.text, items, notes))
                sents = parse_cited_sentences(text)
                for s in sents:
                    s["kind"] = "generated"
            except Exception as exc:  # pragma: no cover - network failure path
                choice = EngineChoice("extractive", f"model call failed ({type(exc).__name__}), extractive fallback")
        if choice.name == "extractive":
            sents = compose(q.tokens, q, items)
        timings["generation_ms"] = round(1000 * (time.time() - t1), 1)
        t2 = time.time()
        sents = self._verify(sents, items)
        timings["verification_ms"] = round(1000 * (time.time() - t2), 1)
        timings["total_ms"] = round(1000 * (time.time() - t0), 1)
        if g.dosing_request:
            sents.insert(0, {"text": G.DOSING_MESSAGE, "citations": [], "kind": "notice", "verification": {"status": "not_applicable"}})
        return base | {
            "engine": choice.name,
            "engine_reason": choice.reason,
            "answer": sents,
            "confidence": self.confidence(items, [s for s in sents if s.get("kind") != "notice"], q),
            "timings": timings,
            "notices": notices,
        }

    def stream(self, question: str, engine: str | None = None) -> Iterator[dict]:
        """Server sent event payloads: evidence first, then tokens, then verified sentences."""
        g, q, items, summary = self.evidence(question)
        yield {"event": "evidence", "data": {"query": q.to_dict(), "guard": g.to_dict(), "evidence": items, "graph": summary}}
        choice = self.engine(engine)
        if g.blocked or choice.name == "extractive":
            res = self.answer(question, engine="extractive")
            yield {"event": "final", "data": res}
            return
        buf = ""
        try:
            for chunk in self.llm.stream(build_messages(g.text, items, [])):
                buf += chunk
                yield {"event": "token", "data": chunk}
        except Exception:
            res = self.answer(question, engine="extractive")
            yield {"event": "final", "data": res}
            return
        sents = self._verify(parse_cited_sentences(buf), items)
        yield {"event": "final", "data": {"question": question, "engine": "llm", "answer": sents, "evidence": items, "graph": summary, "query": q.to_dict(), "confidence": self.confidence(items, sents, q)}}
