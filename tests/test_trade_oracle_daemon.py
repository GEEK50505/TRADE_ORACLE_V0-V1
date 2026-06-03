"""Tests for the single-runtime TRADE_ORACLE daemon."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from ai.langgraph_orchestrator import LangGraphEvaluationResult, LangGraphExecutionCandidate
from ai.trade_oracle_daemon import (
    TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY,
    HttpxTelegramBotClient,
    TradeOracleSingleRuntimeDaemon,
    _try_acquire_cycle_lock,
)
from ai.trade_oracle_storage import (
    build_trade_oracle_benchmark_store,
    build_trade_oracle_runtime_state_store,
)


def _db_path(label: str) -> str:
    return f"results/test_trade_oracle_daemon_{label}_{uuid4().hex}.sqlite"


def test_cycle_lock_blocks_overlap_and_releases():
    lock_path = Path(f"results/test_trade_oracle_cycle_lock_{uuid4().hex}.lock")

    first_lock = _try_acquire_cycle_lock(lock_path, stale_seconds=3600)
    assert first_lock is not None
    assert _try_acquire_cycle_lock(lock_path, stale_seconds=3600) is None

    first_lock.release()
    second_lock = _try_acquire_cycle_lock(lock_path, stale_seconds=3600)
    assert second_lock is not None
    second_lock.release()
    lock_path.unlink(missing_ok=True)


def test_cycle_lock_reclaims_dead_owner_lock():
    lock_path = Path(f"results/test_trade_oracle_dead_owner_cycle_lock_{uuid4().hex}.lock")
    lock_path.write_text('{"pid": 999999, "created_at_epoch": 1}', encoding="utf-8")

    recovered_lock = _try_acquire_cycle_lock(lock_path, stale_seconds=3600)
    assert recovered_lock is not None

    recovered_lock.release()
    lock_path.unlink(missing_ok=True)


class _FakeStateManager:
    def __init__(self, high_watermark: float):
        self.high_watermark = high_watermark

    def update_high_watermark(self, _current_equity: float) -> float:
        return self.high_watermark


class _FakeTelegramClient:
    def __init__(self, updates=None):
        self.review_requests: list[dict[str, str]] = []
        self.messages: list[dict[str, str]] = []
        self.edits: list[dict[str, str]] = []
        self.callback_answers: list[dict[str, str]] = []
        self.updates = list(updates or [])
        self.fetch_offsets: list[int | None] = []

    async def send_review_request(self, *, chat_id: str, text: str, thread_id: str) -> str:
        self.review_requests.append({"chat_id": chat_id, "text": text, "thread_id": thread_id})
        return "101"

    async def send_message(self, *, chat_id: str, text: str) -> str:
        self.messages.append({"chat_id": chat_id, "text": text})
        return "202"

    async def edit_review_message(self, *, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    async def answer_callback_query(self, *, callback_query_id: str, text: str = "") -> None:
        self.callback_answers.append({"callback_query_id": callback_query_id, "text": text})

    async def fetch_updates(self, *, offset: int | None, timeout: int):
        self.fetch_offsets.append(offset)
        updates = list(self.updates)
        self.updates = []
        return updates


class _FakeExecutionClient:
    def __init__(self, *, equity: float = 5200.0, active_trades: int = 0, transmit_result: bool = True):
        self.equity = equity
        self.active_trades = active_trades
        self.transmit_result = transmit_result
        self.transmit_calls: list[dict[str, object]] = []

    async def authenticate(self):
        return True

    async def get_platform_details(self):
        return {"equity": self.equity, "active_trades": self.active_trades}

    async def transmit_limit_order(self, **kwargs):
        self.transmit_calls.append(dict(kwargs))
        return self.transmit_result

    async def shutdown(self):
        return None


class _FakeHttpxResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self.payload = payload or {}
        self.request = httpx.Request("POST", "https://api.telegram.org/botfake/answerCallbackQuery")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}'",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self.payload


class _FakeHttpxClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def post(self, *_args, **_kwargs):
        self.calls += 1
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    async def aclose(self):
        return None


class _FakePendingReviewOrchestrator:
    async def evaluate_batch(self, *args, **kwargs):
        return [
            LangGraphEvaluationResult(
                status="pending_review",
                thread_id="thread-pending-001",
                interrupted=True,
                review_required=True,
                raw_setup={"asset_ticker": "AVAX/USDT", "localized_atr": 1.25},
                review_context={"reason": "human gate"},
                candidate=LangGraphExecutionCandidate(
                    execute_trade=False,
                    symbol="AVAX/USDT",
                    direction="BUY",
                    entry_price=41.25,
                    stop_loss=39.5,
                    take_profit=44.0,
                    size_tokens=0.0,
                    confidence=0.78,
                    execution_status="pending_review",
                    review_required=True,
                    thread_id="thread-pending-001",
                ),
            )
        ]


class _FakeResumeOrchestrator:
    async def resume_review(self, *args, **kwargs):
        return LangGraphEvaluationResult(
            status="completed",
            thread_id="thread-resume-001",
            interrupted=True,
            review_required=False,
            raw_setup={"asset_ticker": "DOGE/USDT", "localized_atr": 0.02},
            review_context={"reason": "telegram gate"},
            candidate=LangGraphExecutionCandidate(
                execute_trade=True,
                symbol="DOGE/USDT",
                direction="BUY",
                entry_price=0.2,
                stop_loss=0.17,
                take_profit=0.24,
                size_tokens=500.0,
                confidence=0.82,
                execution_status="approved",
                execution_tp_mode="tp1_only",
                review_required=False,
                position_sizing={
                    "tokens": 500.0,
                    "entry_price": 0.2,
                    "stop_loss": 0.17,
                    "tp1": 0.24,
                    "tp2": 0.27,
                    "usd_value": 100.0,
                },
                thread_id="thread-resume-001",
            ),
        )


class _FakeAutoApproveOrchestrator:
    async def evaluate_batch(self, *args, **kwargs):
        return [
            LangGraphEvaluationResult(
                status="completed",
                thread_id="thread-auto-approve-001",
                interrupted=True,
                review_required=False,
                raw_setup={"asset_ticker": "DOGE/USDT", "localized_atr": 0.02},
                review_context={"reason": "auto approved"},
                candidate=LangGraphExecutionCandidate(
                    execute_trade=True,
                    symbol="DOGE/USDT",
                    direction="BUY",
                    entry_price=0.2,
                    stop_loss=0.17,
                    take_profit=0.24,
                    size_tokens=500.0,
                    confidence=0.82,
                    execution_status="approved",
                    execution_tp_mode="tp1_only",
                    review_required=False,
                    position_sizing={
                        "tokens": 500.0,
                        "entry_price": 0.2,
                        "stop_loss": 0.17,
                        "tp1": 0.24,
                        "tp2": 0.27,
                        "usd_value": 100.0,
                    },
                    thread_id="thread-auto-approve-001",
                ),
            )
        ]


class _ExplodingResumeOrchestrator:
    async def resume_review(self, *args, **kwargs):
        raise AssertionError("Resolved reviews must not be resumed again.")


async def _fake_scanner_runner(_watchlist):
    return [{"symbol": "AVAX/USDT", "regime": "BULLISH", "current_price": 41.25, "atr": 1.25}]


async def _exploding_scanner_runner(_watchlist):
    raise AssertionError("Open reviews should block new scanner cycles.")


def test_daemon_run_cycle_once_persists_pending_review_and_journal():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("runtime_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient()

    client = _FakeExecutionClient()

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_FakePendingReviewOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["AVAX/USDT"],
        state_manager_factory=lambda: _FakeStateManager(5300.0),
    )

    import asyncio

    result = asyncio.run(daemon.run_cycle_once())

    pending_review = runtime_state_store.get_pending_review("thread-pending-001")
    journal = runtime_state_store.get_forward_journal_entry(result.cycle_id)

    assert result.outcome == "pending_review"
    assert pending_review is not None
    assert pending_review.telegram_message_id == "101"
    assert pending_review.review_status == "pending"
    assert journal is not None
    assert journal.pending_review is True
    assert telegram_client.review_requests[0]["thread_id"] == "thread-pending-001"


def test_daemon_process_callback_query_resolves_review_and_transmits():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("resume_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("resume_benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient()
    client = _FakeExecutionClient(transmit_result=True)

    runtime_state_store.upsert_pending_review(
        {
            "thread_id": "thread-resume-001",
            "cycle_id": "cycle-resume-001",
            "run_id": "trade_oracle_seed",
            "telegram_chat_id": "6323801206",
            "telegram_message_id": "101",
            "symbol": "DOGE/USDT",
            "direction": "BUY",
            "candidate": {"symbol": "DOGE/USDT"},
            "review_context": {"reason": "telegram gate"},
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 0,
                "source": "pytest",
            },
            "review_status": "pending",
            "review_action": "PENDING",
        }
    )

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_FakeResumeOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
        state_manager_factory=lambda: _FakeStateManager(5300.0),
    )

    callback_query = {
        "id": "cb_001",
        "data": "approve:thread-resume-001",
        "from": {"username": "openclaw"},
    }

    import asyncio

    result = asyncio.run(daemon.process_callback_query(callback_query))

    pending_review = runtime_state_store.get_pending_review("thread-resume-001")
    journal = runtime_state_store.get_forward_journal_entry("cycle-resume-001")
    cycle_events = benchmark_store.list_cycle_events("cycle-resume-001", limit=20)

    assert result is not None
    assert result.outcome == "resume_execution_result"
    assert pending_review is not None
    assert pending_review.review_status == "resolved"
    assert pending_review.review_action == "APPROVE"
    assert pending_review.cycle_outcome == "resume_execution_result"
    assert journal is not None
    assert journal.transmit_succeeded is True
    assert any(event.event_type == "super_brain_resume" for event in cycle_events)
    assert any(event.event_type == "order_transmit_result" and event.decision == "transmitted" for event in cycle_events)
    assert telegram_client.callback_answers[0]["callback_query_id"] == "cb_001"
    assert "resume_execution_result" in telegram_client.edits[0]["text"]


def test_daemon_run_cycle_once_transmits_when_review_is_auto_approved():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("auto_approve_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("auto_approve_benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient()
    client = _FakeExecutionClient(transmit_result=True)

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_FakeAutoApproveOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
        state_manager_factory=lambda: _FakeStateManager(5300.0),
    )

    result = asyncio.run(daemon.run_cycle_once())

    assert result.outcome == "execution_result"
    assert result.transmitted is True
    assert client.transmit_calls != []
    assert telegram_client.review_requests == []
    assert runtime_state_store.list_pending_reviews(limit=20) == []


def test_daemon_blocks_approved_resume_when_circuit_breaker_triggers_during_review_window():
    """
    Regression test:
    - Telegram approves an existing pending review
    - During the review window, account drawdown now crosses the 2.5% hard circuit breaker
    - The daemon must NOT execute the approved trade
    - The pending review is resolved with cycle_outcome="halted_circuit_breaker"
    - Telegram receives circuit-breaker alerts
    """
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("cb_halt_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("cb_halt_benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient()

    # Trigger: high_watermark=5300, balance=5160 => drawdown=140 => 140/5300=2.641% >= 2.5%
    client = _FakeExecutionClient(equity=5160.0, active_trades=0, transmit_result=True)

    # If resume_review is called, this test should fail loudly.
    orchestrator = _ExplodingResumeOrchestrator()

    runtime_state_store.upsert_pending_review(
        {
            "thread_id": "thread-resume-cb-001",
            "cycle_id": "cycle-resume-cb-001",
            "run_id": "trade_oracle_seed",
            "telegram_chat_id": "6323801206",
            "telegram_message_id": "101",
            "symbol": "DOGE/USDT",
            "direction": "BUY",
            "candidate": {"symbol": "DOGE/USDT"},
            "review_context": {"reason": "telegram gate"},
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 0,
                "source": "pytest",
            },
            "review_status": "pending",
            "review_action": "PENDING",
        }
    )

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=orchestrator,
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
        state_manager_factory=lambda: _FakeStateManager(5300.0),
    )

    callback_query = {
        "id": "cb_cbhalt_001",
        "data": "approve:thread-resume-cb-001",
        "from": {"username": "openclaw"},
    }

    import asyncio

    result = asyncio.run(daemon.process_callback_query(callback_query))

    assert result is not None
    assert result.outcome == "halted_circuit_breaker"
    assert client.transmit_calls == []

    pending_review = runtime_state_store.get_pending_review("thread-resume-cb-001")
    assert pending_review is not None
    assert pending_review.review_status == "resolved"
    assert pending_review.review_action == "APPROVE"
    assert pending_review.cycle_outcome == "halted_circuit_breaker"

    # First: callback answer should happen
    assert telegram_client.callback_answers[0]["callback_query_id"] == "cb_cbhalt_001"
    assert "received" in telegram_client.callback_answers[0]["text"].lower()

    # Then: Telegram alert(s) for circuit breaker should be sent
    assert any("CIRCUIT BREAKER TRIGGERED" in msg["text"] for msg in telegram_client.messages)
    assert any("Approved trade was NOT executed" in msg["text"] for msg in telegram_client.messages)


def test_daemon_persists_telegram_update_offset_and_reloads_after_restart():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("cursor_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("cursor_benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient(
        updates=[
            {
                "update_id": 42,
                "callback_query": {
                    "id": "cb_cursor_001",
                    "data": "unsupported:thread-missing",
                    "from": {"username": "openclaw"},
                },
            }
        ]
    )
    client = _FakeExecutionClient()

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_ExplodingResumeOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
    )

    import asyncio

    processed = asyncio.run(daemon.poll_telegram_once())
    checkpoint = runtime_state_store.get_daemon_checkpoint(TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY)

    assert processed == 1
    assert daemon.telegram_update_offset == 43
    assert checkpoint is not None
    assert checkpoint.checkpoint_value["offset"] == 43

    restarted_client = _FakeTelegramClient()
    restarted_daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_ExplodingResumeOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=restarted_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
    )
    asyncio.run(restarted_daemon.poll_telegram_once())

    assert restarted_daemon.telegram_update_offset == 43
    assert restarted_client.fetch_offsets == [43]


def test_httpx_telegram_client_ignores_stale_callback_answer_400():
    telegram_client = HttpxTelegramBotClient("fake-token")
    telegram_client.client = _FakeHttpxClient([_FakeHttpxResponse(status_code=400)])

    asyncio.run(
        telegram_client.answer_callback_query(
            callback_query_id="stale-callback-id",
            text="Approve received.",
        )
    )


def test_httpx_telegram_client_retries_fetch_updates_then_succeeds():
    telegram_client = HttpxTelegramBotClient("fake-token")
    telegram_client.client = _FakeHttpxClient(
        [
            httpx.ConnectError("temporary dns failure"),
            _FakeHttpxResponse(
                status_code=200,
                payload={"result": [{"update_id": 15, "callback_query": {"id": "cb_15"}}]},
            ),
        ]
    )

    updates = asyncio.run(telegram_client.fetch_updates(offset=10, timeout=1))

    assert len(updates) == 1
    assert telegram_client.client.calls == 2


def test_httpx_telegram_client_returns_empty_updates_after_retryable_failure():
    telegram_client = HttpxTelegramBotClient("fake-token")
    telegram_client.client = _FakeHttpxClient(
        [
            httpx.ConnectError("temporary dns failure"),
            httpx.ConnectError("temporary dns failure"),
            httpx.ConnectError("temporary dns failure"),
        ]
    )

    updates = asyncio.run(telegram_client.fetch_updates(offset=10, timeout=1))

    assert updates == []
    assert telegram_client.client.calls == telegram_client.request_attempts


def test_httpx_telegram_client_returns_empty_updates_after_409_conflict():
    telegram_client = HttpxTelegramBotClient("fake-token")
    telegram_client.client = _FakeHttpxClient(
        [
            _FakeHttpxResponse(status_code=409),
            _FakeHttpxResponse(status_code=409),
            _FakeHttpxResponse(status_code=409),
        ]
    )

    updates = asyncio.run(telegram_client.fetch_updates(offset=10, timeout=1))

    assert updates == []
    assert telegram_client.client.calls == telegram_client.request_attempts


def test_daemon_ignores_replayed_callback_after_review_is_resolved():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("replay_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("replay_benchmark"),
        backend="sqlite",
    )
    telegram_client = _FakeTelegramClient()
    client = _FakeExecutionClient(transmit_result=True)

    runtime_state_store.upsert_pending_review(
        {
            "thread_id": "thread-replay-001",
            "cycle_id": "cycle-replay-001",
            "run_id": "trade_oracle_seed",
            "telegram_chat_id": "6323801206",
            "telegram_message_id": "101",
            "symbol": "DOGE/USDT",
            "direction": "BUY",
            "candidate": {"symbol": "DOGE/USDT"},
            "review_context": {"reason": "telegram gate"},
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 0,
                "source": "pytest",
            },
            "review_status": "resolved",
            "review_action": "APPROVE",
            "cycle_outcome": "resume_execution_result",
        }
    )

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_ExplodingResumeOrchestrator(),
        scanner_runner=_fake_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id="6323801206",
        watchlist=["DOGE/USDT"],
    )

    callback_query = {
        "id": "cb_replay_001",
        "data": "approve:thread-replay-001",
        "from": {"username": "openclaw"},
    }

    import asyncio

    result = asyncio.run(daemon.process_callback_query(callback_query))

    assert result is None
    assert client.transmit_calls == []
    assert telegram_client.callback_answers[0]["callback_query_id"] == "cb_replay_001"
    assert "already resolved" in telegram_client.callback_answers[0]["text"]


def test_daemon_skips_cycle_when_telegram_sent_review_exists():
    runtime_state_store = build_trade_oracle_runtime_state_store(
        _db_path("telegram_sent_state"),
        backend="sqlite",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        _db_path("telegram_sent_benchmark"),
        backend="sqlite",
    )
    client = _FakeExecutionClient()
    runtime_state_store.upsert_pending_review(
        {
            "thread_id": "thread-telegram-sent-001",
            "cycle_id": "cycle-telegram-sent-001",
            "run_id": "trade_oracle_seed",
            "telegram_chat_id": "6323801206",
            "telegram_message_id": "101",
            "symbol": "SOL/USDT",
            "direction": "BUY",
            "candidate": {"symbol": "SOL/USDT"},
            "review_context": {"reason": "telegram sent"},
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 0,
                "source": "pytest",
            },
            "review_status": "telegram_sent",
            "review_action": "PENDING",
        }
    )

    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_FakePendingReviewOrchestrator(),
        scanner_runner=_exploding_scanner_runner,
        execution_client_factory=lambda: client,
        execution_backend="mt5",
        telegram_client=_FakeTelegramClient(),
        telegram_chat_id="6323801206",
        watchlist=["SOL/USDT"],
    )

    import asyncio

    result = asyncio.run(daemon.run_cycle_once())

    assert result.outcome == "skipped_pending_review"
    assert result.pending_review_count == 1
    assert result.thread_ids == ["thread-telegram-sent-001"]
