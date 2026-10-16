import pytest

from vigilix.config import SETTINGS


def artifacts_ready() -> bool:
    a, p = SETTINGS.paths.artifacts, SETTINGS.paths.processed
    return all(x.exists() for x in (p / "passages.jsonl.gz", p / "kg.json", p / "dictionaries.json", a / "bm25_weights.npz", a / "dense_passages.npy", a / "reranker.txt", a / "verifier.json"))


needs_artifacts = pytest.mark.skipif(not artifacts_ready(), reason="run `make all` first to build the knowledge base and models")


@pytest.fixture(scope="session")
def dictionaries():
    from vigilix.kb.dictionaries import load_dictionaries

    return load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")


@pytest.fixture(scope="session")
def pipeline():
    from vigilix.rag.pipeline import Pipeline

    return Pipeline()
