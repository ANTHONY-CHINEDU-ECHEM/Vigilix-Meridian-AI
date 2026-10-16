"""Central configuration for Vigilix Meridian.

Every setting can be overridden with an environment variable prefixed
``VIGILIX_`` so the same code runs on a laptop, in Docker, on a hospital
server or inside a Hugging Face Space without edits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(f"VIGILIX_{name}", default)


@dataclass(frozen=True)
class Paths:
    root: Path = ROOT
    data: Path = Path(_env("DATA_DIR", str(ROOT / "data")))

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def artifacts(self) -> Path:
        return self.data / "artifacts"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def figures(self) -> Path:
        return self.root / "reports" / "figures"

    @property
    def knowledge(self) -> Path:
        return self.root / "vigilix" / "kb" / "content"

    @property
    def frontend_public(self) -> Path:
        return self.root / "frontend" / "public"

    def ensure(self) -> "Paths":
        for p in (self.raw, self.processed, self.artifacts, self.reports, self.figures):
            p.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class RetrievalSettings:
    bm25_k1: float = 1.2
    bm25_b: float = 0.72
    candidates_per_retriever: int = int(_env("CANDIDATES", "80"))
    rrf_k: int = 60
    final_k: int = int(_env("FINAL_K", "8"))
    max_per_document: int = 2
    dense_backend: str = _env("DENSE", "dual")  # dual | sif | sentence_transformers
    st_model: str = _env("ST_MODEL", "ncbi/MedCPT-Query-Encoder")


@dataclass(frozen=True)
class LLMSettings:
    provider: str = _env("LLM_PROVIDER", "auto")  # auto | ollama | extractive
    model: str = _env("LLM_MODEL", "llama3.1:8b")
    ollama_url: str = _env("OLLAMA_URL", "http://localhost:11434")
    timeout_s: float = float(_env("LLM_TIMEOUT", "90"))
    temperature: float = 0.1


@dataclass(frozen=True)
class Settings:
    paths: Paths = field(default_factory=Paths)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",") if o.strip()
    )
    audit_db: str = _env("AUDIT_DB", str(ROOT / "data" / "artifacts" / "audit.sqlite"))
    random_seed: int = 20261016


SETTINGS = Settings()
