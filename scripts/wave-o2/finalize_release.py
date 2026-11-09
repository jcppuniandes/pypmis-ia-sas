"""Verify native artifacts and record the architecture-only release decision."""

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from zipfile import ZipFile

from collect_evidence import ARCH, PROMPT, QA, ROOT, digest, read
from generate_report import OUT, REFERENCE, REFERENCE_SHA, REPORT
from report_content import chapters

WORKBOOK = OUT / "P&Pmis_Wave_O2_Master_Architecture_Traceability.xlsx"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workbook_contacts():
    module = load_module(
        "o2_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
    )
    module.QA = QA / "workbook"
    module.main()


def finalize(word_directory):
    data = read(QA / "package-data.json")
    assert digest(PROMPT) == data["prompt_sha256"]
    assert all(
        digest(ARCH / name) == sha for name, sha in data["source_sha256"].items()
    )
    assert digest(REFERENCE) == REFERENCE_SHA
    native = load_module(
        "o1c_native_verifier", ROOT / "scripts/wave-o1c/verify_native_artifacts.py"
    )
    native.QA = QA
    native.WORKBOOK = WORKBOOK
    native.EXPECTED_SHEETS = tuple(spec["name"] for spec in data["sheets"])
    expected_tables = [
        {"sheet": spec["name"], "headers": spec["headers"], "rows": spec["rows"]}
        for spec in data["sheets"]
    ]
    assert read(QA / "workbook/expected-tables.json") == expected_tables
    workbook_proof = native.verify_workbook()
    with ZipFile(REPORT) as final, ZipFile(REFERENCE) as ref:
        xmls, relationships = native.package_xml(final)
        assert final.namelist() == ref.namelist()
        assert {
            name for name in final.namelist() if ref.read(name) != final.read(name)
        } == {
            "docProps/core.xml",
            "word/document.xml",
        }
        style_namespace = "{" + native.NS["w"] + "}"
        actual = []
        for p in xmls["word/document.xml"].findall("w:body/w:p", native.NS):
            style = p.find("w:pPr/w:pStyle", native.NS)
            if style is not None and style.get(style_namespace + "val") == "Heading1":
                actual.append(
                    "".join(t.text or "" for t in p.findall(".//w:t", native.NS))
                )
        assert actual == [
            f"{i} {title}" for i, (title, _) in enumerate(chapters(data), 1)
        ]
    render = (QA / word_directory).resolve()
    assert render.is_relative_to(QA.resolve())
    word_proof = read(render / "render-provenance.json")
    assert word_proof["input_docx_sha256"] == digest(REPORT)
    assert word_proof["pages"] and all(
        digest(render / file) == sha for file, sha in word_proof["pages"].items()
    )
    a11y = read(QA / "a11y.json")
    assert not a11y["findings"] and not any(a11y["counts"].values())
    workbook_renders = read(QA / "workbook/render-manifest.json")
    assert {x["sheet"] for x in workbook_renders} == set(native.EXPECTED_SHEETS)
    assert len(workbook_renders) == len({x["file"] for x in workbook_renders})
    previews = {
        x["file"]: digest(QA / "workbook" / x["file"]) for x in workbook_renders
    }
    assert set(OUT.iterdir()) == {REPORT, WORKBOOK}
    before, after = (
        read(QA / f"preservation-{phase}.json")["observation"]
        for phase in ("before", "after")
    )
    assert before == after
    assert all(
        digest(ROOT / file) == sha
        for file, sha in after["application_source_sha256"].items()
    )
    result = {
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "closed_utc": datetime.now(UTC).isoformat(),
        "scope": "ARCHITECTURE_ONLY",
        "criteria_count": data["criteria_count"],
        "offline_design_vectors": len(data["proof"]["cases"]),
        "o1_baselines_reused": len(data["baseline"]["o1_baselines"]),
        "project14_preserved": data["baseline"],
        "open_architecture_s1": 0,
        "open_architecture_s2": 0,
        "runtime_modules_changed": False,
        "migration_applied": False,
        "transactional_o2_uat_performed": False,
        "business_approval_recorded": False,
        "commit_or_push_performed": False,
        "o2a_started": False,
        "next_increment": "WAVE O2A — ENGINEERING FOUNDATION",
        "artifact_native_checks": {
            **workbook_proof,
            "word_headings": len(actual),
            "word_relationships": relationships,
            "word_a11y_findings": 0,
        },
        "visual_checks": {
            "word_pages_manually_reviewed": word_proof["pages"],
            "workbook_ranges_manually_reviewed": previews,
        },
        "architecture_source_sha256": data["source_sha256"],
        "prompt_sha256": data["prompt_sha256"],
        "builder_source_sha256": {
            path.name: digest(path)
            for path in sorted((ROOT / "scripts/wave-o2").iterdir())
            if path.is_file()
        },
        "artifacts": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }
            for path in (REPORT, WORKBOOK)
        ],
    }
    (ARCH / "release-manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "state": result["release_state"],
                "criteria": result["criteria_count"],
                "word_pages": len(word_proof["pages"]),
                "workbook_ranges": len(previews),
                "compared_cells": workbook_proof["compared_cells"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contacts", action="store_true")
    parser.add_argument("--all-pages-and-ranges-inspected", action="store_true")
    parser.add_argument("--word-pages", default="word-pages-1")
    args = parser.parse_args()
    if args.contacts:
        workbook_contacts()
    else:
        assert args.all_pages_and_ranges_inspected
        finalize(args.word_pages)
