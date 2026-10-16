# Model card

Vigilix Meridian contains seven learned components. All of them train on CPU from the public data described in the [data card](data_card.md), with the fixed seed 20261016, and all of them are rebuilt by `make index` and `make train`. None of them is a medical device.

## Intended use and users

Research, teaching and portfolio demonstration of evidence grounded pharmacovigilance tooling: helping a reviewer find, read and weigh published and reported evidence about drug safety. The system is not intended for decisions about an individual patient, for regulatory submissions, or as a replacement for a qualified safety physician or pharmacist.

## Components

### 1. Word2vec and SIF vectors

| Item | Value |
| --- | --- |
| Algorithm | Skip gram word2vec (gensim), smooth inverse frequency weighting with first principal component removal |
| Training text | The 130,957 corpus passages after normalisation |
| Vocabulary | 44,821 words |
| Use | Inputs to the dual encoder, and a dense baseline in the retrieval ablation |

### 2. Dual encoder

| Item | Value |
| --- | --- |
| Architecture | Two linear towers over SIF vectors (query and passage), L2 normalised outputs |
| Objective | Symmetric in batch InfoNCE, Adam, analytic gradients in NumPy |
| Training pairs | 130,312 training and 6,924 validation pairs |
| Pair kinds | objective to results (43,076), inverse cloze (40,757), title kg fact (18,379), title drug label (6,513), q label (4,000), q adverse kg fact (3,851), pair case report (3,718), title case report (2,972), q adverse trial abstract (2,696), pair cid abstract (2,562), title cid abstract (1,500), q adverse case report (1,483), q interaction (1,340), title interaction monograph (1,319), q signal (945), q adverse cid abstract (846), q card (459), title signal summary (315), q card pair (254), title interaction (173), title guidance card (78) |
| Validation | MRR 0.780 and recall@1 0.695 at epoch 4, from 0.659 and 0.564 for the untrained SIF vectors |
| Training time | 418 seconds for the whole index build |

### 3. LambdaMART reranker

| Item | Value |
| --- | --- |
| Algorithm | LightGBM LambdaMART, 49 features (retriever scores and ranks, reciprocal rank fusion, entity, title and phrase matches, source type, evidence level, intent and knowledge graph flags) |
| Training data | 4,081 synthetic queries generated from the knowledge base by templates (never from the evaluation questions), 575,216 candidate rows, 52,414 positives |
| Labels | 2 for passages of the generating document, 1 for passages mentioning the same drug and reaction, 0 otherwise |
| Validation | nDCG@5 0.872, nDCG@10 0.893 at iteration 116 on held out queries |
| Top features | rrf (0.422), rr_entity (0.104), drug_match (0.076), src_trial_abstract (0.065), pair_match (0.043), rr_card (0.041), bm25_norm (0.025), reaction_match (0.024) |
| Browser variant | The same rows without dense features, used by the in browser engine |

### 4. Claim verifier

| Item | Value |
| --- | --- |
| Algorithm | Logistic regression over eleven support features, plus hard rules |
| Training data | 35,859 sentences: verbatim and paraphrased corpus sentences as supported; changed numbers, swapped drugs, swapped reactions, flipped negation and wrong citations as unsupported |
| Test | 8,965 held out sentences, AUROC 0.999, accuracy with rules 98.8% |
| Coefficients | token support +8.47, best sentence support +21.39, bigram support +3.09, numbers present +3.22, numbers fraction +1.09, drug consistency +2.91, reaction consistency +4.95, negation agreement +2.74, citation valid +0.00, log length −0.71, best sentence jaccard −2.83 |
| Hard rules | A number absent from the cited evidence, a drug the evidence does not mention or a missing citation makes the sentence unsupported |
| Weakest case | Changed numbers (93.7%), mostly when the new number also appears elsewhere in the passage |

### 5. Adverse event extractor

| Item | Value |
| --- | --- |
| Models | TF IDF logistic regression sentence classifier; CRF span tagger (sklearn crfsuite) with word shape, affix and dictionary features, trained on positive sentences; logistic regression relation classifier |
| Data | ADE corpus V2, split by PubMed identifier: 16,698 training and 4,269 test sentences from 594 records |
| Sentence classification | F1 0.709, AUROC 0.919 |
| Drug spans | F1 0.808 exact, 0.831 overlap (dictionary baseline 0.526) |
| Effect spans | F1 0.698 exact, 0.836 overlap (dictionary baseline 0.366) |
| Relations end to end | F1 0.553 (dictionary baseline 0.175) |
| Note | Given gold entities, relation classification reaches F1 0.998, the same as a majority baseline, because almost every candidate pair in a positive ADE sentence is a true relation. Span detection is the real difficulty. |

### 6. Gamma mixture prior (MGPS)

| Item | Value |
| --- | --- |
| Model | Two component gamma mixture prior for the observed to expected ratio, fitted by maximum likelihood on the negative binomial marginal, one per FAERS extract |
| Output | EBGM (posterior geometric mean) and EB05 (5th percentile) for every pair |
| Check | All 13 overlapping OMOP and EU ADR controls agree with the EB05 rule |

### 7. Optional language model writer

| Item | Value |
| --- | --- |
| Model | Any Ollama chat model, `llama3.1:8b` by default; not trained or fine tuned here |
| Controls | Evidence only system prompt, one citation per sentence, no doses, sentence verification of every output, extractive fallback |
| Evaluation | Faithfulness numbers in the README use the extractive writer so they do not depend on a particular model; with a model enabled, every sentence still passes through the verifier and unsupported sentences are marked in the interface |

## Known failure modes

* Questions about drugs that are rare in the corpus fall back to label sections and graph facts; answers are then short and moderate in confidence.
* Lay descriptions without a lexicon entry ("my legs feel heavy") may not link to a reaction, which removes the entity routed candidates.
* British approved names that are not in the lexicon are not folded.
* Disproportionality for terms with very few reports is unstable; EB05 shrinks it, ROR and PRR do not.
* The interaction level is heuristic and the PK table is curated, not exhaustive.
* Literature ends in 2017.

## Ethical considerations

Every identifier pattern in the guard is redacted before text is logged, embedded or sent to a model, and the audit table keeps only the redacted text and a hash of the original. Crisis language returns support information instead of retrieval. The system never states a dose for an individual. Output wording keeps reporting association separate from causation.
