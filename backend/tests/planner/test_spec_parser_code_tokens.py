from __future__ import annotations


def test_parse_spec_extracts_code_tokens_from_mixed_text(client):
    # Given: real-world style text (ERP “交易规格”)
    spec_text = "枕套 / PI5 / Q25121102A黄金绒双面印花（棕色毛球） 45X45;1003433256386"
    r = client.post("/api/planner/spec/parse", json={"spec_text": spec_text})
    assert r.status_code == 200, r.text
    data = r.json()
    tokens = data.get("tokens") or []

    # Should extract these stable identifiers even when glued to other text
    assert "Q25121102A" in tokens
    assert "1003433256386" in tokens
    # Optional fallback: 3-char model code as a namespaced token
    assert "MODEL:PI5" in tokens
    # Short alias for convention
    assert "M:PI5" in tokens


def test_parse_spec_extracts_material_code_tokens(client):
    spec_text = "WB01176棉麻布300本白防水,WB02339 1012本白雪尼尔"
    r = client.post("/api/planner/spec/parse", json={"spec_text": spec_text})
    assert r.status_code == 200, r.text
    tokens = r.json().get("tokens") or []
    assert "WB01176" in tokens
    assert "WB02339" in tokens


def test_parse_spec_extracts_phrase_tokens_for_variants(client):
    # Given: common ERP “交易规格” string
    spec_text = "Q25121102D黄金绒背面纯色30X50"
    r = client.post("/api/planner/spec/parse", json={"spec_text": spec_text})
    assert r.status_code == 200, r.text
    tokens = r.json().get("tokens") or []
    # Should emit standalone phrase token so line-variant conditions can match it
    assert "背面纯色" in tokens


def test_parse_spec_extracts_bundle_code_tokens(client):
    spec_text = "组合装BUNDLE:K8F3J2 40X50"
    r = client.post("/api/planner/spec/parse", json={"spec_text": spec_text})
    assert r.status_code == 200, r.text
    tokens = r.json().get("tokens") or []
    assert "B:K8F3J2" in tokens
    assert "BUNDLE:K8F3J2" in tokens

    # New platform-friendly format: B-K8F3J2-A (selector)
    spec_text2 = "组合装 B-K8F3J2-A 40X50"
    r2 = client.post("/api/planner/spec/parse", json={"spec_text": spec_text2})
    assert r2.status_code == 200, r2.text
    tokens2 = r2.json().get("tokens") or []
    assert "B:K8F3J2" in tokens2
    assert "B:K8F3J2:A" in tokens2

