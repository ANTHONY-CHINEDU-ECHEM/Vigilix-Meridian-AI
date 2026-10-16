"""Passage store: metadata, entity postings and the artefacts of the index."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from functools import cached_property
from pathlib import Path

import numpy as np

from vigilix.config import SETTINGS


class PassageStore:
    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.pid_to_idx = {p["pid"]: i for i, p in enumerate(passages)}
        self.doc_to_idx: dict[str, list[int]] = defaultdict(list)
        self.by_drug: dict[str, list[int]] = defaultdict(list)
        self.by_reaction: dict[str, list[int]] = defaultdict(list)
        for i, p in enumerate(passages):
            self.doc_to_idx[p["doc_id"]].append(i)
            for d in p.get("drugs", []):
                self.by_drug[d].append(i)
            for r in p.get("reactions", []):
                self.by_reaction[r].append(i)
        self.source_types = sorted({p["source_type"] for p in passages})

    def __len__(self) -> int:
        return len(self.passages)

    def __getitem__(self, i: int) -> dict:
        return self.passages[i]

    @classmethod
    def load(cls, path: Path | None = None) -> "PassageStore":
        path = path or SETTINGS.paths.processed / "passages.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf8") as fh:
            return cls([json.loads(line) for line in fh])

    def entity_subset(self, drugs: list[str], reactions: list[str]) -> np.ndarray:
        """Passages that mention any query drug, intersected with reactions when both are present."""
        ds = set()
        for d in drugs:
            ds.update(self.by_drug.get(d, []))
        if reactions:
            rs = set()
            for r in reactions:
                rs.update(self.by_reaction.get(r, []))
            both = ds & rs if ds else rs
            if len(both) >= 5:
                return np.array(sorted(both), dtype=np.int64)
        return np.array(sorted(ds), dtype=np.int64)
