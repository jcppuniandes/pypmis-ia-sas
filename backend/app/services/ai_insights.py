"""AI-powered Earned Value insights.

Two surfaces:

- ``AIInsightService`` — the legacy symbolic narrator still used by the
  dashboard endpoint. Kept for backwards compatibility while callers
  migrate to ``generate_evm_insights``.
- ``generate_evm_insights`` — pluggable EVM advisor. Selects between a
  graceful "disabled" template and the Anthropic Claude API based on
  configuration. Designed for unit testing via dependency injection of
  ``ai_provider``/``api_key`` so no live network call is needed in CI.
"""

from __future__ import annotations

from typing import Any

from app.domain.models import KPI, Alert


class AIInsightsError(Exception):
    """Raised when the AI insights call cannot complete."""


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


_SYSTEM_PROMPT = (
    "You are a project controls advisor specializing in AACE TCM and Earned Value Management. "
    "Analyze the EVM data provided and give a concise (3-5 bullet points) actionable recommendation "
    "for the project team. Focus on: schedule recovery options (SPI < 0.95), cost containment "
    "(CPI < 0.95), forecast accuracy, and re-baseline triggers. Be specific to the numbers given."
)

_DISABLED_TEMPLATE = (
    "EVM Analysis: SPI={spi:.2f}, CPI={cpi:.2f}. "
    "Schedule Variance: {sv:+,.0f}. Cost Variance: {cv:+,.0f}. "
    "EAC: {eac:,.0f} vs BAC: {bac:,.0f} (VAC: {vac:+,.0f}). "
    "Configure ANTHROPIC_API_KEY and AI_PROVIDER=claude for AI-powered recommendations."
)


def _format_evm_message(ctx: dict[str, Any]) -> str:
    return (
        f"Project: {ctx.get('project_code', 'Unknown')} | Period: {ctx.get('period', 'Unknown')}\n"
        f"SPI: {ctx.get('spi', 0):.3f} | CPI: {ctx.get('cpi', 0):.3f}\n"
        f"Schedule Variance: {ctx.get('sv', 0):+,.0f}\n"
        f"Cost Variance: {ctx.get('cv', 0):+,.0f}\n"
        f"BAC: {ctx.get('bac', 0):,.0f} | EAC: {ctx.get('eac', 0):,.0f} | VAC: {ctx.get('vac', 0):+,.0f}\n"
        "\nProvide your AACE-aligned recommendations:"
    )


def generate_evm_insights(
    evm_context: dict[str, Any],
    ai_provider: str = "disabled",
    api_key: str = "",
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 1024,
    timeout: int = 30,
) -> str:
    if ai_provider != "claude":
        return _DISABLED_TEMPLATE.format(
            **{k: evm_context.get(k, 0) for k in ("spi", "cpi", "sv", "cv", "eac", "bac", "vac")}
        )

    if not api_key:
        raise AIInsightsError("ANTHROPIC_API_KEY is required when AI_PROVIDER=claude")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        user_message = _format_evm_message(evm_context)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text
    except AIInsightsError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any SDK/network failure as AIInsightsError
        raise AIInsightsError(f"AI insights request failed: {exc}") from exc
