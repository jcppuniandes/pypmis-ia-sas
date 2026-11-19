"""Check the closeout workbook against the preserved original and the edit plan."""

import json
import sys
from hashlib import sha256

from freeze import QA
from openpyxl import load_workbook

NAME = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability.xlsx"
ARTIFACTS = QA / "artifacts"
RELEASE = "16_RELEASE_CRITERIA"


def tables(sheet):
    return {name: sheet.tables[name].ref for name in sheet.tables}


def verify():
    plan = json.loads((ARTIFACTS / "matrix-edits.json").read_text("utf-8"))
    base_path, final_path = (
        ARTIFACTS / part / NAME for part in ("baseline", "candidate")
    )
    base, final = (load_workbook(path) for path in (base_path, final_path))
    assert final.sheetnames == base.sheetnames and len(final.sheetnames) == 17
    errors = []
    for before, after in zip(base, final, strict=True):
        patches = plan["patch"].get(before.title, {})
        additions = {}
        expected_tables = tables(before)
        if before.title == RELEASE:
            additions["E2"] = "Controles de cierre O2B"
            for row, values in enumerate(
                [
                    [
                        "ID",
                        "Requisito",
                        "Implementación",
                        "Prueba",
                        "Evidencia",
                        "Resultado",
                        "Estado",
                        "Observación",
                    ],
                    *plan["controls"],
                ],
                7,
            ):
                for column, value in zip("EFGHIJKL", values, strict=True):
                    additions[f"{column}{row}"] = value
            expected_tables["O2BCloseControls"] = f"E7:L{7 + len(plan['controls'])}"
        if expected_tables != tables(after):
            errors.append(f"{before.title}: native table names or ranges changed")
        if before.freeze_panes != after.freeze_panes:
            errors.append(
                f"{before.title}: freeze panes changed {before.freeze_panes!r} → {after.freeze_panes!r}"
            )
        if {str(key.sqref) for key in before.conditional_formatting} - {
            str(key.sqref) for key in after.conditional_formatting
        }:
            errors.append(f"{before.title}: existing conditional formatting lost")
        if {str(x) for x in before.merged_cells.ranges} != {
            str(x) for x in after.merged_cells.ranges
        }:
            errors.append(f"{before.title}: merged ranges changed")
        for row in after.iter_rows(
            max_row=max(before.max_row, after.max_row),
            max_col=max(before.max_column, after.max_column),
        ):
            for cell in row:
                old = before[cell.coordinate]
                value = patches.get(
                    cell.coordinate, additions.get(cell.coordinate, old.value)
                )
                if cell.value != value:
                    errors.append(
                        f"{before.title}!{cell.coordinate}: unexpected value {cell.value!r} expected {value!r}"
                    )
                if cell.data_type == "e":
                    errors.append(
                        f"{before.title}!{cell.coordinate}: spreadsheet error {cell.value!r}"
                    )
    return {
        "errors": errors,
        "sheets": len(final.sheetnames),
        "closeout_controls": len(plan["controls"]),
        "targeted_cells": sum(len(patches) for patches in plan["patch"].values()),
        "baseline_sha256": sha256(base_path.read_bytes()).hexdigest(),
        "candidate_sha256": sha256(final_path.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    results = verify()
    (ARTIFACTS / "matrix-verification.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), "utf-8"
    )
    print(json.dumps(results, indent=2, ensure_ascii=True))
    sys.exit(bool(results["errors"]))
