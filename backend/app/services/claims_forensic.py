from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    Claim,
    ClaimEntitlementItem,
    ClaimImpactAnalysis,
    ContractNotice,
    Project,
    WorkflowStatus,
)


@dataclass
class DossierSignal:
    amount: float
    cost_detected: bool
    critical_path_detected: bool
    days: int
    delay_detected: bool
    evidence_detected: bool
    notice_detected: bool
    productivity_loss_percent: float


@dataclass
class ForensicDossierResult:
    created_claims: list[Claim]
    created_entitlement_items: list[ClaimEntitlementItem]
    created_impact_analyses: list[ClaimImpactAnalysis]
    created_notices: list[ContractNotice]
    readiness_score: float
    signals: list[str]
    source_files: list[str]
    summary: str


class ClaimsForensicDossierService:
    """Deterministic first-pass claim dossier screening.

    This keeps the current app independent from external AI, mail, drive or
    Firebase services while preserving an auditable claim register.
    """

    readable_suffixes = {".csv", ".ifc", ".json", ".md", ".txt", ".xml"}
    modes = {"review", "discovery", "rebuttal", "shielding", "interrogatory"}

    def __init__(self, db: Session):
        self.db = db

    def analyze(
        self,
        *,
        tenant_id: int,
        project_id: int,
        mode: str,
        uploads: list[tuple[str, bytes]],
    ) -> ForensicDossierResult:
        normalized_mode = mode if mode in self.modes else "review"
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not project:
            raise ValueError("Project not found")
        dossier_text, source_files = self._extract_upload_text(uploads)
        signal = self._detect_signal(dossier_text, source_files)
        claim = self._create_claim(tenant_id, project_id, project, normalized_mode, dossier_text, source_files, signal)
        items = self._create_entitlement_items(tenant_id, project_id, claim, signal, source_files)
        notices = self._create_notices(tenant_id, project_id, claim, signal, source_files)
        analyses = self._create_impact_analyses(tenant_id, project_id, claim, signal, source_files)
        readiness_score = self._readiness_score(items)
        return ForensicDossierResult(
            created_claims=[claim],
            created_entitlement_items=items,
            created_impact_analyses=analyses,
            created_notices=notices,
            readiness_score=readiness_score,
            signals=self._signal_labels(signal),
            source_files=source_files,
            summary=self._summary(normalized_mode, signal, source_files),
        )

    def _extract_upload_text(self, uploads: list[tuple[str, bytes]]) -> tuple[str, list[str]]:
        texts: list[str] = []
        source_files: list[str] = []
        for filename, payload in uploads:
            clean_name = filename or "dossier"
            source_files.append(clean_name)
            suffix = _suffix(clean_name)
            if suffix == ".zip":
                texts.extend(self._extract_zip_text(payload))
            elif suffix == ".docx":
                texts.append(self._extract_docx_text(payload))
            elif suffix in self.readable_suffixes:
                texts.append(_decode(payload))
            elif suffix == ".pdf":
                texts.append(f"PDF file registered: {clean_name}. Text extraction pending.")
            else:
                texts.append(f"File registered: {clean_name}.")
        merged = "\n".join(text for text in texts if text.strip()).strip()
        if not merged:
            merged = "No readable dossier text was found. Manual forensic review is required."
        return merged[:120_000], source_files

    def _extract_zip_text(self, payload: bytes) -> list[str]:
        texts: list[str] = []
        try:
            with ZipFile(BytesIO(payload)) as archive:
                for entry in archive.namelist():
                    if entry.endswith("/") or _suffix(entry) not in self.readable_suffixes | {".docx"}:
                        continue
                    entry_payload = archive.read(entry)
                    if _suffix(entry) == ".docx":
                        texts.append(self._extract_docx_text(entry_payload))
                    else:
                        texts.append(_decode(entry_payload))
        except BadZipFile:
            texts.append("Invalid ZIP dossier. Manual forensic review is required.")
        return texts

    def _extract_docx_text(self, payload: bytes) -> str:
        try:
            with ZipFile(BytesIO(payload)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        except (BadZipFile, KeyError):
            return "DOCX file registered. Text extraction failed."
        text = re.sub(r"<[^>]+>", " ", xml)
        return re.sub(r"\s+", " ", text).strip()

    def _detect_signal(self, text: str, source_files: list[str]) -> DossierSignal:
        normalized = _normalize(text)
        days = max((int(value) for value in re.findall(r"(\d{1,4})\s*(?:dias|days|calendar days|working days)", normalized)), default=0)
        amounts = [_parse_amount(value) for value in re.findall(r"(?:cop|usd|\$)\s*([0-9][0-9.,]*)", normalized)]
        percents = [
            float(value.replace(",", "."))
            for value in re.findall(r"(\d{1,2}(?:[,.]\d+)?)\s*%\s*(?:productividad|productivity|rendimiento)", normalized)
        ]
        notice_detected = _contains_any(normalized, ("notice", "notificacion", "notificación", "aviso", "comunicacion contractual"))
        delay_detected = _contains_any(normalized, ("delay", "delayed", "demora", "retraso", "prorroga", "eot", "extension of time"))
        critical_path_detected = _contains_any(normalized, ("critical path", "ruta critica", "ruta crítica", "cpm", "cronograma"))
        cost_detected = bool(amounts) or _contains_any(normalized, ("cost", "sobrecosto", "mayor valor", "quantum", "costo adicional"))
        evidence_detected = bool(source_files) or _contains_any(
            normalized,
            ("evidence", "soporte", "respaldo", "correspondence", "correspondencia", "bitacora", "schedule update"),
        )
        return DossierSignal(
            amount=max(amounts, default=0),
            cost_detected=cost_detected,
            critical_path_detected=critical_path_detected,
            days=days,
            delay_detected=delay_detected,
            evidence_detected=evidence_detected,
            notice_detected=notice_detected,
            productivity_loss_percent=max(percents, default=0),
        )

    def _create_claim(
        self,
        tenant_id: int,
        project_id: int,
        project: Project,
        mode: str,
        text: str,
        source_files: list[str],
        signal: DossierSignal,
    ) -> Claim:
        signal_name = "delay/cost" if signal.delay_detected and signal.cost_detected else "forensic"
        title = f"{project.code} claim dossier - {signal_name} review"
        if mode == "discovery":
            title = f"{project.code} potential compensable event"
        elif mode == "rebuttal":
            title = f"{project.code} claim rebuttal review"
        elif mode == "interrogatory":
            title = f"{project.code} claim questions register"
        claim = Claim(
            tenant_id=tenant_id,
            project_id=project_id,
            control_account_id=None,
            title=title[:220],
            causality=self._causality_text(signal, text),
            impact=self._impact_text(signal, project.currency),
            evidence_summary=f"Source file(s): {', '.join(source_files) or 'none'}",
            status=WorkflowStatus.analyzing,
        )
        self.db.add(claim)
        self.db.flush()
        return claim

    def _create_entitlement_items(
        self,
        tenant_id: int,
        project_id: int,
        claim: Claim,
        signal: DossierSignal,
        source_files: list[str],
    ) -> list[ClaimEntitlementItem]:
        drafts = [
            (
                "FIDIC / Contract Notice",
                "Notice and time bar",
                "Timely contractual notice",
                "Confirm notice was issued within the contractual period.",
                signal.notice_detected,
                signal.notice_detected,
            ),
            (
                "SCL Delay Protocol",
                "Causation",
                "Cause and effect narrative",
                "Link the event to a discrete project impact and affected activities.",
                signal.delay_detected or signal.cost_detected,
                signal.delay_detected and signal.cost_detected,
            ),
            (
                "AACE 29R-03",
                "Critical path",
                "Schedule impact method",
                "Demonstrate impact through CPM/TIA or accepted delay analysis method.",
                signal.critical_path_detected,
                signal.critical_path_detected and signal.days > 0,
            ),
            (
                "AACE 120R-21",
                "Quantum",
                "Cost and productivity substantiation",
                "Support direct cost, productivity loss or time-related cost with backup.",
                signal.cost_detected or signal.productivity_loss_percent > 0,
                signal.amount > 0 or signal.productivity_loss_percent > 0,
            ),
            (
                "Forensic Evidence",
                "Evidence",
                "Dossier completeness",
                "Keep correspondence, schedule updates, cost backup and decision trail linked to the claim.",
                bool(source_files),
                signal.evidence_detected,
            ),
        ]
        items: list[ClaimEntitlementItem] = []
        for index, (source, category, element, requirement, partial, satisfied) in enumerate(drafts, start=1):
            status = "satisfied" if satisfied else "partial" if partial else "gap"
            score = 1.0 if status == "satisfied" else 0.5 if status == "partial" else 0.0
            item = ClaimEntitlementItem(
                tenant_id=tenant_id,
                project_id=project_id,
                claim_id=claim.id,
                practice_source=source[:40],
                category=category,
                element=element,
                requirement=requirement,
                assessment=_assessment(status),
                evidence_ref=", ".join(source_files)[:260],
                status=status,
                weight=1,
                score=score,
                sequence_no=index,
            )
            self.db.add(item)
            items.append(item)
        self.db.flush()
        return items

    def _create_notices(
        self,
        tenant_id: int,
        project_id: int,
        claim: Claim,
        signal: DossierSignal,
        source_files: list[str],
    ) -> list[ContractNotice]:
        if not signal.notice_detected:
            return []
        notice = ContractNotice(
            tenant_id=tenant_id,
            project_id=project_id,
            contract_id=None,
            claim_id=claim.id,
            change_request_id=None,
            notice_type="claim notice",
            subject=f"Notice evidence detected for {claim.title}"[:260],
            reference=", ".join(source_files)[:120],
            event_date=None,
            notice_date=None,
            due_date=None,
            status="issued",
            days_late=0,
            compliance_status="compliant",
        )
        self.db.add(notice)
        self.db.flush()
        return [notice]

    def _create_impact_analyses(
        self,
        tenant_id: int,
        project_id: int,
        claim: Claim,
        signal: DossierSignal,
        source_files: list[str],
    ) -> list[ClaimImpactAnalysis]:
        if not (signal.delay_detected or signal.cost_detected or signal.productivity_loss_percent > 0):
            return []
        analysis = ClaimImpactAnalysis(
            tenant_id=tenant_id,
            project_id=project_id,
            claim_id=claim.id,
            method="AACE 29R-03 / TIA screening" if signal.delay_detected else "Quantum screening",
            impacted_activity="Critical path activity to be confirmed" if signal.critical_path_detected else "",
            cause="Detected from uploaded dossier keywords.",
            effect=self._impact_text(signal, "COP"),
            schedule_impact_days=signal.days,
            cost_impact=signal.amount,
            productivity_loss_percent=signal.productivity_loss_percent,
            evidence_ref=", ".join(source_files)[:260],
            confidence_score=self._confidence_score(signal),
            status="draft",
        )
        self.db.add(analysis)
        self.db.flush()
        return [analysis]

    def _readiness_score(self, items: list[ClaimEntitlementItem]) -> float:
        if not items:
            return 0
        return round((sum(item.score for item in items) / len(items)) * 100, 1)

    def _confidence_score(self, signal: DossierSignal) -> float:
        score = 0.2
        score += 0.2 if signal.notice_detected else 0
        score += 0.2 if signal.critical_path_detected else 0
        score += 0.2 if signal.amount > 0 else 0
        score += 0.2 if signal.days > 0 else 0
        return round(min(score, 1.0), 2)

    def _causality_text(self, signal: DossierSignal, text: str) -> str:
        if signal.delay_detected and signal.critical_path_detected:
            return "Dossier indicates delay impact requiring CPM/TIA validation. " + _excerpt(text)
        if signal.cost_detected:
            return "Dossier indicates cost or quantum exposure requiring backup validation. " + _excerpt(text)
        return "Dossier registered for manual causation review. " + _excerpt(text)

    def _impact_text(self, signal: DossierSignal, currency: str) -> str:
        parts: list[str] = []
        if signal.days:
            parts.append(f"{signal.days} day(s)")
        if signal.amount:
            parts.append(f"{currency} {signal.amount:,.0f}")
        if signal.productivity_loss_percent:
            parts.append(f"{signal.productivity_loss_percent:g}% productivity loss")
        return " / ".join(parts) if parts else "Impact not quantified yet"

    def _signal_labels(self, signal: DossierSignal) -> list[str]:
        labels: list[str] = []
        if signal.notice_detected:
            labels.append("notice")
        if signal.delay_detected:
            labels.append("delay")
        if signal.critical_path_detected:
            labels.append("critical_path")
        if signal.cost_detected:
            labels.append("cost")
        if signal.evidence_detected:
            labels.append("evidence")
        if signal.productivity_loss_percent:
            labels.append("productivity")
        return labels or ["manual_review"]

    def _summary(self, mode: str, signal: DossierSignal, source_files: list[str]) -> str:
        labels = ", ".join(self._signal_labels(signal))
        return (
            f"Forensic claim dossier run in {mode} mode. "
            f"Detected: {labels}. Sources: {len(source_files)} file(s)."
        )


def _assessment(status: str) -> str:
    if status == "satisfied":
        return "Evidence found in the dossier; validate against contract and source documents."
    if status == "partial":
        return "Partial signal found; complete supporting backup before claim approval."
    return "No reliable signal found; assign responsible reviewer."


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _decode(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return payload.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:320]


def _normalize(text: str) -> str:
    return text.lower().replace("\u00ed", "i").replace("\u00f3", "o").replace("\u00e1", "a")


def _parse_amount(raw: str) -> float:
    digits = re.sub(r"[^0-9]", "", raw)
    return float(digits) if digits else 0


def _suffix(filename: str) -> str:
    clean = filename.lower().split("?", 1)[0].split("#", 1)[0]
    index = clean.rfind(".")
    return clean[index:] if index >= 0 else ""
