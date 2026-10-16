# Data card

All data are public. `scripts/download_data.py` fetches them reproducibly and records byte counts and SHA256 digests in `data/raw/MANIFEST.json`.

| Source | Content used | Scale | Licence | Citation |
| --- | --- | --- | --- | --- |
| PubMed 200k RCT | Randomised trial abstracts with sentence roles, filtered to safety language with a linked drug | 43,080 of 195,654 abstracts, 97,773 passages | CC BY 4.0 | Dernoncourt F, Lee JY. IJCNLP 2017 |
| ADE corpus V2 | Case report sentences with gold drug and adverse effect relations | 2,972 reports, 6,821 relations, 16,695 negative sentences | Research use | Gurulingappa H et al. J Biomed Inform 2012;45:885 |
| DDI corpus 2013 | DrugBank and MEDLINE texts with typed drug interaction annotations | 905 documents, 5,000 positive pairs | CC BY NC 3.0 | Herrero Zazo M et al. J Biomed Inform 2013;46:914 |
| BioCreative V CDR | Abstracts with chemical induced disease relations | 1,500 abstracts, 3,116 relations | Research use | Li J et al. Database 2016 |
| Demner Fushman labels and OnSIDES annotations | US prescribing information sections, UK and EU SmPC section 4.8, US paediatric sections, each with annotated adverse events | 1,219 sections, about 56,000 annotated events | CC BY 4.0 | Demner Fushman D et al. Sci Data 2018; Tanaka Y et al. OnSIDES 2025 |
| Hetionet v1.0 | SIDER 4.1 side effects, DrugCentral pharmacologic classes, PharmacotherapyDB indications, DrugBank targets | 1,552 compounds, 138,944 side effect edges | CC0 integration; SIDER CC BY NC SA 4.0; DrugBank derived CC BY NC 4.0 | Himmelstein DS et al. eLife 2017 |
| FAERS, MDDC package | Drug by preferred term report counts for sedatives (2021 to 2023), beta blockers (2021 to 2023) and statins (2014 to 2020) | 22 drugs, 1,604 terms | MIT package; FAERS US public domain | Ding Y, Markatou M, Ball R. Stat Med 2020; MDDC, JOSS 2025 |
| FAERS, fast track COVID 19 drugs | Contingency tables for 4 products over 5,248,821 deduplicated cases with System Organ Class | 8,320 pairs | GPL 3.0 repository; FAERS US public domain | Kim HJ, Yoon JH, 2023 |
| OMOP and EU ADR reference sets | Expert positive and negative drug outcome controls | 492 pairs, 13 overlapping the FAERS extracts | Apache 2.0 | Ryan PB et al. Drug Saf 2013; Coloma PM et al. Drug Saf 2013 |
| WHO ATC index | Anatomical therapeutic chemical classification | 7,536 codes | WHO terms | WHO Collaborating Centre for Drug Statistics Methodology |
| Authored guidance digests | 77 summaries of regulatory guidance, methods and drug class safety, each with references | 78 passages | MIT, with cited sources | This project |

## Processing notes

* **Spelling and naming.** Canonical drug names follow United States Adopted Names because most abstracts and FAERS product names use them; British approved names and brands fold onto them. Reaction terms are spelling folded so "diarrhoea" and "diarrhea" match.
* **FAERS tables are counts of drug and event pairs**, not unique cases, and the MDDC tables exclude "Off label use" and "Drug ineffective". Each dataset is scored against its own background; they are never pooled.
* **Label coverage.** SIDER in Hetionet has no entries for some common drugs (atorvastatin and warfarin among them). Drugs are treated as label covered only when the references list at least 20 reactions, so expectedness is never asserted from an absent reference.
* **Label substances.** US and EU label brands are mapped to active substances by a curated table (`vigilix/kb/content/label_products.json`); UK SmPC identifiers are numeric, so the substance is detected from the most frequently mentioned drug in the section (137 of 200 resolved).
* **Literature cut off.** PubMed 200k RCT abstracts end in 2017. Newer safety knowledge enters through the guidance digests, which must be checked against current guidance before any use.

## Known biases

* Trial abstracts over represent drugs studied in randomised trials and under represent rare reactions.
* The ADE and CDR corpora were selected by their authors for adverse event content, so case style evidence is denser than in general literature.
* Spontaneous reports reflect reporting behaviour: notoriety, stimulated reporting, duplicates and mass submissions all distort counts. The cluster detector flags one such pattern but cannot remove reporting bias.
