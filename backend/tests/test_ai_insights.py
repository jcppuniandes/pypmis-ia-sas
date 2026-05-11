from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_insights import AIInsightsError, generate_evm_insights


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
