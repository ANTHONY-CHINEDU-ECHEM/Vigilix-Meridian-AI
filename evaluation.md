# Evaluation protocol and results

Every number here is produced by `make evaluate_blind` and stored in `reports/`. The figures are regenerated from the same files.

## Principles

1. **Questions before the system.** The 60 development and 30 blind questions were written before the retriever existed, together with their relevance rules.
2. **A frozen blind set.** The SHA256 of `vigilix/eval/questions/blind.json` was recorded in `reports/blind_hash.txt` (af9e7dad03cd288d…, Fri Oct 16 02:58:33 UTC 2026) before the first scoring run. The evaluation script recomputes the hash and reports whether it matches (this run: matches). The blind questions were never used to change the lexicon, the features or the reranker.
3. **No training on evaluation material.** The reranker and the dual encoder are trained on queries and pairs generated from the knowledge base by templates; the verifier on perturbed corpus sentences; the extractor on a split by PubMed identifier.
4. **Writer independent answer metrics.** Answer metrics use the extractive writer so they measure retrieval and verification rather than a particular language model.
5. **Baselines everywhere.** Each retriever is compared with its parts, the extractor with a dictionary baseline, the signal measures with random and with raw report counts.

## Retrieval

Relevance rules per question: a passage is grade 2 when its document identifier starts with one of the listed documents; grade 1 when it mentions a listed drug (in its drug list or title) and any listed reaction phrase, optionally restricted to listed source types, or contains every listed phrase. Recall@5 counts a question as answered when any of the top five passages is relevant; strict recall@5 needs a grade 2 passage; MRR@10 and nDCG@10 use the grades.

### Blind set

| Mode | Recall@5 | Strict recall@5 | MRR@10 | nDCG@10 | ms per query |
| --- | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.800 | 0.700 | 0.686 | 0.649 | 4.5 |
| sif | 0.400 | 0.300 | 0.348 | 0.304 | 5.5 |
| dense | 0.500 | 0.300 | 0.400 | 0.355 | 7.5 |
| hybrid | 0.600 | 0.467 | 0.570 | 0.529 | 7.4 |
| entity | 0.667 | 0.567 | 0.638 | 0.612 | 9.1 |
| full | 0.967 | 0.900 | 0.948 | 0.911 | 60.8 |

### Development set

| Mode | Recall@5 | Strict recall@5 | MRR@10 | nDCG@10 | ms per query |
| --- | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.933 | 0.767 | 0.911 | 0.836 | 3.0 |
| sif | 0.733 | 0.483 | 0.651 | 0.559 | 5.8 |
| dense | 0.783 | 0.617 | 0.672 | 0.615 | 6.2 |
| hybrid | 0.900 | 0.733 | 0.810 | 0.734 | 6.7 |
| entity | 0.900 | 0.767 | 0.858 | 0.804 | 8.4 |
| full | 1.000 | 0.967 | 0.951 | 0.940 | 69.7 |

### Per question results, blind set, full pipeline

| Id | Question | Recall@5 | Strict | MRR | nDCG@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| b01 | My patient on Lipitor has muscle aches. Is that a known reaction? | 1.00 | 1.00 | 1.00 | 1.00 |
| b02 | Is a lower 95% confidence limit of the ROR above one enough to call a signal? | 1.00 | 1.00 | 1.00 | 1.00 |
| b03 | Fournier's gangrene with SGLT2 drugs | 1.00 | 1.00 | 1.00 | 1.00 |
| b04 | Can Cipralex prolong the QT interval? | 1.00 | 1.00 | 1.00 | 0.92 |
| b05 | Blood thinner and stomach bleed with ibuprofen | 1.00 | 1.00 | 1.00 | 1.00 |
| b06 | What does Uppsala use instead of PRR? | 1.00 | 1.00 | 0.33 | 0.50 |
| b07 | Which beta blocker signals in FAERS are not on the label? | 1.00 | 1.00 | 1.00 | 0.92 |
| b08 | Clonazepam respiratory depression reports | 1.00 | 1.00 | 1.00 | 0.98 |
| b09 | Allopurinol and severe skin reactions in Han Chinese patients | 1.00 | 1.00 | 1.00 | 0.96 |
| b10 | Does ticagrelor cause breathlessness? | 1.00 | 1.00 | 1.00 | 0.74 |
| b11 | Fingolimod first dose bradycardia | 1.00 | 0.00 | 1.00 | 0.73 |
| b12 | Suicidal thoughts with isotretinoin | 1.00 | 1.00 | 1.00 | 1.00 |
| b13 | Molnupiravir in pregnancy | 1.00 | 1.00 | 1.00 | 1.00 |
| b14 | What happens if dexmedetomidine is used in ICU patients under 65? | 1.00 | 1.00 | 1.00 | 1.00 |
| b15 | Why are there so many duplicate FAERS reports? | 1.00 | 1.00 | 1.00 | 1.00 |
| b16 | Codeine in children after tonsillectomy | 1.00 | 1.00 | 1.00 | 0.81 |
| b17 | Linezolid with an antidepressant | 1.00 | 0.00 | 1.00 | 0.64 |
| b18 | How long after starting carbamazepine does DRESS appear? | 1.00 | 1.00 | 1.00 | 1.00 |
| b19 | Tofacitinib serious infections | 1.00 | 1.00 | 1.00 | 1.00 |
| b20 | Gentamicin deafness with a mitochondrial variant | 1.00 | 1.00 | 1.00 | 1.00 |
| b21 | Is dysgeusia expected with Paxlovid? | 1.00 | 1.00 | 1.00 | 1.00 |
| b22 | Metoclopramide extrapyramidal or neuroleptic syndrome | 1.00 | 1.00 | 1.00 | 1.00 |
| b23 | Hyperkalaemia with spironolactone and an ACE inhibitor | 1.00 | 1.00 | 1.00 | 1.00 |
| b24 | What are the frequency categories in section 4.8 of an SmPC? | 1.00 | 1.00 | 1.00 | 0.92 |
| b25 | Self controlled case series for vaccine safety | 1.00 | 1.00 | 1.00 | 0.92 |
| b26 | Is nausea common with semaglutide? | 1.00 | 1.00 | 1.00 | 1.00 |
| b27 | Phenytoin and erythema multiforme after radiotherapy | 1.00 | 1.00 | 1.00 | 1.00 |
| b28 | Gabapentin and opioids breathing problems | 1.00 | 1.00 | 1.00 | 1.00 |
| b29 | Headache and flushing adverse events of sildenafil in trials | 1.00 | 1.00 | 1.00 | 1.00 |
| b30 | Should a fluoroquinolone be used for an uncomplicated urinary infection? | 0.00 | 0.00 | 0.11 | 0.30 |

### Per question results, development set, full pipeline

| Id | Question | Recall@5 | Strict | MRR | nDCG@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| d01 | How is the proportional reporting ratio calculated and what are the Evans criteria? | 1.00 | 1.00 | 1.00 | 1.00 |
| d02 | What does an EB05 of 2 mean in FDA data mining? | 1.00 | 1.00 | 1.00 | 1.00 |
| d03 | What is the information component used by the Uppsala Monitoring Centre? | 1.00 | 1.00 | 1.00 | 1.00 |
| d04 | Why is disproportionality not proof that a drug causes a reaction? | 1.00 | 1.00 | 1.00 | 1.00 |
| d05 | What is masking in spontaneous report databases? | 1.00 | 1.00 | 0.50 | 0.63 |
| d06 | Score a case with the Naranjo algorithm: what totals mean probable or definite? | 1.00 | 1.00 | 1.00 | 1.00 |
| d07 | What are the ICH E2A seriousness criteria? | 1.00 | 1.00 | 1.00 | 1.00 |
| d08 | What counts as a valid individual case safety report? | 1.00 | 1.00 | 1.00 | 1.00 |
| d09 | What are the steps of signal management under GVP Module IX? | 1.00 | 1.00 | 1.00 | 1.00 |
| d10 | Hy's law criteria for drug induced liver injury | 1.00 | 1.00 | 1.00 | 1.00 |
| d11 | Which drugs cause torsade de pointes and what increases the risk? | 1.00 | 1.00 | 1.00 | 1.00 |
| d12 | Can tramadol and sertraline together cause serotonin syndrome? | 1.00 | 1.00 | 1.00 | 1.00 |
| d13 | Which drugs most often cause Stevens Johnson syndrome and what is the HLA B 15:02 link? | 1.00 | 1.00 | 1.00 | 1.00 |
| d14 | Does simvastatin with clarithromycin increase the risk of rhabdomyolysis? | 1.00 | 1.00 | 1.00 | 0.99 |
| d15 | Is myalgia a disproportionate FAERS signal for atorvastatin? | 1.00 | 1.00 | 1.00 | 1.00 |
| d16 | Which FAERS signals stand out for nirmatrelvir ritonavir? | 1.00 | 1.00 | 1.00 | 1.00 |
| d17 | Remdesivir and raised liver enzymes | 1.00 | 1.00 | 1.00 | 1.00 |
| d18 | Does dexmedetomidine cause bradycardia? | 1.00 | 1.00 | 1.00 | 0.92 |
| d19 | Risks of combining an opioid with a benzodiazepine | 1.00 | 1.00 | 1.00 | 1.00 |
| d20 | What bleeding risks are listed for apixaban? | 1.00 | 1.00 | 1.00 | 1.00 |
| d21 | Boxed warning for Xarelto | 1.00 | 1.00 | 1.00 | 1.00 |
| d22 | Pradaxa adverse reactions in clinical trials | 1.00 | 1.00 | 1.00 | 0.98 |
| d23 | Ketoacidosis with dapagliflozin | 1.00 | 1.00 | 1.00 | 0.89 |
| d24 | What are the warnings for canagliflozin about amputation? | 1.00 | 1.00 | 1.00 | 1.00 |
| d25 | Does liraglutide cause pancreatitis? | 1.00 | 1.00 | 1.00 | 0.91 |
| d26 | Tendon rupture with ciprofloxacin | 1.00 | 1.00 | 1.00 | 1.00 |
| d27 | Why is warfarin plus fluconazole dangerous? | 1.00 | 1.00 | 1.00 | 0.81 |
| d28 | Triple whammy: NSAID with ACE inhibitor and diuretic and kidney injury | 1.00 | 1.00 | 1.00 | 1.00 |
| d29 | Which drugs cause hyponatraemia in older people? | 1.00 | 1.00 | 1.00 | 0.91 |
| d30 | Clozapine and constipation or ileus | 1.00 | 1.00 | 1.00 | 1.00 |
| d31 | Valproate exposure in pregnancy | 1.00 | 1.00 | 1.00 | 0.94 |
| d32 | Immune related colitis with ipilimumab | 1.00 | 1.00 | 1.00 | 1.00 |
| d33 | Pneumonitis with pembrolizumab | 1.00 | 1.00 | 1.00 | 0.94 |
| d34 | Weekly methotrexate dosing errors | 1.00 | 1.00 | 1.00 | 1.00 |
| d35 | What raises lithium levels and causes toxicity? | 1.00 | 1.00 | 1.00 | 1.00 |
| d36 | Digoxin toxicity with amiodarone | 1.00 | 1.00 | 1.00 | 1.00 |
| d37 | Vancomycin and piperacillin tazobactam acute kidney injury | 1.00 | 1.00 | 1.00 | 0.89 |
| d38 | Amiodarone lung toxicity | 1.00 | 0.00 | 1.00 | 0.64 |
| d39 | Which enzymes does rifampicin induce and what interactions follow? | 1.00 | 1.00 | 1.00 | 0.87 |
| d40 | Paxlovid drug interactions | 1.00 | 1.00 | 1.00 | 1.00 |
| d41 | Infusion reactions with bebtelovimab | 1.00 | 1.00 | 1.00 | 1.00 |
| d42 | Does Seroquel cause weight gain? | 1.00 | 1.00 | 1.00 | 1.00 |
| d43 | Persistent sexual dysfunction after stopping an SSRI | 1.00 | 1.00 | 1.00 | 1.00 |
| d44 | Long term omeprazole and low magnesium | 1.00 | 1.00 | 0.25 | 0.44 |
| d45 | Hypertension and proteinuria with pazopanib | 1.00 | 1.00 | 1.00 | 0.91 |
| d46 | Arterial occlusion with ponatinib | 1.00 | 1.00 | 0.33 | 0.71 |
| d47 | Lamotrigine rash and valproate co administration | 1.00 | 1.00 | 1.00 | 1.00 |
| d48 | Anticholinergic side effects of diphenhydramine in the elderly | 1.00 | 1.00 | 1.00 | 1.00 |
| d49 | Complex sleep behaviours with zolpidem | 1.00 | 1.00 | 1.00 | 0.88 |
| d50 | Bradycardia and bronchospasm with timolol eye drops | 1.00 | 1.00 | 1.00 | 0.92 |
| d51 | Hypoglycaemia with glibenclamide in renal impairment | 1.00 | 1.00 | 1.00 | 0.90 |
| d52 | Case reports of azithromycin ototoxicity | 1.00 | 1.00 | 1.00 | 1.00 |
| d53 | Reports of cisplatin induced nephrotoxicity | 1.00 | 1.00 | 1.00 | 0.99 |
| d54 | Isoniazid hepatitis | 1.00 | 0.00 | 1.00 | 0.69 |
| d55 | Haloperidol and neuroleptic malignant syndrome | 1.00 | 1.00 | 1.00 | 1.00 |
| d56 | Adverse events of celecoxib versus naproxen in randomised trials | 1.00 | 1.00 | 0.50 | 0.83 |
| d57 | Tolerability of topiramate for migraine prevention in trials | 1.00 | 1.00 | 1.00 | 1.00 |
| d58 | What adverse events led to discontinuation with varenicline in smoking cessation trials? | 1.00 | 1.00 | 0.50 | 0.79 |
| d59 | Does mirtazapine cause agranulocytosis? | 1.00 | 1.00 | 1.00 | 1.00 |
| d60 | Why should statin FAERS signals be compared with the label? | 1.00 | 1.00 | 1.00 | 1.00 |

## Grounded answers

The pipeline answered all 90 questions with the extractive writer. Each answer sentence was verified against the evidence it cites.

| Metric | Value |
| --- | --- |
| Supported sentences | 98.0% |
| Partially supported | 0.0% |
| Unsupported | 2.0% |
| Answers with an unverifiable number | 0 |
| Every sentence cited | 100.0% |
| Relevant evidence cited | 96.7% |
| Guidance or label cited | 83.3% |
| Graph evidence used | 53.3% |
| Confidence high, moderate, low | 83, 6, 1 |
| Median latency | 26.3 ms |

Safety probes (each must pass on every run):

| Probe | Passed | Handled by |
| --- | --- | --- |
| crisis | yes | guard |
| out of scope | yes | guard |
| identifiers | yes | extractive |
| dosing | yes | extractive |
| injection | yes | extractive |

## Signal detection

**Reference.** A drug and preferred term pair is positive when the term (after spelling folding and synonym linking) appears among the reactions listed for the drug in SIDER or in the annotated labels. Only drugs with at least 20 listed reactions are included, so a missing reference is never read as a negative. This reference is noisy in both directions, which is the realistic condition.

**Pairs.** 7,280 pairs with at least three reports across 21 drugs (acebutolol, atenolol, bisoprolol, carvedilol, clonazepam, dexmedetomidine, diazepam, diphenhydramine, doxepin, fluvastatin, lorazepam, metoprolol, midazolam, mirtazapine, nadolol, nitrazepam, propranolol, rosuvastatin, simvastatin, temazepam, timolol), 21.9% labelled. Atorvastatin and the four COVID 19 products are excluded because the reference sources do not cover them, and administrative and product quality terms (off label use, medication errors, device issues and similar) are removed because labels never list them.

| Measure | AUROC | Average precision |
| --- | ---: | ---: |
| Random | 0.500 | 0.219 |
| PRR | 0.574 | 0.252 |
| ROR lower 95% | 0.592 | 0.262 |
| IC025 | 0.596 | 0.266 |
| EB05 | 0.593 | 0.264 |
| Report count | 0.652 | 0.338 |

| Rule | Flagged | Precision | Recall |
| --- | ---: | ---: | ---: |
| Evans (PRR, chi square, n) | 1,790 | 0.258 | 0.289 |
| ROR lower limit above 1 | 2,431 | 0.275 | 0.419 |
| IC025 above 0 | 2,306 | 0.276 | 0.398 |
| EB05 at least 2 | 1,416 | 0.266 | 0.236 |

### Expert reference sets

| Set | Drug | Outcome | Truth | Matched term | Cases | EB05 | Flagged | Agrees |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| OMOP | temazepam | Acute Renal Failure | negative control | Acute kidney injury | 6 | 0.06 | no | yes |
| OMOP | temazepam | Acute myocardial infarction | negative control | Acute myocardial infarction | 0 | 0.0 | no | yes |
| OMOP | temazepam | Upper gastrointestinal bleeding | negative control | Gastrointestinal haemorrhage | 10 | 0.69 | no | yes |
| EU ADR | fluvastatin | Aplastic Anemia | negative control | none | 0 | n/a | no | yes |
| EU ADR | timolol | Aplastic Anemia | negative control | Pancytopenia | 0 | 0.0 | no | yes |
| EU ADR | simvastatin | Upper gastrointestinal bleeding | negative control | none | 0 | n/a | no | yes |
| EU ADR | mirtazapine | Anaphylaxis | negative control | Anaphylactic reaction | 2 | 0.02 | no | yes |
| EU ADR | atenolol | Stevens Johnson syndrome | negative control | Toxic epidermal necrolysis | 0 | 0.0 | no | yes |
| EU ADR | atorvastatin | Leukopenia | negative control | none | 0 | n/a | no | yes |
| EU ADR | timolol | Rhabdomyolysis | negative control | none | 0 | n/a | no | yes |
| EU ADR | atorvastatin | Rhabdomyolysis | positive control | Rhabdomyolysis | 590 | 24.03 | yes | yes |
| EU ADR | rosuvastatin | Rhabdomyolysis | positive control | Rhabdomyolysis | 581 | 18.33 | yes | yes |
| EU ADR | simvastatin | Rhabdomyolysis | positive control | Rhabdomyolysis | 170 | 7.52 | yes | yes |

### Strongest unlabelled signals

These are the pairs a reviewer would look at first. Many are explained by confounding by indication, by reports from a single source or by investigational terms, which is exactly why the interface shows label status, intervals and cluster flags beside the score.

| Drug | Preferred term | Cases | EB05 | ROR | System Organ Class |
| --- | --- | ---: | ---: | ---: | --- |
| nadolol | Macular degeneration | 858 | 107.44 | 125.91 | Eye disorders |
| acebutolol | Creatinine renal clearance decreased | 3,641 | 72.06 | 83.61 | Investigations |
| nadolol | Paraesthesia oral | 296 | 68.55 | 79.4 | Gastrointestinal disorders |
| temazepam | Temperature regulation disorder | 349 | 67.44 | 78.33 | General disorders and administration site conditions |
| nadolol | Chronic sinusitis | 299 | 65.54 | 75.81 | Infections and infestations |
| acebutolol | Blood calcium decreased | 3,641 | 64.65 | 74.51 | Investigations |
| fluvastatin | Pancreatitis necrotising | 16 | 56.34 | 130.54 | Gastrointestinal disorders |
| nadolol | Procedural pain | 285 | 54.72 | 63.17 | Injury, poisoning and procedural complications |
| acebutolol | Depressed level of consciousness | 3,636 | 53.24 | 60.73 | Nervous system disorders |
| midazolam | Multiple drug resistance | 191 | 47.4 | 56.68 | General disorders and administration site conditions |
| nitrazepam | Multiple drug resistance | 35 | 46.03 | 77.58 | General disorders and administration site conditions |
| fluvastatin | Presyncope | 166 | 42.18 | 50.07 | Nervous system disorders |

## Adverse event extraction

See the [model card](model_card.md). The split is by PubMed identifier so no case report contributes sentences to both training and test.

## Label mining

| Group | Sections | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| EU | 4.8 Undesirable effects | 200 | 0.899 | 0.638 | 0.746 |
| UK | 4.8 Undesirable effects | 199 | 0.617 | 0.748 | 0.676 |
| US paediatric | Use in specific populations (paediatric) | 147 | 0.605 | 0.729 | 0.662 |
| US | Adverse reactions | 99 | 0.851 | 0.745 | 0.795 |
| US | Boxed warning | 41 | 0.530 | 0.486 | 0.507 |
| US | Warnings and precautions | 96 | 0.525 | 0.572 | 0.547 |
| all | 782 | 0.741 | 0.681 | 0.710 |

Boxed warnings and warnings sections score lowest because they describe reactions in long clinical sentences ("serious, sometimes fatal, hepatotoxicity has occurred") that the annotators normalised to terms that do not appear verbatim.

## Reproducing

```
make all
make evaluate_blind
```

Results are deterministic for a given machine; small differences in the last digit can occur across BLAS builds.
