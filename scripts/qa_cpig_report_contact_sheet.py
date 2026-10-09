from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path


ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "outputs" / ".qa" / "cpig-gap-review" / "render-fallback"
PAGES = sorted(RENDER.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
NATIVE_PDF = RENDER.parent / "word-native-qa.pdf"
NATIVE_RENDER = RENDER.parent / "render-native"
POPPLER = Path(r"C:\Users\Ricardo\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin")


def contact_pages(pages: list[Path], target_dir: Path) -> None:
    if not pages:
        raise RuntimeError("No rendered pages to inspect")
    cols, rows = 3, 3
    tile_width, tile_height = 560, 760
    for start in range(0, len(pages), cols * rows):
        batch = pages[start : start + cols * rows]
        canvas = Image.new("RGB", (cols * tile_width, rows * tile_height), "#e8edf1")
        draw = ImageDraw.Draw(canvas)
        for offset, path in enumerate(batch):
            page = Image.open(path).convert("RGB")
            page.thumbnail((tile_width - 18, tile_height - 54))
            x = (offset % cols) * tile_width + (tile_width - page.width) // 2
            y = (offset // cols) * tile_height + 38
            canvas.paste(page, (x, y))
            draw.text(((offset % cols) * tile_width + 12, (offset // cols) * tile_height + 12), path.stem, fill="#17324d")
        target = target_dir / f"contact-{start // (cols * rows) + 1}.png"
        canvas.save(target, format="PNG", optimize=True)
        print(target)


def main() -> None:
    contact_pages(PAGES, RENDER)
    if NATIVE_PDF.exists():
        NATIVE_RENDER.mkdir(parents=True, exist_ok=True)
        pages = convert_from_path(str(NATIVE_PDF), dpi=144, poppler_path=str(POPPLER))
        for index, page in enumerate(pages, start=1):
            page.save(NATIVE_RENDER / f"page-{index}.png", "PNG")
        contact_pages(
            sorted(NATIVE_RENDER.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1])),
            NATIVE_RENDER,
        )

    diagrams = sorted((RENDER.parent / "diagrams").glob("*.png"))
    if diagrams:
        diagram_width, diagram_height = 900, 410
        canvas = Image.new("RGB", (diagram_width * 3, diagram_height * 3), "#e8edf1")
        draw = ImageDraw.Draw(canvas)
        for offset, path in enumerate(diagrams):
            page = Image.open(path).convert("RGB")
            page.thumbnail((diagram_width - 20, diagram_height - 56))
            x = (offset % 3) * diagram_width + (diagram_width - page.width) // 2
            y = (offset // 3) * diagram_height + 42
            canvas.paste(page, (x, y))
            draw.text(((offset % 3) * diagram_width + 15, (offset // 3) * diagram_height + 14), path.stem, fill="#17324d")
        target = RENDER / "diagram-contact.png"
        canvas.save(target, format="PNG", optimize=True)
        print(target)


if __name__ == "__main__":
    main()
