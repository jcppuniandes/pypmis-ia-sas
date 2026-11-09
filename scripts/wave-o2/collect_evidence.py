"""Create traceability data from checked design, prompt clauses and repository evidence."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs/architecture/wave-o2"
QA = ROOT / "outputs/.qa/wave-o2-20261109"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/"
    "PROMPT_WAVE_O2_MASTER_ARCHITECTURE_ENGINEERING_PROCUREMENT_CONTRACTS_V2_SOV_COST_SHEET.md"
)
STATE = "WAVE_O2_MASTER_ARCHITECTURE_VALIDATED"
READY = "READY_FOR_WAVE_O2A_ENGINEERING_FOUNDATION"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def table(text, anchor):
    start = text.index(anchor)
    lines = text[start:].splitlines()
    block = []
    for line in lines:
        if not line.startswith("|"):
            break
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        if not all(re.fullmatch(r"[-:]+", cell) for cell in cells):
            block.append(cells)
    return block[0], block[1:]


def criteria_refs():
    return [
        "D01, D16; O1A y Scope",
        "D15, D16; O2-33",
        "D05, D16; O2-34",
        "D11, D16; O2-35",
        "D16, D20; O2-36",
        "D02; O2-02 a O2-05",
        "D02; O2-29",
        "D03, D04; O2-06 a O2-12",
        "D03; O2-29",
        "D03; O2-07/O2-29",
        "O2-13 a O2-17; diseño O2B",
        "O2-18/O2-19; diseño O2B",
        "O2-20 a O2-25; ADR comercial",
        "D04; O2-20",
        "O2-20/O2-21; ADR comercial",
        "D05; O2-25",
        "D04; V-08",
        "D05; O2-25/O2-27",
        "D06; O2-39",
        "D07/D19; V-01 a V-05",
        "D02; M:N O2-02/O2-29",
        "D03; M:N O2-07/O2-29",
        "O2-13/O2-17/O2-29; V-09",
        "O2-18/O2-19/O2-29; V-09",
        "O2-21/O2-24/O2-29; ADR comercial",
        "D14; O2-31/O2-32; V-09",
        "D15/D16; O2-33",
        "D05/D16; O2-28/O2-34",
        "D11/D16; O2-35",
        "D16/D20; O2-36",
        "D12; O2-37; resolución condicional antes de O2B",
        "D13; O2-38",
        "D17; roadmap ADMIN/USER",
        "D17; matriz de roles, V-03/V-08",
        "D17; taxonomía de eventos del roadmap",
        "Roadmap O2A",
        "Roadmap O2B",
        "Roadmap O2C",
        "Roadmap O2D",
        "preservation.json: dos lecturas actuales",
        "Decisions: revisión cruzada sin S1 abiertos",
        "Decisions: revisión cruzada sin S2 abiertos",
        "O2-23; ADR comercial",
        "O2-24; ADR comercial",
        "D08; O2-21/O2-24",
        "D09; V-04",
        "ADR comercial: monto LUMP_SUM",
        "ADR comercial: UNIT_RATE; V-06",
        "D10; O2-28",
        "O2-23/O2-28; D10",
        "D07/D10; V-01/V-07",
        "D10; V-07",
        "O2-24/O2-28; V-07",
        "D08; O2-24/O2-29/O2-30",
        "D11; O2-26/O2-35; V-06",
        "D11; O2-26; futura autoridad fuera de O2",
        "D07/D19; V-01 a V-07",
    ]


def requirement_ref(key):
    number = int(re.match(r"\d+", key).group())
    if key.startswith("24") and len(key) > 2:
        return (
            "08_SOV_Cost_Sheet",
            "ADR comercial §§ Instrumentos y Conciliación; O2-23 a O2-28",
        )
    if number in (0, 1, 2, 44, 45):
        return (
            "02_Domain_Map",
            "Mapa de autoridades O2; siete manifiestos O1 y preservation.json",
        )
    if number in range(3, 8):
        return "03_Engineering", "Diseño O2A; D02 y registros O2-01 a O2-05"
    if number in range(8, 12) or number in (19, 23, 42):
        return "04_Procurement", "Diseño O2B y ADR comercial; D03/D04 y V-08"
    if number in range(12, 16):
        return "05_Materials", "Diseño Materiales; O2-13 a O2-17; V-09"
    if number in (16, 17):
        return "06_Logistics", "Diseño Logística; O2-18/O2-19 y V-09"
    if number in (18, 21, 22, 24, 25, 27):
        return "07_Contracts", "ADR comercial; O2-20 a O2-26; V-01 a V-06"
    if number in (20, 26):
        return "09_Commitments", "ADR comercial; D05/D06/D07/D19 y V-01 a V-05"
    if number == 28:
        return "10_AWP_Integration", "Diseño O2D; D02/D03/D14 y O2-29 a O2-32"
    if number in (29, 30, 43):
        return (
            "11_Readiness",
            "Contrato de evidencia, separación de restricciones y V-09",
        )
    if number in range(31, 35):
        return "12_Schedule_Cost", "Límites de integración D15/D16/D20; O2-33 a O2-36"
    if number in (35, 36, 40, 41):
        return (
            "15_Duplication_Risks",
            "Inventarios de fuentes, D12/D13/D19; adaptación sin duplicar",
        )
    if number == 37:
        return "13_Admin_User", "Roadmap ADMIN/USER y publicación; D17"
    if number in (38, 39):
        return "14_Security", "Matriz SoD, contratos de comando y auditoría; D17"
    if number in (46, 47, 49, 54, 55):
        return (
            "17_Roadmap",
            "Cuatro gates futuros, límites de implementación y plan de escala",
        )
    if number in (48, 52, 53):
        return (
            "19_Release_Criteria",
            "57 criterios con referencias; comparación read-only de Project 14",
        )
    assert number in (50, 51, 56), number
    return (
        "18_Decisions",
        "37 rótulos numerados en el adjunto, 39 títulos efectivos; Word, 19 hojas y cierre",
    )


def main():
    text = PROMPT.read_text("utf-8")
    matches = list(re.finditer(r"^#{1,2} (\d+[A-P]?)\. (.+)$", text, re.MULTILINE))
    requirements = [[f"§{m[1]}", m[2], *requirement_ref(m[1])] for m in matches]
    assert len(requirements) == 73
    sections = {
        m[1]: text[
            m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)
        ]
        for i, m in enumerate(matches)
    }
    clauses = [
        (section, label)
        for section in ("52", "24P")
        for label in re.findall(r"^(.+?) = PASS$", sections[section], re.MULTILINE)
    ]
    refs = criteria_refs()
    assert len(clauses) == len(refs) == 57
    criteria = [
        [f"AC-{i:02}", f"§{section}", label, "PASS DISEÑO", ref]
        for i, ((section, label), ref) in enumerate(zip(clauses, refs, strict=True), 1)
    ]
    names = [
        m for m in re.findall(r"^(\d{2}_[A-Za-z_]+)$", sections["51"], re.MULTILINE)
    ]
    assert len(names) == len(set(names)) == 19
    baseline = read(ARCH / "preservation.json")
    checks = read(ARCH / "design-checks.json")
    assert baseline["result"] == checks["result"] == "PASS"
    assert len(baseline["o1_baselines"]) == 7 and len(checks["cases"]) == 9
    domain = (ARCH / "domain-map.md").read_text("utf-8")
    commercial = (ARCH / "commercial-sov-cost-sheet.md").read_text("utf-8")
    epc = (ARCH / "engineering-procurement-awp.md").read_text("utf-8")
    roadmap = (ARCH / "implementation-roadmap.md").read_text("utf-8")
    decisions = (ARCH / "decisions.md").read_text("utf-8")
    domain_h, domain_r = table(domain, "| ID | Objeto")
    decision_h, decision_r = table(decisions, "| ID | Riesgo")
    assert len(domain_r) == 40 and all(len(row) == 10 for row in domain_r)
    assert len(decision_r) == 20 and all(len(row) == 4 for row in decision_r)
    assert len({row[0] for row in domain_r}) == len(domain_r)
    assert len({row[1] for row in domain_r}) == len(domain_r)
    assert all(
        row[2] == row[6] == "Contracts"
        for row in domain_r
        if row[0] in {"O2-20", "O2-21", "O2-22", "O2-23", "O2-24", "O2-25"}
    )
    for filename, source in (
        ("roadmap", roadmap),
        ("comercial", commercial),
        ("EPC", epc),
    ):
        for relative in re.findall(r"\]\((\.\.?/[^)]+)\)", source):
            assert (ARCH / relative).is_file(), (filename, relative)
    api_h, api_r = table(roadmap, "| Dominio | Lecturas")
    sec_h, sec_r = table(roadmap, "| Dominio | Acciones")
    readiness_h, readiness_r = table(epc, "| Categoría futura")
    inclusion_h, inclusion_r = table(commercial, "| Modo | Efecto")
    assert len(api_r) == 7 and len(readiness_r) == 6 and len(inclusion_r) == 4

    def subset(ids):
        selected = [row for row in domain_r if int(row[0][-2:]) in ids]
        return [
            [row[0], row[1], row[2], row[3], row[5], row[7], row[8], row[9]]
            for row in selected
        ]

    compact_h = [
        "ID",
        "Objeto",
        "Dueño",
        "Clave",
        "Ciclo",
        "Entrada",
        "Consumo",
        "Protección y enlaces",
    ]
    compact_w = [12, 29, 20, 30, 43, 37, 31, 54]
    specs = []

    def add(title, headers, widths, rows):
        assert rows and len(headers) == len(widths)
        assert all(len(row) == len(headers) for row in rows), title
        specs.append(
            {
                "name": names[len(specs)],
                "title": title,
                "headers": headers,
                "widths": widths,
                "rows": rows,
            }
        )

    add(
        "Requisitos y trazabilidad de Wave O2",
        ["Cláusula", "Requisito", "Hoja", "Evidencia de diseño"],
        [13, 55, 29, 75],
        requirements,
    )
    add(
        "Mapa de objetos y autoridades",
        domain_h,
        [12, 27, 20, 32, 12, 39, 27, 37, 29, 53],
        domain_r,
    )
    for title, ids in (
        ("Entregables técnicos y revisiones", range(1, 6)),
        ("Sourcing requisiciones y adjudicación", [*range(6, 13), 40]),
        ("Requisitos y disponibilidad de materiales", range(13, 18)),
        ("Envíos tramos y entregas", range(18, 20)),
        ("Instrumentos y obligaciones legales", range(20, 27)),
    ):
        add(title, compact_h, compact_w, subset(ids))
    add(
        "SOV y Project Cost Sheet",
        ["Caso", "Control de diseño", "Resultado", "Evidencia"],
        [14, 40, 20, 95],
        [
            [
                "SOV-01",
                "Revisión actual y original",
                "DISEÑO",
                "Contracts O2-23. Vigencia, moneda, aprobación y ETag; cambios mediante sucesor inmutable.",
            ],
            [
                "SOV-02",
                "Bases comerciales",
                "DISEÑO",
                "LUMP_SUM declara monto. UNIT_RATE fija cantidad, unidad y tarifa, y conserva saldos de cantidad.",
            ],
            [
                "SOV-03",
                "Línea contractual y SOV Line",
                "DISEÑO",
                "Puente N:N por revisión, participación, moneda y cobertura. Las referencias técnicas no distribuyen dinero.",
            ],
            [
                "SOV-04",
                "Project Cost Sheet por dimensión",
                "DISEÑO",
                "Cost lee Budget, compromiso, Actual, accrual y Forecast. CBS, Cost Code y Control Account; residual UNALLOCATED.",
            ],
            [
                "SOV-05",
                "Certificación futura por línea",
                "DISEÑO",
                "Atribuir previo, actual y acumulado, retención y saldo al evento fuente. No crea factura, pago, Actual ni avance.",
            ],
            *checks["cases"][:7],
        ],
    )
    add("Reglas de inclusión económica", inclusion_h, [20, 60, 96], inclusion_r)
    add(
        "Integración de fuentes EPC con AWP",
        compact_h,
        compact_w,
        subset([2, 7, 17, 19, 24, 29, 30, 31, 32]),
    )
    add("Evidencia necesaria para Readiness", readiness_h, [23, 78, 77], readiness_r)
    add(
        "Límites de Schedule Cost Progress y Forecast",
        compact_h,
        compact_w,
        subset([27, 28, 33, 34, 35, 36]),
    )
    add(
        "Publicación ADMIN y operación USER",
        ["Modo", "Contenido", "Autoridad y control"],
        [15, 70, 88],
        [
            [
                "ADMIN",
                "Catálogos EPC, tipos, métodos, criterios, vigencia, inclusión y evidencia",
                "Perfil del dominio, revisión publicada por actor independiente y herencia verificable",
            ],
            [
                "ADMIN",
                "Aplicabilidad por paquete, autorizaciones, workflow y SoD",
                "Publicar no activa proyecto, transacciones, ni asignaciones de usuario",
            ],
            [
                "USER",
                "Entregables, expedientes, material, envíos, contratos y SOV",
                "Workspace activo y permiso por comando. UI muestra solo acciones aplicables",
            ],
            [
                "USER",
                "Cost Sheet, trazabilidad, evaluación y release",
                "Costo y AWP conservan la autoridad. Leer no escribe ni libera",
            ],
        ],
    )
    add("Permisos y separación de funciones", sec_h, [22, 80, 82], sec_r)
    add(
        "Riesgos de duplicación y tratamiento", decision_h, [12, 46, 88, 65], decision_r
    )
    add("Contratos API previstos", api_h, [24, 72, 76, 64], api_r)
    gates = []
    for m in re.finditer(
        r"^### (O2[A-D]) (.+)\n\n((?:- .+\n)+)", roadmap, re.MULTILINE
    ):
        for row in m[3].splitlines():
            category, value = re.match(r"- \*\*(.+?):\*\* (.+)", row).groups()
            gates.append([m[1], m[2], category, value])
    assert len(gates) == 16
    add(
        "Hoja de ruta con pruebas y salidas futuras",
        ["Ola", "Incremento", "Dimensión", "Diseño y gate de implementación"],
        [12, 40, 29, 108],
        gates,
    )
    add(
        "Decisiones y estado de la arquitectura",
        decision_h,
        [12, 46, 88, 65],
        [
            *decision_r,
            [
                "C01",
                "Estado de arquitectura",
                STATE,
                "57 criterios de diseño, sin ejecución de módulos O2",
            ],
            [
                "C02",
                "Único siguiente incremento",
                "WAVE O2A — ENGINEERING FOUNDATION",
                READY,
            ],
        ],
    )
    add(
        "Criterios de aceptación de arquitectura",
        ["ID", "Cláusula", "Criterio", "Resultado", "Prueba o referencia"],
        [12, 11, 58, 19, 74],
        criteria,
    )
    assert len(specs) == 19
    inputs = [
        "domain-map.md",
        "decisions.md",
        "commercial-sov-cost-sheet.md",
        "engineering-procurement-awp.md",
        "implementation-roadmap.md",
        "preservation.json",
        "design-checks.json",
    ]
    package = {
        "release_state": STATE,
        "final_output": READY,
        "baseline": baseline,
        "proof": checks,
        "sheets": specs,
        "criteria_count": len(criteria),
        "source_sha256": {name: digest(ARCH / name) for name in inputs},
        "prompt_sha256": digest(PROMPT),
    }
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "package-data.json").write_text(
        json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "requirements": len(requirements),
                "criteria": len(criteria),
                "objects": len(domain_r),
                "sheets": len(specs),
            }
        )
    )


if __name__ == "__main__":
    main()
