from vigilix.interactions.checker import pk_mechanisms


def test_strong_cyp3a4_inhibitor_with_sensitive_substrate():
    mech = pk_mechanisms("clarithromycin", "simvastatin")
    assert any(m["mechanism"] == "CYP3A4" and m["perpetrator"] == "clarithromycin" and m["strength"] >= 3 for m in mech)


def test_prodrug_activation_and_renal_clearance():
    assert any("activation" in m["effect"] for m in pk_mechanisms("fluoxetine", "codeine"))
    assert any(m["mechanism"] == "Renal clearance" for m in pk_mechanisms("ibuprofen", "lithium"))


def test_no_mechanism_for_unrelated_pair():
    assert pk_mechanisms("amlodipine", "paracetamol") == []
