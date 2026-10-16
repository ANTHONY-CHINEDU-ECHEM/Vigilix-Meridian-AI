# Architecture

Vigilix Meridian is organised as five layers, each of which can be rebuilt and tested on its own. Every layer reads only the outputs of the layer before it, so a change to one source or one model never requires hand edits elsewhere.

## 1. Acquisition (`vigilix/data/acquire.py`)

Every source is pinned to a Git commit, a Git LFS object or a PyPI release and fetched with a sparse checkout, so only the required files cross the network. Each file is recorded in `data/raw/MANIFEST.json` with its byte count and SHA256 digest, and re running the command skips anything already present. Using version controlled mirrors rather than live portals makes the build reproducible and lets it run on networks that only allow package registries and GitHub.

## 2. Knowledge base (`vigilix/kb/build.py`)

The builder parses every source (`vigilix/data/sources.py`), then produces four artefacts.

**Dictionaries.** A drug dictionary of 4,945 substances unifies WHO ATC names, DrugBank compounds from Hetionet, brand names from the lexicon, the substances behind every annotated label, FAERS product names and the OHDSI reference set drugs. A reaction dictionary of about 11,000 terms unifies SIDER side effects, FAERS preferred terms, label annotator terms and OHDSI outcomes, each with a System Organ Class taken from the FAERS table where available and from a rule table otherwise. A longest match linker finds mentions in prose. Names that collide with study vocabulary ("blind", "infusion", "weight") or with indications ("asthma", "schizophrenia") are kept for exact lookup but never linked inside text, which removed most false entity links found during development.

**FAERS signal scores.** Each of the four FAERS extracts is scored separately because each has its own background: PRR, ROR, Yates chi square, the BCPNN information component with its credibility interval, and the MGPS empirical Bayes geometric mean with a two component gamma prior fitted by maximum likelihood per dataset. Each pair is compared with label derived references, and a cluster detector flags runs of near identical counts with high disproportionality, a classic artefact of duplicated or mass submitted reports.

**Knowledge graph.** About 21 thousand nodes and 194 thousand edges with provenance on every edge: labelled reactions (SIDER and the annotated labels), case reported reactions (ADE corpus, with PubMed identifiers), literature chemical induced disease (BioCreative CDR), FAERS signals (with EBGM, EB05, ROR and counts), documented interactions (DDI corpus, typed), ATC and DrugCentral classes, indications and targets.

**Passage corpus.** 130,957 passages from 51,707 documents. Randomised trial abstracts are kept only when they contain safety language and a linked drug (43,080 of 195,654). Abstracts are chunked into windows of about 170 words with one sentence of overlap and their objective sentence as the passage title; label sections are chunked by paragraph and table row; graph facts are rendered as readable passages per drug and System Organ Class so they can be retrieved and cited like any other evidence.

## 3. Retrieval (`vigilix/rag`)

```
question
  │ guard: identifier redaction, crisis, scope, dosing, injection
  │ query understanding: intents, linked drugs and reactions, populations
  ▼
candidate generators (in parallel)
  ├─ BM25 over 131k passages (sparse weight matrix, ~3 ms)
  ├─ dual encoder over word2vec SIF vectors (dense, ~7 ms)
  ├─ entity routed BM25 inside passages that mention the query drug and reaction
  ├─ guidance routing (best knowledge cards)
  └─ label routing (best label sections for the query drug)
  ▼
reciprocal rank fusion → 49 features → LightGBM LambdaMART → two passages per document at most
  ▼
knowledge graph evidence for the linked drug and reaction pairs (a citable item)
  ▼
writer: local LLM through Ollama, or the extractive composer
  ▼
sentence verifier: learned support probability plus hard rules for numbers, drugs and citations
  ▼
confidence from verification, evidence level and entity coverage; audit log entry
```

**Normalisation** (`text.py`) folds British spelling, brand names, abbreviations and lay phrases (abbreviations and lay phrases are expanded, not replaced, so both forms match). The same rules are ported to TypeScript and a test checks byte for byte parity on a shared fixture.

**Dense retrieval** is trained entirely in domain because no pretrained weights are needed or assumed: skip gram word2vec on the corpus, smooth inverse frequency sentence vectors, then a dual encoder of two linear towers trained with a symmetric in batch InfoNCE loss on about 137 thousand mined pairs (objectives against their results, inverse cloze sentences, titles against content, and template questions with brand names and lay terms substituted). Gradients are derived analytically and optimised with Adam in NumPy. A `sentence_transformers` encoder such as MedCPT can be plugged in when weights are available.

**The reranker** is trained on about 4,000 synthetic queries generated from the knowledge base (never from the evaluation questions) with graded labels: 2 for passages of the generating document, 1 for passages that mention the same drug and reaction. A second, lexical only reranker (no dense features) is trained on the same rows for the browser engine.

**The verifier** scores eleven features of each sentence against the evidence it cites and is trained on perturbations of real corpus sentences: changed numbers, swapped drugs, swapped reactions, flipped negation, wrong citations and paraphrases. A number absent from the cited evidence, a drug the evidence does not mention or a missing citation make a sentence unsupported regardless of the probability.

## 4. Pharmacovigilance services

* **Signal explorer** (`vigilix/signals`) and the disproportionality calculator.
* **Label intelligence** (`vigilix/extraction/labels.py`): dictionary mining with negation scope, compared with annotated adverse events and with FAERS signals for the same substance.
* **Adverse event extraction** (`vigilix/extraction/ade.py`): sentence classifier, CRF span tagger with dictionary features and a relation classifier.
* **Interaction checker** (`vigilix/interactions/checker.py`): documented interactions, pharmacokinetic mechanisms from a curated CYP450, transporter and renal clearance table, pharmacodynamic overlap in serious reaction groups and cumulative burden across a regimen.
* **Case intake and causality** (`vigilix/causality/assess.py`): redaction, extraction, seriousness, outcome, time to onset, dechallenge and rechallenge, ICSR minimum criteria, expectedness, a pre filled Naranjo scale and a WHO UMC category.

## 5. Delivery

The FastAPI service (`vigilix/api`) exposes every capability and serves the React interface. The interface talks to one contract (`frontend/src/api.ts`) implemented twice: by the service, and by an in browser engine (`frontend/src/engine`) that loads a 19 MB exported bundle and runs retrieval, reranking, composition, verification, signal scoring, label mining, interaction screening and case intake locally. The browser engine is what powers the hosted demo.

## Design decisions

* **The model writes, the evidence speaks.** The language model never acts as a source; every sentence must cite a numbered evidence item, and the graph summary is itself a citable item derived from data.
* **Disproportionality is shown with its context.** Every signal is displayed with its label status, its interval, all four screening rules and a cluster warning where relevant.
* **No hidden dependence on network models.** Every learned component trains on a laptop CPU from public data, so the system can run inside a hospital network.
* **Honest evaluation.** The blind question set was written before the retriever existed, its hash was recorded, and it was scored once after every component was frozen.
