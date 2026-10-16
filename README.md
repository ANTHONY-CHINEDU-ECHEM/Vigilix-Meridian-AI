# Vigilix Meridian AI

**A pharmacovigilance intelligence platform that answers drug safety questions from 131 thousand cited passages, scores spontaneous reports with four disproportionality methods, mines product labels, screens interactions and pre fills causality assessment, all on local hardware with every claim verified against its evidence.**
<p align="center">
<img width="1440" height="900" alt="overview" src="https://github.com/user-attachments/assets/d4513b72-5bf7-40aa-bbc0-f031df9155e3" />
</p>

## Project brief

Pharmacovigilance is the work of noticing that a medicine is hurting people before the harm becomes a pattern. Safety teams at manufacturers, regulators and hospitals read spontaneous adverse event reports, case reports, trial publications and product labels, and they must decide, often under time pressure, whether a drug and an event belong together, whether the association is already known, and whether it is serious enough to act on. The evidence is scattered across sources that speak different languages: FAERS reports use MedDRA preferred terms, labels use regulatory prose, literature uses clinical narrative, and every source spells drugs and reactions differently. A safety reviewer who asks "is rhabdomyolysis with rosuvastatin a known signal and what is the strength of the reporting association" needs answers from four places at once, with numbers that can be checked.

Vigilix Meridian AI brings those sources into one knowledge base and one workbench. It parses 196 thousand randomised trial abstracts, 2,972 annotated case reports, 1,500 chemical induced disease abstracts, 905 interaction documents, 1,219 annotated label sections from the United States, the United Kingdom and the European Union, 22,746 FAERS drug and event pairs across four extracts, and a biomedical knowledge graph of 21,084 nodes and 194,109 edges. A retrieval pipeline with sparse, dense, entity routed and graph evidence, followed by a learned reranker, finds the passages that answer a question; a local language model or an extractive writer drafts an answer in which every sentence cites a numbered evidence item; and a learned verifier checks each sentence against the evidence it cites before anything is shown. Around the copilot sit the tools a safety scientist actually uses: a signal explorer with PRR, ROR, the BCPNN information component and MGPS empirical Bayes scores, a disproportionality calculator, label intelligence with mined and annotated terms, a drug safety profile, an interactive knowledge graph, an interaction checker, case intake with Naranjo and WHO UMC causality, an evaluation page and an append only audit log.

The project is built to be trusted rather than admired. Every learned component, from the word2vec vectors and the dual encoder to the LambdaMART reranker, the CRF extractor and the claim verifier, trains on a laptop CPU from public data, so the whole system can run inside a hospital network without sending a single request outside it. Disproportionality is always shown with its interval, its label status, all four screening rules and a warning when the counts look like a duplicated or mass submitted report cluster, because a high ratio is a reason to look, not a finding. The evaluation was set up before the retriever existed: 60 development questions guided the work and 30 blind questions, whose hash was recorded when they were written, were scored once after every component was frozen. The same interface runs against the FastAPI service or entirely inside the browser from a 19 MB exported bundle, which is how the live demo works with no server at all.

## What it does

| Workspace | What a reviewer can do |
| --- | --- |
| Evidence copilot | Ask a safety question in plain language; get an answer whose every sentence cites numbered evidence, is verified against it and carries a confidence level, with the full evidence list, the query understanding and the graph summary alongside |
| Signal explorer | Browse 22,746 FAERS drug and event pairs from four extracts with PRR, ROR, chi square, IC025 and EB05; filter by dataset, drug, System Organ Class, minimum cases, unlabelled only and report clusters; see each pair as a two by two table with intervals |
| Disproportionality calculator | Enter any two by two table and get every measure with its interval and every screening rule, scored against the background prior of a chosen dataset |
| Label intelligence | Read 1,219 label sections with mined adverse event terms highlighted, compare them with expert annotations and with FAERS signals for the same substance |
| Drug safety profile | One page per drug: labelled reactions by System Organ Class, FAERS signals, case reports, literature, interactions, classes, indications and targets |
| Knowledge graph | Explore a safety prioritised neighbourhood of any drug or reaction with provenance on every edge |
| Interaction checker | Screen a regimen for documented interactions, pharmacokinetic mechanisms (CYP450, transporters, renal clearance), shared serious reaction groups and cumulative burden |
| Case intake and causality | Paste a narrative; identifiers are redacted, drugs and events are extracted, seriousness, outcome, onset, dechallenge and rechallenge are detected, ICSR validity is checked and a Naranjo score and a WHO UMC category are pre filled for the assessor to confirm |
| Evaluation and governance | Every metric in this README, live, with the known limitations next to the results |
| Audit log | Append only record of every question with redacted text, a hash of the original, the engine, verification share and confidence |

## Live demo

The demo runs the full system in your browser from an exported bundle: retrieval over all 130,957 passages, the lexical LambdaMART reranker, the extractive writer, the claim verifier, signal scoring, label mining, interaction screening and case intake. Nothing you type leaves your browser.

**[Open the Vigilix Meridian demo](https://claude.ai/artifact/CTnaQ9frLU7jB7SaUvsq2z)**

To run it yourself with the server and an optional local model, see [Running it](#running-it).

## Screenshots

**Evidence copilot.** A cited, verified answer about statin associated rhabdomyolysis with the evidence list and graph summary.

<p align="center">
<img width="1440" height="2493" alt="copilot" src="https://github.com/user-attachments/assets/d184da73-e686-46ba-93c7-d7c482c92296" />
</p>

**Signal explorer.** EB05 against report count for one extract, unlabelled pairs highlighted, with the two by two card for the selected pair.

<p align="center">
<img width="1440" height="1411" alt="signals" src="https://github.com/user-attachments/assets/191d6662-db6b-4a85-9ff7-5ddfafebde9a" />
</p>

**Drug safety profile.** Labelled reactions by System Organ Class next to FAERS signals, case reports and interactions.

<p align="center">
<img width="1440" height="1175" alt="drug_profile" src="https://github.com/user-attachments/assets/b12b4d0a-203b-4397-9163-32d2df2fad2b" />
</p>

**Knowledge graph.** A safety prioritised neighbourhood with edge provenance. 

<p align="center">
<img width="1440" height="900" alt="graph" src="https://github.com/user-attachments/assets/8c430526-a568-45f6-9a74-bcf94007f7ca" />
</p>

**Interaction checker.** Pairwise levels with documented sentences, mechanisms and shared reaction groups. 

<p align="center">
<img width="1440" height="967" alt="interactions" src="https://github.com/user-attachments/assets/f17f2cc5-62fa-4731-b013-215df12077e7" />
</p>

**Label intelligence.** Mined terms highlighted in the label text and compared with the expert annotation.

<p align="center">
<img width="1440" height="1398" alt="labels" src="https://github.com/user-attachments/assets/0e94dd8e-321d-4c89-827b-2ed6291fd768" />
</p>

**Case intake and causality.** Redacted narrative, extracted pairs, seriousness and pre filled Naranjo and WHO UMC assessments. 

<p align="center">
<img width="1440" height="1605" alt="case_intake" src="https://github.com/user-attachments/assets/20b6bc29-80ee-44f3-8277-3c7fd459e682" />
</p>

**Evaluation and governance.** Retrieval ablation, answer faithfulness, signal detection and safety probes.

<p align="center">
<img width="1440" height="1178" alt="evaluation" src="https://github.com/user-attachments/assets/1ed3a796-1764-464a-b1a3-3fc1995ad6f6" />
</p>

The interface is responsive and has a dark theme.

MOBILE

<p align="center">
<img width="780" height="1688" alt="mobile" src="https://github.com/user-attachments/assets/6af4b0fa-b84f-47c8-bb89-baedb45155cc" />
</p>

DARK THEME

<p align="center">
<img width="1440" height="900" alt="dark" src="https://github.com/user-attachments/assets/c5baa72e-ff75-45d2-bd67-f9c84e5f5f6c" />
</p>

## Architecture

```
                         ┌──────────────────────────────────────────────────────────────┐
  public sources ──────► │ acquisition: pinned Git commits, LFS objects and PyPI wheels │
                         └───────────────────────────────┬──────────────────────────────┘
                                                         ▼
       ┌───────────────────────── knowledge base builder ──────────────────────────┐
       │ drug and reaction dictionaries   FAERS scores (PRR, ROR, IC, EBGM)        │
       │ knowledge graph with provenance  passage corpus of 130,957 passages        │
       └───────────────────────────────────────┬───────────────────────────────────┘
                                               ▼
       ┌──────────────────────────────── index and models ─────────────────────────┐
       │ BM25   word2vec + SIF   dual encoder   LambdaMART reranker (49 features)  │
       │ claim verifier   CRF adverse event extractor   label miner               │
       └───────────────────────────────────────┬───────────────────────────────────┘
                                               ▼
  question ─► guard ─► query understanding ─► candidates (BM25, dense, entity, card, label)
            ─► fusion ─► reranker ─► graph evidence ─► writer (Ollama or extractive)
            ─► sentence verifier ─► confidence ─► audit log ─► answer with citations
                                               ▼
       ┌──────────────── FastAPI service  or  in browser engine ─────────────────┐
       │                 one contract, one React interface                        │
       └──────────────────────────────────────────────────────────────────────────┘
```

The system has five layers, each rebuilt by one make target and each reading only the outputs of the layer before it. The full description, including the reasoning behind each design choice, is in [docs/architecture.md](docs/architecture.md).

1. **Acquisition** fetches every source from a pinned Git commit, Git LFS object or PyPI release with a sparse checkout and records the byte count and SHA256 digest of every file.
2. **The knowledge base builder** unifies 4,945 drugs and 11,012 reaction terms into dictionaries, scores every FAERS extract, builds the knowledge graph and chunks every source into passages with titles, entities and evidence levels.
3. **Index and models** builds BM25, trains word2vec, SIF vectors and a dual encoder, trains the reranker on 4,081 synthetic queries, the verifier on 35,859 perturbed sentences and the adverse event extractor on the ADE corpus.
4. **Pharmacovigilance services** expose signals, labels, interactions, causality and the copilot.
5. **Delivery** is a FastAPI service and a React interface that also runs on an in browser engine implementing the same contract.

## Data foundation

| Source | What it contributes | Scale |
| --- | --- | --- |
| PubMed 200k RCT | Randomised trial abstracts with sentence roles, kept when they contain safety language and a linked drug | 43,080 of 195,654 abstracts |
| ADE corpus V2 | Case report sentences with gold drug and adverse effect relations | 2,972 reports |
| DDI corpus 2013 | DrugBank and MEDLINE texts with typed interaction annotations | 905 documents, 5,000 positive pairs |
| BioCreative V CDR | Chemical induced disease abstracts | 1,500 abstracts |
| Annotated product labels (Demner Fushman, OnSIDES) | US prescribing information, UK and EU SmPC section 4.8, US paediatric sections with annotated adverse events | 1,219 sections, 56,331 annotated events |
| Hetionet | SIDER side effects, DrugCentral classes, indications, DrugBank targets | 1,552 compounds |
| FAERS extracts | Sedatives 2021 to 2023, beta blockers 2021 to 2023, statins 2014 to 2020, and four fast track COVID 19 products | 22,746 drug and event pairs |
| OMOP and EU ADR reference sets | Expert positive and negative controls | 492 pairs |
| WHO ATC index | Therapeutic classification | 7,536 codes |
| Guidance digests | Summaries of regulatory guidance, methods and class safety, each with references | 77 cards |

Together they make 130,957 passages from 51,707 documents (15.6 million words), and a knowledge graph of 21,084 nodes and 194,109 edges.

KNOWLEDGE BASE COMPOSITION

<p align="center">
<img width="1191" height="555" alt="kb_composition" src="https://github.com/user-attachments/assets/631dd9c8-02ad-4439-8079-97c6765554b6" />
</p>

| Graph relation | Edges | Provenance |
| --- | ---: | --- |
| Labelled reaction | 161,080 | SIDER and annotated labels |
| Targets | 11,571 | DrugBank through Hetionet |
| In class | 6,283 | ATC and DrugCentral |
| Case reported | 4,670 | ADE corpus with PubMed identifiers |
| Interacts | 3,980 | DDI corpus, typed |
| FAERS signal | 3,195 | EBGM, EB05, ROR and counts per extract |
| Literature induced | 2,185 | BioCreative CDR |
| Treats | 1,145 | PharmacotherapyDB through Hetionet |

Licences, citations, processing notes and known biases are in the [data card](docs/data_card.md).

## Methods

### Normalisation and dictionaries

Drug and reaction names arrive in many forms: British and American spelling, brand names, abbreviations and lay language. A normaliser folds spelling (with guard rules so that "angioedema" is not broken by the "oedema" rule), maps brands to generic names, expands abbreviations and lay phrases alongside the original so both forms match, and applies a conservative stemmer. A longest match linker finds drug and reaction mentions in text, and names that collide with study vocabulary ("blind", "infusion", "weight") or with indications are kept for exact lookup but never linked inside prose. The same rules run in Python and TypeScript, and a parity test checks that both produce identical tokens on a shared fixture.

### Disproportionality

Each FAERS extract is scored against its own background, never pooled.

| Measure | Definition | Signal rule used |
| --- | --- | --- |
| PRR | (a / (a + b)) / (c / (c + d)) | Evans: PRR at least 2, Yates chi square at least 4, at least 3 cases |
| ROR | (a d) / (b c) with Haldane correction | Lower 95% limit above 1 |
| Information component | log2 of observed over expected with BCPNN shrinkage | IC025 above 0 |
| EBGM | MGPS posterior geometric mean with a two component gamma prior fitted by maximum likelihood per extract | EB05 at least 2 |

All p values are adjusted with Benjamini Hochberg. Each pair is also compared with label derived references (only for drugs with at least 20 listed reactions, so that expectedness is never asserted from an absent reference) and checked by a report cluster detector, which flags runs of at least five terms with counts within 1% of each other and a median EB05 of at least 3, the pattern left by duplicated or mass submitted reports.

### Retrieval

| Stage | Method |
| --- | --- |
| Sparse | BM25 over 78,980 terms, stored as a sparse weight matrix |
| Dense | Skip gram word2vec (44,821 words) trained on the corpus, smooth inverse frequency sentence vectors, and a dual encoder of two linear towers trained with symmetric in batch InfoNCE on 137 thousand mined pairs, with analytic gradients and Adam in NumPy |
| Routing | Entity routed BM25 inside passages mentioning the query drug and reaction; guidance card routing; label section routing |
| Fusion | Reciprocal rank fusion of every generator |
| Reranking | LightGBM LambdaMART over 49 features, trained on 4,081 synthetic queries generated from the knowledge base (never from the evaluation questions) with graded labels |
| Diversity | At most two passages per document in the final evidence |
| Graph evidence | A citable summary of labelled, reported, literature, FAERS and interaction edges for the linked drug and reaction pairs |

<p align="center">
<img width="774" height="509" alt="dense_training" src="https://github.com/user-attachments/assets/19d1ca23-4bf1-4221-9631-c806afd62eee" />
</p>

### Writing and verification

The writer is a local model through Ollama (any chat model; `llama3.1:8b` by default) or, when no model is available, an extractive composer that selects and orders verbatim evidence sentences. Either way every sentence must cite a numbered evidence item. The verifier scores eleven features of each sentence against the evidence it cites (token, bigram and best sentence support, numbers, drug and reaction consistency, sentence aligned negation agreement, citation validity) with a logistic regression trained on 35,859 perturbed corpus sentences. Hard rules override the probability: a number absent from the cited evidence, a drug the evidence does not mention or a missing citation always makes a sentence unsupported. Confidence combines the verified share, the evidence level of the cited sources and entity coverage.

### Safety controls

A guard runs before retrieval and redacts NHS numbers, other identifiers, dates of birth, dates, emails, phone numbers, postcodes, record numbers, titled names and ages above 89; routes first person crisis language to crisis support instead of retrieval; declines clearly unrelated questions; answers individual dosing requests with a fixed notice; and neutralises prompt injection in the question and in every retrieved passage. Details are in [docs/safety.md](docs/safety.md).

### Adverse event extraction, label mining, interactions and causality

| Component | Method |
| --- | --- |
| Adverse event extractor | TF IDF logistic regression sentence classifier, a CRF span tagger with dictionary features trained on positive sentences, and a relation classifier, all on the ADE corpus with a split by PubMed identifier |
| Label miner | Dictionary matching over label sections with a negation window and heading detection, scored against expert annotations |
| Interaction checker | Documented DDI corpus sentences, a curated pharmacokinetic table (CYP3A4, CYP2D6, CYP2C9, CYP2C19, CYP1A2, P glycoprotein, OATP1B1, renal clearance) and pharmacodynamic overlap in serious reaction groups, combined into a heuristic triage level |
| Causality | Narrative parsing for seriousness, outcome, onset, dechallenge and rechallenge, ICSR minimum criteria, expectedness, a pre filled Naranjo scale and a WHO UMC category |

## Results

All numbers below come from `reports/evaluation_summary.json`, produced by `make evaluate_blind` on a clean build. Methodology and per question results are in [docs/evaluation.md](docs/evaluation.md).

### Retrieval

Relevance is graded before retrieval: grade 2 for passages from the source document a question was written about, grade 1 for passages that mention the right drug and reaction or contain every required phrase. Strict recall counts only grade 2.

**Blind set (30 questions, scored once after freezing; hash verified: yes)**

| Retriever | Recall@5 | Strict recall@5 | MRR@10 | nDCG@10 | ms per query |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.800 | 0.700 | 0.686 | 0.649 | 4.5 |
| SIF vectors | 0.400 | 0.300 | 0.348 | 0.304 | 5.5 |
| Dual encoder | 0.500 | 0.300 | 0.400 | 0.355 | 7.5 |
| BM25 and dual encoder fused | 0.600 | 0.467 | 0.570 | 0.529 | 7.4 |
| Entity routed BM25 | 0.667 | 0.567 | 0.638 | 0.612 | 9.1 |
| **Full pipeline with reranker** | **0.967** | **0.900** | **0.948** | **0.911** | 60.8 |

**Development set (60 questions)**

| Retriever | Recall@5 | Strict recall@5 | MRR@10 | nDCG@10 | ms per query |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.933 | 0.767 | 0.911 | 0.836 | 3.0 |
| SIF vectors | 0.733 | 0.483 | 0.651 | 0.559 | 5.8 |
| Dual encoder | 0.783 | 0.617 | 0.672 | 0.615 | 6.2 |
| BM25 and dual encoder fused | 0.900 | 0.733 | 0.810 | 0.734 | 6.7 |
| Entity routed BM25 | 0.900 | 0.767 | 0.858 | 0.804 | 8.4 |
| **Full pipeline with reranker** | **1.000** | **0.967** | **0.951** | **0.940** | 69.7 |

<p align="center">
<img width="1134" height="599" alt="retrieval_ablation" src="https://github.com/user-attachments/assets/ed0963c3-0876-4a1a-9e87-3d9461e8a584" />
</p>

The full pipeline improves on the best single generator by 26.2 nDCG@10 points on the blind set. The reranker learned to trust fusion first, then entity routing and exact drug matches:

<p align="center">
<img width="987" height="625" alt="reranker_importance" src="https://github.com/user-attachments/assets/339f6286-5889-4e78-a3aa-6e154ced0262" />
</p>

| Reranker | Value |
| --- | --- |
| Training queries | 4,081 |
| Training rows | 575,216 |
| Best iteration | 116 |
| Validation nDCG@5 | 0.872 |
| Validation nDCG@10 | 0.893 |

### Grounded answers

Measured with the extractive writer over all 90 development and blind questions, so the numbers do not depend on a particular language model.

| Metric | Value |
| --- | --- |
| Sentences verified as supported | 98.0% |
| Sentences unsupported | 2.0% |
| Answers with an unverifiable number | 0 |
| Answers where every sentence carries a citation | 100.0% |
| Answers citing at least one relevant passage | 96.7% |
| Answers citing guidance or a label | 83.3% |
| Answers using graph evidence | 53.3% |
| Confidence high, moderate, low | 83, 6, 1 |
| Median latency | 26.3 ms |
| Safety probes passed | 5 of 5 |

### Claim verifier

| Perturbation | Test sentences | Accuracy |
| --- | ---: | ---: |
| Verbatim sentence (supported) | 1,774 | 100.0% |
| Paraphrase (supported) | 1,789 | 97.8% |
| Wrong citation | 1,771 | 100.0% |
| Drug swapped | 892 | 99.7% |
| Reaction swapped | 622 | 99.2% |
| Negation flipped | 1,228 | 99.7% |
| Number changed | 889 | 93.7% |

Overall AUROC 0.999 and accuracy with hard rules 98.8% on 8,965 held out sentences.

<p align="center">
<img width="1053" height="532" alt="verifier_perturbations" src="https://github.com/user-attachments/assets/1a5a5a95-e709-48d2-9580-903d7bb1972b" />
</p>

### Signal detection

Each measure was scored against label derived references on the 7,280 drug and event pairs from the three MDDC extracts (21 drugs, 21.9% of pairs labelled). This is a hard and honest test: labels list many reactions that are rarely reported and FAERS is full of reactions that are reported but not causal.

| Measure | AUROC | Average precision |
| --- | ---: | ---: |
| Random | 0.500 | 0.219 |
| PRR | 0.574 | 0.252 |
| ROR lower 95% | 0.592 | 0.262 |
| IC025 | 0.596 | 0.266 |
| EB05 | 0.593 | 0.264 |
| Report count | 0.652 | 0.338 |

| Screening rule | Pairs flagged | Precision | Recall |
| --- | ---: | ---: | ---: |
| Evans (PRR, chi square, n) | 1,790 | 0.258 | 0.289 |
| ROR lower limit above 1 | 2,431 | 0.275 | 0.419 |
| IC025 above 0 | 2,306 | 0.276 | 0.398 |
| EB05 at least 2 | 1,416 | 0.266 | 0.236 |

<p align="center">
<img width="964" height="509" alt="signal_auroc" src="https://github.com/user-attachments/assets/f8632f83-4ab2-4f8c-bf54-5ba38ff988e2" />
</p>

| Extract | Pairs | Labelled share | AUROC of EB05 | AUROC of report count |
| --- | ---: | ---: | ---: | ---: |
| Beta blockers 2021 to 2023 | 2,204 | 26.1% | 0.623 | 0.657 |
| Sedatives 2021 to 2023 | 4,773 | 19.7% | 0.591 | 0.644 |
| Statins 2014 to 2020 | 303 | 27.4% | 0.498 | 0.667 |

| Term frequency band | Pairs | Labelled share | AUROC of EB05 | AUROC of report count | Precision of EB05 rule |
| --- | ---: | ---: | ---: | ---: | ---: |
| Most frequently reported 20% of terms | 1,453 | 40.2% | 0.603 | 0.586 | 0.420 |
| Middle 60% | 4,377 | 18.8% | 0.631 | 0.624 | 0.270 |
| Least frequently reported 20% | 1,450 | 13.2% | 0.650 | 0.648 | 0.223 |

Removing the 164 pairs in flagged report clusters changes the EB05 rule precision from 0.266 to 0.269.

Every one of the 13 OMOP and EU ADR reference controls that overlap the extracts agrees with the EB05 rule (3 positive controls, all three statin and rhabdomyolysis pairs, flagged; 10 negative controls not flagged).

<p align="center">
<img width="888" height="602" alt="signal_screen_atorvastatin" src="https://github.com/user-attachments/assets/d6b77406-b5fb-4cd9-9290-0d594ee624d2" />
</p>

### Adverse event extraction

Test split of 4,269 sentences from 594 PubMed records never seen in training.

| Task | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Adverse event sentence classification | 0.695 | 0.724 | 0.709 |
| Drug spans, CRF, exact | 0.883 | 0.745 | 0.808 |
| Drug spans, CRF, overlap | 0.903 | 0.770 | 0.831 |
| Drug spans, dictionary baseline | 0.560 | 0.496 | 0.526 |
| Effect spans, CRF, exact | 0.740 | 0.661 | 0.698 |
| Effect spans, CRF, overlap | 0.883 | 0.794 | 0.836 |
| Effect spans, dictionary baseline | 0.356 | 0.376 | 0.366 |
| Drug and effect relations end to end, CRF | 0.639 | 0.487 | 0.553 |
| Drug and effect relations end to end, dictionary | 0.181 | 0.170 | 0.175 |

<p align="center">
<img width="1045" height="486" alt="extraction_f1" src="https://github.com/user-attachments/assets/e67b939d-faff-439b-bdeb-e1e11db36a4b" />
</p>

### Label mining

| Label group | Sections | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| US prescribing information, adverse reactions | 99 | 0.851 | 0.745 | 0.795 |
| US prescribing information, warnings and precautions | 96 | 0.525 | 0.572 | 0.547 |
| US prescribing information, boxed warning | 41 | 0.530 | 0.486 | 0.507 |
| US paediatric use sections | 147 | 0.605 | 0.729 | 0.662 |
| UK SmPC section 4.8 | 199 | 0.617 | 0.748 | 0.676 |
| EU SmPC section 4.8 | 200 | 0.899 | 0.638 | 0.746 |
| **All sections** | 782 | 0.741 | 0.681 | 0.710 |

<p align="center">
<img width="1123" height="532" alt="label_mining" src="https://github.com/user-attachments/assets/4b01df9c-a2b9-49d9-8298-588855958cc7" />
</p>

## Key insights

1. **No single retriever is enough for safety questions.** On the blind set BM25 alone found relevant evidence in the top five for 80% of questions and the in domain dense encoders for at most 50%, but the full pipeline reached 96.7% with strict recall of 90%. The blind questions are written the way people actually ask ("my patient on Lipitor has muscle aches"), with brand names, lay words and British spelling, and the gap between the single generators and the full pipeline is much wider on them than on the development set. Normalisation, entity routing and the reranker do the work that a larger embedding model would otherwise be asked to do.

2. **The reranker learned to trust agreement, then entities.** Reciprocal rank fusion carries 42% of the gain, followed by the rank in the entity routed list (10%) and an exact drug match (8%). The model rewards a passage that several independent generators agree on and that names the drug the reviewer asked about, which is how a careful human reviewer reads search results too.

3. **Verification catches what matters most, numbers and negation, but not perfectly.** The verifier rejects swapped drugs, swapped reactions, flipped negation and wrong citations at 99% or better, and the hard rules mean an invented number can never be shown as supported. Changed numbers are the hardest case (93.7%) because the replacement number often appears elsewhere in the same passage, which is why the interface shows the cited passage beside every sentence.

4. **Disproportionality measures barely separate labelled from unlabelled reactions, and that is the honest result.** Against label derived references across 7,280 pairs, every measure reaches an AUROC between 0.57 and 0.60, and the raw report count does better (0.65) because labels list the reactions that are common. The value of EB05 shows up where it is designed to help: among the least frequently reported terms its AUROC rises to 0.65, and all 13 expert reference controls that overlap the data are classified correctly, including every statin and rhabdomyolysis pair.

5. **Rules trade precision for recall in a predictable order.** The ROR and IC rules flag about 2,400 pairs with recall near 40%, the Evans rule flags 1,790 and EB05 at least 2 is the most conservative at 1,416 with recall of 24%. Precision stays near 27% for all of them, so the choice of rule is a choice of workload, not of accuracy, and the signal explorer lets a reviewer switch between them.

6. **Report clusters are real and removable.** The cluster detector flagged 164 pairs whose counts run in near identical chains with high EB05, the trace of duplicated or mass submitted reports. They are hidden by default in the overview and flagged everywhere else rather than deleted, because a reviewer should see that the pattern exists.

7. **Span detection, not relation classification, is the bottleneck in case report extraction.** Given correct entities, drug and effect pairing is trivial (F1 0.998, the same as a majority baseline), but end to end F1 is 0.55 because effect spans have fuzzy boundaries ("severe muscle pain and weakness"). Overlap F1 of 0.83 to 0.84 shows that most misses are boundary disagreements rather than missed events, which is good enough for pre filling a case form that a person confirms.

8. **Label mining works best where labels are structured.** Mined terms reach F1 0.80 on US adverse reaction sections, which are largely lists and tables, and drop to about 0.5 on boxed warnings and warnings sections, where reactions are described in clinical sentences that annotators normalised to terms that do not appear verbatim.

## Running it

Requirements: Python 3.11 or newer, Node 20 or newer, about 8 GB of memory and 4 GB of disk. A GPU is not needed.

```
make install       # Python package and interface dependencies
make all           # data, knowledge base, index, models, evaluation, browser bundle and interface
make serve         # http://localhost:8000, API documentation at /docs
```

`make all` takes about 30 minutes on two CPU cores. Each stage can be run on its own:

| Target | What it does |
| --- | --- |
| `make data` | Download every source with checksums |
| `make kb` | Dictionaries, FAERS scores, knowledge graph and passage corpus |
| `make index` | BM25, word2vec, SIF vectors and the dual encoder |
| `make train` | Reranker (full and lexical), claim verifier and adverse event extractor |
| `make evaluate` | Every evaluation on the development questions, reports and figures |
| `make evaluate_blind` | The same, plus the frozen blind set |
| `make export` | Offline browser bundle |
| `make web` | Production build of the interface |
| `make test` | Python and TypeScript test suites |
| `make docker` | Docker Compose with an Ollama container and the service |

To use a local language model, install [Ollama](https://ollama.com), pull any chat model (for example `ollama pull llama3.1:8b`) and start the service; it is detected automatically. Without a model the extractive writer is used. Configuration uses environment variables prefixed `VIGILIX_` (writer provider, model name, Ollama address, data directory, audit database and allowed origins). Deployment inside a hospital network, Docker and static hosting are covered in [docs/deployment.md](docs/deployment.md).

## API

| Method and path | Purpose |
| --- | --- |
| `POST /api/ask` | Cited, verified answer with evidence, query understanding and confidence |
| `POST /api/ask/stream` | The same as server sent events |
| `POST /api/search` | Ranked passages for any retrieval mode |
| `GET /api/drugs/{name}` | Drug safety profile |
| `GET /api/reactions/{name}` | Drugs linked to a reaction |
| `GET /api/graph/{name}` | Knowledge graph neighbourhood |
| `GET /api/signals` | Filtered, scored FAERS pairs |
| `POST /api/signals/compute` | Every measure for any two by two table |
| `GET /api/labels/{doc_id}` | Label section with mined and annotated terms |
| `POST /api/interactions` | Regimen screening |
| `POST /api/case/intake` | Narrative extraction and causality |
| `GET /api/evaluation` | Evaluation summary |
| `GET /api/audit` | Audit log |

Example:

```python
import requests

reply = requests.post(
    "http://localhost:8000/api/ask",
    json={"question": "Is rhabdomyolysis with rosuvastatin a known signal?"},
).json()
for sentence in reply["answer"]:
    print(sentence["text"], sentence["citations"], sentence["verification"]["status"])
```

The complete reference with every parameter is in [docs/api.md](docs/api.md), and interactive documentation is served at `/docs`.

## Repository structure

```
vigilix/
  data/            acquisition and source parsers
  kb/              dictionaries, knowledge base builder, curated content (lexicon, cards, PK table)
  signals/         PRR, ROR, IC, EBGM, gamma prior fitting, cluster detection
  rag/             normaliser, BM25, dense encoders, retriever, reranker, guard, writer, verifier, pipeline
  extraction/      adverse event extractor and label miner
  interactions/    interaction checker
  causality/       Naranjo, WHO UMC and case intake
  eval/            questions, retrieval, answer and signal evaluation, figures
  export/          browser bundle export
  api/             FastAPI service and audit log
frontend/
  src/pages/       eleven workspaces
  src/components/  shared interface and chart components
  src/engine/      in browser engine: normaliser, BM25, GBDT reranker, writer, verifier, statistics, tools
scripts/           one script per make target
tests/             Python tests
reports/           evaluation results and figures
docs/              architecture, data card, model card, evaluation, safety, API, deployment
deploy/            Dockerfile, Compose file, Hugging Face Space notes
```

## Limitations and responsible use

* **Not a medical device.** Vigilix Meridian is a research and portfolio system. It has not been clinically validated and must not be used for decisions about an individual patient.
* **Disproportionality is not causation.** Reporting ratios measure reporting, which is shaped by notoriety, stimulated reporting, duplicates and confounding by indication. The signal evaluation shows how weakly any measure separates labelled from unlabelled pairs in practice.
* **Label references are incomplete.** Labelled status comes from SIDER and annotated labels; some common drugs have no SIDER entries, and expectedness is only asserted when coverage is meaningful.
* **The FAERS data are extracts.** Three MDDC tables and four COVID 19 product tables, not the full database, and the MDDC tables exclude two common terms.
* **The literature stops in 2017.** PubMed 200k RCT ends there; newer knowledge enters only through the guidance digests, which must be checked against current guidance.
* **The interaction level is heuristic triage**, not a validated severity scale, and it is always shown with its underlying evidence.
* **Causality pre fills are suggestions.** Every answer is shown with the text that justified it and can be changed by the assessor.
* **The evaluation questions were written by the developer.** The blind set guards against tuning to the questions, but not against the developer's view of what matters.

More detail is in the [model card](docs/model_card.md) and [docs/safety.md](docs/safety.md).

## Roadmap

* Load the full quarterly FAERS files with deduplication by case version, and add MedDRA hierarchy roll up when a licence is available.
* Add time to signal analysis: cumulative EB05 by quarter, so emergence can be dated.
* Plug in a biomedical encoder such as MedCPT when weights can be hosted locally, and compare with the in domain dual encoder.
* Extend label intelligence to compare versions of the same label over time.
* Add E2B (R3) export of a structured case from case intake.
* Add a reviewer workflow: signal triage states, assignment and comments, recorded in the audit log.

## Licence and acknowledgements

The code is released under the MIT licence. The data remain under their own licences, listed in the [data card](docs/data_card.md); several are for non commercial research use only. This work builds on PubMed 200k RCT (Dernoncourt and Lee), the ADE corpus (Gurulingappa and colleagues), the DDI corpus (Herrero Zazo and colleagues), BioCreative V CDR, the annotated drug labels of Demner Fushman and colleagues and the OnSIDES project, Hetionet (Himmelstein and colleagues) with SIDER, DrugCentral and DrugBank, the MDDC package and FAERS tables (Ding, Markatou and Ball), the COVID 19 FAERS tables of Kim and Yoon, the OMOP and EU ADR reference sets, and the WHO ATC index. FAERS data are published by the US Food and Drug Administration, which does not endorse this work.
