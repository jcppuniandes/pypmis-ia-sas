import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const ROOT = process.cwd();
const SOURCE = path.join(ROOT, "docs", "23-resumen-estado-instructivos-2026-05-14.md");
const OUTPUTS = [
  path.join(ROOT, "docs", "Resumen_Estado_Instructivos_2026-05-14.pdf"),
  path.join(ROOT, "docs", "Resumen_Estado_Instructivos_Prioridades_Implementadas_2026-05-14.pdf"),
  path.join(ROOT, "docs", "Resumen_Estado_Instructivos_Agente_Auditor_2026-05-14.pdf"),
  path.join(ROOT, "docs", "Resumen_Estado_Instructivos_Agente_Auditor_Propuesta_2026-05-14.pdf"),
];

const PAGE_W = 595;
const PAGE_H = 842;
const LEFT = 54;
const TOP = 790;
const BOTTOM = 54;
const LINE = 13;

function clean(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[–—]/g, "-")
    .replace(/[“”]/g, "\"")
    .replace(/[’]/g, "'")
    .replace(/[^\x09\x0a\x0d\x20-\x7e]/g, "?");
}

function stripMarkdown(value) {
  return clean(value).replace(/`([^`]+)`/g, "$1").replace(/\*\*/g, "");
}

function wrapText(value, width) {
  const words = stripMarkdown(value).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    if (!line) line = word;
    else if (`${line} ${word}`.length <= width) line += ` ${word}`;
    else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

class PdfDoc {
  constructor() {
    this.pages = [];
    this.current = [];
    this.y = TOP;
  }

  newPage() {
    if (this.current.length) {
      this.footer();
      this.pages.push(this.current);
    }
    this.current = [];
    this.y = TOP;
  }

  footer() {
    const pageNo = this.pages.length + 1;
    this.current.push({ type: "text", x: 42, y: 34, size: 7, font: "F1", text: "P&Pmis Ai SaaS - Estado frente a instructivos", gray: 0 });
    this.current.push({ type: "text", x: 510, y: 34, size: 7, font: "F1", text: `Pagina ${pageNo}`, gray: 0 });
  }

  ensure(lines = 1) {
    if (this.y - lines * LINE < BOTTOM) this.newPage();
  }

  ensureHeight(height) {
    if (this.y - height < BOTTOM) this.newPage();
  }

  text(value, size = 9, font = "F1", indent = 0) {
    this.ensure(1);
    this.current.push({ type: "text", x: LEFT + indent, y: this.y, size, font, text: clean(value), gray: 0 });
    this.y -= size <= 10 ? LINE : size + 5;
  }

  gap(amount = 5) {
    this.y -= amount;
  }

  heading(value) {
    this.ensure(3);
    this.text(value, 13, "F2");
    this.gap(3);
  }

  paragraph(value) {
    for (const line of wrapText(value, 96)) this.text(line);
    this.gap(4);
  }

  bullet(value) {
    const lines = wrapText(value, 90);
    this.text(`- ${lines[0]}`, 9, "F1", 10);
    for (const line of lines.slice(1)) this.text(`  ${line}`, 9, "F1", 10);
  }

  rect(x, y, width, height, options = {}) {
    this.current.push({
      type: "rect",
      x,
      y,
      width,
      height,
      fillGray: options.fillGray,
      strokeGray: options.strokeGray ?? 0.78,
    });
  }

  line(x1, y1, x2, y2, gray = 0.78) {
    this.current.push({ type: "line", x1, y1, x2, y2, gray });
  }

  cellText(value, x, y, width, size = 7, font = "F1") {
    const lines = wrapText(value, Math.max(8, Math.floor(width / 4.15)));
    lines.forEach((line, index) => {
      this.current.push({ type: "text", x, y: y - index * (size + 3), size, font, text: clean(line), gray: 0 });
    });
    return lines.length;
  }

  table(rows) {
    if (rows.length < 2) return;
    const columnCount = rows[0].length;
    const tableWidth = PAGE_W - LEFT * 2;
    const widths =
      columnCount === 3
        ? [145, 88, tableWidth - 233]
        : Array.from({ length: columnCount }, () => tableWidth / columnCount);
    const rowGap = 7;
    const headerHeight = 24;
    const drawHeader = () => {
      this.ensureHeight(headerHeight + 8);
      const top = this.y;
      this.rect(LEFT, top - headerHeight, tableWidth, headerHeight, { fillGray: 0.92, strokeGray: 0.55 });
      let x = LEFT;
      rows[0].forEach((cell, index) => {
        if (index > 0) this.line(x, top, x, top - headerHeight, 0.65);
        this.cellText(cell, x + 5, top - 8, widths[index] - 10, 7, "F2");
        x += widths[index];
      });
      this.y -= headerHeight;
    };

    drawHeader();
    for (const row of rows.slice(1)) {
      const lineCounts = row.map((cell, index) => wrapText(cell, Math.max(8, Math.floor((widths[index] - 10) / 4.15))).length);
      const rowHeight = Math.max(24, Math.max(...lineCounts) * 10 + rowGap);
      if (this.y - rowHeight < BOTTOM) drawHeader();
      const top = this.y;
      this.rect(LEFT, top - rowHeight, tableWidth, rowHeight, { strokeGray: 0.78 });
      let x = LEFT;
      row.forEach((cell, index) => {
        if (index > 0) this.line(x, top, x, top - rowHeight, 0.82);
        this.cellText(cell, x + 5, top - 8, widths[index] - 10, 7, index === 1 ? "F2" : "F1");
        x += widths[index];
      });
      this.y -= rowHeight;
    }
    this.gap(8);
  }

  cover() {
    this.newPage();
    this.y = 700;
    this.current.push({ type: "text", x: 70, y: this.y, size: 22, font: "F2", text: "Resumen de estado actual", gray: 0 });
    this.y -= 32;
    this.current.push({ type: "text", x: 70, y: this.y, size: 14, font: "F2", text: "P&Pmis Ai SaaS frente a instructivos Unifier 26", gray: 0 });
    this.y -= 24;
    this.current.push({ type: "text", x: 70, y: this.y, size: 10, font: "F1", text: "Fecha: 14 de mayo de 2026", gray: 0 });
    this.y -= 34;
    this.paragraph("Informe generado con base en los tres instructivos compartidos y en el estado actual de la app levantada localmente.");
    this.newPage();
  }

  renderMarkdown(markdown) {
    const lines = markdown.split(/\r?\n/);
    for (let index = 0; index < lines.length; index += 1) {
      const stripped = lines[index].trim();
      if (!stripped) {
        this.gap(3);
      } else if (stripped.startsWith("# ")) {
        continue;
      } else if (stripped.startsWith("## ")) {
        this.heading(stripped.slice(3));
      } else if (stripped.startsWith("### ")) {
        this.heading(stripped.slice(4));
      } else if (stripped.startsWith("|")) {
        const rows = [];
        while (index < lines.length && lines[index].trim().startsWith("|")) {
          const parts = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((part) => part.trim());
          if (!parts.every((part) => /^[-: ]+$/.test(part))) rows.push(parts);
          index += 1;
        }
        this.table(rows);
        index -= 1;
      } else if (stripped.startsWith("- ")) {
        this.bullet(stripped.slice(2));
      } else if (/^\d+\. /.test(stripped)) {
        this.bullet(stripped.replace(/^\d+\. /, ""));
      } else {
        this.paragraph(stripped);
      }
    }
  }

  finish() {
    if (this.current.length) {
      this.footer();
      this.pages.push(this.current);
      this.current = [];
    }
  }
}

function pdfEscape(value) {
  return clean(value).replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function addObject(objects, body) {
  objects.push(Buffer.isBuffer(body) ? body : Buffer.from(body, "latin1"));
  return objects.length;
}

function buildPdf(doc) {
  doc.finish();
  const objects = [];
  const fontRegular = addObject(objects, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  const fontBold = addObject(objects, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>");
  const contentIds = [];

  for (const page of doc.pages) {
    const chunks = [];
    for (const item of page) {
      if (item.type === "text") {
        chunks.push("BT");
        chunks.push(`${item.gray ?? 0} g`);
        chunks.push(`/${item.font} ${item.size} Tf`);
        chunks.push(`${item.x} ${item.y} Td (${pdfEscape(item.text)}) Tj`);
        chunks.push("ET");
      } else if (item.type === "rect") {
        if (item.fillGray !== undefined) {
          chunks.push(`q ${item.fillGray} g ${item.x} ${item.y} ${item.width} ${item.height} re f Q`);
        }
        chunks.push(`q ${item.strokeGray ?? 0.78} G 0.5 w ${item.x} ${item.y} ${item.width} ${item.height} re S Q`);
      } else if (item.type === "line") {
        chunks.push(`q ${item.gray ?? 0.78} G 0.5 w ${item.x1} ${item.y1} m ${item.x2} ${item.y2} l S Q`);
      }
    }
    const stream = Buffer.from(chunks.join("\n"), "latin1");
    contentIds.push(
      addObject(objects, Buffer.concat([Buffer.from(`<< /Length ${stream.length} >>\nstream\n`, "latin1"), stream, Buffer.from("\nendstream", "latin1")])),
    );
  }

  const pagesId = objects.length + doc.pages.length + 1;
  const pageIds = contentIds.map((contentId) =>
    addObject(
      objects,
      `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources << /Font << /F1 ${fontRegular} 0 R /F2 ${fontBold} 0 R >> >> /Contents ${contentId} 0 R >>`,
    ),
  );
  const kids = pageIds.map((id) => `${id} 0 R`).join(" ");
  addObject(objects, `<< /Type /Pages /Kids [${kids}] /Count ${pageIds.length} >>`);
  const catalogId = addObject(objects, `<< /Type /Catalog /Pages ${pagesId} 0 R >>`);

  const parts = [Buffer.from("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n", "latin1")];
  const offsets = [0];
  for (let index = 0; index < objects.length; index += 1) {
    offsets.push(Buffer.concat(parts).length);
    parts.push(Buffer.from(`${index + 1} 0 obj\n`, "latin1"), objects[index], Buffer.from("\nendobj\n", "latin1"));
  }
  const beforeXref = Buffer.concat(parts);
  const xrefOffset = beforeXref.length;
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) xref += `${String(offset).padStart(10, "0")} 00000 n \n`;
  xref += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.concat([beforeXref, Buffer.from(xref, "latin1")]);
}

const markdown = await readFile(SOURCE, "utf8");
const doc = new PdfDoc();
doc.cover();
doc.renderMarkdown(markdown);
const bytes = buildPdf(doc);
const results = [];
for (const output of OUTPUTS) {
  try {
    await writeFile(output, bytes);
    results.push({ output, status: "written" });
  } catch (error) {
    results.push({ output, status: "error", message: error.message });
  }
}
console.log(JSON.stringify({ pages: doc.pages.length, bytes: bytes.length, results }, null, 2));
