"""Make private QA contact sheets from the live workbook's rendered ranges."""

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1a-20261019/workbook"


def main() -> None:
    previews = json.loads((QA / "render-manifest.json").read_text(encoding="utf-8"))
    contacts = []
    for batch in range(0, len(previews), 12):
        entries = previews[batch : batch + 12]
        tiles = []
        for entry in entries:
            with Image.open(QA / entry["file"]) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((760, 470))
                tile = Image.new("RGB", (780, 510), "#e4eaf0")
                ImageDraw.Draw(tile).text(
                    (10, 8), f"{entry['sheet']} {entry['range']}", fill="black"
                )
                tile.paste(thumb, (10, 32))
                tiles.append(tile)
        contact = Image.new("RGB", (1560, 510 * ((len(tiles) + 1) // 2)), "white")
        for index, tile in enumerate(tiles):
            contact.paste(tile, ((index % 2) * 780, (index // 2) * 510))
        target = QA / f"contact-{batch // 12 + 1}.png"
        contact.save(target)
        contacts.append(target.name)
    print(json.dumps({"rendered_ranges": len(previews), "contacts": contacts}))


if __name__ == "__main__":
    main()
