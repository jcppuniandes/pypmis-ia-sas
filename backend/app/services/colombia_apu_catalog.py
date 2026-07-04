from __future__ import annotations

import html
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import ColombiaApuCatalogItem, QuantityTakeoffLine

DATACAUCA_SOURCE_KEY = "datacauca_public_apu"
DATACAUCA_SOURCE_URL = "https://datacauca.gov.co/apu/apu/apu/query"
INVIAS_SOURCE_KEY = "invias_reference_apu"
INVIAS_SOURCE_URL = "https://hermes.invias.gov.co/arcgis/rest/services/SEIV_GEIV/APUs/FeatureServer/1/query"
IDU_SOURCE_KEY = "idu_reference_apu"
IDU_SOURCE_URL = "https://www.idu.gov.co/page/siipviales/economico/portafolio"
PUBLIC_LICENSE_NOTE = "Fuente publica gratuita; validar vigencia y oficialidad antes de aprobar presupuesto."
PUBLIC_UPDATE_FREQUENCY = "Public source / manual or scheduled sync"
INVIAS_LICENSE_NOTE = (
    "APU regionalizados de referencia INVIAS; validar provincia, especificacion, transporte, AIU y vigencia."
)
IDU_LICENSE_NOTE = (
    "Precios unitarios de referencia IDU; validar aplicabilidad para Bogota, vigencia, AIU y condiciones del proyecto."
)
INVIAS_UPDATE_FREQUENCY = "INVIAS ArcGIS public reference / manual sync"
IDU_UPDATE_FREQUENCY = "IDU public reference / manual sync"
STARTER_SOURCE_KEY = "local_starter_colombia_apu"
STARTER_SOURCE_URL = "local://colombia-apu-starter"
STARTER_LICENSE_NOTE = (
    "Catalogo starter local gratuito; reemplazar o validar contra fuente oficial/publica antes de aprobar presupuesto."
)
STARTER_UPDATE_FREQUENCY = "Local starter / sync public source when network is available"


@dataclass(frozen=True)
class ApuSuggestion:
    line_id: int
    catalog_item_id: int
    source_key: str
    cost_item_code: str
    cost_item_name: str
    budget_unit: str
    unit_rate: float
    currency: str
    quantity: float
    budget_amount: float
    match_score: float
    review_note: str
    source_url: str
    license_note: str
    apu_structure: list[dict[str, Any]]
    structure_note: str
    structure_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "catalog_item_id": self.catalog_item_id,
            "source_key": self.source_key,
            "cost_item_code": self.cost_item_code,
            "cost_item_name": self.cost_item_name,
            "budget_unit": self.budget_unit,
            "unit_rate": self.unit_rate,
            "currency": self.currency,
            "quantity": self.quantity,
            "budget_amount": self.budget_amount,
            "match_score": self.match_score,
            "review_note": self.review_note,
            "source_url": self.source_url,
            "license_note": self.license_note,
            "apu_structure": self.apu_structure,
            "structure_note": self.structure_note,
            "structure_status": self.structure_status,
        }


class ColombiaApuCatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_public_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for fetcher in (self._fetch_datacauca_rows, self._fetch_invias_rows, self._fetch_idu_rows):
            try:
                rows.extend(fetcher(limit=limit))
            except (httpx.HTTPError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
                continue
        return rows if rows else _starter_rows()[:limit]

    def _fetch_datacauca_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while len(rows) < limit:
            try:
                response = httpx.get(
                    DATACAUCA_SOURCE_URL,
                    params={"page": page},
                    timeout=20,
                    follow_redirects=True,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                break
            page_rows = _parse_datacauca_rows(response.text)
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < 20:
                break
            page += 1
        return rows[:limit]

    def _fetch_invias_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        response = httpx.get(
            INVIAS_SOURCE_URL,
            params={
                "where": "1=1",
                "outFields": "id_apu,item_,descripcion__,unidad__,costo_total__,territorial",
                "returnGeometry": "false",
                "f": "json",
                "resultRecordCount": max(1, min(limit, 10000)),
                "resultOffset": 0,
            },
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()
        rows: list[dict[str, Any]] = []
        for feature in data.get("features") or []:
            attributes = feature.get("attributes") or {}
            item_code = _clean_text(attributes.get("item_") or "")
            item_name = _clean_text(attributes.get("descripcion__") or "")
            unit = _clean_text(attributes.get("unidad__") or "")
            region = _clean_text(attributes.get("territorial") or "Colombia")
            if not item_code or not item_name or not unit:
                continue
            rows.append(
                {
                    "code": item_code,
                    "name": item_name,
                    "unit": unit,
                    "group": f"INVIAS / {region}",
                    "chapter": _invias_chapter(item_code),
                    "region": region,
                    "price": attributes.get("costo_total__") or 0,
                    "source_key": INVIAS_SOURCE_KEY,
                    "source_url": INVIAS_SOURCE_URL,
                    "license_note": INVIAS_LICENSE_NOTE,
                    "update_frequency": INVIAS_UPDATE_FREQUENCY,
                    "apu_structure": [
                        {
                            "component": "Costo directo",
                            "code": item_code,
                            "description": item_name,
                            "quantity": 1,
                            "unit": unit,
                            "unit_rate": attributes.get("costo_total__") or 0,
                            "amount": attributes.get("costo_total__") or 0,
                        }
                    ],
                    "structure_note": (
                        "Indice APU INVIAS. Componentes oficiales relacionados: mano de obra, materiales y transporte."
                    ),
                    "id_apu": attributes.get("id_apu"),
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def _fetch_idu_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        # The official IDU page publishes the current reference-price viewer. If the
        # environment cannot resolve/download the workbook, keep a structured local
        # starter so the catalog still exposes the IDU source and hierarchy.
        return _idu_starter_rows()[:limit]

    def sync_public_catalog(self, tenant_id: int, project_id: int, limit: int = 500) -> dict[str, Any]:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        source_keys: set[str] = set()
        source_urls: set[str] = set()
        license_notes: set[str] = set()
        update_frequencies: set[str] = set()
        rows = self.fetch_public_rows(limit=limit)
        synced_at = utc_now()
        for raw_row in rows:
            normalized = _normalize_public_row(raw_row)
            if not normalized:
                skipped_count += 1
                continue
            source_keys.add(normalized["source_key"])
            source_urls.add(normalized["source_url"])
            license_notes.add(normalized["license_note"])
            update_frequencies.add(normalized["update_frequency"])
            existing = self.db.scalar(
                select(ColombiaApuCatalogItem).where(
                    ColombiaApuCatalogItem.tenant_id == tenant_id,
                    ColombiaApuCatalogItem.project_id == project_id,
                    ColombiaApuCatalogItem.source_key == normalized["source_key"],
                    ColombiaApuCatalogItem.external_id == normalized["external_id"],
                )
            )
            if existing:
                updated_count += 1
                item = existing
            else:
                created_count += 1
                item = ColombiaApuCatalogItem(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_key=normalized["source_key"],
                    external_id=normalized["external_id"],
                    item_code=normalized["item_code"],
                )
                self.db.add(item)
            item.item_code = normalized["item_code"]
            item.item_name = normalized["item_name"]
            item.unit = normalized["unit"]
            item.unit_rate = normalized["unit_rate"]
            item.currency = normalized["currency"]
            item.group_name = normalized["group_name"]
            item.chapter = normalized["chapter"]
            item.region = normalized["region"]
            item.source_url = normalized["source_url"]
            item.license_note = normalized["license_note"]
            item.update_frequency = normalized["update_frequency"]
            item.status = "review"
            item.raw_data = {
                **_clean_row(_with_apu_resource_structure(raw_row, normalized)),
                "synced_at": synced_at.isoformat(),
            }
            item.updated_at = synced_at
        self.db.flush()
        total_count = self.db.scalar(
            select(func.count(ColombiaApuCatalogItem.id)).where(
                ColombiaApuCatalogItem.tenant_id == tenant_id,
                ColombiaApuCatalogItem.project_id == project_id,
            )
        )
        if total_count is None:
            total_count = len(rows) - skipped_count
        source_key = " + ".join(sorted(source_keys)) if source_keys else DATACAUCA_SOURCE_KEY
        source_url = sorted(source_urls)[0] if len(source_urls) == 1 else "multiple://colombia-apu-public-sources"
        license_note = (
            sorted(license_notes)[0]
            if len(license_notes) == 1
            else "Fuentes publicas de referencia; validar vigencia, region, AIU, alcance y aplicabilidad antes de aprobar."
        )
        update_frequency = (
            sorted(update_frequencies)[0] if len(update_frequencies) == 1 else "Manual sync / public reference sources"
        )
        return {
            "project_id": project_id,
            "source_key": source_key,
            "source_url": source_url,
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "total_count": int(total_count),
            "license_note": license_note,
            "update_frequency": update_frequency,
            "synced_at": synced_at,
        }

    def list_items(
        self,
        tenant_id: int,
        project_id: int,
        search: str = "",
        limit: int = 50,
        source_key: str = "",
    ) -> list[ColombiaApuCatalogItem]:
        stmt = select(ColombiaApuCatalogItem).where(
            ColombiaApuCatalogItem.tenant_id == tenant_id,
            ColombiaApuCatalogItem.project_id == project_id,
        )
        if source_key:
            stmt = stmt.where(ColombiaApuCatalogItem.source_key == source_key)
        terms = [term for term in _tokens(search) if len(term) >= 2]
        if terms:
            clauses = []
            for term in terms:
                like = f"%{term}%"
                clauses.extend(
                    [
                        ColombiaApuCatalogItem.item_code.ilike(like),
                        ColombiaApuCatalogItem.item_name.ilike(like),
                        ColombiaApuCatalogItem.chapter.ilike(like),
                        ColombiaApuCatalogItem.group_name.ilike(like),
                    ]
                )
            stmt = stmt.where(or_(*clauses))
        return list(
            self.db.scalars(stmt.order_by(ColombiaApuCatalogItem.item_code).limit(max(1, min(limit, 200)))).all()
        )

    def suggest_for_lines(
        self,
        tenant_id: int,
        project_id: int,
        lines: list[QuantityTakeoffLine],
        apply_best: bool = False,
        limit_per_line: int = 3,
    ) -> list[ApuSuggestion]:
        catalog = list(
            self.db.scalars(
                select(ColombiaApuCatalogItem)
                .where(
                    ColombiaApuCatalogItem.tenant_id == tenant_id,
                    ColombiaApuCatalogItem.project_id == project_id,
                    ColombiaApuCatalogItem.status != "inactive",
                )
                .order_by(ColombiaApuCatalogItem.item_code)
            ).all()
        )
        suggestions: list[ApuSuggestion] = []
        for line in lines:
            line_suggestions = _rank_suggestions(line, catalog)[:limit_per_line]
            suggestions.extend(line_suggestions)
            if apply_best and line_suggestions:
                best = line_suggestions[0]
                raw_data = dict(line.raw_data or {})
                raw_data["apu_suggestion"] = {
                    "apu_structure": best.apu_structure,
                    "budget_amount": best.budget_amount,
                    "budget_unit": best.budget_unit,
                    "catalog_item_id": best.catalog_item_id,
                    "cost_item_code": best.cost_item_code,
                    "cost_item_name": best.cost_item_name,
                    "currency": best.currency,
                    "license_note": best.license_note,
                    "line_id": best.line_id,
                    "match_score": best.match_score,
                    "quantity": best.quantity,
                    "review_note": best.review_note,
                    "source_key": best.source_key,
                    "source_url": best.source_url,
                    "status": "suggested",
                    "structure_note": best.structure_note,
                    "structure_status": best.structure_status,
                    "suggested_at": utc_now().isoformat(),
                    "unit_rate": best.unit_rate,
                }
                line.raw_data = raw_data
                line.updated_at = utc_now()
        self.db.flush()
        return suggestions


def _starter_rows() -> list[dict[str, Any]]:
    starter_items = [
        ("COL-CON-MURO-001", "Muro en concreto reforzado", "m2", "Concreto", "Muros"),
        ("COL-CON-LOSA-001", "Losa maciza en concreto reforzado", "m2", "Concreto", "Losas"),
        ("COL-CON-VIGA-001", "Viga en concreto reforzado", "m3", "Concreto", "Vigas"),
        ("COL-CON-COL-001", "Columna en concreto reforzado", "m3", "Concreto", "Columnas"),
        ("COL-ACE-REF-001", "Acero de refuerzo figurado e instalado", "kg", "Acero", "Estructura"),
        ("COL-MAM-BLO-001", "Mamposteria en bloque", "m2", "Mamposteria", "Muros"),
        ("COL-MOV-EXC-001", "Excavacion en material comun", "m3", "Movimiento de tierras", "Excavaciones"),
        ("COL-HID-PVC-001", "Tuberia PVC instalada", "m", "Hidrosanitaria", "Tuberias"),
        ("COL-ARQ-PUE-001", "Puerta instalada", "ea", "Arquitectura", "Puertas"),
        ("COL-ARQ-VEN-001", "Ventana instalada", "m2", "Arquitectura", "Ventanas"),
    ]
    return [
        {
            "code": code,
            "name": name,
            "unit": unit,
            "group": group,
            "chapter": chapter,
            "region": "Colombia / revisar region",
            "price": 0,
            "source_key": STARTER_SOURCE_KEY,
            "source_url": STARTER_SOURCE_URL,
            "license_note": STARTER_LICENSE_NOTE,
            "update_frequency": STARTER_UPDATE_FREQUENCY,
        }
        for code, name, unit, group, chapter in starter_items
    ]


def _idu_starter_rows() -> list[dict[str, Any]]:
    starter_items = [
        ("IDU-ESP-PUB-001", "Anden en concreto", "m2", "Espacio publico", "Andenes", "Bogota D.C.", 0),
        (
            "IDU-VIA-PAV-001",
            "Carpeta asfaltica en caliente",
            "m3",
            "Pavimentos",
            "Mezclas asfalticas",
            "Bogota D.C.",
            0,
        ),
        ("IDU-VIA-DEM-001", "Demolicion de placa en concreto", "m2", "Demoliciones", "Pavimentos", "Bogota D.C.", 0),
        ("IDU-RED-SUM-001", "Sumidero vial", "un", "Redes", "Drenaje", "Bogota D.C.", 0),
        ("IDU-SEN-HOR-001", "Senalizacion horizontal", "m2", "Senalizacion", "Demarcacion", "Bogota D.C.", 0),
        ("IDU-MOB-BOR-001", "Bordillo prefabricado", "m", "Espacio publico", "Bordillos", "Bogota D.C.", 0),
    ]
    return [
        {
            "code": code,
            "name": name,
            "unit": unit,
            "group": f"IDU / {group}",
            "chapter": chapter,
            "region": region,
            "price": price,
            "source_key": IDU_SOURCE_KEY,
            "source_url": IDU_SOURCE_URL,
            "license_note": IDU_LICENSE_NOTE,
            "update_frequency": IDU_UPDATE_FREQUENCY,
            "apu_structure": [
                {
                    "component": "Costo directo",
                    "code": code,
                    "description": name,
                    "quantity": 1,
                    "unit": unit,
                    "unit_rate": price,
                    "amount": price,
                }
            ],
            "structure_note": "Catalogo IDU visible con estructura base; validar contra visor oficial vigente antes de aprobar.",
        }
        for code, name, unit, group, chapter, region, price in starter_items
    ]


def _parse_datacauca_rows(content: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in re.finditer(r"<tr[^>]*>(.*?)</tr>", content, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            _clean_text(html.unescape(re.sub(r"<[^>]+>", " ", cell)))
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", match.group(1), flags=re.IGNORECASE | re.DOTALL)
        ]
        cells = [re.sub(r"\s+", " ", cell) for cell in cells if cell]
        if len(cells) < 7:
            continue
        rows.append(
            {
                "code": cells[0],
                "name": cells[1],
                "unit": cells[2],
                "group": cells[3],
                "chapter": cells[4],
                "region": cells[5],
                "price": cells[6],
                "source_url": DATACAUCA_SOURCE_URL,
            }
        )
    return rows


def _normalize_public_row(row: dict[str, Any]) -> dict[str, Any] | None:
    source_key = str(row.get("source_key") or DATACAUCA_SOURCE_KEY).strip()
    item_code = _clean_text(row.get("code") or row.get("item_code") or "")
    item_name = _clean_text(row.get("name") or row.get("item_name") or "")
    unit = _clean_text(row.get("unit") or row.get("unidad") or "")
    unit_rate = _money(row.get("price") or row.get("unit_rate") or row.get("precio"))
    if not item_code or not item_name or not unit or unit_rate < 0:
        return None
    external_id = f"{source_key}:{item_code}:{_compact(row.get('region') or '')}"
    return {
        "source_key": source_key,
        "external_id": external_id,
        "item_code": item_code,
        "item_name": item_name,
        "unit": unit,
        "unit_rate": unit_rate,
        "currency": "COP",
        "group_name": _clean_text(row.get("group") or ""),
        "chapter": _clean_text(row.get("chapter") or ""),
        "region": _clean_text(row.get("region") or ""),
        "source_url": _clean_text(row.get("source_url") or DATACAUCA_SOURCE_URL),
        "license_note": _clean_text(row.get("license_note") or PUBLIC_LICENSE_NOTE),
        "update_frequency": _clean_text(row.get("update_frequency") or PUBLIC_UPDATE_FREQUENCY),
    }


def _with_apu_resource_structure(row: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    current_structure = row.get("apu_structure")
    if isinstance(current_structure, list) and len(current_structure) > 1:
        return row
    enriched = dict(row)
    enriched["apu_structure"] = _resource_apu_structure(normalized)
    enriched["structure_note"] = _resource_structure_note(normalized)
    enriched["structure_status"] = "review_required"
    return enriched


def _resource_apu_structure(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    item_name = str(normalized.get("item_name") or "")
    group_name = str(normalized.get("group_name") or "")
    chapter = str(normalized.get("chapter") or "")
    unit = str(normalized.get("unit") or "und")
    amount = float(normalized.get("unit_rate") or 0)
    profile = _resource_profile(" ".join([item_name, group_name, chapter]))
    lines: list[dict[str, Any]] = []
    for component_type, ratio in profile:
        component_amount = round(amount * ratio, 2)
        lines.append(
            {
                "amount": component_amount,
                "code": f"{normalized.get('item_code', '')}-{component_type}",
                "component": _resource_component_label(component_type),
                "component_type": component_type,
                "description": _resource_component_description(component_type, item_name),
                "quantity": 1,
                "source": "estimated_resource_split",
                "status": "review",
                "unit": unit,
                "unit_rate": component_amount,
            }
        )
    return lines


def _resource_profile(text: str) -> list[tuple[str, float]]:
    normalized = _compact(text)
    if any(token in normalized for token in ("excavacion", "demolicion", "desmonte", "limpieza", "retiro", "cargue")):
        return [("LABOR", 0.25), ("MATERIAL", 0.05), ("EQUIPMENT", 0.55), ("TRANSPORT", 0.15)]
    if any(token in normalized for token in ("tuberia", "tubo", "codo", "valvula", "accesorio", "suministro")):
        return [("LABOR", 0.2), ("MATERIAL", 0.7), ("EQUIPMENT", 0.05), ("TRANSPORT", 0.05)]
    if any(token in normalized for token in ("concreto", "losa", "muro", "bordillo", "anden", "pavimento")):
        return [("LABOR", 0.25), ("MATERIAL", 0.55), ("EQUIPMENT", 0.15), ("TRANSPORT", 0.05)]
    if any(token in normalized for token in ("senalizacion", "demarcacion", "pintura")):
        return [("LABOR", 0.25), ("MATERIAL", 0.6), ("EQUIPMENT", 0.1), ("TRANSPORT", 0.05)]
    return [("LABOR", 0.35), ("MATERIAL", 0.45), ("EQUIPMENT", 0.15), ("TRANSPORT", 0.05)]


def _resource_component_label(component_type: str) -> str:
    labels = {
        "EQUIPMENT": "Equipo y herramienta",
        "LABOR": "Mano de obra",
        "MATERIAL": "Materiales",
        "TRANSPORT": "Transporte",
    }
    return labels.get(component_type, component_type)


def _resource_component_description(component_type: str, item_name: str) -> str:
    labels = {
        "EQUIPMENT": f"Equipo, herramienta menor o maquinaria asociada a {item_name}",
        "LABOR": f"Cuadrilla y rendimiento para ejecutar {item_name}",
        "MATERIAL": f"Insumos/materiales principales para {item_name}",
        "TRANSPORT": f"Transporte, acarreos o movilizacion asociada a {item_name}",
    }
    return labels.get(component_type, item_name)


def _resource_structure_note(normalized: dict[str, Any]) -> str:
    source_key = str(normalized.get("source_key") or "")
    if source_key == INVIAS_SOURCE_KEY:
        return (
            "Estructura de recursos estimada desde el costo directo INVIAS. Validar contra componentes oficiales "
            "de mano de obra, materiales, equipos y transporte antes de aprobar."
        )
    if source_key == IDU_SOURCE_KEY:
        return (
            "Estructura de recursos estimada para visor IDU. Debe reemplazarse por el Excel/visor oficial vigente "
            "antes de aprobar presupuesto."
        )
    return (
        "Estructura de recursos estimada para revision. Validar composicion APU, rendimientos, desperdicios, "
        "transporte, AIU y vigencia regional antes de aprobar."
    )


def _invias_chapter(item_code: str) -> str:
    prefix = _clean_text(item_code).split(".", maxsplit=1)[0]
    chapters = {
        "100": "Preliminares",
        "200": "Explanaciones",
        "300": "Afirmados, subbases y bases",
        "400": "Pavimentos asfalticos",
        "500": "Pavimentos en concreto",
        "600": "Estructuras y drenaje",
        "700": "Senalizacion y seguridad",
        "800": "Ambiente y obras complementarias",
    }
    return chapters.get(prefix, f"INVIAS item {prefix}" if prefix else "INVIAS APU")


def _rank_suggestions(line: QuantityTakeoffLine, catalog: list[ColombiaApuCatalogItem]) -> list[ApuSuggestion]:
    line_terms = _line_terms(line)
    line_unit = _unit_key(_controlled_unit(line))
    quantity = _controlled_quantity(line)
    ranked: list[tuple[float, ColombiaApuCatalogItem]] = []
    for item in catalog:
        item_terms = _tokens(" ".join([item.item_name, item.chapter, item.group_name]))
        if not item_terms:
            continue
        overlap = len(line_terms & item_terms)
        score = overlap * 18
        if _unit_key(item.unit) == line_unit and line_unit:
            score += 35
        if _ifc_hint(line.ifc_class) & item_terms:
            score += 20
        if _compact(line.category) and _compact(line.category) in _compact(item.item_name):
            score += 10
        if score <= 0:
            continue
        ranked.append((min(score, 100), item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].item_code))
    return [
        ApuSuggestion(
            line_id=line.id,
            catalog_item_id=item.id,
            source_key=item.source_key,
            cost_item_code=item.item_code,
            cost_item_name=item.item_name,
            budget_unit=item.unit,
            unit_rate=float(item.unit_rate or 0),
            currency=item.currency or "COP",
            quantity=quantity,
            budget_amount=round(quantity * float(item.unit_rate or 0), 2),
            match_score=round(score, 2),
            review_note=(
                "Sugerencia automatica desde catalogo APU Colombia; validar alcance, rendimiento, AIU y vigencia regional."
            ),
            source_url=item.source_url,
            license_note=item.license_note,
            apu_structure=_catalog_item_apu_structure(item),
            structure_note=_catalog_item_structure_note(item),
            structure_status=_catalog_item_structure_status(item),
        )
        for score, item in ranked
    ]


def _catalog_item_apu_structure(item: ColombiaApuCatalogItem) -> list[dict[str, Any]]:
    raw_structure = (item.raw_data or {}).get("apu_structure")
    if isinstance(raw_structure, list):
        return [dict(line) for line in raw_structure if isinstance(line, dict)]
    normalized = {
        "chapter": item.chapter,
        "group_name": item.group_name,
        "item_code": item.item_code,
        "item_name": item.item_name,
        "source_key": item.source_key,
        "unit": item.unit,
        "unit_rate": float(item.unit_rate or 0),
    }
    return _resource_apu_structure(normalized)


def _catalog_item_structure_note(item: ColombiaApuCatalogItem) -> str:
    note = (item.raw_data or {}).get("structure_note")
    if isinstance(note, str) and note.strip():
        return note.strip()
    return _resource_structure_note(
        {
            "source_key": item.source_key,
            "item_name": item.item_name,
            "group_name": item.group_name,
            "chapter": item.chapter,
        }
    )


def _catalog_item_structure_status(item: ColombiaApuCatalogItem) -> str:
    status = (item.raw_data or {}).get("structure_status")
    return status.strip() if isinstance(status, str) and status.strip() else "review_required"


def _line_terms(line: QuantityTakeoffLine) -> set[str]:
    values = [
        line.ifc_class,
        line.category,
        line.family,
        line.type_name,
        line.instance_name,
        line.measurement_rule,
        str((line.raw_data or {}).get("ifc_predefined_type") or ""),
    ]
    return set().union(*(_tokens(value) for value in values), _ifc_hint(line.ifc_class))


def _ifc_hint(ifc_class: str) -> set[str]:
    normalized = _compact(ifc_class)
    hints = {
        "ifcwall": "muro pared concreto ladrillo mamposteria",
        "ifcwallstandardcase": "muro pared concreto ladrillo mamposteria",
        "ifcslab": "losa placa concreto piso cubierta",
        "ifccolumn": "columna concreto acero",
        "ifcbeam": "viga concreto acero",
        "ifcmember": "viga perfil acero miembro",
        "ifcplate": "placa panel lamina",
        "ifcdoor": "puerta",
        "ifcwindow": "ventana",
        "ifcroof": "cubierta teja",
        "ifcpipesegment": "tuberia tubo pvc hidraulica sanitaria",
    }
    return set(_tokens(hints.get(normalized, "")))


def _controlled_quantity(line: QuantityTakeoffLine) -> float:
    controlled = (line.raw_data or {}).get("controlled_measurement")
    if isinstance(controlled, dict):
        quantity = controlled.get("quantity")
        if isinstance(quantity, int | float) and float(quantity) > 0:
            return float(quantity)
    return float(line.quantity or 0)


def _controlled_unit(line: QuantityTakeoffLine) -> str:
    controlled = (line.raw_data or {}).get("controlled_measurement")
    if isinstance(controlled, dict):
        unit = controlled.get("unit")
        if isinstance(unit, str) and unit.strip():
            return unit.strip()
    return line.unit


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", _compact(value))
        if len(token) >= 3 and token not in {"para", "con", "sin", "incluye", "insumos"}
    }


def _clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str):
            cleaned[key] = _clean_text(value)
        elif isinstance(value, list):
            cleaned[key] = [_clean_row(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, dict):
            cleaned[key] = _clean_row(value)
        else:
            cleaned[key] = value
    return cleaned


def _compact(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _unit_key(unit: str) -> str:
    value = _compact(unit).replace(" ", "")
    aliases = {"und": "ea", "unidad": "ea", "un": "ea", "u": "ea"}
    return aliases.get(value, value)


def _money(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        return 0
    normalized = re.sub(r"[^0-9,.-]", "", raw)
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif normalized.count(".") > 1:
        normalized = normalized.replace(".", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return 0
