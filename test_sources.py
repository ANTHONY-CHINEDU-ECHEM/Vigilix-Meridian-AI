from vigilix.data.sources import detokenise, html_to_text


def test_detokenise_pubmed_rct_text():
    assert detokenise("risk ( 95 % CI 1.2-3.4 ) was higher") == "risk (95% CI 1.2-3.4) was higher"


def test_html_to_text_keeps_table_cells():
    out = html_to_text("<p>Common:</p><table><tr><td>nausea</td><td>vomiting</td></tr></table>")
    assert "nausea" in out and "vomiting" in out and "<" not in out
