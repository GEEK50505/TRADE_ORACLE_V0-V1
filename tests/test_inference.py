import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_inference_module():
    sys.modules.setdefault(
        "google.generativeai",
        SimpleNamespace(configure=lambda **kwargs: None, GenerativeModel=lambda *args, **kwargs: None),
    )
    module_path = Path(__file__).resolve().parents[1] / "ai" / "inference.py"
    spec = importlib.util.spec_from_file_location("trade_oracle_ai_inference", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_deepseek_response_parsing_uses_first_choice():
    inference = _load_inference_module()
    AIOrchestrator = inference.AIOrchestrator

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "execute_trade": True,
                                    "asset_ticker": "AVAX/USDT",
                                    "conviction_score": 7.5,
                                    "entry_price": 41.25,
                                    "stop_loss": 39.22,
                                    "fractional_tps": [43.95, 46.98],
                                    "compliance_proof": "Mocked proof",
                                }
                            )
                        )
                    )
                ]
            )

    orchestrator = object.__new__(AIOrchestrator)
    orchestrator.model_provider = "deepseek"
    orchestrator.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    orchestrator.model_id = "deepseek-chat"

    result = asyncio.run(
        orchestrator.generate_optimal_setup(
            [
                {
                    "symbol": "AVAX/USDT",
                    "regime": "BULLISH",
                    "current_price": 41.25,
                    "atr": 1.35,
                }
            ]
        )
    )

    assert result is not None
    assert result.asset_ticker == "AVAX/USDT"
    assert result.execute_trade is True
    assert result.conviction_score == 7.5
