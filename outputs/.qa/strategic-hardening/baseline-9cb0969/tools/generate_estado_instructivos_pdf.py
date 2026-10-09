from pathlib import Path
import re
from textwrap import wrap


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "23-resumen-estado-instructivos-2026-05-14.md"
OUTPUT = ROOT / "docs" / "Resumen_Estado_Instructivos_2026-05-14.pdf"
FALLBACK_OUTPUT = ROOT / "docs" / "Resumen_Estado_Instructivos_Prioridades_Implementadas_2026-05-14.pdf"

PAGE_W = 595
PAGE_H = 842
LEFT = 54
TOP = 790
BOTTOM = 54
LINE = 13


def clean(text: str) -> str:
    replacements = {
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "’": "'",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "ñ": "n",
        "Ñ": "N",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "")
    return clean(text)


def escape_pdf(text: str) -> str:
    return clean(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class SimplePdf:
    def __init__(self) -> None:
        self.pages: list[list[tuple[int, str, str]]] = []
        self.current: list[tuple[int, str, str]] = []
        self.y = TOP

    def new_page(self) -> None:
        if self.current:
            self._footer()
            self.pages.append(self.current)
        self.current = []
        self.y = TOP

    def _footer(self) -> None:
        page_no = len(self.pages) + 1
        self.current.append((42, "Helvetica", "P&Pmis Ai SaaS - Estado frente a instructivos"))
        self.current.append((42, "Helvetica", f"Pagina {page_no}"))

    def ensure(self, lines: int = 1) -> None:
        if self.y - lines * LINE < BOTTOM:
            self.new_page()

    def text(self, value: str, size: int = 9, font: str = "Helvetica", indent: int = 0) -> None:
        self.ensure(1)
        self.current.append((self.y, f"{font}:{size}:{LEFT + indent}", value))
        self.y -= LINE if size <= 10 else size + 5

    def gap(self, amount: int = 6) -> None:
        self.y -= amount

    def heading(self, value: str) -> None:
        self.ensure(3)
        self.text(value, size=13, font="Helvetica-Bold")
        self.gap(3)

    def paragraph(self, value: str, width: int = 96, indent: int = 0) -> None:
        value = strip_markdown(value)
        for line in wrap(value, width):
            self.text(line, size=9, indent=indent)
        self.gap(4)

    def bullet(self, value: str) -> None:
        lines = wrap(strip_markdown(value), 90)
        if not lines:
            return
        self.text("- " + lines[0], size=9, indent=10)
        for line in lines[1:]:
            self.text("  " + line, size=9, indent=10)

    def table_row(self, cells: list[str]) -> None:
        cells = (cells + ["", "", ""])[:3]
        text = f"{strip_markdown(cells[0])}: {strip_markdown(cells[1])}. {strip_markdown(cells[2])}"
        self.bullet(text)

    def cover(self) -> None:
        self.new_page()
        self.y = 700
        self.current.append((self.y, "Helvetica-Bold:22:70", "Resumen de estado actual"))
        self.y -= 32
        self.current.append((self.y, "Helvetica-Bold:14:70", "P&Pmis Ai SaaS frente a instructivos Unifier 26"))
        self.y -= 24
        self.current.append((self.y, "Helvetica:10:70", "Fecha: 14 de mayo de 2026"))
        self.y -= 34
        self.paragraph(
            "Informe generado con base en los tres instructivos compartidos y en el estado actual de la app "
            "levantada localmente. Resume que ya esta operativo, que falta para completar la alineacion tipo "
            "Unifier y como usar el flujo disponible.",
            width=82,
            indent=16,
        )
        self.new_page()

    def render_markdown(self, markdown: str) -> None:
        lines = markdown.splitlines()
        index = 0
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped:
                self.gap(3)
                index += 1
                continue
            if stripped.startswith("# "):
                index += 1
                continue
            if stripped.startswith("## "):
                self.heading(stripped[3:])
            elif stripped.startswith("### "):
                self.heading(stripped[4:])
            elif stripped.startswith("|"):
                rows: list[list[str]] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    parts = [part.strip() for part in lines[index].strip().strip("|").split("|")]
                    if not all(set(part) <= {"-", ":", " "} for part in parts):
                        rows.append(parts)
                    index += 1
                for row in rows[1:]:
                    self.table_row(row)
                continue
            elif stripped.startswith("- "):
                self.bullet(stripped[2:])
            elif re.match(r"^\d+\. ", stripped):
                self.bullet(re.sub(r"^\d+\. ", "", stripped))
            else:
                self.paragraph(stripped)
            index += 1

    def finish(self) -> None:
        if self.current:
            self._footer()
            self.pages.append(self.current)
            self.current = []

    def write(self, path: Path) -> None:
        self.finish()
        objects: list[bytes] = []

        def add_object(payload: bytes) -> int:
            objects.append(payload)
            return len(objects)

        font_regular = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_bold = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        page_ids: list[int] = []
        content_ids: list[int] = []

        for page in self.pages:
            chunks = ["BT"]
            for y, font_spec, value in page:
                if ":" in font_spec:
                    font_name, size, x = font_spec.split(":")
                    font_key = "F2" if font_name == "Helvetica-Bold" else "F1"
                    chunks.append(f"/{font_key} {size} Tf")
                    chunks.append(f"{x} {y} Td ({escape_pdf(value)}) Tj")
                    chunks.append(f"-{x} -{y} Td")
                else:
                    chunks.append(f"/F1 7 Tf 42 {y} Td ({escape_pdf(value)}) Tj -42 -{y} Td")
            chunks.append("ET")
            stream = "\n".join(chunks).encode("latin-1")
            content_id = add_object(
                f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
            )
            content_ids.append(content_id)
            page_ids.append(0)

        pages_id = len(objects) + len(self.pages) + 1
        for idx, content_id in enumerate(content_ids):
            page_id = add_object(
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("latin-1")
            )
            page_ids[idx] = page_id

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        pages_id_actual = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1"))
        assert pages_id_actual == pages_id
        catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id, payload in enumerate(objects, start=1):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode("latin-1"))
            output.extend(payload)
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        output.extend(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("latin-1")
        )
        path.write_bytes(output)


def main() -> None:
    pdf = SimplePdf()
    pdf.cover()
    pdf.render_markdown(SOURCE.read_text(encoding="utf-8"))
    try:
        pdf.write(OUTPUT)
        print(OUTPUT)
    except PermissionError:
        pdf.write(FALLBACK_OUTPUT)
        print(FALLBACK_OUTPUT)


if __name__ == "__main__":
    main()
