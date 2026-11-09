"""Record manual visual inspection of the already rendered O1C evidence."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"


def png_digests(paths):
    paths = list(paths)
    assert paths and all(path.is_file() and path.stat().st_size > 0 for path in paths)
    return {
        str(path.relative_to(QA)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("browser", "artifacts"))
    parser.add_argument(
        "--all-rendered-views-inspected", action="store_true", required=True
    )
    parser.add_argument("--word-pages", default="word-pages-final")
    args = parser.parse_args()
    checked_at = datetime.now(UTC).isoformat()
    if args.target == "browser":
        browser = QA / "chromium"
        layout = json.loads((browser / "layout-final.json").read_text("utf-8"))
        assert layout["result"] == "PASS"
        screenshots = [
            path
            for path in sorted(browser.glob("*.png"))
            if not path.name.startswith("failure-")
        ]
        final = [path for path in screenshots if path.name.startswith("presentation-")]
        business = [path for path in screenshots if path not in final]
        assert len(final) == 6 and business and layout["presentation_revalidated"]
        proof = {
            "result": "PASS",
            "checked_at_utc": checked_at,
            "original_business_uat_screenshots": png_digests(business),
            "final_presentation_screenshots": png_digests(final),
            "manual_review": "Original UAT retains pre-polish visuals; final recheck verifies the corrected views",
        }
        output = browser / "visual-check.json"
    else:
        word = (QA / args.word_pages).resolve()
        assert word.is_relative_to(QA.resolve())
        provenance = json.loads((word / "render-provenance.json").read_text("utf-8"))
        word_pages = sorted(word.glob("page-*.png"))
        assert len(word_pages) == len(provenance["pages"])
        workbook = QA / "workbook"
        previews = json.loads((workbook / "render-manifest.json").read_text("utf-8"))
        sheets = {item["sheet"] for item in previews}
        assert len(sheets) == 19
        proof = {
            "result": "PASS",
            "checked_at_utc": checked_at,
            "all_word_pages_reviewed": True,
            "all_workbook_sheets_reviewed": True,
            "all_workbook_preview_ranges_reviewed": True,
            "word_latest_render": args.word_pages,
            "word_pages": len(word_pages),
            "workbook_sheets": len(sheets),
            "workbook_preview_ranges": len(previews),
            "word_png_sha256": png_digests(word_pages),
            "workbook_png_sha256": png_digests(
                workbook / item["file"] for item in previews
            ),
        }
        output = QA / "visual-review.json"
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(
        json.dumps({"result": "PASS", "target": args.target, "evidence": str(output)})
    )


if __name__ == "__main__":
    main()
