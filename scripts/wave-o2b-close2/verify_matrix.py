"""Read-only verification of the CLOSE-2 workbook export and its edit boundary."""

import json
import sys
from hashlib import file_digest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "outputs/.qa/wave-o2b-close2-20261112/artifacts"
STEM = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability"


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def tables(sheet):
    return {
        item.name: (
            item.ref,
            item.autoFilter.ref if item.autoFilter else None,
            item.tableStyleInfo.name if item.tableStyleInfo else None,
            [column.name for column in item.tableColumns],
        )
        for item in sheet.tables.values()
    }


def structure(sheet):
    return {
        "tables": tables(sheet),
        "freeze_panes": sheet.freeze_panes,
        "merges": sorted(str(value) for value in sheet.merged_cells.ranges),
        "conditional": {
            str(key.sqref): [
                (row.type, row.operator, row.formula)
                for row in sheet.conditional_formatting[key]
            ]
            for key in sheet.conditional_formatting
        },
        "validations": [
            (str(row.sqref), row.type, row.formula1, row.formula2)
            for row in (
                sheet.data_validations.dataValidation if sheet.data_validations else []
            )
        ],
        "columns": {
            key: (value.min, value.max, value.width, value.hidden)
            for key, value in sheet.column_dimensions.items()
        },
        "state": sheet.sheet_state,
        "gridlines": sheet.sheet_view.showGridLines,
    }


def verify():
    edits = json.loads((ARTIFACTS / "matrix-edits.json").read_text("utf-8"))
    source = ROOT / "outputs/wave-o2b" / f"{STEM}.xlsx"
    candidate = ARTIFACTS / "candidate" / f"{STEM}1.xlsx"
    assert digest(source) == edits["baseline_sha256"], (
        "Baseline differs from authored revision"
    )
    assert digest(candidate) == edits["candidate_sha256"], (
        "Candidate differs from authored revision"
    )
    before, after = map(load_workbook, (source, candidate))
    assert before.sheetnames == after.sheetnames and len(before.sheetnames) == 17
    errors = []
    counts = {"values_updated": 0, "tables_preserved": 0}
    for old, new in zip(before, after, strict=True):
        patch = edits["cells"].get(old.title, {})
        previous, current = structure(old), structure(new)
        counts["tables_preserved"] += len(previous["tables"])
        for key in previous:
            if previous[key] != current[key]:
                errors.append(f"{old.title}: {key} changed unexpectedly.")
        if (old.max_row, old.max_column) != (new.max_row, new.max_column):
            errors.append(f"{old.title}: sheet extent changed unexpectedly.")
        for row in old.iter_rows(
            max_row=max(old.max_row, new.max_row),
            max_col=max(old.max_column, new.max_column),
        ):
            for a in row:
                b = new[a.coordinate]
                if b.value != patch.get(a.coordinate, a.value):
                    errors.append(f"{old.title}!{a.coordinate}: unexpected content.")
                if a.value != b.value:
                    counts["values_updated"] += 1
                if b.data_type == "e":
                    errors.append(
                        f"{old.title}!{a.coordinate}: Excel error {b.value!r}."
                    )
    assert counts["values_updated"] == sum(
        len(cells) for cells in edits["cells"].values()
    )
    return {
        "attempt": edits["attempt"],
        "sheets_preserved": len(before.sheetnames),
        **counts,
        "baseline_sha256": edits["baseline_sha256"],
        "candidate_sha256": edits["candidate_sha256"],
        "errors": errors,
    }


if __name__ == "__main__":
    report = verify()
    (ARTIFACTS / "matrix-verification.json").write_text(
        json.dumps(report, indent=2), "utf-8"
    )
    print(json.dumps(report, indent=2))
    sys.exit(bool(report["errors"]))
