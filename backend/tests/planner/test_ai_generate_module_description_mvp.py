from __future__ import annotations


API_PREFIX = "/api/planner"


def test_ai_generate_process_module_description_accepts_structure(client):
    resp = client.post(
        f"{API_PREFIX}/ai/process-modules/describe",
        json={
            "module_name": "卷材UV打印",
            "category": "打印",
            "structure": {"mode": "global", "standard_code": None, "slots": []},
            "materials": [{"material_name": "UV墨水", "calculation_method": "area"}],
            "steps": [{"process_name": "UV打印", "measure_type": "area"}],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("description"), str) and data["description"].strip()
    assert data.get("provider") in {"llm", "fallback"}


