import pytest
from conftest import needs_artifacts


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from vigilix.api.main import app

    return TestClient(app)


@needs_artifacts
def test_health_and_overview(client):
    assert client.get("/api/health").json()["status"] == "ok"
    o = client.get("/api/overview").json()
    assert o["kb"]["passages"] > 100000


@needs_artifacts
def test_ask_and_search(client):
    r = client.post("/api/ask", json={"question": "Tendon rupture with ciprofloxacin"}).json()
    assert r["evidence"] and r["answer"]
    s = client.post("/api/search", json={"query": "warfarin fluconazole", "mode": "bm25", "k": 3}).json()
    assert len(s["results"]) == 3


@needs_artifacts
def test_signals_compute_labels_interactions_case(client):
    s = client.get("/api/signals", params={"dataset": "statins", "drug": "simvastatin", "only_signals": True}).json()
    assert s["total"] > 0 and all(r["eb_signal"] for r in s["rows"])
    c = client.post("/api/signals/compute", json={"a": 20, "b": 980, "c": 400, "d": 200000}).json()
    assert c["evans"] and c["eb05"] > 2
    labs = client.get("/api/labels", params={"region": "EU"}).json()
    assert labs and client.get(f"/api/labels/{labs[0]['doc_id']}").json()["text"]
    i = client.post("/api/interactions", json={"drugs": ["simvastatin", "clarithromycin"]}).json()
    assert i["pairs"][0]["level"] == "major"
    k = client.post("/api/case/intake", json={"narrative": "A 60 year old man developed rhabdomyolysis two weeks after starting simvastatin; it resolved after the drug was stopped."}).json()
    assert "simvastatin" in k["suspect_drugs"] and "rhabdomyolysis" in k["events"]


@needs_artifacts
def test_audit_is_append_only(client):
    import sqlite3

    from vigilix.config import SETTINGS

    client.post("/api/ask", json={"question": "Mr John Smith had a rash on lamotrigine"})
    entries = client.get("/api/audit").json()["entries"]
    assert entries and "John Smith" not in (entries[0]["redacted_query"] or "")
    with sqlite3.connect(SETTINGS.audit_db) as con, pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM audit")
