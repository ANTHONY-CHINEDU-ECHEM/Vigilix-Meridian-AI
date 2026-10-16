from vigilix.rag.text import analyse, canonical_drug, canonical_term, numbers, sentences, stem


def test_brand_and_british_names_fold_to_generic():
    assert canonical_drug("Lipitor") == "atorvastatin"
    assert canonical_drug("paracetamol") == "acetaminophen"
    assert canonical_drug("Cipralex") == "escitalopram"


def test_spelling_rules_and_guard_for_angioedema():
    toks = analyse("oedema diarrhoea haemorrhage angioedema lymphoedema")
    assert "edema" in toks and "diarrhea" in toks and "hemorrhage" in toks
    assert "angioedema" in toks and "lymphedema" in toks


def test_lay_terms_and_abbreviations_are_expanded_not_replaced():
    toks = analyse("muscle pain after SJS")
    assert "myalgia" in toks and "muscle" in toks
    assert "sjs" in toks and "johnson" in toks


def test_canonical_terms():
    assert canonical_term("Diarrhoea") == "diarrhea"
    assert canonical_term("low blood sugar") == "hypoglycemia"


def test_numbers_handle_thousands_and_percentages():
    assert numbers("5,248,821 cases, 12.50% and HR 0.85") == ["5.24882e+06", "12.5", "0.85"]


def test_stemmer_is_conservative():
    assert stem("rates") == "rate"
    assert stem("qt") == "qt"
    assert stem("analysis") == "analysis"


def test_sentence_splitter_keeps_abbreviations():
    s = sentences("Risk rose vs. placebo in the trial. A second finding was reported here.")
    assert len(s) == 2
