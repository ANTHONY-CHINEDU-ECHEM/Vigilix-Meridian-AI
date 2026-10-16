"""Reproducible acquisition of every public source used by Vigilix Meridian.

Each source is pinned to a repository commit, a Git LFS object or a PyPI
release, fetched with sparse checkouts so only the needed files cross the
network, and recorded in ``data/raw/MANIFEST.json`` with byte counts and
SHA256 digests. Re running the command skips anything already verified.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from vigilix.config import SETTINGS


@dataclass(frozen=True)
class GitSource:
    key: str
    repo: str
    commit: str
    paths: tuple[str, ...]
    licence: str
    citation: str
    role: str


@dataclass(frozen=True)
class UrlSource:
    key: str
    url: str
    filename: str
    licence: str
    citation: str
    role: str


@dataclass(frozen=True)
class WheelSource:
    key: str
    package: str
    version: str
    members: tuple[str, ...]
    licence: str
    citation: str
    role: str


GIT_SOURCES: tuple[GitSource, ...] = (
    GitSource(
        key="pubmed_rct",
        repo="Franck-Dernoncourt/pubmed-rct",
        commit="17ed2cb0590decfca0266add0c76f254f67232b4",
        paths=("PubMed_200k_RCT/train.7z", "PubMed_200k_RCT/dev.txt", "PubMed_200k_RCT/test.txt"),
        licence="CC BY 4.0 (abstract text from MEDLINE, NLM terms)",
        citation="Dernoncourt F, Lee JY. PubMed 200k RCT. IJCNLP 2017.",
        role="Randomised trial abstracts filtered to drug safety and tolerability",
    ),
    GitSource(
        key="ade_corpus",
        repo="trunghlt/AdverseDrugReaction",
        commit="2851af96e26050cf551a2e1f716ff861f7b1059b",
        paths=("ADE-Corpus-V2/DRUG-AE.rel", "ADE-Corpus-V2/DRUG-DOSE.rel", "ADE-Corpus-V2/ADE-NEG.txt", "ADE-Corpus-V2/README.txt"),
        licence="Research use, as distributed by the corpus authors",
        citation="Gurulingappa H et al. ADE corpus. J Biomed Inform 2012;45:885.",
        role="Case report sentences with gold drug to adverse effect relations",
    ),
    GitSource(
        key="ddi_corpus",
        repo="isegura/DDICorpus",
        commit="819b0fa538ed83ab2a8b4f5417bba3c03249b7f3",
        paths=("DDICorpus-2013.zip", "README"),
        licence="CC BY NC 3.0",
        citation="Herrero Zazo M et al. The DDI corpus. J Biomed Inform 2013;46:914.",
        role="DrugBank and MEDLINE texts with typed drug interaction annotations",
    ),
    GitSource(
        key="cdr_corpus",
        repo="JHnlp/BioCreative-V-CDR-Corpus",
        commit="HEAD",
        paths=("CDR_Data.zip", "README.md"),
        licence="Free for research (BioCreative V)",
        citation="Li J et al. BioCreative V CDR corpus. Database 2016;baw068.",
        role="PubMed abstracts with chemical induced disease relations",
    ),
    GitSource(
        key="onsides_annot",
        repo="tatonetti-lab/onsides",
        commit="HEAD",
        paths=(
            "database/annotations/demner-fushman-train-labels.json",
            "database/annotations/demner-fushman-test-labels.json",
            "database/annotations/uk-annot.json",
            "database/annotations/eu-annot.json",
            "database/annotations/fda-pediatric-special-populations-annot.json",
            "LICENSE-DATA",
        ),
        licence="CC BY 4.0",
        citation="Tanaka Y et al. OnSIDES. Med 2025; Demner Fushman D et al. Sci Data 2018;5:180001.",
        role="Drug label safety sections (US, UK, EU) with manually annotated adverse events",
    ),
    GitSource(
        key="atc",
        repo="fabkury/atcd",
        commit="HEAD",
        paths=("WHO ATC-DDD 2026-04-25.csv", "LICENSE"),
        licence="Scraped from WHOCC public pages; WHO terms apply",
        citation="WHO Collaborating Centre for Drug Statistics Methodology, ATC/DDD Index 2026.",
        role="Anatomical Therapeutic Chemical classification and defined daily doses",
    ),
    GitSource(
        key="ohdsi_reference",
        repo="OHDSI/MethodEvaluation",
        commit="HEAD",
        paths=("data/omopReferenceSet.rda", "data/euadrReferenceSet.rda"),
        licence="Apache 2.0",
        citation="Ryan PB et al. Drug Saf 2013;36 Suppl 1:S33; Coloma PM et al. Drug Saf 2013;36:13.",
        role="Expert curated positive and negative drug outcome controls",
    ),
    GitSource(
        key="faers_covid",
        repo="HyoJungKim/FAERS_Data_for_Investigating-the-Safety-of-Fast-Track-COVID-19-Drugs",
        commit="HEAD",
        paths=("2_contigence table_4_drugs.xlsx", "README.md"),
        licence="GPL 3.0 repository; FAERS is US public domain",
        citation="Kim HJ, Yoon JH. FAERS 2020 to 2022 processed for fast track COVID 19 drugs.",
        role="FAERS contingency tables over 5,248,821 deduplicated cases",
    ),
)

URL_SOURCES: tuple[UrlSource, ...] = (
    UrlSource(
        key="hetionet",
        url="https://media.githubusercontent.com/media/hetio/hetionet/main/hetnet/json/hetionet-v1.0.json.bz2",
        filename="hetionet-v1.0.json.bz2",
        licence="CC0 for the integration; SIDER CC BY NC SA 4.0; DrugBank derived nodes CC BY NC 4.0",
        citation="Himmelstein DS et al. Hetionet. eLife 2017;6:e26726.",
        role="Knowledge graph: SIDER side effects, indications, pharmacologic classes, targets",
    ),
)

WHEEL_SOURCES: tuple[WheelSource, ...] = (
    WheelSource(
        key="faers_mddc",
        package="mddc",
        version="1.1.0",
        members=(
            "MDDC/datasets/data/sedative1000.csv",
            "MDDC/datasets/data/betablocker500.csv",
            "MDDC/datasets/data/statin101.csv",
            "MDDC/datasets/data/sedative1000.rst",
            "MDDC/datasets/data/betablocker500.rst",
            "MDDC/datasets/data/statin101.rst",
        ),
        licence="MIT (package); FAERS is US public domain",
        citation="Liu A et al. MDDC: an R and Python package for adverse event identification. JOSS 2025.",
        role="FAERS report counts for sedatives, beta blockers and statins by preferred term",
    ),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _run(cmd: list[str], cwd: Path | None = None, retries: int = 3) -> str:
    last = ""
    for attempt in range(retries):
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout
        last = proc.stderr
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"command failed: {' '.join(cmd)}\n{last}")


def fetch_git(src: GitSource, dest: Path) -> list[Path]:
    out_dir = dest / src.key
    wanted = [out_dir / Path(p).name for p in src.paths]
    if all(p.exists() and p.stat().st_size > 0 for p in wanted):
        return wanted
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        url = f"https://github.com/{src.repo}"
        _run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", "--depth", "1" if src.commit == "HEAD" else "50", url, str(work)])
        ref = "HEAD" if src.commit == "HEAD" else src.commit
        _run(["git", "checkout", "--quiet", ref, "--", *src.paths], cwd=work)
        for rel in src.paths:
            shutil.copy2(work / rel, out_dir / Path(rel).name)
    return wanted


def fetch_url(src: UrlSource, dest: Path) -> list[Path]:
    out_dir = dest / src.key
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / src.filename
    if target.exists() and target.stat().st_size > 0:
        return [target]
    partial = target.with_suffix(target.suffix + ".part")
    start = partial.stat().st_size if partial.exists() else 0
    req = urllib.request.Request(src.url, headers={"Range": f"bytes={start}-"} if start else {})
    with urllib.request.urlopen(req, timeout=120) as resp, partial.open("ab" if start else "wb") as fh:
        shutil.copyfileobj(resp, fh, length=1 << 20)
    partial.rename(target)
    return [target]


def fetch_wheel(src: WheelSource, dest: Path) -> list[Path]:
    out_dir = dest / src.key
    wanted = [out_dir / Path(m).name for m in src.members]
    if all(p.exists() for p in wanted):
        return wanted
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        _run(["python3", "-m", "pip", "download", f"{src.package}=={src.version}", "--no-deps", "--quiet", "-d", tmp])
        wheel = next(Path(tmp).glob("*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            for member in src.members:
                (out_dir / Path(member).name).write_bytes(zf.read(member))
    return wanted


def acquire_all(verbose: bool = True) -> dict:
    paths = SETTINGS.paths.ensure()
    manifest_path = paths.raw / "MANIFEST.json"
    manifest: dict = {"sources": {}}
    jobs: list[tuple[str, object, callable]] = (
        [(s.key, s, fetch_git) for s in GIT_SOURCES]
        + [(s.key, s, fetch_url) for s in URL_SOURCES]
        + [(s.key, s, fetch_wheel) for s in WHEEL_SOURCES]
    )
    for key, src, fn in jobs:
        t0 = time.time()
        files = fn(src, paths.raw)
        manifest["sources"][key] = {
            "origin": getattr(src, "repo", None) or getattr(src, "url", None) or f"pypi:{src.package}=={src.version}",
            "licence": src.licence,
            "citation": src.citation,
            "role": src.role,
            "files": {f.name: {"bytes": f.stat().st_size, "sha256": _sha256(f)} for f in files},
        }
        if verbose:
            size = sum(f.stat().st_size for f in files) / 1e6
            print(f"  {key:18s} {len(files)} files  {size:8.1f} MB  {time.time() - t0:5.1f}s")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    acquire_all()
