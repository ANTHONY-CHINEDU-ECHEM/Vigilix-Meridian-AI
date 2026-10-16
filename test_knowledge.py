from conftest import needs_artifacts


@needs_artifacts
def test_dictionary_linking(dictionaries):
    drugs, reactions = dictionaries
    assert drugs.mentions("Lipitor and warfarin with Cipralex") == ["atorvastatin", "warfarin", "escitalopram"]
    assert "rhabdomyolysis" in reactions.mentions("rhabdomyolysis and muscle pain")
    assert "blind" not in reactions.mentions("a double blind trial")


@needs_artifacts
def test_graph_pair_evidence():
    from vigilix.rag.graph import KnowledgeGraph

    g = KnowledgeGraph.load()
    ev = g.pair_evidence("simvastatin", "rhabdomyolysis")
    assert {"labelled_reaction", "faers_signal"} <= set(ev["relations"])
    inter = g.interaction("simvastatin", "clarithromycin")
    assert inter["documented"]


@needs_artifacts
def test_label_mining_finds_listed_terms(dictionaries):
    from vigilix.extraction.labels import extract_terms

    _, reactions = dictionaries
    terms = extract_terms("Common: nausea, headache. No cases of hepatic failure were observed.", reactions)
    by = {t["term"]: t["negated"] for t in terms}
    assert by.get("nausea") is False and by.get("hepatic failure") is True
