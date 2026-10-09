from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.services.schedule_ingestion import ParsedActivity, ParsedRelationship, ParsedSchedule, ScheduleIngestionService


@dataclass(frozen=True)
class ForensicRagSource:
    title: str
    file_name: str
    source_type: str
    relevance: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WindowScheduleSource:
    file_name: str
    source: str
    status: str
    data_date: date | None = None
    baseline_name: str = ""
    activity_count: int = 0
    relationship_count: int = 0
    quality_score: float = 0
    finding_code: str = ""
    message: str = ""


@dataclass(frozen=True)
class WindowActivityDelta:
    activity_id: str
    activity_name: str
    wbs_code: str
    wbs_name: str
    start_slip_days: int
    finish_slip_days: int
    total_float_delta_days: float
    critical_in_start: bool
    critical_in_finish: bool
    classification: str
    # Tipo de variacion a nivel de actividad (ALV) segun SVP 2.4:
    # extended_duration, delayed_start, finish_slip o float_change.
    alv_type: str = ""


@dataclass(frozen=True)
class SourceValidationCheck:
    protocol: str
    check: str
    status: str
    detail: str


@dataclass(frozen=True)
class WindowLogicDelta:
    added_relationships: int
    removed_relationships: int
    changed_relationships: int


@dataclass(frozen=True)
class ForensicWindowResult:
    window_no: int
    start_schedule: str
    finish_schedule: str
    start_data_date: date | None
    finish_data_date: date | None
    start_completion: date | None
    finish_completion: date | None
    completion_slip_days: int
    critical_delay_days: int
    mitigation_days: int
    common_activity_count: int
    added_activity_count: int
    removed_activity_count: int
    delayed_activity_count: int
    critical_or_near_critical_delay_count: int
    logic_delta: WindowLogicDelta
    top_delay_events: list[WindowActivityDelta] = field(default_factory=list)
    interpretation: str = ""


@dataclass(frozen=True)
class ForensicWindowAnalysisResult:
    method_id: str
    method_name: str
    standard_reference: str
    methodology_note: str
    schedule_sources: list[WindowScheduleSource]
    windows: list[ForensicWindowResult]
    rag_sources: list[ForensicRagSource]
    summary: dict[str, int | float | str]
    limitations: list[str] = field(default_factory=list)
    source_validation: list[SourceValidationCheck] = field(default_factory=list)


class ForensicWindowAnalysisService:
    """AACE RP29R-03 MIP 3.7 screening over multiple schedule snapshots."""

    method_id = "AACE-RP29R-MIP-3.7"
    # El servicio compara updates de forma observacional; la simulacion aditiva
    # con fragnets del MIP 3.7 completo es una etapa posterior, por eso el
    # resultado se presenta como screening y no como el metodo terminado.
    method_name = "Screening de Ventanas 3.7 (paso previo al MIP 3.7 Multiple Base Additive)"
    standard_reference = "AACE RP29R-03 Forensic Schedule Analysis, Method Implementation Protocol 3.7"

    def __init__(self, schedule_service: ScheduleIngestionService | None = None) -> None:
        self.schedule_service = schedule_service or ScheduleIngestionService(None)  # type: ignore[arg-type]

    def analyze(
        self,
        uploads: list[tuple[str, bytes]],
        near_critical_threshold_days: float = 10,
    ) -> ForensicWindowAnalysisResult:
        parsed_sources: list[tuple[int, str, ParsedSchedule]] = []
        source_rows: list[WindowScheduleSource] = []
        for index, (file_name, content) in enumerate(uploads):
            parsed = self._parse_supported_source(file_name, content)
            if parsed is None:
                source_rows.append(
                    WindowScheduleSource(
                        file_name=file_name,
                        source="ms_project_mpp",
                        status="unsupported",
                        finding_code="MPP_BINARY_UNSUPPORTED",
                        message=(
                            "Binary MPP is not parsed directly yet. Export the schedule to Microsoft Project XML, "
                            "Primavera XML or XER for the 3.7 window analysis."
                        ),
                    )
                )
                continue
            status = "valid" if parsed.activities else "rejected"
            finding_code = "" if parsed.activities else "NO_ACTIVITIES"
            message = (
                parsed.validation_summary if parsed.activities else "No activities were parsed from this schedule."
            )
            source_rows.append(
                WindowScheduleSource(
                    file_name=file_name,
                    source=str(parsed.source),
                    status=status,
                    data_date=parsed.data_date,
                    baseline_name=parsed.baseline_name,
                    activity_count=len(parsed.activities),
                    relationship_count=len(parsed.relationships),
                    quality_score=parsed.quality_score,
                    finding_code=finding_code,
                    message=message,
                )
            )
            if parsed.activities:
                parsed_sources.append((index, file_name, parsed))

        parsed_sources.sort(key=lambda item: (item[2].data_date or date.max, item[0]))
        windows: list[ForensicWindowResult] = []
        for window_index, (_, start_name, start_schedule) in enumerate(parsed_sources[:-1], start=1):
            _, finish_name, finish_schedule = parsed_sources[window_index]
            windows.append(
                self._compare_window(
                    window_no=window_index,
                    start_name=start_name,
                    finish_name=finish_name,
                    start_schedule=start_schedule,
                    finish_schedule=finish_schedule,
                    near_critical_threshold_days=near_critical_threshold_days,
                )
            )

        total_delay = sum(window.critical_delay_days for window in windows)
        total_mitigation = sum(window.mitigation_days for window in windows)
        valid_schedules = len(parsed_sources)
        actual_dated_activities = sum(
            1
            for _, _, parsed in parsed_sources
            for activity in parsed.activities
            if activity.actual_start is not None or activity.actual_finish is not None
        )
        source_validation = self._source_validation(parsed_sources, actual_dated_activities)
        return ForensicWindowAnalysisResult(
            method_id=self.method_id,
            method_name=self.method_name,
            standard_reference=self.standard_reference,
            methodology_note=(
                "Screening based on AACE RP29R-03 MIP 3.7: schedules are ordered as multiple bases, "
                "each window compares the prior update with the next update, and CPM deltas identify "
                "candidate delay events before a formal fragnet insertion simulation."
            ),
            schedule_sources=source_rows,
            windows=windows,
            rag_sources=self._rag_sources(),
            summary={
                "valid_schedule_count": valid_schedules,
                "unsupported_schedule_count": len([row for row in source_rows if row.status == "unsupported"]),
                "window_count": len(windows),
                "total_critical_delay_days": total_delay,
                "total_mitigation_days": total_mitigation,
                "net_delay_days": total_delay - total_mitigation,
                "actual_dated_activity_count": actual_dated_activities,
            },
            limitations=self._limitations(valid_schedules),
            source_validation=source_validation,
        )

    def rag_sources(self) -> list[ForensicRagSource]:
        return self._rag_sources()

    def _source_validation(
        self,
        parsed_sources: list[tuple[int, str, ParsedSchedule]],
        actual_dated_activities: int,
    ) -> list[SourceValidationCheck]:
        """Checklist proporcional de los SVP de la RP 29R-03 sobre las fuentes cargadas."""

        checks: list[SourceValidationCheck] = []
        if not parsed_sources:
            return checks

        # SVP 2.1 - la primera base debe ser un modelo CPM funcional.
        _, base_name, base_schedule = parsed_sources[0]
        predecessor_ids = {relationship.predecessor for relationship in base_schedule.relationships}
        successor_ids = {relationship.successor for relationship in base_schedule.relationships}
        open_starts = [
            activity.external_id for activity in base_schedule.activities if activity.external_id not in successor_ids
        ]
        open_finishes = [
            activity.external_id for activity in base_schedule.activities if activity.external_id not in predecessor_ids
        ]
        open_ends = len(open_starts) + len(open_finishes)
        checks.append(
            SourceValidationCheck(
                protocol="SVP 2.1",
                check="Extremos abiertos en la base inicial",
                status="warn" if open_ends > 2 else "pass",
                detail=(
                    f"{base_name}: {len(open_starts)} actividad(es) sin predecesor y "
                    f"{len(open_finishes)} sin sucesor. La RP 29R espera lógica CPM continua "
                    "(un inicio y un fin abiertos son normales)."
                ),
            )
        )
        has_critical_path = any(activity.critical_path for activity in base_schedule.activities)
        checks.append(
            SourceValidationCheck(
                protocol="SVP 2.1",
                check="Ruta crítica presente en la base inicial",
                status="pass" if has_critical_path else "warn",
                detail=(
                    f"{base_name}: la base {'contiene' if has_critical_path else 'no contiene'} "
                    "actividades marcadas como críticas."
                ),
            )
        )

        # SVP 2.2 - contraste as-built: sin fechas reales no hay validacion de
        # la izquierda del data date.
        checks.append(
            SourceValidationCheck(
                protocol="SVP 2.2",
                check="Fechas reales disponibles para contraste as-built",
                status="pass" if actual_dated_activities else "warn",
                detail=(
                    f"{actual_dated_activities} actividad(es) con fechas reales parseadas. "
                    + (
                        "El contraste as-built de la izquierda del data date es posible."
                        if actual_dated_activities
                        else "Sin fechas reales el avance reportado no puede contrastarse con evidencia as-built."
                    )
                ),
            )
        )

        # SVP 2.3 - cadena de updates: data dates presentes y sin gaps largos.
        missing_data_dates = [name for _, name, parsed in parsed_sources if parsed.data_date is None]
        if missing_data_dates:
            checks.append(
                SourceValidationCheck(
                    protocol="SVP 2.3",
                    check="Data dates presentes en la cadena",
                    status="warn",
                    detail=f"Sin data date: {', '.join(missing_data_dates)}.",
                )
            )
        dated = [(name, parsed.data_date) for _, name, parsed in parsed_sources if parsed.data_date is not None]
        for (prior_name, prior_date), (next_name, next_date) in zip(dated, dated[1:], strict=False):
            gap_days = (next_date - prior_date).days
            if gap_days > 45:
                checks.append(
                    SourceValidationCheck(
                        protocol="SVP 2.3",
                        check="Continuidad de la cadena de updates",
                        status="warn",
                        detail=(
                            f"Gap de {gap_days} día(s) entre {prior_name} ({prior_date}) y "
                            f"{next_name} ({next_date}); la ventana pierde resolución contemporánea."
                        ),
                    )
                )
        if len(dated) >= 2 and not any(check.protocol == "SVP 2.3" for check in checks):
            checks.append(
                SourceValidationCheck(
                    protocol="SVP 2.3",
                    check="Continuidad de la cadena de updates",
                    status="pass",
                    detail="Data dates consecutivos sin gaps mayores a 45 días.",
                )
            )
        return checks

    def _parse_supported_source(self, file_name: str, content: bytes) -> ParsedSchedule | None:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".mpp" and not content.lstrip().startswith(b"<"):
            return None
        if suffix == ".mpp":
            return self.schedule_service.parse(f"{Path(file_name).stem}.xml", content)
        return self.schedule_service.parse(file_name, content)

    def _compare_window(
        self,
        window_no: int,
        start_name: str,
        finish_name: str,
        start_schedule: ParsedSchedule,
        finish_schedule: ParsedSchedule,
        near_critical_threshold_days: float,
    ) -> ForensicWindowResult:
        start_by_id = {activity.external_id: activity for activity in start_schedule.activities}
        finish_by_id = {activity.external_id: activity for activity in finish_schedule.activities}
        common_ids = sorted(set(start_by_id).intersection(finish_by_id))
        added_ids = set(finish_by_id).difference(start_by_id)
        removed_ids = set(start_by_id).difference(finish_by_id)

        deltas: list[WindowActivityDelta] = []
        for activity_id in common_ids:
            start_activity = start_by_id[activity_id]
            finish_activity = finish_by_id[activity_id]
            finish_slip = self._days_between(start_activity.planned_finish, finish_activity.planned_finish)
            start_slip = self._days_between(start_activity.planned_start, finish_activity.planned_start)
            float_delta = finish_activity.total_float_days - start_activity.total_float_days
            if finish_slip <= 0 and start_slip <= 0 and float_delta >= 0:
                continue
            classification = self._classify_delta(
                start_activity,
                finish_activity,
                finish_slip,
                near_critical_threshold_days,
            )
            deltas.append(
                WindowActivityDelta(
                    activity_id=activity_id,
                    activity_name=finish_activity.name or start_activity.name,
                    wbs_code=finish_activity.wbs_code or start_activity.wbs_code,
                    wbs_name=finish_activity.wbs_name or start_activity.wbs_name,
                    start_slip_days=start_slip,
                    finish_slip_days=finish_slip,
                    total_float_delta_days=round(float_delta, 2),
                    critical_in_start=start_activity.critical_path,
                    critical_in_finish=finish_activity.critical_path,
                    classification=classification,
                    alv_type=self._alv_type(start_activity, finish_activity, start_slip, finish_slip),
                )
            )

        top_delay_events = sorted(
            [
                delta
                for delta in deltas
                if delta.finish_slip_days > 0 and delta.classification in {"critical", "near_critical"}
            ],
            key=lambda item: (item.finish_slip_days, -abs(item.total_float_delta_days)),
            reverse=True,
        )[:10]
        logic_delta = self._logic_delta(start_schedule.relationships, finish_schedule.relationships)
        start_completion = self._completion_date(start_schedule.activities)
        finish_completion = self._completion_date(finish_schedule.activities)
        completion_slip = self._days_between(start_completion, finish_completion)
        critical_delay = max(completion_slip, 0)
        mitigation = max(-completion_slip, 0)
        return ForensicWindowResult(
            window_no=window_no,
            start_schedule=start_name,
            finish_schedule=finish_name,
            start_data_date=start_schedule.data_date,
            finish_data_date=finish_schedule.data_date,
            start_completion=start_completion,
            finish_completion=finish_completion,
            completion_slip_days=completion_slip,
            critical_delay_days=critical_delay,
            mitigation_days=mitigation,
            common_activity_count=len(common_ids),
            added_activity_count=len(added_ids),
            removed_activity_count=len(removed_ids),
            delayed_activity_count=len([delta for delta in deltas if delta.finish_slip_days > 0]),
            critical_or_near_critical_delay_count=len(top_delay_events),
            logic_delta=logic_delta,
            top_delay_events=top_delay_events,
            interpretation=self._interpret_window(completion_slip, top_delay_events, logic_delta),
        )

    def _alv_type(
        self,
        start_activity: ParsedActivity,
        finish_activity: ParsedActivity,
        start_slip_days: int,
        finish_slip_days: int,
    ) -> str:
        """Tipifica la Activity-Level Variance (SVP 2.4) entre dos updates.

        La duración se compara entre updates (no contra la línea base) para no
        acumular atrasos de predecesoras en la lectura de la variación.
        """

        start_span = self._days_between(start_activity.planned_start, start_activity.planned_finish)
        finish_span = self._days_between(finish_activity.planned_start, finish_activity.planned_finish)
        if finish_span > start_span:
            return "extended_duration"
        if start_slip_days > 0:
            return "delayed_start"
        if finish_slip_days > 0:
            return "finish_slip"
        return "float_change"

    def _classify_delta(
        self,
        start_activity: ParsedActivity,
        finish_activity: ParsedActivity,
        finish_slip_days: int,
        near_critical_threshold_days: float,
    ) -> str:
        if start_activity.critical_path or finish_activity.critical_path:
            return "critical"
        if finish_slip_days > 0 and (
            start_activity.total_float_days <= near_critical_threshold_days
            or finish_activity.total_float_days <= near_critical_threshold_days
        ):
            return "near_critical"
        if finish_slip_days > 0:
            return "non_critical_delay"
        return "float_change"

    def _logic_delta(
        self,
        start_relationships: list[ParsedRelationship],
        finish_relationships: list[ParsedRelationship],
    ) -> WindowLogicDelta:
        start_pairs = {(rel.predecessor, rel.successor): rel for rel in start_relationships}
        finish_pairs = {(rel.predecessor, rel.successor): rel for rel in finish_relationships}
        added_keys = set(finish_pairs).difference(start_pairs)
        removed_keys = set(start_pairs).difference(finish_pairs)
        changed = 0
        for key in set(start_pairs).intersection(finish_pairs):
            start = start_pairs[key]
            finish = finish_pairs[key]
            if start.relationship_type != finish.relationship_type or round(start.lag_days, 2) != round(
                finish.lag_days, 2
            ):
                changed += 1
        return WindowLogicDelta(
            added_relationships=len(added_keys),
            removed_relationships=len(removed_keys),
            changed_relationships=changed,
        )

    def _interpret_window(
        self,
        completion_slip_days: int,
        top_delay_events: list[WindowActivityDelta],
        logic_delta: WindowLogicDelta,
    ) -> str:
        if completion_slip_days > 0 and top_delay_events:
            return (
                f"The window shows {completion_slip_days} day(s) of completion slip. "
                f"The leading CPM candidate is {top_delay_events[0].activity_id}."
            )
        if completion_slip_days > 0:
            return f"The window shows {completion_slip_days} day(s) of completion slip without a parsed critical candidate."
        if completion_slip_days < 0:
            return f"The update recovers {-completion_slip_days} day(s) against the prior completion forecast."
        if logic_delta.added_relationships or logic_delta.removed_relationships or logic_delta.changed_relationships:
            return (
                "No completion slip is visible, but logic changes should be reviewed before relying on float movement."
            )
        return "No completion movement is visible in this window."

    def _completion_date(self, activities: list[ParsedActivity]) -> date | None:
        finishes = [activity.planned_finish for activity in activities if activity.planned_finish is not None]
        return max(finishes) if finishes else None

    def _days_between(self, start: date | None, finish: date | None) -> int:
        if start is None or finish is None:
            return 0
        return (finish - start).days

    def _limitations(self, valid_schedule_count: int) -> list[str]:
        limitations = [
            "The service compares parsed CPM updates and flags candidate causes; formal entitlement still needs cause-effect evidence.",
            "Full additive MIP 3.7 simulation requires validated delay fragnets inserted into each relevant base schedule.",
            "Binary MPP requires export to XML or an external converter before direct parsing.",
        ]
        if valid_schedule_count < 2:
            limitations.insert(0, "Upload at least two valid schedule snapshots to create forensic windows.")
        return limitations

    def _rag_sources(self) -> list[ForensicRagSource]:
        manifest_path = Path(__file__).resolve().parents[1] / "rag" / "aace29" / "window_analysis_sources.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return [ForensicRagSource(**item) for item in manifest]
        except (OSError, TypeError, ValueError):
            pass
        return [
            ForensicRagSource(
                title="AACE RP29R-03 Forensic Schedule Analysis",
                file_name="RP29R-03 Forensic Schedule Analysis.pdf",
                source_type="standard",
                relevance="Defines MIP 3.7 modeled/additive/multiple-base forensic schedule analysis.",
                tags=["AACE", "MIP 3.7", "windows", "forensic schedule analysis"],
            ),
            ForensicRagSource(
                title="Analisis de Ventanas",
                file_name="Analisis de Ventanas.pdf",
                source_type="user_rag",
                relevance="User-provided guide for structuring windows analysis and practical review outputs.",
                tags=["windows analysis", "schedule delay", "RAG"],
            ),
            ForensicRagSource(
                title="Instructivo Relacion Causa Efecto Modelado CPM",
                file_name="Instructivo_Relacion_Causa_Efecto_Modelado_CPM_AACE29R_120R_130R.docx",
                source_type="user_rag",
                relevance="Supports the cause-effect model and CPM impact traceability.",
                tags=["cause-effect", "CPM", "AACE"],
            ),
            ForensicRagSource(
                title="Hybrid Windows Analysis",
                file_name="Hybrid Windows Analysis .pdf",
                source_type="user_rag",
                relevance="Supports hybrid window interpretation when updates and modeled impacts coexist.",
                tags=["hybrid windows", "delay analysis"],
            ),
        ]
