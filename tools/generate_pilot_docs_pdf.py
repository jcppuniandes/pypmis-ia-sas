from pathlib import Path
import re
from textwrap import wrap

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]

DOCUMENTS = [
    {
        "source": ROOT / "docs" / "09-resumen-analisis-manual-piloto.md",
        "output": ROOT / "docs" / "Analisis_Resumen_Piloto_Pypmis_Ai_SaaS.pdf",
        "title": "Analisis Y Resumen Del Piloto",
        "subtitle": "P&Pmis Ai SaaS - Estado, comparativo y paso a paso",
    },
    {
        "source": ROOT / "docs" / "10-manual-uso-detallado-modulos.md",
        "output": ROOT / "docs" / "Manual_Uso_Detallado_Modulos_Pypmis_Ai_SaaS.pdf",
        "title": "Manual De Uso Detallado",
        "subtitle": "Modulo por modulo para piloto colaborativo",
    },
]

W, H = A4
LEFT = 1.55 * cm
RIGHT = W - 1.55 * cm
TOP = H - 1.45 * cm
BOTTOM = 1.45 * cm
LINE = 12.5


def clean(text: str) -> str:
    replacements = {
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "✅": "OK",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "")
    text = text.replace("__", "")
    return clean(text)


def parse_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and lines[index].strip().startswith("|"):
        parts = [strip_markdown(part.strip()) for part in lines[index].strip().strip("|").split("|")]
        if not all(set(part) <= {"-", ":", " "} for part in parts):
            rows.append(parts)
        index += 1
    return rows, index


class PdfDoc:
    def __init__(self, output: Path, title: str, subtitle: str, source_name: str) -> None:
        self.output = output
        self.title = title
        self.subtitle = subtitle
        self.source_name = source_name
        self.canvas = canvas.Canvas(str(output), pagesize=A4)
        self.canvas.setTitle(title)
        self.canvas.setAuthor("Codex")
        self.page_no = 0
        self.y = TOP

    def footer(self) -> None:
        c = self.canvas
        c.setStrokeColor(colors.HexColor("#d8dee5"))
        c.line(LEFT, 1.12 * cm, RIGHT, 1.12 * cm)
        c.setFillColor(colors.HexColor("#667481"))
        c.setFont("Helvetica", 7.3)
        c.drawString(LEFT, 0.76 * cm, clean(f"P&Pmis Ai SaaS - {self.title}"))
        c.drawRightString(RIGHT, 0.76 * cm, f"Pagina {self.page_no}")

    def new_page(self, title: str | None = None) -> None:
        if self.page_no:
            self.footer()
            self.canvas.showPage()
        self.page_no += 1
        self.y = TOP
        if title:
            c = self.canvas
            c.setFillColor(colors.HexColor("#17212b"))
            c.setFont("Helvetica-Bold", 15.5)
            c.drawString(LEFT, self.y, clean(title[:92]))
            self.y -= 18
            c.setStrokeColor(colors.HexColor("#0f8b8d"))
            c.setLineWidth(1.2)
            c.line(LEFT, self.y + 7, RIGHT, self.y + 7)
            self.y -= 8

    def ensure_space(self, lines: int = 4) -> None:
        if self.y - lines * LINE < BOTTOM:
            self.new_page()

    def cover(self, headings: list[str]) -> None:
        self.new_page()
        c = self.canvas
        c.setFillColor(colors.HexColor("#17212b"))
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(W / 2, H - 4.2 * cm, clean(self.title))
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.HexColor("#0f8b8d"))
        c.drawCentredString(W / 2, H - 5.05 * cm, clean(self.subtitle))
        c.setFont("Helvetica", 10.2)
        c.setFillColor(colors.HexColor("#52616f"))
        c.drawCentredString(W / 2, H - 5.75 * cm, "Fecha base: 2026-05-06")
        c.drawCentredString(W / 2, H - 6.35 * cm, clean(f"Fuente: {self.source_name}"))

        c.setFillColor(colors.HexColor("#edf7f7"))
        c.roundRect(LEFT, H - 11.8 * cm, RIGHT - LEFT, 3.2 * cm, 8, fill=1, stroke=0)
        self.y = H - 9.15 * cm
        self.paragraph(
            "Documento generado para ejecutar el piloto de P&Pmis Ai SaaS como plataforma colaborativa en linea "
            "de Project Controls, con trazabilidad por roles, workflows, Cost Manager, AWP, contratos, claims y readiness.",
            width_chars=92,
            gap=10,
        )

        self.y = H - 12.8 * cm
        self.heading("Contenido")
        for heading in headings[:24]:
            self.bullet_line(heading, width_chars=94)

    def heading(self, text: str) -> None:
        self.ensure_space(3)
        self.canvas.setFillColor(colors.HexColor("#0f4c5c"))
        self.canvas.setFont("Helvetica-Bold", 12)
        self.canvas.drawString(LEFT, self.y, clean(text[:105]))
        self.y -= 15.5

    def subheading(self, text: str) -> None:
        self.ensure_space(2)
        self.canvas.setFillColor(colors.HexColor("#17212b"))
        self.canvas.setFont("Helvetica-Bold", 10.2)
        self.canvas.drawString(LEFT, self.y, clean(text[:110]))
        self.y -= 13.5

    def paragraph(self, text: str, width_chars: int = 102, gap: int = 5) -> None:
        text = strip_markdown(text)
        if not text:
            self.y -= 3
            return
        self.canvas.setFont("Helvetica", 8.9)
        self.canvas.setFillColor(colors.HexColor("#243441"))
        for line in wrap(text, width_chars):
            self.ensure_space(1)
            self.canvas.drawString(LEFT, self.y, clean(line))
            self.y -= LINE
        self.y -= gap

    def bullet_line(self, text: str, width_chars: int = 96) -> None:
        lines = wrap(strip_markdown(text), width_chars)
        self.ensure_space(len(lines) + 1)
        self.canvas.setFont("Helvetica", 8.8)
        self.canvas.setFillColor(colors.HexColor("#0f8b8d"))
        self.canvas.drawString(LEFT + 4, self.y, "-")
        self.canvas.setFillColor(colors.HexColor("#243441"))
        self.canvas.drawString(LEFT + 18, self.y, clean(lines[0] if lines else ""))
        self.y -= LINE
        for line in lines[1:]:
            self.canvas.drawString(LEFT + 18, self.y, clean(line))
            self.y -= LINE

    def numbered_line(self, number: str, text: str, width_chars: int = 94) -> None:
        lines = wrap(strip_markdown(text), width_chars)
        self.ensure_space(len(lines) + 1)
        self.canvas.setFont("Helvetica-Bold", 8.8)
        self.canvas.setFillColor(colors.HexColor("#0f8b8d"))
        self.canvas.drawString(LEFT + 2, self.y, clean(number))
        self.canvas.setFont("Helvetica", 8.8)
        self.canvas.setFillColor(colors.HexColor("#243441"))
        self.canvas.drawString(LEFT + 24, self.y, clean(lines[0] if lines else ""))
        self.y -= LINE
        for line in lines[1:]:
            self.canvas.drawString(LEFT + 24, self.y, clean(line))
            self.y -= LINE

    def code_block(self, code: list[str]) -> None:
        if not code:
            return
        width_chars = 94
        rendered: list[str] = []
        for raw in code:
            rendered.extend(wrap(clean(raw), width_chars) or [""])
        height = len(rendered) * LINE + 12
        self.ensure_space(len(rendered) + 2)
        self.canvas.setFillColor(colors.HexColor("#f1f4f6"))
        self.canvas.roundRect(LEFT, self.y - height + 6, RIGHT - LEFT, height, 5, fill=1, stroke=0)
        self.canvas.setFont("Courier", 8.2)
        self.canvas.setFillColor(colors.HexColor("#17212b"))
        yy = self.y - 4
        for line in rendered:
            self.canvas.drawString(LEFT + 8, yy, clean(line))
            yy -= LINE
        self.y -= height + 4

    def table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        col_count = max(len(row) for row in rows)
        col_width = (RIGHT - LEFT) / col_count
        for row_index, row in enumerate(rows):
            normalized = row + [""] * (col_count - len(row))
            wrapped = [wrap(strip_markdown(cell), max(int(col_width / 4.1), 16)) or [""] for cell in normalized]
            row_lines = max(len(cell_lines) for cell_lines in wrapped)
            height = row_lines * LINE + 9
            self.ensure_space(row_lines + 2)
            self.canvas.setFillColor(colors.HexColor("#eaf8f2") if row_index == 0 else colors.HexColor("#fbfcfd"))
            self.canvas.rect(LEFT, self.y - height + 7, RIGHT - LEFT, height, fill=1, stroke=0)
            self.canvas.setStrokeColor(colors.HexColor("#d8dee5"))
            self.canvas.rect(LEFT, self.y - height + 7, RIGHT - LEFT, height, fill=0, stroke=1)
            for col_index, cell_lines in enumerate(wrapped):
                x = LEFT + col_index * col_width + 5
                yy = self.y
                self.canvas.setFont("Helvetica-Bold" if row_index == 0 else "Helvetica", 7.7)
                self.canvas.setFillColor(colors.HexColor("#17212b") if row_index == 0 else colors.HexColor("#243441"))
                for line in cell_lines:
                    self.canvas.drawString(x, yy, clean(line[:44]))
                    yy -= LINE
            self.y -= height + 2
        self.y -= 4

    def save(self) -> None:
        self.footer()
        self.canvas.save()


def render_markdown(source: Path, output: Path, title: str, subtitle: str) -> int:
    lines = source.read_text(encoding="utf-8").splitlines()
    headings = [strip_markdown(line[3:].strip()) for line in lines if line.startswith("## ")]
    doc = PdfDoc(output, title, subtitle, source.name)
    doc.cover(headings)

    index = 0
    in_code = False
    code_lines: list[str] = []
    while index < len(lines):
        raw = lines[index]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                doc.code_block(code_lines)
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue

        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if stripped.startswith("|"):
            rows, index = parse_table(lines, index)
            doc.table(rows)
            continue

        if stripped.startswith("# "):
            index += 1
            continue

        if stripped.startswith("## "):
            doc.new_page(strip_markdown(stripped[3:].strip()))
        elif stripped.startswith("### "):
            doc.heading(strip_markdown(stripped[4:].strip()))
        elif stripped.startswith("#### "):
            doc.subheading(strip_markdown(stripped[5:].strip()))
        elif stripped.startswith("- "):
            doc.bullet_line(stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            number, text = stripped.split(".", 1)
            doc.numbered_line(f"{number}.", text.strip())
        else:
            doc.paragraph(stripped)
        index += 1

    doc.save()
    return len(PdfReader(str(output)).pages)


def main() -> None:
    for item in DOCUMENTS:
        pages = render_markdown(item["source"], item["output"], item["title"], item["subtitle"])
        print(f"{item['output'].relative_to(ROOT)} - {pages} paginas")


if __name__ == "__main__":
    main()
