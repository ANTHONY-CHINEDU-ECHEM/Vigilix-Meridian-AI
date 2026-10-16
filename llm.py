"""Local language model client (Ollama) and the grounded answer prompt.

The model is treated as a writer, never as a source. It receives numbered
evidence items and must cite one for every sentence. If no model is
reachable the pipeline falls back to the extractive composer, so the system
degrades to a slower to read but faithful answer instead of failing.
"""
from __future__ import annotations

import json
import re
from typing import Iterator

import httpx

from vigilix.config import SETTINGS

SYSTEM_PROMPT = """You are Vigilix Meridian, a pharmacovigilance evidence assistant for drug safety professionals.
Rules you must follow:
1. Use ONLY the numbered evidence items provided. Never add facts, numbers, drug names or trial names that are not in them.
2. End every sentence with one or more citations in square brackets, for example [2] or [1][4].
3. Prefer guidance digests, regulatory labels and randomised trials over case reports; say which kind of evidence supports each point.
4. Distinguish clearly between a labelled (expected) reaction, a disproportionality signal from spontaneous reports, and isolated case reports. Disproportionality is not proof of causation.
5. State the population or setting a finding applies to when the evidence gives it.
6. Do not recommend doses for individual patients. Do not diagnose.
7. If the evidence does not answer the question, say so plainly in one sentence and cite the closest item.
8. Write in plain clinical English, at most 7 sentences, no headings, no bullet points."""


def format_evidence(items: list[dict], max_chars: int = 900) -> str:
    lines = []
    for it in items:
        text = it["text"]
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + " ..."
        lines.append(f"[{it['n']}] ({it['evidence_label']}; {it['title']}) {text}")
    return "\n".join(lines)


def build_messages(question: str, items: list[dict], notes: list[str]) -> list[dict]:
    note = ("\nNotes for the writer: " + " ".join(notes)) if notes else ""
    user = f"Question: {question}\n\nEvidence:\n{format_evidence(items)}{note}\n\nWrite the cited answer now."
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


class OllamaClient:
    def __init__(self, url: str | None = None, model: str | None = None, timeout: float | None = None):
        self.url = (url or SETTINGS.llm.ollama_url).rstrip("/")
        self.model = model or SETTINGS.llm.model
        self.timeout = timeout or SETTINGS.llm.timeout_s

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=1.5)
            if r.status_code != 200:
                return False
            names = {m.get("name", "") for m in r.json().get("models", [])}
            return any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names)
        except Exception:
            return False

    def chat(self, messages: list[dict]) -> str:
        r = httpx.post(
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False, "options": {"temperature": SETTINGS.llm.temperature}},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    def stream(self, messages: list[dict]) -> Iterator[str]:
        with httpx.stream(
            "POST",
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": True, "options": {"temperature": SETTINGS.llm.temperature}},
            timeout=self.timeout,
        ) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break


_CITE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def parse_cited_sentences(text: str) -> list[dict]:
    """Split model output into sentences with their citation numbers."""
    from vigilix.rag.text import sentences

    out = []
    for s in sentences(text.replace("\n", " ")):
        cites = []
        for m in _CITE.finditer(s):
            cites += [int(x) for x in re.split(r"[,;\s]+", m.group(1)) if x]
        clean = _CITE.sub("", s).strip()
        clean = re.sub(r"\s+([.,;:])", r"\1", clean)
        if clean:
            out.append({"text": clean, "citations": sorted(set(cites))})
    return out
