from app.services.forensic_window_analysis import ForensicWindowAnalysisService


def test_window_analysis_37_detects_critical_delay_between_xer_updates() -> None:
    baseline = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t2026-01-01 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%R\t10\t1\t10\tN\t1\tENG\tIngenieria
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t10\tA100\tDiseno critico\t2026-01-01 08:00\t2026-01-10 17:00\t0
%R\t200\t10\tA200\tConstruccion critica\t2026-01-11 08:00\t2026-01-20 17:00\t0
%T\tTASKPRED
%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\t1\t200\t100\tPR_FS\t0
"""
    update = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t2026-01-11 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%R\t10\t1\t10\tN\t1\tENG\tIngenieria
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t10\tA100\tDiseno critico\t2026-01-01 08:00\t2026-01-14 17:00\t0
%R\t200\t10\tA200\tConstruccion critica\t2026-01-15 08:00\t2026-01-25 17:00\t0
%T\tTASKPRED
%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\t1\t200\t100\tPR_FS\t0
"""

    result = ForensicWindowAnalysisService().analyze(
        uploads=[("baseline.xer", baseline), ("update-01.xer", update)],
        near_critical_threshold_days=5,
    )

    assert result.method_id == "AACE-RP29R-MIP-3.7"
    assert len(result.windows) == 1
    window = result.windows[0]
    assert window.completion_slip_days == 5
    assert window.critical_delay_days == 5
    assert window.mitigation_days == 0
    assert window.top_delay_events[0].activity_id == "A200"
    assert window.top_delay_events[0].finish_slip_days == 5
    assert result.summary["total_critical_delay_days"] == 5
    assert result.rag_sources


def test_window_analysis_37_reports_source_validation_and_alv_types() -> None:
    # Base: A200 sin sucesor (extremo abierto SVP 2.1); duraciones A100 10d, A200 10d.
    baseline = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t2026-01-01 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%R\t10\t1\t10\tN\t1\tENG\tIngenieria
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\tact_start_date\tact_end_date
%R\t100\t10\tA100\tDiseno critico\t2026-01-01 08:00\t2026-01-10 17:00\t0\t\t
%R\t200\t10\tA200\tConstruccion critica\t2026-01-11 08:00\t2026-01-20 17:00\t0\t\t
%R\t300\t10\tA300\tActividad suelta sin logica\t2026-01-05 08:00\t2026-01-08 17:00\t400\t\t
%T\tTASKPRED
%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\t1\t200\t100\tPR_FS\t0
"""
    # Update con gap de data date > 45 dias (SVP 2.3), A100 con fechas reales
    # (SVP 2.2), A100 con mayor duracion (10d -> 18d, extended_duration) y A200
    # desplazada sin crecer (delayed_start).
    update = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t2026-03-15 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%R\t10\t1\t10\tN\t1\tENG\tIngenieria
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\tact_start_date\tact_end_date
%R\t100\t10\tA100\tDiseno critico\t2026-01-01 08:00\t2026-01-18 17:00\t0\t2026-01-01 08:00\t
%R\t200\t10\tA200\tConstruccion critica\t2026-01-19 08:00\t2026-01-28 17:00\t0\t\t
%R\t300\t10\tA300\tActividad suelta sin logica\t2026-01-05 08:00\t2026-01-08 17:00\t400\t\t
%T\tTASKPRED
%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\t1\t200\t100\tPR_FS\t0
"""

    result = ForensicWindowAnalysisService().analyze(
        uploads=[("baseline.xer", baseline), ("update-01.xer", update)],
        near_critical_threshold_days=5,
    )

    assert result.method_name.lower().startswith("screening")
    checks_by_protocol: dict[str, list[str]] = {}
    for check in result.source_validation:
        checks_by_protocol.setdefault(check.protocol, []).append(check.status)
    # SVP 2.1: extremo abierto (A200 sin sucesor) debe generar advertencia.
    assert "warn" in checks_by_protocol.get("SVP 2.1", [])
    # SVP 2.3: gap de data dates de 73 dias debe generar advertencia.
    assert "warn" in checks_by_protocol.get("SVP 2.3", [])
    # SVP 2.2: hay al menos una actividad con fecha real parseada.
    assert result.summary["actual_dated_activity_count"] >= 1
    assert "pass" in checks_by_protocol.get("SVP 2.2", [])

    deltas_by_id = {delta.activity_id: delta for delta in result.windows[0].top_delay_events}
    assert deltas_by_id["A100"].alv_type == "extended_duration"
    assert deltas_by_id["A200"].alv_type == "delayed_start"


def test_window_analysis_37_warns_when_no_actual_dates_are_available() -> None:
    schedule = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tPY-01\t2026-01-01 08:00\tCOP
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t1\tY\t\tPY-01\tProyecto
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t1\tA100\tDiseno\t2026-01-01 08:00\t2026-01-10 17:00\t0
"""
    result = ForensicWindowAnalysisService().analyze(uploads=[("only.xer", schedule)])

    svp22 = [check for check in result.source_validation if check.protocol == "SVP 2.2"]
    assert svp22 and svp22[0].status == "warn"
    assert result.summary["actual_dated_activity_count"] == 0


def test_window_analysis_37_flags_binary_mpp_as_unsupported_until_converter_exists() -> None:
    result = ForensicWindowAnalysisService().analyze(uploads=[("schedule.mpp", b"\xd0\xcf\x11\xe0binary")])

    assert result.schedule_sources[0].status == "unsupported"
    assert result.schedule_sources[0].finding_code == "MPP_BINARY_UNSUPPORTED"
    assert result.windows == []
