from app.domain.models import KPI, Alert


class AIInsightService:
    def explain_project_variance(self, project_kpi: KPI, alerts: list[Alert]) -> str:
        red_alerts = [alert for alert in alerts if alert.severity == "red"]
        if red_alerts:
            return (
                "AI control brief: the project requires intervention. "
                f"SPI {project_kpi.spi} and CPI {project_kpi.cpi} indicate that the decision layer should prioritize "
                "critical-path recovery, commitment control and forensic preservation of evidence for impacted accounts."
            )

        return (
            "AI control brief: the project is inside primary EVM thresholds. "
            "Keep the CAPTURE-VALIDATE-ANALYZE loop active and focus on constraint removal before the next cut-off."
        )
