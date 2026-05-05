from app.domain.models import AlertSeverity
from app.services.evm import EVMResult


class EarlyWarningService:
    def evaluate(self, kpi: EVMResult, productivity_index: float | None = None) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []

        if kpi.spi < 0.9:
            alerts.append(
                {
                    "severity": AlertSeverity.red.value,
                    "rule": "SPI < 0.9",
                    "message": f"Schedule performance is below control threshold: SPI {kpi.spi}.",
                    "recommendation": "Run lookahead recovery, validate critical path drivers and escalate constraints.",
                }
            )

        if kpi.cpi < 0.9:
            alerts.append(
                {
                    "severity": AlertSeverity.red.value,
                    "rule": "CPI < 0.9",
                    "message": f"Cost performance is below control threshold: CPI {kpi.cpi}.",
                    "recommendation": "Freeze discretionary commitments and perform account-level variance analysis.",
                }
            )

        if productivity_index is not None and productivity_index < 0.85:
            alerts.append(
                {
                    "severity": AlertSeverity.amber.value,
                    "rule": "Low productivity",
                    "message": f"Installed quantity per labor hour is trending low: index {productivity_index:.2f}.",
                    "recommendation": "Validate crew composition, workface readiness and material availability.",
                }
            )

        if not alerts:
            alerts.append(
                {
                    "severity": AlertSeverity.green.value,
                    "rule": "Within thresholds",
                    "message": "Control account is operating inside current EVM thresholds.",
                    "recommendation": "Continue monitoring in the next control cycle.",
                }
            )

        return alerts
