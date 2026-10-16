from vigilix.causality.assess import naranjo, who_umc


def test_naranjo_categories():
    full = {"previous_reports": "yes", "after_drug": "yes", "improved_on_stop": "yes", "reappeared_on_rechallenge": "yes", "alternative_causes": "no", "objective_evidence": "yes"}
    r = naranjo(full)
    assert r["score"] == 9 and r["category"] == "definite"
    assert naranjo({})["category"] == "doubtful"
    assert naranjo({"after_drug": "yes", "improved_on_stop": "yes", "previous_reports": "yes", "objective_evidence": "yes"})["category"] == "probable"


def test_who_umc_mapping():
    assert who_umc("yes", "no", "yes", "yes", "yes")["category"] == "certain"
    assert who_umc("yes", "no", "yes", "unknown", "unknown")["category"] == "probable"
    assert who_umc("no", "no", "yes", "yes", "yes")["category"] == "unlikely"
    assert who_umc("yes", "yes", "yes", "unknown", "yes")["category"] == "possible"
    assert who_umc("yes", "unknown", "unknown", "unknown", "unknown")["category"] == "conditional"
    assert who_umc("yes", "no", "yes", "yes", "yes", sufficient_information=False)["category"] == "unassessable"
