"""Database-free granular Quality/Progress conservation boundary tests."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.quality.consumer_sources import _progress_quantity_coverage


def pin(identity=10, version=2, digest="a"):
    return {
        "source_entity_type": "PRODUCTION",
        "source_entity_id": identity,
        "source_version": version,
        "source_hash": digest * 64,
    }


def adoption(source, measurement_id=2, quantity="1", **changes):
    return SimpleNamespace(
        **{key: source[key] for key in ("source_entity_id", "source_version", "source_hash")},
        linked_entity_id=measurement_id,
        quantity=Decimal(quantity),
        uom=changes.pop("uom", "EA"),
        **changes,
    )


def acceptance(source, quantity="1"):
    return SimpleNamespace(
        source_snapshot={
            "facts": {
                "quantity": quantity,
                "uom": "EA",
                "subject_reference": {
                    "source_type": "FIELD_PRODUCTION",
                    "source_id": source["source_entity_id"],
                    "source_version": source["source_version"],
                    "source_hash": source["source_hash"],
                },
            }
        }
    )


def measurement(identity, numerator, *, sources=(), predecessor=None, input_mode="CUMULATIVE", input_quantity=None):
    return SimpleNamespace(
        id=identity,
        numerator=Decimal(numerator),
        subject_key="SCOPE:7:INSTALL",
        scope_item_id=7,
        unit="EA",
        supersedes_id=predecessor,
        source_snapshot={"field_operations": list(sources)},
        input_json={"input_mode": input_mode, "numerator": input_quantity or numerator},
        content_hash="d" * 64,
    )


class Owner:
    tenant_id = 3

    def __init__(self, reservations, *records):
        self.records = {row.id: row for row in records}
        self.statements = []

        def scalars(statement):
            self.statements.append(statement)
            return reservations

        self.db = SimpleNamespace(scalars=scalars)

    @staticmethod
    def _error(status, code):
        raise HTTPException(status, detail={"code": code})

    def _get(self, model, workspace, identity):
        assert model is ProgressMeasurement and workspace == 5
        return self.records[identity]


def test_quality_covers_new_native_reservation_not_preexisting_manual_cumulative_quantity():
    source = pin()
    previous = measurement(1, ".6")
    current = measurement(2, "1.6", sources=[source], predecessor=1)
    owner = Owner([adoption(source)], previous)
    before = deepcopy(vars(current))
    assert _progress_quantity_coverage(owner, 5, current, [acceptance(source)]) is None
    assert vars(current) == before
    sql = str(owner.statements[0])
    for field in ("tenant_id", "project_workspace_id", "consumer", "source_entity_type", "linked_entity_id"):
        assert field in sql


def test_period_delta_keeps_prior_period_native_progress_without_reaccepting_it():
    source = pin()
    previous = measurement(1, ".6")
    current = measurement(2, "1.6", sources=[source], input_mode="PERIOD_DELTA", input_quantity="1")
    current.source_snapshot["previous_measurement"] = {"id": 1, "content_hash": previous.content_hash}
    assert _progress_quantity_coverage(Owner([adoption(source)], previous), 5, current, [acceptance(source)]) is None


def test_repeated_partial_adoptions_of_same_exact_pin_are_all_covered_once():
    source = pin()
    previous = measurement(1, "1", sources=[source])
    current = measurement(2, "2", sources=[source, source], predecessor=1)
    owner = Owner([adoption(source, 1), adoption(source, 2)], previous)
    with pytest.raises(HTTPException, match="") as failure:
        _progress_quantity_coverage(owner, 5, current, [acceptance(source, "1")])
    assert failure.value.detail["code"] == "PROGRESS_QUALITY_GRANULAR_COVERAGE_INCOMPLETE"
    _progress_quantity_coverage(owner, 5, current, [acceptance(source, "2")])


@pytest.mark.parametrize(
    "variant", ["different_source", "version", "hash", "missing_reservation", "surplus_other_source"]
)
def test_exact_source_pins_and_per_source_quantities_cannot_be_borrowed(variant):
    first, second = pin(), pin(11, digest="b")
    current = measurement(2, "2", sources=[first, second], predecessor=1)
    previous = measurement(1, "1", sources=[first])
    reservations = [adoption(first, 1), adoption(second, 2)]
    acceptances = [acceptance(first, "1"), acceptance(second, "1")]
    if variant == "different_source":
        acceptances[1] = acceptance(pin(12, digest="b"))
    elif variant == "version":
        acceptances[1] = acceptance(pin(11, version=3, digest="b"))
    elif variant == "hash":
        acceptances[1] = acceptance(pin(11, digest="c"))
    elif variant == "missing_reservation":
        reservations = reservations[:1]
    else:
        acceptances = [acceptance(first, "2"), acceptance(second, ".1")]
    with pytest.raises(HTTPException):
        _progress_quantity_coverage(Owner(reservations, previous), 5, current, acceptances)


def test_multiple_itps_for_one_indivisible_source_do_not_double_count_acceptance():
    source = pin()
    current = measurement(2, "2", sources=[source], input_mode="PERIOD_DELTA")
    with pytest.raises(HTTPException):
        _progress_quantity_coverage(
            Owner([adoption(source, quantity="2")]), 5, current, [acceptance(source), acceptance(source)]
        )


@pytest.mark.parametrize("change", ["cumulative_input", "stored_numerator", "delta_input", "uom", "cycle"])
def test_native_reservation_amount_cannot_be_inflated_or_relabelled(change):
    source = pin()
    previous = measurement(1, ".6")
    current = measurement(2, "1.6", sources=[source], predecessor=1)
    reservation = adoption(source)
    if change == "cumulative_input":
        current.input_json["numerator"] = "2.6"
    elif change == "stored_numerator":
        current.numerator = Decimal("2.6")
    elif change == "delta_input":
        current.input_json = {"input_mode": "PERIOD_DELTA", "numerator": "1.6"}
    elif change == "uom":
        reservation.uom = "m3"
    else:
        previous.supersedes_id = 2
    with pytest.raises(HTTPException):
        _progress_quantity_coverage(Owner([reservation], previous, current), 5, current, [acceptance(source, "10")])


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "0", "-1"])
def test_non_positive_or_nonfinite_acceptance_is_not_coverage(quantity):
    source = pin()
    current = measurement(2, "1", sources=[source], input_mode="PERIOD_DELTA")
    with pytest.raises(HTTPException):
        _progress_quantity_coverage(Owner([adoption(source)]), 5, current, [acceptance(source, quantity)])
