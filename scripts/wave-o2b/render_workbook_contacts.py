"""Build private contact sheets to review every rendered Excel range."""

import json
import sys
from pathlib import Path

from evidence import QA
from PIL import Image, ImageDraw


def main(directory):
    directory = directory.resolve()
    assert directory.is_relative_to(QA)
    proof = json.loads((directory / "render-provenance.json").read_text("utf-8"))
    previews = proof["previews"]
    width, height, batch = 960, 460, 6
    for start in range(0, len(previews), batch):
        entries = previews[start : start + batch]
        canvas = Image.new(
            "RGB", (width * 2, height * ((len(entries) + 1) // 2)), "#eef2f6"
        )
        label = ImageDraw.Draw(canvas)
        for index, row in enumerate(entries):
            x, y = (index % 2) * width, (index // 2) * height
            label.text(
                (x + 10, y + 7), f"{row['sheet']} {row['range']}", fill="#172e45"
            )
            with Image.open(directory / row["file"]) as source:
                thumbnail = source.convert("RGB")
                thumbnail.thumbnail((width - 20, height - 32))
                canvas.paste(thumbnail, (x + 10, y + 25))
        canvas.save(directory / f"contact-{start // batch + 1}.png")
    print(f"{len(previews)} ranges included")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
