from conftest import needs_artifacts


@needs_artifacts
def test_retrieval_finds_guidance_for_method_question(pipeline):
    q, res = pipeline.retriever.search("What does an EB05 of 2 mean?", k=5)
    assert res and pipeline.retriever.store[res[0].idx]["doc_id"] == "card_mgps_ebgm"


@needs_artifacts
def test_answer_is_cited_and_verified(pipeline):
    r = pipeline.answer("Does dexmedetomidine cause bradycardia?", engine="extractive")
    assert r["answer"] and all(s["citations"] for s in r["answer"])
    assert sum(s["verification"]["status"] == "supported" for s in r["answer"]) >= len(r["answer"]) - 1
    assert r["query"]["drugs"] == ["dexmedetomidine"]


@needs_artifacts
def test_verifier_flags_invented_number(pipeline):
    ev = "Myalgia was reported in 5.2% of patients receiving the drug."
    ok = pipeline.verifier.verify("Myalgia was reported in 5.2% of patients.", [ev])
    bad = pipeline.verifier.verify("Myalgia was reported in 25% of patients.", [ev])
    assert ok["status"] == "supported" and bad["status"] == "unsupported"


@needs_artifacts
def test_guard_paths(pipeline):
    assert pipeline.answer("I want to kill myself tonight")["engine"] == "guard"
    r = pipeline.answer("What dose of warfarin should I give my patient?")
    assert "dosing" in r["notices"]
