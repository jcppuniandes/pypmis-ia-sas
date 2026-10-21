"""Private contact sheets of the exact saved workbook preview ranges."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/operational-master-architecture-20261019"


def main():
    proof = json.loads(
        (QA / "workbook/saved-verification.json").read_text(encoding="utf-8")
    )
    assert len(proof["renders"]) == 106
    groups = {}
    for render in proof["renders"]:
        path = ROOT / render["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == render["sha256"]
        groups.setdefault(render["sheetName"], []).append(render)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    contacts = []
    dest = QA / "contacts"
    dest.mkdir(parents=True, exist_ok=True)
    for sheet, rows in groups.items():
        for offset in range(0, len(rows), 4):
            chunk = rows[offset : offset + 4]
            canvas = Image.new("RGB", (2300, 2300), "#CBD5E1")
            draw = ImageDraw.Draw(canvas)
            for index, row in enumerate(chunk):
                path = ROOT / row["path"]
                source = Image.open(path).convert("RGB")
                source.thumbnail((1120, 1080))
                x, y = (index % 2) * 1150 + 10, (index // 2) * 1150 + 45
                draw.text(
                    (x, y - 33), sheet + " / " + row["range"], font=font, fill="#17324D"
                )
                canvas.paste(source, (x, y))
            path = dest / f"{sheet}-{offset // 4 + 1}.png"
            canvas.save(path)
            contacts.append(
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "ranges": chunk,
                }
            )
    (dest / "manifest.json").write_text(
        json.dumps(
            {"workbook_sha256": proof["outputSha256"], "contacts": contacts}, indent=2
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ranges": 106, "contacts": len(contacts), "sheets": len(groups)}))


if __name__ == "__main__":
    main()
