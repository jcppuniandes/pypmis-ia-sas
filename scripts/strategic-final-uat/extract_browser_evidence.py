"""Extract only named JSON Playwright attachments; never unzip trace paths."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/strategic-final-uat"
SOURCE = QA / "browser-final"
OUT = QA / "performance"
NAMES = {
    "local-read-measurements.json",
    "local-navigation-measurement.json",
    "generic-admin-project-negative.json",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    extracted = []
    for archive in sorted(SOURCE.glob("*/trace.zip")):
        with ZipFile(archive) as trace:
            for line in trace.read("test.trace").decode("utf-8").splitlines():
                event = json.loads(line)
                for attachment in event.get("attachments", []):
                    name = attachment.get("name")
                    if name not in NAMES:
                        continue
                    sha1 = attachment.get("sha1", "")
                    if not re.fullmatch(r"[0-9a-f]{40}", sha1):
                        raise ValueError(f"Invalid trace attachment SHA1: {name}")
                    raw = trace.read(f"resources/{sha1}")
                    if hashlib.sha1(raw).hexdigest() != sha1:
                        raise ValueError(f"Trace resource hash mismatch: {name}")
                    json.loads(raw)
                    target = OUT / name
                    target.write_bytes(raw)
                    extracted.append(
                        {
                            "name": name,
                            "source": archive.relative_to(ROOT).as_posix(),
                            "resource": f"resources/{sha1}",
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
    if {item["name"] for item in extracted} != NAMES:
        raise ValueError("Not all expected browser attachments were extracted")

    observations = {
        "admin-composition-rules.png": {
            "visual": "Legible desktop rule editor; active Composition Rules tab, hierarchy guardrail form, published type list and breadcrumbs visible. No Project creation form visible.",
            "limitations": "The tab row clips the following Physical Workspace label at the right boundary. Screenshot does not prove all tabs keyboard reachable or editing/publishing behavior.",
        },
        "user-review-after-convergence.png": {
            "visual": "Desktop sidebar places Periodic Portfolio Review after Scenario Convergence; breadcrumb and empty-session Review surface are legible.",
            "limitations": "No Review session exists: the screenshot is an empty-state/navigation proof, not populated Project Matrix evidence. Long horizontal tab row exceeds visible width.",
        },
        "user-review-mobile.png": {
            "visual": "390-pixel responsive view has legible text, stacked context cards, visible breadcrumb, Review controls and empty-state content. No overlapping body text found.",
            "limitations": "Expanded navigation dominates several thousand pixels before main content. Two-column phase arrangement makes Phase 5 appear visually above Phase 4; labels are individually readable but linear process scanning is awkward. Review tab strip shows only its first items. No assertion of full mobile usability or WCAG conformance.",
        },
        "reader-admin-denied.png": {
            "visual": "Configuration access required denial message is clear and no rule editor/Save action is visible.",
            "limitations": "Direct ADMIN URL still renders ADMIN shell/header and navigation for the read-only actor. Proof is content/action denial, not total shell concealment or complete authorization coverage.",
        },
        "enterprise-explorer-context.png": {
            "visual": "Explorer route, breadcrumb, authorized action links and focused type filter are legible.",
            "limitations": "Captured during CONSULTANDO... with 0 results and no selected node. This image does NOT prove hydrated hierarchical context or successful selection. Spec waits only for heading, focus and Create Project button, not overview response completion, loading disappearance or actual node rendering.",
        },
        "gate-frozen-historical-read.png": {
            "visual": "Selected Preparation r1, evidence package, READY versus can_enter_fid=false and multiple governed evidence cards are visible. Historical equality is asserted separately in test JSON, not established by this image alone.",
            "limitations": "Actionable card text overflow: resource-feasibility VALID badge reaches/overlaps its right border and a long FROZEN_HISTORICAL_SOURCE_PRESERVED warning token crosses into the neighboring card. Decision Package long status is clipped at the right edge. Other long card names wrap. Test does not check frozen controls are disabled; some Remove controls remain visible/enabled. Do not infer mutation authorization from their appearance alone.",
        },
        "business-case-captured-sources.png": {
            "visual": "Sources & Evidence tab, BC-00001 R3 COMPLETED READY and source lineage table are legible; source/read-only boundary banner visible.",
            "limitations": "Wide source table clips Source/action columns to the right and tab strip is horizontally scrolled/clips Strategic Case. Several source rows explicitly NOT_AVAILABLE or STALE: this is historical display, not evidence that all modern Five Case providers are current or fresh Capital Owner UAT complete.",
        },
        "policy-historical-read-only.png": {
            "visual": "History tab shows published and draft revisions with hash prefixes, and persisted=false dry-run success banner. No overlapping text.",
            "limitations": "At screenshot time current Policy revision selector says rev1 draft and Save/Publish remain visible. Test previously selected the published ID, but the PNG is history display proof, not proof that a published revision was still selected or all historical editor controls disabled. History equality before/after is asserted separately. Long tab strip clips leading items.",
        },
    }
    screenshots = []
    for path in sorted(SOURCE.glob("*/*.png")):
        with Image.open(path) as img:
            dimensions = list(img.size)
        screenshots.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "dimensions": dimensions,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "visually_inspected": True,
                **observations[path.name],
            }
        )
    if len(screenshots) != 8:
        raise ValueError(f"Expected exactly 8 PNGs, got {len(screenshots)}")
    xml = ET.parse(QA / "browser-final.xml").getroot()
    result = {
        "audit_kind": "Read-only extraction and visual evidence audit; no browser rerun or product changes",
        "junit": {
            "tests": int(xml.attrib["tests"]),
            "failures": int(xml.attrib["failures"]),
            "errors": int(xml.attrib["errors"]),
            "skipped": int(xml.attrib["skipped"]),
            "wrapper_seconds": float(xml.attrib["time"]),
            "test_body_seconds": sum(float(x.attrib["time"]) for x in xml.iter("testcase")),
            "cases": [
                {"name": case.attrib["name"], "seconds": float(case.attrib["time"])}
                for case in xml.iter("testcase")
            ],
        },
        "extracted_attachments": extracted,
        "screenshots": screenshots,
        "conclusion": "4 tests PASS, 8 screenshots inspected; visual caveats and evidence coverage limits remain. Do not label the UI visually flawless or whole strategic UAT accepted.",
        "accessibility_scope": "Automated focus and Enter/Tab checks on selected controls plus one mobile screenshot only; no comprehensive WCAG, screen-reader, contrast or full keyboard traversal audit.",
        "performance_scope": "Single local reads/UI action including JSON parsing on isolated Chromium/API/PostgreSQL fixture. No percentiles, concurrency/load or production SLA. Portfolio Review Project Matrix was not measured because no session existed. Navigation timing ends at visible route surface, not full hydration.",
    }
    (OUT / "browser-evidence-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attachments": len(extracted), "screenshots_inspected": len(screenshots), "junit": result["junit"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
