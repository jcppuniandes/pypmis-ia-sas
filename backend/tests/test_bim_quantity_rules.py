from app.services.bim_quantity_rules import evaluate_quantity_rule, summarize_quantity_rules


def _line(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ifc_class": "IfcWallStandardCase",
        "category": "Muro",
        "quantity": 12.5,
        "unit": "m2",
        "measurement_rule": "NetSideArea",
        "validation_notes": "",
        "raw_data": {"ifc_entity": "IFCWALLSTANDARDCASE"},
    }
    payload.update(overrides)
    return payload


def test_marks_published_ifc_wall_area_quantities_as_authoritative() -> None:
    result = evaluate_quantity_rule(_line())

    assert result["status"] == "valid"
    assert result["confidence"] == "Alta"
    assert result["source"] == "IFC Quantity Set publicado"
    assert "m2" in result["expected_units"]
    assert "IfcWallStandardCase" in result["explanation"]
    assert "area" in result["explanation"].lower()


def test_accepts_wall_length_when_the_budget_measurement_is_linear() -> None:
    result = evaluate_quantity_rule(
        _line(quantity=12, unit="m", measurement_rule="NetLength")
    )

    assert result["status"] == "valid"
    assert result["expected_units"] == ["m2", "m3", "m"]
    assert result["preferred_unit"] == "m2"


def test_accepts_inventory_count_for_naturally_countable_ifc_classes() -> None:
    result = evaluate_quantity_rule(
        _line(
            ifc_class="IfcDoor",
            category="Puerta",
            quantity=1,
            unit="ea",
            measurement_rule="ElementCount",
            validation_notes="No published IFC quantity found",
        )
    )

    assert result["status"] == "valid"
    assert result["confidence"] == "Media"
    assert result["source"] == "Conteo fallback"
    assert result["preferred_unit"] == "ea"


def test_blocks_dimensional_ifc_classes_when_only_element_count_is_available() -> None:
    result = evaluate_quantity_rule(
        _line(
            ifc_class="IfcSlab",
            category="Losa",
            quantity=1,
            unit="ea",
            measurement_rule="ElementCount",
            validation_notes="No published IFC quantity found",
        )
    )

    assert result["status"] == "blocked"
    assert result["source"] == "Conteo fallback"
    assert result["preferred_measure"] == "area"
    assert result["preferred_unit"] == "m2"
    assert "medicion dimensional" in " ".join(result["findings"]).lower()


def test_accepts_approved_real_geometry_for_columns() -> None:
    result = evaluate_quantity_rule(
        _line(
            ifc_class="IfcColumn",
            category="Columna",
            quantity=1,
            unit="ea",
            measurement_rule="ElementCount",
            raw_data={
                "controlled_measurement": {
                    "measurement_rule": "GeometryMeshVolume",
                    "quantity": 0.27,
                    "source": "IFC geometry inspection",
                    "status": "approved",
                    "unit": "m3",
                }
            },
        )
    )

    assert result["status"] == "valid"
    assert result["source"] == "Calculo geometrico desde IFC"
    assert result["preferred_unit"] == "m3"


def test_blocks_quantity_lines_with_wrong_units_for_the_ifc_class() -> None:
    result = evaluate_quantity_rule(
        _line(
            ifc_class="IfcPipeSegment",
            category="Tuberia",
            quantity=20,
            unit="m3",
            measurement_rule="NetLength",
        )
    )

    assert result["status"] == "blocked"
    assert result["confidence"] == "Media"
    assert "m" in result["expected_units"]
    assert "Unidad" in " ".join(result["findings"])


def test_summarizes_quantity_rule_quality() -> None:
    summary = summarize_quantity_rules(
        [
            _line(),
            _line(ifc_class="IfcSlab", unit="ea", measurement_rule="ElementCount", validation_notes="No published IFC quantity found"),
            _line(ifc_class="IfcPipeSegment", unit="m3", measurement_rule="NetLength"),
        ]
    )

    assert summary == {
        "authoritative": 1,
        "blocked": 2,
        "review": 0,
        "total": 3,
        "valid": 1,
    }
