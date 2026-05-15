from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_insights import AIInsightsError, generate_control_agent_synthesis, generate_evm_insights


SAMPLE_EVM_CONTEXT = {
    "project_code": "PRJ-001",
    "period": "2024-Q1",
    "spi": 0.87,
    "cpi": 0.92,
    "sv": -150000.0,
    "cv": -80000.0,
    "eac": 5200000.0,
    "bac": 5000000.0,
    "vac": -200000.0,
}


def test_generate_insights_disabled_returns_template() -> None:
    result = generate_evm_insights(SAMPLE_EVM_CONTEXT, ai_provider="disabled")
    assert "SPI=0.87" in result
    assert "CPI=0.92" in result
    assert "ANTHROPIC_API_KEY" in result


def test_generate_insights_claude_requires_api_key() -> None:
    with pytest.raises(AIInsightsError, match="ANTHROPIC_API_KEY"):
        generate_evm_insights(SAMPLE_EVM_CONTEXT, ai_provider="claude", api_key="")


def test_generate_insights_calls_claude_api() -> None:
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="SPI of 0.87 indicates schedule delay. Recommend rebaseline review.")]

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_message

        result = generate_evm_insights(
            SAMPLE_EVM_CONTEXT,
            ai_provider="claude",
            api_key="sk-ant-test",
        )

    assert "SPI of 0.87" in result
    mock_client.messages.create.assert_called_once()


def test_generate_insights_wraps_api_exception() -> None:
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("upstream timeout")

        with pytest.raises(AIInsightsError, match="upstream timeout"):
            generate_evm_insights(SAMPLE_EVM_CONTEXT, ai_provider="claude", api_key="sk-ant-test")


def test_control_agent_synthesis_disabled_returns_empty_string() -> None:
    result = generate_control_agent_synthesis(
        {
            "agent_name": "AI Control Auditor",
            "summary": "Control Audit Agent found 2 findings.",
            "findings": [{"severity": "high", "title": "BP policy missing"}],
        },
        ai_provider="disabled",
    )

    assert result == ""


def test_control_agent_synthesis_calls_low_cost_model() -> None:
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Prioritize BP policy closure before draft AWP release.")]

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_message

        result = generate_control_agent_synthesis(
            {
                "agent_name": "AI Control Auditor",
                "summary": "Senior AWP Packaging Advisor created 3 draft AWP package(s).",
                "findings": [{"severity": "info", "title": "Created draft CWP CWP-100"}],
            },
            ai_provider="claude",
            api_key="sk-ant-test",
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
        )

    assert "Prioritize BP policy closure" in result
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 256
