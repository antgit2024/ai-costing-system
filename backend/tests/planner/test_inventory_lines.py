from decimal import Decimal


def test_inventory_lines_keeps_real_lines_even_without_material_code(db_session):
    # Import internal helper directly (unit test for edge case: missing material_code)
    from src.planner.services.bom_generation_service import _build_inventory_lines

    final_lines = [
        {
            "line_index": 1,
            "material_kind": "real",
            "material_ref_id": "MAT-1",
            "material_code": "",  # missing code (data issue)
            "material_name": "无编码真实物料",
            "unit_of_measure": "pcs",
            "computed_quantity": Decimal("2"),
            "loss_rate": Decimal("0"),
        }
    ]
    inv = _build_inventory_lines(db_session, final_lines)
    assert inv["inventory_line_count"] == 1
    assert inv["inventory_lines"][0]["material_name"] == "无编码真实物料"
    assert inv["inventory_lines"][0]["quantity"] == Decimal("2")


