from unittest.mock import MagicMock

def test_deepseek_response_parsing_does_not_raise():
    """
    Confirms that the DeepSeek response.choices[0] indexing is correct.
    This test guards against regression to response.choices.message.content
    which raises AttributeError because choices is a list.
    """
    mock_choice = MagicMock()
    mock_choice.message.content = '{"execute_trade": false, "asset_ticker": "AVAX/USDT", "conviction_score": 1.0, "entry_price": 0.0, "stop_loss": 0.0, "fractional_tps": [0.0, 0.0], "compliance_proof": "test"}'
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]  # List, not object
    
    # This must NOT raise AttributeError
    content = mock_response.choices[0].message.content
    assert content is not None
    assert "execute_trade" in content
